"""
Smoke integrado do C2 — coleta real + 3 VariableTests + persistência.

Pipeline:
    Domain -> FallbackChain -> FileSystemRepository.put()
                            -> BannerCookiesTest, PoliticaPrivacidadeTest,
                               CanalTitularTest -> SQLiteResultStore.upsert()
                            -> SQLiteResultStore.query()

Alvos: 3 sites baseline (gov.br/anpd, serpro.gov.br, uol.com.br) para
permitir comparação entre estratos governamental e empresarial.
"""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from pathlib import Path

from privacyscope.core.plugin_registry import resolve, list_plugins
from privacyscope.core.types import Domain
from privacyscope.fetchers.fallback_chain import FallbackChain
from privacyscope.fetchers.http_fetcher import HttpFetcher
from privacyscope.fetchers.playwright_fetcher import PlaywrightFetcher


CHAIN_PARAMS = {
    "fetchers": [
        {
            "name": "http_simples",
            "params": {"respect_robots_txt": True, "max_per_category": 1, "max_total_subpages": 4},
            "escalate_if": [
                {"signal": "cookies_pre_consent_zero"},
                {"signal": "html_root_smaller_than_bytes", "threshold": 5000},
                {"signal": "has_js_shell_markers"},
            ],
        },
        {
            "name": "playwright",
            "params": {"phase_screenshots": True, "revoke_after_consent": False, "scroll_max_iterations": 3,
                       "max_per_category": 1, "max_total_subpages": 4},
        },
    ],
    "abort_on": [{"exception": "RobotsDisallowedError"}],
}

TARGETS = [
    Domain(url="https://www.gov.br/anpd/pt-br", tld=".br", source_name="manual"),
    Domain(url="https://www.serpro.gov.br", tld=".br", source_name="manual"),
    Domain(url="https://www.uol.com.br", tld=".br", source_name="manual"),
]


def _bar(c: str = "=") -> str:
    return c * 78


async def main() -> None:
    OUT = Path(__file__).resolve().parent.parent / "data" / "smoke_c2"
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    chain = FallbackChain(fetchers=[HttpFetcher(), PlaywrightFetcher()])

    RepoCls = resolve("repositories", "filesystem")
    StoreCls = resolve("result_stores", "sqlite")
    test_classes = [
        resolve("variable_tests", "banner_cookies"),
        resolve("variable_tests", "politica_privacidade"),
        resolve("variable_tests", "canal_titular"),
    ]
    tests = [cls() for cls in test_classes]

    repo = RepoCls(OUT)
    store = StoreCls(OUT / "results.sqlite")

    run_id = str(uuid.uuid4())
    protocol_version = "c2-smoke-0.1.0"

    store.begin_run(run_id, protocol_version=protocol_version, sample_size=len(TARGETS))

    print(_bar("#"))
    print(f"# Smoke C2 integrado — 3 VariableTests deterministicos")
    print(f"# Alvos:    {len(TARGETS)}")
    print(f"# run_id:   {run_id}")
    print(f"# Saída:    {OUT.resolve()}")
    print(_bar("#"))

    print(f"\nRegistry inventário:")
    for layer, names in list_plugins().items():
        print(f"  {layer}: {names}")

    for domain in TARGETS:
        print(f"\n{_bar('=')}")
        print(f"[Coletando] {domain.url}")
        t0 = time.perf_counter()
        ev = await chain.fetch(domain, CHAIN_PARAMS)
        elapsed = time.perf_counter() - t0
        print(f"  fetcher={ev.fetcher_name}  elapsed={elapsed:.1f}s")
        print(f"  cookies_by_phase keys: {sorted(ev.cookies_by_phase.keys())}")
        print(f"  subpage_selection categorias: {sorted(ev.subpage_selection.keys())}")
        for cat, items in ev.subpage_selection.items():
            print(f"    [{cat}] {len(items)} candidato(s)")

        ref = repo.put(ev, run_id, protocol_version_hash=protocol_version)
        print(f"\n  tar.gz: {Path(ref.path).name}")
        print(f"  sha256: {ref.sha256[:32]}...")

        print(f"\n  [Aplicando 3 VariableTests]")
        for test in tests:
            result = test.evaluate(ev, {}, protocol_version=protocol_version, run_id=run_id)
            store.upsert(result)
            via = result.audit_trail.get("matched_via") or result.audit_trail.get("source") or "?"
            print(f"    {result.variable_name:30s} value={result.value!s:5s} conf={result.confidence:.2f}  via={via}")

    store.finish_run(run_id)

    print(f"\n{_bar('=')}")
    print(f"[Query final no SQLite]")
    rows = list(store.query({"run_id": run_id}))
    print(f"  {len(rows)} VariableResult persistidos")
    print(f"\n  {'domain_url':35s} {'variable':30s} {'value':5s} {'conf':5s}")
    print(f"  {'-'*35} {'-'*30} {'-'*5} {'-'*5}")
    for r in rows:
        print(f"  {r.domain_url[:35]:35s} {r.variable_name:30s} {str(r.value):5s} {r.confidence:.2f}")
    store.close()

    print(f"\nArtefatos:")
    print(f"  raw/manifest.jsonl    {(OUT / 'raw' / 'manifest.jsonl').stat().st_size:,} bytes")
    print(f"  raw/audit_log.jsonl   {(OUT / 'raw' / 'audit_log.jsonl').stat().st_size:,} bytes")
    print(f"  results.sqlite        {(OUT / 'results.sqlite').stat().st_size:,} bytes")


if __name__ == "__main__":
    asyncio.run(main())
