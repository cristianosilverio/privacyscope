# -*- coding: utf-8 -*-
"""Extracao de texto de PDFs de politica (camada de texto + OCR de reserva) e
selecao das URLs de PDF a baixar.

Usado pela camada de Coleta (FallbackChain) para anexar o PDF da politica a
``RawEvidence.pdf_documents`` — de modo que, em coletas novas, o PDF viaja
DENTRO do mesmo pacote de evidencia (tar.gz) e sob o MESMO hash de custodia.

Estrategia de extracao:
1. Camada de texto nativa do PDF via PyMuPDF (rapido, fiel).
2. Se o texto for insuficiente (PDF escaneado/imagem), OCR das paginas
   renderizadas via pytesseract (Tesseract). Idioma padrao 'por'.

Estrategia de selecao (duas fontes complementares, uniao):
- ``select_policy_pdf_urls``: le do ``subpage_selection`` (subpaginas que a
  descoberta CATEGORIZOU). Cobre o caso em que a propria subpagina e um .pdf.
- ``select_policy_pdf_urls_from_html``: varre os ``<a href="...pdf">`` SOLTOS
  dentro do HTML armazenado. Cobre o padrao dominante em sitios publicos, que
  publicam a politica como documento formal (Portaria/Resolucao/Ato) em PDF
  referenciado por um link comum — que nunca vira "subpagina categorizada".
  Resolve URLs relativas contra a base e aceita host externo (e.g., a politica
  hospedada em storage de terceiros).

Dependencias: pymupdf (obrigatoria); pytesseract + Tesseract com o pacote de
idioma 'por' (tesseract-ocr-por) para o OCR. Sem OCR disponivel, retorna o que a
camada de texto fornecer (degradacao graciosa; nunca levanta).
"""
from __future__ import annotations

import io
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

try:
    import fitz  # PyMuPDF
    _HAVE_FITZ = True
except Exception:
    _HAVE_FITZ = False

try:
    import pytesseract
    from PIL import Image
    _HAVE_OCR = True
except Exception:
    _HAVE_OCR = False


def _resolve_lang(lang):
    try:
        avail = set(pytesseract.get_languages(config=""))
    except Exception:
        return lang
    want = [l for l in lang.split("+") if l in avail] or [l for l in ("por", "eng") if l in avail]
    return "+".join(want) or "eng"


