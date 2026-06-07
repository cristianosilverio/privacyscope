"""
Extração de subpáginas candidatas — utilitário compartilhado entre fetchers.

Vive em ``fetchers/_subpage`` (underscore prefix = privado da camada por
convenção). Compartilhado entre HttpFetcher e PlaywrightFetcher para evitar
duplicação de lógica. Não exposto como API pública do framework.

Decoupling preservado:
    - HttpFetcher e PlaywrightFetcher importam daqui, mas não um do outro.
    - Função é pura: HTML+config → dict. Sem estado, sem dependência de
      fetcher.
    - Contrato `PageFetcher.fetch(domain) → RawEvidence` da ABC permanece
      intacto. Esta utilidade opera DENTRO da implementação do fetch.
    - Refinamentos pós-piloto se aplicam aos dois fetchers de uma vez.

Padrões de detecção:
    O separador ``[\\s_\\-]*`` é usado entre palavras-chave para casar tanto
    texto visível (com espaços) quanto hrefs (com hífens ou underscores).

TODO (refinamento pós-piloto): os defaults atuais são permissivos demais.
Smoke test em 17/05/2026 capturou false positives óbvios. Refinar com base
em rotulagem manual da piloto n=50. Ver docs/notas_de_refinamento.md.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup


#: Versão semântica deste módulo. Bumped para 0.3.0 em 2026-06-07 com a
#: introdução da categoria-trampolim ``acesso_informacao_gov`` (Lei 12.527/2011)
#: e da função ``extract_trampoline_lgpd_candidates`` que habilita descoberta
#: de páginas LGPD em profundidade 2 a partir de seções de Acesso à Informação.
#: Esta constante aparece em ``meta.json`` da camada de Evidência Bruta para
#: rastreabilidade da versão do descobridor de subpáginas usada em cada coleta.
SUBPAGE_VERSION = "0.3.0"


#: Padrões default para detecção de subpáginas em sites institucionais brasileiros.
#: Cada chave é uma categoria; cada valor é lista de regexes (case-insensitive)
#: que casa contra atributos do <a>. Sobrescritível via params do protocolo.
DEFAULT_SUBPAGE_CATEGORIES: dict[str, list[str]] = {
    "politica_privacidade": [
        # Originais
        r"polit\w+[\s_\-]*de[\s_\-]*privacid",
        r"aviso[\s_\-]*de[\s_\-]*privacid",
        r"privacy[\s_\-]*policy",
        r"\blgpd\b",
        r"prote\w*[\s_\-]*de[\s_\-]*dados",
        # Expansão 2026-05-19 — cobertura ampliada antes da piloto B4
        r"notifica\w*[\s_\-]*de[\s_\-]*privacid",   # "notificação de privacidade"
        r"declara\w*[\s_\-]*de[\s_\-]*privacid",    # "declaração de privacidade"
        r"portal[\s_\-]*de[\s_\-]*privacid",        # "portal de privacidade"
        r"central[\s_\-]*de[\s_\-]*privacid",       # "central de privacidade"
        r"privacy[\s_\-]*notice",
        r"privacy[\s_\-]*statement",
        # Refinamento A (2026-05-19, pós pré-piloto n=10): link rotulado
        # apenas "Privacidade"/"Privacy" (sem "política de"). FN observado em
        # uol.com.br e mercadolivre.com.br. Baixa precisão isolada, mas o
        # VariableTest qualifica por conteúdo (>=3 keywords, >=500 bytes),
        # filtrando falsos positivos na 2a etapa.
        r"\bprivacidade\b",
        r"\bprivacy\b",
    ],
    "termos_uso": [
        r"termos[\s_\-]*de[\s_\-]*uso",
        r"termos[\s_\-]*de[\s_\-]*servic",
        r"terms[\s_\-]*of[\s_\-]*(use|service)",
        r"condi\w*[\s_\-]*de[\s_\-]*uso",
    ],
    "encarregado": [
        # Conceito legal específico: pessoa designada (art. 41 LGPD).
        r"encarregad\w+",
        r"\bdpo\b",
        r"data[\s_\-]*protection[\s_\-]*officer",
        r"fale[\s_\-]*conosco.*lgpd",
        r"contato.*prote\w*[\s_\-]*de[\s_\-]*dados",
    ],
    "canal_titular": [
        # Mecanismos de exercício de direitos (art. 18 LGPD). Distinto do
        # "encarregado" (pessoa) por escopo conceitual — detectar portais,
        # centrais, formulários de exercício de direitos.
        r"portal[\s_\-]*do[\s_\-]*titular",
        r"central[\s_\-]*do[\s_\-]*titular",
        r"canal[\s_\-]*do[\s_\-]*titular",
        r"\bseus[\s_\-]*direitos\b",
        r"direitos[\s_\-]*do[\s_\-]*titular",
        r"exerc\w*[\s_\-]*de[\s_\-]*direitos",
        r"requisi\w*[\s_\-]*lgpd",
        r"solicita\w*[\s_\-]*lgpd",
    ],
    # Categoria-trampolim adicionada em v0.3.0 (2026-06-07). Não é alvo direto
    # da análise — serve para descobrir páginas LGPD em profundidade 2 a
    # partir de seções de Acesso à Informação. Justificativa normativa: a Lei
    # 12.527/2011 (LAI) obriga sítios públicos brasileiros (e entes equiparados:
    # autarquias, empresas estatais, fundações, empresas que recebem recursos
    # públicos — art. 1º, parágrafo único) a manter seção dedicada de
    # Acesso à Informação. Material LGPD frequentemente reside dentro dela,
    # em vez de no menu principal. Observado no B8 (n=50 held-out) em
    # saogoncalo.rn.gov.br (acessoainformacao.php → lgpd.php) e cgu.gov.br
    # (acesso-a-informacao → privacidade-e-protecao-de-dados). Sem esta
    # categoria-trampolim, o descobridor de subpáginas com profundidade 1
    # falha sistematicamente para esse padrão estrutural. O comportamento
    # de trampolim — i.e., a páginas dessa categoria são SECUNDARIAMENTE
    # varridas em busca de páginas LGPD — é controlado pelos fetchers via
    # consulta a ``TRAMPOLINE_CATEGORIES`` e ``extract_trampoline_lgpd_candidates``.
    "acesso_informacao_gov": [
        r"acesso[\s_\-]*[àa][\s_\-]*informa\w*",
        r"acessoainforma\w*",
        r"\btranspar\w*",
        r"\be[\s_\-]*sic\b",
        r"\bouvidor\w*",
    ],
}


#: Categorias cuja coleta dispara descoberta de profundidade 2 (varredura do
#: HTML da subpágina por links LGPD). Os fetchers consultam este conjunto
#: depois da coleta principal e antes de retornar a RawEvidence. Manter como
#: ``frozenset`` para impedir mutação acidental por consumidores.
TRAMPOLINE_CATEGORIES: frozenset[str] = frozenset({"acesso_informacao_gov"})


#: Categorias LGPD-alvo que a profundidade 2 do trampolim TENTA descobrir.
#: Exclui o próprio trampolim (evita auto-recursão) e ``termos_uso`` (não é
#: alvo LGPD core; sua descoberta segue restrita à profundidade 1).
DEFAULT_LGPD_DEPTH2_CATEGORIES: frozenset[str] = frozenset({
    "politica_privacidade",
    "encarregado",
    "canal_titular",
})


#: Path-blockers (Refinamento D, 2026-05-20): padrões de URL que indicam
#: conteúdo editorial/efêmero (notícias, blog, eventos), NÃO documentos
#: normativos de privacidade. Candidatos cujo full_url casa qualquer um destes
#: são descartados ANTES do download — evita (a) falsos positivos do padrão
#: "privacidade" isolado casando slugs de notícia (ex.: globo.com
#: ".../pede-privacidade.ghtml") e (b) downloads inúteis em escala no n=384.
#: Sobrescritível via params['path_blockers'] no protocolo.
DEFAULT_PATH_BLOCKERS: list[str] = [
    r"/noticias?/",
    r"/blog/",
    r"/artigos?/",
    r"/materias?/",
    r"/post/",
    r"/imprensa/",
    r"\.ghtml",
    r"/videos?/",
    r"/galeria/",
]


def validate_subpage_config(
    params: dict[str, Any],
) -> tuple[dict[str, list[str]], int, int]:
    """Resolve defaults e valida params de subpáginas.

    Args:
        params: dict do protocolo (pode conter ``subpage_categories``,
            ``max_per_category``, ``max_total_subpages``).

    Returns:
        Tupla ``(categories, max_per_category, max_total_subpages)``.

    Raises:
        ValueError: param mal-formado, regex inválido, etc.
    """
    cats = params.get("subpage_categories", DEFAULT_SUBPAGE_CATEGORIES)
    if not isinstance(cats, dict):
        raise ValueError("subpage_categories deve ser dict[str, list[str]]")
    validated: dict[str, list[str]] = {}
    for cat, patterns in cats.items():
        if not isinstance(cat, str) or not cat:
            raise ValueError(
                f"chave de categoria deve ser string não-vazia; recebido: {cat!r}"
            )
        if not isinstance(patterns, list):
            raise ValueError(
                f"patterns para '{cat}' deve ser lista de strings de regex"
            )
        for p in patterns:
            if not isinstance(p, str):
                raise ValueError(
                    f"pattern em '{cat}' deve ser str; recebido: {p!r}"
                )
            try:
                re.compile(p, re.IGNORECASE)
            except re.error as e:
                raise ValueError(f"regex inválido em '{cat}': {p!r}: {e}") from e
        validated[cat] = list(patterns)

    max_per_category = params.get("max_per_category", 1)
    if not isinstance(max_per_category, int) or max_per_category < 1:
        raise ValueError("max_per_category deve ser inteiro >= 1")

    max_total = params.get("max_total_subpages", 5)
    if not isinstance(max_total, int) or max_total < 0:
        raise ValueError("max_total_subpages deve ser inteiro >= 0")

    return validated, max_per_category, max_total


def extract_subpage_candidates(
    html: bytes | str,
    base_url: str,
    categories: dict[str, list[str]],
    max_per_category: int,
    max_total: int,
    path_blockers: list[str] | None = None,
    same_host_categories: frozenset[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Encontra subpáginas candidatas no HTML e devolve auditoria por categoria.

    Estrutura compatível com ``RawEvidence.subpage_selection``::

        {categoria: [{url, matched_pattern, matched_against, snippet}, ...]}

    Cada ``<a>`` contribui para no máximo uma categoria. Categorias sem
    matches são omitidas do retorno.

    Ordem de inspeção (importa para o ``matched_against`` do audit_trail):

        1. ``text``       — o que humano vê
        2. ``aria-label`` — o que tecnologias assistivas leem (WCAG / eMAG / LBI)
        3. ``title``      — tooltip
        4. ``href``       — URL/path

    Args:
        html: HTML como bytes ou string. Aceita ambos para que o
            PlaywrightFetcher possa passar ``page.content()`` diretamente.
        base_url: URL absoluta para resolver hrefs relativos. **Deve ser a
            URL final pós-redirect** quando ``same_host_categories`` for
            usado — caso contrário o teste de same-host compara contra um
            netloc obsoleto.
        categories: dict de regexes por categoria (já validado).
        max_per_category: limite de URLs por categoria.
        max_total: teto global de URLs.
        path_blockers: lista de regexes para descartar URLs editoriais/
            efêmeras (notícias, blog). Default ``DEFAULT_PATH_BLOCKERS``.
        same_host_categories: conjunto de categorias que devem aceitar
            APENAS candidatos com o mesmo host (netloc) do ``base_url`` ou
            subdomínios dele. Útil para categorias-trampolim — material de
            Acesso à Informação que mora em portal terceirizado de gestão
            (sogov, geocriativa, betha) não cumpre a LAI da forma esperada
            e não conterá evidência LGPD do controlador originário.
            Default ``None`` (desativado).

    Returns:
        Dict ``{categoria: [items]}`` deduplicado.
    """
    if max_total == 0:
        return {}

    soup = BeautifulSoup(html, "lxml")
    compiled = {
        cat: [re.compile(p, re.IGNORECASE) for p in patterns]
        for cat, patterns in categories.items()
    }
    # Refinamento D: compila path-blockers (default ou override do protocolo).
    blocker_patterns = path_blockers if path_blockers is not None else DEFAULT_PATH_BLOCKERS
    compiled_blockers = [re.compile(p, re.IGNORECASE) for p in blocker_patterns]

    # Refinamento E (v0.3.0, 2026-06-07): same-host enforcement por categoria.
    # Para categorias listadas em ``same_host_categories``, candidatos com
    # netloc diferente do base_url são descartados ANTES de saturar
    # ``max_per_category``. Calcula o netloc-base uma única vez.
    from urllib.parse import urlparse as _urlparse  # local import (evita poluir top)

    def _normalize_netloc(nl: str) -> str:
        """Normaliza netloc: lowercase, strip 'www.' inicial. Bug-fix vs lstrip
        que aceita set de chars, não prefixo string."""
        nl = nl.lower()
        return nl[4:] if nl.startswith("www.") else nl

    base_netloc = _normalize_netloc(_urlparse(base_url).netloc) if base_url else ""
    same_host_set = same_host_categories or frozenset()

    result: dict[str, list[dict[str, Any]]] = {cat: [] for cat in categories}
    # Refinamento B (2026-05-19): dedup POR categoria (nao global), permitindo
    # que a mesma URL apareca em multiplas categorias quando casa padroes de
    # mais de uma (ex.: /privacidade pode ser politica E canal do titular).
    # ``seen_any`` controla o teto global de URLs unicas a baixar (max_total).
    seen_per_cat: dict[str, set[str]] = {cat: set() for cat in categories}
    seen_any: set[str] = set()
    total = 0

    for a in soup.find_all("a", href=True):
        if total >= max_total:
            break
        href = str(a["href"]).strip()
        text = (a.get_text() or "").strip()
        aria_label = str(a.get("aria-label", "")).strip()
        title_attr = str(a.get("title", "")).strip()
        if not href:
            continue

        # Ordem de inspeção: text > aria-label > title > href.
        # Sites institucionais BR (gov.br, grandes empresas) frequentemente têm
        # ícones/links com texto vago mas aria-label explícito devido a eMAG/LBI.
        inspection_order = [
            ("text",       text,       text.lower()),
            ("aria-label", aria_label, aria_label.lower()),
            ("title",      title_attr, title_attr.lower()),
            ("href",       href,       href.lower()),
        ]

        for cat, regexes in compiled.items():
            if len(result[cat]) >= max_per_category:
                continue
            matched_pattern: str | None = None
            matched_against: str | None = None
            snippet_source: str = ""

            for source_name, source_raw, source_lower in inspection_order:
                if not source_lower:
                    continue
                for rx in regexes:
                    if rx.search(source_lower):
                        matched_pattern = rx.pattern
                        matched_against = source_name
                        snippet_source = source_raw
                        break
                if matched_pattern is not None:
                    break

            if matched_pattern is None:
                continue

            full_url = urljoin(base_url, href)
            if not full_url.startswith(("http://", "https://")):
                continue
            # Refinamento D: descarta candidatos de conteúdo editorial/efêmero
            # (notícias, blog, eventos), que casam "privacidade" por acaso no
            # slug mas não são documentos normativos.
            if any(b.search(full_url) for b in compiled_blockers):
                continue
            # Refinamento E (v0.3.0): same-host enforcement por categoria.
            # Categorias-trampolim (Acesso à Informação) exigem que o destino
            # esteja no mesmo host do base_url ou em subdomínio dele —
            # material LAI em portal terceirizado (sogov, geocriativa, betha)
            # não contém evidência LGPD do controlador originário e levaria
            # o trampolim a descer em domínio errado, desperdiçando orçamento.
            if cat in same_host_set:
                cand_netloc = _normalize_netloc(_urlparse(full_url).netloc)
                if cand_netloc != base_netloc and not cand_netloc.endswith(
                    "." + base_netloc
                ):
                    continue
            # Dedup por categoria: a mesma URL pode entrar em categorias
            # distintas, mas nao duas vezes na mesma categoria.
            if full_url in seen_per_cat[cat]:
                continue
            seen_per_cat[cat].add(full_url)

            result[cat].append({
                "url": full_url,
                "matched_pattern": matched_pattern,
                "matched_against": matched_against,
                "snippet": snippet_source[:120],
            })
            # total conta URLs UNICAS (uma URL em 2 categorias = 1 download).
            if full_url not in seen_any:
                seen_any.add(full_url)
                total += 1
                if total >= max_total:
                    break
        # Refinamento B: sem break entre categorias — um <a> pode casar
        # multiplas categorias (politica E canal, p.ex.).

    # Omite categorias vazias
    return {cat: items for cat, items in result.items() if items}


