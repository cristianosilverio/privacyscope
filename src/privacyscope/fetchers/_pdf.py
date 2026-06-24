# -*- coding: utf-8 -*-
"""Extracao de texto de PDFs de politica (camada de texto + OCR de reserva).

Usado pela camada de Analise para obter o texto de politicas servidas como PDF
(ponto cego historico do pipeline). Estrategia:

1. Camada de texto nativa do PDF via PyMuPDF (rapido, fiel).
2. Se o texto for insuficiente (PDF escaneado/imagem), OCR das paginas
   renderizadas via pytesseract (Tesseract). Idioma padrao 'por'.

Dependencias: pymupdf (obrigatoria); pytesseract + Tesseract com o pacote de
idioma 'por' (tesseract-ocr-por) para o OCR. Sem OCR disponivel, retorna o que a
camada de texto fornecer (degradacao graciosa; nunca levanta).
"""
from __future__ import annotations

import io

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
    Pura (sem rede): decide quais PDFs baixar. Retorna lista deduplicada."""
    urls = []
    for cat in categories:
        for item in (subpage_selection or {}).get(cat, []) or []:
            u = (item or {}).get("url", "") or ""
            base = u.split("?")[0].split("#")[0]
            if base.lower().endswith(".pdf") and u not in urls:
                urls.append(u)
    return urls


__all__ = ["extract_pdf_text", "select_policy_pdf_urls"]
