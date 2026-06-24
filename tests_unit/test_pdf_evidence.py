# -*- coding: utf-8 -*-
"""Regressao do contrato PDF (Frente A do endurecimento de fetchers).

Cobre: campo aditivo RawEvidence.pdf_documents (backward-compat), serializacao
no storage (custodia do PDF original sob hash), round-trip put/get, selecao de
URLs .pdf para download, e extracao de texto. Primeiro teste proprio do repo.
"""
import datetime
import hashlib
from pathlib import Path

import pytest

from privacyscope.core.types import RawEvidence, Domain
from privacyscope.storage.filesystem_repo import (
    FileSystemRepository,
    _serialize_evidence_to_dir,
)
from privacyscope.fetchers._pdf import extract_pdf_text, select_policy_pdf_urls

try:
    import fitz  # PyMuPDF
    _HAVE_FITZ = True
except Exception:
    _HAVE_FITZ = False


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _make_text_pdf(text):
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in [text[i:i + 80] for i in range(0, len(text), 80)]:
        page.insert_text((72, y), line, fontsize=12)
        y += 16
    return doc.tobytes()


def _evidence_with_pdf(pdf_bytes):
    return RawEvidence(
        domain=Domain(url="https://exemplo.com.br", tld=".com.br", source_name="csv"),
        html_pages={"/": b"<html>raiz</html>", "/politica": b"<html>sub</html>"},
        pdf_documents={"https://exemplo.com.br/politica.pdf": pdf_bytes},
        fetcher_name="playwright",
        timestamp_utc=_utcnow(),
    )


def test_pdf_documents_field_default_empty():
    """Campo aditivo: ausente -> dict vazio (backward-compat)."""
    ev = RawEvidence(
        domain=Domain(url="https://x.com.br", tld=".com.br", source_name="csv"),
        fetcher_name="http_simples",
        timestamp_utc=_utcnow(),
    )
    assert ev.pdf_documents == {}


def test_serialize_keeps_pdf_out_of_meta_and_writes_file(tmp_path):
    ev = _evidence_with_pdf(b"%PDF-1.4 fake bytes")
    dest = tmp_path / "ev"
    _serialize_evidence_to_dir(ev, dest)
    meta = (dest / "meta.json").read_text(encoding="utf-8")
    assert "pdf_documents" not in meta  # bytes nunca vao para o meta.json
    pdfs = list((dest / "pdf_documents").glob("doc_*.pdf"))
    assert len(pdfs) == 1
    idx = (dest / "pdf_documents" / "_index.json").read_text(encoding="utf-8")
    assert "politica.pdf" in idx


def test_put_get_roundtrip_preserves_pdf_and_hash(tmp_path):
    ev = _evidence_with_pdf(b"%PDF-1.4 custody bytes 12345")
    repo = FileSystemRepository(base_path=tmp_path)
    ref = repo.put(ev, run_id="testrun-0001")
    on_disk = hashlib.sha256(Path(ref.path).read_bytes()).hexdigest()
    assert on_disk == ref.sha256  # custodia: hash do tar == EvidenceRef
    ev2 = repo.get(ref)
    assert ev2.pdf_documents == ev.pdf_documents
    assert ev2.html_pages == ev.html_pages
    assert ev2.fetcher_name == ev.fetcher_name


def test_select_policy_pdf_urls_filters_and_dedups():
    ss = {
        "politica_privacidade": [{"url": "https://a.com.br/politica.pdf"}],
        "termos_uso": [
            {"url": "https://a.com.br/termo.pdf"},
            {"url": "https://a.com.br/termos"},
        ],
        "encarregado": [{"url": "https://a.com.br/dpo.pdf?v=1"}],
        "canal_titular": [{"url": "https://a.com.br/portal"}],
    }
    urls = select_policy_pdf_urls(ss)
    assert sorted(urls) == [
        "https://a.com.br/dpo.pdf?v=1",
        "https://a.com.br/politica.pdf",
        "https://a.com.br/termo.pdf",
    ]


def test_select_policy_pdf_urls_empty_when_no_pdf():
    assert select_policy_pdf_urls({}) == []
    assert select_policy_pdf_urls(
        {"politica_privacidade": [{"url": "https://x/p.html"}]}
    ) == []


def test_extract_pdf_text_never_raises_on_garbage():
    text, method = extract_pdf_text(b"isto nao e um pdf")
    assert method == "empty"
    assert text == ""


@pytest.mark.skipif(not _HAVE_FITZ, reason="PyMuPDF nao instalado")
def test_extract_pdf_text_reads_text_layer():
    pdf = _make_text_pdf("POLITICA DE PRIVACIDADE conforme a LGPD. " * 8)
    text, method = extract_pdf_text(pdf)
    assert method == "text_layer"
    assert "PRIVACIDADE" in text.upper()
