# -*- coding: utf-8 -*-
"""Exportacao dos artefatos do teto comparativo, sobre representacao densa.

O QUE ESTE ARTEFATO E, E O QUE ELE NAO E
----------------------------------------
O teto comparativo mede quanta folga a representacao esparsa deixa. Ele NAO e o
mecanismo do arcabouco: o objeto do trabalho e a construcao do instrumento, e o
modelo pre-treinado e artefato de terceiro cujo conteudo nao se examina.

Por isso o plugin correspondente nao e habilitado na configuracao padrao. Quem
quiser remedir a folga sobre material novo executa o protocolo proprio do teto.

O ARTEFATO NAO E AUTOCONTIDO
----------------------------
Ao contrario dos outros quatro, este exige, alem do proprio arquivo, os pesos do
codificador — que nao acompanham o repositorio, por terem centenas de megabytes.
Reproduzir um resultado do teto depende de obte-los.

O que o artefato carrega e a cabeca ajustada, algumas centenas de coeficientes, e a
IDENTIDADE do codificador: resumo criptografico que cobre pesos E TOKENIZADOR.
Vocabulario de subpalavras distinto produz entrada distinta para os mesmos pesos, e
conferir apenas os pesos deixaria passar justamente a troca mais silenciosa.

SELECAO
-------
Pelo mesmo procedimento das demais variaveis — particao agrupada por sitio,
escolhendo conjuntamente a regularizacao e o limiar sobre predicoes fora do ajuste.
Nenhuma metrica de acerto e emitida aqui.

Uso:
    python scripts/exportar_modelo_bertimbau.py --codificador C:/modelos/bertimbau
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

from privacyscope.models.artefato import (                    # noqa: E402
    grava_denso, le_denso, resumo_diretorio, resumo_texto,
)
from privacyscope.text.segmentacao import VERSAO_PREPARO      # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "mb", REPO / "scripts" / "modelar_bertimbau.py")
_mb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mb)

VARIAVEIS = _mb.VARIAVEIS
ROTULO = _mb.ROTULO
VERSAO_MODELO = "1.0.0"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpo", default="outputs/segmentos_rotulados.csv")
    ap.add_argument("--vetores", default="outputs/vetores_bertimbau.npz")
    ap.add_argument("--codificador", required=True,
                    help="diretorio local com os pesos e o tokenizador")
    ap.add_argument("--agregacao", default="media", choices=["media", "cls"])
    ap.add_argument("--destino", default="models")
    ap.add_argument("--versao", default=VERSAO_MODELO)
    args = ap.parse_args()

    codificador = Path(args.codificador)
    if not codificador.is_dir():
        print(f"ERRO: {codificador} nao e um diretorio.")
        print("      Baixe o codificador uma vez e aponte o caminho local: sem ele o")
        print("      artefato identificaria o modelo por rotulo, e rotulo nao detecta")
        print("      troca de conteudo.")
        return 2
    cod_sha = resumo_diretorio(codificador)

    csv.field_size_limit(10 ** 7)
    with (REPO / args.corpo).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    z = np.load(REPO / args.vetores, allow_pickle=False)
    assert len(z["site_id"]) == len(R), "vetores e corpo tem tamanhos distintos"
    for i, r in enumerate(R):
        assert z["site_id"][i] == r["site_id"] and z["segmento_id"][i] == r["segmento_id"], \
            f"desalinhamento na linha {i}"

    nome_codificador = str(z["modelo"])
    max_len = int(z["max_len"])
    X = _mb.normaliza_linhas(z[args.agregacao].astype(np.float64))
    sitios = sorted({r["site_id"] for r in R})
    idx = {s: i for i, s in enumerate(sitios)}
    grupos = np.array([idx[r["site_id"]] for r in R])
    corpo_sha = resumo_texto(r["texto"] for r in R)

    print(f"corpo: {len(R):,} segmentos, {len(sitios)} politicas")
    print(f"codificador: {nome_codificador}")
    print(f"  diretorio: {codificador}")
    print(f"  resumo (pesos e tokenizador): {cod_sha}")
    print(f"agregacao: {args.agregacao}   teto: {max_len} subpalavras\n")

    destino = REPO / args.destino
    linhas = []
    for v in VARIAVEIS:
        y = np.array([int(r[v]) for r in R])
        C, limiar = _mb.seleciona_interno(X, y, grupos)
        from sklearn.linear_model import LogisticRegression
        m = LogisticRegression(C=C, max_iter=3000, solver="liblinear").fit(X, y)

        arquivo = destino / f"denso-{v}-v{args.versao}.npz"
        sha = grava_denso(arquivo, variavel=v, codificador=nome_codificador,
                          codificador_sha256=cod_sha, agregacao=args.agregacao,
                          max_len=max_len, coeficientes=m.coef_[0],
                          intercepto=float(m.intercept_[0]), limiar=float(limiar),
                          regularizacao=float(C), preparo_versao=VERSAO_PREPARO,
                          corpo_sha256=corpo_sha,
                          gerado_por=f"exportar_modelo_bertimbau.py v{args.versao}")
        a = le_denso(arquivo, sha)
        dif = float(np.abs(a.probabilidades(X[:800])
                           - m.predict_proba(X[:800])[:, 1]).max())
        print(f"{ROTULO[v]}")
        print(f"  positivos {int(y.sum()):>5}   dimensoes {X.shape[1]:>4}   "
              f"C {C:<7} limiar {limiar:.3f}")
        print(f"  arquivo   {arquivo.name}  ({arquivo.stat().st_size/1e3:.1f} kB)")
        print(f"  sha256    {sha}")
        print(f"  releitura {'confere' if dif < 1e-10 else f'DIVERGE em {dif:.2e}'}\n")
        linhas.append({"variavel": f"{v}__denso", "arquivo": arquivo.name,
                       "sha256": sha, "C": C, "limiar": limiar,
                       "n_atributos": int(X.shape[1]), "positivos": int(y.sum()),
                       "corpo_sha256": corpo_sha, "preparo_versao": VERSAO_PREPARO,
                       "cobertura_p05": "", "cobertura_mediana": "",
                       "exportado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")})

    manifesto = destino / "MANIFESTO.csv"
    escreve_cabecalho = not manifesto.exists()
    with manifesto.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0]), delimiter=";")
        if escreve_cabecalho:
            w.writeheader()
        w.writerows(linhas)
    print(f"manifesto: {manifesto}")
    print(f"\nO codificador NAO acompanha o repositorio. Declare o diretorio local no")
    print(f"protocolo do teto, em `codificador_dir`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
