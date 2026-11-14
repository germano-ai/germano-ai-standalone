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


def _container_text(path, ext, max_chars, depth, audio=None, headers=False):
    """Testo dei file contenuti in un archivio (ZIP, TAR, GZ, 7Z, RAR...) o in una busta .p7m. Gli archivi si aprono
    con gli stessi controlli di sicurezza dell'elaborazione (formats/archive.py): un file alla volta, con nomi neutri."""
    import tempfile
    from .. import common
    from ..engine import CancelledError
    if depth > 2:
        return ""
    os.makedirs(common.WORK_TMP_DIR, exist_ok=True)
    out, size = [], 0

    def add(name, p):
        nonlocal size
        try:
            t = sample_text(p, max_chars, depth + 1, audio, headers, label=name)
        except CancelledError:
            raise
        except Exception as e:
            from . import reraise_control
            reraise_control(e)
            return
        if t and t.strip():
            out.append(f"### {name}\n{t}" if headers else t)
            size += len(t)

    with tempfile.TemporaryDirectory(dir=common.WORK_TMP_DIR) as d:
        if ext == ".p7m":
            from .p7m import extract_signed_content, _guess_ext
            with open(path, "rb") as f:
                content = extract_signed_content(f.read())
            inner = os.path.basename(path)[:-4]
            if not os.path.splitext(inner)[1]:
                inner += _guess_ext(content)
            p = os.path.join(d, "0_" + common.safe_filename(inner, max_len=80))
            with open(p, "wb") as f:
                f.write(content)
            add(inner, p)
        else:
            from .archive import sample_members
            for name, p in sample_members(path, d, max_member_bytes=_MAX_FILE):
                add(name, p)
                if size > max_chars:
                    break
    return ("\n\n" if headers else "\n").join(out)[:max_chars]


def sample_text(path, max_chars=3_000_000, depth=0, audio=None, headers=False, label=None):
    """`audio`: funzione (percorso, nome) -> testo che trascrive un file audio; senza, i file audio non hanno testo.
    `headers`: i file di un archivio sono preceduti da «### nome» (allegati dell'Harness)."""
    from . import TEXT_EXTS, OOXML_EXTS, ODF_EXTS, ARCHIVE_EXTS, AUDIO_EXTS
    ext = os.path.splitext(path)[1].lower()
    if ext in AUDIO_EXTS:
        return audio(path, label or os.path.basename(path))[:max_chars] if audio is not None else ""
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
    if ext in ARCHIVE_EXTS or ext == ".p7m":
        return _container_text(path, ext, max_chars, depth, audio, headers)
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
