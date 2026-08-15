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
from privacyscope.core.types import NAO_APLICAVEL
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
        # Guarda de colisao, ANTES de construir qualquer coisa: protocolo invalido
        # nao deve criar repositorio nem banco antes de ser recusado.
        #
        # A camada de resultados tem chave unica por (protocolo, run, variavel,
        # dominio) e grava por substituicao. Dois testes que produzam o mesmo nome
        # de variavel se apagam mutuamente, e o sobrevivente depende da ordem de
        # declaracao — falha silenciosa da pior especie, porque o arquivo resultante
        # parece integro. A situacao e concreta: o canal do titular tem dois regimes
        # registrados, e o teto comparativo produz as mesmas variaveis da
        # representacao esparsa.
        nomes: dict[str, list[str]] = {}
        for t_cfg in self.protocol["tests"]:
            cls = resolve("variable_tests", t_cfg["name"])
            sufixo = (t_cfg.get("params") or {}).get("variavel_sufixo", "")
            nomes.setdefault(f"{cls.variable_name}{sufixo}", []).append(t_cfg["name"])
        repetidos = {k: v for k, v in nomes.items() if len(v) > 1}
        if repetidos:
            detalhe = "; ".join(f"{k} <- {', '.join(v)}" for k, v in repetidos.items())
            raise ValueError(
                f"o protocolo declara testes que produzem a mesma variavel: {detalhe}. "
                f"A camada de resultados sobrescreveria um com o outro sem aviso. "
                f"Declare `variavel_sufixo` em um deles, ou retire-o do protocolo.")

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

        # VariableTests — carrega rules_file (se houver) para dentro de params,
        # realizando o desenho declarado de config externa por teste. Arquivo
        # como base; params inline do protocolo sobrescrevem. Graceful se faltar.
        self.tests = []
        _root = Path(__file__).resolve().parents[2]
        for t_cfg in self.protocol["tests"]:
            TestCls = resolve("variable_tests", t_cfg["name"])
            params = dict(t_cfg.get("params", {}))
            rules_file = t_cfg.get("rules_file")
            if rules_file:
                file_params: dict = {}
                for _p in (Path(rules_file), _root / rules_file):
                    try:
                        if _p.is_file():
                            _data = yaml.safe_load(_p.read_text(encoding="utf-8"))
                            if isinstance(_data, dict):
                                file_params = _data
                            break
                    except Exception as _e:  # noqa: BLE001
                        logger.warning("rules_file %s ilegivel: %s", _p, _e)
                params = {**file_params, **params}
            self.tests.append((TestCls(), params))


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
                logger.error("falha em %s: %s", domain.url, exc, exc_info=False)
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
                logger.error("falha em %s: %s", domain.url, exc, exc_info=False)
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

        self.render_outputs(run_id)

    # ------------------------------------------------------------------
    # Saída — a sexta camada
    # ------------------------------------------------------------------
    def render_outputs(self, run_id: str | None = None) -> list[Path]:
        """Executa os renderizadores declarados em ``outputs``.

        A chave e opcional: protocolo sem ela encerra com os resultados apenas na
        camada de Resultados Estruturados, que e o comportamento anterior. Quando
        presente, cada entrada nomeia um renderizador registrado e seus parametros.

        O filtro por execucao e injetado quando o chamador informa o identificador,
        de modo que o artefato de saida corresponda ao que se acabou de produzir, e
        nao a tudo que ja houve no mesmo armazenamento.
        """
        entradas = self.protocol.get("outputs") or []
        if not entradas:
            return []
        gerados: list[Path] = []
        for cfg in entradas:
            nome = cfg["name"] if isinstance(cfg, dict) and "name" in cfg else None
            if nome is None:
                logger.warning("entrada de outputs sem `name`: %r", cfg)
                continue
            params = dict(cfg.get("params") or {})
            if run_id:
                params.setdefault("filtro", {}).setdefault("run_id", run_id)
            try:
                RendCls = resolve("output_renderers", nome)
            except KeyError as e:
                logger.error("renderizador %r nao registrado: %s", nome, e)
                continue
            try:
                caminho = RendCls().render(self.store, params)
            except Exception as exc:                          # noqa: BLE001
                # Falha de um renderizador nao invalida os resultados ja
                # persistidos nem impede os demais artefatos de saida.
                logger.error("falha no renderizador %s: %s", nome, exc)
                continue
            gerados.append(caminho)
            logger.info("saida gerada: %s -> %s", nome, caminho)
            print(f"  saida  {nome:16} {caminho}")
        return gerados

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _collect_one(self, domain: Domain) -> RawEvidence:
        """Invoca o fetcher (chain) para um domínio."""
        return await self.fetcher.fetch(domain, self.fetcher_params)

    def _analyze_evidence(self, evidence: RawEvidence, run_id: str) -> None:
        """Aplica os VariableTests à evidência, respeitando dependências declaradas.

        DEPENDÊNCIA ENTRE VARIÁVEIS
        ---------------------------
        Algumas variáveis só existem enquanto propriedade de um documento: finalidade,
        direitos do titular e transferência internacional são declarações DENTRO da
        política de privacidade. Aplicá-las a um sítio sem política é submeter a um
        classificador de políticas um material que não é política — e o resultado não
        é ausência de divulgação, é medição indevida.

        A consequência foi medida sobre 506 sítios: 46% não têm política detectada, e
        neles a variável de finalidade ainda saía positiva em 21,8% dos casos, o que
        respondia por 16% de todos os positivos. Um portal municipal, submetido ao
        classificador, dispara em itens de menu como "Cadastro de Fornecedores", que
        nomeiam atividade de tratamento sem ser declaração do controlador.

        A dependência é DECLARADA no protocolo, e não inferida dentro do plugin: os
        testes não se conhecem entre si, e embutir a regra num deles a tornaria
        invisível a quem lê o protocolo. Quando ela não é satisfeita, o resultado sai
        com valor ``nao_aplicavel`` — nunca ``false``, que confundiria "não divulgou"
        com "não foi medido" e enviesaria o indicador na direção que mais importa.

        O custo é conhecido e pequeno: o detector de política tem revocação de 95,2%
        sobre os sítios com política, de sorte que cerca de 5% deles recebem
        ``nao_aplicavel`` indevidamente. Vai declarado como limitação.
        """
        anteriores: dict[str, Any] = {}
        for test, params in self.tests:
            faltando = [d for d in (params.get("depende_de") or [])
                        if not anteriores.get(d)]
            if faltando:
                result = self._nao_aplicavel(test, evidence, run_id, faltando,
                                             anteriores)
            else:
                result = test.evaluate(
                    evidence, params,
                    protocol_version=self.protocol["metadata"]["protocol_version"],
                    run_id=run_id,
                )
            anteriores[result.variable_name] = result.value is True
            self.store.upsert(result)

    def _nao_aplicavel(self, test, evidence: RawEvidence, run_id: str,
                       faltando: list[str], anteriores: dict[str, Any]):
        """Resultado de variável cuja precondição não se verificou."""
        from datetime import datetime, timezone

        from privacyscope.core.types import VariableResult

        # Dependência não apurada difere de dependência apurada e falsa: a primeira
        # denuncia ordem errada no protocolo, e precisa ser distinguível no registro.
        nao_apuradas = [d for d in faltando if d not in anteriores]
        if nao_apuradas:
            logger.warning(
                "%s depende de %s, que ainda nao foi apurada nesta execucao; "
                "verifique a ordem dos testes no protocolo",
                getattr(test, "name", type(test).__name__), nao_apuradas)
        return VariableResult(
            domain_url=evidence.domain.url,
            variable_name=test.variable_name,
            value=NAO_APLICAVEL,
            confidence=0.0,
            audit_trail={"motivo": "precondicao_nao_satisfeita",
                         "depende_de": list(faltando),
                         "nao_apuradas": nao_apuradas,
                         "aplicavel": False},
            protocol_version=self.protocol["metadata"]["protocol_version"],
            plugin_version=getattr(test, "version", "0"),
            run_id=run_id,
            timestamp_utc=datetime.now(timezone.utc))

    def close(self) -> None:
        """Fecha recursos (ResultStore)."""
        try:
            self.store.close()
        except Exception:
            pass


__all__ = ["Orchestrator"]
