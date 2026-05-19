"""
Smoke test do FileSystemRepository — coleta real + persistência + audit.

Valida o ciclo completo:
    1. Coleta com FallbackChain (HttpFetcher -> PlaywrightFetcher) em 1 site real.
    2. Persiste com FileSystemRepository (gera tar.gz + manifest.jsonl + audit_log).
    3. Inspeciona layout interno do tar.gz.
    4. Audita o manifest com verify_manifest.
    5. Round-trip: get() recupera RawEvidence, compara hash bytes a bytes.
    6. Tamper test: altera 1 byte e confirma verify() retorna False.

Alvo padrão: ``https://www.serpro.gov.br`` (validado ontem; banner detectável,
poucos cookies, tempo razoável). Pode ser ajustado em TARGETS.

Execução::

    python -m scripts.smoke_filesystem_repo
    # ou
    python scripts/smoke_filesystem_repo.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tarfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from privacyscope.core.types import Domain
from privacyscope.fetchers.fallback_chain import FallbackChain
from privacyscope.fetchers.http_fetcher import HttpFetcher
from privacyscope.fetchers.playwright_fetcher import PlaywrightFetcher
from privacyscope.storage.filesystem_repo import FileSystemRepository
from privacyscope.storage.manifest_audit import verify_manifest


# ----------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------
TARGETS = [
    Domain(url="https://www.serpro.gov.br", tld=".br", source_name="manual"),
]

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "smoke_fs_repo"

# Config no formato do protocol.yaml — declara cada fetcher do chain.
CHAIN_PARAMS: dict = {
    "fetchers": [
        {
            "name": "http_simples",
            "params": {
                "connect_timeout_s": 10,
                "read_timeout_s": 30,
                "respect_robots_txt": True,
                "max_per_category": 1,
                "max_total_subpages": 3,
            },
            "escalate_if": [
                {"exception": "NavigationFailedError"},
                {"exception": "JsRequiredError"},
                {"signal": "html_root_smaller_than_bytes", "threshold": 5000},
                {"signal": "cookies_pre_consent_zero"},
                {"signal": "subpage_selection_empty"},
                {"signal": "has_js_shell_markers"},
            ],
        },
        {
            "name": "playwright",
            "params": {
                "phase_screenshots": True,
                "revoke_after_consent": False,
                "scroll_max_iterations": 3,
                "max_per_category": 1,
                "max_total_subpages": 3,
            },
        },
    ],
    "abort_on": [{"exception": "RobotsDisallowedError"}],
}


def _bar(c: str = "=") -> str:
    return c * 78


async def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    chain = FallbackChain(fetchers=[HttpFetcher(), PlaywrightFetcher()])

    repo = FileSystemRepository(OUT_DIR)
    run_id = str(uuid.uuid4())

    print(_bar("#"))
    print(f"# Smoke do FileSystemRepository")
    print(f"# Alvos:   {len(TARGETS)}")
    print(f"# run_id:  {run_id}")
    print(f"# Saída:   {OUT_DIR.resolve()}")
    print(_bar("#"))

    refs = []
    for domain in TARGETS:
        print(f"\n[1] Coletando {domain.url} via FallbackChain...")
        t0 = time.perf_counter()
        evidence = await chain.fetch(domain, CHAIN_PARAMS)
        elapsed = time.perf_counter() - t0
        print(f"    fetcher_name: {evidence.fetcher_name}")
        print(f"    elapsed:      {elapsed:.1f}s")
        print(f"    cookies_by_phase keys: {sorted(evidence.cookies_by_phase.keys())}")
        for ph, ck in evidence.cookies_by_phase.items():
            print(f"      {ph}: {len(ck)} cookies")
        print(f"    phase_screenshots keys: {sorted(evidence.phase_screenshots.keys())}")
        print(f"    html_pages keys: {len(evidence.html_pages)}")
        print(f"    errors count: {len(evidence.errors)}")

        print(f"\n[2] Persistindo via FileSystemRepository.put()...")
        ref = repo.put(evidence, run_id, protocol_version_hash="smoke-protocol-hash")
        print(f"    tar:    {Path(ref.path).name}")
        print(f"    sha256: {ref.sha256[:32]}...")
        print(f"    size:   {Path(ref.path).stat().st_size:,} bytes")

        print(f"\n[3] Layout interno do tar.gz:")
        with tarfile.open(ref.path, "r:gz") as tar:
            for name in sorted(tar.getnames()):
                info = tar.getmember(name)
                kind = "DIR " if info.isdir() else "FILE"
                size = f"{info.size:>10,}" if info.isfile() else ""
                print(f"    {kind}  {size}  {name}")

        print(f"\n[4] verify(ref):")
        ok = repo.verify(ref)
        print(f"    integridade: {ok}")
        assert ok

        print(f"\n[5] Round-trip via get(ref):")
        recovered = repo.get(ref)
        equal_cookies = recovered.cookies_by_phase == evidence.cookies_by_phase
        equal_html = recovered.html_pages == evidence.html_pages
        equal_screenshots = recovered.phase_screenshots == evidence.phase_screenshots
        equal_headers = recovered.headers == evidence.headers
        print(f"    cookies_by_phase idêntico:  {equal_cookies}")
        print(f"    html_pages idêntico:        {equal_html}")
        print(f"    phase_screenshots idêntico: {equal_screenshots}")
        print(f"    headers idêntico:           {equal_headers}")
        assert all([equal_cookies, equal_html, equal_screenshots, equal_headers])

        refs.append(ref)

    print(f"\n[6] Auditoria do manifest (verify_manifest):")
    report = verify_manifest(OUT_DIR)
    print(f"    total_entries:        {report.total_entries}")
    print(f"    verified:             {report.verified}")
    print(f"    missing:              {report.missing}")
    print(f"    corrupted:            {report.corrupted}")
    print(f"    audit_log_consistent: {report.audit_log_consistent}")
    print(f"    manifest_sha256:      {report.manifest_sha256[:32]}...")
    print(f"    all_valid:            {report.all_valid}")
    assert report.all_valid

    print(f"\n[7] Tamper test (altera 1 byte do tar.gz):")
    target = Path(refs[0].path)
    size = target.stat().st_size
    with open(target, "r+b") as f:
        f.seek(size // 2)
        b = f.read(1)
        f.seek(size // 2)
        f.write(bytes([b[0] ^ 0xFF]))
    tampered = repo.verify(refs[0])
    print(f"    verify após adulteração: {tampered}  (esperado: False)")
    assert tampered is False
    report2 = verify_manifest(OUT_DIR)
    print(f"    verify_manifest após adulteração:")
    print(f"      corrupted: {report2.corrupted}  (esperado: 1)")
    print(f"      all_valid: {report2.all_valid}  (esperado: False)")
    assert report2.corrupted == 1 and report2.all_valid is False

    print()
    print(_bar("="))
    print(f"Concluído. Artefatos em: {OUT_DIR.resolve()}")
    print(f"  raw/manifest.jsonl     ({(OUT_DIR / 'raw' / 'manifest.jsonl').stat().st_size:,} bytes)")
    print(f"  raw/audit_log.jsonl    ({(OUT_DIR / 'raw' / 'audit_log.jsonl').stat().st_size:,} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
