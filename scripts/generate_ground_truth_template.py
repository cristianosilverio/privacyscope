"""
Gera template CSV para rotulagem manual do pré-piloto.

Lê o protocol.yaml, extrai os domínios (de override_domains ou sources), e
escreve um CSV com colunas em branco para cada variável + confidence + notes.

O CSV resultante será preenchido manualmente pelo Cristiano enquanto navega
nos 10 sites em browser limpo, e depois cruzado com o output do framework
via compare_to_ground_truth.py.

Uso::

    python scripts/generate_ground_truth_template.py protocols/prepilot.yaml \
        --out data/prepilot/ground_truth_template.csv

Critério de rotulagem (replica Tabela 1 do docx V1):

    tem_banner_cookies = True
        sse aparece banner de cookies em browser limpo em até 5s.

    tem_politica_privacidade = True
        sse em ate 3 cliques a partir da home eu encontro pagina rotulada
        como politica/aviso/declaracao/notificacao/portal de privacidade,
        descrevendo o tratamento de dados conforme LGPD.

    tem_canal_titular = True
        sse encontro e-mail DPO/encarregado/lgpd/privacidade@ OU
        portal/formulario de exercicio de direitos.

Confidence: high (certeza absoluta) / medium (achei mas com dúvida) /
low (talvez exista mas não achei facil) / unknown (não consegui avaliar).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml


VARIABLES = ("tem_banner_cookies", "tem_politica_privacidade", "tem_canal_titular")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("protocol", type=Path, help="Caminho do protocol.yaml")
    p.add_argument(
        "--out", type=Path, default=Path("data/prepilot/ground_truth_template.csv"),
        help="Caminho do CSV de saida. Padrao: data/prepilot/ground_truth_template.csv",
    )
    args = p.parse_args()

    protocol = yaml.safe_load(args.protocol.read_text(encoding="utf-8"))

    domains = protocol.get("override_domains") or []
    if not domains:
        # Não suporta sources aqui — o pré-piloto usa override_domains explícito.
        print("ERRO: protocol.yaml precisa ter 'override_domains' com lista de URLs.", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)

    headers = ["domain_url"]
    for v in VARIABLES:
        headers.append(f"{v}_value")          # True/False/unknown
        headers.append(f"{v}_confidence")     # high/medium/low/unknown
    headers.append("notes")

    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for dom in domains:
            row = [dom]
            for _ in VARIABLES:
                row.extend(["", ""])  # value + confidence em branco
            row.append("")  # notes
            writer.writerow(row)

    print(f"OK gerado: {args.out}")
    print(f"  {len(domains)} dominios para rotular")
    print(f"  {len(headers)} colunas")
    print()
    print(f"Proximo passo: abra cada URL em browser limpo (anonimo), aplique o")
    print(f"criterio do header deste script, e preencha as colunas _value (True/False)")
    print(f"e _confidence (high/medium/low/unknown) para cada variavel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
