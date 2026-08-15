# -*- coding: utf-8 -*-
"""Ajuste final e exportacao dos artefatos das tres variaveis textuais.

PROPOSITO, E O QUE ESTE PROGRAMA NAO FAZ
----------------------------------------
Produz o artefato que o arcabouco emprega em operacao. Difere de
scripts/modelar_textuais.py, que estima DESEMPENHO por particao que deixa um
documento de fora. As duas finalidades nao sao intercambiaveis:

  - o desempenho provem exclusivamente daquela particao, que avalia cada segmento
    por um modelo ajustado sem o documento a que ele pertence;
  - o artefato provem deste ajuste unico sobre as quinze politicas, porque media
    de coeficientes ao longo das particoes nao equivale ao ajuste sobre o conjunto
    completo.

**Nenhuma metrica de acerto e emitida aqui.** Metrica apurada sobre a mesma amostra
empregada no ajuste e otimista por construcao, e exibi-la ao lado dos coeficientes
convidaria a confusao entre as duas finalidades.

SELECAO DA REGULARIZACAO E DO LIMIAR
------------------------------------
Pelo mesmo procedimento das particoes internas de modelar_textuais.py — particao
agrupada por sitio sobre as politicas de treino, escolhendo conjuntamente a forca da
regularizacao e o limiar pelo coeficiente de Matthews sobre predicoes fora do
ajuste. A diferenca e o escopo: aqui o procedimento percorre as quinze politicas,
ao passo que na avaliacao ele percorria as catorze de cada dobra.

Fixar esses valores a priori foi cogitado e descartado por medicao: a analise de
sensibilidade mostrou o coeficiente de Matthews da transferencia internacional
variando de 0,370 a 0,700 conforme a regularizacao adotada. Sob variacao dessa
magnitude, fixar o parametro nao e conduta conservadora — e sorteio.

COBERTURA DE VOCABULARIO, APURADA FORA DO AJUSTE
------------------------------------------------
A cobertura serve para marcar extrapolacao em material novo, e por isso NAO pode
ser medida sobre os proprios documentos que constituiram o vocabulario: ali ela e
otimista por construcao, e o limiar dela nunca dispararia.

Apura-se deixando um documento de fora: para cada politica, mede-se a cobertura de
seus segmentos contra o vocabulario ajustado sobre as outras catorze. E a
estimativa do que um documento NAO VISTO exibe, que e exatamente a situacao de quem
executa o arcabouco contra a propria lista de sitios.

UM ARTEFATO POR VARIAVEL
------------------------
As tres variaveis compartilham o mesmo vocabulario, porque o vetorizador se ajusta
sobre os mesmos segmentos. Ainda assim grava-se um arquivo por variavel, com sua
copia do vocabulario. A duplicacao custa cerca de um decimo de megabyte por
variavel e compra independencia: cada artefato e substituivel sozinho, sem reescrever
os demais, e o protocolo declara um resumo criptografico por teste.

Uso:
    python scripts/exportar_modelo_textuais.py
    python scripts/exportar_modelo_textuais.py --variavel finalidade
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

from privacyscope.models.artefato import grava, le, resumo_texto   # noqa: E402
from privacyscope.text.segmentacao import PARAMETROS, VERSAO_PREPARO  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "mt", REPO / "scripts" / "modelar_textuais.py")
_mt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mt)

VARIAVEIS = _mt.VARIAVEIS
ROTULO = _mt.ROTULO
VERSAO_MODELO = "1.0.0"


def cobertura_fora_do_ajuste(textos, grupos, semente=0):
    """Quantis da cobertura de vocabulario que um documento nao visto exibe.

    Para cada politica, ajusta-se o vetorizador sobre as demais e mede-se a fracao
    das sequencias de seus segmentos que constam do vocabulario resultante.
    """
    valores = []
    for g in np.unique(grupos):
        tr, te = grupos != g, grupos == g
        vec = _mt.vetorizador()
        vec.fit([textos[i] for i in np.where(tr)[0]])
        analisa = vec.build_analyzer()
        vocab = vec.vocabulary_
        for i in np.where(te)[0]:
            termos = analisa(textos[i])
            if termos:
                valores.append(sum(1 for t in termos if t in vocab) / len(termos))
    v = np.asarray(valores, dtype=float)
    return {"n": int(v.size),
            "p05": float(np.percentile(v, 5)),
            "p25": float(np.percentile(v, 25)),
            "mediana": float(np.median(v)),
            "p75": float(np.percentile(v, 75)),
            "media": float(v.mean())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpo", default="outputs/segmentos_rotulados.csv")
    ap.add_argument("--destino", default="models")
    ap.add_argument("--versao", default=VERSAO_MODELO)
    ap.add_argument("--variavel", choices=VARIAVEIS, default=None)
    args = ap.parse_args()

    csv.field_size_limit(10 ** 7)
    with (REPO / args.corpo).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    textos = [r["texto"] for r in R]
    sitios = sorted({r["site_id"] for r in R})
    idx = {s: i for i, s in enumerate(sitios)}
    grupos = np.array([idx[r["site_id"]] for r in R])

    # O resumo do corpo identifica o material do ajuste sem carrega-lo. Emprega-se
    # a ordem de gravacao do arquivo, que e determinista.
    corpo_sha = resumo_texto(textos)
    print(f"corpo: {len(R):,} segmentos, {len(sitios)} politicas")
    print(f"resumo do corpo: {corpo_sha}")
    print(f"preparo de texto: versao {VERSAO_PREPARO}\n")

    print("cobertura de vocabulario, apurada fora do ajuste...")
    cobertura = cobertura_fora_do_ajuste(textos, grupos)
    print(f"  sobre {cobertura['n']:,} segmentos: mediana {cobertura['mediana']:.3f}, "
          f"p05 {cobertura['p05']:.3f}, p25 {cobertura['p25']:.3f}\n")

    destino = REPO / args.destino
    destino.mkdir(parents=True, exist_ok=True)
    linhas = []
    for v in ([args.variavel] if args.variavel else VARIAVEIS):
        y = np.array([int(r[v]) for r in R])
        C, limiar = _mt.seleciona_interno(textos, y, grupos)
        vec = _mt.vetorizador()
        X = vec.fit_transform(textos)
        from sklearn.linear_model import LogisticRegression
        m = LogisticRegression(C=C, max_iter=3000, solver="liblinear").fit(X, y)

        arquivo = destino / f"textuais-{v}-v{args.versao}.npz"
        sha = grava(arquivo, variavel=v,
                    vocabulario={t: int(j) for t, j in vec.vocabulary_.items()},
                    idf=vec.idf_, coeficientes=m.coef_[0],
                    intercepto=float(m.intercept_[0]), limiar=float(limiar),
                    regularizacao=float(C), ngramas=(1, 3), minusculas=True, sublinear_tf=True,
                    preparo_versao=VERSAO_PREPARO, preparo_parametros=PARAMETROS,
                    corpo_sha256=corpo_sha, cobertura_treino=cobertura,
                    gerado_por=f"exportar_modelo_textuais.py v{args.versao}")

        # Conferencia imediata: o artefato tem de reproduzir o ajuste de origem.
        # Gravar sem reler deixaria passar defeito de serializacao ate a producao.
        a = le(arquivo, sha)
        amostra = textos[:800]
        dif = float(np.abs(a.probabilidades(amostra)
                           - m.predict_proba(vec.transform(amostra))[:, 1]).max())
        estado = "confere" if dif < 1e-10 else f"DIVERGE em {dif:.2e}"

        print(f"{ROTULO[v]}")
        print(f"  positivos {int(y.sum()):>5}   atributos {X.shape[1]:>7,}   "
              f"C {C:<7} limiar {limiar:.3f}")
        print(f"  arquivo   {arquivo.name}  ({arquivo.stat().st_size/1e6:.2f} MB)")
        print(f"  sha256    {sha}")
        print(f"  releitura {estado}\n")
        linhas.append({"variavel": v, "arquivo": arquivo.name, "sha256": sha,
                       "C": C, "limiar": limiar, "n_atributos": int(X.shape[1]),
                       "positivos": int(y.sum()), "corpo_sha256": corpo_sha,
                       "preparo_versao": VERSAO_PREPARO,
                       "cobertura_p05": cobertura["p05"],
                       "cobertura_mediana": cobertura["mediana"],
                       "exportado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")})

    manifesto = destino / "MANIFESTO.csv"
    campos = list(linhas[0])
    escreve_cabecalho = not manifesto.exists()
    with manifesto.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=";")
        if escreve_cabecalho:
            w.writeheader()
        w.writerows(linhas)
    print(f"manifesto: {manifesto}")
    print("\nDeclare no protocolo, por variavel, o arquivo e o resumo acima.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
