"""
Tipos centrais do PrivacyScope.

Define os quatro dataclasses Pydantic que constituem o contrato de dados
trafegado entre as seis camadas da arquitetura (ver docs/arquitetura.md e
docs/figuras/figura1_arquitetura.svg).

Fluxo:
    Ingestão (1)         -> produz Domain
    Coleta (2)           -> consome Domain,         produz RawEvidence
    Evidência Bruta (3)  -> consome RawEvidence,    produz EvidenceRef
    Análise (4)          -> consome RawEvidence,    produz VariableResult
    Resultados (5)       -> consome VariableResult
    Saída (6)            -> consome VariableResult em lote

Convenções:
    - Todos os tipos são imutáveis (`frozen=True`). Uma vez criada, uma
      instância não pode ser modificada — protege contra mutação acidental
      de evidência entre testes e é requisito de reprodutibilidade.
    - Datas e horários são sempre em UTC (ABNT NBR ISO/IEC 27037:2013).
    - Validação ocorre nos limites das camadas: se um plugin tentar produzir
      um VariableResult inválido (confidence > 1.0, sha256 mal-formado, etc.),
      Pydantic rejeita antes do armazenamento.

Referências:
    - Pydantic v2: https://docs.pydantic.dev/latest/
    - Inversão de dependência e Open/Closed: Martin (2000)
    - Boas práticas de reprodutibilidade computacional: Wilson et al. (2017)
    - Cadeia de custódia de evidência digital: ABNT NBR ISO/IEC 27037:2013;
      Casey (2011)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# 1) Domain - produzido pela camada de Ingestao (SampleSource)
# =============================================================================
class Domain(BaseModel):
    """Endereço web a ser analisado pelo framework.

    Produzido pela camada de Ingestão a partir de uma SampleSource. Consumido
    pela camada de Coleta como entrada do PageFetcher.

    Attributes:
        url: URL completa com scheme http(s)://. Ex.: 'https://www.exemplo.gov.br'.
        tld: TLD efetivo extraído por tldextract. Ex.: '.gov.br', '.com.br'.
        source_name: Nome do plugin de Ingestão que produziu este Domain
            ('tranco', 'csv', ...). Aparece no audit_trail.
        rank: Posição no ranking da fonte de origem (Tranco fornece; CsvSource
            pode não fornecer). None quando não aplicável.
        stratum: Rótulo do estrato amostral atribuído pela política de
            amostragem ('governamental' | 'empresarial' | None).
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    url: str = Field(..., min_length=8, description="URL completa com scheme")
    tld: str = Field(..., min_length=3, description="TLD efetivo")
    source_name: str = Field(..., min_length=1, description="Plugin de origem")
    rank: Optional[int] = Field(default=None, ge=1, description="Rank no ranking de origem")
    stratum: Optional[str] = Field(default=None, description="Rótulo do estrato amostral")

    @field_validator("url")
    @classmethod
    def _validate_scheme(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url deve incluir scheme http:// ou https://")
        return v

    @field_validator("tld")
    @classmethod
    def _validate_tld(cls, v: str) -> str:
        if not v.startswith("."):
            raise ValueError("tld deve começar com '.' (ex.: '.gov.br')")
        return v


# =============================================================================
# 2) RawEvidence - produzido pela camada de Coleta (PageFetcher)
# =============================================================================
class RawEvidence(BaseModel):
    """Conjunto bruto de artefatos coletados de um Domain.

    Produzido pela camada de Coleta. Persistido pela camada de Evidência Bruta
    em arquivo tar.gz com hash SHA-256 (cadeia de custódia). Consumido pela
    camada de Análise como entrada dos VariableTest.

    A imutabilidade garante que um teste de análise não pode modificar a
    evidência consumida por outro teste — requisito essencial de
    reprodutibilidade e isolamento.

    Attributes:
        domain: Domain de origem.
        html_pages: dict path_relativo -> bytes do HTML. A chave é o path
            interno do site ('/', '/politica-privacidade', '/encarregado').
        cookies_by_phase: Dict ``{phase_name: [cookies]}`` contendo todos os
            cookies fixados durante a coleta, segmentados por fase. Cada cookie
            é um dict com ao menos 'name', 'domain', 'path', 'expires',
            'httpOnly', 'secure', 'sameSite'. Convenção de chaves:
            ``"single"`` para fetchers single-shot (HttpFetcher, CurlCffi etc.,
            que capturam cookies em uma única request HTTP sem interação JS);
            ``"pre_consent" | "post_consent" | "post_revocation"`` para o
            PlaywrightFetcher. Outros fetchers podem introduzir nomes próprios
            de fase sem alteração do schema — a estrutura é deliberadamente
            extensível por chave-string livre, em linha com ``phase_screenshots``.
        headers: dict url -> dict de cabeçalhos HTTP recebidos por aquela URL.
        screenshot: PNG full-page em bytes; None quando desabilitado no
            protocolo (ex.: execução de massa sem necessidade visual). Em
            fetchers multi-fase (PlaywrightFetcher), corresponde ao screenshot
            "principal" — tipicamente o pós-consent. Screenshots por fase ficam
            em ``phase_screenshots``.
        phase_screenshots: Dict ``{phase_name: PNG bytes}`` com capturas
            específicas de cada fase do PlaywrightFetcher. Chaves esperadas:
            ``"pre_consent" | "post_consent" | "post_revocation"``. Extensível
            sem mudança de schema. Vazio em fetchers de fase única (HttpFetcher).
        network_log: Log HAR-like das requisições feitas durante a coleta.
            Cada item tem timing, status, content-type, content-length.
        subpage_selection: Auditoria da seleção automática de subpáginas pelo
            fetcher. Estrutura:
            ``{categoria: [{url, matched_pattern, matched_against, snippet}]}``,
            onde ``matched_against`` é um de
            ``"text" | "aria-label" | "title" | "href"`` e ``snippet`` traz até
            120 caracteres do trecho que disparou o match. A ordem de inspeção
            prioriza ``text`` (humano vê) > ``aria-label`` (assistive tech) >
            ``title`` (tooltip) > ``href`` (URL). Vazio para fetchers que não
            selecionam subpáginas (e.g., fetchers de endpoint único).
            Consumido pelos VariableTests para compor o audit_trail dos
            resultados e por análises agregadas de qualidade das regras.
        consent_actions: Lista cronológica de ações automáticas tentadas pelo
            fetcher sobre UI de consent. Cada item:
            ``{phase: "accept"|"revoke"|"reject"|..., attempted, success,
            method, selector_used, button_text, snippet, duration_ms, error}``.
            Permite estender para novas fases (reject-all, granular) sem
            mudança de schema.
        fetcher_name: Identificador do fetcher que produziu ('http_simples',
            'playwright').
        timestamp_utc: Momento exato do término da coleta, em UTC.
        errors: Falhas não-fatais ocorridas (timeout em subpágina, redireci-
            onamento ignorado, etc.). Falhas fatais impedem a criação do
            RawEvidence, então aqui ficam apenas as recuperáveis.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    domain: Domain
    html_pages: dict[str, bytes] = Field(default_factory=dict)
    cookies_by_phase: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    consent_actions: list[dict[str, Any]] = Field(default_factory=list)
    headers: dict[str, dict[str, str]] = Field(default_factory=dict)
    screenshot: Optional[bytes] = None
    phase_screenshots: dict[str, bytes] = Field(default_factory=dict)
    network_log: list[dict[str, Any]] = Field(default_factory=list)
    subpage_selection: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    fetcher_name: str = Field(..., min_length=1)
    timestamp_utc: datetime
    errors: list[str] = Field(default_factory=list)

    @field_validator("timestamp_utc")
    @classmethod
    def _enforce_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp_utc deve ser timezone-aware")
        if v.utcoffset().total_seconds() != 0:
            raise ValueError("timestamp_utc deve estar em UTC (offset 0)")
        return v


# =============================================================================
# 3) EvidenceRef - produzido pela camada de Evidência Bruta (RawRepository)
# =============================================================================
class EvidenceRef(BaseModel):
    """Referência leve a uma RawEvidence armazenada em tar.gz.

    Retornado por RawRepository.put(). Permite que a camada de Análise saiba
    onde a evidência está e como verificar sua integridade, sem precisar
    carregá-la em memória.

    O par (path, sha256) constitui o elo formal da cadeia de custódia: se o
    hash recomputado do arquivo divergir do registrado aqui, a evidência foi
    adulterada.

    Attributes:
        path: Caminho absoluto do arquivo tar.gz no sistema de arquivos.
        sha256: Hash hex de 64 caracteres do arquivo tar.gz.
        domain_url: URL do domínio (denormalizado para queries rápidas no
            manifest sem precisar abrir o tar).
        run_id: UUID da execução que produziu esta evidência.
        created_at: Momento de escrita do arquivo tar.gz, em UTC.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    path: str = Field(..., min_length=1, description="Caminho absoluto do tar.gz")
    sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$", description="Hash hex SHA-256")
    domain_url: str = Field(..., min_length=8)
    run_id: str = Field(..., min_length=1)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _enforce_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("created_at deve ser timezone-aware")
        if v.utcoffset().total_seconds() != 0:
            raise ValueError("created_at deve estar em UTC (offset 0)")
        return v


# =============================================================================
# 4) VariableResult - produzido pela camada de Análise (VariableTest)
# =============================================================================
class VariableResult(BaseModel):
    """Resultado da aplicação de um VariableTest sobre uma RawEvidence.

    Persistido pela camada de Resultados Estruturados em formato long-format
    no SQLite/Parquet. Consumido pela camada de Saída pelos OutputRenderers.

    A presença obrigatória de `audit_trail`, `protocol_version` e
    `plugin_version` é o que torna o framework defensável em banca: qualquer
    veredito pode ser rastreado até a regra ou modelo que o produziu, à versão
    do plugin e à versão do protocolo que governou aquela execução.

    Attributes:
        domain_url: URL alvo do teste.
        variable_name: Nome da variável testada (ex.: 'tem_banner_cookies').
        value: Resultado; tipo varia por variável (bool, int, float, str).
        confidence: Confiança em [0, 1]. Testes determinísticos retornam 0.0
            ou 1.0; classificadores ML retornam a probabilidade da classe
            predita.
        audit_trail: Dicionário livre com evidência da decisão. Conteúdo
            varia por tipo de teste — esperado conter ao menos uma das
            chaves: 'rule_fired', 'snippet', 'model_name', 'top_features'.
        protocol_version: Versão do protocol.yaml que governou esta execução.
        plugin_version: Versão do plugin de teste específico.
        run_id: UUID da execução.
        timestamp_utc: Momento em que o teste foi executado.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    domain_url: str = Field(..., min_length=8)
    variable_name: str = Field(..., min_length=1)
    value: Union[bool, int, float, str]
    confidence: float = Field(..., ge=0.0, le=1.0)
    audit_trail: dict[str, Any] = Field(default_factory=dict)
    protocol_version: str = Field(..., min_length=1)
    plugin_version: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    timestamp_utc: datetime

    @field_validator("timestamp_utc")
    @classmethod
    def _enforce_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp_utc deve ser timezone-aware")
        if v.utcoffset().total_seconds() != 0:
            raise ValueError("timestamp_utc deve estar em UTC (offset 0)")
        return v


# =============================================================================
# Helper
# =============================================================================
def utc_now() -> datetime:
    """Retorna o instante atual em UTC, com tzinfo=timezone.utc.

    Use nos plugins em vez de `datetime.now()` (que é naive ou local).
    """
    return datetime.now(timezone.utc)


__all__ = [
    "Domain",
    "RawEvidence",
    "EvidenceRef",
    "VariableResult",
    "utc_now",
]
