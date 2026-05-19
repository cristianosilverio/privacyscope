"""
Smoke test manual do PlaywrightFetcher contra sites brasileiros reais.

Compara empiricamente o que o HttpFetcher não consegue ver: cookies pré vs
pós-consent, subpáginas descobertas via DOM renderizado, etc.

Uso:
    cd C:\\Dev\\privacyscope
    .\\.venv\\Scripts\\Activate.ps1
    playwright install chromium   # apenas na primeira vez
    python scripts/smoke_playwright_fetcher.py

Para testar o fluxo de revoke (opt-in):
    Edite PARAMS abaixo: "revoke_after_consent": True
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from pathlib import Path

from privacyscope.core import Domain
from privacyscope.fetchers import (
    DEFAULT_CONSENT_BANNER_CONFIG,
    DEFAULT_PRIVACY_CENTER_CONFIG,
    DEFAULT_SUBPAGE_CATEGORIES,
    FetchError,
    NavigationFailedError,
    PlaywrightFetcher,
    RobotsDisallowedError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
# Reduz ruído do Playwright
logging.getLogger("websockets").setLevel(logging.WARNING)

# Mesmos 3 alvos do smoke do HttpFetcher para comparar empiricamente
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

PARAMS: dict = {
    "phase_screenshots": True,
    "revoke_after_consent": False,   # liga para testar fluxo completo
    "navigation_timeout_ms": 30_000,
    "networkidle_timeout_ms": 5_000,
    "consent_click_timeout_ms": 3_000,
    "scroll_max_iterations": 5,
    "scroll_wait_ms": 500,
    # Filtro do network_log — None = registrar tudo
    # "network_log_resource_types": ["document", "xhr", "fetch"],
    "max_per_category": 1,
    "max_total_subpages": 5,
}

OUT_DIR = Path("data/smoke_playwright_fetcher")
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

    print(f"Fetcher: {evidence.fetcher_name}")
    print(f"Timestamp UTC: {evidence.timestamp_utc.isoformat()}")

    # Cookies por fase
    pre = evidence.cookies_pre_consent
    post = evidence.cookies_post_consent
    revoke = evidence.cookies_post_revocation
    print(f"\n[Cookies por fase]")
    print(f"  pre_consent:        {len(pre):>4}")
    print(f"  post_consent:       {len(post):>4}    (delta: {len(post) - len(pre):+d})")
    if revoke:
        print(f"  post_revocation:    {len(revoke):>4}    (delta: {len(revoke) - len(post):+d})")

    if post and len(post) > len(pre):
        # Mostra os cookies adicionais ativados pelo accept
        pre_names = {c["name"] for c in pre}
        new_after_accept = [c for c in post if c["name"] not in pre_names]
        print(f"  -> {len(new_after_accept)} cookies novos após accept (primeiros 6):")
        for c in new_after_accept[:6]:
            flags = []
            if c.get("secure"): flags.append("Secure")
            if c.get("httpOnly"): flags.append("HttpOnly")
            print(f"     {c['name']:35s} domain={c['domain']:30s} {' '.join(flags)}")

    # Ações de consent
    print(f"\n[Consent actions: {len(evidence.consent_actions)}]")
    for a in evidence.consent_actions:
        status = "OK" if a.get("success") else "FALHOU"
        print(f"  [{a['phase']}] {status} method={a.get('method') or a.get('method_center', '?')}")
        if a.get("selector_used"):
            print(f"     selector: {a['selector_used']}")
        if a.get("button_text"):
            print(f"     button:   {a['button_text']!r}")
        print(f"     duration: {a['duration_ms']}ms")

    # Subpáginas
    print(f"\n[Subpáginas detectadas]")
    if not evidence.subpage_selection:
        print("  (nenhuma — defaults não casaram)")
    for cat, items in evidence.subpage_selection.items():
        for it in items:
            print(f"  [{cat}]")
            print(f"    URL:     {it['url']}")
            print(f"    Pattern: {it['matched_pattern']!r}")
            print(f"    Match:   contra '{it['matched_against']}' -> {it['snippet']!r}")

    # HTML pages
    print(f"\n[HTML pages coletadas: {len(evidence.html_pages)}]")
    for path, body in evidence.html_pages.items():
        print(f"  {path:60s} {len(body):>10,} bytes")

    # Screenshots
    if evidence.phase_screenshots:
        print(f"\n[Screenshots por fase]")
        for phase, png in evidence.phase_screenshots.items():
            print(f"  {phase:20s} {len(png):>10,} bytes")

    # Network log resumido
    nl = evidence.network_log
    if nl:
        by_status = Counter(e.get("status", 0) for e in nl)
        by_type = Counter(e.get("resource_type", "?") for e in nl)
        print(f"\n[Network: {len(nl)} requisições]")
        print(f"  Por status: {dict(by_status.most_common(5))}")
        print(f"  Por tipo:   {dict(by_type.most_common(10))}")

    if evidence.errors:
        print(f"\n[Erros não-fatais: {len(evidence.errors)}]")
        for e in evidence.errors:
            print(f"  - {e}")


async def fetch_one(fetcher, domain, params):
    t0 = time.perf_counter()
    try:
        ev = await fetcher.fetch(domain, params)
        return ev, None, time.perf_counter() - t0
    except (FetchError, NavigationFailedError, RobotsDisallowedError) as e:
        return None, e, time.perf_counter() - t0
    except Exception as e:
        return None, e, time.perf_counter() - t0


def _safe_host(url):
    return url.replace("https://", "").replace("http://", "").replace("/", "_").strip("_")


def persist(domain, evidence):
    host = _safe_host(domain.url)

    # HTMLs em arquivos separados
    for path, body in evidence.html_pages.items():
        safe = path.replace("/", "_").lstrip("_") or "root"
        (OUT_DIR / f"{host}__{safe}.html").write_bytes(body)

    # Screenshots por fase
    for phase, png in evidence.phase_screenshots.items():
        (OUT_DIR / f"{host}__{phase}.png").write_bytes(png)

    # Dump JSON (sem HTML, sem screenshots binários)
    dump = evidence.model_dump(mode="python")
    dump["html_pages"] = {k: f"<{len(v):,} bytes>" for k, v in evidence.html_pages.items()}
    dump.pop("screenshot", None)
    dump["phase_screenshots"] = {k: f"<{len(v):,} bytes>" for k, v in evidence.phase_screenshots.items()}
    (OUT_DIR / f"{host}.json").write_text(
        json.dumps(dump, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


async def main():
    fetcher = PlaywrightFetcher(headless=True)
    print(_bar("#"))
    print(f"# Smoke test do PlaywrightFetcher")
    print(f"# Alvos:               {len(TARGETS)}")
    print(f"# Revoke ativo:        {PARAMS.get('revoke_after_consent')}")
    print(f"# Screenshots:         {PARAMS.get('phase_screenshots')}")
    print(f"# Saída:               {OUT_DIR.resolve()}")
    print(_bar("#"))

    for domain in TARGETS:
        ev, err, elapsed = await fetch_one(fetcher, domain, PARAMS)
        summarize(domain, ev, err, elapsed)
        if ev is not None:
            persist(domain, ev)
            print(f"\n  -> artefatos em {OUT_DIR / _safe_host(domain.url)}*")

    print()
    print(_bar("="))
    print(f"Concluído. Inspecione: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
