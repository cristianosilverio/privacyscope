"""
Sorteio SUPLEMENTAR do estrato governamental do B7.

Motivo: a amostra original de 50 candidatos gov (protocols/b7_sample.csv) rendeu
apenas 33 coletas vivas (17 dominios mortos/inacessiveis, mesmo apos endurecer o
fetcher com ignore_https_errors + www-fallback). Para atingir o alvo
pre-registrado de 40 gov, sorteamos candidatos gov ADICIONAIS da MESMA lista
Tranco (mantendo o frame amostral), excluindo os 50 ja usados.

Reproduzivel: mesma lista (list_id), mesmas heuristicas de exclusao do sample_b7
(reusa sample_b4), dedup por dominio registravel, e semente fixa NOVA (20260525)
documentada. Saida: protocols/b7_gov_supp_sample.csv (coluna 'aprovado' em
branco) para REVISAO MANUAL antes de gerar o protocolo de coleta.

Uso::

    python scripts/sample_b7_gov_supp.py --list-id 43Z8X \\
        --exclude-csv protocols/b7_sample.csv \\
        --out protocols/b7_gov_supp_sample.csv
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

import tldextract

from sample_b4 import (
    DEFAULT_EXCLUDED_SUBSTRINGS,
    _is_excluded,
    _is_infrastructure_subdomain,
    _registered_domain,
)

# Semente NOVA do sorteio suplementar (data da decisao) — reprodutibilidade.
DEFAULT_SEED = 20260525
DEFAULT_N_GOV_SUPP = 20


def _host(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").rstrip("/").lower()


def _load_exclusion_regs(exclude_csv: Path, extract) -> set[str]:
    """Dominios registraveis dos candidatos gov JA usados (a excluir do pool)."""
    regs: set[str] = set()
    if not exclude_csv.exists():
        return regs
    with open(exclude_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("estrato") or "").strip().lower().startswith("govern"):
                host = _host(row.get("dominio") or row.get("url") or "")
                if host:
                    regs.add(_registered_domain(host, extract))
    return regs


def build_gov_pool(domains, extract, excluded_substrings):
    """Reproduz o ramo gov do stratify_and_sample: exclusao + dedup, em ordem de rank."""
    seen: set[str] = set()
    gov_pool = []
    for dom in domains:
        host = _host(dom.url)
        if _is_excluded(host, excluded_substrings) or _is_infrastructure_subdomain(host):
            continue
        reg = _registered_domain(host, extract)
        if reg in seen:
            continue
        seen.add(reg)
        if host.endswith(".gov.br"):
            gov_pool.append(dom)
    return gov_pool


def write_csv(rows, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ordem", "estrato", "rank_tranco", "dominio", "url", "aprovado"])
        for i, dom in enumerate(rows, start=1):
            host = dom.url.replace("https://", "").rstrip("/")
            w.writerow([i, "governamental", getattr(dom, "rank", "") or "", host, dom.url, ""])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--list-id", default="43Z8X")
    p.add_argument("--top-n", type=int, default=1_000_000)
    p.add_argument("--n-gov-supp", type=int, default=DEFAULT_N_GOV_SUPP)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--exclude-csv", type=Path, default=Path("protocols/b7_sample.csv"))
    p.add_argument("--out", type=Path, default=Path("protocols/b7_gov_supp_sample.csv"))
    p.add_argument("--cache-root", type=Path, default=Path("data/raw"))
    args = p.parse_args()

    from privacyscope.sources.tranco import TrancoSource

    extract = tldextract.TLDExtract(cache_dir=str(args.cache_root / "tldextract_cache"))
    src = TrancoSource(cache_root=args.cache_root)
    print(f"Carregando Tranco list_id={args.list_id} top_n={args.top_n} filtro=.br ...")
    domains = list(src.list_domains({
        "list_id": args.list_id, "top_n": args.top_n, "tld_filters": [".br"],
    }))
    print(f"  dominios .br: {len(domains)}")

    gov_pool = build_gov_pool(domains, extract, DEFAULT_EXCLUDED_SUBSTRINGS)
    excl = _load_exclusion_regs(args.exclude_csv, extract)
    remaining = [d for d in gov_pool if _registered_domain(_host(d.url), extract) not in excl]

    print(f"  gov_pool total:               {len(gov_pool)}")
    print(f"  exclusao (gov ja usados):     {len(excl)}")
    print(f"  gov disponiveis pos-exclusao: {len(remaining)}")

    rng = random.Random(args.seed)
    n = min(args.n_gov_supp, len(remaining))
    supp = rng.sample(remaining, n)
    write_csv(supp, args.out)
    print(f"\nOK: {n} candidatos gov suplementares -> {args.out}")
    print("Proximo: revise o CSV (coluna 'aprovado'=true), depois gero o protocolo b7_gov_supp.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
