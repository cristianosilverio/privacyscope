# -*- coding: utf-8 -*-
"""Linhas de base das tres variaveis textuais, em nivel de sentenca.

PROPOSITO
---------
Fixa o piso contra o qual o classificador supervisionado sera confrontado. Nenhuma
afirmacao de desempenho tem sentido sem ele: sob desequilibrio de 1 para 119, a regra
que responde sempre "nao" atinge 99,2% de acuracia.

Tres linhas de base:

  CLASSE MAJORITARIA — responde sempre negativo. Demonstra por que a acuracia nao
  pode figurar como metrica de manchete.

  COMPRIMENTO DA CADEIA — decide pelo numero de caracteres do segmento, com o limiar
  apurado nas particoes de treino. Mediu-se que o comprimento sozinho alcanca 57,4%
  de acuracia balanceada no conjunto completo, resquicio da diferenca entre passagem
  de prosa e fragmento de navegacao. Reporta-la e imprescindivel: sem ela, parte do
  desempenho do modelo fica sem atribuicao.

  REGRA — operacionaliza os criterios do codebook por casamento de padroes. Para
  direitos do titular corresponde ao contador dos incisos I a IX do artigo 18, cuja
  avaliacao como linha de base forte o proprio trabalho registra como recomendacao,
  ante a suspeita de que torne o classificador supervisionado parcialmente redundante.

As regras sao DECLARADAS a partir do codebook e nao ajustadas sobre os dados. Ajusta-
las contra o resultado converteria a linha de base em modelo rival mal documentado.

ESQUEMA DE AVALIACAO
--------------------
Particao agrupada por sitio, deixando um documento de fora: quinze ajustes, cada um
sobre catorze politicas. O agrupamento evita que segmentos da mesma politica figurem
em treino e teste, o que permitiria ao modelo reconhecer o fraseado do documento em
lugar de julgar a sentenca.

As metricas sao apuradas UMA VEZ sobre as predicoes reunidas de todas as particoes, e
nao como media entre elas: cinco das quinze politicas nao contem positivo algum de
transferencia internacional, e nessas a revocacao seria indefinida.

A incerteza provem de reamostragem sobre os quinze DOCUMENTOS, e nao sobre os
segmentos. A pergunta que se responde e se o desempenho se transfere a outras
politicas, e essa e variabilidade de documento; reamostrar segmentos trataria como
independentes unidades que compartilham autoria e redacao.

DOIS REGIMES DE METRICA
-----------------------
Reportam-se ambos, para que a escolha se faca com os numeros a vista.

O regime declarado no trabalho — acuracia balanceada, macro-F1 e coeficiente de
Matthews — foi fixado tendo em conta o canal do titular, cujas classes se dividem de
forma quase equilibrada.

O regime alternativo — precisao, revocacao e F1 da CLASSE POSITIVA, coeficiente de
Matthews e precisao media — e o usual sob desequilibrio acentuado. A macro-F1, sob 1
para 119, e dominada pela classe negativa, cujo F1 se aproxima da unidade ainda que
nenhum positivo seja recuperado.

Uso:
    python scripts/linhas_base_textuais.py
"""
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from math import sqrt
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
VARIAVEIS = ["finalidade", "direitos_titular", "transf_internacional"]
ROTULO = {"finalidade": "Finalidade", "direitos_titular": "Direitos",
          "transf_internacional": "Transf. intern."}


def normaliza(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).lower().strip()


# --------------------------------------------------------------- regras
# Operacionalizacao dos criterios do codebook. Declaradas uma vez, nao ajustadas.

# Finalidade: conectivo de proposito seguido de atividade concreta (criterio F1),
# excluidas as formulas genericas que o codebook relaciona como negativas.
_FIN_CONECTIVO = (r"(?:\bpara\b|\ba fim de\b|\bcom (?:o objetivo|a finalidade|o proposito|"
                  r"o intuito) de\b|\bvisando\b|\bdestinad[oa]s? a\b|\bfinalidades?\b)")
_FIN_ATIVIDADE = (r"(?:process\w+|entreg\w+|envi\w+|cadastr\w+|identific\w+|autentic\w+|"
                  r"personaliz\w+|recomend\w+|analis\w+|estatistic\w+|marketing|publicidad\w+|"
                  r"anunci\w+|cobran\w+|fatur\w+|pagament\w+|prevenc\w+|fraude|contat\w+|"
                  r"comunica\w+|atendiment\w+|suport\w+|newsletter|promoc\w+|ofert\w+|"
                  r"lembr\w+|reconhec\w+|login|navegac\w+|metric\w+|pesquis\w+|contrat\w+|"
                  r"pedido|compra|vend\w+|selec\w+|recrut\w+|vaga|curriculo|agendament\w+|"
                  r"exame|consulta|obrigac\w+|cumprir?|seguran\w+|auditor\w+)")
