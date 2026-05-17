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

| Variável | Tipo | Detecção |
|---|---|---|
| `tem_banner_cookies` | binária | seletor CSS + léxico |
| `tem_politica_privacidade` | binária | regex no DOM e em hrefs |
| `tem_canal_titular` | binária | regex DPO/encarregado |
| `cookies_set_count` | contagem | Playwright headless |
| `categoria_cookies` | categórica | regras + classificador supervisionado |
| `menciona_lgpd` | binária | TF-IDF + Regressão Logística |

Detalhamento em `config/protocol.yaml` e `docs/arquitetura.md`.

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
