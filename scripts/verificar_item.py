# -*- coding: utf-8 -*-
"""Verificacao de aceite de cada item da camada de analise.

Executa a suite de testes do item e, alem dela, as conferencias que exigem o
material real do trabalho — as que nao cabem em teste unitario porque dependem do
corpo rotulado e dos pacotes de evidencia.

Cada item so e dado por concluido quando este programa imprime APROVADO. O criterio
de cada um esta declarado abaixo, junto com o motivo de existir.

Uso:
    python scripts/verificar_item.py 2
    python scripts/verificar_item.py 2 --verboso
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

VERDE, VERMELHO, FIM = "\033[32m", "\033[31m", "\033[0m"


class Relatorio:
    def __init__(self) -> None:
        self.itens: list[tuple[bool, str, str]] = []

    def afere(self, ok: bool, titulo: str, detalhe: str = "") -> None:
        self.itens.append((bool(ok), titulo, detalhe))
        marca = f"{VERDE}  OK  {FIM}" if ok else f"{VERMELHO} FALHA{FIM}"
        print(f"{marca}  {titulo}")
        if detalhe:
            for linha in detalhe.splitlines():
                print(f"          {linha}")

    @property
    def aprovado(self) -> bool:
        return all(ok for ok, _, _ in self.itens)


def roda_testes(alvo: str, verboso: bool) -> bool:
    print(f"\n--- suite de testes: {alvo} ---")
    r = subprocess.run([sys.executable, "-m", "pytest", alvo, "-q" if not verboso else "-v"],
                       cwd=REPO, env={**__import__("os").environ,
                                      "PYTHONPATH": str(REPO / "src")})
    return r.returncode == 0


# ===========================================================================
def item_2(rel: Relatorio, verboso: bool) -> None:
    """Artefato de modelo.

    O que se exige, e por que:

      IDENTIDADE  O artefato tem resumo criptografico proprio e a leitura recusa
                  arquivo cuja identidade nao confere. Sem isso, resultado
                  atribuido a um modelo poderia ter vindo de outro.
      AUSENCIA DE CODIGO  O arquivo e recipiente de dados. Se contivesse objeto
                  serializado, le-lo seria executa-lo, e conferi-lo exigiria
                  confiar em quem o produziu.
      EQUIVALENCIA  A vetorizacao propria coincide com a da biblioteca de
                  aprendizado sobre o CORPO REAL. E ela que autoriza a inferencia
                  a nao depender da versao instalada daquela biblioteca.
      PROVENIENCIA  Resumo do conjunto de treino e versao do preparo viajam dentro
                  do artefato, de sorte que a origem seja verificavel sem o corpo.
    """
    import csv
    import numpy as np
    from privacyscope.models.artefato import (
        ArtefatoCorrompido, grava, le, resumo_arquivo, resumo_texto)
    from privacyscope.text.segmentacao import PARAMETROS, VERSAO_PREPARO

    corpo = REPO / "outputs" / "segmentos_rotulados.csv"
    if not corpo.exists():
        rel.afere(False, "corpo rotulado disponivel",
                  f"nao encontrado: {corpo}\nrode antes: python scripts/construir_corpo_textuais.py")
        return

    csv.field_size_limit(10 ** 7)
    with corpo.open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    textos = [r["texto"] for r in R]
    y = np.array([int(r["finalidade"]) for r in R])
    rel.afere(len(R) > 0, "corpo rotulado carregado",
              f"{len(R):,} segmentos, {len({r['site_id'] for r in R})} politicas")

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    vec = TfidfVectorizer(lowercase=True, stop_words=None, ngram_range=(1, 3),
                          min_df=3, sublinear_tf=True, norm="l2", strip_accents=None)
    X = vec.fit_transform(textos)
    m = LogisticRegression(C=10.0, max_iter=3000, solver="liblinear").fit(X, y)
    print(f"        ajuste de referencia: {X.shape[1]:,} atributos")

    # Diretorio temporario, e nao outputs/: a verificacao nao deve deixar residuo
    # no repositorio nem depender de permissao de remocao no destino.
    tmp = tempfile.TemporaryDirectory(prefix="privacyscope-verif-")
    destino = Path(tmp.name) / "artefato.npz"
    sha = grava(destino, variavel="finalidade",
                vocabulario={t: int(j) for t, j in vec.vocabulary_.items()},
                idf=vec.idf_, coeficientes=m.coef_[0],
                intercepto=float(m.intercept_[0]), limiar=0.44,
                preparo_versao=VERSAO_PREPARO, preparo_parametros=PARAMETROS,
                corpo_sha256=resumo_texto(textos),
                cobertura_treino={"p05": 0.30, "mediana": 0.70},
                gerado_por="verificar_item.py")
    a = le(destino, sha)
    rel.afere(a.sha256 == sha == resumo_arquivo(destino),
              "identidade: resumo do arquivo confere na leitura", sha)

    try:
        le(destino, "0" * 64)
        rel.afere(False, "identidade: artefato divergente interrompe a execucao")
    except ArtefatoCorrompido:
        rel.afere(True, "identidade: artefato divergente interrompe a execucao")

    bruto = destino.read_bytes()
    rel.afere(b"sklearn" not in bruto and b"__reduce__" not in bruto,
              "ausencia de codigo: o arquivo nao carrega objeto serializado",
              f"{len(bruto)/1e6:.2f} MB")

    amostra = textos[:1500]
    A = a.vetoriza(amostra)
    B = vec.transform(amostra).toarray()
    dif = float(np.abs(A - B).max())
    rel.afere(dif < 1e-12, "equivalencia: vetorizacao propria == biblioteca",
              f"maior diferenca absoluta: {dif:.2e} sobre {len(amostra):,} segmentos")

    pa = a.probabilidades(amostra)
    pb = m.predict_proba(vec.transform(amostra))[:, 1]
    difp = float(np.abs(pa - pb).max())
    rel.afere(difp < 1e-10, "equivalencia: probabilidade propria == biblioteca",
              f"maior diferenca absoluta: {difp:.2e}")

    rel.afere(a.preparo_versao == VERSAO_PREPARO and a.corpo_sha256,
              "proveniencia: versao do preparo e resumo do corpo gravados",
              f"preparo {a.preparo_versao}   corpo {a.corpo_sha256[:16]}...")

    cob = [a.cobertura(t) for t in amostra[:300]]
    rel.afere(min(cob) <= max(cob) and max(cob) > 0,
              "cobertura de vocabulario computavel",
              f"mediana {float(np.median(cob)):.2f}, minimo {min(cob):.2f}, maximo {max(cob):.2f}")
    estranho = a.cobertura("zzz qqq www vvv uuu ttt")
    rel.afere(a.em_extrapolacao(estranho),
              "extrapolacao detectada em texto fora do vocabulario",
              f"cobertura do texto estranho: {estranho:.2f}")

    tmp.cleanup()


ITENS = {2: ("Artefato de modelo", "tests_unit/test_artefato.py", item_2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("item", type=int, choices=sorted(ITENS))
    ap.add_argument("--verboso", action="store_true")
    args = ap.parse_args()

    titulo, suite, funcao = ITENS[args.item]
    print(f"\n{'=' * 74}\n  VERIFICACAO DO ITEM {args.item} — {titulo}\n{'=' * 74}")

    rel = Relatorio()
    ok_testes = roda_testes(suite, args.verboso)
    print(f"\n--- conferencias sobre o material do trabalho ---")
    rel.afere(ok_testes, f"suite {suite}")
    funcao(rel, args.verboso)

    n_ok = sum(1 for ok, _, _ in rel.itens if ok)
    print(f"\n{'=' * 74}")
    if rel.aprovado:
        print(f"  {VERDE}APROVADO{FIM} — {n_ok} de {len(rel.itens)} conferencias passaram")
        print(f"{'=' * 74}\n")
        return 0
    print(f"  {VERMELHO}REPROVADO{FIM} — {n_ok} de {len(rel.itens)} conferencias passaram")
    for ok, t, _ in rel.itens:
        if not ok:
            print(f"    falhou: {t}")
    print(f"{'=' * 74}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
