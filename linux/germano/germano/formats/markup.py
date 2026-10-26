"""XML (lxml, sicuro contro XXE) e HTML (BeautifulSoup) con analisi di testo e attributi."""
from ..analyzer import Unit, apply_replacements
from ..detect import CATEGORY_MAP

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


def process_xml(in_path, out_path, ctx):
    from lxml import etree
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, remove_blank_text=False,
                             load_dtd=False, recover=False)
    try:
        tree = etree.parse(in_path, parser)
    except etree.XMLSyntaxError:
        from .textlike import process_text
        return process_text(in_path, out_path, ctx)
    units, setters = [], []

    def add(value, setter, context="", force=None):
        units.append(Unit(value, context=context, force_label=force))
        setters.append(setter)

    for el in tree.getroot().iter():
        if isinstance(el, (etree._Comment, etree._ProcessingInstruction)):
            if isinstance(el, etree._Comment) and el.text and el.text.strip():
                add(el.text, lambda v, e=el: setattr(e, "text", v))
            if el.tail and el.tail.strip():
                add(el.tail, lambda v, e=el: setattr(e, "tail", v))
            continue
        name = _local(el.tag)
        if el.text and el.text.strip():
            force = _forced_label(name, ctx) if len(el) == 0 else None
            add(el.text, lambda v, e=el: setattr(e, "text", v), context=f"{name}: " if name else "", force=force)
        for k, v in list(el.attrib.items()):
            an = _local(k)
            if an in _SKIP_ATTRS or not v or len(v) < 3 or not any(c.isalpha() for c in v):
                continue
            add(v, lambda nv, e=el, kk=k: e.set(kk, nv), context=f"{an}: ")
        if el.tail and el.tail.strip():
            add(el.tail, lambda v, e=el: setattr(e, "tail", v))

    res = ctx.analyze(units) if units else []
    for u, setter, r in zip(units, setters, res):
        if r:
            setter(apply_replacements(u.text, r))
    di = tree.docinfo
    tree.write(out_path, encoding=di.encoding or "UTF-8", xml_declaration=True,
               standalone=di.standalone if di.standalone is not None else None)
    return None


# ------------------------------------------------------------------------------------------ HTML
_HTML_TEXT_SKIP = {"script", "style", "template"}
_HTML_ATTRS = ("title", "alt", "placeholder", "value", "aria-label", "data-name", "data-email", "label", "summary")
_META_NAMES = {"author", "description", "keywords", "subject", "creator", "publisher", "copyright", "reply-to",
               "og:title", "og:description", "twitter:title", "twitter:description", "dc.creator", "dc.title"}


def transform_soup(soup, ctx):
    from bs4 import Declaration, Doctype
    units, setters = [], []

    def add(value, setter, force=None):
        units.append(Unit(value, force_label=force))
        setters.append(setter)

    for node in list(soup.find_all(string=True)):
        if isinstance(node, (Doctype, Declaration)):
            continue
        parent = node.parent
        if parent is not None and parent.name in _HTML_TEXT_SKIP:
            continue
        s = str(node)
        if not s.strip():
            continue

        # Si conserva il tipo del nodo (Comment resta commento: il testo nascosto non diventa visibile)
        def _set(v, n=node, c=type(node)):
            n.replace_with(c(v))
        add(s, _set)

    for tag in soup.find_all(True):
        for attr in _HTML_ATTRS:
            v = tag.get(attr)
            if isinstance(v, str) and v.strip():
                add(v, lambda nv, t=tag, a=attr: t.__setitem__(a, nv))
        href = tag.get("href")
        if isinstance(href, str) and href.lower().startswith(("mailto:", "tel:", "sms:", "callto:")):
            add(href, lambda nv, t=tag: t.__setitem__("href", nv))
        if tag.name == "meta":
            nm = (tag.get("name") or tag.get("property") or "").lower()
            c = tag.get("content")
            if nm in _META_NAMES and isinstance(c, str) and c.strip():
                force = "[PERSONA]" if nm in ("author", "creator", "dc.creator") and ctx.settings.get("censor_person", True) else None
                add(c, lambda nv, t=tag: t.__setitem__("content", nv), force=force)

    res = ctx.analyze(units) if units else []
    changed = False
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
