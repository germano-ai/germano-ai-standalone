"""XML (lxml, sicuro contro XXE) e HTML (BeautifulSoup) con analisi di testo e attributi."""
import re
import urllib.parse

from ..analyzer import Unit, apply_replacements
from ..detect import CATEGORY_MAP
from . import embedded_text

# Elementi XML il cui contenuto e' per definizione un dato personale (es. FatturaPA, moduli PA).
_XML_FORCE = {
    "nome": "private_person", "cognome": "private_person", "nominativo": "private_person",
    "codicefiscale": "cf_iva", "idcodice": "cf_iva", "partitaiva": "cf_iva", "piva": "cf_iva",
    "indirizzo": "private_address", "numerocivico": "private_address", "cap": "private_address",
    "comune": "private_address", "email": "private_email", "pec": "private_email",
    "pecdestinatario": "private_email", "telefono": "private_phone", "cellulare": "private_phone",
    "fax": "private_phone", "iban": "account_number", "datanascita": "private_date",
    "denominazione": "private_org", "ragionesociale": "private_org",
}
_SKIP_ATTRS = {"version", "encoding", "standalone", "type", "lang", "space", "versione", "schemalocation",
               "nonamespaceschemalocation", "id", "class", "style", "href", "src", "ref", "target", "xmlns"}


def _local(tag):
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower()


def _forced_label(name, ctx):
    group = _XML_FORCE.get(name)
    if not group:
        return None
    label, key = CATEGORY_MAP[group]
    if key and not ctx.settings.get(key, True):
        return None
    return label


def _name_hint(el):
    """Nome del file dichiarato accanto a un allegato incorporato (FatturaPA: <NomeAttachment> vicino ad <Attachment>)."""
    parent = el.getparent()
    if parent is None:
        return ""
    for sib in parent:
        if sib is el or not isinstance(sib.tag, str) or len(sib) or not sib.text:
            continue
        low, text = _local(sib.tag), sib.text.strip()
        if ("nome" in low or "name" in low) and 3 <= len(text) <= 255 and "." in text:
            return text
    return ""


def _transform_xml_tree(tree, ctx):
    from lxml import etree
    units, setters = [], []

    def add(value, setter, context="", force=None):
        units.append(Unit(value, context=context, force_label=force))
        setters.append(setter)

    for el in tree.getroot().iter():
        if isinstance(el, (etree._Comment, etree._ProcessingInstruction)):
            if el.text and el.text.strip():
                add(el.text, lambda v, e=el: setattr(e, "text", v))
            if el.tail and el.tail.strip():
                add(el.tail, lambda v, e=el: setattr(e, "tail", v))
            continue
        name = _local(el.tag)
        if el.text and el.text.strip():
            # Allegato incorporato in Base64 (FatturaPA <Attachment>, certificati, documenti nelle buste): e' un file,
            # non un testo. Analizzato come testo usciva identico; ora viene elaborato col suo formato o tolto.
            blob = embedded_text(el.text, ctx, _name_hint(el), f"contenuto incorporato in <{name}>") \
                if len(el) == 0 else None
            if blob is not None:
                if blob != el.text:
                    el.text = blob
            else:
                force = _forced_label(name, ctx) if len(el) == 0 else None
                add(el.text, lambda v, e=el: setattr(e, "text", v), context=f"{name}: " if name else "", force=force)
        for k, v in list(el.attrib.items()):
            an = _local(k)
            if not v or len(v) < 3:
                continue
            if v[:5].lower() == "data:":
                # immagine o documento in linea (SVG <image href="data:image/png;base64,...">)
                nv = embedded_text(v, ctx, "", f"contenuto in linea di <{name}>")
                if nv is not None:
                    if nv != v:
                        el.set(k, nv)
                    continue
            if an == "href":
                if v.lower().startswith(("mailto:", "tel:", "sms:", "callto:")):
                    add(v, lambda nv, e=el, kk=k: e.set(kk, nv), context="href: ")
                continue
            if an in _SKIP_ATTRS:
                continue
            if not any(c.isalpha() for c in v) and not (len(v) >= 5 and any(c.isdigit() for c in v)):
                continue
            add(v, lambda nv, e=el, kk=k: e.set(kk, nv), context=f"{an}: ")
        if el.tail and el.tail.strip():
            add(el.tail, lambda v, e=el: setattr(e, "tail", v))

    res = ctx.analyze(units) if units else []
    for u, setter, r in zip(units, setters, res):
        if r:
            setter(apply_replacements(u.text, r))


