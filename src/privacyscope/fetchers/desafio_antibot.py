"""Deteccao de desafio anti-bot na evidencia coletada.

POR QUE ISTO EXISTE
-------------------
Quando o servidor de origem classifica o coletor como robo, ele nao devolve o sitio:
devolve uma pagina de desafio. O coletor guarda essa pagina, e os detectores, que nao
tem como saber o que estao lendo, concluem que nao ha politica de privacidade — com
`confidence_label: high`, porque a regra de fato nao encontrou nada.

O defeito e o mesmo que o ternario `nao_aplicavel` corrigiu nas variaveis textuais:
nao distinguir "nao ha" de "nao vi". Aqui ele e mais grave porque nao aparece. A
informacao esta no `headers.json` gravado dentro do tar.gz desde sempre; nenhuma
camada a lia.

E enviesado por porte. Quem instala Cloudflare, DataDome ou PerimeterX e o sitio
maior, que e justamente onde a etapa de Monitoramento tem mais interesse.

CRITERIO DE INCLUSAO DE MARCA
-----------------------------
So entram marcas cuja presenca signifique desafio, e nao mera presenca do produto.
`server: cloudflare` NAO entra: e devolvido por milhoes de sitios servidos sem
qualquer mitigacao, e trata-lo como bloqueio invalidaria coleta boa. `x-datadome-cid`
NAO entra pelo mesmo motivo — o identificador acompanha toda resposta protegida,
bloqueada ou nao.

A assimetria e deliberada. Falso negativo aqui custa uma medicao errada a menos do
que ja temos; falso positivo descarta medicao valida e, pior, poderia descartar
seletivamente os sitios de uma tecnologia so.

ALCANCE DA MARCACAO
-------------------
Uma marca em QUALQUER pagina invalida a coleta inteira, e nao apenas a pagina
marcada. Duas razoes. Primeira, o desafio significa que a origem classificou o agente
como robo, de sorte que nada do que veio pode ser assumido representativo do que um
navegador comum receberia. Segunda, a contaminacao nao e so em uma direcao: a
interstitial do desafio fixa cookies proprios e pode exibir aviso proprio, e tres dos
quatro casos encontrados em b7 e b9 estavam com `tem_banner_cookies = true`.
Suprimir apenas a variavel de politica deixaria o falso positivo de banner de pe.

Referencia da marca de Cloudflare: cabecalho `cf-mitigated`, documentado em
https://developers.cloudflare.com/waf/reference/cloudflare-challenges/
"""
from __future__ import annotations

from typing import Any, Optional

# nome_da_marca -> (cabecalho, valor esperado ou None para "basta existir")
# Cada entrada precisa significar DESAFIO, e nao presenca do produto.
MARCAS: tuple[tuple[str, str, Optional[str]], ...] = (
    # Cloudflare devolve este cabecalho apenas quando a requisicao foi mitigada.
    ("cloudflare_challenge", "cf-mitigated", "challenge"),
    # A interstitial do Turnstile declara o proprio dominio no CSP da resposta.
    ("cloudflare_turnstile", "content-security-policy", "challenges.cloudflare.com"),
    # DataDome marca a resposta bloqueada; o `-cid` de sessao fica de fora.
    ("datadome_block", "x-datadome", "protected"),
    # PerimeterX sinaliza bloqueio explicito.
    ("perimeterx_block", "x-px-block", None),
)


def detecta_desafio(evidence: Any) -> Optional[dict[str, Any]]:
    """Devolve descricao do desafio encontrado, ou None.

    Args:
        evidence: RawEvidence, de que se le apenas `headers` (url -> cabecalhos).

    Returns:
        None quando nada foi encontrado. Caso contrario, dict com `marcas`
        (nomes distintos, ordenados), `paginas` (URLs atingidas, ordenadas) e
        `cabecalho_exemplo`, suficiente para auditar a decisao sem reabrir o tar.
    """
    achados: dict[str, list[str]] = {}
    exemplo: Optional[str] = None
    for url, cabecalhos in (getattr(evidence, "headers", None) or {}).items():
        if not isinstance(cabecalhos, dict):
            continue
        # Cabecalho HTTP e insensivel a caixa (RFC 9110 §5.1), e os coletores nao
        # normalizam: httpx devolve minusculas, Playwright preserva o que veio.
        normalizados = {str(k).lower(): str(v) for k, v in cabecalhos.items()}
        for nome, chave, esperado in MARCAS:
            valor = normalizados.get(chave)
            if valor is None:
                continue
            if esperado is not None and esperado.lower() not in valor.lower():
                continue
            achados.setdefault(nome, []).append(url)
            if exemplo is None:
                exemplo = f"{chave}: {valor[:200]}"
    if not achados:
        return None
    return {
        "marcas": sorted(achados),
        "paginas": sorted({u for us in achados.values() for u in us}),
        "cabecalho_exemplo": exemplo,
    }


def _chave(url: str) -> tuple[str, str]:
    """Identidade de pagina tolerante a `www` e a barra final.

    A URL registrada no cabecalho e a do fim da cadeia de redirecionamento; a
    registrada na selecao de subpaginas e a do link. Compara-las literalmente
    perderia o par em todo sitio que redireciona apex para www.
    """
    from urllib.parse import urlparse

    u = urlparse(url if "//" in url else f"//{url}")
    host = (u.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    caminho = (u.path or "/").rstrip("/") or "/"
    return host, caminho.lower()


def paginas_bloqueadas(evidence: Any) -> set[tuple[str, str]]:
    """Conjunto de paginas com desafio, em forma comparavel a URLs de candidatas."""
    d = detecta_desafio(evidence)
    return {_chave(u) for u in d["paginas"]} if d else set()


def bloqueada(url: str, bloqueadas: set[tuple[str, str]]) -> bool:
    """Diz se `url` esta entre as paginas bloqueadas."""
    return _chave(url) in bloqueadas
