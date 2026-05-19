"""
Orchestrator — executa o pipeline declarado no protocol.yaml.

Lê o YAML, resolve plugins via ``core.plugin_registry``, executa as 6
camadas em ordem (Ingestão → Coleta → Evidência → Análise → Resultados →
Saída) e registra um ``run_id`` único no SQLite.

Três modos de operação:

    - ``run()``: pipeline completo. Coleta + análise.
    - ``collect_only()``: para após persistir as evidências brutas.
    - ``analyze_only(run_id)``: lê evidências de um run anterior (via
      manifest.jsonl) e aplica os VariableTests. Útil quando se ajusta a
      regra de algum teste e quer-se re-rodar sem nova coleta.

Política operacional:
    - Falhas em **um site** não interrompem o run inteiro (decisão D12).
      A exceção é registrada em ``runs.errors_count`` e o loop segue.
    - O hash SHA-256 do protocol.yaml é calculado e gravado em cada
      evidência persistida (rastreabilidade entre parâmetros e resultados).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import yaml

from privacyscope.core.plugin_registry import resolve
from privacyscope.core.types import Domain, EvidenceRef, RawEvidence

logger = logging.getLogger(__name__)


# =============================================================================
# Orchestrator
# =============================================================================
class Orchestrator:
    """Executa pipeline conforme protocol.yaml.

    Args:
        protocol_yaml_path: caminho do arquivo YAML.

    Raises:
        FileNotFoundError: se o YAML não existir.
        ValueError: se o YAML for inválido (estrutura) ou referenciar
            plugin não registrado.
    """

    def __init__(self, protocol_yaml_path: Path | str) -> None:
        self.protocol_path = Path(protocol_yaml_path)
        if not self.protocol_path.exists():
            raise FileNotFoundError(f"protocol não encontrado: {self.protocol_path}")

        raw_bytes = self.protocol_path.read_bytes()
        self.protocol_version_hash = hashlib.sha256(raw_bytes).hexdigest()
        try:
            self.protocol: dict[str, Any] = yaml.safe_load(raw_bytes) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"YAML inválido em {self.protocol_path}: {e}") from e

        self._validate_protocol()
        self._build_plugins()

    # ------------------------------------------------------------------
    # Validação e construção de plugins
    # ------------------------------------------------------------------
    def _validate_protocol(self) -> None:
        """Verifica chaves obrigatórias. Falha-cedo com mensagem clara."""
        required_top = ["metadata", "repository", "result_store", "fetcher", "tests"]
        missing = [k for k in required_top if k not in self.protocol]
        if missing:
            raise ValueError(
                f"protocol.yaml sem chaves obrigatórias: {missing}. "
                f"Disponíveis: {sorted(self.protocol.keys())}"
            )
        if not isinstance(self.protocol["tests"], list) or not self.protocol["tests"]:
            raise ValueError("'tests' deve ser lista não-vazia")

    def _build_plugins(self) -> None:
        """Instancia todos os plugins declarados, falha-cedo se algum não existir."""
        # Repository
        repo_cfg = self.protocol["repository"]
        RepoCls = resolve("repositories", repo_cfg["name"])
        self.repo = RepoCls(**repo_cfg.get("params", {}))

        # ResultStore
        store_cfg = self.protocol["result_store"]
        StoreCls = resolve("result_stores", store_cfg["name"])
        self.store = StoreCls(**store_cfg.get("params", {}))

        # Fetcher (instancia o FallbackChain com fetchers internos)
        fetcher_cfg = self.protocol["fetcher"]
        if fetcher_cfg["name"] == "fallback_chain":
            inner_fetchers = []
            for fe_entry in fetcher_cfg["params"]["fetchers"]:
                FeCls = resolve("fetchers", fe_entry["name"])
                inner_fetchers.append(FeCls())
            ChainCls = resolve("fetchers", "fallback_chain")
            self.fetcher = ChainCls(fetchers=inner_fetchers)
            # Params para o fetch(): repassa o dict inteiro de params
            self.fetcher_params = fetcher_cfg["params"]
        else:
            # Single fetcher (não-chain)
            FeCls = resolve("fetchers", fetcher_cfg["name"])
            self.fetcher = FeCls()
            self.fetcher_params = fetcher_cfg.get("params", {})

        # VariableTests
        self.tests = []
        for t_cfg in self.protocol["tests"]:
            TestCls = resolve("variable_tests", t_cfg["name"])
            self.tests.append((TestCls(), t_cfg.get("params", {})))

    # ------------------------------------------------------------------
    # Domínios
    # ------------------------------------------------------------------
    def _iter_domains(self) -> Iterator[Domain]:
        """Resolve domínios a serem coletados.

        Preferência: ``override_domains`` no YAML (útil para smoke e debug).
        Senão: instancia o SampleSource declarado em ``sources``.
        """
        override = self.protocol.get("override_domains")
        if override:
            for url in override:
                yield Domain(url=url, tld=".br", source_name="override")
            return

        sources_cfg = self.protocol.get("sources", [])
        if not sources_cfg:
            raise ValueError("protocol.yaml deve declarar 'sources' ou 'override_domains'")
        for src_entry in sources_cfg:
            SrcCls = resolve("sources", src_entry["name"])
            src = SrcCls(**src_entry.get("params", {}))
            max_n = src_entry.get("params", {}).get("max_n", 50)
            count = 0
            for dom in src.iter():
                yield dom
                count += 1
                if count >= max_n:
                    break

    # ------------------------------------------------------------------
    # Modos de operação
    # ------------------------------------------------------------------
    async def run(self) -> str:
        """Pipeline completo: coleta + análise. Retorna ``run_id``."""
        run_id = str(uuid.uuid4())
        domains = list(self._iter_domains())
        self.store.begin_run(
            run_id,
            protocol_version=self.protocol["metadata"]["protocol_version"],
            sample_size=len(domains),
        )
        errors = 0
        for domain in domains:
            try:
                evidence = await self._collect_one(domain)
                ref = self.repo.put(
                    evidence, run_id,
                    protocol_version_hash=self.protocol_version_hash,
                )
                logger.info("collected %s -> %s", domain.url, Path(ref.path).name)
                self._analyze_evidence(evidence, run_id)
            except Exception as exc:
                logger.error("falha em %s: %s", domain.url, exc, exc_info=True)
                errors += 1
        self.store.finish_run(run_id, errors_count=errors)
        return run_id

    async def collect_only(self) -> str:
        """Apenas camadas 1-3 (Ingestão → Coleta → Evidência). Retorna run_id."""
        run_id = str(uuid.uuid4())
        domains = list(self._iter_domains())
        self.store.begin_run(
            run_id,
            protocol_version=self.protocol["metadata"]["protocol_version"],
            sample_size=len(domains),
        )
        errors = 0
        for domain in domains:
            try:
                evidence = await self._collect_one(domain)
                self.repo.put(evidence, run_id, protocol_version_hash=self.protocol_version_hash)
            except Exception as exc:
                logger.error("falha em %s: %s", domain.url, exc, exc_info=True)
                errors += 1
        self.store.finish_run(run_id, errors_count=errors)
        return run_id

    def analyze_only(self, run_id: str) -> None:
        """Re-aplica VariableTests sobre evidências persistidas do run_id.

        Lê o manifest.jsonl do repositório, reconstrói o EvidenceRef de cada
        entry pertencente ao run_id, recupera a RawEvidence via repo.get(),
        e aplica os tests declarados no protocol atual. Útil quando se ajusta
        a regra de algum teste sem querer re-coletar.

        Args:
            run_id: UUID do run anterior cujas evidências serão re-analisadas.

        Raises:
            ValueError: se nenhuma entrada do manifest referenciar este run_id.
        """
        manifest_path = self.repo.raw_dir / "manifest.jsonl"
        if not manifest_path.exists():
            raise ValueError(f"manifest não encontrado em {manifest_path}")

        entries_for_run = []
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("run_id") == run_id:
                entries_for_run.append(entry)

        if not entries_for_run:
            raise ValueError(f"nenhuma evidência encontrada para run_id={run_id}")

        for entry in entries_for_run:
            tar_path = self.repo.raw_dir / entry["tar_filename"]
            ref = EvidenceRef(
                path=str(tar_path.resolve()),
                sha256=entry["sha256"],
                domain_url=entry["domain_url"],
                run_id=entry["run_id"],
                created_at=datetime.fromisoformat(entry["created_at"]),
            )
            try:
                evidence = self.repo.get(ref)
                self._analyze_evidence(evidence, run_id)
            except Exception as exc:
                logger.error("falha analyze_only em %s: %s", entry["domain_url"], exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _collect_one(self, domain: Domain) -> RawEvidence:
        """Invoca o fetcher (chain) para um domínio."""
        return await self.fetcher.fetch(domain, self.fetcher_params)

    def _analyze_evidence(self, evidence: RawEvidence, run_id: str) -> None:
        """Aplica todos os VariableTests à evidência e persiste resultados."""
        for test, params in self.tests:
            result = test.evaluate(
                evidence, params,
                protocol_version=self.protocol["metadata"]["protocol_version"],
                run_id=run_id,
            )
            self.store.upsert(result)

    def close(self) -> None:
        """Fecha recursos (ResultStore)."""
        try:
            self.store.close()
        except Exception:
            pass


__all__ = ["Orchestrator"]