def transform_xml_bytes(data, ctx):
    from lxml import etree
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False,
                             load_dtd=False, recover=False)
    root = etree.fromstring(data, parser)
    tree = etree.ElementTree(root)
    _transform_xml_tree(tree, ctx)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def process_xml(in_path, out_path, ctx):
    from lxml import etree
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False,
                             load_dtd=False, recover=False)
    try:
        tree = etree.parse(in_path, parser)
    except etree.XMLSyntaxError:
        from .textlike import process_text
        return process_text(in_path, out_path, ctx)
    _transform_xml_tree(tree, ctx)
    di = tree.docinfo
    tree.write(out_path, encoding=di.encoding or "UTF-8", xml_declaration=True,
               standalone=di.standalone if di.standalone is not None else None)
    return None


# ------------------------------------------------------------------------------------------ HTML
_HTML_ATTRS = ("title", "alt", "placeholder", "value", "aria-label", "data-name", "data-email", "label", "summary")
# <meta> tecnici: mai analizzati. TUTTI gli altri si' (prima valeva un elenco chiuso di 14 nomi: «citation_author»,
# «article:author», «profile:first_name», «twitter:creator»... uscivano in chiaro).
_META_SKIP = {"viewport", "robots", "googlebot", "theme-color", "color-scheme", "format-detection", "referrer",
              "generator", "msapplication-tilecolor", "msapplication-config", "apple-mobile-web-app-capable",
              "apple-mobile-web-app-status-bar-style", "mobile-web-app-capable", "og:type", "og:locale",
              "twitter:card", "progid", "originator"}
_META_PERSON = {"author", "creator", "dc.creator", "dcterms.creator", "dc.contributor", "citation_author",
                "article:author", "book:author", "twitter:creator", "parsely-author", "sailthru.author", "owner",
                "profile:first_name", "profile:last_name", "profile:username", "lastauthor", "operator"}
# attributi che possono contenere un file in linea («data:image/png;base64,...»): foto, scansioni, firme
_HTML_DATA_ATTRS = ("src", "href", "data", "poster", "background", "xlink:href")
_CSS_DATA_URI_RE = re.compile(r"url\(\s*(['\"]?)(data:[^)'\"]{24,})\1\s*\)", re.I)


def _css_data_uris(css, ctx):
    """Immagini in linea di un foglio di stile (`url(data:...)`) elaborate come file; restituisce il nuovo testo."""
    if "data:" not in css.lower():
        return css

    def one(m):
        nv = embedded_text(m.group(2), ctx, "", "immagine in linea del foglio di stile")
        return m.group(0) if nv is None or nv == m.group(2) else f"url({m.group(1)}{nv}{m.group(1)})"
    return _CSS_DATA_URI_RE.sub(one, css)


