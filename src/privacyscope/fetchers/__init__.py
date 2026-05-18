"""Plugins de Coleta (PageFetcher).

Reexporta as implementações concretas para que o orquestrador possa
descobri-las por nome a partir do protocol.yaml.
"""

from privacyscope.fetchers.http_fetcher import (
    DEFAULT_SUBPAGE_CATEGORIES,
    DEFAULT_USER_AGENT,
    FetchError,
    HttpFetcher,
    ResponseTooLargeError,
    RobotsDisallowedError,
)

__all__ = [
    "HttpFetcher",
    "DEFAULT_SUBPAGE_CATEGORIES",
    "DEFAULT_USER_AGENT",
    "FetchError",
    "RobotsDisallowedError",
    "ResponseTooLargeError",
]
