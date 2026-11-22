"""OpenDocument (ODT/ODS/ODP): testo, intestazioni/pie' di pagina, note, commenti, revisioni, metadati,
immagini e oggetti incorporati. La miniatura (che mostra la prima pagina originale) viene sostituita."""
import io
import os
import re
import zipfile

from lxml import etree

from ..analyzer import Segment, Unit, apply_to_segments, segments_text
from . import ProcessingError, process_embedded, reraise_control
from .ooxml import (_Collector, write_zip, _PARSER, _local, unreadable_part, check_unique_names, restore_sheet_name,
                    safe_zip_read, ZIP_MAX_ENTRIES, ZIP_MAX_TOTAL_BYTES, _VECTOR_EXTS, _blank_png_bytes, _SHEET_BAD)

NS_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
NS_OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
NS_DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
NS_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
NS_META = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XLINK = "http://www.w3.org/1999/xlink"
NS_SVG = "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
NS_FORM = "urn:oasis:names:tc:opendocument:xmlns:form:1.0"
NS_MANIFEST = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"

T = lambda n: "{%s}%s" % (NS_TEXT, n)  # noqa: E731
O = lambda n: "{%s}%s" % (NS_OFFICE, n)  # noqa: E731,E741

P_TAGS = {T("p"), T("h")}
SPACE_TAGS = {T("s"), T("tab"), T("line-break"), T("soft-page-break")}
NO_DESCEND = {
    "{%s}annotation" % NS_OFFICE, "{%s}annotation-end" % NS_OFFICE, T("note"), "{%s}frame" % NS_DRAW,
    "{%s}custom-shape" % NS_DRAW, "{%s}text-box" % NS_DRAW, "{%s}table" % NS_TABLE, T("tracked-changes"),
}
_RASTER_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
CELL_TAGS = {"{%s}table-cell" % NS_TABLE, "{%s}covered-table-cell" % NS_TABLE}
TABLE_TAG = "{%s}table" % NS_TABLE
TABLE_NAME = "{%s}name" % NS_TABLE
# Valore «vero» di una cella non di testo: LibreOffice mostra QUESTO, non il paragrafo (che e' solo la sua resa)
_CELL_VALUE_ATTRS = (O("value"), O("date-value"), O("time-value"), O("boolean-value"), O("currency"))
_VALUE_TYPE_ATTRS = (O("value-type"), "{urn:org:documentfoundation:names:experimental:calc:xmlns:calcext:1.0}value-type")
# attributi che contengono riferimenti a celle (da aggiornare quando un foglio cambia nome)
_REF_ATTRS = {"formula", "cell-range-address", "base-cell-address", "target-range-address", "print-ranges",
              "condition", "values-cell-range-address", "label-cell-address", "label-cell-range-address",
              "cell-range", "source-cell-range-addresses", "cell-address", "end-cell-address"}
_SIGNATURE_FILES = {"meta-inf/documentsignatures.xml", "meta-inf/macrosignatures.xml",
                    "meta-inf/packagesignatures.xml"}
_OLE_MEDIA_TYPE = "application/vnd.sun.star.oleobject"


def _space_text(el):
    tag = el.tag
    if tag == T("s"):
        try:
            return " " * min(4096, max(1, int(el.get(T("c")) or 1)))
        except ValueError:
            return " "
    if tag == T("tab"):
        return "\t"
    if tag == T("line-break"):
        return "\n"
    return ""


def _walk(el, segs):
    if el.text:
        segs.append(Segment(el.text, setter=lambda v, e=el: setattr(e, "text", v)))
    for child in el:
        tag = child.tag
        if isinstance(tag, str):
            if tag in SPACE_TAGS:
                segs.append(Segment(_space_text(child), writable=False))
            elif tag in NO_DESCEND:
                pass
            else:
                _walk(child, segs)
        if child.tail:
            segs.append(Segment(child.tail, setter=lambda v, c=child: setattr(c, "tail", v)))