def extract_pdf_text(data, *, lang="por", min_text_chars=200, ocr_dpi=200, max_pages=40):
    """Extrai texto de ``data`` (bytes de PDF). Retorna (texto, metodo) com
    metodo em {'text_layer','ocr','empty'}. Nunca levanta."""
    if not _HAVE_FITZ:
        return "", "empty"
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return "", "empty"
    parts = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        try:
            parts.append(page.get_text())
        except Exception:
            pass
    text = "\n".join(parts).strip()
    if len(text) >= min_text_chars:
        return text, "text_layer"
    if not _HAVE_OCR:
        return (text, "text_layer") if text else ("", "empty")
    langs = _resolve_lang(lang)
    ocr_parts = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        try:
            pix = page.get_pixmap(dpi=ocr_dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            try:
                ocr_parts.append(pytesseract.image_to_string(img, lang=langs))
            except Exception:
                ocr_parts.append(pytesseract.image_to_string(img))
        except Exception:
            pass
    ocr_text = "\n".join(ocr_parts).strip()
    if len(ocr_text) > len(text):
        return ocr_text, "ocr"
    if text:
        return text, "text_layer"
    return (ocr_text, "ocr") if ocr_text else ("", "empty")


def select_policy_pdf_urls(subpage_selection, categories=(
    "politica_privacidade", "encarregado", "canal_titular", "termos_uso",
)):
    """Seleciona URLs .pdf das categorias de subpagina relevantes a politica.
    Pura (sem rede): decide quais PDFs baixar. Retorna lista deduplicada.

    Fonte 1 de 2. Cobre o caso em que a SUBPAGINA descoberta ja e o proprio
    .pdf. Nao cobre links .pdf soltos dentro das paginas — para isso existe
    ``select_policy_pdf_urls_from_html``.
    """
    urls = []
    for cat in categories:
        for item in (subpage_selection or {}).get(cat, []) or []:
            u = (item or {}).get("url", "") or ""
            base = u.split("?")[0].split("#")[0]
            if base.lower().endswith(".pdf") and u not in urls:
                urls.append(u)
    return urls


# --- Qualificacao de um PDF como candidato a POLITICA DE PRIVACIDADE DO SITIO ---
#
# Tres filtros, nesta ordem. O objetivo e trazer a politica do PROPRIO sitio e
# NAO poluir a evidencia com documentos de terceiros — o que, alem de desperdicio,
# e risco de rotulagem: o anotador pode rotular com base na politica alheia
# (caso ja observado: politica da Cloudflare capturada como se fosse do sitio).

# (1) POSITIVO — o documento precisa ser especificamente sobre privacidade /
# protecao de dados. "politica" sozinho NAO basta: casaria com "politica
# nacional do idoso", "politica de compras", "politica de qualidade",
# "politica de sustentabilidade", "politicas publicas" etc.
_PRIVACY_KW = re.compile(
    r"(privacidad|privacy|prote[c\u00e7][a\u00e3]o[\s_%+.\-]*de[\s_%+.\-]*dados"
    r"|lgpd|dados[\s_%+.\-]*pessoa|aviso[\s_%+.\-]*de[\s_%+.\-]*privac"
    r"|encarregad|\bdpo\b)",
    re.IGNORECASE,
)

# (2) NEGATIVO — material de REFERENCIA/EDUCATIVO. Guias da ANPD/CGU/CGE,
# cartilhas, manuais e e-books sao publicados por terceiros e linkados como
# apoio; nunca sao a politica do sitio.
_REFERENCE_KW = re.compile(
    r"(guia|cartilha|manual|e-?book|apresenta|boas[\s_%+.\-]*pr[a\u00e1]ticas"
    r"|gloss[a\u00e1]rio|cartaz|folder|curso|treinamento|palestra"
    r"|pol[i\u00ed]tica[\s_%+.\-]*nacional|pol[i\u00ed]ticas[\s_%+.\-]*p[u\u00fa]blicas)",
    re.IGNORECASE,
)

# (3) NEGATIVO — hosts de politica de TERCEIROS (nunca a do sitio analisado).
_THIRD_PARTY_HOST = re.compile(r"(gstatic\.com|\.adobe\.com)", re.IGNORECASE)


def _normaliza_href(href: str) -> str:
    """Normaliza href malformado com barra invertida (observado em pcd.com.br:
    'https://x/\\public\\privacidade-termos\\pol.pdf').

    ARMADILHA: apos trocar '\\' por '/', um href como '/\\public' vira '//public',
    que urljoin trata como URL PROTOCOLO-RELATIVA e SEQUESTRA o host — o
    download iria para 'https://public/...'. Por isso colapsamos as barras
    iniciais, mas somente quando o href original NAO era protocolo-relativo
    ('//cdn.exemplo.com/x.pdf' e legitimo e deve ser preservado).
    """
    if "\\" not in href:
        return href
    protocolo_relativo = href.startswith("//")
    out = href.replace("\\", "/")
    if not protocolo_relativo:
        out = re.sub(r"^/{2,}", "/", out)
    return out


def _qualifica_pdf_politica(href: str, texto: str) -> bool:
    """True se o PDF e candidato plausivel a politica de privacidade DO SITIO."""
    alvo = f"{href} {texto or ''}"
    if not _PRIVACY_KW.search(alvo):
        return False
    if _REFERENCE_KW.search(alvo):
        return False
    if _THIRD_PARTY_HOST.search(href):
        return False
    return True


class _AnchorCollector(HTMLParser):
    """Coleta pares (href, texto_da_ancora) do HTML. Tolerante a HTML malformado."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self._href = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.anchors.append((self._href, " ".join(self._buf).strip()))
            self._href = None
            self._buf = []


def select_policy_pdf_urls_from_html(html_pages, base_url, *, max_urls=8):
    """Seleciona URLs de PDF de politica varrendo o HTML ARMAZENADO.

    Fonte 2 de 2 (complementar a ``select_policy_pdf_urls``). Motivacao: em
    sitios publicos a politica costuma ser um documento formal (Portaria,
    Resolucao, Ato) publicado em PDF e referenciado por um ``<a href>`` comum
    dentro de uma pagina — que nunca e categorizado como subpagina, e por isso
    escapava do download.

    Corrige tres modos de falha observados:
      (a) link .pdf solto dentro da pagina (nao categorizado);
      (b) URL RELATIVA (e.g. '/images/PDF/Politica_de_Protecao_de_Dados.pdf'),
          agora resolvida contra ``base_url``;
      (c) HOST EXTERNO (politica hospedada em storage de terceiros).

    Pura: nao faz rede. Args:
        html_pages: dict ``{path: bytes}`` como em ``RawEvidence.html_pages``.
        base_url: URL base do dominio (``evidence.domain.url``), usada para
            resolver hrefs relativos.
        max_urls: teto de URLs retornadas (evita explosao em portais grandes).

    Returns:
        list[str]: URLs absolutas (http/https), deduplicadas, na ordem de
        descoberta.
    """
    urls = []
    for _path, body in (html_pages or {}).items():
        if not body:
            continue
        try:
            if isinstance(body, (bytes, bytearray)):
                html = bytes(body).decode("utf-8", "ignore")
            else:
                html = str(body)
        except Exception:
            continue
        parser = _AnchorCollector()
        try:
            parser.feed(html)
        except Exception:
            pass
        for href, text in parser.anchors:
            if not href:
                continue
            href = _normaliza_href(href)
            path = href.split("?")[0].split("#")[0]
            if not path.lower().endswith(".pdf"):
                continue
            if not _qualifica_pdf_politica(href, text):
                continue
            try:
                # hrefs malformados com barra invertida (observado em pcd.com.br:
                # 'https://x/\\public\\privacidade-termos\\pol.pdf') quebram o download.
                absolute = urljoin(base_url or "", href)
            except Exception:
                continue
            if not absolute.lower().startswith(("http://", "https://")):
                continue
            if absolute not in urls:
                urls.append(absolute)
                if len(urls) >= max_urls:
                    return urls
    return urls


__all__ = [
    "extract_pdf_text",
    "select_policy_pdf_urls",
    "select_policy_pdf_urls_from_html",
]
