# -*- coding: utf-8 -*-
"""Listagem de revisao das formas de canal registradas em ``canal_forma``.

A auditoria do extrator evidenciou divergencias entre a forma registrada e a
definicao constante do codebook. Este script reune os fatos observaveis de cada
sitio positivo — enderecos de e-mail presentes, prefixo, dominio e ancoragem — ao
lado da forma registrada, de modo a subsidiar revisao manual.

O script nao altera a rotulagem. Produz outputs/revisao_formas_canal.csv.

Escopo da revisao. O rotulo binario ``tem_canal_titular`` nao e objeto de
alteracao: nos casos listados o canal existe, e apenas o subtipo esta em questao.
Alterar o binario a partir de saida de extrator contaminaria o gabarito. O campo
``canal_forma``, por nao integrar o conjunto de entrada do modelo, admite
correcao — cujo criterio e a conformidade ao codebook, padrao escrito e anterior
ao extrator.

Consequencia metodologica. Uma vez corrigidas as formas, a auditoria passa a
medir a aderencia do extrator ao codebook, e nao mais o alinhamento entre
criterio sintatico e julgamento semantico. Este ultimo constitui achado do
trabalho — em orgaos publicos o Encarregado costuma responder por dominio do
orgao-pai, como em ``planalto.gov.br`` e ``encarregado.lgpd@presidencia.gov.br``
— e sua preservacao e recomendavel.

Regra do codebook (secao 5) aplicada para sugestao:
  email_lgpd_controlador  : prefixo de privacidade e dominio do proprio sitio
  email_grupo_controlador : dominio distinto do sitio
  email_generico_rotulado : sem prefixo de privacidade, ancorado a direitos

Uso:
    python scripts/revisar_formas_canal.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "extr", REPO / "scripts" / "extrair_features_canal.py")
_extr = importlib.util.module_from_spec(_spec)
_sys_argv, sys.argv = sys.argv, ["x"]
_spec.loader.exec_module(_extr)
sys.argv = _sys_argv


def nz(v) -> str:
    return (v or "").strip()


def forma_sugerida(prefixo_lgpd: bool, mesmo_dom: bool, ancorado: bool) -> str:
    """Aplica a regra constante do codebook. Independe do modelo."""
    if prefixo_lgpd and mesmo_dom:
        return "email_lgpd_controlador"
    if not mesmo_dom:
        return "email_grupo_controlador"
    if not prefixo_lgpd and ancorado:
        return "email_generico_rotulado"
    return "(ambiguo — decidir manualmente)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotulos", default="rotulagem_b9.csv")
    ap.add_argument("--out", default="outputs/revisao_formas_canal.csv")
    ap.add_argument("--janela", type=int, default=200)
    args = ap.parse_args()

    with (REPO / args.rotulos).open(encoding="utf-8-sig", newline="") as fh:
        rot = list(csv.DictReader(fh, delimiter=";"))
    man = {}
    for l in (_extr.RAW / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if l.strip():
            e = json.loads(l)
            man[_extr.dominio_base(e["domain_url"])] = e

    FORMAS_EMAIL = ["email_lgpd_controlador", "email_grupo_controlador",
                    "email_generico_rotulado"]
    linhas = []
    for r in rot:
        if nz(r.get("tem_canal_titular")) != "1":
            continue
        rotuladas = [f for f in FORMAS_EMAIL if nz(r.get("forma:" + f)) == "1"]
        if not rotuladas:
            continue                       # a revisao abrange apenas formas de e-mail
        host = nz(r["site_id"])
        e = man.get(host)
        if not e:
            continue
        try:
            html, vis, _ = _extr.carregar(_extr.RAW / e["tar_filename"])
        except Exception:
            continue
        tot = vis + " " + _extr.texto_pdf(host)
        sdom = _extr.dominio_base(e["domain_url"])
        anc = _extr.posicoes_ancora(tot)

        emails = sorted({x.lower() for x in _extr.EMAIL_RE.findall(tot)}
                        | {x.lower() for x in _extr.EMAIL_RE.findall(html)})
        import re as _re
        for em in emails:
            user, dom = em.split("@", 1)
            if _extr.eh_provedor(dom):
                continue
            pref = any(user.startswith(p) for p in _extr.PREFIXOS_LGPD)
            mesmo = _extr.mesmo_dominio(dom, sdom)
            ancorado = _extr.perto_pos(
                anc, _re.compile(_re.escape(em), _re.I), tot, args.janela)
            sug = forma_sugerida(pref, mesmo, ancorado)
            diverge = sug not in rotuladas and not sug.startswith("(")
            linhas.append({
                "site_id": host,
                "estrato": nz(r.get("estrato")),
                "formas_rotuladas": "|".join(rotuladas),
                "email": em,
                "prefixo_privacidade": "sim" if pref else "nao",
                "dominio_email": dom,
                "dominio_sitio": sdom,
                "mesmo_dominio": "sim" if mesmo else "nao",
                "ancorado_a_direitos": "sim" if ancorado else "nao",
                "forma_pelo_codebook": sug,
                "DIVERGE": "SIM" if diverge else "",
                "canal_evid": nz(r.get("canal_evid"))[:180],
            })

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = list(linhas[0].keys()) if linhas else []
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=";")
        w.writeheader(); w.writerows(linhas)

    div = [l for l in linhas if l["DIVERGE"] == "SIM"]
    sites_div = sorted({l["site_id"] for l in div})
    print(f"linhas analisadas (e-mails em sitios positivos): {len(linhas)}")
    print(f"linhas com divergencia: {len(div)}  |  sitios afetados: {len(sites_div)}")
    print(f"\nsaida: {out}")
    print("\nA revisao incide apenas sobre canal_forma. O binario tem_canal_titular")
    print("permanece inalterado.")
    if sites_div:
        print("\nsitios com divergencia:")
        for s in sites_div[:30]:
            l = next(x for x in div if x["site_id"] == s)
            print(f"  {s:30.30} rotulado={l['formas_rotuladas']:24.24} "
                  f"codebook={l['forma_pelo_codebook']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
