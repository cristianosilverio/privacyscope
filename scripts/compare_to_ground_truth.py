"""
Compara output do PrivacyScope com rotulagem manual (ground truth).

Inputs:
    - results.sqlite gerado pelo Orchestrator (run_id especifico)
    - ground_truth.csv preenchido manualmente

Outputs:
    - comparison.md (Markdown legível) com:
        * Resumo geral: tabela com matriz 2x2 por variável
        * Métricas: precisão, recall, F1, acurácia, kappa de Cohen
        * Lista de discordâncias com link ao audit_trail
        * Aviso sobre IC largo em n=10

Uso::

    python scripts/compare_to_ground_truth.py \\
        --sqlite data/prepilot/results.sqlite \\
        --run-id <UUID> \\
        --ground-truth data/prepilot/ground_truth.csv \\
        --out data/prepilot/comparison.md
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


VARIABLES = ("tem_banner_cookies", "tem_politica_privacidade", "tem_canal_titular")


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------
def parse_bool(s: str) -> bool | None:
    """Tolera variações: 'true'/'TRUE'/'1'/'Sim' → True; 'false'/'0'/'Não' → False."""
    s = (s or "").strip().lower()
    if s in ("true", "1", "sim", "s", "y", "yes"):
        return True
    if s in ("false", "0", "nao", "não", "n", "no"):
        return False
    return None


def _read_text_robust(path: Path) -> str:
    """Le arquivo texto tolerando encoding. Excel no Windows-BR salva CSV em
    cp1252 (Windows-1252), nao utf-8. Tenta utf-8-sig (lida com BOM) e cai
    para cp1252 e por fim latin-1 (que nunca falha por byte invalido).
    """
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    # latin-1 nunca chega aqui, mas por seguranca:
    return path.read_text(encoding="latin-1", errors="replace")


def _detect_delimiter(header_line: str) -> str:
    """Detecta delimitador do CSV. Excel no Windows-BR usa ';' por padrao
    (separador de lista do locale pt-BR); ferramentas internacionais usam ','.
    Heuristica: o delimitador correto e o que aparece mais na linha de header.
    """
    candidates = [",", ";", "\t"]
    counts = {d: header_line.count(d) for d in candidates}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def load_ground_truth(path: Path) -> dict[str, dict[str, dict]]:
    """Retorna ``{domain_url: {variable_name: {value: bool|None, confidence: str}}}``."""
    import io

    gt: dict[str, dict[str, dict]] = {}
    text = _read_text_robust(text_path := path)
    first_line = text.splitlines()[0] if text.strip() else ""
    delimiter = _detect_delimiter(first_line)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    for row in reader:
        dom = (row.get("domain_url") or "").strip()
        if not dom:
            continue
        per_var = {}
        for v in VARIABLES:
            per_var[v] = {
                "value": parse_bool(row.get(f"{v}_value", "")),
                "confidence": (row.get(f"{v}_confidence", "") or "").strip().lower(),
            }
        gt[dom] = per_var
    return gt


def load_framework_results(sqlite_path: Path, run_id: str) -> dict[str, dict[str, dict]]:
    """Retorna ``{domain_url: {variable_name: {value: bool, confidence: float, audit_trail: dict}}}``."""
    conn = sqlite3.connect(sqlite_path)
    rows = conn.execute(
        "SELECT domain_url, variable_name, value, confidence, audit_trail_json "
        "FROM variables WHERE run_id = ? ORDER BY domain_url, variable_name",
        (run_id,),
    ).fetchall()
    conn.close()
    fw: dict[str, dict[str, dict]] = defaultdict(dict)
    for dom, var, val, conf, audit in rows:
        fw[dom][var] = {
            "value": json.loads(val),
            "confidence": conf,
            "audit_trail": json.loads(audit) if audit else {},
        }
    return dict(fw)


# ----------------------------------------------------------------------
# Métricas
# ----------------------------------------------------------------------
def confusion_matrix(pairs: list[tuple[bool, bool]]) -> dict[str, int]:
    """pairs = [(framework_value, human_value), ...]. Retorna {tp,tn,fp,fn,n}."""
    tp = tn = fp = fn = 0
    for fw, hu in pairs:
        if fw is True and hu is True:
            tp += 1
        elif fw is False and hu is False:
            tn += 1
        elif fw is True and hu is False:
            fp += 1
        elif fw is False and hu is True:
            fn += 1
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "n": tp + tn + fp + fn}


def metrics(cm: dict[str, int]) -> dict[str, float | None]:
    tp, tn, fp, fn, n = cm["tp"], cm["tn"], cm["fp"], cm["fn"], cm["n"]
    if n == 0:
        return {"precision": None, "recall": None, "f1": None, "accuracy": None, "kappa": None}
    prec = tp / (tp + fp) if (tp + fp) > 0 else None
    rec = tp / (tp + fn) if (tp + fn) > 0 else None
    f1 = (2 * prec * rec) / (prec + rec) if (prec and rec and (prec + rec) > 0) else None
    acc = (tp + tn) / n
    # Cohen's kappa
    po = (tp + tn) / n
    p_yes = ((tp + fp) * (tp + fn)) / (n * n)
    p_no = ((fn + tn) * (fp + tn)) / (n * n)
    pe = p_yes + p_no
    kappa = (po - pe) / (1 - pe) if pe < 1.0 else None
    return {"precision": prec, "recall": rec, "f1": f1, "accuracy": acc, "kappa": kappa}


def fmt(v: float | None) -> str:
    return f"{v:.3f}" if v is not None else "—"


# ----------------------------------------------------------------------
# Geração do Markdown
# ----------------------------------------------------------------------
def generate_markdown(
    framework: dict[str, dict[str, dict]],
    ground_truth: dict[str, dict[str, dict]],
    run_id: str,
) -> str:
    lines: list[str] = []
    lines.append(f"# Comparacao Framework vs Ground Truth Manual")
    lines.append("")
    lines.append(f"- **run_id:** `{run_id}`")
    lines.append(f"- **n (sites no framework):** {len(framework)}")
    lines.append(f"- **n (sites rotulados manualmente):** {len(ground_truth)}")
    common = set(framework.keys()) & set(ground_truth.keys())
    lines.append(f"- **n (interseccao analisada):** {len(common)}")
    lines.append("")
    lines.append(
        "> **Aviso:** com n≤10, os intervalos de confianca das metricas sao largos. "
        "Este pre-piloto serve para detectar CLASSES DE ERRO no framework, nao para "
        "gerar metricas defensaveis para o TCC. As metricas estatisticamente robustas "
        "vem da subamostra de validacao em B8/B9 (n=50, IC 95%, margem 10%)."
    )
    lines.append("")

    # --- Resumo por variável ---------------------------------------------
    lines.append("## Resumo por variavel")
    lines.append("")
    lines.append("| Variavel | n | TP | TN | FP | FN | Acuracia | Precisao | Recall | F1 | Kappa |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    overall_cms = {}
    for var in VARIABLES:
        pairs = []
        for dom in sorted(common):
            fw = framework[dom].get(var)
            gt = ground_truth[dom].get(var)
            if not fw or not gt:
                continue
            if gt["value"] is None:
                continue  # célula nao rotulada — pular
            pairs.append((fw["value"], gt["value"]))
        cm = confusion_matrix(pairs)
        m = metrics(cm)
        overall_cms[var] = (cm, m)
        lines.append(
            f"| `{var}` | {cm['n']} | {cm['tp']} | {cm['tn']} | {cm['fp']} | {cm['fn']} | "
            f"{fmt(m['accuracy'])} | {fmt(m['precision'])} | {fmt(m['recall'])} | "
            f"{fmt(m['f1'])} | {fmt(m['kappa'])} |"
        )
    lines.append("")

    # --- Discordâncias por variável -------------------------------------
    lines.append("## Discordancias detalhadas")
    lines.append("")
    any_disc = False
    for var in VARIABLES:
        disc_rows: list[tuple[str, dict, dict]] = []
        for dom in sorted(common):
            fw = framework[dom].get(var)
            gt = ground_truth[dom].get(var)
            if not fw or not gt or gt["value"] is None:
                continue
            if fw["value"] != gt["value"]:
                disc_rows.append((dom, fw, gt))
        if not disc_rows:
            continue
        any_disc = True
        lines.append(f"### `{var}` — {len(disc_rows)} discordancia(s)")
        lines.append("")
        for dom, fw, gt in disc_rows:
            kind = ("FP" if fw["value"] is True else "FN")
            lines.append(f"#### {kind}: {dom}")
            lines.append("")
            lines.append(f"- **Framework:** value=`{fw['value']}`, confidence=`{fw['confidence']:.2f}`")
            lines.append(f"- **Humano:** value=`{gt['value']}`, confidence=`{gt['confidence']}`")
            lines.append(f"")
            lines.append(f"**Audit trail do framework:**")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(fw["audit_trail"], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")
    if not any_disc:
        lines.append("Nenhuma discordancia encontrada — framework concorda 100% com a rotulagem manual.")
        lines.append("")

    # --- Sites sem rotulagem ou sem framework ---------------------------
    only_fw = set(framework.keys()) - set(ground_truth.keys())
    only_gt = set(ground_truth.keys()) - set(framework.keys())
    if only_fw or only_gt:
        lines.append("## Cobertura parcial")
        lines.append("")
        if only_fw:
            lines.append(f"**Coletado pelo framework mas nao rotulado manualmente** ({len(only_fw)}):")
            for d in sorted(only_fw):
                lines.append(f"- `{d}`")
            lines.append("")
        if only_gt:
            lines.append(f"**Rotulado manualmente mas nao coletado pelo framework** ({len(only_gt)}):")
            for d in sorted(only_gt):
                lines.append(f"- `{d}`")
            lines.append("")

    # --- Recomendação operacional ---------------------------------------
    lines.append("## Recomendacao operacional (criterio D17)")
    lines.append("")
    for var, (cm, m) in overall_cms.items():
        total_disc = cm["fp"] + cm["fn"]
        if total_disc >= 3:
            lines.append(f"- **`{var}`** ({total_disc} discordancias): REFINAR antes da piloto B4. "
                         f"Investigar audit_trail acima para identificar classe de erro dominante.")
        elif total_disc > 0:
            lines.append(f"- **`{var}`** ({total_disc} discordancias): anotar para B7 pos-feedback do Denis. "
                         f"Nao vale risco de overfit com n≤10.")
        else:
            lines.append(f"- **`{var}`** (0 discordancias): manter como esta. Re-avaliar com n=50 na piloto.")
    lines.append("")

    return "\n".join(lines)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite", type=Path, required=True, help="results.sqlite")
    p.add_argument("--run-id", required=True, help="UUID do run a comparar")
    p.add_argument("--ground-truth", type=Path, required=True, help="ground_truth.csv preenchido")
    p.add_argument(
        "--out", type=Path, default=Path("data/prepilot/comparison.md"),
        help="Caminho do markdown de saida.",
    )
    args = p.parse_args()

    if not args.sqlite.exists():
        print(f"ERRO: sqlite nao encontrado: {args.sqlite}", file=sys.stderr)
        return 1
    if not args.ground_truth.exists():
        print(f"ERRO: ground_truth nao encontrado: {args.ground_truth}", file=sys.stderr)
        return 1

    fw = load_framework_results(args.sqlite, args.run_id)
    gt = load_ground_truth(args.ground_truth)

    if not fw:
        print(f"ERRO: nenhum resultado encontrado para run_id={args.run_id}", file=sys.stderr)
        return 2
    if not gt:
        print(f"ERRO: ground_truth vazio em {args.ground_truth}", file=sys.stderr)
        return 2

    md = generate_markdown(fw, gt, args.run_id)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(f"OK comparison gerado em: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
