# PrivacyScope — Arquitetura do Framework

**Versão:** 0.1 (draft, 17/05/2026)
**Autor:** Cristiano Gouveia Silverio
**Contexto:** Trabalho de Conclusão de Curso — MBA USP/ESALQ em Data Science e Analytics
**Orientador:** Prof. Me. Denis Bruno Viríssimo

---

## 1. Objetivo deste documento

Este documento descreve as decisões arquiteturais do framework **PrivacyScope**, ferramental computacional desenvolvido para apoiar a etapa de Monitoramento prevista no processo fiscalizatório da Autoridade Nacional de Proteção de Dados (ANPD), conforme a Resolução CD/ANPD nº 1/2021. O documento é parte integrante do TCC e será referenciado em seu Apêndice.

A arquitetura aqui descrita atende, simultaneamente, a três restrições:

1. **Auditabilidade integral.** Toda execução é rastreável até a evidência bruta que a originou.
2. **Reprodutibilidade científica.** Mesmo input + mesmo protocolo → mesmo output.
3. **Evolução desacoplada.** Novos critérios, fontes ou saídas são adicionados sem alteração do núcleo.

---

## 2. Princípios norteadores

| Princípio | Aplicação concreta no PrivacyScope |
|---|---|
| Inversão de dependência e Open/Closed (Martin, 2000) | Camadas conversam apenas por interfaces abstratas (`ABC`); adicionar plugin não exige alterar orquestrador |
| Separation of concerns | Coleta nunca interpreta; análise nunca recoleta |
| Imutabilidade da evidência | Raw Storage é append-only |
| Configuração externalizada (Sculley et al., 2015) | Protocolo declarativo YAML governa cada execução |
| Cadeia de custódia (ABNT NBR ISO/IEC 27037:2013; Casey, 2011) | Cada evidência empacotada em tar.gz com hash SHA-256 |
| Reprodutibilidade computacional (Wilson et al., 2017) | Versionamento de protocolo, dataset, código e ambiente |

---

## 3. Visão geral em camadas

A arquitetura é um pipeline de **seis camadas** + **três preocupações transversais** (Protocolo, Orquestrador, Auditoria). Ver Figura 1 (`docs/figuras/figura1_arquitetura.svg`).

```
[Protocolo YAML] -> [Orquestrador]
                        |
                        v
  [1 Ingestão] -> [2 Coleta] -> [3 Evidência Bruta] -> [4 Análise] -> [5 Resultados] -> [6 Saída]
```

Cada caixa do diagrama é uma interface; o que aparece dentro são **plugins** intercambiáveis registrados no protocolo.

---

## 4. Contratos das camadas (interfaces)

### 4.1. SampleSource (Ingestão)
```python
class SampleSource(ABC):
    name: str            # identificador no protocolo
    version: str         # versão do plugin

    @abstractmethod
    def list_domains(self, params: dict) -> Iterator[Domain]: ...
```
Implementações iniciais: `TrancoSource` (única ativa no protocolo v1.0.0) e `CsvSource` (auxiliar, para listas curadas). `GovBrSource` e outros plugins permanecem como exemplo de extensibilidade — o framework permite registrá-los sem alteração do orquestrador.

### 4.2. PageFetcher (Coleta)
```python
class PageFetcher(ABC):
    @abstractmethod
    async def fetch(self, domain: Domain, params: dict) -> RawEvidence: ...
```
Implementações iniciais: `HttpFetcher`, `PlaywrightFetcher`, `FallbackChain` (orquestra os anteriores com retry/backoff).

### 4.3. RawRepository (Persistência bruta — chain of custody)
```python
class RawRepository(ABC):
    @abstractmethod
    def put(self, ev: RawEvidence) -> EvidenceRef: ...
    @abstractmethod
    def get(self, ref: EvidenceRef) -> RawEvidence: ...
```
Implementação: `FileSystemRepository`. Para cada `RawEvidence` recebido:
1. Serializa em diretório temporário com layout fixo (`html.gz`, `cookies.json`, `headers.json`, `screenshot.png`, `meta.json`).
2. Empacota em `<domain>__<run_id>__<timestamp>.tar.gz`.
3. Calcula SHA-256 do tar.
4. Persiste o tar e registra `(domain, run_id, hash, path, ts)` no `manifest.json` global.
5. Retorna `EvidenceRef(path, hash)`.

A integridade pode ser verificada a qualquer momento recomputando o SHA-256 e comparando com o manifest — base da defesa probatória em banca.

