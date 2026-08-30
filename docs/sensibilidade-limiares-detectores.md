# Análise de sensibilidade dos limiares — detectores PrivacyScope (piloto B4, n=49)

**Data:** 2026-05-24
**Objetivo:** verificar se as métricas dependem dos valores específicos escolhidos para os limiares numéricos dos três detectores determinísticos, isto é, se os parâmetros são *load-bearing*. Cada limiar foi variado numa faixa e o `evaluate` **real** de cada teste foi reexecutado sobre os 49 sites (constantes do módulo alteradas em tempo de execução), recalculando-se precisão, recall, F1 e kappa contra o gabarito manual (canal com gabarito corrigido pelo critério do Encarregado).

**Conclusão geral:** nenhum dos limiares numéricos é load-bearing nesta amostra — as métricas permanecem estáveis em faixas largas em torno dos valores adotados. Isso responde, com evidência, à pergunta "por que esse valor e não outro": dentro de uma faixa ampla o resultado é idêntico, logo a escolha específica não é consequente. **Ressalva:** a estabilidade foi medida em B4 (desenvolvimento); os platôs devem ser reconfirmados na amostra held-out (B8).

## 1. Política — `MIN_POLICY_SIZE_BYTES` × `MIN_KEYWORDS_FOR_HIGH`

Baseline adotado: bytes=500, kw_high=3. Resultado em **todas** as 15 combinações testadas:

| bytes \ kw_high | 2 | 3 | 4 |
|---|---|---|---|
| 200 | P0,966 R0,966 F0,966 K0,913 | idem | idem |
| 300 | idem | idem | idem |
| 500 | idem | **idem (baseline)** | idem |
| 800 | idem | idem | idem |
| 1200 | idem | idem | idem |

FP=1, FN=1 em todas. **Totalmente insensível** — após o refinamento v0.2.0, a decisão é dominada por `content_qualified` (páginas de política reais têm muitas keywords, muito acima de qualquer limiar) e por `content_light`+path-de-política (que independe do limiar exato de keywords).

## 2. Canal do titular — `min_subpage_bytes`

Baseline adotado: 500. Resultado para {100, 500, 2000, 10000}:

| min_bytes | FP | FN | Precisão | Recall | F1 | Kappa |
|---|--:|--:|--:|--:|--:|--:|
| 100 | 0 | 1 | 1,000 | 0,909 | 0,952 | 0,939 |
| 500 | 0 | 1 | 1,000 | 0,909 | 0,952 | 0,939 |
| 2000 | 0 | 1 | 1,000 | 0,909 | 0,952 | 0,939 |
| 10000 | 0 | 1 | 1,000 | 0,909 | 0,952 | 0,939 |

**Invariante.** Na piloto B4 a decisão do canal vem inteiramente do sinal de e-mail do Encarregado; o ramo de qualificação de subpágina (onde o limiar atua) não dispara em nenhum site. O limiar é, portanto, inerte nesta amostra.

## 3. Banner de cookies — `_MAX_ANCESTOR_DEPTH` (filtro de visibilidade)

Baseline adotado: 6. Resultado para {1, 2, 4, 6, 8, 12}:

| depth | FP | FN | Precisão | Recall | F1 | Kappa |
|---|--:|--:|--:|--:|--:|--:|
| 1 | 1 | 2 | 0,952 | 0,909 | 0,930 | 0,874 |
| 2 | 1 | 2 | 0,952 | 0,909 | 0,930 | 0,874 |
| 4 | 0 | 2 | 1,000 | 0,909 | 0,952 | 0,915 |
| 6 | 0 | 2 | 1,000 | 0,909 | 0,952 | 0,915 (baseline) |
| 8 | 0 | 2 | 1,000 | 0,909 | 0,952 | 0,915 |
| 12 | 0 | 2 | 1,000 | 0,909 | 0,952 | 0,915 |

**Estável para profundidade ≥ 4.** Há uma única transição: com profundidade ≤ 2 surge 1 falso positivo a mais — um banner cujo marcador de ocultação está num ancestral 3–4 níveis acima do elemento. O valor adotado (6) está dentro do platô estável, com margem de 2 níveis. Acima de 4 o resultado é idêntico até 12.

## Implicação metodológica

Os valores específicos dos limiares não conduzem as métricas em B4 — eles caem em platôs largos. Isso mitiga (mas não elimina) o viés de parametrização: a parte não atacada por esta análise é o conteúdo das **listas/vocabulários** derivados da própria amostra (vocabulário de container do banner, vocabulário de path da política, blocklist do canal), cuja validade depende da validação em dados held-out (B8) e, no que for aprendível, da supersessão por classificador supervisionado (B9).
