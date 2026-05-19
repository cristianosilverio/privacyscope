"""
Smoke integrado do C1 — exercita as 5 camadas que entraram em C1.

Pipeline simulado:
    Domain -> FallbackChain -> FileSystemRepository.put()
                            -> BannerCookiesTest.evaluate()
                            -> SQLiteResultStore.upsert()
                            -> SQLiteResultStore.query()

Não substitui o orchestrator (que entra no C3 com Orchestrator + CLI);
aqui o flow é hard-coded para validar que as peças compõem corretamente.

Alvo: serpro.gov.br (validado nos smokes anteriores).
"""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from privacyscope.core.plugin_registry import resolve
from privacyscope.core.types import Domain
from privacyscope.fetchers.fallback_chain import FallbackChain
from privacyscope.fetchers.http_fetcher import HttpFetcher
from privacyscope.fetchers.playwright_fetcher import PlaywrightFetcher


CHAIN_PARAMS = {
    "fetchers": [
        {
            "name": "http_simples",
            "params": {"respect_robots_txt": True, "max_per_category": 1, "max_total_subpages": 3},
            "escalate_if": [
                {"signal": "cookies_pre_consent_zero"},
                {"signal": "html_root_smaller_than_bytes", "threshold": 5000},
                {"signal": "has_js_shell_markers"},
            ],
        },
        {
            "name": "playwright",
            "params": {"phase_screenshots": True, "revoke_after_consent": False, "scroll_max_iterations": 3,
                       "max_per_category": 1, "max_total_subpages": 3},
        },
    ],
    "abort_on": [{"exception": "RobotsDisallowedError"}],
}


async def main() -> None:
    OUT = Path(__file__).resolve().parent.parent / "data" / "smoke_c1"
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    chain = FallbackChain(fetchers=[HttpFetcher(), PlaywrightFetcher()])

    # Plugins via registry
    RepoCls = resolve("repositories", "filesystem")
    StoreCls = resolve("result_stores", "sqlite")
    TestCls = resolve("variable_tests", "banner_cookies")

    repo = RepoCls(OUT)
    store = StoreCls(OUT / "results.sqlite")
    test = TestCls()

    run_id = str(uuid.uuid4())
    protocol_version = "c1-smoke-0.1.0"

    domains = [
        Domain(url="https://www.serpro.gov.br", tld=".br", source_name="manual"),
    ]

    store.begin_run(run_id, protocol_version=protocol_version, sample_size=len(domains))

    print(f"# Smoke C1 integrado — run_id={run_id}")
    print(f"# Saída: {OUT.resolve()}\n")

    for domain in domains:
        print(f"[Coletando] {domain.url}")
        t0 = time.perf_counter()
        ev = await chain.fetch(domain, CHAIN_PARAMS)
        elapsed_fetch = time.perf_counter() - t0
        print(f"  fetcher_name={ev.fetcher_name} elapsed={elapsed_fetch:.1f}s")
        print(f"  cookies_by_phase keys: {sorted(ev.cookies_by_phase.keys())}")

        print(f"[Persistindo evidência]")
        ref = repo.put(ev, run_id, protocol_version_hash=protocol_version)
        print(f"  tar.gz: {Path(ref.path).name}")
        print(f"  sha256: {ref.sha256[:32]}...")

        print(f"[Aplicando BannerCookiesTest]")
        result = test.evaluate(ev, {}, protocol_version=protocol_version, run_id=run_id)
        print(f"  value={result.value}")
        print(f"  confidence={result.confidence}")
        print(f"  audit_trail.matched_via={result.audit_trail['matched_via']}")
        print(f"  audit_trail.lexicon_hit_count={result.audit_trail['lexicon_hit_count']}")
        if result.audit_trail['vendor_hits']:
            print(f"  audit_trail.vendor_hits: {[h['vendor'] for h in result.audit_trail['vendor_hits']]}")

        print(f"[Persistindo VariableResult]")
        store.upsert(result)
        print(f"  ok")

    store.finish_run(run_id)

    # Query final
    print(f"\n[Query final no SQLite]")
    rows = list(store.query({"run_id": run_id}))
    print(f"  {len(rows)} VariableResult persistidos")
    for r in rows:
        print(f"    {r.domain_url:35s} {r.variable_name:30s} value={r.value} confidence={r.confidence}")

    store.close()

    print(f"\nArtefatos:")
    print(f"  raw/manifest.jsonl    {(OUT / 'raw' / 'manifest.jsonl').stat().st_size} bytes")
    print(f"  raw/audit_log.jsonl   {(OUT / 'raw' / 'audit_log.jsonl').stat().st_size} bytes")
    print(f"  results.sqlite        {(OUT / 'results.sqlite').stat().st_size} bytes")


if __name__ == "__main__":
    asyncio.run(main())
