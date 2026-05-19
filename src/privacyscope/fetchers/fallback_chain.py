"""
FallbackChain — orquestrador de cadeia de fetchers com escalonamento por sinais.

Implementa ``PageFetcher`` (camada 2). Para o consumidor (orquestrador,
testes, outros plugins), é só mais um fetcher: chama-se ``fetch(domain, params)``
e recebe-se ``RawEvidence``. Internamente, delega para uma lista ordenada
de fetchers reais, escalando conforme condições configuráveis.

Recursão é suportada por design: como ``FallbackChain`` é ``PageFetcher``,
pode-se passar uma ``FallbackChain`` como item da lista de outra
``FallbackChain`` (composite pattern). Permite agrupar famílias de
fetchers semanticamente quando o framework crescer.

Decoupling preservado:
    - Não importa nenhum fetcher concreto (apenas a ABC ``PageFetcher``)
    - Recebe instâncias prontas de ``PageFetcher`` no ``__init__``
    - Resolve fetcher por nome (``fetcher.name``) ao processar o YAML
    - Quem constrói os fetchers é o orquestrador (próximo arquivo)

Padrão de escalonamento (Padrão C da análise):
    Cadeia linear ordenada + condições any-of por fetcher (``escalate_if``)
    que podem ser de dois tipos:
        - ``{exception: NomeDaClasse}`` — casa exception classe ou subclasse
        - ``{signal: nome_do_sinal, ...params}`` — chama função do registry

    Condições any-of em ``abort_on`` (só ``exception``) cancelam a cadeia
    inteira sem escalonar (ex.: robots.txt proíbe).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, ClassVar

from privacyscope.core.interfaces import PageFetcher
from privacyscope.core.types import Domain, RawEvidence
from privacyscope.fetchers._exceptions import FetchError
from privacyscope.fetchers._signals import SIGNAL_REGISTRY

logger = logging.getLogger(__name__)


# =============================================================================
# Constantes
# =============================================================================
DEFAULT_MAX_RETRIES_PER_FETCHER = 1
DEFAULT_BACKOFF_INITIAL_MS = 500
DEFAULT_BACKOFF_FACTOR = 2.0


# =============================================================================
# FallbackChain
# =============================================================================
class FallbackChain(PageFetcher):
    """Cadeia ordenada de fetchers com escalonamento por sinais.

    Args:
        fetchers: lista de instâncias prontas de ``PageFetcher``. Cada
            instância é identificada por ``fetcher.name``. Não pode haver
            nomes duplicados.

    Raises:
        ValueError: lista vazia ou nomes duplicados.
    """

    name: ClassVar[str] = "fallback_chain"
    version: ClassVar[str] = "0.1.0"

    def __init__(self, fetchers: list[PageFetcher]) -> None:
        if not fetchers:
            raise ValueError("FallbackChain exige pelo menos 1 fetcher")
        self.fetchers_by_name: dict[str, PageFetcher] = {}
        for f in fetchers:
            if f.name in self.fetchers_by_name:
                raise ValueError(f"nome de fetcher duplicado: {f.name!r}")
            self.fetchers_by_name[f.name] = f

    # ------------------------------------------------------------------
    # Validação de params (chain config do YAML)
    # ------------------------------------------------------------------
    def _validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Valida estrutura do chain config. Falha cedo em config mal-formada."""
        cfg: dict[str, Any] = {}

        # fetchers — obrigatório, lista não-vazia
        fetchers_cfg = params.get("fetchers", [])
        if not isinstance(fetchers_cfg, list) or not fetchers_cfg:
            raise ValueError("params.fetchers deve ser lista não-vazia")

        validated_fetchers = []
        for i, entry in enumerate(fetchers_cfg):
            if not isinstance(entry, dict):
                raise ValueError(f"fetchers[{i}] deve ser dict")
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError(f"fetchers[{i}].name obrigatório (string não-vazia)")
            if name not in self.fetchers_by_name:
                raise ValueError(
                    f"fetcher {name!r} não foi registrado no construtor do "
                    f"FallbackChain. Disponíveis: {list(self.fetchers_by_name)}"
                )
            fetcher_params = entry.get("params", {})
            if not isinstance(fetcher_params, dict):
                raise ValueError(f"fetchers[{i}].params deve ser dict")
            escalate_if = entry.get("escalate_if", [])
            if not isinstance(escalate_if, list):
                raise ValueError(f"fetchers[{i}].escalate_if deve ser lista")
            for j, cond in enumerate(escalate_if):
                self._validate_condition(
                    cond, f"fetchers[{i}].escalate_if[{j}]", allow_signals=True
                )
            validated_fetchers.append({
                "name": name,
                "params": fetcher_params,
                "escalate_if": escalate_if,
            })
        cfg["fetchers"] = validated_fetchers

        # abort_on — opcional, só exceções
        abort_on = params.get("abort_on", [])
        if not isinstance(abort_on, list):
            raise ValueError("abort_on deve ser lista")
        for j, cond in enumerate(abort_on):
            self._validate_condition(cond, f"abort_on[{j}]", allow_signals=False)
        cfg["abort_on"] = abort_on

        # Retries e backoff
        cfg["max_retries_per_fetcher"] = params.get(
            "max_retries_per_fetcher", DEFAULT_MAX_RETRIES_PER_FETCHER
        )
        if (
            not isinstance(cfg["max_retries_per_fetcher"], int)
            or cfg["max_retries_per_fetcher"] < 0
        ):
            raise ValueError("max_retries_per_fetcher deve ser inteiro >= 0")

        cfg["backoff_initial_ms"] = params.get(
            "backoff_initial_ms", DEFAULT_BACKOFF_INITIAL_MS
        )
        if not isinstance(cfg["backoff_initial_ms"], int) or cfg["backoff_initial_ms"] < 0:
            raise ValueError("backoff_initial_ms deve ser inteiro >= 0")

        cfg["backoff_factor"] = params.get("backoff_factor", DEFAULT_BACKOFF_FACTOR)
        if not isinstance(cfg["backoff_factor"], (int, float)) or cfg["backoff_factor"] < 1.0:
            raise ValueError("backoff_factor deve ser número >= 1.0")

        return cfg

    @staticmethod
    def _validate_condition(cond: Any, path: str, allow_signals: bool) -> None:
        """Valida uma condição de escalate_if ou abort_on."""
        if not isinstance(cond, dict):
            raise ValueError(f"{path} deve ser dict")
        has_exc = "exception" in cond
        has_sig = "signal" in cond
        if has_exc and has_sig:
            raise ValueError(f"{path}: use 'exception' OU 'signal', não ambos")
        if not has_exc and not has_sig:
            raise ValueError(f"{path}: deve ter 'exception' ou 'signal'")
        if has_exc:
            if not isinstance(cond["exception"], str) or not cond["exception"]:
                raise ValueError(f"{path}.exception deve ser string com nome da classe")
        else:
            if not allow_signals:
                raise ValueError(
                    f"{path}: condição 'signal' não permitida aqui (apenas 'exception')"
                )
            sig_name = cond["signal"]
            if not isinstance(sig_name, str):
                raise ValueError(f"{path}.signal deve ser string")
            if sig_name not in SIGNAL_REGISTRY:
                raise ValueError(
                    f"{path}.signal={sig_name!r} não existe. "
                    f"Disponíveis: {list(SIGNAL_REGISTRY)}"
                )

    # ------------------------------------------------------------------
    # Avaliação de condições
    # ------------------------------------------------------------------
    @staticmethod
    def _eval_condition_on_exception(
        cond: dict, raised_exception: BaseException
    ) -> bool:
        """Verifica condição do tipo exception via MRO (suporta herança)."""
        if "exception" not in cond:
            return False
        target_name = cond["exception"]
        # MRO permite casar subclasses: NavigationFailedError casa FetchError
        return any(
            cls.__name__ == target_name for cls in type(raised_exception).__mro__
        )

    @staticmethod
    def _eval_condition_on_evidence(cond: dict, evidence: RawEvidence) -> bool:
        """Verifica condição do tipo signal contra evidência."""
        if "signal" not in cond:
            return False
        signal_name = cond["signal"]
        signal_fn = SIGNAL_REGISTRY[signal_name]
        signal_params = {k: v for k, v in cond.items() if k != "signal"}
        return signal_fn(evidence, signal_params)

    def _should_escalate(
        self,
        escalate_if: list[dict],
        evidence: RawEvidence | None,
        exception: BaseException | None,
    ) -> tuple[bool, str | None]:
        """Avalia se devemos escalar (any-of). Retorna (bool, motivo legível)."""
        for cond in escalate_if:
            if exception is not None and self._eval_condition_on_exception(cond, exception):
                return True, f"exception={cond['exception']}"
            if evidence is not None and self._eval_condition_on_evidence(cond, evidence):
                return True, f"signal={cond['signal']}"
        return False, None

    def _should_abort(
        self, abort_on: list[dict], exception: BaseException | None
    ) -> tuple[bool, str | None]:
        """Avalia se devemos cancelar a cadeia (any-of, só exceções)."""
        if exception is None:
            return False, None
        for cond in abort_on:
            if self._eval_condition_on_exception(cond, exception):
                return True, f"abort_on={cond['exception']}"
        return False, None

    # ------------------------------------------------------------------
    # Retry com backoff exponencial
    # ------------------------------------------------------------------
    async def _try_fetcher_with_retries(
        self,
        fetcher: PageFetcher,
        domain: Domain,
        fetcher_params: dict,
        max_retries: int,
        backoff_initial_ms: int,
        backoff_factor: float,
    ) -> tuple[RawEvidence | None, BaseException | None, list[str]]:
        """Tenta o fetcher até ``max_retries + 1`` vezes.

        Backoff exponencial entre tentativas (não aplicado após última).

        Returns:
            (evidence | None, last_exception | None, audit_lines).
        """
        audit_lines: list[str] = []
        last_exception: BaseException | None = None
        evidence: RawEvidence | None = None

        for attempt in range(max_retries + 1):
            t0 = time.perf_counter()
            try:
                evidence = await fetcher.fetch(domain, fetcher_params)
                duration_ms = int((time.perf_counter() - t0) * 1000)
                audit_lines.append(
                    f"chain.attempt fetcher={fetcher.name} retry={attempt} "
                    f"success duration_ms={duration_ms}"
                )
                last_exception = None
                return evidence, last_exception, audit_lines
            except BaseException as e:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                msg = str(e)[:120].replace("\n", " ")
                audit_lines.append(
                    f"chain.attempt fetcher={fetcher.name} retry={attempt} "
                    f"exception={type(e).__name__} message={msg!r} "
                    f"duration_ms={duration_ms}"
                )
                last_exception = e
                if attempt < max_retries:
                    delay_ms = backoff_initial_ms * (backoff_factor ** attempt)
                    await asyncio.sleep(delay_ms / 1000.0)
        return evidence, last_exception, audit_lines

    # ------------------------------------------------------------------
    # Anexa auditoria à evidência (preserva imutabilidade via model_copy)
    # ------------------------------------------------------------------
    @staticmethod
    def _enrich_with_audit(
        evidence: RawEvidence, chain_audit: list[str]
    ) -> RawEvidence:
        new_errors = list(evidence.errors) + chain_audit
        return evidence.model_copy(update={"errors": new_errors})

    # ------------------------------------------------------------------
    # ORQUESTRAÇÃO PRINCIPAL — fetch()
    # ------------------------------------------------------------------
    async def fetch(self, domain: Domain, params: dict[str, Any]) -> RawEvidence:
        """Itera pela cadeia, escalando conforme sinais. Levanta ou devolve."""
        cfg = self._validate_params(params)
        chain_audit: list[str] = [
            f"chain.start fetchers={[fe['name'] for fe in cfg['fetchers']]}"
        ]
        last_evidence_unsat: RawEvidence | None = None
        last_exception: BaseException | None = None

        for i, fetcher_entry in enumerate(cfg["fetchers"]):
            fname = fetcher_entry["name"]
            fparams = fetcher_entry["params"]
            escalate_if = fetcher_entry["escalate_if"]
            fetcher = self.fetchers_by_name[fname]

            chain_audit.append(f"chain.try[{i}] fetcher={fname}")
            evidence, exception, audit_lines = await self._try_fetcher_with_retries(
                fetcher,
                domain,
                fparams,
                cfg["max_retries_per_fetcher"],
                cfg["backoff_initial_ms"],
                cfg["backoff_factor"],
            )
            chain_audit.extend(audit_lines)

            # 1) abort?
            should_abort, abort_reason = self._should_abort(
                cfg["abort_on"], exception
            )
            if should_abort:
                chain_audit.append(f"chain.abort[{i}] reason={abort_reason}")
                logger.warning(
                    "FallbackChain abortada em %s: %s", fname, abort_reason
                )
                # Re-lança a exceção original — preserva tipo para o caller
                raise exception  # type: ignore[misc]

            # 2) Houve evidência?
            if evidence is not None:
                should_escalate, escalate_reason = self._should_escalate(
                    escalate_if, evidence, None
                )
                if not should_escalate:
                    chain_audit.append(f"chain.success[{i}] fetcher={fname}")
                    return self._enrich_with_audit(evidence, chain_audit)
                chain_audit.append(
                    f"chain.escalate[{i}->{i+1}] from={fname} reason={escalate_reason}"
                )
                last_evidence_unsat = evidence
                last_exception = None
                continue

            # 3) Não houve evidência (exceção). escalate_if cobre?
            should_escalate, escalate_reason = self._should_escalate(
                escalate_if, None, exception
            )
            if not should_escalate:
                chain_audit.append(
                    f"chain.fail[{i}] fetcher={fname} "
                    f"exception={type(exception).__name__} no_escalation_match"
                )
                raise FetchError(
                    f"FallbackChain falhou em {fname} sem condição de escalonamento "
                    f"casando: {type(exception).__name__}: {exception}. "
                    f"Audit: {chain_audit}"
                ) from exception
            chain_audit.append(
                f"chain.escalate[{i}->{i+1}] from={fname} reason={escalate_reason}"
            )
            last_evidence_unsat = None
            last_exception = exception

        # ====== Cadeia exaurida ======
        if last_evidence_unsat is not None:
            chain_audit.append("chain.exhausted last_evidence_matched_escalate_if")
            raise FetchError(
                f"FallbackChain exauriu — último fetcher produziu evidência mas "
                f"matchou escalate_if dele. Audit: {chain_audit}"
            )
        chain_audit.append("chain.exhausted no_evidence")
        if last_exception is not None:
            raise FetchError(
                f"FallbackChain exauriu sem evidência. Audit: {chain_audit}"
            ) from last_exception
        raise FetchError(f"FallbackChain exauriu. Audit: {chain_audit}")


__all__ = ["FallbackChain"]