FIN_GENERICO = re.compile(r"melhorar (?:sua|a) experiencia|otimizar? (?:sua|a) experiencia|"
                          r"melhorar (?:os )?(?:nossos )?servicos|fins previstos nesta|"
                          r"finalidades legitimas|conforme a legislacao|melhor experiencia")
REGRA_FIN = re.compile(_FIN_CONECTIVO + r"[^.;]{0,70}" + _FIN_ATIVIDADE)

# Direitos: as nove substancias do artigo 18, mais revisao de decisao automatizada
# (artigo 20) e peticao a autoridade, que o codebook alcanca pelo construto do binario.
REGRA_DIR = re.compile(
    r"confirma\w*[^.;]{0,40}(?:existencia|tratament)"                      # I
    r"|(?:acess\w+|obter (?:copia|uma copia))[^.;]{0,30}(?:dados|informac)"  # II
    r"|(?:corrig\w+|retific\w+|atualiz\w+)[^.;]{0,40}(?:dados|incomplet|inexat|desatualiz)"  # III
    r"|(?:anonimiz\w+|bloque\w+)[^.;]{0,40}(?:dados|desnecessari|excessiv)"  # IV
    r"|portabilidade|transferir[^.;]{0,40}(?:outro fornecedor|outro servico)"  # V
    r"|(?:elimin\w+|exclu\w+|apagar)[^.;]{0,50}(?:dados|consentiment)"      # VI
    r"|(?:saber|informac\w+|conhecer)[^.;]{0,50}(?:com quem|entidades|compartilha)"  # VII
    r"|nao (?:fornecer|consentir)[^.;]{0,40}consequencia"                   # VIII
    r"|revoga\w+[^.;]{0,30}consentiment|retirar[^.;]{0,30}consentiment"     # IX
    r"|revis\w+[^.;]{0,40}decis[^.;]{0,40}automatizad|peticion\w+")         # art. 20 e peticao

# Transferencia: elemento transfronteirico explicito (criterio T1), excluidos o texto
# definitorio da lei e a negacao expressa (criterio T5).
_TR_FRONTEIRA = (r"(?:fora do (?:brasil|pais)|no exterior|em outros paises|"
                 r"nos estados unidos|\beua\b|internacionalmente|transfronteir\w+)")
_TR_VERBO = (r"(?:transferi\w+|transmit\w+|armazen\w+|process\w+|hospedad?\w*|mantid\w+|"
             r"compartilhad?\w*|enviad\w+|localizad\w+|servidor\w*|tratad\w+|acess\w+)")
TR_DEFINICAO = re.compile(r"uso compartilhado de dados\s*:|comunicacao, difusao, transferencia")
TR_NEGACAO = re.compile(r"nao (?:ha|ocorre|realiza\w*|efetua\w*|existe|havera|havendo)"
                        r"[^.;]{0,60}transfer")
REGRA_TR = re.compile(_TR_VERBO + r"[^.;]{0,80}" + _TR_FRONTEIRA
                      + r"|" + _TR_FRONTEIRA + r"[^.;]{0,60}" + _TR_VERBO
                      + r"|transferencia internacional")


def aplica_regra(texto, variavel):
    x = normaliza(texto)
    if variavel == "finalidade":
        return int(bool(REGRA_FIN.search(x)) and not FIN_GENERICO.search(x))
    if variavel == "direitos_titular":
        return int(bool(REGRA_DIR.search(x)))
    if variavel == "transf_internacional":
        if TR_DEFINICAO.search(x) or TR_NEGACAO.search(x):
            return 0
        return int(bool(REGRA_TR.search(x)))
    return 0


# -------------------------------------------------------------- metricas
def matriz(y, p):
    y, p = np.asarray(y), np.asarray(p)
    return (int(np.sum((y == 1) & (p == 1))), int(np.sum((y == 0) & (p == 1))),
            int(np.sum((y == 1) & (p == 0))), int(np.sum((y == 0) & (p == 0))))


def metricas(y, p):
    vp, fp, fn, vn = matriz(y, p)
    sens = vp / (vp + fn) if vp + fn else 0.0
    esp = vn / (vn + fp) if vn + fp else 0.0
    prec = vp / (vp + fp) if vp + fp else 0.0
    f1p = 2 * prec * sens / (prec + sens) if prec + sens else 0.0
    p0 = vn / (vn + fn) if vn + fn else 0.0
    f1n = 2 * p0 * esp / (p0 + esp) if p0 + esp else 0.0
    den = sqrt((vp + fp) * (vp + fn) * (vn + fp) * (vn + fn))
    return {"bal": (sens + esp) / 2, "macro_f1": (f1p + f1n) / 2,
            "mcc": (vp * vn - fp * fn) / den if den else 0.0,
            "prec": prec, "rev": sens, "f1_pos": f1p,
            "vp": vp, "fp": fp, "fn": fn, "vn": vn}


