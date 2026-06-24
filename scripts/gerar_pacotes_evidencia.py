# -*- coding: utf-8 -*-
"""
Gera, para cada sitio da amostra ampliada (200), um pacote de evidencia em TEXTO
(texto visivel da home + texto de TODAS as subpaginas armazenadas + sinais
neutros de e-mail/telefone/links) e copia o screenshot principal. Rotular sobre
ESTE material (snapshot coletado), nunca o site ao vivo, e SEM olhar a saida do
detector (data/*/results.sqlite).

Local: <repo>/scripts/. Le tarballs de <repo>/data/*/raw e ESCREVE em OUT
(pasta Rotulagem do TCC). Uso:
    cd C:\Dev\privacyscope\scripts
    python gerar_pacotes_evidencia.py
Resumivel (pula .txt existente). So biblioteca padrao.
"""
import os, re, glob, json, tarfile, csv, unicodedata
from html.parser import HTMLParser
from collections import OrderedDict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = r"C:\Users\Cristiano.Silverio\OneDrive - LGPD2U\Treinamentos\ESALQ\TCC\Rotulagem"
EVID = os.path.join(OUT, "evidencia")
SHOTS = os.path.join(OUT, "screenshots")
COPIAR_SCREENSHOTS = True
RAW_DIRS = [os.path.join(REPO, "data", d, "raw") for d in ("b7", "b7_recollect", "b7_gov_supp", "b7_T1")]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
TEL_RE   = re.compile(r"""href=["'](tel:[^"']+|https?://wa\.me/[^"']+|https?://api\.whatsapp[^"']+)["']""", re.I)
RIGHTS   = re.compile(r"titular|direito|privacidad|encarregad|\bdpo\b|lgpd|opt[\s\-]?out|solicita", re.I)


class Vis(HTMLParser):
    SKIP = {"script", "style", "noscript", "head", "svg", "path"}

    def __init__(self):
        super().__init__()
        self.buf = []
        self.skip = 0
        self.links = []
        self._a = None
        self._t = []

    def handle_starttag(self, t, a):
        if t in self.SKIP:
            self.skip += 1
        if t == "a":
            self._a = dict(a).get("href", "") or ""
            self._t = []

    def handle_endtag(self, t):
        if t in self.SKIP and self.skip > 0:
            self.skip -= 1
        if t == "a" and self._a is not None:
            self.links.append((self._a, " ".join(self._t).strip()))
            self._a = None

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


def find_tar(h):
    for d in RAW_DIRS:
        g = glob.glob(os.path.join(d, "*__%s.tar.gz" % h))
        if g:
            return g[0]
    return None


def load(h):
    t = find_tar(h)
    if not t:
        return None, None
    o = {"root": b"", "subs": OrderedDict(), "meta": {}, "index": {}}
    shot = None
    with tarfile.open(t, "r:gz") as tf:
        for m in tf.getmembers():
            n = m.name
            if n.endswith("/html_root.html"):
                o["root"] = tf.extractfile(m).read()
            elif "/html_subpages/" in n and n.endswith(".html"):
                o["subs"][os.path.basename(n)] = tf.extractfile(m).read()
            elif n.endswith("/_index.json"):
                o["index"] = json.load(tf.extractfile(m))
            elif n.endswith("/meta.json"):
                o["meta"] = json.load(tf.extractfile(m))
            elif n.endswith("/screenshot.png") and shot is None and "/phases/" not in n:
                shot = tf.extractfile(m).read()
    return o, shot


def _norm(u):
    u = re.sub(r"\?.*$", "", u or "")
    u = re.sub(r"^https?://[^/]+", "", u)
    return unicodedata.normalize("NFC", u).lower().rstrip("/")


def build(h, s):
    roottxt, rlinks = parse(s["root"])
    links = list(rlinks)
    subtxt = {}
    for k, b in s["subs"].items():
        tt, ll = parse(b)
        subtxt[k] = tt
        links += ll
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

    ss = (s.get("meta") or {}).get("subpage_selection", {})
    cats = list(ss.keys())
    idx = s.get("index", {})

    sub2cat = {}
    for cat, items in ss.items():
        for it in items:
            nu = _norm(it.get("url", ""))
            for sub, path in idx.items():
                npth = _norm(path)
                if nu and npth and (nu == npth or nu.endswith(npth) or npth.endswith(nu)):
                    sub2cat[sub + ".html"] = cat

    pol = []
    for key in sorted(subtxt):
        base = key[:-5] if key.endswith(".html") else key
        path = idx.get(base, base)
        if path == "/__pre_consent":
            continue
        cat = sub2cat.get(key, "subpagina")
        pol.append((cat, path, subtxt[key][:200000]))

    L = ["SITIO: %s" % h, "=" * 70,
         "[SINAIS NEUTROS - material bruto, NAO e veredito do detector]",
         "e-mails: %s" % (", ".join(emails) if emails else "(nenhum)"),
         "tel/whatsapp: %s" % (", ".join(tels) if tels else "(nenhum)"),
         "subpaginas (categorias): %s" % (", ".join(cats) if cats else "(nenhuma)"),
         "links externos c/ texto de direitos:"]
    L += ["   - %s -> %s" % (a, hh) for a, hh in ext] or ["   (nenhum)"]
    L += ["", "[TEXTO VISIVEL - PAGINA INICIAL]", roottxt[:30000] or "(vazio)"]
    for cat, path, t in pol:
        L += ["", "[SUBPAGINA: %s] %s" % (cat, path), t or "(vazio)"]
    if not pol:
        L += ["", "[SUBPAGINAS] (nenhuma subpagina interna armazenada alem da home)"]
    return "\n".join(L)


def main():
    os.makedirs(EVID, exist_ok=True)
    if COPIAR_SCREENSHOTS:
        os.makedirs(SHOTS, exist_ok=True)
    rows = list(csv.DictReader(open(os.path.join(REPO, "protocols", "b7_efetivas.csv"), encoding="utf-8")))
    feitos = 0
    semtar = []
    for i, r in enumerate(rows, 1):
        h = r["host"].strip()
        out = os.path.join(EVID, h + ".txt")
        if os.path.exists(out):
            continue
        try:
            s, shot = load(h)
        except Exception as e:
            print("[%d/200] %s: ERRO %s" % (i, h, e))
            continue
        if not s or not (s["root"] or s["subs"]):
            semtar.append(h)
            print("[%d/200] %s: SEM TARBALL" % (i, h))
            continue
        with open(out + ".tmp", "w", encoding="utf-8") as f:
            f.write(build(h, s))
        os.replace(out + ".tmp", out)
        if COPIAR_SCREENSHOTS and shot:
            with open(os.path.join(SHOTS, h + ".png"), "wb") as f:
                f.write(shot)
        feitos += 1
        if feitos % 20 == 0:
            print("  ... %d novos pacotes" % feitos)
    total = len([x for x in os.listdir(EVID) if x.endswith(".txt")])
    print("\nConcluido. Novos: %d. Total: %d/200. Sem tarball: %d" % (feitos, total, len(semtar)))
    if semtar:
        print("Sem tarball:", ", ".join(semtar))


if __name__ == "__main__":
    main()
