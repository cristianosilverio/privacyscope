# -*- coding: utf-8 -*-
"""Verificacao retrospectiva do desafio anti-bot sobre toda a evidencia guardada.

O QUE SE VERIFICA
-----------------
1. Quantas coletas do repositorio trazem marca de desafio anti-bot, por conjunto.
2. Se as paginas atingidas eram candidatas a politica de privacidade — condicao que
   determina se o veredito `tem_politica_privacidade = false` era falso negativo.
3. Se o detector, com a correcao, deixa de afirmar `false` nesses casos.

Os numeros apurados em 15/08/2026 estao AFIRMADOS abaixo. O programa termina com
codigo diferente de zero quando a apuracao diverge deles, de sorte que a afirmacao
feita no texto do trabalho fique amarrada a evidencia e nao a memoria.

Nao altera nada. Le os tar.gz e reaplica o detector em memoria.

Uso:
    python scripts/verificar_desafio_antibot.py
    python scripts/verificar_desafio_antibot.py --conjunto b9
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from privacyscope.fetchers.desafio_antibot import (          # noqa: E402
    bloqueada, detecta_desafio, paginas_bloqueadas)

# Apurado em 15/08/2026. Divergencia interrompe.
AFIRMADO = {
    "coletas_varridas": 1045,
    "sitios_atingidos": {
        "b7": ["casadaarte.com.br", "diariodolitoral.com.br"],
        "b9": ["futebolpaulista.com.br", "invictusmanipulacao.com.br"],
        "aovivo": ["noataque.com.br", "radios.com.br", "simepar.br"],
        "exercicio_csv": ["maxtitanium.com.br", "seminovos.com.br"],
    },
    "conjuntos_limpos": ["b4", "b7_T1", "b7_gov_supp", "b7_recollect",
                         "b9_validacao", "prepilot"],
    # Das 12 coletas atingidas, 10 tiveram o desafio sobre CANDIDATA A POLITICA — e
    # sao essas que produziam falso negativo. As 2 restantes sao simepar.br (uma por
    # execucao ao vivo), cuja pagina bloqueada estava na categoria
    # `acesso_informacao_gov` e cuja raiz veio integra, sem nenhuma candidata a
    # politica: ali o `false` nao decorre do bloqueio, e a correcao corretamente NAO
    # o altera.
    "coletas_com_desafio_em_candidata": 10,
    "coletas_com_desafio_fora_de_candidata": 2,
}


def _le_tar(caminho: str) -> tuple[dict, dict]:
    """Devolve (cabecalhos por URL, selecao de subpaginas) de um tar.gz."""
    cabecalhos: dict = {}
    selecao: dict = {}
    with tarfile.open(caminho) as t:
        for m in t.getmembers():
            if m.name.endswith("headers.json"):
                try:
                    cabecalhos.update(json.loads(
                        t.extractfile(m).read().decode("utf-8", "replace")))
                except Exception:                              # noqa: BLE001
                    pass
            elif m.name.endswith("meta.json"):
                try:
                    d = json.loads(t.extractfile(m).read().decode("utf-8", "replace"))
                except Exception:                              # noqa: BLE001
                    continue
                if isinstance(d, dict) and isinstance(d.get("subpage_selection"), dict):
                    selecao = d["subpage_selection"]
    return cabecalhos, selecao


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conjunto", help="limita a um diretorio sob data/")
    args = ap.parse_args()

    conjuntos = ([args.conjunto] if args.conjunto
                 else sorted(os.listdir(REPO / "data")))
    total = 0
    atingidos: dict[str, set[str]] = {}
    candidatas_ok = candidatas_nao = 0

    for c in conjuntos:
        arqs = sorted(glob.glob(str(REPO / "data" / c / "raw" / "*.tar.gz")))
        if not arqs:
            continue
        marcados: set[str] = set()
        for p in arqs:
            total += 1
            host = os.path.basename(p).split("__")[-1].replace(".tar.gz", "")
            cab, sel = _le_tar(p)
            ev = SimpleNamespace(headers=cab)
            d = detecta_desafio(ev)
            if not d:
                continue
            marcados.add(host)
            bloq = paginas_bloqueadas(ev)
            urls_cand = [x.get("url") for x in
                         sel.get("politica_privacidade", []) if x.get("url")]
            if any(bloqueada(u, bloq) for u in urls_cand):
                candidatas_ok += 1
            else:
                candidatas_nao += 1
                print(f"  nota: {host} teve pagina bloqueada FORA das candidatas a "
                      f"politica ({len(urls_cand)} candidatas); veredito preservado")
        print(f"{c:22s} {len(arqs):5d} coletas  {len(marcados):3d} sitios com desafio"
              f"  {sorted(marcados) if marcados else ''}")
        if marcados:
            atingidos[c] = marcados

    print(f"\ntotal de coletas varridas: {total}")
    print(f"coletas com desafio em candidata a politica: {candidatas_ok}")
    print(f"coletas com desafio fora de candidata:       {candidatas_nao}")

    if args.conjunto:
        return 0

    # --- confronto com o afirmado -------------------------------------------
    divergencias: list[str] = []
    if total != AFIRMADO["coletas_varridas"]:
        divergencias.append(
            f"coletas varridas: afirmado {AFIRMADO['coletas_varridas']}, apurado {total}")
    for conj, esperados in AFIRMADO["sitios_atingidos"].items():
        apurado = sorted(atingidos.get(conj, set()))
        if apurado != sorted(esperados):
            divergencias.append(f"{conj}: afirmado {esperados}, apurado {apurado}")
    for conj in AFIRMADO["conjuntos_limpos"]:
        if atingidos.get(conj):
            divergencias.append(f"{conj}: afirmado limpo, apurado {sorted(atingidos[conj])}")
    if candidatas_ok != AFIRMADO["coletas_com_desafio_em_candidata"]:
        divergencias.append(
            f"desafio em candidata a politica: afirmado "
            f"{AFIRMADO['coletas_com_desafio_em_candidata']}, apurado {candidatas_ok}")
    if candidatas_nao != AFIRMADO["coletas_com_desafio_fora_de_candidata"]:
        divergencias.append(
            f"desafio fora de candidata: afirmado "
            f"{AFIRMADO['coletas_com_desafio_fora_de_candidata']}, apurado {candidatas_nao}")

    if divergencias:
        print("\nDIVERGENCIA em relacao ao afirmado:")
        for d in divergencias:
            print("  -", d)
        return 1
    print("\nApuracao confere com o afirmado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
