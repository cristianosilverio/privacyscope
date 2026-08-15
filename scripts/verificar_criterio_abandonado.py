# -*- coding: utf-8 -*-
"""Verificacao retrospectiva do criterio de repeticao abandonado.

POR QUE ESTE PROGRAMA EXISTE
----------------------------
A etapa de preparo do texto empregou, ate 11/08/2026, um filtro de navegacao por
REPETICAO, com dois contadores sob o mesmo corte:

    A, intra-sitio    o texto ocorre `corte` vezes ou mais no MESMO sitio
    B, entre-sitios   o texto ocorre em `corte` sitios DISTINTOS ou mais

O criterio foi substituido por deduplicacao intra-sitio. Um dos tres argumentos que
sustentaram a substituicao e CITADO NO TRABALHO: o contador entre-sitios descartava
segmentos portadores de evidencia, isto e, removia declaracao junto com material de
plataforma.

Numero citado exige verificacao executavel. Sem este programa, a afirmacao seria
alegacao sobre um mecanismo que nao existe mais no codigo e que, portanto, ninguem
poderia conferir.

O QUE ELE FAZ, E O QUE NAO FAZ
------------------------------
Recomputa os dois contadores sobre o conjunto INTEGRAL de unidades, confronta o
resultado com os valores afirmados no texto e ENCERRA COM ERRO se divergirem. Nao
decide nada: a decisao esta tomada, e a deduplicacao e o procedimento em vigor.

HISTORICO DE UMA CORRECAO
-------------------------
A medicao original devolveu SETE segmentos com evidencia no balde exclusivo do
contador entre-sitios. Aquele numero saiu de execucao conduzida sem a pasta do TCC,
que descartava em silencio todo o texto de politica publicada em PDF — 47.609
unidades em lugar de 53.171. Sobre o material completo o valor e TREZE, quase o
dobro, o que reforca a decisao em vez de enfraquece-la.

E o motivo pelo qual a verificacao passou a ser executavel e a confrontar valores
declarados: numero conferido uma vez, num ambiente, nao permanece conferido.

Pre-requisito:
    python scripts/segmentar_politicas.py --manter-duplicatas \
           --out outputs/segmentos_com_navegacao.csv

Uso:
    python scripts/verificar_criterio_abandonado.py
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPET_MAX = 30

# Valores afirmados no trabalho e no contrato do preparo. Alterar aqui exige alterar
# la, e vice-versa — e a divergencia entre os dois e o que este programa detecta.
#
#   docs/pipeline-segmentacao.md, etapa 5, justificativa da substituicao
#   TCC, Metodo, paragrafo da deduplicacao
AFIRMADO = {
    "corte": 5,
    "evidencia_so_entre_sitios": 13,
    "sitios_sem_alcance_intra": 78,
}


def carrega(caminho: Path) -> list[dict]:
    csv.field_size_limit(10 ** 7)
    with caminho.open(encoding="utf-8", newline="") as fh:
        linhas = list(csv.DictReader(fh, delimiter=";"))
    if not linhas:
        raise SystemExit(f"ABORTADO: {caminho} vazio.")
    if "duplicata" not in linhas[0]:
        raise SystemExit(
            f"ABORTADO: {caminho} nao traz a coluna `duplicata`, o que indica que foi "
            f"gerado sem --manter-duplicatas. Sem as copias descartadas, os contadores "
            f"do criterio abandonado nao sao recomputaveis.")
    return linhas


def contadores(linhas: list[dict]):
    """Reproduz os dois contadores tal como o criterio abandonado os apurava.

    A contagem percorre uma unica fatia de variavel porque o arquivo esta em formato
    longo: a mesma unidade comparece uma vez por variavel, e conta-la tres vezes
    triplicaria as ocorrencias.
    """
    var0 = linhas[0]["variavel"]
    fatia = [l for l in linhas if l["variavel"] == var0]
    ocorr = Counter((l["site_id"], l["texto"]) for l in fatia)
    sitios: dict[str, set] = defaultdict(set)
    for l in fatia:
        sitios[l["texto"]].add(l["site_id"])
    return fatia, ocorr, sitios


def apura_corte(linhas, ocorr, sitios) -> int:
    """Menor corte em que nenhum documento rotulado perde toda a evidencia."""
    por_doc: dict[tuple, list] = defaultdict(list)
    for l in linhas:
        if l["y"] == "1":
            por_doc[(l["site_id"], l["variavel"])].append(l)

    def zera(c: int) -> bool:
        for ls in por_doc.values():
            atingidos = [l for l in ls
                         if ocorr[(l["site_id"], l["texto"])] >= c
                         or len(sitios[l["texto"]]) >= c]
            if atingidos and len(atingidos) == len(ls):
                return True
        return False

    corte = next((c for c in range(2, REPET_MAX + 1) if not zera(c)), None)
    if corte is None:
        raise SystemExit("ABORTADO: nenhum corte ate o teto preserva a evidencia.")
    return corte


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="outputs/segmentos_com_navegacao.csv")
    ap.add_argument("--out", default="outputs/criterio_abandonado.csv")
    args = ap.parse_args()

    caminho = REPO / args.entrada
    if not caminho.exists():
        print(f"ERRO: {caminho} nao existe. Gere antes com:")
        print(f"  python scripts/segmentar_politicas.py --manter-duplicatas \\")
        print(f"         --out {args.entrada}")
        return 2

    linhas = carrega(caminho)
    fatia, ocorr, sitios = contadores(linhas)
    corte = apura_corte(linhas, ocorr, sitios)

    def em_A(l): return ocorr[(l["site_id"], l["texto"])] >= corte
    def em_B(l): return len(sitios[l["texto"]]) >= corte

    baldes = {
        "so A (intra-sitio)": lambda l: em_A(l) and not em_B(l),
        "so B (entre-sitios)": lambda l: em_B(l) and not em_A(l),
        "os dois": lambda l: em_A(l) and em_B(l),
        "preservado": lambda l: not em_A(l) and not em_B(l),
    }
    print(f"conjunto integral: {len(fatia):,} unidades, "
          f"{len({l['site_id'] for l in fatia})} politicas")
    print(f"corte reproduzido pela regra declarada: {corte}\n")
    print(f"  {'balde':24}{'segmentos':>12}{'com evidencia':>16}")
    saida = []
    contagens = {}
    for nome, cond in baldes.items():
        n = sum(1 for l in fatia if cond(l))
        ev = sum(1 for l in linhas if cond(l) and l["y"] == "1")
        contagens[nome] = ev
        print(f"  {nome:24}{n:>12,}{ev:>16}")
        saida.append({"balde": nome, "segmentos": n, "com_evidencia": ev})

    maxpor: dict[str, int] = defaultdict(int)
    for (s, _), n in ocorr.items():
        maxpor[s] = max(maxpor[s], n)
    inertes = sum(1 for n in maxpor.values() if n < corte)
    print(f"\n  sitios em que o contador intra-sitio nunca dispararia: "
          f"{inertes} de {len(maxpor)}")
    saida.append({"balde": "sitios sem alcance do contador intra-sitio",
                  "segmentos": inertes, "com_evidencia": ""})

    obtido = {"corte": corte,
              "evidencia_so_entre_sitios": contagens["so B (entre-sitios)"],
              "sitios_sem_alcance_intra": inertes}
    divergem = {k: (AFIRMADO[k], obtido[k]) for k in AFIRMADO if AFIRMADO[k] != obtido[k]}

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["balde", "segmentos", "com_evidencia"],
                           delimiter=";")
        w.writeheader(); w.writerows(saida)
    print(f"\nsaida: {out}")

    print(f"\n{'=' * 70}")
    if not divergem:
        print("  CONFERE — os valores afirmados no trabalho correspondem ao material.")
        for k, v in AFIRMADO.items():
            print(f"    {k:32} {v}")
        print(f"{'=' * 70}")
        return 0
    print("  DIVERGE — os valores afirmados no trabalho NAO correspondem ao material.")
    for k, (esperado, achado) in divergem.items():
        print(f"    {k:32} afirmado {esperado}, apurado {achado}")
    print("\n  Corrija o texto, ou a constante AFIRMADO deste programa, conforme o caso.")
    print("  Os valores aparecem em docs/pipeline-segmentacao.md e no TCC.")
    print(f"{'=' * 70}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
