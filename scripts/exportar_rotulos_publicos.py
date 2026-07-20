# -*- coding: utf-8 -*-
"""Gera a versao publicavel da rotulagem, sem dado pessoal.

O arquivo de trabalho reune, nas colunas de evidencia, transcricoes literais de
trechos das politicas de privacidade. Como a evidencia do canal e justamente o
contato do encarregado, essas colunas concentram enderecos de correio eletronico
e numeros de telefone.

O artigo 41 da Lei 13.709/2018 obriga o controlador a divulgar publicamente a
identidade e o contato do encarregado, de modo que tais dados ja se encontram
acessiveis. A publicidade original, porem, nao autoriza por si so a redistribuicao
em base compilada: o artigo 7, paragrafo 3, determina que o tratamento de dados de
acesso publico considere a finalidade, a boa-fe e o interesse publico que
justificaram a disponibilizacao, e a finalidade que justificou aquela divulgacao —
permitir que o titular alcance o encarregado — nao se estende a formacao de
cadastro redistribuivel.

O mesmo artigo 7, em seu inciso IV, admite o tratamento para a realizacao de
estudos, determinando a anonimizacao sempre que possivel. Aqui ela e possivel sem
qualquer perda analitica, porque a modelagem opera sobre atributos binarios
derivados do texto, e nao sobre as cadeias de caracteres: as colunas de evidencia
sustentam a auditoria da rotulagem, nao o ajuste dos modelos.

Procedimento adotado: as quatro colunas de evidencia sao suprimidas; a coluna de
observacoes e preservada, por registrar decisoes metodologicas, com mascaramento
dos identificadores; e a saida so e gravada apos varredura que confirme a ausencia
de residuo. As transcricoes integrais permanecem sob guarda do autor e podem ser
disponibilizadas para verificacao mediante solicitacao.

Uso:
    python scripts/exportar_rotulos_publicos.py
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COLUNAS_SUPRIMIDAS = ["canal_evid", "finalidade_evid", "direitos_evid", "transf_evid"]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TELEFONE = re.compile(r"\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}")


def mascarar(texto):
    """Substitui identificadores por marcador, preservando a leitura da nota."""
    texto = EMAIL.sub("[correio suprimido]", texto)
    return TELEFONE.sub("[telefone suprimido]", texto)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="rotulagem_b9.csv")
    ap.add_argument("--saida", default="outputs/rotulagem_b9_publica.csv")
    args = ap.parse_args()

    with (REPO / args.entrada).open(encoding="utf-8-sig", newline="") as fh:
        leitor = csv.DictReader(fh, delimiter=";")
        campos = [c for c in leitor.fieldnames if c not in COLUNAS_SUPRIMIDAS]
        registros = list(leitor)

    mascaradas = 0
    saida = []
    for r in registros:
        nova = {c: r.get(c, "") for c in campos}
        if nova.get("obs"):
            antes = nova["obs"]
            nova["obs"] = mascarar(antes)
            if nova["obs"] != antes:
                mascaradas += 1
        saida.append(nova)

    # varredura de conferencia: nada e gravado se sobrar residuo
    residuo = []
    for i, r in enumerate(saida, start=2):
        for k, v in r.items():
            if v and (EMAIL.search(v) or TELEFONE.search(v)):
                residuo.append((i, k))
    if residuo:
        for linha, col in residuo[:10]:
            print(f"  RESIDUO linha {linha}, coluna {col}")
        raise SystemExit(f"ABORTADO: {len(residuo)} residuos; nada foi gravado")

    destino = REPO / args.saida
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=";")
        w.writeheader(); w.writerows(saida)

    print(f"registros: {len(saida)}")
    print(f"colunas suprimidas: {', '.join(COLUNAS_SUPRIMIDAS)}")
    print(f"colunas preservadas: {len(campos)}")
    print(f"observacoes com mascaramento aplicado: {mascaradas}")
    print("varredura final: nenhum endereco ou telefone remanescente")
    print(f"\nsaida: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
