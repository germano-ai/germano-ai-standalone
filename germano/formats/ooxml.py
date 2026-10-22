"""Word / Excel / PowerPoint (OOXML) elaborati direttamente a livello XML.

Rispetto alla v0.50 (python-docx `paragraph.text = ...`) la formattazione dei singoli "run", le immagini,
i campi e i collegamenti restano intatti; vengono coperti anche note a pie' di pagina, caselle di testo,
commenti, revisioni, intestazioni/pie' di pagina, note del relatore, gruppi, SmartArt, grafici, metadati.
"""
import os
import re
import zipfile

from lxml import etree

from .. import common
from ..analyzer import Segment, Unit, apply_replacements, apply_to_segments, segments_text
from . import is_supported, process_bytes

W_NS = ("http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "http://purl.oclc.org/ooxml/wordprocessingml/main")
A_NS = ("http://schemas.openxmlformats.org/drawingml/2006/main",
        "http://purl.oclc.org/ooxml/drawingml/main")
S_NS = ("http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "http://purl.oclc.org/ooxml/spreadsheetml/main")
C_NS = ("http://schemas.openxmlformats.org/drawingml/2006/chart",
        "http://purl.oclc.org/ooxml/drawingml/chart")
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _q(nss, local):
    return tuple("{%s}%s" % (ns, local) for ns in nss)


W_P, W_T, W_TAB, W_BR, W_CR = _q(W_NS, "p"), _q(W_NS, "t"), _q(W_NS, "tab"), _q(W_NS, "br"), _q(W_NS, "cr")
W_NBH, W_DELTEXT, W_INSTR = _q(W_NS, "noBreakHyphen"), _q(W_NS, "delText"), _q(W_NS, "instrText")
W_FLDSIMPLE = _q(W_NS, "fldSimple")
A_P, A_T, A_BR = _q(A_NS, "p"), _q(A_NS, "t"), _q(A_NS, "br")
S_SI, S_T, S_R, S_RPH = _q(S_NS, "si"), _q(S_NS, "t"), _q(S_NS, "r"), _q(S_NS, "rPh")
C_V = _q(C_NS, "v")
C_STRCACHE, C_TX = _q(C_NS, "strCache"), _q(C_NS, "tx")

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, remove_blank_text=False)
_RASTER_EXTS = {".png", ".jpg", ".jpeg", ".jpe", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
_PERSON = "[PERSONA]"


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _set_text_preserve(el, v):
    el.text = v
    el.set(XML_SPACE, "preserve")


def _set_text(el, v):
    el.text = v


class _Collector:
    def __init__(self):
        self.units = []
        self.appliers = []  # (part_name, callable(repls) -> bool)

    def segments(self, part, segs, sep=None):
        if not segs:
            return
        text = segments_text(segs)
        if text.strip():
            self.units.append(Unit(text, sep=sep))
            self.appliers.append((part, lambda r, s=segs: apply_to_segments(s, r)))

    def text(self, part, value, setter, force=None, context=""):
        if isinstance(value, str) and value.strip():
            self.units.append(Unit(value, force_label=force, context=context))

            def _ap(r, v=value, st=setter):
                if not r:
                    return False
                st(apply_replacements(v, r))
                return True
            self.appliers.append((part, _ap))

    def run(self, ctx):
        changed = set()
        if not self.units:
            return changed
        results = ctx.analyze(self.units)
        for (part, ap), r in zip(self.appliers, results):
            if r and ap(r):
                changed.add(part)
        return changed


def _paragraph_segments(root, p_tags, t_tags, sep_map, setter):
    """Raggruppa i nodi di testo per paragrafo (il paragrafo piu' vicino: le caselle di testo annidate
    formano paragrafi separati)."""
    tags = tuple(t_tags) + tuple(sep_map.keys())
    paras = {}
    order = []
    p_set = set(p_tags)
    for el in root.iter(*tags):
        p = None
        for anc in el.iterancestors():
            if anc.tag in p_set:
                p = anc
                break
        if p is None:
            continue
        key = id(p)
        if key not in paras:
            paras[key] = (p, [])
            order.append(key)
        segs = paras[key][1]
        if el.tag in sep_map:
            segs.append(Segment(sep_map[el.tag], writable=False))
        else:
            segs.append(Segment(el.text or "", setter=lambda v, e=el: setter(e, v)))
    return [paras[k][1] for k in order]


# ------------------------------------------------------------------------------------------------
def _kind(name_list):
    names = set(name_list)
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    if "ppt/presentation.xml" in names:
        return "pptx"
    return None


def _is_text_part(kind, name):
    n = name.lower()
    if not n.endswith(".xml") or n.startswith("[content_types]"):
        return False
    if "/_rels/" in n or n.endswith(".rels"):
        return False
    base = n.rsplit("/", 1)[-1]
    if base in ("styles.xml", "stylesweffects.xml", "fonttable.xml", "numbering.xml", "websettings.xml",
                "settings.xml", "theme1.xml", "presprops.xml", "viewprops.xml", "tablestyles.xml", "calcchain.xml"):
        return False
    if "/theme/" in n or "/printersettings/" in n or "itemprops" in base:
        return False
    if n.startswith("docprops/"):
        return base in ("core.xml", "app.xml", "custom.xml")
    if n.startswith("customxml/"):
        return base.startswith("item")
    return True


def process_ooxml(in_path, out_path, ctx):
    if not zipfile.is_zipfile(in_path):
        raise ValueError("File Office non valido o protetto da password (non e' un pacchetto OOXML).")
    with zipfile.ZipFile(in_path, "r") as zin:
        infos = zin.infolist()
        names = [i.filename for i in infos]
        kind = _kind(names)
        if kind is None:
            raise ValueError("Pacchetto Office non riconosciuto.")
        trees = {}
        for info in infos:
            if _is_text_part(kind, info.filename):
                try:
                    trees[info.filename] = etree.fromstring(zin.read(info.filename), _PARSER)
                except etree.XMLSyntaxError:
                    pass
        rels = {}
        for info in infos:
            if info.filename.endswith(".rels"):
                try:
                    rels[info.filename] = etree.fromstring(zin.read(info.filename), _PARSER)
                except etree.XMLSyntaxError:
                    pass

        col = _Collector()
        sheet_renames = {}
        sst_map = {}
        _collect(kind, trees, col, ctx, sheet_renames, sst_map)
        _collect_rels(rels, col)
        changed = col.run(ctx)

        if kind == "xlsx":
            changed |= _finish_xlsx(trees, sheet_renames, sst_map)

        new_data = {}
        removed = set()
        for name in changed:
            if name in trees:
                new_data[name] = etree.tostring(trees[name], xml_declaration=True, encoding="UTF-8", standalone=True)
            elif name in rels:
                new_data[name] = etree.tostring(rels[name], xml_declaration=True, encoding="UTF-8", standalone=True)

        # Immagini incorporate, documenti annidati, miniature
        for info in infos:
            n = info.filename
            low = n.lower()
            ext = os.path.splitext(low)[1]
            if "/media/" in low and ext in _RASTER_EXTS and ctx.vision_enabled():
                ctx.check()
                from .images import anonymize_image_bytes
                try:
                    nb = anonymize_image_bytes(zin.read(n), ctx)
                    if nb is not None:
                        new_data[n] = nb
                except Exception as e:
                    ctx.note(f"immagine incorporata non elaborata ({os.path.basename(n)}): {e}")
            elif "/embeddings/" in low:
                base = os.path.basename(n)
                if is_supported(base) and ext not in (".bin",):
                    try:
                        nb, _ = process_bytes(zin.read(n), base, ctx.child())
                        new_data[n] = nb
                        common.log(f"Documento incorporato elaborato: {base}")
                    except Exception as e:
                        ctx.note(f"oggetto incorporato non elaborabile ({base}): {e}")
                elif ctx.anonymize:
                    ctx.note(f"Oggetto OLE incorporato non analizzabile ({base}): verificarne il contenuto manualmente.")
            elif low.startswith("docprops/thumbnail") and ctx.anonymize:
                removed.add(n)

        if removed:
            _drop_parts(removed, new_data, zin, rels)

        write_zip(out_path, zin, infos, new_data, removed)
    return None


def clone_zipinfo(info):
    """Nuovo ZipInfo con i soli metadati utili (evita di ricopiare campi extra/zip64 non piu' validi)."""
    zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    zi.compress_type = info.compress_type
    zi.external_attr = info.external_attr
    zi.create_system = info.create_system
    zi.comment = info.comment
    return zi


def write_zip(out_path, zin, infos, new_data, removed=()):
    """Riscrive l'archivio mantenendo ordine e metodo di compressione (es. 'mimetype' ODF non compresso)."""
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zout:
        for info in infos:
            if info.filename in removed:
                continue
            data = new_data[info.filename] if info.filename in new_data else zin.read(info.filename)
            zout.writestr(clone_zipinfo(info), data)


def _drop_parts(removed, new_data, zin, rels):
    root_rels = "_rels/.rels"
    tree = rels.get(root_rels)
    if tree is not None:
        for rel in list(tree):
            target = (rel.get("Target") or "").lstrip("/")
            if target in removed:
                tree.remove(rel)
        new_data[root_rels] = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)
    try:
        ct = etree.fromstring(zin.read("[Content_Types].xml"), _PARSER)
        for ov in list(ct):
            if (ov.get("PartName") or "").lstrip("/") in removed:
                ct.remove(ov)
        new_data["[Content_Types].xml"] = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True)
    except Exception:
        pass


