"""Atributos estruturados de ``tem_canal_titular``, extraidos da evidencia bruta.

Este modulo e a IMPLEMENTACAO CANONICA da extracao. O programa que constroi a
matriz de atributos para o ajuste o importa, e o plugin de classificacao o importa
tambem: treino e uso executam o mesmo codigo, pela mesma razao que vale para o
preparo do texto — divergencia entre duas implementacoes da mesma extracao nao se
manifesta como falha, e sim como queda de desempenho sem causa aparente.

OS OITO ATRIBUTOS
-----------------
    F1 email_lgpd_dominio_proprio  prefixo de privacidade no dominio do sitio
    F2 email_lgpd_dominio_externo  prefixo de privacidade em dominio de grupo
    F3 email_generico_ancorado     endereco sem prefixo, proximo a ancora de direitos
    F4 subpagina_titular           subpagina de canal ou encarregado, plausivel
    F5 contato_ancorado            formulario ou vinculo ancorado a direitos
    F6 telefone_ancorado           telefone proximo a ancora
    F7 ancora_encarregado          mencao a Encarregado
    F8 ancora_direitos             mencao a exercicio de direitos

F7 e F8 sao binarios e nao contagens. A escolha e empirica: testados os cortes de
contagem de 1 a 14, o otimo e maior ou igual a um, identico a binarizacao, com
ganho nulo em acuracia balanceada. A contagem bruta e ainda confundida pelo
comprimento do documento — politica extensa menciona mais vezes por ser extensa —,
de modo que mediria extensao textual em lugar do construto.

F1 e F4 correspondem aos sinais do detector por regra, de sorte que o conjunto
contem a linha de base como caso particular. Os modelos sao aninhados, o que torna
a comparacao por McNemar um teste direto sobre o ganho dos sinais adicionais.

A JANELA DE PROXIMIDADE
-----------------------
Fixada em 200 caracteres, ordem de grandeza de um paragrafo, e definida ANTES da
avaliacao. As execucoes com 100 e 400 destinam-se a verificacao de robustez, nao a
selecao: escolher a janela pelo desempenho equivaleria a ajustar hiperparametro
sobre a amostra inteira.

MATERIAL SUBMETIDO
------------------
Ao contrario do preparo das variaveis textuais, aqui se emprega o sitio INTEIRO —
pagina inicial inclusive — mais o texto dos documentos em PDF. A diferenca e do
construto: o canal de atendimento nao e propriedade do texto da politica e pode
ser divulgado em pagina de contato, ao passo que finalidade, direitos e
transferencia so existem enquanto declaracao dentro da politica.
"""
from __future__ import annotations

import bisect
import re
from html.parser import HTMLParser
from typing import Iterable, Mapping, Sequence

__all__ = ["ATRIBUTOS", "JANELA_PADRAO", "VERSAO_EXTRATOR", "PARAMETROS",
           "extrai_atributos", "visivel", "dominio_base"]

ATRIBUTOS = ("F1_email_lgpd_proprio", "F2_email_lgpd_externo",
             "F3_email_generico_ancorado", "F4_subpagina_titular",
             "F5_contato_ancorado", "F6_telefone_ancorado",
             "F7_ancora_encarregado", "F8_ancora_direitos")

JANELA_PADRAO = 200
MIN_SUBPAGE_BYTES = 500
TETO_HTML = 2_000_000     # portais extensos degradam a busca por expressao regular
MAX_GENERICOS = 60        # alternancia unica de enderecos, para uma so varredura

# Identifica o procedimento de extracao. Vai gravada no artefato e no registro de
# auditoria: extrator e coeficientes formam par, e trocar um sem o outro produz
# predicao plausivel e errada.
VERSAO_EXTRATOR = "1.0.0"
PARAMETROS = {"janela": JANELA_PADRAO, "min_subpage_bytes": MIN_SUBPAGE_BYTES,
              "teto_html": TETO_HTML, "max_genericos": MAX_GENERICOS}

EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:com|com\.br|br|gov\.br|org|org\.br|edu|edu\.br|net|net\.br))\b",
    re.IGNORECASE)
PREFIXOS_LGPD = ("dpo", "encarregado", "encarregada", "privacidade", "lgpd",
                 "protecaodedados", "protecao.dados", "protecao_dados", "meusdados")
# Provedores de infraestrutura e de plataforma: endereco de encarregado no dominio
# deles pertence ao operador, e nao ao controlador sob analise.
BLOCKLIST = frozenset({
    "cloudflare.com", "cloudfront.net", "akamai.com", "akamaihd.net", "fastly.com",
    "amazonaws.com", "wordpress.com", "automattic.com", "shopify.com", "wix.com",
    "wixpress.com", "squarespace.com", "hubspot.com", "zendesk.com", "salesforce.com",
    "google.com", "gstatic.com", "adobe.com", "sentry.io", "example.com",
})
ANC_ENCARREGADO = re.compile(r"\bencarregad[oa]\b|\bdpo\b|data\s+protection\s+officer", re.I)
ANC_DIREITOS = re.compile(
    r"portal\s+do\s+titular|central\s+do\s+titular|canal\s+do\s+titular|seus\s+direitos"
    r"|direitos\s+do\s+titular|exerc\w+\s+(?:de\s+|seus\s+)?direitos|requisi\w+\s+lgpd"
    r"|solicita\w+\s+lgpd|titular\s+dos\s+dados", re.I)