def precisao_media(y, escore):
    """Area sob a curva de precisao-revocacao, por interpolacao de retangulos."""
    o = np.argsort(-np.asarray(escore, dtype=float))
    y = np.asarray(y)[o]
    tp = np.cumsum(y)
    prec = tp / np.arange(1, len(y) + 1)
    total = y.sum()
    if not total:
        return float("nan")
    return float(np.sum(prec * y) / total)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpo", default="outputs/segmentos_rotulados.csv")
    ap.add_argument("--reamostras", type=int, default=2000)
    ap.add_argument("--semente", type=int, default=20260811)
    ap.add_argument("--out", default="outputs/linhas_base_textuais.csv")
    args = ap.parse_args()

    with (REPO / args.corpo).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    sitios = sorted({r["site_id"] for r in R})
    idx_sitio = {s: i for i, s in enumerate(sitios)}
    grupo = np.array([idx_sitio[r["site_id"]] for r in R])
    comp = np.array([int(r["n_caracteres"]) for r in R], dtype=float)

    print(f"corpo: {len(R):,} segmentos, {len(sitios)} politicas")
    print(f"esquema: deixar um documento de fora ({len(sitios)} particoes), "
          f"predicoes reunidas")
    print(f"incerteza: {args.reamostras} reamostras sobre os {len(sitios)} documentos\n")

    rng = np.random.default_rng(args.semente)
    linhas = []
    for v in VARIAVEIS:
        y = np.array([int(r[v]) for r in R])
        regra = np.array([aplica_regra(r["texto"], v) for r in R])

        # comprimento: limiar apurado nas particoes de treino
        pred_comp = np.zeros(len(R), dtype=int)
        for g in range(len(sitios)):
            tr, te = grupo != g, grupo == g
            melhor, corte = -1, 0
            for c in np.percentile(comp[tr], np.arange(50, 100, 2)):
                m = metricas(y[tr], (comp[tr] >= c).astype(int))
                if m["mcc"] > melhor:
                    melhor, corte = m["mcc"], c
            pred_comp[te] = (comp[te] >= corte).astype(int)

        casos = [("classe majoritaria", np.zeros(len(R), dtype=int), None),
                 ("comprimento da cadeia", pred_comp, comp),
                 ("regra do codebook", regra, None)]

        print("=" * 100)
        print(f"{ROTULO[v]}   positivos: {int(y.sum())}   negativos: {int((1 - y).sum())}"
              f"   proporcao 1 : {int((1 - y).sum() / max(y.sum(), 1))}")
        print("=" * 100)
        print(f"  {'linha de base':24}{'--- regime declarado ---':>30}"
              f"{'--- regime alternativo ---':>38}")
        print(f"  {'':24}{'bal.acc':>10}{'macroF1':>10}{'MCC':>10}"
              f"{'prec':>9}{'rev':>8}{'F1+':>8}{'AP':>8}{'VP':>6}{'FP':>7}")
        for nome, pred, escore in casos:
            m = metricas(y, pred)
            ap_ = precisao_media(y, escore) if escore is not None else float("nan")
            # a precisao media exige escore continuo; regra binaria nao o produz
            ap_txt = f"{ap_*100:6.1f}%" if ap_ == ap_ else "     —"
            print(f"  {nome:24}{m['bal']*100:9.1f}%{m['macro_f1']*100:9.1f}%{m['mcc']:10.3f}"
                  f"{m['prec']*100:8.1f}%{m['rev']*100:7.1f}%{m['f1_pos']*100:7.1f}%"
                  f"{ap_txt:>8}{m['vp']:6}{m['fp']:7}")
            # incerteza por reamostragem de documentos
            vals = []
            for _ in range(args.reamostras):
                g = rng.integers(0, len(sitios), len(sitios))
                sel = np.concatenate([np.where(grupo == k)[0] for k in g])
                vals.append(metricas(y[sel], pred[sel])["mcc"])
            lo, hi = np.percentile(vals, [2.5, 97.5])
            print(f"  {'':24}{'MCC, IC 95% por reamostragem de documentos:':>52} "
                  f"[{lo:.3f}, {hi:.3f}]")
            linhas.append({"variavel": v, "linha_base": nome, **m,
                           "ap": ap_, "mcc_ic_inf": lo, "mcc_ic_sup": hi})
        print()

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader(); w.writerows(linhas)
    print(f"saida: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
