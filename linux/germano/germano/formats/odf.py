"""OpenDocument (ODT/ODS/ODP): testo, intestazioni/pie' di pagina, note, commenti, revisioni, metadati,
immagini e oggetti incorporati. La miniatura (che mostra la prima pagina originale) viene sostituita."""
import io
import os
import zipfile

from lxml import etree

from ..analyzer import Segment
from .ooxml import _Collector, write_zip, _PARSER, _local, unreadable_part

NS_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
NS_OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
NS_DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
NS_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
NS_META = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XLINK = "http://www.w3.org/1999/xlink"

T = lambda n: "{%s}%s" % (NS_TEXT, n)  # noqa: E731

P_TAGS = {T("p"), T("h")}
SPACE_TAGS = {T("s"), T("tab"), T("line-break"), T("soft-page-break")}
NO_DESCEND = {
    "{%s}annotation" % NS_OFFICE, "{%s}annotation-end" % NS_OFFICE, T("note"), "{%s}frame" % NS_DRAW,
    "{%s}custom-shape" % NS_DRAW, "{%s}text-box" % NS_DRAW, "{%s}table" % NS_TABLE, T("tracked-changes"),
}
_RASTER_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}


def _space_text(el):
    tag = el.tag
    if tag == T("s"):
        try:
            return " " * max(1, int(el.get(T("c")) or 1))
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


def _collect(name, root, col, person):
    for p in root.iter(*P_TAGS):
        segs = []
        _walk(p, segs)
        col.segments(name, segs)
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        lk = _local(el.tag)
        ns = el.tag[1:].split("}", 1)[0] if el.tag.startswith("{") else ""
        if ns == NS_DC and lk == "creator" and el.text:
            col.text(name, el.text, lambda v, e=el: setattr(e, "text", v), force=person)
        elif ns == NS_META and lk == "initial-creator" and el.text:
            col.text(name, el.text, lambda v, e=el: setattr(e, "text", v), force=person)
        elif (ns == NS_DC and lk in ("title", "subject", "description")) or (ns == NS_META and lk in ("keyword", "user-defined")):
            if el.text:
                col.text(name, el.text, lambda v, e=el: setattr(e, "text", v))
        href = el.get("{%s}href" % NS_XLINK)
        if href and href.lower().startswith(("mailto:", "tel:", "callto:", "sms:")):
            col.text(name, href, lambda v, e=el: e.set("{%s}href" % NS_XLINK, v))
        sv = el.get("{%s}string-value" % NS_OFFICE)
        if sv:
            col.text(name, sv, lambda v, e=el: e.set("{%s}string-value" % NS_OFFICE, v))


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


def process_odf(in_path, out_path, ctx):
    if not zipfile.is_zipfile(in_path):
        raise ValueError("Documento OpenDocument non valido o cifrato.")
    person = "[PERSONA]" if ctx.settings.get("censor_person", True) else None
    with zipfile.ZipFile(in_path, "r") as zin:
        infos = zin.infolist()
        names = [i.filename for i in infos]
        if "content.xml" not in names:
            raise ValueError("Documento OpenDocument privo di content.xml (forse cifrato con password).")
        trees = {}
        for n in names:
            base = n.rsplit("/", 1)[-1]
            if base in ("content.xml", "styles.xml", "meta.xml"):
                try:
                    trees[n] = etree.fromstring(zin.read(n), _PARSER)
                except etree.XMLSyntaxError as e:
                    if base == "content.xml" and n == "content.xml":
                        raise ValueError(f"content.xml non leggibile (documento cifrato?): {e}")
                    raise unreadable_part(n, "OpenDocument") from None
        col = _Collector()
        for n, root in trees.items():
            _collect(n, root, col, person)
        changed = col.run(ctx)
        new_data = {}
        for n in changed:
            new_data[n] = etree.tostring(trees[n], xml_declaration=True, encoding="UTF-8")
        for n in names:
            low = n.lower()
            ext = os.path.splitext(low)[1]
            if low.startswith("thumbnails/") and ext == ".png" and ctx.anonymize:
                new_data[n] = _blank_png_like(zin.read(n))
            elif low.startswith("pictures/") and ext in _RASTER_EXTS and ctx.vision_enabled():
                ctx.check()
                from .images import anonymize_image_bytes
                try:
                    nb = anonymize_image_bytes(zin.read(n), ctx)
                    if nb is not None:
                        new_data[n] = nb
                except Exception as e:
                    ctx.note(f"immagine incorporata non elaborata ({os.path.basename(n)}): {e}")
        write_zip(out_path, zin, infos, new_data)
    return None
