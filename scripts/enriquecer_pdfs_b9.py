# -*- coding: utf-8 -*-
"""Enriquecimento da coleta b9 com os PDFs de politica referenciados na evidencia.

Sitios institucionais, sobretudo no setor publico, publicam a politica como
documento formal — Portaria, Resolucao, Ato — em PDF referenciado por um ``<a
href>`` comum dentro de uma pagina. Tais links nao sao categorizados como
subpagina, e por isso escapavam ao download na coleta original. A correcao no
framework consta de ``fetchers/_pdf.py`` e ``fetchers/fallback_chain.py``; este
script remedia a coleta ja realizada, sem recoleta.

Preservacao da cadeia de custodia. Os tarballs de ``data/b9/raw`` estao sob
custodia: cada um possui SHA-256 registrado em ``manifest.jsonl`` e conferido por
``manifest_audit.verify_manifest()``. Gravar os PDFs no interior dos tarballs
invalidaria todos os hashes. O procedimento adotado, portanto:

  * nao escreve nos tarballs originais, abertos em modo leitura;
  * verifica a integridade da colecao antes de qualquer operacao;
  * grava os PDFs em arvore propria (``data/b9/pdf_enrichment/``), com manifest e
    hashes proprios, cada entrada referenciando o hash da evidencia de origem.

O original permanece byte-identico e verificavel, e o enriquecimento constitui
derivado datado, hasheado e rastreavel: consigna-se que determinado PDF foi
obtido em certa data a partir de link presente em evidencia de hash conhecido. O
procedimento observa a ABNT NBR ISO/IEC 27037 e Casey (2011) quanto a nao alterar
o original e produzir derivado documentado.

O script e transitorio. Em coletas posteriores o problema nao se coloca: o
fetcher corrigido anexa o PDF a ``RawEvidence.pdf_documents`` e o
``FileSystemRepository`` o serializa no proprio tar.gz, sob o mesmo hash do
pacote — um unico artefato, uma unica custodia.

Execucao retomavel: sitios ja enriquecidos sao ignorados.

Uso:
    python scripts/enriquecer_pdfs_b9.py --dry-run
    python scripts/enriquecer_pdfs_b9.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from privacyscope.fetchers._pdf import (  # noqa: E402  (apos sys.path)
    extract_pdf_text,
    select_policy_pdf_urls,
    select_policy_pdf_urls_from_html,
)

UA = "PrivacyScope-Research/1.0 (+pesquisa academica; TCC MBA USP/ESALQ)"
MAX_BYTES = 10_000_000
TIMEOUT = 30.0


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ler_evidencia(tar_path: Path):
    """Le o tarball em modo leitura, sem escrita. Devolve (html_pages,
    subpage_selection), com html_pages no formato de RawEvidence.html_pages."""
    html_pages: dict[str, bytes] = {}
    subpage_selection: dict = {}
    index: dict = {}
    with tarfile.open(tar_path, "r:gz") as tf:
        for m in tf.getmembers():
            n = m.name
            if n.endswith("/html_root.html"):
                html_pages["/"] = tf.extractfile(m).read()
            elif n.endswith("/meta.json"):
                try:
                    meta = json.load(tf.extractfile(m))
                    subpage_selection = meta.get("subpage_selection") or {}
                except Exception:
                    pass
            elif n.endswith("/_index.json"):
                try:
                    index = json.load(tf.extractfile(m))
                except Exception:
                    pass
            elif "/html_subpages/" in n and n.endswith(".html"):
                html_pages.setdefault(os.path.basename(n), tf.extractfile(m).read())
    # rechaveia subpaginas pelo path real quando o _index permite
    if index:
        rekeyed: dict[str, bytes] = {"/": html_pages.get("/", b"")}
        for fname, body in html_pages.items():
            if fname == "/":
                continue
            stem = fname[:-5] if fname.endswith(".html") else fname
            rekeyed[index.get(stem, fname)] = body
        html_pages = rekeyed
    return html_pages, subpage_selection


def main() -> int:
    ap = argparse.ArgumentParser(description="Enriquece a evidencia b9 com os PDFs de politica (append-only).")
    ap.add_argument("--data", default="data/b9", help="diretorio da coleta (default: data/b9)")
    ap.add_argument("--dry-run", action="store_true", help="apenas lista os PDFs que baixaria")
    ap.add_argument("--skip-verify", action="store_true", help="pula a verificacao de integridade (nao recomendado)")
    args = ap.parse_args()

    data_dir = (REPO / args.data).resolve()
    raw_dir = data_dir / "raw"
    manifest_path = raw_dir / "manifest.jsonl"
    out_dir = data_dir / "pdf_enrichment"
    out_manifest = out_dir / "manifest.jsonl"

    if not manifest_path.exists():
        print(f"ERRO: manifest nao encontrado em {manifest_path}")
        return 2

    # 1) Integridade da colecao original, previamente a qualquer operacao.
    if not args.skip_verify:
        from privacyscope.storage.manifest_audit import verify_manifest
        print("Verificando integridade da evidencia original...")
        rep = verify_manifest(data_dir)
        # ManifestAuditReport expoe contagens inteiras; all_valid e property.
        print(
            f"  total={rep.total_entries} verificadas={rep.verified} "
            f"ausentes={rep.missing} corrompidas={rep.corrupted}"
        )
        if rep.corrupted:
            print("ERRO: ha evidencias CORROMPIDAS (sha256 divergente). Abortando —")
            print("      nao se enriquece uma cadeia de custodia quebrada.")
            for tar, desc in (rep.problems or [])[:10]:
                print(f"      - {tar}: {desc}")
            return 3
        if rep.missing:
            print(f"  AVISO: {rep.missing} entrada(s) do manifest sem arquivo em disco; serao puladas.")
        # A property all_valid exige tambem audit_log_consistent, que pode ser
        # falso por motivos alheios a adulteracao. O criterio de aborto e a
        # existencia de tarball corrompido entre os que serao lidos.

    entradas = [json.loads(l) for l in manifest_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Evidencias no manifest: {len(entradas)}")

    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        import httpx  # so precisa de rede quando nao e dry-run

    feitos = ja = baixados = falhas = 0
    linhas_manifest: list[str] = []

    client = None
    if not args.dry_run:
        client = httpx.Client(follow_redirects=True, timeout=TIMEOUT, headers={"User-Agent": UA})

    try:
        for e in entradas:
            tar_name = e.get("tar_filename")
            origin_sha = e.get("sha256")
            base_url = (e.get("domain_url") or "").strip()
            host = base_url.split("://")[-1].strip("/")
            tar_path = raw_dir / tar_name
            if not tar_path.exists():
                continue

            site_dir = out_dir / host
            if site_dir.exists() and (site_dir / "meta.json").exists():
                ja += 1
                continue

            try:
                html_pages, subsel = ler_evidencia(tar_path)
            except Exception as ex:
                print(f"  [ERRO] {host}: leitura do tarball ({type(ex).__name__})")
                falhas += 1
                continue

            # 2) Selecao pela mesma funcao pura do fetcher, fonte unica de verdade.
            from urllib.parse import urljoin
            urls: list[str] = []
            for u in select_policy_pdf_urls(subsel):
                a = urljoin(base_url, u) if base_url else u
                if a not in urls:
                    urls.append(a)
            for u in select_policy_pdf_urls_from_html(html_pages, base_url):
                if u not in urls:
                    urls.append(u)
            urls = urls[:8]
            if not urls:
                continue

            if args.dry_run:
                print(f"  {host}: {len(urls)} pdf(s)")
                for u in urls:
                    print(f"      {u}")
                feitos += 1
                continue

            # 3) Download e extracao de texto.
            docs = []
            for i, u in enumerate(urls, start=1):
                try:
                    r = client.get(u)
                    body = r.content
                    ct = (r.headers.get("content-type") or "").lower()
                    is_pdf = ("pdf" in ct) or u.split("?")[0].lower().endswith(".pdf")
                    if r.status_code != 200 or not is_pdf or not (0 < len(body) <= MAX_BYTES):
                        print(f"      [skip] {u} status={r.status_code} ct={ct} bytes={len(body)}")
                        continue
                    texto, metodo = extract_pdf_text(body)
                    site_dir.mkdir(parents=True, exist_ok=True)
                    pdf_name = f"doc_{i:03d}.pdf"
                    txt_name = f"doc_{i:03d}.txt"
                    (site_dir / pdf_name).write_bytes(body)
                    (site_dir / txt_name).write_text(texto or "", encoding="utf-8")
                    docs.append({
                        "arquivo_pdf": pdf_name,
                        "arquivo_txt": txt_name,
                        "source_url": u,
                        "sha256_pdf": sha256_bytes(body),
                        "bytes": len(body),
                        "metodo_extracao": metodo,          # text_layer | ocr | empty
                        "chars_texto": len(texto or ""),
                    })
                    baixados += 1
                    print(f"      [ok] {u} ({len(body)}B, {metodo}, {len(texto or '')} chars)")
                except Exception as ex:
                    print(f"      [err] {u}: {type(ex).__name__}")

            if not docs:
                continue

            # 4) Custodia do derivado, com referencia explicita ao original.
            meta = {
                "host": host,
                "domain_url": base_url,
                "origin_tar": tar_name,
                "origin_sha256": origin_sha,          # vinculo com o original imutavel
                "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                "selector_version": "select_policy_pdf_urls_from_html/1.0",
                "documentos": docs,
            }
            (site_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            linhas_manifest.append(json.dumps({
                "host": host,
                "origin_tar": tar_name,
                "origin_sha256": origin_sha,
                "n_documentos": len(docs),
                "sha256_meta": sha256_bytes((site_dir / "meta.json").read_bytes()),
                "created_at": meta["downloaded_at_utc"],
            }, ensure_ascii=False))
            feitos += 1
            print(f"  [{host}] {len(docs)} pdf(s) enriquecido(s)")
    finally:
        if client is not None:
            client.close()

    if linhas_manifest:
        with out_manifest.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(linhas_manifest) + "\n")

    print("\n" + "=" * 60)
    if args.dry_run:
        print(f"DRY-RUN: {feitos} sitio(s) teriam PDF baixado.")
    else:
        print(f"Sitios enriquecidos: {feitos} | PDFs baixados: {baixados} | ja feitos: {ja} | falhas: {falhas}")
        print(f"Saida: {out_dir}")
        print(f"Manifest do derivado: {out_manifest}")
        print("Os originais em data/*/raw permanecem inalterados; os hashes seguem validos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