ANC_QUALQUER = re.compile(f"({ANC_ENCARREGADO.pattern})|({ANC_DIREITOS.pattern})", re.I)
TEL_RE = re.compile(r"tel:[+0-9()\s.\-]{8,}|\(?\d{2}\)?\s?\d{4,5}[\-\s.]?\d{4}")
PLAUSIBILIDADE = ("titular", "direito", "lgpd", "exercer", "exercicio", "exercício",
                  "encarregado", "dpo", "solicitacao", "solicitação", "requisicao",
                  "requisição", "fale conosco")


class _Vis(HTMLParser):
    """Texto visivel, sem fronteiras de bloco.

    Difere deliberadamente do extrator do preparo textual, que preserva fronteira
    de bloco porque a unidade la e a sentenca. Aqui a unidade e o sitio inteiro, e
    o que interessa e a PROXIMIDADE entre marcas — introduzir fronteiras alteraria
    as distancias sobre as quais a janela opera.
    """

    SKIP = {"script", "style", "noscript", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buf: list[str] = []
        self.skip = 0

    def handle_starttag(self, t, a):
        if t in self.SKIP:
            self.skip += 1

    def handle_endtag(self, t):
        if t in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, d):
        if not self.skip and d.strip():
            self.buf.append(d.strip())


def visivel(html: str) -> str:
    p = _Vis()
    try:
        p.feed(html)
    except Exception:
        pass
    return re.sub(r"\s+", " ", " ".join(p.buf))


def dominio_base(url: str) -> str:
    d = re.sub(r"^https?://", "", (url or "")).split("/")[0].lower()
    return d[4:] if d.startswith("www.") else d


def _mesmo_dominio(email_dom: str, site_dom: str) -> bool:
    e, s = email_dom.lower().strip(), site_dom.lower().strip()
    return e == s or e.endswith("." + s) or s.endswith("." + e)


def _eh_provedor(dom: str) -> bool:
    d = dom.lower()
    return any(d == p or d.endswith("." + p) for p in BLOCKLIST)


def _posicoes_ancora(texto: str) -> list[int]:
    """Posicoes das ancoras, calculadas uma unica vez.

    O recalculo por ocorrencia domina o tempo em documentos extensos.
    """
    return [m.start() for m in ANC_QUALQUER.finditer(texto)]


def _perto(anc: Sequence[int], alvo_re, texto: str, janela: int) -> bool:
    """Alguma ocorrencia de `alvo_re` dista ate `janela` caracteres de uma ancora.

    A busca binaria sobre as posicoes ordenadas evita varredura linear.
    """
    if not anc:
        return False
    for m in alvo_re.finditer(texto):
        p = m.start()
        i = bisect.bisect_left(anc, p)
        for j in (i - 1, i):
            if 0 <= j < len(anc) and abs(p - anc[j]) <= janela:
                return True
    return False


def extrai_atributos(html: str, *, url: str,
                     subpage_selection: Mapping | None = None,
                     texto_pdf: str = "",
                     janela: int = JANELA_PADRAO) -> dict[str, int]:
    """Os oito atributos binarios, a partir do material coletado.

    Args:
        html: marcacao concatenada da pagina inicial e das subpaginas.
        url: URL do sitio, de onde se deriva o dominio proprio.
        subpage_selection: auditoria da selecao de subpaginas produzida pelo
            coletor, de onde vem a existencia de subpagina de canal ou encarregado.
        texto_pdf: texto ja extraido dos documentos em PDF de politica.
        janela: proximidade em caracteres. Nao selecionar pelo desempenho.
    """
    vis = visivel(html)
    vis_total = (vis + " " + (texto_pdf or "")).strip()
    sdom = dominio_base(url)
    subsel = subpage_selection or {}

    enderecos = ({e.lower() for e in EMAIL_RE.findall(vis_total)}
                 | {e.lower() for e in EMAIL_RE.findall(html)})
    f1 = f2 = 0
    genericos: list[str] = []
    for e in enderecos:
        user, dom = e.split("@", 1)
        if _eh_provedor(dom):
            continue
        if any(user.startswith(p) for p in PREFIXOS_LGPD):
            if _mesmo_dominio(dom, sdom):
                f1 = 1
            else:
                f2 = 1
        else:
            genericos.append(e)

    anc_vis = _posicoes_ancora(vis_total)
    f3 = 0
    if genericos:
        alt = re.compile("|".join(re.escape(e) for e in genericos[:MAX_GENERICOS]), re.I)
        f3 = 1 if _perto(anc_vis, alt, vis_total, janela) else 0

    f4 = 0
    for cat in ("canal_titular", "encarregado"):
        for _item in (subsel.get(cat) or []):
            f4 = 1
    if f4 and not any(k in vis_total.lower() for k in PLAUSIBILIDADE):
        f4 = 0
    if f4 and len(html) < MIN_SUBPAGE_BYTES:
        f4 = 0

    f5 = 0
    htm = html[:TETO_HTML]
    anc_html = _posicoes_ancora(htm)
    if _perto(anc_html, re.compile(r"<form\b", re.I), htm, janela):
        f5 = 1
    if not f5:
        for m in re.finditer(r"<a\b[^>]{0,400}>([^<]{0,120})</a>", htm, re.I):
            if ANC_DIREITOS.search(m.group(1) or "") and not re.search(
                    r'href="(mailto:|tel:)', m.group(0), re.I):
                f5 = 1
                break

    f6 = 1 if _perto(anc_vis, TEL_RE, vis_total, janela) else 0
    f7 = 1 if ANC_ENCARREGADO.search(vis_total) else 0
    f8 = 1 if ANC_DIREITOS.search(vis_total) else 0
    return dict(zip(ATRIBUTOS, (f1, f2, f3, f4, f5, f6, f7, f8)))