# ------------------------------------------------------------------------------------------------
def _collect(kind, trees, col, ctx, sheet_renames, sst_map):
    person = _PERSON if ctx.settings.get("censor_person", True) else None
    for name, root in trees.items():
        low = name.lower()
        if low.startswith("docprops/"):
            _collect_docprops(name, root, col, person)
            continue
        # Paragrafi WordprocessingML (Word, caselle di testo, commenti, note)
        if kind == "docx":
            for segs in _paragraph_segments(root, W_P, W_T, {W_TAB[0]: "\t", W_TAB[1]: "\t", W_BR[0]: "\n",
                                                             W_BR[1]: "\n", W_CR[0]: "\n", W_CR[1]: "\n",
                                                             W_NBH[0]: "-", W_NBH[1]: "-"}, _set_text_preserve):
                col.segments(name, segs)
            for segs in _paragraph_segments(root, W_P, W_DELTEXT, {}, _set_text_preserve):
                col.segments(name, segs)
            for segs in _paragraph_segments(root, W_P, W_INSTR, {}, _set_text_preserve):
                col.segments(name, segs)
            for el in root.iter(*W_FLDSIMPLE):
                for k in list(el.attrib):
                    if _local(k) == "instr":
                        col.text(name, el.get(k), lambda v, e=el, kk=k: e.set(kk, v))
        # Paragrafi DrawingML (PowerPoint, forme, grafici, SmartArt, disegni Excel)
        for segs in _paragraph_segments(root, A_P, A_T, {A_BR[0]: "\n", A_BR[1]: "\n"}, _set_text):
            col.segments(name, segs)
        # Valori stringa memorizzati nei grafici
        for el in root.iter(*C_V):
            par = el.getparent()
            gp = par.getparent() if par is not None else None
            if (par is not None and par.tag in C_TX) or (gp is not None and gp.tag in C_STRCACHE):
                col.text(name, el.text, lambda v, e=el: _set_text(e, v))
        if kind == "xlsx":
            _collect_xlsx_part(name, root, col, person, sheet_renames, sst_map)
        # Attributi con nomi di persone / testi alternativi
        for el in root.iter():
            if not isinstance(el.tag, str):
                continue
            tag_local = _local(el.tag)
            for k, v in list(el.attrib.items()):
                lk = _local(k)
                if not v or not v.strip():
                    continue
                if lk == "author" or (lk == "name" and tag_local in ("cmAuthor", "author")) or lk == "displayName":
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv), force=person)
                elif lk == "initials" and tag_local in ("cmAuthor", "author", "comment", "person"):
                    if ctx.anonymize:
                        el.set(k, "--")
                elif lk in ("userId", "providerId") and "@" in v:
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv))
                elif lk in ("descr", "title") and tag_local in ("docPr", "cNvPr"):
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv))
        # Parti XML personalizzate (customXml): tutti i nodi di testo
        if low.startswith("customxml/"):
            for el in root.iter():
                if isinstance(el.tag, str) and el.text and el.text.strip() and len(el) == 0:
                    col.text(name, el.text, lambda v, e=el: _set_text(e, v), context=_local(el.tag) + ": ")


