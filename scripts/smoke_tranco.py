"""Smoke test manual do TrancoSource contra a Tranco real."""
import logging
import time
import json
import hashlib
import shutil
from collections import Counter
from pathlib import Path

from privacyscope.sources import TrancoSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

# Lista diária da Tranco de 16/05/2026, obtida via API /api/lists/date/YYYY-MM-DD
LIST_ID = "43KLX"
TOP_N = 100000
CACHE = Path("data/raw")  # cache em data/raw/tranco/

# Descomente para forçar re-download e ver o caminho de download completo:
# shutil.rmtree(CACHE / "tranco", ignore_errors=True)

src = TrancoSource(cache_root=CACHE)

# ---------- RUN 1: filtro .br genérico ----------
print(f"\n=== RUN 1: list_id={LIST_ID}, top_n={TOP_N:,}, tld_filters=['.br'] ===")
t0 = time.perf_counter()
br = list(src.list_domains({
    "list_id": LIST_ID,
    "top_n": TOP_N,
    "tld_filters": [".br"],
}))
print(f"Encontrados {len(br):,} domínios .br em {time.perf_counter() - t0:.1f}s")

dist = Counter(d.tld for d in br)
print("\nDistribuição por TLD efetivo (top 10):")
for tld, n in dist.most_common(10):
    print(f"  {tld:20s} {n:6,}")

# ---------- Foco no estrato governamental ----------
gov = [d for d in br if d.tld == ".gov.br"]
print(f"\nDomínios .gov.br no top {TOP_N:,}: {len(gov):,}")
print("Primeiros 15 (com rank Tranco):")
for d in gov[:15]:
    print(f"  rank={d.rank:6d}  {d.url}")

# ---------- RUN 2: cache hit (deve ser instantâneo) ----------
print(f"\n=== RUN 2 (cache hit): tld_filters=['.gov.br', '.com.br'] ===")
t0 = time.perf_counter()
mix = list(src.list_domains({
    "list_id": LIST_ID,
    "top_n": TOP_N,
    "tld_filters": [".gov.br", ".com.br"],
}))
elapsed = time.perf_counter() - t0
print(f"{len(mix):,} domínios em {elapsed:.2f}s (cache hit, esperado <1s)")
print(f"  .gov.br: {sum(1 for d in mix if d.tld == '.gov.br'):,}")
print(f"  .com.br: {sum(1 for d in mix if d.tld == '.com.br'):,}")

# ---------- Verificação de integridade ----------
mfst_path = CACHE / "tranco" / f"{LIST_ID}_top{TOP_N}.manifest.json"
csv_path = CACHE / "tranco" / f"{LIST_ID}_top{TOP_N}.csv.gz"
manifest = json.loads(mfst_path.read_text())
recomputed = hashlib.sha256(csv_path.read_bytes()).hexdigest()

print(f"\n=== Verificação de integridade (cadeia de custódia da entrada) ===")
print(f"Manifest:")
print(json.dumps(manifest, indent=2, ensure_ascii=False))
print(f"\nSHA-256 do cache (recomputado agora):")
print(f"  {recomputed}")
print(f"Confere com manifest? {recomputed == manifest['sha256']}")
print(f"Received as gzip?     {manifest['received_as_gzip']}")