def _cell_to_string(cell):
    """La cella diventa di testo: il numero o la data originali non devono restare negli attributi del valore."""
    for attr in _CELL_VALUE_ATTRS:
        if attr in cell.attrib:
            del cell.attrib[attr]
    for attr in _VALUE_TYPE_ATTRS:
        if attr in cell.attrib or attr == _VALUE_TYPE_ATTRS[0]:
            cell.set(attr, "string")


def _collect(name, root, col, person, ctx, sheet_renames):
    for p in root.iter(*P_TAGS):
        segs = []
        _walk(p, segs)
        cell = p.getparent()
        if cell is not None and cell.tag in CELL_TAGS and cell.get(O("value-type")) not in (None, "string") \
                and any(a in cell.attrib for a in _CELL_VALUE_ATTRS):
            # Cella numerica, data, ora, valuta: il paragrafo e' solo la resa del valore scritto negli attributi
            # (office:value="3331234567", office:date-value="1980-01-01"). Sostituire il solo paragrafo non basta:
            # riaprendo il foglio LibreOffice mostra di nuovo il valore originale.
            text = segments_text(segs)
            if text.strip():
                def _ap(r, s=segs, c=cell):
                    if not apply_to_segments(s, r):
                        return False
                    _cell_to_string(c)
                    return True
                col.units.append(Unit(text))
                col.appliers.append((name, _ap))
            continue
        col.segments(name, segs)
    drop = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        lk = _local(el.tag)
        ns = el.tag[1:].split("}", 1)[0] if el.tag.startswith("{") else ""
        if ns == NS_DC and lk == "creator" and el.text:
            col.text(name, el.text, lambda v, e=el: setattr(e, "text", v), force=person)
        elif ns == NS_META and lk in ("initial-creator", "printed-by") and el.text:
            col.text(name, el.text, lambda v, e=el: setattr(e, "text", v), force=person)
        elif (ns == NS_DC and lk in ("title", "subject", "description")) or (ns == NS_META and lk in ("keyword", "user-defined")):
            if el.text:
                col.text(name, el.text, lambda v, e=el: setattr(e, "text", v))
        elif ns == NS_SVG and lk in ("title", "desc") and el.text:
            # titolo e descrizione di immagini e forme (testo alternativo)
            col.text(name, el.text, lambda v, e=el: setattr(e, "text", v))
        elif ns == NS_META and lk == "template" and ctx.anonymize:
            # modello usato: percorso sul computer di chi ha scritto il documento (cartella utente) e titolo
            drop.append(el)
            continue
        elif el.tag == TABLE_TAG and el.get(TABLE_NAME):
            # nome del foglio (Calc) o della tabella: «Mario Rossi», «Cliente Bianchi»...
            old = el.get(TABLE_NAME)
            if ctx.anonymize:
                col.text(name, old, lambda nv, e=el, o=old, part=name: sheet_renames.setdefault(o, []).append((part, e, nv)))
            else:
                new = restore_sheet_name(old, ctx)
                if new != old:
                    sheet_renames.setdefault(old, []).append((name, el, new))
        href = el.get("{%s}href" % NS_XLINK)
        if href and href.lower().startswith(("mailto:", "tel:", "callto:", "sms:")):
            col.text(name, href, lambda v, e=el: e.set("{%s}href" % NS_XLINK, v))
        for attr in (O("string-value"), T("string-value")):
            sv = el.get(attr)
            if sv:
                col.text(name, sv, lambda v, e=el, a=attr: e.set(a, v))
        if ns == NS_FORM:
            # campi dei moduli: valore corrente, valore predefinito, etichetta
            for attr in ("current-value", "value", "label"):
                fv = el.get("{%s}%s" % (NS_FORM, attr))
                if fv and fv.strip():
                    col.text(name, fv, lambda v, e=el, a="{%s}%s" % (NS_FORM, attr): e.set(a, v))
    for el in drop:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)
            col.touched.add(name)