### 4.4. VariableTest (Análise)
```python
class VariableTest(ABC):
    name: str
    version: str
    @abstractmethod
    def evaluate(self, ev: RawEvidence, params: dict) -> VariableResult: ...
```
Cada `VariableResult` carrega:
- `value`: valor da variável (bool, categoria, numérico)
- `confidence`: float ∈ [0,1]
- `audit_trail`: dict com (a) regra/seletor/modelo acionado, (b) snippet evidencial, (c) versão do plugin, (d) versão do protocolo, (e) timestamp

Implementações iniciais: `StructuralTest`, `LexiconTest`, `MLClassifierTest`, `CookieAnalyzer`.

### 4.5. ResultStore (Persistência estruturada)
```python
class ResultStore(ABC):
    @abstractmethod
    def upsert(self, r: VariableResult) -> None: ...
    @abstractmethod
    def query(self, filt: dict) -> Iterable[VariableResult]: ...
```
Implementação: `SQLiteStore` com schema *long-format*:
`(domain_id, variable_name, value, confidence, audit_trail_json, run_id, protocol_version, ts)`.

### 4.6. OutputRenderer (Saída)
```python
class OutputRenderer(ABC):
    @abstractmethod
    def render(self, store: ResultStore, params: dict) -> Path: ...
```
Implementações iniciais: `CsvExport`, `ParquetExport`, `MarkdownReport`, `DashboardJsonExport`.

---

## 5. Protocolo declarativo

Toda execução é governada por um `protocol.yaml` versionado. Exemplo (excerto):

```yaml
protocol_version: v1.0.0
sources:
  - name: tranco
    version: 2026-05-01
    params:
      tld_filter: ".br"
      # nota: a Tranco filtrada por .br já contém domínios .gov.br suficientes
      # para o estrato governamental; fonte única evita viés diferencial.

sampling:
  strategy: stratified_random
  seed: 20260517
  strata:
    governamental: { filter: { domain_pattern: ".gov.br" }, n: 25 }
    empresarial:   { filter: { domain_pattern_exclude: ".gov.br" }, n: 25 }

crawlers:
  - name: fallback_chain
    chain: [http_simples, playwright]
    timeout_s: 60
    retries: 2

tests:
  - name: banner_cookies
    type: structural+lexicon
    rules_file: "rules/banner_cookies.yaml"
  - name: politica_privacidade
    type: structural
    rules_file: "rules/politica.yaml"
  # ...

outputs:
  - parquet:    { path: "data/results/results.parquet" }
  - csv:        { path: "data/results/results.csv" }
  - markdown:   { path: "data/results/report.md" }
```

O hash SHA-256 do `protocol.yaml` é gravado no `audit_log.jsonl` no início de cada execução. Mudou um caractere do protocolo → o hash muda → a execução é uma nova `protocol_version`.

---

## 6. Cadeia de custódia da evidência

Cada site analisado gera um pacote tar.gz com a seguinte estrutura interna:

```
<domain>__<run_id>__<timestamp>/
├── html.gz                  # HTML completo da página de entrada
├── html_subpages/           # políticas, termos, encarregado, etc.
├── cookies.json             # cookies set durante a sessão (Playwright)
├── headers.json             # headers HTTP de cada requisição
├── screenshot.png           # captura full-page
├── network.har              # opcional, trace HAR
└── meta.json                # url, status, user-agent, timestamps, plugin_versions
```

Para cada tar:
- Calcula-se SHA-256 do arquivo.
- O par `(tar_filename, sha256, run_id, protocol_version_hash, ts)` é registrado em `manifest.jsonl`.
- O manifest é, ele próprio, assinado: SHA-256 do `manifest.jsonl` é gravado no `audit_log.jsonl`.

Resultado: qualquer adulteração posterior (do tar, do manifest ou do log) é detectável recomputando hashes em cascata. Padrão equivalente ao recomendado em ABNT NBR ISO/IEC 27037:2013 (*Tecnologia da informação — Técnicas de segurança — Diretrizes para identificação, coleta, aquisição e preservação de evidência digital*) para preservação de evidência digital.

---

## 7. Decisões deliberadas (e seus tradeoffs)

