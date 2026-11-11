#!/usr/bin/env python3
"""Monta ./public a partir do espelho bruto do site (mirror).

Uso: python3 build.py <pasta-do-espelho> <pasta-de-saida>

O que faz (só ajustes estruturais, sem redesign):
- copia tudo, descartando lixo do rastreador
- garante index.html em toda pasta que só tem index.htm
- troca links absolutos do próprio domínio (e do host antigo oiw12) por caminhos relativos à raiz
- remove a busca de terceiros (SearchIQ) e o crédito "Powered by OIW"
- troca os formulários MachForm (PHP) por formulários nativos que postam em /api/form
"""
import os
import re
import shutil
import sys
from pathlib import Path

SRC = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
HERE = Path(__file__).resolve().parent
MAX_ASSET = 25 * 1024 * 1024  # limite por arquivo do Workers Static Assets

STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ "
          "NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC").split()
SOURCES = ["Google", "Bing", "Yahoo", "Current Customer", "Newsletter", "Other"]

FULL = ["first_name", "last_name", "company", "phone", "email", "address", "city", "state", "zip",
        "comments", "source"]
SHORT = ["first_name", "last_name", "phone", "email", "comments"]
NEWS = ["first_name", "last_name", "company", "email"]

FORMS = {
    "10241": ("contact", "Contact Us", FULL),
    "10754": ("quote", "Request A Quote", FULL),
    "13184": ("consultation", "Free Consultation", FULL),
    "10920": ("safetech", "Safetech", SHORT),
    "12230": ("ecosystem", "Ecosystem CTA", SHORT),
    "11350": ("newsletter", "Newsletter", NEWS),
}

LABELS = {
    "first_name": ("First Name", "text", True, "given-name"),
    "last_name": ("Last Name", "text", True, "family-name"),
    "company": ("Company Name", "text", True, "organization"),
    "phone": ("Phone", "tel", True, "tel"),
    "email": ("Email", "email", True, "email"),
    "address": ("Street Address", "text", True, "street-address"),
    "city": ("City", "text", True, "address-level2"),
    "state": ("State", "select", True, "address-level1"),
    "zip": ("Zip Code", "text", True, "postal-code"),
    "comments": ("Comments or Questions", "textarea", False, "off"),
    "source": ("How Did You Find Us?", "select", True, "off"),
}


def form_html(form_id):
    key, title, fields = FORMS[form_id]
    rows = []
    for name in fields:
        label, kind, required, auto = LABELS[name]
        req = " required" if required else ""
        star = ' <span class="rf-req" aria-hidden="true">*</span>' if required else ""
        fid = f"rf-{key}-{name}"
        if kind == "textarea":
            control = f'<textarea id="{fid}" name="{name}" rows="5"{req}></textarea>'
        elif kind == "select":
            opts = STATES if name == "state" else SOURCES
            control = (f'<select id="{fid}" name="{name}" autocomplete="{auto}"{req}><option value=""></option>'
                       + "".join(f"<option>{o}</option>" for o in opts) + "</select>")
        else:
            control = f'<input id="{fid}" name="{name}" type="{kind}" autocomplete="{auto}"{req}>'
        wide = " rf-wide" if kind == "textarea" or name in ("address", "source") else ""
        rows.append(f'<div class="rf-field{wide}"><label for="{fid}">{label}{star}</label>{control}</div>')
    return (
        f'<form class="rf-form" data-rf-form="{key}" method="post" action="/api/form" novalidate>'
        f'<input type="hidden" name="form" value="{key}">'
        '<div class="rf-hp" aria-hidden="true"><label>Leave this field empty'
        '<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>'
        f'<div class="rf-grid">{"".join(rows)}</div>'
        '<div class="rf-actions"><button type="submit" class="rf-submit">Submit</button></div>'
        '<p class="rf-status" role="status" aria-live="polite"></p>'
        '</form>'
        '<link rel="stylesheet" href="/forms/rf-forms.css">'
        '<script src="/forms/rf-forms.js" defer></script>'
    )


