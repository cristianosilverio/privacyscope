"""
Smoke test manual do HttpFetcher contra sites brasileiros reais.

Executa coleta HTTP contra 3 sites variados (.gov.br + .com.br) e produz:
    1) Resumo legível no stdout: HTML coletado, cookies, subpáginas detectadas
       com auditoria completa (qual regex disparou, contra qual atributo,
       snippet evidencial), network log e erros não-fatais.
    2) Dump JSON da RawEvidence em data/smoke_http_fetcher/<host>.json
       (sem o HTML completo — esse vai em arquivos separados).
    3) HTMLs salvos em data/smoke_http_fetcher/<host>__<path>.html para
       inspeção manual.

Uso:
    cd C:\\Dev\\privacyscope
    .\\.venv\\Scripts\\Activate.ps1
    python scripts/smoke_http_fetcher.py

Para customizar:
    - Edite TARGETS abaixo para incluir outras URLs
    - Edite PARAMS para mudar timeouts, subpage_categories, etc.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from privacyscope.core import Domain
from privacyscope.fetchers import (
    DEFAULT_SUBPAGE_CATEGORIES,
    FetchError,
    HttpFetcher,
    RobotsDisallowedError,
)

# ----------------------------------------------------------------------------
# Configuração do teste
# ----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # menos ruído

# Mix proposital: 2 .gov.br + 1 .com.br grande. Substitua à vontade.
TARGETS: list[Domain] = [
    Domain(
        url="https://www.gov.br/anpd/pt-br",
        tld=".gov.br",
        source_name="manual_smoke",
        rank=None,
        stratum="governamental",
    ),
    Domain(
        url="https://www.serpro.gov.br",
        tld=".gov.br",
        source_name="manual_smoke",
        rank=None,
        stratum="governamental",
    ),
    Domain(
        url="https://www.uol.com.br",
        tld=".com.br",
        source_name="manual_smoke",
        rank=None,
        stratum="empresarial",
    ),
]

# Equivalente ao que viria do protocol.yaml em params do crawler:
PARAMS: dict = {
    "respect_robots_txt": True,
    "connect_timeout_s": 10.0,
    "read_timeout_s": 30.0,
    "max_redirects": 5,
    "max_response_bytes": 5_000_000,
    # Para usar categorias custom, descomente e edite:
    # "subpage_categories": {
    #     "politica_cookies": [r"polit\w*[\s_\-]*de[\s_\-]*cookies?", r"cookie[\s_\-]*policy"],
    #     "acessibilidade":   [r"acessibilidade"],
    # },
    "max_per_category": 1,
    "max_total_subpages": 5,
}

OUT_DIR = Path("data/smoke_http_fetcher")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------
# Helpers de apresentação
# ----------------------------------------------------------------------------
def _bar(char: str = "=", width: int = 78) -> str:
    return char * width


def summarize(domain: Domain, evidence, error: Exception | None, elapsed: float) -> None:
    print()
    print(_bar("="))
    print(f"URL:    {domain.url}")
    print(f"TLD:    {domain.tld}  | estrato: {domain.stratum}")
    print(f"Tempo:  {elapsed:.2f}s")

    if error is not None:
        print(f"FALHA:  {type(error).__name__}: {error}")
        return

    assert evidence is not None
    print(f"Fetcher: {evidence.fetcher_name}")
    print(f"Timestamp UTC: {evidence.timestamp_utc.isoformat()}")

    print(f"\n[HTML pages coletadas: {len(evidence.html_pages)}]")
    for path, body in evidence.html_pages.items():
        print(f"  {path:30s} {len(body):>10,} bytes")

    print(f"\n[Cookies fixados via Set-Cookie: {len(evidence.cookies)}]")
    for c in evidence.cookies[:6]:
        flags = []
        if c.get("secure"):
            flags.append("Secure")
        if c.get("httpOnly"):
            flags.append("HttpOnly")
        if c.get("sameSite"):
            flags.append(f"SameSite={c['sameSite']}")
        flags_str = ", ".join(flags) or "(sem flags)"
        domain_str = c.get("domain") or "(none)"
        print(f"  {c['name']:35s} dom={domain_str:30s} {flags_str}")
    if len(evidence.cookies) > 6:
        print(f"  ... e mais {len(evidence.cookies) - 6}")

    print(f"\n[Subpáginas detectadas (auditoria por categoria)]")
    if not evidence.subpage_selection:
        print("  (nenhuma — defaults não casaram com os links da raiz)")
    for cat, items in evidence.subpage_selection.items():
        for it in items:
            print(f"  [{cat}]")
            print(f"    URL:     {it['url']}")
            print(f"    Pattern: {it['matched_pattern']!r}")
            print(f"    Match:   contra '{it['matched_against']}' -> {it['snippet']!r}")

    print(f"\n[Network log: {len(evidence.network_log)} requisições]")
    for entry in evidence.network_log:
        print(
            f"  {entry['status']} {entry['method']:4s} "
            f"{entry['size_bytes']:>8,} bytes "
            f"{entry['duration_ms']:>5} ms  {entry['url']}"
        )

    if evidence.errors:
        print(f"\n[Erros não-fatais: {len(evidence.errors)}]")
        for e in evidence.errors:
            print(f"  - {e}")


# ----------------------------------------------------------------------------
# Coleta + persistência
# ----------------------------------------------------------------------------
async def fetch_one(fetcher: HttpFetcher, domain: Domain, params: dict):
    t0 = time.perf_counter()
    try:
        evidence = await fetcher.fetch(domain, params)
        return evidence, None, time.perf_counter() - t0
    except (FetchError, RobotsDisallowedError) as e:
        return None, e, time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001 - smoke test pega tudo
        return None, e, time.perf_counter() - t0


def _safe_host(url: str) -> str:
    return (
        url.replace("https://", "")
        .replace("http://", "")
        .replace("/", "_")
        .replace(":", "_")
        .strip("_")
    )


def persist(domain: Domain, evidence) -> None:
    host = _safe_host(domain.url)

    # 1) HTMLs em arquivos separados
    for path, body in evidence.html_pages.items():
        safe = path.replace("/", "_").lstrip("_") or "root"
        (OUT_DIR / f"{host}__{safe}.html").write_bytes(body)

    # 2) JSON da RawEvidence (sem o HTML, que já está salvo separado)
    dump = evidence.model_dump(mode="python")
    dump["html_pages"] = {k: f"<{len(v):,} bytes>" for k, v in evidence.html_pages.items()}
    dump.pop("screenshot", None)
    (OUT_DIR / f"{host}.json").write_text(
        json.dumps(dump, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
async def main() -> None:
    fetcher = HttpFetcher()

    print(_bar("#"))
    print(f"# Smoke test do HttpFetcher")
    print(f"# Alvos:        {len(TARGETS)}")
    print(f"# User-Agent:   {fetcher.default_user_agent}")
    print(f"# Categorias:   {list(DEFAULT_SUBPAGE_CATEGORIES.keys())}")
    print(f"# Saída:        {OUT_DIR.resolve()}")
    print(_bar("#"))

    for domain in TARGETS:
        evidence, error, elapsed = await fetch_one(fetcher, domain, PARAMS)
        summarize(domain, evidence, error, elapsed)
        if evidence is not None:
            persist(domain, evidence)
            print(f"\n  -> dump em {OUT_DIR / (_safe_host(domain.url) + '.json')}")

    print()
    print(_bar("="))
    print(f"Concluído. Inspecione: {OUT_DIR.resolve()}")
    print(_bar("="))


if __name__ == "__main__":
    asyncio.run(main())
