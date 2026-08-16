# -*- coding: utf-8 -*-
"""O detector de politica precisa ler o PDF colhido pelo enriquecimento.

O laco sobre `subpage_selection` so alcanca o documento que a PROPRIA raiz linka.
Politica em segundo nivel, ou em rede de distribuicao de outro hospedeiro, e
encontrada pelo enriquecimento e guardada em `evidence.pdf_documents` — campo que
este teste nao lia. O efeito era o pior possivel: documento integro no pacote de
evidencia e veredito `false` com confianca alta.
"""
from datetime import datetime, timezone

import pytest

from privacyscope.core.types import Domain, RawEvidence
from privacyscope.tests.politica_privacidade import PoliticaPrivacidadeTest

# Medido nos PDFs reais em 16/08/2026: cebraspe 16 termos, itaucultural 15,
# enel 14; o PDF de "Termos e Condicoes de Uso" de mevo.com.br, 2.
POLITICA = ("lgpd lei geral de proteção de dados dados pessoais titular "
            "encarregado finalidade base legal tratamento de dados anpd")
TERMOS = "consentimento das partes e finalidade do contrato de uso da plataforma"


def _ev(pdfs=None, candidatas=(), paginas=None):
    return RawEvidence(
        domain=Domain(url="https://x.br", tld=".br", source_name="t"),
        html_pages=paginas or {"/": b"<html><body>portal</body></html>"},
        cookies_by_phase={}, headers={}, screenshot=None, phase_screenshots={},
        network_log=[],
        subpage_selection={"politica_privacidade": [
            {"url": u, "matched_pattern": "p", "matched_against": "text", "snippet": ""}
            for u in candidatas]},
        consent_actions=[], fetcher_name="http_simples",
        timestamp_utc=datetime.now(timezone.utc), errors=[],
        pdf_documents=pdfs or {})


def _avalia(ev, params=None):
    return PoliticaPrivacidadeTest().evaluate(
        ev, params or {}, protocol_version="t", run_id="r")


@pytest.fixture
def extracao(monkeypatch):
    """Substitui a extracao para que o teste nao dependa de PyMuPDF nem de OCR."""
    chamadas = []

    def falsa(dados, **kw):
        chamadas.append(kw)
        return dados.decode("utf-8"), "text_layer"

    monkeypatch.setattr("privacyscope.fetchers._pdf.extract_pdf_text", falsa)
    return chamadas


def test_pdf_com_conteudo_de_politica_qualifica(extracao):
    r = _avalia(_ev({"https://cdn.x.br/Politica-de-Privacidade.pdf": POLITICA.encode()}))
    assert r.value is True
    assert r.audit_trail["source"] == "pdf_enriquecido+content_qualified"
    assert r.audit_trail["matched_url"].endswith("Politica-de-Privacidade.pdf")
    assert r.audit_trail["matched_against"].startswith("pdf:")
    assert r.confidence >= 0.9


def test_pdf_de_termos_de_uso_nao_qualifica(extracao):
    """Caso real de mevo.com.br. O corte que ja vigora para hipertexto separa
    documento de termos de politica de privacidade sem ajuste algum — e fixa-lo
    aqui impede que alguem afrouxe o corte sem perceber o que esta afrouxando."""
    r = _avalia(_ev({"https://x.br/Termos-e-Condicoes-de-Uso.pdf": TERMOS.encode()}))
    assert r.value is False
    assert r.audit_trail["source"] == "no_match_any_source"


def test_digitalizacao_sem_texto_cai_no_degrau_por_url(monkeypatch):
    monkeypatch.setattr("privacyscope.fetchers._pdf.extract_pdf_text",
                        lambda dados, **kw: ("", "empty"))
    r = _avalia(_ev({"https://x.br/politica-de-privacidade.pdf": b"%PDF-scan"}))
    assert r.value is True
    assert r.audit_trail["source"] == "pdf_enriquecido+policy_like_url"
    assert r.audit_trail["confidence_label"] != "high", (
        "sem camada de texto, a decisao e pelo nome do arquivo e nao pelo conteudo")


def test_digitalizacao_sem_texto_e_sem_nome_de_politica_nao_qualifica(monkeypatch):
    monkeypatch.setattr("privacyscope.fetchers._pdf.extract_pdf_text",
                        lambda dados, **kw: ("", "empty"))
    r = _avalia(_ev({"https://x.br/edital-2022.pdf": b"%PDF-scan"}))
    assert r.value is False


def test_ocr_desligado_por_omissao(extracao):
    """Este detector roda sobre TODO sitio da amostra, inclusive os sem politica.
    Reconhecimento optico no caminho quente encareceria a execucao de massa."""
    _avalia(_ev({"https://x.br/p.pdf": POLITICA.encode()}))
    assert extracao and extracao[0]["permitir_ocr"] is False
    extracao.clear()
    _avalia(_ev({"https://x.br/p.pdf": POLITICA.encode()}), {"ocr_pdf": True})
    assert extracao[0]["permitir_ocr"] is True


def test_hipertexto_que_qualifica_dispensa_o_pdf(extracao):
    """O ramo so roda quando a busca em hipertexto nao concluiu positivo."""
    corpo = ("<html><body>" + POLITICA * 30 + "</body></html>").encode()
    ev = _ev({"https://x.br/qualquer.pdf": TERMOS.encode()},
             candidatas=["https://x.br/privacidade"],
             paginas={"/": b"<html>raiz</html>", "/privacidade": corpo})
    r = _avalia(ev)
    assert r.value is True
    assert r.audit_trail["source"].startswith("subpage_selection")
    assert extracao == [], "nao deveria ter aberto PDF algum"


def test_contagem_de_pdfs_vai_para_a_auditoria(extracao):
    r = _avalia(_ev({"https://x.br/a.pdf": TERMOS.encode(),
                     "https://x.br/b.pdf": TERMOS.encode()}))
    assert r.audit_trail["pdf_documents_count"] == 2
