"""
Interfaces (Abstract Base Classes) das seis camadas do PrivacyScope.

Cada plugin do framework herda de uma destas ABCs e implementa os métodos
abstratos. O orquestrador conversa apenas com estas interfaces — nunca com
classes concretas. Isso materializa, em código, o princípio Open/Closed
descrito por Martin (2000) e citado em docs/arquitetura.md.

Adicionar uma nova fonte amostral, um novo fetcher, um novo teste ou um
novo formato de saída resume-se a:
    1. herdar da ABC correspondente;
    2. implementar os métodos abstratos;
    3. registrar o plugin (via decorator em core/registry.py ou via
       entry_point em pyproject.toml).
Nenhum outro código do framework precisa mudar.

Mapeamento camada → ABC:
    1) Ingestão            -> SampleSource
    2) Coleta              -> PageFetcher
    3) Evidência Bruta     -> RawRepository
    4) Análise             -> VariableTest
    5) Resultados          -> ResultStore
    6) Saída               -> OutputRenderer

Referências:
    - Martin, R. C. (2000). Design Principles and Design Patterns.
    - Open/Closed Principle, Single Responsibility, Dependency Inversion (SOLID).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Iterable, Iterator

from privacyscope.core.types import (
    Domain,
    EvidenceRef,
    RawEvidence,
    VariableResult,
)


# =============================================================================
# 1) SampleSource - camada de Ingestão
# =============================================================================
class SampleSource(ABC):
    """Fonte de amostra: produz uma sequência de Domain.

    Implementações iniciais previstas: TrancoSource, CsvSource. Outras (e.g.,
    GovBrSource, CommonCrawlSource, WhoisSource) podem ser adicionadas sem
    alteração do orquestrador.

    Atributos de classe (obrigatórios em cada subclasse):
        name: Identificador único do plugin no protocolo YAML.
        version: Versão do plugin; aparece no audit_trail dos resultados.

    Método abstrato:
        list_domains: gera Domains de forma lazy (Iterator), evitando
            carregar listagens grandes (e.g., Tranco com 1M de entradas) na
            memória. O sampler do orquestrador consome esse Iterator com
            reservoir sampling ou outras estratégias.
    """

    name: ClassVar[str]
    version: ClassVar[str]

    @abstractmethod
    def list_domains(self, params: dict[str, Any]) -> Iterator[Domain]:
        """Itera sobre Domains produzidos por esta fonte.

        Args:
            params: parâmetros vindos do protocolo (e.g., {"tld_filter": ".br"}).

        Yields:
            Domain: cada domínio elegível, na ordem natural da fonte.
        """
        raise NotImplementedError


# =============================================================================
# 2) PageFetcher - camada de Coleta
# =============================================================================
class PageFetcher(ABC):
    """Coletor de evidência bruta a partir de um Domain.

    Implementações iniciais: HttpFetcher (rápido, sem JS), PlaywrightFetcher
    (lento, com renderização JS), FallbackChain (combina os anteriores com
    retry/backoff).

    Atributos de classe:
        name: Identificador único do plugin.
        version: Versão do plugin.

    Método abstrato:
        fetch: assíncrono (async/await). Coletas são I/O-bound; paralelismo
            via asyncio.gather no orquestrador dá ganho típico de 5-10x
            sobre execução serial.
    """

    name: ClassVar[str]
    version: ClassVar[str]

    @abstractmethod
    async def fetch(self, domain: Domain, params: dict[str, Any]) -> RawEvidence:
        """Coleta evidência bruta de um Domain.

        Args:
            domain: alvo da coleta.
            params: parâmetros vindos do protocolo (timeout, retries, headers).

        Returns:
            RawEvidence: pacote bruto (HTML, cookies, headers, screenshot,
            metadados, erros não-fatais).

        Raises:
            Exceções fatais (falha total de coleta) devem ser propagadas —
            elas indicam que o Domain não pôde ser analisado. Erros
            recuperáveis ficam em RawEvidence.errors.
        """
        raise NotImplementedError


# =============================================================================
# 3) RawRepository - camada de Evidência Bruta
# =============================================================================
class RawRepository(ABC):
    """Repositório imutável (append-only) de evidências brutas.

    Implementação inicial: FileSystemRepository — empacota cada RawEvidence
    em tar.gz, calcula SHA-256, registra em manifest.jsonl assinado.

    A imutabilidade e a verificação por hash compõem a cadeia de custódia
    do framework, em aderência a ABNT NBR ISO/IEC 27037:2013 e Casey (2011).

    Atributos de classe:
        name: Identificador único do plugin.
        version: Versão do plugin.

    Métodos abstratos:
        put: empacota a evidência e devolve referência com hash.
        get: recupera uma evidência armazenada (para re-análise sem re-coleta).
        verify: recomputa o hash do pacote armazenado e confirma integridade.
            Existe deliberadamente no contrato para que qualquer
            implementação saiba se auto-verificar.
    """

    name: ClassVar[str]
    version: ClassVar[str]

    @abstractmethod
    def put(self, evidence: RawEvidence, run_id: str) -> EvidenceRef:
        """Armazena a evidência e devolve referência com hash.

        Args:
            evidence: RawEvidence imutável.
            run_id: UUID da execução em curso (registrado no EvidenceRef).

        Returns:
            EvidenceRef: path do tar.gz, hash SHA-256, domain_url, run_id, created_at.

        Raises:
            IOError: se o armazenamento falhar.
        """
        raise NotImplementedError

    @abstractmethod
    def get(self, ref: EvidenceRef) -> RawEvidence:
        """Recupera uma evidência armazenada.

        Args:
            ref: referência produzida por put().

        Returns:
            RawEvidence: a evidência tal qual foi armazenada.

        Raises:
            FileNotFoundError: se a referência apontar para arquivo inexistente.
            ValueError: se a verificação de integridade falhar (hash divergente).
        """
        raise NotImplementedError

    @abstractmethod
    def verify(self, ref: EvidenceRef) -> bool:
        """Recomputa o hash do pacote armazenado e compara com ref.sha256.

        Args:
            ref: referência a verificar.

        Returns:
            True se o hash atual confere com o registrado em ref;
            False se houve adulteração ou corrupção.
        """
        raise NotImplementedError


# =============================================================================
# 4) VariableTest - camada de Análise
# =============================================================================
class VariableTest(ABC):
    """Teste aplicado a uma RawEvidence, produzindo um VariableResult.

    Cada subclasse implementa uma variável técnica do protocolo. Implementações
    iniciais: StructuralTest, LexiconTest, MLClassifierTest, CookieAnalyzer.

    Atributos de classe:
        name: Identificador único do plugin (tipicamente igual a variable_name).
        version: Versão do plugin.
        variable_name: Nome da variável produzida (vai no campo
            VariableResult.variable_name). Pode coincidir com name ou diferir
            quando uma mesma classe é parametrizada para produzir variáveis
            distintas via params.

    Método abstrato:
        evaluate: aplica o teste e devolve o resultado com audit_trail.
    """

    name: ClassVar[str]
    version: ClassVar[str]
    variable_name: ClassVar[str]

    @abstractmethod
    def evaluate(
        self,
        evidence: RawEvidence,
        params: dict[str, Any],
        *,
        protocol_version: str,
        run_id: str,
    ) -> VariableResult:
        """Aplica o teste à evidência e devolve o resultado.

        Args:
            evidence: RawEvidence imutável a analisar.
            params: parâmetros vindos do protocolo (limiares, dicionários, etc.).
            protocol_version: versão do protocol.yaml em uso (vai no resultado).
            run_id: UUID da execução (vai no resultado).

        Returns:
            VariableResult: value + confidence + audit_trail + metadados.
            audit_trail deve conter informação suficiente para reproduzir
            ou auditar a decisão (regra/seletor/snippet/modelo/top_features).
        """
        raise NotImplementedError


# =============================================================================
# 5) ResultStore - camada de Resultados Estruturados
# =============================================================================
class ResultStore(ABC):
    """Persistência tabular dos VariableResult em formato long-format.

    Implementação inicial: SQLiteStore (arquivo .sqlite versionado junto ao TCC).
    Outras implementações podem suportar PostgreSQL, DuckDB, etc.

    Atributos de classe:
        name: Identificador único do plugin.
        version: Versão do plugin.

    Métodos abstratos:
        upsert: insere ou atualiza um resultado. Re-execuções sob mesma chave
            natural (protocol_version, run_id, variable_name, domain_url)
            sobrescrevem — não duplicam.
        query: devolve resultados filtrados.
        close: encerra a conexão; necessário em backends com WAL/locks.
    """

    name: ClassVar[str]
    version: ClassVar[str]

    @abstractmethod
    def upsert(self, result: VariableResult) -> None:
        """Insere ou atualiza um resultado.

        Chave natural: (protocol_version, run_id, variable_name, domain_url).
        Se já existir registro com essa chave, sobrescreve.
        """
        raise NotImplementedError

    @abstractmethod
    def query(self, filter: dict[str, Any]) -> Iterable[VariableResult]:
        """Devolve resultados que satisfazem o filtro.

        Args:
            filter: dict com chaves entre {'variable_name', 'protocol_version',
                'run_id', 'domain_url', 'stratum', ...}.
        """
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Fecha conexão e libera recursos."""
        raise NotImplementedError


# =============================================================================
# 6) OutputRenderer - camada de Saída
# =============================================================================
class OutputRenderer(ABC):
    """Gera artefato consumível a partir dos resultados estruturados.

    Implementações iniciais: CsvExport, ParquetExport, MarkdownReport,
    DashboardJsonExport.

    Atributos de classe:
        name: Identificador único do plugin.
        version: Versão do plugin.

    Método abstrato:
        render: produz o artefato e devolve o caminho do arquivo gerado,
            fechando o ciclo de auditoria (orquestrador registra o caminho
            no audit_log.jsonl).
    """

    name: ClassVar[str]
    version: ClassVar[str]

    @abstractmethod
    def render(self, store: ResultStore, params: dict[str, Any]) -> Path:
        """Gera o artefato e devolve seu caminho final.

        Args:
            store: ResultStore com os dados a renderizar.
            params: parâmetros vindos do protocolo (e.g., {"path": "..."}).

        Returns:
            Path: caminho absoluto do arquivo gerado.
        """
        raise NotImplementedError


__all__ = [
    "SampleSource",
    "PageFetcher",
    "RawRepository",
    "VariableTest",
    "ResultStore",
    "OutputRenderer",
]