RE_SIQ = re.compile(r'<script type="text/javascript">\s*\(function \(\) \{\s*window\.siqConfig.*?</script>', re.S)
RE_MF = re.compile(
    r'<div id="mf_placeholder"\s+data-formurl="/machform/embed\.php\?id=(\d+)".*?'
    r"\}\)\(document,'/machform/'\);\s*</script>", re.S)
RE_OIW = re.compile(r'\s*(?:&nbsp;)?\s*\|\s*(?:&nbsp;)?\s*Powered by\s*<a href="https?://www\.optinwireless\.com/?"[^>]*>\s*OIW\s*</a>', re.I)
RE_CANON_OIW = re.compile(r'(<link rel="canonical" href="https://www\.riceelectronics)\.oiw12(\.com/)', re.I)
RE_SOFT404 = re.compile(r'rel="canonical" href="https://www\.riceelectronics\.com/404\.htm"', re.I)
RE_REL = re.compile(r'''((?:href|src)\s*=\s*["'])(?!/|https?:|#|mailto:|tel:|data:|javascript:)''', re.I)
RE_TAG = re.compile(r'<(a|img|script|iframe|source|link|form|area)\b[^>]*>', re.I)
RE_SELF = re.compile(r'''((?:href|src|action)\s*=\s*["'])(?:https?:)?//(?:www\.)?riceelectronics\.(?:oiw12\.)?com(?=[/"'])''', re.I)

stats = {"soft404": [], "fake_assets": [], "canon_fixed": 0, "pages": 0, "siq": 0, "forms": 0, "oiw": 0, "links": 0, "index_added": 0, "skipped": [], "big": []}


def fix_tag(m):
    tag = m.group(0)
    if "canonical" in tag.lower():
        return tag
    new, n = RE_SELF.subn(lambda x: x.group(1), tag)
    if n:
        # href="" (domínio sem barra) vira a raiz
        new = re.sub(r'''((?:href|src|action)\s*=\s*)(["'])\2''', r'\1\2/\2', new)
        stats["links"] += n
    return new


def process_html(text):
    text, n = RE_SIQ.subn("", text)
    stats["siq"] += n
    text, n = RE_MF.subn(lambda m: form_html(m.group(1)) if m.group(1) in FORMS else m.group(0), text)
    stats["forms"] += n
    text, n = RE_OIW.subn("", text)
    stats["oiw"] += n
    # canonical apontava pro host interno da plataforma antiga
    text, n = RE_CANON_OIW.subn(r"\1\2", text)
    stats["canon_fixed"] += n
    # busca do site dependia do SearchIQ (conta da plataforma antiga): sai o ícone e o campo
    text = re.sub(r'<div id="top-search".*?<!-- #top-search end -->', "", text, flags=re.S)
    text = re.sub(r'<form\b[^>]*action="[^"]*search-results\.htm"[^>]*>.*?</form>', "", text, flags=re.S)
    # link de fonte quebrado no original (faltava uma barra) e caminhos com barra dupla
    text = text.replace('href="/fonts.googleapis.com/', 'href="https://fonts.googleapis.com/')
    text = re.sub(r'''((?:href|src)\s*=\s*["']/(?!/)[^"'?#]*?)//+''', r"\1/", text)
    return RE_TAG.sub(fix_tag, text)


