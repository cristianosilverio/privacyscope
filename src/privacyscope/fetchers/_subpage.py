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
}


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
        base_url: URL absoluta para resolver hrefs relativos.
        categories: dict de regexes por categoria (já validado).
        max_per_category: limite de URLs por categoria.
        max_total: teto global de URLs.

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


__all__ = [
    "DEFAULT_SUBPAGE_CATEGORIES",
    "DEFAULT_PATH_BLOCKERS",
    "validate_subpage_config",
    "extract_subpage_candidates",
]
