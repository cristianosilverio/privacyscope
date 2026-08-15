# -*- coding: utf-8 -*-
"""Grava no protocolo o resumo SHA-256 da lista que a fonte `csv` vai ler.

POR QUE ESTE PASSO EXISTE
-------------------------
O quadro amostral integra a cadeia de custodia como qualquer outro insumo. A fonte
`csv` confere o resumo declarado no protocolo contra o arquivo lido e INTERROMPE na
divergencia, em lugar de executar sobre lista que nao e a declarada.

Isso cria uma ordem obrigatoria: a lista nasce do programa de amostragem, e so
depois o protocolo pode declarar sua identidade. Transcrever o resumo a mao entre um
passo e outro e trabalho mecanico sobre sessenta e quatro caracteres, que e
exatamente o tipo de transcricao em que erro entra sem ser notado.

O QUE ELE NAO FAZ
-----------------
Nao valida a lista, nao a reordena e nao opina sobre o que ha nela. Registra a
identidade do que existe no disco. Se a lista estiver errada, este programa grava
fielmente o resumo da lista errada — a garantia e de correspondencia entre protocolo
e arquivo, e nao de correcao do arquivo.

A substituicao e pontual, sobre a linha `sha256:` da fonte `csv`, e nao reescreve o
YAML: reserializar apagaria os comentarios do protocolo, que sao onde as decisoes de
desenho estao registradas.

Uso:
    python scripts/declarar_lista.py protocols/exercicio_csv.yaml
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def resumo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("protocolo")
    ap.add_argument("--fonte", default="csv",
                    help="nome da fonte cuja lista se declara")
    args = ap.parse_args()

    p = Path(args.protocolo)
    if not p.is_absolute():
        p = REPO / args.protocolo
    if not p.is_file():
        print(f"ERRO: protocolo nao encontrado: {p}")
        return 2

    texto = p.read_text(encoding="utf-8")
    doc = yaml.safe_load(texto)
    fontes = [f for f in (doc.get("sources") or []) if f.get("name") == args.fonte]
    if len(fontes) != 1:
        print(f"ERRO: esperava UMA fonte `{args.fonte}` em {p.name}, "
              f"encontrei {len(fontes)}.")
        return 2

    lista = Path(fontes[0].get("params", {}).get("path", ""))
    if not lista.is_absolute():
        lista = REPO / lista
    if not lista.is_file():
        print(f"ERRO: lista nao encontrada: {lista}\n"
              f"      gere-a antes de declarar sua identidade.")
        return 2

    novo = resumo(lista)
    atual = fontes[0].get("params", {}).get("sha256")
    if atual == novo:
        print(f"sha256 ja confere: {novo}")
        return 0

    # Substituicao pontual: reserializar o YAML apagaria os comentarios, que sao
    # onde as decisoes de desenho do protocolo estao registradas.
    padrao = re.compile(r"^(\s*sha256:\s*)\S+\s*$", re.MULTILINE)
    if len(padrao.findall(texto)) != 1:
        print("ERRO: esperava exatamente uma linha `sha256:` no protocolo.")
        return 2
    p.write_text(padrao.sub(lambda m: f"{m.group(1)}{novo}", texto), encoding="utf-8")

    linhas = sum(1 for _ in lista.open(encoding="utf-8-sig")) - 1
    print(f"lista     : {lista.relative_to(REPO)} ({linhas} dominios)")
    print(f"sha256    : {novo}")
    print(f"substitui : {atual}")
    print(f"protocolo : {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