def clean_name(name):
    """Tira query string que o rastreador gravou no nome do arquivo (fonte.woff?v=4.7.0)."""
    return name.split("?", 1)[0]


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    for root, dirs, files in os.walk(SRC):
        rel = Path(root).relative_to(SRC)
        parts = rel.parts
        if any(c in p for p in parts for c in "`${}") or (parts and parts[0] in ("fonts.googleapis.com", "machform")):
            dirs[:] = []
            stats["skipped"].append(str(rel))
            continue
        dirs[:] = [d for d in dirs if not any(c in d for c in "`${}")]
        (OUT / rel).mkdir(parents=True, exist_ok=True)
        for f in sorted(files, key=lambda x: ("?" in x, x)):
            src = Path(root) / f
            name = clean_name(f)
            if not name or any(c in name for c in "`${}"):
                continue
            dst = OUT / rel / name
            if dst.exists():
                continue
            if src.stat().st_size > MAX_ASSET:
                stats["big"].append(str(rel / name))
            if name.lower().endswith((".htm", ".html")):
                raw = src.read_bytes()
                try:
                    text = raw.decode("utf-8")
                    enc = "utf-8"
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
                    enc = "latin-1"
                if RE_SOFT404.search(text):
                    # URL que no site antigo já caía na página de erro
                    stats["soft404"].append(str(rel / name))
                    continue
                dst.write_bytes(process_html(text).encode(enc))
                stats["pages"] += 1
            else:
                if not name.lower().endswith(".pdf"):
                    with open(src, "rb") as fh:
                        head = fh.read(300).lstrip().lower()
                    if head.startswith((b"<!doctype html", b"<html")):
                        # arquivo que não existe no site antigo (o servidor devolvia a página de erro)
                        stats["fake_assets"].append(str(rel / name))
                        continue
                shutil.copy2(src, dst)
    # pasta que só tem index.htm precisa de index.html pra URL da pasta responder
    for root, _dirs, files in os.walk(OUT):
        if "index.htm" in files and "index.html" not in files:
            shutil.copy2(Path(root) / "index.htm", Path(root) / "index.html")
            stats["index_added"] += 1
    # arquivos tratados à mão que substituem os originais (ex.: PDFs recomprimidos pra caber em 25 MiB)
    if (HERE / "overrides").exists():
        shutil.copytree(HERE / "overrides", OUT, dirs_exist_ok=True)
        stats["big"] = [b for b in stats["big"] if (OUT / b).stat().st_size > MAX_ASSET]
    shutil.copytree(HERE / "forms", OUT / "forms")
    # página de erro: mesma do site antigo, com caminhos absolutos pra funcionar em qualquer pasta
    err = (HERE / "static" / "404-src.htm").read_text(encoding="utf-8", errors="replace")
    err = RE_REL.sub(lambda m: m.group(1) + "/", process_html(err))
    err = re.sub(r'<link rel="canonical"[^>]*>', '<meta name="robots" content="noindex">', err)
    (OUT / "404.html").write_text(err, encoding="utf-8")
    # sitemap: tudo em www e sem as URLs que já eram erro
    dead = {"/" + p for p in stats["soft404"]}
    sm = (HERE / "static" / "sitemap-src.xml").read_text(encoding="utf-8")
    sm = sm.replace("://riceelectronics.com", "://www.riceelectronics.com")
    seen = set()
    def keep(m):
        loc = re.search(r"<loc>\s*([^<\s]+)", m.group(0)).group(1)
        path = re.sub(r"^https?://[^/]+", "", loc)
        if path in dead or loc in seen:
            return ""
        seen.add(loc)
        return m.group(0)
    sm = re.sub(r"<url>.*?</url>\s*", keep, sm, flags=re.S)
    (OUT / "sitemap.xml").write_text(sm, encoding="utf-8")
    stats["sitemap_urls"] = len(seen)
    (OUT.parent / "relatorio-build.txt").write_text(
        "URLs que ja eram erro no site antigo (removidas):\n" + "\n".join(sorted(stats["soft404"]))
        + "\n\nArquivos referenciados mas inexistentes no site antigo:\n" + "\n".join(sorted(stats["fake_assets"]))
        + "\n\nArquivos acima de 25 MiB (precisam de tratamento):\n" + "\n".join(stats["big"]) + "\n", encoding="utf-8")
    for extra in ("_headers", "robots.txt"):
        if (HERE / "static" / extra).exists():
            shutil.copy2(HERE / "static" / extra, OUT / extra)
    for k, v in stats.items():
        print(k, v if not isinstance(v, list) else (len(v), v[:10]))


if __name__ == "__main__":
    main()
