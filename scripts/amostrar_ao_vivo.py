# -*- coding: utf-8 -*-
"""Amostra dominios .br de uma lista Tranco e gera o protocolo da coleta ao vivo.

PROPOSITO, E O QUE ESTA COLETA NAO E
------------------------------------
Serve a VALIDACAO TECNICA do caminho de coleta: o comando `run` nunca foi
exercitado com as quatro variaveis por classificacao supervisionada. Todas as
verificacoes ate aqui usaram `analyze` sobre evidencia congelada, de sorte que a
juncao entre coletor e classificador — em que a evidencia chega recem-produzida, com
PDF baixado na hora e selecao de subpaginas fresca — permanece a ultima nao
exercitada. E onde ja falhamos duas vezes.

**Os resultados NAO integram a amostra do trabalho.** O quadro amostral aqui e outra
lista Tranco, com identificador proprio, e portanto outro universo: misturar as
observacoes produziria conjunto com tres quadros amostrais e nenhum desenho
declarado. O que esta coleta produz e evidencia de que o arcabouco executa de ponta
a ponta, e nada alem disso.

REPRODUTIBILIDADE DA ENTRADA
----------------------------
A lista e obtida pela propria fonte amostral do arcabouco, que a baixa uma vez por
identificador e grava manifesto paralelo com resumo SHA-256, tamanho e instante. O
identificador da Tranco e imutavel, de sorte que a amostra e reproduzivel a partir
de (identificador, semente, tamanho).

FILTROS
-------
Reaproveitam-se os de scripts/sample_b4.py, ja validados: deduplicacao por dominio
registravel, exclusao de encurtadores e redes de distribuicao, e descarte de
subdominio cujo primeiro rotulo indique infraestrutura. Sem eles, a amostra se enche
de hospedagem e ativos, que nao sao sitios institucionais.

Uso:
    python scripts/amostrar_ao_vivo.py --list-id N2KLW --n 100
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import random
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from privacyscope.sources.tranco import TrancoSource          # noqa: E402

_spec = importlib.util.spec_from_file_location("s4", REPO / "scripts" / "sample_b4.py")
_s4 = importlib.util.module_from_spec(_spec)
# O modulo precisa constar de sys.modules ANTES de executado: o decorador de classe
# de dados consulta sys.modules[cls.__module__] ao processar a classe, e sem o
# registro a consulta devolve vazio e a carga falha com erro que nao diz isso.
sys.modules[_spec.name] = _s4
_spec.loader.exec_module(_s4)


def _resumo(caminho: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-id", required=True,
                    help="identificador da lista Tranco (tranco-list.eu)")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--top-n", type=int, default=200_000,
                    help="profundidade do ranque a considerar")
    ap.add_argument("--semente", type=int, default=20260812)
    ap.add_argument("--protocolo", default="protocols/aovivo.yaml")
    ap.add_argument("--amostra", default="protocols/aovivo_amostra.csv")
    ap.add_argument("--excluir", action="append", default=[],
                    help="CSV cujos dominios devem ficar de fora; repetivel")
    ap.add_argument("--so-lista", action="store_true",
                    help="grava apenas o CSV, sem gerar protocolo; a lista serve de "
                         "entrada para a fonte `csv`")
    args = ap.parse_args()

    print(f"lista Tranco {args.list_id}, top {args.top_n:,}")
    fonte = TrancoSource(cache_root=REPO / "data" / "raw")
    dominios = list(fonte.list_domains({"list_id": args.list_id, "top_n": args.top_n,
                                        "tld_filters": [".br"]}))
    print(f"  dominios .br no recorte: {len(dominios):,}")

    extract = None
    try:
        import tldextract
        extract = tldextract.TLDExtract(cache_dir=str(REPO / "data" / "raw" / "tldextract_cache"))
    except Exception:                                          # noqa: BLE001
        pass

    # Exclusoes: dominios ja empregados em outra amostra. Reamostrar sobre eles
    # produziria conjuntos sobrepostos, e comparar resultados entre amostras que
    # compartilham unidades confundiria diferenca de material com repeticao.
    excluidos: set[str] = set()
    for arq in args.excluir:
        a = Path(arq)
        if not a.is_absolute():
            a = REPO / arq
        if not a.is_file():
            print(f"ERRO: arquivo de exclusao nao encontrado: {a}")
            return 2
        with a.open(encoding="utf-8-sig", newline="") as fh:
            amostra_txt = fh.read(8192); fh.seek(0)
            d = ";" if amostra_txt.count(";") > amostra_txt.count(",") else ","
            for linha in csv.DictReader(fh, delimiter=d):
                for c in ("dominio", "url", "host", "site"):
                    if linha.get(c):
                        h = linha[c].replace("https://", "").replace("http://", "")
                        excluidos.add(h.split("/")[0].strip().lower())
                        break
    if excluidos:
        print(f"  excluidos por lista previa: {len(excluidos):,}")

    vistos, elegiveis = set(), []
    for d in dominios:
        host = d.url.replace("https://", "").replace("http://", "").rstrip("/").lower()
        if _s4._is_excluded(host, _s4.DEFAULT_EXCLUDED_SUBSTRINGS):
            continue
        if _s4._is_infrastructure_subdomain(host):
            continue
        if host in excluidos:
            continue
        reg = _s4._registered_domain(host, extract) if extract else host
        if reg in vistos:
            continue
        vistos.add(reg)
        elegiveis.append(d)
    print(f"  apos deduplicacao e exclusoes: {len(elegiveis):,}")

    if len(elegiveis) < args.n:
        print(f"ERRO: elegiveis ({len(elegiveis)}) abaixo do pedido ({args.n}).")
        return 2
    amostra = random.Random(args.semente).sample(elegiveis, args.n)
    amostra.sort(key=lambda d: (getattr(d, "rank", 0) or 0))

    saida = REPO / args.amostra
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["ordem", "rank_tranco", "dominio", "url"])
        for i, d in enumerate(amostra, 1):
            w.writerow([i, getattr(d, "rank", "") or "",
                        d.url.replace("https://", "").rstrip("/"), d.url])
    print(f"  amostra: {saida}")

    if args.so_lista:
        print(f"\nLista pronta para a fonte `csv`. Declare no protocolo:")
        print(f"  sources:")
        print(f"    - name: csv")
        print(f"      params:")
        print(f"        path: {args.amostra}")
        print(f"        sha256: {_resumo(saida)}")
        return 0

    base = yaml.safe_load((REPO / "protocols" / "padrao.yaml").read_text(encoding="utf-8"))
    proto = {
        "metadata": {
            "protocol_version": f"aovivo-{args.list_id}-v1.0.0",
            "description": (f"Validacao tecnica do caminho de coleta: {args.n} dominios "
                            f".br da lista Tranco {args.list_id}, semente {args.semente}. "
                            f"NAO integra a amostra do trabalho.")},
        "override_domains": [d.url for d in amostra],
        "repository": {"name": "filesystem", "params": {"base_path": "data/aovivo/"}},
        "fetcher": base["fetcher"],
        "tests": base["tests"],
        "result_store": {"name": "sqlite",
                         "params": {"db_path": "data/aovivo/results.sqlite"}},
        "outputs": [{"name": n, "params": {"path": f"data/aovivo/{a}"}}
                    for n, a in (("csv", "resultados.csv"),
                                 ("csv_largo", "resultados_largo.csv"),
                                 ("csv_evidencias", "evidencias.csv"),
                                 ("parquet", "resultados.parquet"),
                                 ("json", "resultados.json"))],
    }
    cab = (f"# =============================================================================\n"
           f"# VALIDACAO TECNICA DO CAMINHO DE COLETA — NAO E AMOSTRA DO TRABALHO\n"
           f"#\n"
           f"# {args.n} dominios .br sorteados da lista Tranco {args.list_id} "
           f"(top {args.top_n:,}),\n"
           f"# semente {args.semente}. Reproduzivel por:\n"
           f"#   python scripts/amostrar_ao_vivo.py --list-id {args.list_id} "
           f"--n {args.n} --semente {args.semente}\n"
           f"#\n"
           f"# O quadro amostral e OUTRO: os protocolos do trabalho usam as listas 43Z8X e\n"
           f"# 74NJX. Misturar as observacoes produziria conjunto com tres quadros e nenhum\n"
           f"# desenho declarado. Esta coleta demonstra que o arcabouco executa de ponta a\n"
           f"# ponta com as variaveis supervisionadas, e nada alem disso.\n"
           f"# =============================================================================\n")
    p = REPO / args.protocolo
    p.write_text(cab + yaml.safe_dump(proto, allow_unicode=True, sort_keys=False),
                 encoding="utf-8")
    print(f"  protocolo: {p}\n")
    print(f"Execute com:\n  privacyscope run {args.protocolo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