def _replace_sheet_refs(text, renames):
    """Riferimenti ai fogli nelle formule e negli intervalli di OpenDocument: «'Mario Rossi'.A1», «$Foglio1.$A$1»."""
    out = text
    for old, new in renames.items():
        q_new = "'" + new.replace("'", "''") + "'."
        out = out.replace("'" + old.replace("'", "''") + "'.", q_new)
        if re.fullmatch(r"[A-Za-z_À-ɏ][\wÀ-ɏ]*", old):
            out = re.sub(r"(?<![\w.'])" + re.escape(old) + r"\.", lambda m: q_new, out)
    return out


def _finish_sheets(trees, sheet_renames):
    """Applica i nuovi nomi dei fogli (validi e unici) e aggiorna i riferimenti nelle formule e negli intervalli."""
    changed = set()
    renames = {}
    todo = {}
    for old, items in sheet_renames.items():
        for part, el, new_raw in items:
            todo.setdefault(part, []).append((old, el, new_raw))
    # i nomi sono unici dentro ogni documento (quello principale e ciascun oggetto incorporato); i riferimenti degli
    # oggetti incorporati (grafici) puntano ai fogli del documento principale, che quindi si elabora per primo
    for part in sorted(todo, key=lambda p: (p != "content.xml", p)):
        used = {(t.get(TABLE_NAME) or "").lower() for t in trees[part].iter(TABLE_TAG)}
        for old, el, new_raw in todo[part]:
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
            el.set(TABLE_NAME, new)
            renames.setdefault(old, new)
            changed.add(part)
    if renames:
        for name, root in trees.items():
            touched = False
            for el in root.iter():
                if not isinstance(el.tag, str):
                    continue
                for k, v in list(el.attrib.items()):
                    lk = _local(k)
                    if (lk in _REF_ATTRS or (lk == "href" and v.startswith("#"))) and any(o in v for o in renames):
                        nv = _replace_sheet_refs(v, renames)
                        if nv != v:
                            el.set(k, nv)
                            touched = True
            if touched:
                changed.add(name)
    return changed


