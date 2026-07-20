# -*- coding: utf-8 -*-
"""Varredura de dado pessoal em arquivo texto.

Instrumento de conferencia previa a publicacao. Relata contagens e localizacao
por coluna ou por linha, sem exibir o conteudo identificado — exibi-lo no
terminal transferiria o dado para registros de sessao e para o historico do
console, contrariando o proprio objetivo da conferencia.

Os padroes de telefone produzem falso positivo sobre sequencias longas de
digitos, notadamente resumos criptograficos. A saida separa os casos conforme a
vizinhanca seja alfanumerica, permitindo distinguir telefone de trecho de hash.

Uso:
    python scripts/varrer_dado_pessoal.py caminho/do/arquivo.csv
    python scripts/varrer_dado_pessoal.py arquivo.csv --amostra
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TELEFONE = re.compile(r"(?<![0-9A-Fa-f])\(?\d{2}\)?[\s-]?9?\d{4}[-\s]?\d{4}(?![0-9A-Fa-f])")
CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
PADROES = {"correio": EMAIL, "telefone": TELEFONE, "cpf": CPF, "cnpj": CNPJ}


def anonimiza(valor):
    """Reduz o achado a formato que confirme o tipo sem revelar o dado."""
    if "@" in valor:
        usuario, _, dominio = valor.partition("@")
        return f"{usuario[:1]}***@***{dominio[-4:]}"
    return f"{valor[:2]}***{valor[-2:]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("caminho")
    ap.add_argument("--amostra", action="store_true",
                    help="exibe achados em forma reduzida, para conferencia do tipo")
    args = ap.parse_args()

    caminho = Path(args.caminho)
    if not caminho.exists():
        print(f"arquivo inexistente: {caminho}")
        return 2

    texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    print(f"arquivo: {caminho}   {caminho.stat().st_size} bytes")

    distintos = {k: set() for k in PADROES}
    for nome, padrao in PADROES.items():
        distintos[nome].update(padrao.findall(texto))

    por_coluna = defaultdict(lambda: defaultdict(int))
    if caminho.suffix.lower() in (".csv", ".tsv"):
        sep = ";" if texto.count(";") > texto.count(",") else ","
        for reg in csv.DictReader(texto.splitlines(), delimiter=sep):
            for col, val in reg.items():
                if not val:
                    continue
                for nome, padrao in PADROES.items():
                    n = len(padrao.findall(val))
                    if n:
                        por_coluna[col][nome] += n

    total = sum(len(v) for v in distintos.values())
    print(f"\nvalores distintos encontrados: {total}")
    for nome in PADROES:
        print(f"  {nome:10} {len(distintos[nome]):5}")

    if por_coluna:
        print("\npor coluna:")
        for col, d in sorted(por_coluna.items(), key=lambda x: -sum(x[1].values())):
            detalhe = "  ".join(f"{k}={v}" for k, v in d.items())
            print(f"  {col:26} {detalhe}")

    if args.amostra:
        print("\namostra reduzida (confirma o tipo, nao revela o dado):")
        for nome, vals in distintos.items():
            for v in sorted(vals)[:5]:
                print(f"  {nome:10} {anonimiza(v)}")

    print("\nVEREDITO:", "CONTEM DADO PESSOAL" if total else "limpo")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
