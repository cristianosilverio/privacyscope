# -*- coding: utf-8 -*-
"""Reune os manifestos de custodia em diretorio versionado.

A evidencia bruta permanece fora do repositorio por volume — cerca de 5 GB — e
por reunir conteudo integral de sitios de terceiros. A integridade da coleta,
contudo, precisa ser verificavel por quem examine o trabalho. Os manifestos
cumprem esse papel: registram, para cada captura, o endereco de origem, o resumo
criptografico SHA-256 do pacote, o identificador da execucao, o carimbo de tempo
e o resumo da versao do protocolo, em conformidade com a ISO/IEC 27037 quanto a
preservacao de evidencia digital.

Verificou-se por varredura que os manifestos e os registros de auditoria nao
contem enderecos de correio eletronico nem numeros de telefone. As sequencias
numericas que uma expressao regular de telefone chega a assinalar sao trechos de
digitos internos aos proprios resumos criptograficos.

Os arquivos sao COPIADOS para data/manifests/ em vez de mantidos no local de
origem porque o git nao readmite arquivo cujo diretorio ascendente esteja
excluido; a negacao de padrao seria silenciosamente ineficaz.

Uso:
    python scripts/publicar_manifestos.py
    python scripts/publicar_manifestos.py --conferir
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DESTINO = REPO / "data" / "manifests"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def coletar():
    """Manifestos e registros de auditoria, com o lote inferido do caminho."""
    achados = []
    for padrao in ("manifest.jsonl", "audit_log.jsonl"):
        for origem in sorted((REPO / "data").rglob(padrao)):
            if DESTINO in origem.parents:
                continue
            rel = origem.relative_to(REPO / "data")
            lote = "__".join(rel.parts[:-1]) or "raiz"
            achados.append((origem, f"{lote}__{origem.name}"))
    return achados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conferir", action="store_true",
                    help="apenas relata, sem escrever")
    args = ap.parse_args()

    DESTINO.mkdir(parents=True, exist_ok=True)
    achados = coletar()
    total_reg = 0
    indice = []

    for origem, nome in achados:
        texto = origem.read_text(encoding="utf-8", errors="replace")
        if EMAIL.search(texto):
            raise SystemExit(f"ABORTADO: {origem} contem endereco de correio")
        n = sum(1 for l in texto.splitlines() if l.strip())
        total_reg += n
        alvo = DESTINO / nome
        if not args.conferir:
            shutil.copy2(origem, alvo)
        indice.append({"arquivo": nome,
                       "origem": str(origem.relative_to(REPO)).replace("\\", "/"),
                       "registros": n,
                       "sha256": hashlib.sha256(origem.read_bytes()).hexdigest()})
        print(f"  {nome:44} {n:5} registros")

    if not args.conferir:
        (DESTINO / "INDICE.json").write_text(
            json.dumps(indice, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n{len(achados)} arquivos, {total_reg} registros de custodia")
    print("nenhum endereco de correio eletronico detectado")
    if args.conferir:
        print("modo de conferencia: nada foi escrito")
    else:
        print(f"destino: {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
