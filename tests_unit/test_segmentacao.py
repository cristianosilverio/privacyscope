# -*- coding: utf-8 -*-
"""Propriedades do preparo de texto que nao podem regredir."""
from privacyscope.text.segmentacao import (  # noqa: F401
    MIN_SEG, divide_por_sentenca, em_portugues, extrai_blocos, indices_uteis,
    limpa, reconstroi_pdf, segmenta,
)

LONGO = "Tratamos os seus dados pessoais para a finalidade de entrega. "


def test_bloco_encerra_unidade():
    """Itens de lista consecutivos nao podem fundir-se: a enumeracao do art. 18
    e tipicamente marcada em lista, sem pontuacao final."""
    b = extrai_blocos(b"<ul><li>Confirmar tratamento</li><li>Acessar os dados</li></ul>")
    assert b == ["Confirmar tratamento", "Acessar os dados"]


def test_quebra_de_linha_do_codigo_fonte_nao_e_fronteira():
    """Defeito medido em 2,9% dos blocos de 33 de 70 sitios."""
    assert limpa("Usamos seus dados\n   para entrega") == "Usamos seus dados para entrega"


def test_abreviatura_nao_quebra_sentenca():
    """A guarda protege tanto a abreviatura quanto a inicial isolada: em
    "art. 6, X. Tratamos", nenhum dos dois pontos encerra periodo, e a unidade
    permanece inteira. Quebrar em "X." produziria fragmento sem sujeito."""
    assert divide_por_sentenca("Conforme o art. 6, X. Tratamos dados.") == [
        "Conforme o art. 6, X. Tratamos dados."]
    assert divide_por_sentenca("Usamos dados. Tratamos dados.") == [
        "Usamos dados.", "Tratamos dados."]


def test_separador_decimal_preservado():
    assert divide_por_sentenca("A Lei 13.709 de 2018.") == ["A Lei 13.709 de 2018."]


def test_idioma_conservador_em_texto_curto():
    """Abaixo do minimo a deteccao nao e confiavel: na duvida, preserva."""
    assert em_portugues("The privacy policy")


def test_idioma_exclui_texto_longo_em_ingles():
    assert not em_portugues(("We use your personal data and information for the "
                             "purposes of this privacy policy. ") * 8)


def test_reconstrucao_de_pdf_une_linhas_de_diagramacao():
    u = reconstroi_pdf(["Tratamos os seus dados pessoais para", "a finalidade de entrega."])
    assert u == ["Tratamos os seus dados pessoais para a finalidade de entrega."]


def test_reconstrucao_remove_cabecalho_recorrente():
    linhas = ["Politica de Privacidade", "Primeira frase da politica.",
              "Politica de Privacidade", "Segunda frase da politica.",
              "Politica de Privacidade", "Terceira frase da politica."]
    assert not any("Politica de Privacidade" in u for u in reconstroi_pdf(linhas))


def test_hifen_une_vocabulo_partido():
    assert reconstroi_pdf(["compartilha-", "mento de dados."]) == ["compartilhamento de dados."]


def test_deduplicacao_preserva_a_primeira_ocorrencia():
    u = [LONGO, "outro texto suficientemente longo para passar", LONGO]
    assert indices_uteis(u) == [0, 1]


def test_fragmento_curto_descartado():
    assert indices_uteis(["curto", LONGO]) == [1]
    assert len("curto") < MIN_SEG


def test_documento_contiguo_inclui_unidades_descartadas():
    """Filtrar antes abriria lacunas e impediria a correspondencia de trechos
    que atravessam uma unidade curta."""
    r = segmenta({"p.html": b"<p>curto</p><p>" + LONGO.encode() + b"</p>"})
    doc, iv = r.documento_contiguo()
    assert "curto" in doc
    assert all(x is not None for x in iv)


def test_pagina_em_outro_idioma_e_removida_e_reportada():
    en = ("<p>We use your personal data and information for the purposes of this "
          "privacy policy and we may share it with third parties.</p>") * 6
    r = segmenta({"pt.html": b"<p>" + (LONGO * 8).encode() + b"</p>",
                  "en.html": en.encode()})
    assert r.subpaginas_removidas == ("en.html",)
    assert r.blocos_integrais, "os blocos integrais precedem o filtro de idioma"


def test_ordem_html_antes_de_pdf():
    r = segmenta({"p.html": b"<p>" + LONGO.encode() + b"</p>"}, ["Texto vindo do PDF."])
    assert r.unidades[-1] == "Texto vindo do PDF."


def test_documento_sem_conteudo_nao_levanta():
    r = segmenta({})
    assert r.unidades == () and r.uteis == ()


def test_marcacao_interna_de_iframe_nao_vira_segmento():
    """Regressao de reprodutibilidade entre versoes do interpretador.

    `CDATA_CONTENT_ELEMENTS` do `html.parser` variou entre versoes do CPython.
    Onde `iframe` figura no conjunto, sua marcacao interna chega como TEXTO e
    vira segmento; onde nao figura, e analisada como marcacao e desaparece. O
    preparo fixa o conjunto classico para nao herdar essa variacao — e porque foi
    sob ele que o corpo de rotulagem foi construido e marcado.
    """
    html = (b'<div><iframe src="https://x/y"><span class="fr-mk" '
            b'style="display: none;">&nbsp;</span> </iframe></div>')
    assert extrai_blocos(html) == []


def test_texto_legitimo_em_iframe_e_preservado():
    """Descartar todo o conteudo de iframe seria um terceiro comportamento,
    distinto dos dois que os interpretadores exibem, e suprimiria texto."""
    assert extrai_blocos(b"<iframe>Texto alternativo do quadro.</iframe>") == [
        "Texto alternativo do quadro."]


def test_conjunto_de_texto_puro_e_declarado_e_nao_herdado():
    from html.parser import HTMLParser
    from privacyscope.text.segmentacao import VisBloco
    assert VisBloco.CDATA_CONTENT_ELEMENTS == ("script", "style")
    assert "CDATA_CONTENT_ELEMENTS" in vars(VisBloco), "precisa ser declarado na classe"
    del HTMLParser
