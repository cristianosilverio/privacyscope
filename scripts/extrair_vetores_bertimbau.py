# -*- coding: utf-8 -*-
"""Extracao dos vetores do BERTimbau com o codificador congelado.

POR QUE O CODIFICADOR CONGELADO VEM ANTES DO AJUSTE FINO
--------------------------------------------------------
A pergunta que motiva o modelo neural nao e "o ajuste fino supera a representacao
esparsa", e sim, antes disso, "a representacao pre-treinada carrega sinal que a
representacao esparsa nao carrega". As duas perguntas se confundem quando so o ajuste
fino e executado: um resultado negativo ali fica ambiguo entre ausencia de sinal na
representacao e instabilidade do procedimento de ajuste, que nesta escala de dados e
conhecida (Dodge et al., 2020; Mosbach et al., 2021).

O codificador congelado responde a primeira pergunta com uma unica passagem adiante,
sem gradiente, em minutos e sem hiperparametro de otimizacao. Ele estabelece um piso:
se a representacao densa, sob o MESMO estimador e o MESMO esquema de avaliacao,
sequer alcanca a esparsa, o ajuste fino passa a ser aposta com custo declarado, e nao
etapa obrigatoria.

O desenho isola deliberadamente UMA variavel. Estimador, particao, procedimento de
limiar e metrica sao identicos aos da representacao esparsa. A unica coisa que muda e
a representacao. Diferenca observada e, portanto, atribuivel a ela.

MODELO
------
BERTimbau base, `neuralmind/bert-base-portuguese-cased` (Souza et al., 2020),
pre-treinado em portugues do Brasil. A escolha por modelo pre-treinado no idioma, e
nao por modelo multilingue, decorre do material: politica de privacidade brasileira
emprega vocabulario juridico que a fragmentacao em subpalavras de um vocabulario
multilingue reparte de modo mais agressivo.

O modelo preserva a caixa. Aqui NAO se minusculiza, ao contrario do que se faz na
representacao esparsa: la a minusculizacao reduz esparsidade do vocabulario, o que
importa com o numero de positivos disponivel; aqui o vocabulario e fixo e pre-treinado,
e minusculizar apenas afastaria o texto da distribuicao em que o modelo foi ajustado.

AGREGACAO DAS POSICOES
----------------------
Gravam-se DUAS agregacoes, obtidas na mesma passagem e portanto sem custo adicional:

  MEDIA das posicoes da ultima camada oculta, ponderada pela mascara de atencao, de
  modo que o preenchimento nao entre na conta. E a agregacao PRIMARIA.

  POSICAO [CLS], gravada como verificacao de robustez, e NAO elegivel pela regra de
  selecao. Sem ajuste fino, essa posicao nao foi otimizada para representar a sentenca
  na tarefa em questao, e reporta-la como alternativa a escolher converteria a
  robustez em mais uma comparacao sobre o mesmo material.

COMPRIMENTO
-----------
Teto de 256 subpalavras, com preenchimento dinamico por lote. Como a extensao mediana
do segmento e de 102 caracteres, o custo efetivo e ditado pelo maior item de cada
lote, e nao pelo teto; elevar o teto de 128 para 256 e portanto quase gratuito. A
escolha se justifica pelo que trunca: sob 128 subpalavras, nove segmentos positivos de
finalidade perdem o final; sob 256, nenhum positivo e truncado em nenhuma das tres
variaveis. Truncar um positivo e falso negativo autoinfligido, e nao limitacao do
modelo.

DETERMINISMO
------------
O modelo opera em modo de avaliacao, sem abandono de unidades e sem gradiente. Nao ha
sorteio: a reexecucao reproduz os vetores, a menos de aritmetica de ponto flutuante do
dispositivo.

Instalacao das dependencias:
    pip install -e ".[ml-advanced]"

Uso:
    python scripts/extrair_vetores_bertimbau.py
    python scripts/extrair_vetores_bertimbau.py --dispositivo cuda --lote 64
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
MODELO = "neuralmind/bert-base-portuguese-cased"
VARIAVEIS = ["finalidade", "direitos_titular", "transf_internacional"]


def dispositivo_efetivo(pedido):
    import torch
    if pedido != "auto":
        return pedido
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def relata_truncamento(registros, comprimentos, teto):
    """Quantos segmentos perdem o final, e quantos deles sao positivos.

    A contagem de positivos truncados e o que decide o teto: perder o final de um
    segmento negativo custa pouco, perder o de um positivo cria erro que nenhum
    estimador adiante consegue corrigir.
    """
    corte = comprimentos > teto
    print(f"  subpalavras por segmento: mediana {np.median(comprimentos):.0f}, "
          f"p95 {np.percentile(comprimentos, 95):.0f}, maximo {comprimentos.max():.0f}")
    print(f"  truncados sob teto {teto}: {int(corte.sum())} de {len(comprimentos)} "
          f"({100 * corte.mean():.2f}%)")
    for v in VARIAVEIS:
        y = np.array([int(r[v]) for r in registros])
        n = int((corte & (y == 1)).sum())
        marca = "  <-- REVER O TETO" if n else ""
        print(f"    positivos truncados em {v:22}: {n}{marca}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpo", default="outputs/segmentos_rotulados.csv")
    ap.add_argument("--saida", default="outputs/vetores_bertimbau.npz")
    ap.add_argument("--modelo", default=MODELO)
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--lote", type=int, default=32)
    ap.add_argument("--dispositivo", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    args = ap.parse_args()

    import torch
    from transformers import AutoModel, AutoTokenizer

    with (REPO / args.corpo).open(encoding="utf-8", newline="") as fh:
        R = list(csv.DictReader(fh, delimiter=";"))
    textos = [r["texto"] for r in R]
    print(f"corpo: {len(R):,} segmentos, "
          f"{len({r['site_id'] for r in R})} politicas")

    dev = dispositivo_efetivo(args.dispositivo)
    print(f"modelo: {args.modelo}   dispositivo: {dev}   teto: {args.max_len} subpalavras")

    tok = AutoTokenizer.from_pretrained(args.modelo)
    modelo = AutoModel.from_pretrained(args.modelo).to(dev)
    modelo.eval()

    comprimentos = np.array([len(tok(t, add_special_tokens=True)["input_ids"])
                             for t in textos])
    relata_truncamento(R, comprimentos, args.max_len)

    media = np.zeros((len(R), modelo.config.hidden_size), dtype=np.float32)
    cls = np.zeros_like(media)
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, len(textos), args.lote):
            lote = textos[i:i + args.lote]
            ent = tok(lote, padding=True, truncation=True, max_length=args.max_len,
                      return_tensors="pt").to(dev)
            h = modelo(**ent).last_hidden_state
            # A mascara zera as posicoes de preenchimento antes da soma: sem isso, a
            # media do segmento curto seria diluida pelo enchimento do lote, e o vetor
            # passaria a depender de com quem o segmento foi sorteado para o lote.
            m = ent["attention_mask"].unsqueeze(-1).to(h.dtype)
            media[i:i + len(lote)] = ((h * m).sum(1) / m.sum(1)).cpu().numpy()
            cls[i:i + len(lote)] = h[:, 0, :].cpu().numpy()
            if (i // args.lote) % 20 == 0:
                print(f"    {i + len(lote):>6,} de {len(textos):,}", end="\r")
    print(f"  passagem concluida em {time.time() - t0:.0f} s" + " " * 20)

    saida = REPO / args.saida
    saida.parent.mkdir(parents=True, exist_ok=True)
    # O indice viaja junto com os vetores. A ordem das linhas e o unico vinculo entre
    # o vetor e o rotulo, e um arquivo de vetores sem indice e indistinguivel de um
    # arquivo desalinhado. O consumidor confere o indice contra o corpo antes de usar.
    np.savez_compressed(
        saida, media=media, cls=cls,
        site_id=np.array([r["site_id"] for r in R]),
        segmento_id=np.array([r["segmento_id"] for r in R]),
        modelo=np.array(args.modelo), max_len=np.array(args.max_len))
    print(f"saida: {saida}   {media.shape[0]:,} x {media.shape[1]} "
          f"({saida.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