def _collect_docprops(name, root, col, person):
    for el in root.iter():
        if not isinstance(el.tag, str) or not el.text or not el.text.strip():
            continue
        lk = _local(el.tag)
        if lk in ("creator", "lastModifiedBy", "Manager"):
            col.text(name, el.text, lambda v, e=el: _set_text(e, v), force=person)
        elif lk in ("title", "subject", "keywords", "description", "category", "contentStatus", "Company",
                    "HyperlinkBase", "lpwstr"):
            col.text(name, el.text, lambda v, e=el: _set_text(e, v))


def _si_segments(si):
    segs = []
    for child in si:
        if child.tag in S_T:
            segs.append(Segment(child.text or "", setter=lambda v, e=child: _set_text_preserve(e, v)))
        elif child.tag in S_R:
            for t in child:
                if t.tag in S_T:
                    segs.append(Segment(t.text or "", setter=lambda v, e=t: _set_text_preserve(e, v)))
    return segs


def _collect_xlsx_part(name, root, col, person, sheet_renames, sst_map):
    tag = _local(root.tag)
    if tag == "sst":
        for si in root:
            if si.tag in S_SI:
                segs = _si_segments(si)
                if not segs:
                    continue
                old = segments_text(segs)

                def _ap(r, s=segs, o=old):
                    if not r:
                        return False
                    apply_to_segments(s, r)
                    sst_map[o] = segments_text(s)
                    return True
                if old.strip():
                    col.units.append(Unit(old))
                    col.appliers.append((name, _ap))
    elif tag == "worksheet":
        for c in root.iter(*_q(S_NS, "c")):
            t = c.get("t")
            if t == "inlineStr":
                for is_ in c:
                    if _local(is_.tag) == "is":
                        col.segments(name, _si_segments(is_))
            elif t == "str":
                for v in c:
                    if _local(v.tag) == "v" and v.text:
                        col.text(name, v.text, lambda nv, e=v: _set_text(e, nv))
        for hf in root.iter(*_q(S_NS, "headerFooter")):
            for el in hf:
                if el.text and el.text.strip():
                    col.text(name, el.text, lambda v, e=el: _set_text(e, v))
    elif tag == "comments":
        for el in root.iter():
            lk = _local(el.tag)
            if lk == "author" and el.text:
                col.text(name, el.text, lambda v, e=el: _set_text(e, v), force=person)
            elif lk == "text":
                col.segments(name, _si_segments(el))
    elif tag == "ThreadedComments":
        for el in root.iter():
            if _local(el.tag) == "text" and el.text:
                col.text(name, el.text, lambda v, e=el: _set_text(e, v))
    elif tag == "workbook":
        for sh in root.iter(*_q(S_NS, "sheet")):
            old = sh.get("name")
            if old:
                col.text(name, old, lambda nv, e=sh, o=old: sheet_renames.__setitem__(o, (e, nv)))
    elif tag == "pivotCacheDefinition":
        for el in root.iter():
            if _local(el.tag) == "s" and el.get("v"):
                col.text(name, el.get("v"), lambda nv, e=el: e.set("v", nv))


