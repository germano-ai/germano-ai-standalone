"""Estrazione rapida del testo di un file, per riconoscere i documenti "di ritorno dall'AI"
(contenenti etichette del vault come [PERSONA_1]) da ripristinare invece che anonimizzare."""
import html
import os
import re
import zipfile

_TAG_STRIP = re.compile(r"<[^>]+>")
_PARA_END = re.compile(r"</(?:w:p|a:p|text:p|text:h|si|row)>")
_MAX_FILE = 64 * 1024 * 1024


def _xml_text(xml_bytes):
    s = xml_bytes.decode("utf-8", errors="replace")
    s = _PARA_END.sub("\n", s)
    return html.unescape(_TAG_STRIP.sub("", s))


def _container_text(path, ext, max_chars, depth):
    """Testo dei file contenuti in uno ZIP o in una busta .p7m."""
    import tempfile
    from .. import common
    if depth > 2:
        return ""
    os.makedirs(common.WORK_TMP_DIR, exist_ok=True)
    out = []
    with tempfile.TemporaryDirectory(dir=common.WORK_TMP_DIR) as d:
        items = []
        if ext == ".p7m":
            from .p7m import extract_signed_content, _guess_ext
            with open(path, "rb") as f:
                content = extract_signed_content(f.read())
            inner = os.path.basename(path)[:-4]
            if not os.path.splitext(inner)[1]:
                inner += _guess_ext(content)
            items.append((inner, content))
        else:
            with zipfile.ZipFile(path) as z:
                for info in z.infolist()[:500]:
                    if info.is_dir() or info.flag_bits & 0x1 or info.file_size > _MAX_FILE:
                        continue
                    items.append((os.path.basename(info.filename), z.read(info)))
        for i, (name, data) in enumerate(items):
            p = os.path.join(d, f"{i}_{name}")
            with open(p, "wb") as f:
                f.write(data)
            try:
                out.append(sample_text(p, max_chars, depth + 1))
            except Exception:
                pass
            if sum(len(x) for x in out) > max_chars:
                break
    return "\n".join(out)[:max_chars]


def sample_text(path, max_chars=3_000_000, depth=0):
    from . import TEXT_EXTS, OOXML_EXTS, ODF_EXTS
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXTS or ext in (".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".xml", ".html", ".htm", ".xhtml", ".eml"):
        with open(path, "rb") as f:
            data = f.read(_MAX_FILE)
        from .textlike import decode_bytes
        return decode_bytes(data)[0][:max_chars]
    if ext in OOXML_EXTS or ext in ODF_EXTS:
        out = []
        size = 0
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                low = n.lower()
                if not low.endswith(".xml") or "/_rels/" in low or low.startswith("[content_types]"):
                    continue
                if ext in ODF_EXTS and os.path.basename(low) not in ("content.xml", "styles.xml"):
                    continue
                t = _xml_text(z.read(n))
                out.append(t)
                size += len(t)
                if size > max_chars:
                    break
        return "\n".join(out)[:max_chars]
    if ext == ".pdf":
        try:
            import pymupdf as fitz
        except ImportError:  # pragma: no cover
            import fitz
        out = []
        size = 0
        with fitz.open(path) as doc:
            if doc.needs_pass:
                return ""
            for i, page in enumerate(doc):
                if i >= 300 or size > max_chars:
                    break
                t = page.get_text()
                out.append(t)
                size += len(t)
        return "\n".join(out)[:max_chars]
    if ext == ".rtf":
        from .rtf import rtf_plain_text
        with open(path, "rb") as f:
            return rtf_plain_text(f.read(_MAX_FILE))[:max_chars]
    if ext == ".zip" or ext == ".p7m":
        return _container_text(path, ext, max_chars, depth)
    if ext in (".doc", ".xls", ".ppt"):
        from .legacy import _sniff
        kind = _sniff(path)
        if kind == "ole" and ext == ".xls":
            try:
                import xlrd
                book = xlrd.open_workbook(path, on_demand=True)
                out = []
                for i in range(book.nsheets):
                    sh = book.sheet_by_index(i)
                    for r in range(sh.nrows):
                        out.extend(str(v) for v in sh.row_values(r) if isinstance(v, str) and v)
                return "\n".join(out)[:max_chars]
            except Exception:
                return ""
        if kind == "rtf":
            from .rtf import rtf_plain_text
            with open(path, "rb") as f:
                return rtf_plain_text(f.read(_MAX_FILE))[:max_chars]
        if kind in ("html", "xml"):
            with open(path, "rb") as f:
                return f.read(_MAX_FILE).decode("utf-8", errors="replace")[:max_chars]
        if kind in ("docx", "xlsx", "pptx"):
            try:
                return sample_text_zip(path, max_chars)
            except Exception:
                return ""
    return ""


def sample_text_zip(path, max_chars):
    out = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.lower().endswith(".xml") and "/_rels/" not in n.lower():
                out.append(_xml_text(z.read(n)))
    return "\n".join(out)[:max_chars]