| Decisão | Alternativa rejeitada | Razão |
|---|---|---|
| `asyncio` simples como orquestrador | Airflow / Prefect | Overhead de operação fora de escala (N < 1.000) |
| SQLite como ResultStore | PostgreSQL | Reprodutibilidade: o arquivo `.sqlite` é parte do TCC |
| FileSystem + tar.gz como Raw | S3 / blob storage | Custo zero, totalmente local, auditável |
| Long-format no ResultStore | Wide-format | Variáveis adicionadas sem migração de schema |
| Protocolo em YAML | JSON / TOML | Legibilidade humana + suporte a comentários |
| `audit_log.jsonl` por linha | log textual livre | Parseável → tabela "execuções" no Apêndice |
| Sem Docker no MVP | Docker desde o início | Simplicidade no TCC; adiciona-se depois se virar produto |

---

## 8. Aderência aos objetivos específicos do projeto aprovado

| Objetivo específico | Camada / mecanismo responsável |
|---|---|
| Framework parametrizável | Protocolo YAML + plugin registry |
| Variáveis com regras formais e auditáveis | `VariableTest` + `audit_trail` em `VariableResult` |
| Webscraping/crawling estruturado | Camada 2 + FallbackChain |
| Análise textual/estrutural + ML quando pertinente | Camada 4 (testes independentes por tipo) |
| Consolidação tabular | `SQLiteStore` long-format |
| Consistência, reprodutibilidade, robustez | Camada 3 imutável + hashes + `protocol_version` |
| Aderência conceitual à Resolução CD/ANPD nº 1/2021 | Discutida no texto do TCC (não codificada) |
| Flexibilidade (novos critérios) | Plugin novo + uma linha no YAML |

---

## 9. Estrutura de repositório

```
PrivacyScope/
├── pyproject.toml
├── README.md
├── LICENSE                  # MIT (ver decisão pendente)
├── config/
│   ├── protocol.yaml
│   ├── thresholds.yaml
│   └── rules/
│       ├── banner_cookies.yaml
│       └── ...
├── src/privacyscope/
│   ├── core/                # ABCs + tipos (Domain, RawEvidence, VariableResult)
│   ├── sources/             # plugins de Ingestão
│   ├── fetchers/            # plugins de Coleta
│   ├── storage/             # raw repo + result store
│   ├── tests/               # plugins de Análise
│   ├── outputs/             # renderers
│   ├── orchestrator.py
│   └── cli.py
├── data/
│   ├── raw/                 # tar.gz por execução (gitignored)
│   ├── manifests/           # manifest.jsonl por run (versionado)
│   └── results/             # SQLite + Parquet (versionado para o TCC)
├── notebooks/               # análise exploratória / figuras
├── tests_unit/              # pytest
└── docs/
    ├── arquitetura.md       # este documento
    └── figuras/
        ├── figura1_arquitetura.svg
        └── figura1_arquitetura.png
```

---

## 10. Referências relevantes

- ASSOCIAÇÃO BRASILEIRA DE NORMAS TÉCNICAS. ABNT NBR ISO/IEC 27037:2013 — *Tecnologia da informação — Técnicas de segurança — Diretrizes para identificação, coleta, aquisição e preservação de evidência digital*. Rio de Janeiro, Brasil, 2013.
- CASEY, E. *Digital Evidence and Computer Crime: Forensic Science, Computers and the Internet*. 3ed. Academic Press, Waltham, MA, USA, 2011.
- LE POCHAT, V.; VAN GOETHEM, T.; TAJALIZADEHKHOOB, S.; KORCZYŃSKI, M.; JOOSEN, W. Tranco: A research-oriented top sites ranking hardened against manipulation. In: *Proceedings of the 26th Network and Distributed System Security Symposium (NDSS 2019)*. San Diego, CA, USA, 2019.
- MARTIN, R. C. *Design Principles and Design Patterns*. Object Mentor, 2000. Disponível em: https://wnmurphy.com/assets/pdf/Robert_C._Martin_-_2000_-_Principles_and_Patterns.pdf
- SCULLEY, D.; HOLT, G.; GOLOVIN, D.; DAVYDOV, E.; PHILLIPS, T.; EBNER, D.; CHAUDHARY, V.; YOUNG, M.; CRESPO, J.-F.; DENNISON, D. Hidden technical debt in machine learning systems. In: *Proceedings of the 28th International Conference on Neural Information Processing Systems (NeurIPS 2015)*. Montreal, Canada, p. 2503-2511, 2015.
- WILSON, G.; BRYAN, J.; CRANSTON, K.; KITZES, J.; NEDERBRAGT, L.; TEAL, T. K. Good enough practices in scientific computing. *PLOS Computational Biology* 13(6): e1005510, 2017.