def _collect_rels(rels, col):
    for name, root in rels.items():
        for rel in root:
            if rel.get("TargetMode") != "External":
                continue
            target = rel.get("Target") or ""
            if target.lower().startswith(("mailto:", "tel:", "file:", "callto:", "sms:")) or re.match(r"^[A-Za-z]:\\", target):
                col.text(name, target, lambda v, e=rel: e.set("Target", v))


# ------------------------------------------------------------------------------------------------
_SHEET_BAD = re.compile(r"[\[\]:*?/\\]")


def _replace_sheet_refs(text, renames):
    if not text:
        return text
    out = text
    for old, new in renames.items():
        q_new = "'" + new.replace("'", "''") + "'!"
        out = out.replace("'" + old.replace("'", "''") + "'!", q_new)
        if re.fullmatch(r"[A-Za-z_À-ɏ][\w.À-ɏ]*", old):
            out = re.sub(r"(?<![\w.'!])" + re.escape(old) + r"!", lambda m: q_new, out)
    return out


def _finish_xlsx(trees, sheet_renames, sst_map):
    changed = set()
    renames = {}
    used = set()
    wb_name = None
    for name, root in trees.items():
        if _local(root.tag) == "workbook":
            wb_name = name
            for sh in root.iter(*_q(S_NS, "sheet")):
                used.add((sh.get("name") or "").lower())
    for old, (el, new_raw) in sheet_renames.items():
        new = _SHEET_BAD.sub("", new_raw).strip().strip("'")[:31] or "Foglio"
        if new == old:
            continue
        used.discard(old.lower())
        base, k = new, 2
        while new.lower() in used:
            suffix = f" ({k})"
            new = base[:31 - len(suffix)] + suffix
            k += 1
        used.add(new.lower())
        el.set("name", new)
        renames[old] = new
    if renames and wb_name:
        changed.add(wb_name)
        for name, root in trees.items():
            touched = False
            for el in root.iter():
                lk = _local(el.tag) if isinstance(el.tag, str) else ""
                if lk in ("f", "definedName") and el.text:
                    nt = _replace_sheet_refs(el.text, renames)
                    if nt != el.text:
                        el.text = nt
                        touched = True
                elif lk == "worksheetSource" and el.get("sheet") in renames:
                    el.set("sheet", renames[el.get("sheet")])
                    touched = True
                elif lk == "lpstr" and el.text in renames:
                    el.text = renames[el.text]
                    touched = True
            if touched:
                changed.add(name)
    if sst_map:
        # Le intestazioni delle tabelle Excel devono coincidere con il testo delle celle
        for name, root in trees.items():
            if _local(root.tag) != "table":
                continue
            touched = False
            for tc in root.iter(*_q(S_NS, "tableColumn")):
                nm = tc.get("name")
                if nm in sst_map and sst_map[nm] != nm:
                    tc.set("name", sst_map[nm])
                    touched = True
            if touched:
                changed.add(name)
    return changed
