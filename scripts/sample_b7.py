"""
Amostragem estratificada do B7 (expansao n=200).

Reutiliza a logica validada de scripts/sample_b4.py (dedup por dominio
registravel, exclusao de infraestrutura/encurtadores, estratos por .gov.br,
amostragem aleatoria com semente fixa). Mantem a sobre-representacao do estrato
governamental adotada no B4 (panorama de mercado, nao comparacao entre estratos).

Alvo: 160 empresariais + 40 governamentais (n=200). Buffer assimetrico (falhas concentram no corp): corp +30% (208) e gov +25% (50) para
folga de falhas de coleta; a selecao final por estrato e pos-processada do SQLite.

Saida: protocols/b7_sample.csv para REVISAO MANUAL antes de gerar o b7.yaml.

Uso::

    python scripts/sample_b7.py --list-id 43Z8X --out protocols/b7_sample.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Reusa as funcoes puras (sem duplicar logica) de sample_b4.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sample_b4 import stratify_and_sample, write_csv  # noqa: E402

DEFAULT_SEED = 20260524          # data da decisao do B7 (reprodutibilidade)
DEFAULT_N_CORP = 208             # alvo 160 + 30% de buffer (corp falha ~20% no B4)
DEFAULT_N_GOV = 50               # alvo 40 + 25% de buffer


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--list-id", required=True, help="ID da lista Tranco (tranco-list.eu)")
    p.add_argument("--out", type=Path, default=Path("protocols/b7_sample.csv"))
    p.add_argument("--n-corp", type=int, default=DEFAULT_N_CORP)
    p.add_argument("--n-gov", type=int, default=DEFAULT_N_GOV)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--top-n", type=int, default=1_000_000)
    a = p.parse_args()

    from privacyscope.sources.tranco import TrancoSource
    src = TrancoSource()
    print(f"Carregando Tranco list_id={a.list_id} top_n={a.top_n} filtro=.br ...")
    domains = list(src.list_domains({
        "list_id": a.list_id, "top_n": a.top_n, "tld_filters": [".br"],
    }))
    print(f"  dominios .br carregados: {len(domains)}")

    rep = stratify_and_sample(domains, n_corp=a.n_corp, n_gov=a.n_gov, seed=a.seed)

    print("\n=== Diagnostico ===")
    print(f"  total .br processados:        {rep.total_br}")
    print(f"  excluidos (heuristica):       {rep.excluded_count}")
    print(f"  deduplicados:                 {rep.deduped_count}")
    print(f"  governamentais disponiveis:   {rep.total_gov_available}")
    print(f"  empresariais disponiveis:     {rep.total_corp_available}")
    print(f"\n  amostrados governamentais:    {len(rep.gov)} (alvo {a.n_gov})")
    print(f"  amostrados empresariais:      {len(rep.corp)} (alvo {a.n_corp})")
    if rep.gov_shortfall:
        print("\n  AVISO: .gov.br na Tranco .br < alvo. Complementar com a lista")
        print("  oficial de dominios .gov.br (fallback ja previsto na amostragem).")

    write_csv(rep, a.out)
    print(f"\nOK: {len(rep.gov)+len(rep.corp)} candidatos -> {a.out}")
    print("Proximo: revise o CSV (coluna 'aprovado') e me avise para gerar protocols/b7.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
