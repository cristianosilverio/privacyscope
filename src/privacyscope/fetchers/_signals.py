"""
Sinais de qualidade sobre RawEvidence — utilitário compartilhado.

Vive em ``fetchers/_signals`` (underscore prefix = privado da camada por
convenção). Usado pelo ``FallbackChain`` para decidir escalonamento entre
fetchers com base em sinais qualitativos sobre o resultado coletado.

Cada função tem assinatura ``(evidence, params) -> bool``:
    - Retorna ``True`` quando o sinal "dispara" (condição satisfeita).
    - Pura: sem estado, sem efeito colateral, sem I/O.
    - ``params`` é dict opcional para limiares (threshold, markers, etc.).

================================================================================
Guia para autores de novos fetchers / sinais
================================================================================

Ao adicionar um novo sinal:

1. **Crie função pura** no formato ``(evidence: RawEvidence, params: dict) -> bool``.
2. **Documente** quais campos de ``RawEvidence`` ela inspeciona e o
   significado do True/False.
3. **Registre em ``SIGNAL_REGISTRY``** abaixo, com chave em snake_case.
4. **Não dependa de estado externo** (banco de dados, configurações
   globais, etc.). Sinais devem ser composições puras sobre evidência.
5. **Use defaults razoáveis** em ``params`` para que a função funcione
   mesmo sem configuração explícita no protocol.yaml.

O ``FallbackChain`` valida no momento do parse do protocol.yaml que cada
``signal`` referenciado existe neste registry — falha cedo, com mensagem
clara, em vez de erro de runtime no meio da coleta.
"""

from __future__ import annotations

import re
from typing import Callable

from privacyscope.core.types import RawEvidence


def is_html_root_smaller_than_bytes(
    evidence: RawEvidence, params: dict
) -> bool:
    """True se o HTML da raiz (chave ``'/'``) for menor que ``threshold`` bytes.

    Sinal de SPA-shell: páginas modernas com JS-only retornam HTML mínimo
    (centenas de bytes com ``<div id='root'></div>`` vazio). Threshold
    típico: 1000-2000 bytes.

    Params:
        threshold (int): default 1000.
    """
    threshold = params.get("threshold", 1000)
    root = evidence.html_pages.get("/", b"")
    return len(root) < threshold


def is_subpage_selection_empty(evidence: RawEvidence, params: dict) -> bool:
    """True se nenhuma subpágina foi detectada.

    Sites institucionais com links de privacidade/encarregado mas que
    dependem de JavaScript para renderizar links no rodapé tipicamente
    acabam aqui no HttpFetcher. Sinal para escalar a um fetcher com
    browser real (PlaywrightFetcher).

    Params: nenhum.
    """
    return len(evidence.subpage_selection) == 0


def is_cookies_pre_consent_zero(evidence: RawEvidence, params: dict) -> bool:
    """True se a fase ``pre_consent`` em ``cookies_by_phase`` estiver vazia/ausente.

    Após a refatoração para fases dinâmicas (``cookies_by_phase: dict[str, list]``),
    o sinal lê ``evidence.cookies_by_phase.get("pre_consent", [])``. A semântica
    intencional preserva o comportamento por fetcher:

        - HttpFetcher: popula ``cookies_by_phase["single"]``, NUNCA
          ``"pre_consent"``. Logo este sinal SEMPRE dispara — exatamente o
          que se quer para escalar a coleta ao PlaywrightFetcher quando o
          objetivo é distinguir cookies pré/pós-consent (impossível sem JS).
        - PlaywrightFetcher: popula ``"pre_consent"`` no primeiro networkidle.
          Dispara se o site não setou nada antes do accept — pode indicar
          site bem-comportado OU bloqueio anti-bot impedindo carga de tracking.

    Params: nenhum.
    """
    return len(evidence.cookies_by_phase.get("pre_consent", [])) == 0


def are_consent_actions_all_failed(
    evidence: RawEvidence, params: dict
) -> bool:
    """True se houve ao menos uma tentativa de consent e TODAS falharam.

    Útil para escalar quando o banner não foi clicável pelo fetcher
    atual mas talvez seja por outro com estratégia diferente de
    seletores. Diferente de "não tentou" — só dispara se attempted=True
    em pelo menos uma ação e success=False em todas.

    Params: nenhum.
    """
    actions = evidence.consent_actions
    if not actions:
        return False  # sem tentativa = não dispara
    return all(not a.get("success", False) for a in actions)


#: Marcadores default que indicam shell SPA ou exigência de JavaScript.
#: Cobre padrões comuns em PT-BR e EN.
DEFAULT_JS_SHELL_MARKERS: list[str] = [
    r"<noscript>.*?(JavaScript|javascript).*?</noscript>",
    r"(enable|habilit\w+).{0,30}(JavaScript|javascript)",
    r"(você|voce).{0,20}(precisa|necessita).{0,20}(JavaScript|javascript)",
    r'<div\s+id=["\'](root|app|__next|main|__nuxt|svelte)["\']\s*></div>',
    r"You need to enable JavaScript to run this app",
    r"This (app|application) requires JavaScript",
]


def has_js_shell_markers(evidence: RawEvidence, params: dict) -> bool:
    """True se o HTML da raiz contém marcadores típicos de shell SPA.

    Procura por regexes que indicam:
        - Tags ``<noscript>`` pedindo JavaScript
        - Mensagens "habilite JavaScript" (PT/EN)
        - Divs vazios típicos de SPA (``#root``, ``#app``, ``#__next``)

    Params:
        markers (list[str]): regexes adicionais ou substitutas. Default
            usa ``DEFAULT_JS_SHELL_MARKERS``.
        mode (str): ``"replace"`` (default) substitui defaults pelos
            fornecidos, ou ``"extend"`` que adiciona aos defaults.
    """
    user_markers = params.get("markers")
    mode = params.get("mode", "replace")
    if user_markers is None:
        markers = DEFAULT_JS_SHELL_MARKERS
    elif mode == "extend":
        markers = DEFAULT_JS_SHELL_MARKERS + list(user_markers)
    else:
        markers = list(user_markers)

    root_bytes = evidence.html_pages.get("/", b"")
    if not root_bytes:
        return False
    text = root_bytes.decode("utf-8", errors="ignore")
    return any(re.search(p, text, re.IGNORECASE | re.DOTALL) for p in markers)


#: Registry de sinais disponíveis. ``FallbackChain`` valida nomes contra
#: este dicionário no parse do protocol.yaml.
SIGNAL_REGISTRY: dict[str, Callable[[RawEvidence, dict], bool]] = {
    "html_root_smaller_than_bytes": is_html_root_smaller_than_bytes,
    "subpage_selection_empty": is_subpage_selection_empty,
    "cookies_pre_consent_zero": is_cookies_pre_consent_zero,
    "consent_actions_all_failed": are_consent_actions_all_failed,
    "has_js_shell_markers": has_js_shell_markers,
}


__all__ = [
    "SIGNAL_REGISTRY",
    "is_html_root_smaller_than_bytes",
    "is_subpage_selection_empty",
    "is_cookies_pre_consent_zero",
    "are_consent_actions_all_failed",
    "has_js_shell_markers",
]
