# PrivacyScope

> Framework computacional parametrizável para apoio à etapa de Monitoramento do processo fiscalizatório da Autoridade Nacional de Proteção de Dados (ANPD).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Status: research preview](https://img.shields.io/badge/status-research%20preview-orange.svg)]()

PrivacyScope é o artefato técnico desenvolvido como parte do Trabalho de Conclusão de Curso (TCC) do MBA USP/ESALQ em Data Science e Analytics. O framework opera em seis camadas desacopladas — Ingestão, Coleta, Evidência Bruta, Análise, Resultados Estruturados e Saída — governadas por um protocolo declarativo em YAML, com cadeia de custódia das evidências brutas via empacotamento e hash criptográfico (ABNT NBR ISO/IEC 27037:2013).

O objetivo é traduzir requisitos observáveis de transparência digital (presença de banner de cookies, política de privacidade, canal do titular, etc.) em variáveis técnicas mensuráveis, coletáveis automaticamente sobre websites institucionais brasileiros, com resultados auditáveis e reprodutíveis. O trabalho **não** realiza juízo jurídico de conformidade nem classifica infrações administrativas — limita-se à produção de evidências técnico-descritivas.

## Arquitetura

Ver [`docs/arquitetura.md`](docs/arquitetura.md) e Figura 1 (`docs/figuras/figura1_arquitetura.svg`).

```
[Protocolo YAML] → [Orquestrador]
                      |
                      v
[1 Ingestão] → [2 Coleta] → [3 Evidência Bruta] → [4 Análise] → [5 Resultados] → [6 Saída]
```

## Instalação

```bash
git clone https://github.com/cristianosilverio/privacyscope.git
cd privacyscope
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

## Uso (preview)

```bash
privacyscope run --config config/protocol.yaml
```

Cada execução gera:
- Pacotes de evidência bruta em `data/raw/` (`<dominio>__<run_id>__<ts>.tar.gz` + SHA-256 no manifest)
- Resultados estruturados em `data/results/results.sqlite` e `data/results/results.parquet`
- Relatório em Markdown em `data/results/report.md`
- Log de auditoria em `data/results/audit_log.jsonl`

## Variáveis técnicas (v1.0.0)

| Variável | Detecção | Depende de |
|---|---|---|
| `tem_banner_cookies` | regra: seletor CSS + léxico | — |
| `tem_politica_privacidade` | regra: padrões no DOM e em hrefs | — |
| `tem_canal_titular` | regressão logística penalizada sobre oito atributos estruturais | — |
| `finalidade_especificada` | TF-IDF + regressão logística, no nível da sentença | `tem_politica_privacidade` |
| `direitos_titular_explicados` | TF-IDF + regressão logística, no nível da sentença | `tem_politica_privacidade` |
| `transf_internacional_divulgada` | TF-IDF + regressão logística, no nível da sentença | `tem_politica_privacidade` |

O canal do titular tem também um detector por regra (`canal_titular`), mantido como linha de base. Registrados e não habilitados por padrão, três classificadores por representação densa servem de **teto comparativo**: custam horas por execução e exigem pesos que não acompanham o repositório.

`cookies_set` e `categoria_cookies` foram movidas para trabalho futuro. `menciona_lgpd` não integra a bateria.

Detalhamento em `protocols/padrao.yaml` e `docs/arquitetura.md`.

## Estados de uma medição

O resultado de uma variável **não é booleano**. Reduzi-lo a verdadeiro/falso enviesa o indicador exatamente na direção que a etapa de Monitoramento quer medir. São quatro estados:

| estado | significa | fala sobre |
|---|---|---|
| `true` | o sinal foi medido e está presente | o sítio |
| `false` | o sinal foi medido e está ausente | o sítio |
| `nao_aplicavel` | a precondição declarada não se verificou | o sítio |
| `nao_coletado` | o instrumento não obteve o objeto da medição | o instrumento |

**`nao_aplicavel`** decorre da dependência declarada no protocolo. Finalidade, direitos do titular e transferência internacional são declarações *dentro* da política de privacidade; aplicá-las a um sítio sem política submeteria a um classificador de políticas um material que não é política. O resultado disso não é ausência de divulgação — é medição indevida. Sobre 506 sítios, 46% não tinham política detectada, e neles a variável de finalidade ainda saía positiva em 21,8% dos casos.

**`nao_coletado`** cobre a unidade que falhou na coleta e a página que o servidor de origem recusou entregar. Antes de existir, o domínio que falhava simplesmente sumia das saídas — saía do numerador e do denominador ao mesmo tempo, e qualquer proporção passava a medir prevalência entre os alcançados, e não entre os amostrados. Taxa de alcance é parte do resultado.

Os dois estados são distintos de propósito: fundi-los faria um sítio nunca alcançado aparecer como sítio sem política.

Na saída de triagem, a ordenação por não conformidade é lexicográfica e ancorada no grafo de dependências, e não na soma de sinais ausentes — somar `false` faria o sítio *sem* política ficar abaixo do sítio *com* política que falha nas textuais, porque a dependência tira três variáveis da contagem do primeiro. Nenhum peso por gravidade é arbitrado.

## Cadeia de custódia

Cada conjunto de evidências (HTML, cookies, headers, screenshot, metadados) é empacotado em `tar.gz`, recebe hash SHA-256, e é registrado em `manifest.jsonl` assinado. O hash do manifest é gravado em `audit_log.jsonl`. Qualquer adulteração é detectável pela recomputação em cascata. Referência: ABNT NBR ISO/IEC 27037:2013; Casey (2011).

## Reprodutibilidade

Toda execução é governada por `config/protocol.yaml`, versionado e identificado por hash SHA-256 (`protocol_version`). Mesmo input + mesmo protocolo → mesmo output. A camada de Evidência Bruta é imutável (append-only) — múltiplas análises podem ser aplicadas sobre o mesmo conjunto preservado.

## Limitações

O framework analisa apenas evidências observáveis em ambientes digitais públicos. **Não** infere práticas internas de tratamento, **não** classifica infrações, **não** estima sanções, **não** prioriza ações fiscalizatórias. Indicadores produzidos têm natureza técnico-descritiva e não constituem avaliação jurídica de conformidade.

## Estrutura do repositório

```
privacyscope/
├── config/
│   ├── protocol.yaml
│   ├── thresholds.yaml
│   └── rules/
├── src/privacyscope/
│   ├── core/            # ABCs + tipos (Domain, RawEvidence, VariableResult)
│   ├── sources/         # TrancoSource, GovBrSource, CsvSource
│   ├── fetchers/        # HttpFetcher, PlaywrightFetcher, FallbackChain
│   ├── storage/         # FileSystemRepository, SQLiteStore
│   ├── tests/           # StructuralTest, LexiconTest, MLClassifierTest, CookieAnalyzer
│   ├── outputs/         # CsvExport, ParquetExport, MarkdownReport, DashboardJsonExport
│   ├── orchestrator.py
│   └── cli.py
├── data/                # gitignored (dados de execução)
├── docs/                # arquitetura, figuras
├── notebooks/           # análise exploratória, figuras do TCC
└── tests_unit/          # pytest
```

## Citação

Se você usar este framework em pesquisa, por favor cite:

> SILVERIO, C. G. *Apoio à Etapa de Monitoramento no Processo Fiscalizatório da ANPD: abordagem baseada em webscraping e machine learning*. Trabalho de Conclusão de Curso — MBA em Data Science e Analytics, USP/Esalq, Piracicaba, SP, Brasil, 2026.

## Licença

MIT — ver [LICENSE](LICENSE).

## Autor

Cristiano Gouveia Silverio · CEO LGPD2U · cristiano.silverio@lgpd2u.com.br
Orientador: Prof. Me. Denis Bruno Viríssimo · IPT/USP · denisbv@ipt.br