def transform_soup(soup, ctx):
    from bs4 import Declaration, Doctype
    units, setters = [], []
    changed = False

    def add(value, setter, force=None):
        units.append(Unit(value, force_label=force))
        setters.append(setter)

    for node in list(soup.find_all(string=True)):
        if isinstance(node, (Doctype, Declaration)):
            continue
        s = str(node)
        if not s.strip():
            continue
        parent = node.parent
        if parent is not None and parent.name == "style":
            css = _css_data_uris(s, ctx)
            if css != s:
                new_node = type(node)(css)
                node.replace_with(new_node)
                node, s, changed = new_node, css, True

        # Si conserva il tipo del nodo (Comment resta commento: il testo nascosto non diventa visibile). Anche il
        # contenuto di <script> e <style> e' testo da analizzare, come nei file .js e .css: lo stato che le pagine
        # salvano in uno script («var utente = {nome: ..., email: ...}») prima veniva saltato e usciva in chiaro.
        def _set(v, n=node, c=type(node)):
            n.replace_with(c(v))
        add(s, _set)

    person = "[PERSONA]" if ctx.settings.get("censor_person", True) else None
    for tag in soup.find_all(True):
        for attr in _HTML_DATA_ATTRS:
            v = tag.get(attr)
            if isinstance(v, str) and v.lstrip()[:5].lower() == "data:":
                # file in linea: elaborato col suo formato (immagini: volti, firme, OCR, metadati) o tolto
                nv = embedded_text(v, ctx, "", f"contenuto in linea di <{tag.name}>")
                if nv is not None and nv != v:
                    tag[attr] = nv
                    changed = True
        style = tag.get("style")
        if isinstance(style, str) and "data:" in style.lower():
            new_style = _css_data_uris(style, ctx)
            if new_style != style:
                tag["style"] = new_style
                changed = True
        for attr in _HTML_ATTRS:
            v = tag.get(attr)
            if isinstance(v, str) and v.strip():
                add(v, lambda nv, t=tag, a=attr: t.__setitem__(a, nv))
        for attr, v in list((tag.attrs or {}).items()):
            if isinstance(attr, str) and attr.startswith("data-") and attr not in _HTML_ATTRS:
                if isinstance(v, str) and len(v.strip()) >= 3 and (any(c.isalpha() for c in v) or len(v) >= 5):
                    add(v, lambda nv, t=tag, a=attr: t.__setitem__(a, nv))
        # Collegamenti: mailto/tel ovunque; negli <a>/<area> e nei <form> l'intero indirizzo (i link di disiscrizione
        # e di profilo portano l'email o il nome di chi riceve: «...?email=mario.rossi%40example.com»). Le sequenze
        # %XX si risolvono prima dell'analisi, altrimenti «%40» nasconde la chiocciola alle regole.
        for attr in (("href", "action") if tag.name == "form" else ("href",)):
            url = tag.get(attr)
            if not isinstance(url, str) or len(url.strip()) < 3 or url.lstrip()[:5].lower() == "data:":
                continue
            if tag.name in ("a", "area", "form") or url.lower().startswith(("mailto:", "tel:", "sms:", "callto:")):
                add(urllib.parse.unquote(url) if "%" in url else url, lambda nv, t=tag, a=attr: t.__setitem__(a, nv))
        if tag.name == "meta" and not tag.get("http-equiv"):
            nm = str(tag.get("name") or tag.get("property") or tag.get("itemprop") or "").strip().lower()
            c = tag.get("content")
            if nm not in _META_SKIP and isinstance(c, str) and c.strip():
                add(c, lambda nv, t=tag: t.__setitem__("content", nv), force=person if nm in _META_PERSON else None)

    res = ctx.analyze(units) if units else []
    for u, setter, r in zip(units, setters, res):
        if r:
            setter(apply_replacements(u.text, r))
            changed = True
    return changed


def transform_html_string(html, ctx):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    if transform_soup(soup, ctx):
        return str(soup)
    return html


def process_html(in_path, out_path, ctx):
    from bs4 import BeautifulSoup
    with open(in_path, "rb") as f:
        raw = f.read()
    soup = BeautifulSoup(raw, "html.parser")
    transform_soup(soup, ctx)
    # encode() aggiorna anche il <meta charset> dichiarato nel documento
    data = soup.encode("utf-8", formatter="minimal")
    with open(out_path, "wb") as f:
        f.write(data)
    return None