def _blank_png_like(data):
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as im:
            size = im.size
    except Exception:
        size = (256, 256)
    buf = io.BytesIO()
    Image.new("RGB", size, (255, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


def _manifest(zin, names, budget):
    """(albero di META-INF/manifest.xml, {percorso: tipo}) oppure (None, {}) se manca o non si legge (l'elenco dei
    file non contiene testo del documento: un elenco rovinato non impedisce l'elaborazione)."""
    if "META-INF/manifest.xml" not in names:
        return None, {}
    try:
        tree = etree.fromstring(safe_zip_read(zin, "META-INF/manifest.xml", budget), _PARSER)
    except etree.XMLSyntaxError:
        return None, {}
    types = {}
    for entry in tree.iter("{%s}file-entry" % NS_MANIFEST):
        types[entry.get("{%s}full-path" % NS_MANIFEST) or ""] = entry.get("{%s}media-type" % NS_MANIFEST) or ""
    return tree, types


def process_odf(in_path, out_path, ctx):
    if not zipfile.is_zipfile(in_path):
        raise ValueError("Documento OpenDocument non valido o cifrato.")
    person = "[PERSONA]" if ctx.settings.get("censor_person", True) else None
    with zipfile.ZipFile(in_path, "r") as zin:
        infos = zin.infolist()
        if len(infos) > ZIP_MAX_ENTRIES:
            raise ProcessingError("Documento OpenDocument con troppi elementi interni: rifiutato per sicurezza.")
        budget = {"total": 0, "max_total": ZIP_MAX_TOTAL_BYTES}
        names = [i.filename for i in infos]
        check_unique_names(names, "OpenDocument")
        if "content.xml" not in names:
            raise ValueError("Documento OpenDocument privo di content.xml (forse cifrato con password).")
        trees = {}
        for info in infos:
            n = info.filename
            base = n.rsplit("/", 1)[-1]
            if base in ("content.xml", "styles.xml", "meta.xml"):
                try:
                    trees[n] = etree.fromstring(safe_zip_read(zin, info, budget), _PARSER)
                except etree.XMLSyntaxError as e:
                    if base == "content.xml" and n == "content.xml":
                        raise ValueError(f"content.xml non leggibile (documento cifrato?): {e}")
                    raise unreadable_part(n, "OpenDocument") from None
        manifest, media_types = _manifest(zin, set(names), budget)
        col = _Collector()
        col.touched = set()
        sheet_renames = {}
        for n, root in trees.items():
            _collect(n, root, col, person, ctx, sheet_renames)
        changed = col.run(ctx) | col.touched
        changed |= _finish_sheets(trees, sheet_renames)
        new_data = {}
        removed = set()
        for n in changed:
            new_data[n] = etree.tostring(trees[n], xml_declaration=True, encoding="UTF-8")
        def _image_done(name, nb, err):
            if err is not None:
                ctx.note(f"immagine incorporata non elaborata ({os.path.basename(name)}): {err}")
                if ctx.anonymize:
                    new_data[name] = _blank_png_bytes()
            elif nb is not None:
                new_data[name] = nb
        from .images import ImageBatcher
        batcher = ImageBatcher(ctx, _image_done)   # a finestre: un'unica analisi del testo letto per finestra
        signatures = False
        for info in infos:
            n = info.filename
            low = n.lower()
            ext = os.path.splitext(low)[1]
            if n.endswith("/"):
                continue
            if low.startswith("thumbnails/") and ext == ".png" and ctx.anonymize:
                new_data[n] = _blank_png_like(safe_zip_read(zin, info, budget))
            elif low.startswith("pictures/") and ext in _RASTER_EXTS and ctx.vision_enabled():
                ctx.check()
                batcher.add(n, safe_zip_read(zin, info, budget))
            elif low.startswith("pictures/") and ext in _VECTOR_EXTS and ctx.anonymize:
                ctx.check()
                if ext == ".svg":
                    try:
                        from .markup import transform_xml_bytes
                        new_data[n] = transform_xml_bytes(safe_zip_read(zin, info, budget), ctx)
                    except Exception as e:
                        reraise_control(e)
                        removed.add(n)
                        ctx.note(f"immagine vettoriale rimossa per sicurezza ({os.path.basename(n)}): {e}")
                else:
                    removed.add(n)
                    ctx.note(f"immagine vettoriale ({os.path.basename(n)}) rimossa per sicurezza (formato non analizzabile).")
            elif low.startswith("objectreplacements/") and ctx.anonymize:
                # anteprima di un grafico o di un oggetto incorporato, disegnata con i dati ORIGINALI (formato non
                # analizzabile): LibreOffice la rigenera dal contenuto, gia' anonimizzato
                removed.add(n)
            elif low in _SIGNATURE_FILES and ctx.anonymize:
                removed.add(n)
                signatures = True
            elif media_types.get(n) == _OLE_MEDIA_TYPE:
                # oggetto OLE incorporato (un foglio Excel, un documento Word dentro il documento)
                ctx.check()
                data = safe_zip_read(zin, info, budget)
                nb, reason = process_embedded(data, ctx)
                if nb is None:
                    removed.add(n)
                    ctx.note(f"oggetto incorporato rimosso per sicurezza ({os.path.basename(n)}): {reason}.")
                elif nb != data:
                    new_data[n] = nb
        batcher.flush()
        if signatures:
            ctx.note("Firma digitale rimossa dal documento OpenDocument (conteneva i dati del firmatario; dopo la "
                     "modifica non sarebbe piu' valida).")
        if removed and manifest is not None:
            # l'elenco dei file del pacchetto non deve nominare parti che non ci sono piu'
            for entry in list(manifest.iter("{%s}file-entry" % NS_MANIFEST)):
                if entry.get("{%s}full-path" % NS_MANIFEST) in removed:
                    entry.getparent().remove(entry)
            new_data["META-INF/manifest.xml"] = etree.tostring(manifest, xml_declaration=True, encoding="UTF-8")
        write_zip(out_path, zin, infos, new_data, removed, budget=budget)
    return None
