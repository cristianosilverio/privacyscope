"""
Smoke test manual do FallbackChain compondo HttpFetcher + PlaywrightFetcher.

Demonstra a escalada por sinal de qualidade contra sites reais. Como o
HttpFetcher é estruturalmente cego a cookies setados via JavaScript, o
sinal ``cookies_pre_consent_zero`` sempre dispara — o chain escala para
o PlaywrightFetcher que tem o estado real do navegador.

Audit log no campo ``errors[]`` da RawEvidence (prefixo ``chain.``) mostra
toda a sequência de tentativas, exceções, sinais que casaram e fetchers
chamados.

Uso:
    cd C:\\Dev\\privacyscope
    .\\.venv\\Scripts\\Activate.ps1
    playwright install chromium    # se ainda não instalou
    python scripts/smoke_fallback_chain.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from privacyscope.core import Domain
from privacyscope.fetchers import (
    FallbackChain,
    FetchError,
    HttpFetcher,
    PlaywrightFetcher,
    RobotsDisallowedError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

TARGETS: list[Domain] = [
    Domain(url="https://www.gov.br/anpd/pt-br", tld=".gov.br",
           source_name="manual_smoke", rank=None, stratum="governamental"),
    Domain(url="https://www.serpro.gov.br", tld=".gov.br",
           source_name="manual_smoke", rank=None, stratum="governamental"),
    Domain(url="https://www.uol.com.br", tld=".com.br",
           source_name="manual_smoke", rank=None, stratum="empresarial"),
]

# Config do chain — equivalente ao que viria do protocol.yaml.
CHAIN_PARAMS: dict = {
    "fetchers": [
        {
            "name": "http_simples",
            "params": {
                "connect_timeout_s": 10,
                "read_timeout_s": 30,
                "respect_robots_txt": True,
                "max_per_category": 1,
                "max_total_subpages": 5,
            },
            "escalate_if": [
                # Exceções comuns de HTTP
                {"exception": "NavigationFailedError"},
                {"exception": "JsRequiredError"},
                # Sinais qualitativos sobre o resultado
                {"signal": "html_root_smaller_than_bytes", "threshold": 5000},
                {"signal": "cookies_pre_consent_zero"},
                {"signal": "subpage_selection_empty"},
                {"signal": "has_js_shell_markers"},
            ],
        },
        {
            "name": "playwright",
            "params": {
                "phase_screenshots": False,   # economiza disco no smoke
                "revoke_after_consent": False,
                "scroll_max_iterations": 3,   # mais rápido
            },
            # último na cadeia — sem escalate_if
        },
    ],
    "abort_on": [
        {"exception": "RobotsDisallowedError"},
    ],
    "max_retries_per_fetcher": 1,
    "backoff_initial_ms": 500,
    "backoff_factor": 2.0,
}

OUT_DIR = Path("data/smoke_fallback_chain")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _bar(c="=", w=78):
    return c * w


def summarize(domain, evidence, error, elapsed):
    print()
    print(_bar("="))
    print(f"URL:     {domain.url}")
    print(f"Estrato: {domain.stratum}")
    print(f"Tempo:   {elapsed:.2f}s")

    if error is not None:
        print(f"FALHA:   {type(error).__name__}: {error}")
        return

    print(f"Fetcher vencedor: {evidence.fetcher_name}")

    # Audit do chain (linhas com prefixo 'chain.')
    audit = [e for e in evidence.errors if e.startswith("chain.")]
    print(f"\n[Chain audit: {len(audit)} eventos]")
    for line in audit:
        print(f"  {line}")

    # Cookies por fase — dict dinâmico, chaves variam por fetcher final do chain
    cbp = evidence.cookies_by_phase
    if cbp:
        print(f"\n[Cookies por fase] (chaves: {sorted(cbp.keys())})")
        pre = cbp.get("pre_consent", [])
        post = cbp.get("post_consent", [])
        single = cbp.get("single", [])
        if pre:
            print(f"  pre_consent:    {len(pre)}")
        if post:
            print(f"  post_consent:   {len(post)} (delta: {len(post) - len(pre):+d})")
        if single:
            print(f"  single:         {len(single)} (HttpFetcher single-shot)")

    # Consent actions
    if evidence.consent_actions:
        print(f"\n[Consent actions: {len(evidence.consent_actions)}]")
        for a in evidence.consent_actions:
            status = "OK" if a.get("success") else "FALHOU"
            print(f"  [{a['phase']}] {status} duration={a['duration_ms']}ms")

    # Subpáginas
    print(f"\n[Subpáginas detectadas]")
    if not evidence.subpage_selection:
        print("  (nenhuma)")
    for cat, items in evidence.subpage_selection.items():
        for it in items:
            print(f"  [{cat}] against={it['matched_against']} url={it['url']}")

    # HTML pages
    print(f"\n[HTML pages: {len(evidence.html_pages)}]")
    for path, body in evidence.html_pages.items():
        print(f"  {path:60s} {len(body):>10,} bytes")

    # Outros erros (não-chain)
    non_chain = [e for e in evidence.errors if not e.startswith("chain.")]
    if non_chain:
        print(f"\n[Erros não-chain: {len(non_chain)}]")
        for e in non_chain[:5]:
            print(f"  - {e}")


async def fetch_one(chain, domain, params):
    t0 = time.perf_counter()
    try:
        ev = await chain.fetch(domain, params)
        return ev, None, time.perf_counter() - t0
    except (FetchError, RobotsDisallowedError) as e:
        return None, e, time.perf_counter() - t0
    except Exception as e:
        return None, e, time.perf_counter() - t0


def _safe_host(url):
    return url.replace("https://", "").replace("http://", "").replace("/", "_").strip("_")


def persist(domain, evidence):
    host = _safe_host(domain.url)
    for path, body in evidence.html_pages.items():
        safe = path.replace("/", "_").lstrip("_") or "root"
        (OUT_DIR / f"{host}__{safe}.html").write_bytes(body)
    dump = evidence.model_dump(mode="python")
    dump["html_pages"] = {k: f"<{len(v):,} bytes>" for k, v in evidence.html_pages.items()}
    dump.pop("screenshot", None)
    dump["phase_screenshots"] = {k: f"<{len(v):,} bytes>" for k, v in evidence.phase_screenshots.items()}
    (OUT_DIR / f"{host}.json").write_text(
        json.dumps(dump, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


async def main():
    # Instancia fetchers concretos
    http = HttpFetcher()
    playwright = PlaywrightFetcher(headless=True)
    chain = FallbackChain(fetchers=[http, playwright])

    print(_bar("#"))
    print(f"# Smoke test do FallbackChain (HttpFetcher + PlaywrightFetcher)")
    print(f"# Alvos:                  {len(TARGETS)}")
    print(f"# Sinais de escalonamento: html_root_smaller, cookies_pre_consent_zero, subpage_selection_empty, has_js_shell_markers")
    print(f"# Saída:                  {OUT_DIR.resolve()}")
    print(_bar("#"))

    for domain in TARGETS:
        ev, err, elapsed = await fetch_one(chain, domain, CHAIN_PARAMS)
        summarize(domain, ev, err, elapsed)
        if ev is not None:
            persist(domain, ev)
            print(f"\n  -> artefatos em {OUT_DIR / _safe_host(domain.url)}.json + .html")

    print()
    print(_bar("="))
    print(f"Concluído. Inspecione: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
