"""Plugins de Coleta (PageFetcher).

Reexporta implementações concretas, defaults e exceções compartilhadas.

Para autores de novos fetchers:
    - Exceções: importar de ``privacyscope.fetchers._exceptions``
    - Extração de subpáginas: usar ``privacyscope.fetchers._subpage``
    - Sinais de qualidade (consumidos pelo FallbackChain): registrar em
      ``privacyscope.fetchers._signals.SIGNAL_REGISTRY``
    - Não definir tipos/exceções/utilitários localmente que já existam
      nos módulos compartilhados (underscore prefix = privados da camada)
"""

from privacyscope.fetchers._exceptions import (
    FetchError,
    JsRequiredError,
    NavigationFailedError,
    ResponseTooLargeError,
    RobotsDisallowedError,
)
from privacyscope.fetchers._signals import SIGNAL_REGISTRY
from privacyscope.fetchers.fallback_chain import FallbackChain
from privacyscope.fetchers.http_fetcher import (
    DEFAULT_HTTP_USER_AGENT,
    DEFAULT_SUBPAGE_CATEGORIES,
    DEFAULT_USER_AGENT,  # alias retrocompat
    HttpFetcher,
)
from privacyscope.fetchers.playwright_fetcher import (
    DEFAULT_CONSENT_BANNER_CONFIG,
    DEFAULT_PLAYWRIGHT_USER_AGENT,
    DEFAULT_PRIVACY_CENTER_CONFIG,
    PlaywrightFetcher,
)

__all__ = [
    # Fetchers concretos
    "HttpFetcher",
    "PlaywrightFetcher",
    "FallbackChain",
    # Defaults compartilhados
    "DEFAULT_SUBPAGE_CATEGORIES",
    "DEFAULT_HTTP_USER_AGENT",
    "DEFAULT_PLAYWRIGHT_USER_AGENT",
    "DEFAULT_USER_AGENT",
    "DEFAULT_CONSENT_BANNER_CONFIG",
    "DEFAULT_PRIVACY_CENTER_CONFIG",
    # Sinais
    "SIGNAL_REGISTRY",
    # Exceções compartilhadas
    "FetchError",
    "RobotsDisallowedError",
    "ResponseTooLargeError",
    "NavigationFailedError",
    "JsRequiredError",
]