def extract_trampoline_lgpd_candidates(
    html: bytes | str,
    base_url: str,
    categories: dict[str, list[str]],
    source_category: str,
    max_per_category: int = 1,
    max_total: int = 3,
    path_blockers: list[str] | None = None,
    lgpd_target_categories: frozenset[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Descobre páginas LGPD em profundidade 2 a partir de uma página-trampolim.

    Aplica ``extract_subpage_candidates`` SOMENTE com as categorias LGPD-alvo
    (default ``DEFAULT_LGPD_DEPTH2_CATEGORIES``), anota ``discovered_via`` em
    cada item com a categoria de origem (``"trampoline:<source_category>"``) e
    devolve o mesmo formato de ``extract_subpage_candidates``.

    Justificativa de design — por que separar do ``extract_subpage_candidates``:

    - **Defesa contra auto-recursão**: garante que ``acesso_informacao_gov``
      não dispare nova descoberta a partir de uma página-trampolim já varrida.
    - **Tetos próprios**: a profundidade 2 usa orçamento separado (default
      ``max_total=3``), não consume o ``max_total_subpages`` global. Evita
      que sítios com muitos links LAI esgotem o teto sem ter explorado a
      profundidade 1.
    - **Auditabilidade**: o campo ``discovered_via`` permite distinguir, na
      camada de Análise e no audit_trail, candidatos descobertos diretamente
      (depth 1) de candidatos descobertos via LAI (depth 2). Crucial para a
      defesa metodológica em banca.

    Args:
        html: HTML da página-trampolim (já coletada).
        base_url: URL da página-trampolim. Usada para resolver hrefs
            relativos da profundidade 2 corretamente.
        categories: Mesmo dict completo de categorias passado para
            ``extract_subpage_candidates``. Será filtrado internamente para
            ``lgpd_target_categories``.
        source_category: Nome da categoria-trampolim que originou esta
            chamada (ex.: ``"acesso_informacao_gov"``). Aparece em
            ``discovered_via``.
        max_per_category: Limite de URLs por categoria LGPD. Default 1.
        max_total: Teto local de URLs descobertas em profundidade 2.
            Default 3 — propositalmente conservador.
        path_blockers: Override opcional dos default path-blockers.
        lgpd_target_categories: Override opcional do conjunto de categorias
            LGPD-alvo. Default ``DEFAULT_LGPD_DEPTH2_CATEGORIES``.

    Returns:
        Dict ``{categoria_lgpd: [items]}`` no mesmo formato de
        ``extract_subpage_candidates``, com cada item enriquecido com
        ``discovered_via: f"trampoline:{source_category}"``.
        Categorias sem matches são omitidas.
    """
    if lgpd_target_categories is None:
        lgpd_target_categories = DEFAULT_LGPD_DEPTH2_CATEGORIES
    filtered_cats = {
        cat: patterns
        for cat, patterns in categories.items()
        if cat in lgpd_target_categories
    }
    if not filtered_cats:
        return {}
    # Trampolim impõe same-host em TODAS as categorias LGPD-alvo (v0.3.0):
    # material LGPD do controlador originário tipicamente reside no próprio
    # host, não em portais terceirizados. Preserva integridade da evidência
    # para a camada de Análise (e.g., e-mail do canal precisa ser do domínio
    # próprio do controlador, regra do detector v0.2.2 do canal).
    raw = extract_subpage_candidates(
        html=html,
        base_url=base_url,
        categories=filtered_cats,
        max_per_category=max_per_category,
        max_total=max_total,
        path_blockers=path_blockers,
        same_host_categories=lgpd_target_categories,
    )
    annotated: dict[str, list[dict[str, Any]]] = {}
    for cat, items in raw.items():
        annotated[cat] = [
            {**item, "discovered_via": f"trampoline:{source_category}"}
            for item in items
        ]
    return annotated


__all__ = [
    "SUBPAGE_VERSION",
    "DEFAULT_SUBPAGE_CATEGORIES",
    "DEFAULT_PATH_BLOCKERS",
    "TRAMPOLINE_CATEGORIES",
    "DEFAULT_LGPD_DEPTH2_CATEGORIES",
    "validate_subpage_config",
    "extract_subpage_candidates",
    "extract_trampoline_lgpd_candidates",
]
