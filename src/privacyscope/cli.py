"""
CLI entrypoint do PrivacyScope.

Subcomandos:

    privacyscope run PROTOCOL.yaml
        Executa o pipeline completo declarado no YAML.

    privacyscope analyze PROTOCOL.yaml --run-id UUID
        Re-aplica os VariableTests do protocol sobre evidências de um run
        anterior — útil quando se ajusta a regra de algum teste sem querer
        re-coletar.

    privacyscope verify-manifest BASE_PATH
        Audita o manifest.jsonl de um repositório: detecta tar.gz
        corrompidos, ausentes, e quebra da cascata com audit_log.jsonl.

    privacyscope list-plugins
        Lista todos os plugins registrados (sources, fetchers, etc.).

Dependências externas: nenhuma além das que o pacote já usa (argparse stdlib).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from privacyscope.core.plugin_registry import list_plugins


logger = logging.getLogger("privacyscope.cli")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# =============================================================================
# Subcomandos
# =============================================================================
def cmd_run(args: argparse.Namespace) -> int:
    from privacyscope.orchestrator import Orchestrator

    orch = Orchestrator(args.protocol)
    try:
        run_id = asyncio.run(orch.run())
    finally:
        orch.close()
    print(f"\n=== Pipeline concluído ===")
    print(f"run_id:                  {run_id}")
    print(f"protocol_version:        {orch.protocol['metadata']['protocol_version']}")
    print(f"protocol_version_hash:   {orch.protocol_version_hash[:16]}...")
    print(f"raw repository:          {orch.repo.raw_dir}")
    print(f"result store:            {orch.store.db_path}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    from privacyscope.orchestrator import Orchestrator

    orch = Orchestrator(args.protocol)
    try:
        orch.analyze_only(args.run_id)
    finally:
        orch.close()
    print(f"\n=== Análise concluída ===")
    print(f"run_id:                  {args.run_id}")
    print(f"protocol_version:        {orch.protocol['metadata']['protocol_version']}")
    print(f"protocol_version_hash:   {orch.protocol_version_hash[:16]}...")
    return 0


def cmd_verify_manifest(args: argparse.Namespace) -> int:
    from privacyscope.storage.manifest_audit import verify_manifest

    report = verify_manifest(args.base_path)
    print(f"=== Auditoria de manifest ===")
    print(f"manifest:                {report.manifest_path}")
    print(f"total_entries:           {report.total_entries}")
    print(f"verified:                {report.verified}")
    print(f"missing:                 {report.missing}")
    print(f"corrupted:               {report.corrupted}")
    print(f"audit_log_consistent:    {report.audit_log_consistent}")
    if report.manifest_sha256:
        print(f"manifest_sha256:         {report.manifest_sha256[:16]}...")
    print(f"all_valid:               {report.all_valid}")
    if report.problems:
        print(f"\nproblemas ({len(report.problems)}):")
        for tar, p in report.problems:
            print(f"  - {tar or '<no_tar>'}: {p}")
    return 0 if report.all_valid else 2


def cmd_list_plugins(args: argparse.Namespace) -> int:
    inv = list_plugins()
    print(f"=== Plugins registrados ===")
    width = max(len(layer) for layer in inv) + 2
    for layer, names in inv.items():
        names_str = ", ".join(names) if names else "(vazio)"
        print(f"  {layer:<{width}} {names_str}")
    return 0


# =============================================================================
# Argparse
# =============================================================================
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="privacyscope",
        description="Framework de apoio à etapa de Monitoramento da ANPD.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Habilita logging em nível DEBUG.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMANDO")

    # run
    p_run = sub.add_parser("run", help="Executa pipeline completo a partir de protocol.yaml.")
    p_run.add_argument("protocol", type=Path, help="Caminho do protocol.yaml.")
    p_run.set_defaults(func=cmd_run)

    # analyze
    p_analyze = sub.add_parser(
        "analyze",
        help="Re-aplica VariableTests sobre evidências de um run existente.",
    )
    p_analyze.add_argument("protocol", type=Path, help="Caminho do protocol.yaml.")
    p_analyze.add_argument("--run-id", required=True, help="UUID do run a re-analisar.")
    p_analyze.set_defaults(func=cmd_analyze)

    # verify-manifest
    p_vm = sub.add_parser(
        "verify-manifest",
        help="Audita integridade do manifest de evidências.",
    )
    p_vm.add_argument("base_path", type=Path, help="Diretório raiz do repositório (contém raw/).")
    p_vm.set_defaults(func=cmd_verify_manifest)

    # list-plugins
    p_lp = sub.add_parser("list-plugins", help="Lista plugins registrados.")
    p_lp.set_defaults(func=cmd_list_plugins)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
