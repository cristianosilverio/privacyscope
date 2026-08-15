# -*- coding: utf-8 -*-
"""Exportacao do artefato do classificador de ``tem_canal_titular``.

PROPOSITO
---------
Produz o artefato que o arcabouco emprega em operacao, a partir do ajuste unico
sobre a amostra inteira. Difere de scripts/modelar_canal.py, que estima DESEMPENHO
por validacao cruzada, e reaproveita o ajuste de scripts/ajuste_final_canal.py, que
produz a equacao publicavel e a inferencia por coeficiente.

**Nenhuma metrica de acerto e emitida aqui.** O desempenho provem exclusivamente da
validacao cruzada, que avalia cada sitio por um modelo que nao o utilizou no ajuste;
metrica apurada sobre a amostra do proprio ajuste e otimista por construcao.

O LIMIAR
--------
Fixado em 0,5, que e o ponto de operacao sob o qual as metricas reportadas foram
apuradas — acuracia balanceada de 0,880 e coeficiente de Matthews de 0,774. Os
limiares de triagem por ausencia, derivados de revocacoes-alvo, constituem leitura
alternativa e nao entram aqui: ponto de operacao distinto e OUTRO artefato, com
identidade propria, e nao parametro que o protocolo ajusta. Permitir a troca no
protocolo romperia a atomicidade que da sentido ao resumo criptografico.

A ORDEM DOS ATRIBUTOS
---------------------
E o risco principal deste artefato. Coeficientes atribuidos a colunas trocadas
produzem probabilidade plausivel e errada, sem que nada acuse. Por isso os nomes
viajam no arquivo e a inferencia recebe um mapeamento, nunca um vetor: a ordenacao
e feita contra os nomes gravados, e atributo ausente interrompe a execucao.

Uso:
    python scripts/exportar_modelo_canal.py
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from privacyscope.features.canal_titular import (            # noqa: E402
    ATRIBUTOS, PARAMETROS, VERSAO_EXTRATOR,
)
from privacyscope.models.artefato import (                   # noqa: E402
    grava_canal, le_canal, resumo_texto,
)

_spec = importlib.util.spec_from_file_location("firth", REPO / "scripts" / "firth.py")
_firth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_firth)

VARIAVEL = "tem_canal_titular"
VERSAO_MODELO = "1.0.0"
LIMIAR = 0.5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="outputs/features_canal_N200.csv")
    ap.add_argument("--destino", default="models")
    ap.add_argument("--versao", default=VERSAO_MODELO)
    ap.add_argument("--limiar", type=float, default=LIMIAR)
    args = ap.parse_args()

    with (REPO / args.features).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    faltando = [a for a in ATRIBUTOS if a not in R[0]]
    if faltando:
        print(f"ERRO: a matriz nao tem os atributos {faltando}.")
        print(f"      Regenere com: python scripts/extrair_features_canal.py --janela 200")
        return 2

    X = np.array([[float(r[a]) for a in ATRIBUTOS] for r in R], dtype=float)
    y = np.array([int(r["y"]) for r in R], dtype=int)

    # O resumo identifica a matriz que sustentou o ajuste, sem carrega-la. Emprega-se
    # a linha inteira, e nao apenas os atributos: rotulo trocado e material distinto.
    corpo_sha = resumo_texto(f"{r['site_id']}|" + "|".join(r[a] for a in ATRIBUTOS)
                             + f"|{r['y']}" for r in R)

    print(f"matriz: {len(R)} sitios, {len(ATRIBUTOS)} atributos")
    print(f"prevalencia da presenca: {y.mean() * 100:.1f}%")
    print(f"extrator: versao {VERSAO_EXTRATOR}, janela {PARAMETROS['janela']}")
    print(f"resumo da matriz: {corpo_sha}\n")

    ajuste = _firth.firth_logistic(X, y)
    beta = ajuste["beta"] if isinstance(ajuste, dict) else ajuste
    beta = np.asarray(beta, dtype=float).ravel()
    if len(beta) == len(ATRIBUTOS) + 1:
        intercepto, coef = float(beta[0]), beta[1:]
    else:
        raise SystemExit(f"ajuste devolveu {len(beta)} coeficientes; "
                         f"esperados {len(ATRIBUTOS) + 1} com o intercepto")

    destino = REPO / args.destino
    arquivo = destino / f"canal-titular-v{args.versao}.npz"
    sha = grava_canal(arquivo, variavel=VARIAVEL, atributos=ATRIBUTOS,
                      coeficientes=coef, intercepto=intercepto, limiar=args.limiar,
                      extrator_versao=VERSAO_EXTRATOR, extrator_parametros=PARAMETROS,
                      corpo_sha256=corpo_sha, n_observacoes=len(R),
                      gerado_por=f"exportar_modelo_canal.py v{args.versao}")

    # Conferencia imediata: o artefato tem de reproduzir o ajuste de origem.
    a = le_canal(arquivo, sha)
    eta = X @ coef + intercepto
    esperado = 1.0 / (1.0 + np.exp(-eta))
    obtido = np.array([a.probabilidade(dict(zip(ATRIBUTOS, linha))) for linha in X])
    dif = float(np.abs(obtido - esperado).max())
    estado = "confere" if dif < 1e-12 else f"DIVERGE em {dif:.2e}"

    print(f"{'atributo':32}{'beta':>12}{'razao de chances':>20}")
    print(f"  {'intercepto':30}{intercepto:>12.4f}{np.exp(intercepto):>20.4f}")
    for nome, b in zip(ATRIBUTOS, coef):
        print(f"  {nome:30}{b:>12.4f}{np.exp(b):>20.4f}")
    print(f"\narquivo   {arquivo.name}  ({arquivo.stat().st_size / 1e3:.1f} kB)")
    print(f"sha256    {sha}")
    print(f"limiar    {args.limiar}")
    print(f"releitura {estado}")

    manifesto = destino / "MANIFESTO.csv"
    linha = {"variavel": VARIAVEL, "arquivo": arquivo.name, "sha256": sha,
             "C": "", "limiar": args.limiar, "n_atributos": len(ATRIBUTOS),
             "positivos": int(y.sum()), "corpo_sha256": corpo_sha,
             "preparo_versao": VERSAO_EXTRATOR, "cobertura_p05": "",
             "cobertura_mediana": "",
             "exportado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    escreve_cabecalho = not manifesto.exists()
    with manifesto.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linha), delimiter=";")
        if escreve_cabecalho:
            w.writeheader()
        w.writerow(linha)
    print(f"\nmanifesto: {manifesto}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
