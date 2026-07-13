# -*- coding: utf-8 -*-
"""Testes da selecao de URLs de PDF de politica a partir do HTML armazenado.

Cobre os tres modos de falha que faziam o PDF da politica escapar do download
na coleta b9 (dominantes em sitios publicos, que publicam a politica como
documento formal em PDF):
  (a) link .pdf SOLTO na pagina (nunca vira "subpagina categorizada");
  (b) URL RELATIVA (precisa ser resolvida contra a base do dominio);
  (c) HOST EXTERNO (politica hospedada em storage de terceiros).

A funcao e PURA (sem rede), portanto testavel de forma deterministica.
"""
from __future__ import annotations

from privacyscope.fetchers._pdf import (
    select_policy_pdf_urls,
    select_policy_pdf_urls_from_html,
)

BASE = "https://cbm.sc.gov.br"


def test_resolve_url_relativa():
    """(b) href relativo deve virar URL absoluta contra a base."""
    html = {"/": b'<a href="/images/PDF/Politica_de_Protecao_de_Dados.pdf">Politica</a>'}
    out = select_policy_pdf_urls_from_html(html, BASE)
    assert out == [f"{BASE}/images/PDF/Politica_de_Protecao_de_Dados.pdf"]


def test_aceita_host_externo():
    """(c) politica hospedada fora do dominio deve ser aceita."""
    url = "https://bkpsitecpsnew.blob.core.windows.net/x/Aviso_Privacidade.pdf"
    html = {"/": f'<a href="{url}">Aviso de Privacidade</a>'.encode()}
    assert select_policy_pdf_urls_from_html(html, "https://cps.sp.gov.br") == [url]


def test_link_solto_em_subpagina_conta():
    """(a) link .pdf dentro de qualquer pagina armazenada, nao so na home."""
    html = {
        "/": b"<a href='/sobre'>Sobre</a>",
        "/acesso-a-informacao": b'<a href="/doc/politica-privacidade.pdf">Politica</a>',
    }
    out = select_policy_pdf_urls_from_html(html, BASE)
    assert out == [f"{BASE}/doc/politica-privacidade.pdf"]


def test_qualifica_pelo_texto_da_ancora():
    """URL sem palavra-chave, mas ancora diz 'Politica de Privacidade' -> conta."""
    html = {"/": b'<a href="/arquivos/doc_2024_07.pdf">Politica de Privacidade</a>'}
    assert select_policy_pdf_urls_from_html(html, BASE) == [f"{BASE}/arquivos/doc_2024_07.pdf"]


def test_ignora_pdf_nao_relacionado_a_politica():
    """PDF sem vinculo com politica (edital, cartilha de licitacao) e ignorado."""
    html = {"/": b'<a href="/docs/edital_licitacao.pdf">Edital de licitacao</a>'}
    assert select_policy_pdf_urls_from_html(html, BASE) == []


def test_ignora_nao_pdf():
    """Link de politica em HTML (nao-PDF) nao entra nesta fonte."""
    html = {"/": b'<a href="/politica-de-privacidade">Politica de Privacidade</a>'}
    assert select_policy_pdf_urls_from_html(html, BASE) == []


def test_deduplica_e_respeita_teto():
    """Mesma URL em paginas diferentes entra uma vez; max_urls limita."""
    a = b'<a href="/p/politica-privacidade.pdf">Politica</a>'
    html = {"/": a, "/contato": a, "/sobre": b'<a href="/p/lgpd_aviso.pdf">LGPD</a>'}
    assert len(select_policy_pdf_urls_from_html(html, BASE)) == 2
    assert len(select_policy_pdf_urls_from_html(html, BASE, max_urls=1)) == 1


def test_html_vazio_ou_malformado_nao_levanta():
    """Degradacao graciosa: HTML quebrado nao pode derrubar a coleta."""
    assert select_policy_pdf_urls_from_html({}, BASE) == []
    assert select_policy_pdf_urls_from_html({"/": b""}, BASE) == []
    assert select_policy_pdf_urls_from_html({"/": b"<a href=<<>politica.pdf"}, BASE) == []


def test_fonte_1_intacta_contrato_preservado():
    """A funcao antiga (subpage_selection) mantem assinatura e semantica."""
    sel = {"politica_privacidade": [{"url": "https://x.gov.br/pol.pdf"}, {"url": "https://x.gov.br/p"}]}
    assert select_policy_pdf_urls(sel) == ["https://x.gov.br/pol.pdf"]


# ---------------------------------------------------------------------------
# Filtro de qualificacao: o PDF precisa ser a politica de privacidade DO SITIO.
# Casos extraidos do dry-run real sobre a coleta b9 — todos eram falsos
# positivos que poluiriam a evidencia e, pior, poderiam induzir o anotador a
# rotular com base em documento de terceiro.
# ---------------------------------------------------------------------------

def _sel(href, texto=""):
    html = {"/": f'<a href="{href}">{texto}</a>'.encode()}
    return select_policy_pdf_urls_from_html(html, BASE)


def test_rejeita_politica_publica_nao_de_privacidade():
    """'politica' sozinho nao basta: politica nacional do idoso NAO e privacidade."""
    assert _sel("/uploads/politica-nacional-do-idoso.pdf", "Politica Nacional do Idoso") == []
    assert _sel("/uploads/politica_de_compras.pdf", "Politica de Compras") == []
    assert _sel("/uploads/politica-sustentabilidade.pdf", "Sustentabilidade") == []


def test_rejeita_material_de_referencia_de_terceiros():
    """Guias da ANPD/CGU e cartilhas sao apoio, nunca a politica do sitio."""
    assert _sel("https://www.gov.br/anpd/guia_da_atuacao_do_encarregado_anpd.pdf", "Guia") == []
    assert _sel("https://www.cge.pr.gov.br/cartilha_LGPD_2025.pdf", "Cartilha LGPD") == []
    assert _sel("/docs/manual_de_implementacao_da_lgpd.pdf", "Manual") == []
    assert _sel("/docs/E-Book-Lei-Geral-de-Protecao-de-Dados.pdf", "E-book") == []


def test_rejeita_politica_de_privacidade_de_terceiro_conhecido():
    """Politica do Google/Adobe linkada no rodape nao e a politica do sitio."""
    assert _sel("https://www.gstatic.com/policies/privacy/pdf/google_privacy_policy.pdf") == []
    assert _sel("https://www.adobe.com/legal/Magento_Security_Privacy_Guide.pdf") == []


def test_normaliza_href_com_barra_invertida():
    """href malformado (observado em pcd.com.br) precisa virar URL valida."""
    out = _sel(r"/\public\privacidade-termos\politica-privacidade.pdf")
    assert out == [f"{BASE}/public/privacidade-termos/politica-privacidade.pdf"]


def test_aceita_politica_do_sitio_ainda_que_em_host_externo():
    """Politica propria hospedada em storage de terceiro deve ser aceita."""
    u = "https://anpad.blob.core.windows.net/files/politica_privacidade_v1.pdf"
    assert _sel(u, "Politica de Privacidade") == [u]
