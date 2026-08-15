# -*- coding: utf-8 -*-
"""Diagnostico do filtro de navegacao: o que cada contador remove, e o que a
deduplicacao mudaria.

MOTIVO
------
O filtro da etapa 5 remove por repeticao, sob disjuncao de dois contadores que
compartilham o mesmo corte:

    A, intra-sitio    o texto ocorre `corte` vezes ou mais no MESMO sitio
    B, entre-sitios   o texto ocorre em `corte` sitios DISTINTOS ou mais

Tres perguntas ficaram em aberto quando se redigiu o contrato do pipeline, e nenhuma
delas se decide por argumento:

  1. O contador B e computavel sobre o material de treino, que reune 145 sitios, mas
     nao sobre um sitio isolado em producao, onde a contagem de sitios distintos vale
     sempre um. Quanto material ele remove que o contador A nao removeria? Esse volume
     E a divergencia entre o preparo do treino e o do uso.

  2. O contador A so dispara se o sitio tiver subpaginas suficientes para alcancar o
     corte. Sitio com poucas subpaginas capturadas fica sem filtro algum. Quantos estao
     nessa situacao?

  3. Remover todas as ocorrencias de um texto repetido e mais severo do que o problema
     exige. O problema e DUPLICACAO — a mesma frase contada dezenas de vezes distorce a
     proporcao de classes e a ponderacao documental. Preservar UMA copia e descartar as
     demais resolveria a duplicacao sem apagar nada. O que essa conduta custaria?

O terceiro ponto merece contabilidade nos dois sentidos, e nao so no favoravel. A
deduplicacao RESTAURA segmentos hoje removidos, que nunca passaram pelo anotador e
portanto exigiriam nova rodada de marcacao; e DESCARTA copias hoje preservadas, entre
as quais ha positivos. Um positivo que ocorre quatro vezes no sitio vira um positivo.
Nenhuma evidencia distinta se perde, mas o numero de exemplos da classe rara cai, e a
variavel de transferencia internacional dispoe de quarenta e seis.

Este programa nao decide nada. Ele produz os numeros que a decisao exige.

PRE-REQUISITO
-------------
    python scripts/segmentar_politicas.py --manter-repetidos \
           --out outputs/segmentos_com_navegacao.csv

A bandeira preserva as linhas removidas e acrescenta a coluna `navegacao`. Sem ela o
material removido nao existe em disco e nada aqui e computavel.

Uso:
    python scripts/diagnostico_filtro_navegacao.py
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPET_MAX = 30


def carrega(caminho):
    csv.field_size_limit(10 ** 7)
    with caminho.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def contadores(linhas, var0):
    """Reproduz os dois contadores exatamente como o pipeline os apura.

    A contagem percorre uma unica fatia de variavel porque o arquivo esta em formato
    longo: a mesma unidade de texto comparece uma vez por variavel, e conta-la tres
    vezes triplicaria as ocorrencias.
    """
    fatia = [l for l in linhas if l["variavel"] == var0]
    ocorr = Counter((l["site_id"], l["texto"]) for l in fatia)
    sitios = defaultdict(set)
    for l in fatia:
        sitios[l["texto"]].add(l["site_id"])
    return ocorr, sitios


def apura_corte(linhas, ocorr, sitios):
    """Menor corte em que nenhum documento rotulado perde a totalidade da evidencia."""
    por_doc = defaultdict(list)
    for l in linhas:
        if l["y"] == "1":
            por_doc[(l["site_id"], l["variavel"])].append(l)

    def zera_algum(c):
        for ls in por_doc.values():
            atingidos = [l for l in ls
                         if ocorr[(l["site_id"], l["texto"])] >= c
                         or len(sitios[l["texto"]]) >= c]
            if atingidos and len(atingidos) == len(ls):
                return True
        return False

    return next((c for c in range(2, REPET_MAX + 1) if not zera_algum(c)), None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="outputs/segmentos_com_navegacao.csv")
    ap.add_argument("--rotulados", default="outputs/segmentos_rotulados.csv")
    ap.add_argument("--out", default="outputs/diagnostico_filtro_navegacao.csv")
    args = ap.parse_args()

    caminho = REPO / args.entrada
    if not caminho.exists():
        print(f"ERRO: {caminho} nao existe.")
        print("Gere-o antes com:")
        print("  python scripts/segmentar_politicas.py --manter-repetidos \\")
        print(f"         --out {args.entrada}")
        return 1

    linhas = carrega(caminho)
    if "navegacao" not in linhas[0]:
        print(f"ERRO: {args.entrada} nao tem a coluna `navegacao`.")
        print("Foi gerado sem --manter-repetidos; o material removido nao esta ali.")
        return 1

    variaveis = sorted({l["variavel"] for l in linhas})
    var0 = variaveis[0]
    ocorr, sitios = contadores(linhas, var0)
    corte = apura_corte(linhas, ocorr, sitios)
    fatia = [l for l in linhas if l["variavel"] == var0]
    rotulados = {r["site_id"] for r in carrega(REPO / args.rotulados)}

    print(f"entrada: {len(fatia):,} unidades de texto, "
          f"{len({l['site_id'] for l in fatia})} sitios, {len(variaveis)} variaveis")
    print(f"corte reproduzido: {corte}   "
          f"(o pipeline deve ter apurado o mesmo valor; divergencia indica que a "
          f"entrada nao corresponde a execucao vigente)")
    print(f"politicas com marcacao exaustiva: {len(rotulados)}\n")

    def em_A(l):
        return ocorr[(l["site_id"], l["texto"])] >= corte

    def em_B(l):
        return len(sitios[l["texto"]]) >= corte

    linhas_saida = []

    # ------------------------------------------------------------ pergunta 1
    print("=" * 100)
    print("1. O QUE CADA CONTADOR REMOVE  (o balde 'so B' e a divergencia treino/servico)")
    print("=" * 100)
    baldes = {"so A (intra-sitio)": lambda l: em_A(l) and not em_B(l),
              "so B (entre-sitios)": lambda l: em_B(l) and not em_A(l),
              "os dois": lambda l: em_A(l) and em_B(l),
              "preservado": lambda l: not em_A(l) and not em_B(l)}
    print(f"  {'balde':24}{'segmentos':>12}{'% do total':>12}{'com evidencia':>16}")
    for nome, cond in baldes.items():
        sel = [l for l in fatia if cond(l)]
        # A evidencia e o que o casamento posicional das transcricoes localizou. Um
        # segmento removido que carrega evidencia e perda real, e nao limpeza.
        ev = sum(1 for l in linhas if cond(l) and l["y"] == "1")
        print(f"  {nome:24}{len(sel):>12,}{100 * len(sel) / len(fatia):>11.2f}%{ev:>16,}")
        linhas_saida.append({"pergunta": "1. contadores", "item": nome,
                             "segmentos": len(sel), "com_evidencia": ev})
    print("\n  Leitura: se 'so B' tiver evidencia zero, o contador B esteve removendo")
    print("  cromo de plataforma e nao declaracao, e abandona-lo custa apenas falsos")
    print("  positivos adicionais na producao. Se tiver evidencia, ele protegia texto.")

    # ------------------------------------------------------------ pergunta 2
    print("\n" + "=" * 100)
    print("2. O CONTADOR A CONSEGUE DISPARAR EM CADA SITIO?")
    print("=" * 100)
    # Sem identificador de subpagina no arquivo, a maior contagem intra-sitio serve de
    # aproximacao do numero de subpaginas: o cromo comparece uma vez por subpagina.
    maxpor = defaultdict(int)
    for (s, t), n in ocorr.items():
        maxpor[s] = max(maxpor[s], n)
    inertes = sorted(s for s, n in maxpor.items() if n < corte)
    print(f"  aproximacao do numero de subpaginas = maior contagem intra-sitio")
    print(f"  sitios em que nenhum texto alcanca {corte} ocorrencias: "
          f"{len(inertes)} de {len(maxpor)}")
    print(f"    desses, com marcacao exaustiva: "
          f"{len([s for s in inertes if s in rotulados])} de {len(rotulados)}")
    if inertes:
        print(f"    exemplos: {', '.join(inertes[:6])}")
    print("\n  Leitura: nesses sitios o contador A e inerte. Sob a conduta que abandona")
    print("  o contador B, eles ficam SEM filtro de navegacao algum.")
    linhas_saida.append({"pergunta": "2. alcance do contador A",
                         "item": f"sitios em que A nunca dispara (corte {corte})",
                         "segmentos": len(inertes)})

    # ------------------------------------------------------------ pergunta 3
    print("\n" + "=" * 100)
    print("3. CUSTO DA DEDUPLICACAO  (preservar uma copia em vez de apagar todas)")
    print("=" * 100)
    removidos = [l for l in fatia if em_A(l) or em_B(l)]
    restaurados = {(l["site_id"], l["texto"]) for l in removidos}
    rest_rot = {p for p in restaurados if p[0] in rotulados}
    # Copias hoje preservadas que a deduplicacao descartaria: toda ocorrencia alem da
    # primeira, entre os textos que sobrevivem ao filtro vigente.
    descartados = sum(n - 1 for (s, t), n in ocorr.items()
                      if n > 1 and not (n >= corte or len(sitios[t]) >= corte))
    print(f"  segmentos hoje removidos:                        {len(removidos):>8,}")
    print(f"  restaurados pela deduplicacao (um por sitio/texto):{len(restaurados):>8,}")
    print(f"    destes, nas 15 politicas com marcacao exaustiva:{len(rest_rot):>8,}"
          f"   <-- NOVA RODADA DE MARCACAO")
    print(f"  copias hoje preservadas que a deduplicacao descarta:{descartados:>7,}")

    print(f"\n  Efeito sobre os positivos das politicas marcadas:")
    print(f"  {'variavel':24}{'hoje':>10}{'sob deduplicacao':>20}{'perda':>10}")
    R = carrega(REPO / args.rotulados)
    alvo = [v for v in ("finalidade", "direitos_titular", "transf_internacional")
            if v in R[0]]
    for v in alvo:
        hoje = sum(1 for r in R if r[v].strip() == "1")
        vistos = set()
        dedup = 0
        for r in R:
            if r[v].strip() == "1":
                ch = (r["site_id"], r["texto"])
                if ch not in vistos:
                    vistos.add(ch); dedup += 1
        print(f"  {v:24}{hoje:>10,}{dedup:>20,}{hoje - dedup:>10,}")
        linhas_saida.append({"pergunta": "3. deduplicacao", "item": f"positivos {v}",
                             "segmentos": hoje, "sob_deduplicacao": dedup,
                             "perda": hoje - dedup})
    linhas_saida.append({"pergunta": "3. deduplicacao", "item": "a remarcar (15 politicas)",
                         "segmentos": len(rest_rot)})
    print("\n  Leitura: a coluna 'perda' nao representa evidencia distinta perdida — a")
    print("  passagem continua no corpo, uma vez. Representa exemplos a menos da classe")
    print("  rara. Pesa contra a deduplicacao na medida em que a variavel for escassa.")

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    campos = []
    for l in linhas_saida:
        for k in l:
            if k not in campos:
                campos.append(k)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=";", restval="")
        w.writeheader(); w.writerows(linhas_saida)
    print(f"\nsaida: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
