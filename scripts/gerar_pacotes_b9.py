# -*- coding: utf-8 -*-
"""Gera pacotes de evidencia em TEXTO para a recoleta b9 (snapshot data/b9).

Diferencas vs. a versao b7: le data/b9/raw (um tarball por sitio coletado),
ESCREVE em Rotulagem/evidencia_b9 e screenshots_b9, e EXTRAI o texto dos PDFs
de politica capturados (pdf_documents/) com PyMuPDF + OCR de reserva. Rotular
sobre ESTE material; nunca o site ao vivo; sem olhar results.sqlite.

Uso (Windows, .venv ativo): cd C:\\Dev\\privacyscope\\scripts ; python gerar_pacotes_b9.py
Resumivel (pula .txt existente).
"""
import os, re, glob, json, tarfile, unicodedata, io
from html.parser import HTMLParser
from collections import OrderedDict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(REPO, "data", "b9", "raw")
OUT = r"C:\Users\Cristiano.Silverio\OneDrive - LGPD2U\Treinamentos\ESALQ\TCC\Rotulagem"
EVID = os.path.join(OUT, "evidencia_b9")
# Arvore de enriquecimento por PDF (remediacao b9, append-only): os PDFs cujos
# links estavam na evidencia mas nao foram baixados pelo fetcher. Fica FORA do
# tarball para nao quebrar o hash de custodia do original. Em coletas NOVAS o
# fetcher corrigido ja poe o PDF dentro do proprio tar.gz (pdf_documents/).
ENRICH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "data", "b9", "pdf_enrichment")
SHOTS = os.path.join(OUT, "screenshots_b9")
COPIAR_SCREENSHOTS = True

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
TEL_RE = re.compile(r"""href=["'](tel:[^"']+|https?://wa\.me/[^"']+|https?://api\.whatsapp[^"']+)["']""", re.I)
RIGHTS = re.compile(r"titular|direito|privacidad|encarregad|\bdpo\b|lgpd|opt[\s\-]?out|solicita", re.I)

try:
    import fitz
    _FITZ = True
except Exception:
    _FITZ = False
try:
    import pytesseract
    from PIL import Image
    _OCR = True
except Exception:
    _OCR = False


def extract_pdf_text(data, lang="por", min_chars=200, dpi=200, max_pages=40):
    if not _FITZ:
        return "", "sem_pymupdf"
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return "", "empty"
    parts = []
    for i, p in enumerate(doc):
        if i >= max_pages:
            break
        try:
            parts.append(p.get_text())
        except Exception:
            pass
    text = "\n".join(parts).strip()
    if len(text) >= min_chars or not _OCR:
        return text, ("text_layer" if text else "empty")
    ocr = []
    for i, p in enumerate(doc):
        if i >= max_pages:
            break
        try:
            pix = p.get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            try:
                ocr.append(pytesseract.image_to_string(img, lang=lang))
            except Exception:
                ocr.append(pytesseract.image_to_string(img))
        except Exception:
            pass
    ot = "\n".join(ocr).strip()
    return (ot, "ocr") if len(ot) > len(text) else (text or ot, "text_layer" if text else "ocr")


class Vis(HTMLParser):
    SKIP = {"script", "style", "noscript", "head", "svg", "path"}

    def __init__(self):
        super().__init__()
        self.buf = []; self.skip = 0; self.links = []; self._a = None; self._t = []

    def handle_starttag(self, t, a):
        if t in self.SKIP:
            self.skip += 1
        if t == "a":
            self._a = dict(a).get("href", "") or ""; self._t = []

    def handle_endtag(self, t):
        if t in self.SKIP and self.skip > 0:
            self.skip -= 1
        if t == "a" and self._a is not None:
            self.links.append((self._a, " ".join(self._t).strip())); self._a = None

    def handle_data(self, d):
        if self.skip == 0:
            s = d.strip()
            if s:
                self.buf.append(s)
                if self._a is not None:
                    self._t.append(s)


def parse(b):
    p = Vis()
    try:
        p.feed(b.decode("utf-8", "ignore"))
    except Exception:
        pass
    return re.sub(r"[ \t]+", " ", " ".join(p.buf)), p.links


def _norm(u):
    u = re.sub(r"\?.*$", "", u or "")
    u = re.sub(r"^https?://[^/]+", "", u)
    return unicodedata.normalize("NFC", u).lower().rstrip("/")


def load(tar):
    o = {"root": b"", "subs": OrderedDict(), "meta": {}, "index": {}, "pdfs": OrderedDict(), "pdfidx": {}}
    shot = None
    with tarfile.open(tar, "r:gz") as tf:
        for m in tf.getmembers():
            n = m.name
            if n.endswith("/html_root.html"):
                o["root"] = tf.extractfile(m).read()
            elif "/html_subpages/" in n and n.endswith(".html"):
                o["subs"][os.path.basename(n)] = tf.extractfile(m).read()
            elif n.endswith("/html_subpages/_index.json"):
                o["index"] = json.load(tf.extractfile(m))
            elif n.endswith("/meta.json"):
                o["meta"] = json.load(tf.extractfile(m))
            elif "/pdf_documents/" in n and n.endswith(".pdf"):
                o["pdfs"][os.path.basename(n)] = tf.extractfile(m).read()
            elif n.endswith("/pdf_documents/_index.json"):
                o["pdfidx"] = json.load(tf.extractfile(m))
            elif n.endswith("/screenshot.png") and shot is None and "/phases/" not in n:
                shot = tf.extractfile(m).read()
    return o, shot


def build(h, s):
    roottxt, rlinks = parse(s["root"])
    links = list(rlinks); subtxt = {}
    for k, b in s["subs"].items():
        tt, ll = parse(b); subtxt[k] = tt; links += ll
    allhtml = s["root"].decode("utf-8", "ignore") + "\n" + "\n".join(b.decode("utf-8", "ignore") for b in s["subs"].values())
    emails = sorted(set(EMAIL_RE.findall(allhtml)))
    tels = sorted(set(m if isinstance(m, str) else m[0] for m in TEL_RE.findall(allhtml)))
    ext = []
    for href, at in links:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if href.startswith("http") and h.split(".")[0] not in href and at and RIGHTS.search(at):
            ext.append((at[:60], href[:120]))
    ext = list(dict.fromkeys(ext))[:15]
    ss = (s.get("meta") or {}).get("subpage_selection", {}); cats = list(ss.keys())
    idx = s.get("index", {})
    pol = []
    for key in sorted(subtxt):
        base = key[:-5] if key.endswith(".html") else key
        path = idx.get(base, base)
        if path == "/__pre_consent":
            continue
        pol.append((path, subtxt[key][:200000]))
    L = ["SITIO: %s" % h, "=" * 70,
         "[SINAIS NEUTROS - material bruto, NAO e veredito do detector]",
         "e-mails: %s" % (", ".join(emails) if emails else "(nenhum)"),
         "tel/whatsapp: %s" % (", ".join(tels) if tels else "(nenhum)"),
         "subpaginas (categorias): %s" % (", ".join(cats) if cats else "(nenhuma)"),
         "PDFs de politica capturados: %d" % len(s["pdfs"]),
         "links externos c/ texto de direitos:"]
    L += ["   - %s -> %s" % (a, hh) for a, hh in ext] or ["   (nenhum)"]
    L += ["", "[TEXTO VISIVEL - PAGINA INICIAL]", roottxt[:30000] or "(vazio)"]
    for path, t in pol:
        L += ["", "[SUBPAGINA] %s" % path, t or "(vazio)"]
    # PDFs de politica
    p2u = s.get("pdfidx", {})
    for k in sorted(s["pdfs"]):
        url = p2u.get(k[:-4], k)
        txt, meth = extract_pdf_text(s["pdfs"][k])
        L += ["", "[POLITICA EM PDF: %s] (extracao=%s)" % (url, meth), txt[:200000] or "(vazio)"]

    # PDFs vindos da REMEDIACAO (baixados depois, a partir de links ja presentes
    # na evidencia). Marcados distintamente para o anotador saber a procedencia.
    n_enr = 0
    emeta = os.path.join(ENRICH, h, "meta.json")
    if os.path.exists(emeta):
        try:
            em = json.load(open(emeta, encoding="utf-8"))
            for d in em.get("documentos", []):
                tp = os.path.join(ENRICH, h, d.get("arquivo_txt", ""))
                if not os.path.exists(tp):
                    continue
                txt = open(tp, encoding="utf-8", errors="ignore").read()
                L += ["", "[POLITICA EM PDF - ENRIQUECIMENTO: %s] (extracao=%s, baixado_em=%s)"
                      % (d.get("source_url", "?"), d.get("metodo_extracao", "?"),
                         (em.get("downloaded_at_utc", "?") or "?")[:10]),
                      txt[:200000] or "(vazio)"]
                n_enr += 1
        except Exception:
            pass
    if not pol and not s["pdfs"] and not n_enr:
        L += ["", "[SUBPAGINAS] (nenhuma subpagina interna nem PDF alem da home)"]
    return "\n".join(L)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Gera os pacotes de evidencia para rotulagem.")
    ap.add_argument("--force", action="store_true",
                    help="REGERA pacotes ja existentes (necessario apos o enriquecimento por PDF).")
    ap.add_argument("--only-enriched", action="store_true",
                    help="Regera apenas os sitios que tem PDF em data/b9/pdf_enrichment/.")
    args = ap.parse_args()
    enriquecidos = set()
    if os.path.isdir(ENRICH):
        enriquecidos = {d for d in os.listdir(ENRICH)
                        if os.path.isdir(os.path.join(ENRICH, d))}
        print("Sitios com PDF enriquecido: %d" % len(enriquecidos))

    os.makedirs(EVID, exist_ok=True)
    if COPIAR_SCREENSHOTS:
        os.makedirs(SHOTS, exist_ok=True)
    tars = sorted(glob.glob(os.path.join(RAW_DIR, "*.tar.gz")))
    feitos = 0
    for i, tar in enumerate(tars, 1):
        h = os.path.basename(tar).split("__")[-1][:-7]  # <ts>__<run>__<host>.tar.gz
        out = os.path.join(EVID, h + ".txt")
        if args.only_enriched and h not in enriquecidos:
            continue
        if os.path.exists(out) and not (args.force or args.only_enriched):
            continue
        try:
            s, shot = load(tar)
        except Exception as e:
            print("[%d/%d] %s: ERRO %s" % (i, len(tars), h, e)); continue
        with open(out + ".tmp", "w", encoding="utf-8") as f:
            f.write(build(h, s))
        os.replace(out + ".tmp", out)
        if COPIAR_SCREENSHOTS and shot:
            with open(os.path.join(SHOTS, h + ".png"), "wb") as f:
                f.write(shot)
        feitos += 1
        if feitos % 50 == 0:
            print("  ... %d pacotes" % feitos)
    print("Concluido. Pacotes: %d / %d tarballs." % (
        len([x for x in os.listdir(EVID) if x.endswith(".txt")]), len(tars)))


if __name__ == "__main__":
    main()
