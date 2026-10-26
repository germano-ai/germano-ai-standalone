"""Elaborazione dei formati di file (anonimizzazione e ripristino) con un unico dispatcher."""
import contextlib
import os
import shutil
import tempfile

from .. import common
from ..analyzer import Anonymizer, Restorer, Unit, apply_replacements
from ..detect import Propagator
from ..engine import NO_CANCEL

MAX_DEPTH = 4


class UnsupportedFormat(Exception):
    pass


class ProcessingError(Exception):
    pass


class Ctx:
    """Contesto di elaborazione di un documento (condiviso con i documenti annidati)."""

    def __init__(self, mode, settings, engine=None, vault=None, tag_map=None, cancel=None, progress=None,
                 depth=0, audit=None, notes=None, propagator=None):
        self.mode = mode
        self.settings = settings
        self.engine = engine
        self.vault = vault
        self.tag_map = tag_map or {}
        self.cancel = cancel or NO_CANCEL
        self.progress = progress
        self.depth = depth
        self.audit = audit if audit is not None else []
        self.notes = notes if notes is not None else []
        self.propagator = propagator if propagator is not None else Propagator()
        self.transformer = Anonymizer(self) if mode == "anonymize" else Restorer(self)

    @property
    def anonymize(self):
        return self.mode == "anonymize"

    def child(self):
        if self.depth + 1 > MAX_DEPTH:
            raise ProcessingError("Troppi livelli di file annidati (archivi/allegati).")
        return Ctx(self.mode, self.settings, self.engine, self.vault, self.tag_map, self.cancel, self.progress,
                   self.depth + 1, self.audit, self.notes, self.propagator)

    # -------------------------------------------------------------- analisi
    def analyze(self, units, batch_context=True):
        if not units:
            return []
        return self.transformer.run(units, batch_context=batch_context)

    def analyze_texts(self, texts, batch_context=True):
        units = [Unit(t) for t in texts]
        res = self.analyze(units, batch_context)
        return [apply_replacements(u.text, r) for u, r in zip(units, res)]

    def classify_many(self, texts):
        if self.engine is None:
            return [[] for _ in texts]
        return self.engine.classify_many(texts, self.settings, self.cancel)

    # -------------------------------------------------------------- servizio
    def audit_add(self, word, label, entity, score):
        self.audit.append({"word": word, "label": label, "entity": str(entity), "score": round(float(score), 4)})

    def note(self, msg):
        if msg not in self.notes:
            self.notes.append(msg)
            common.log(f"Avviso: {msg}")

    def check(self):
        self.cancel.check()

    def report(self, detail):
        if self.progress:
            try:
                self.progress(detail)
            except Exception:
                pass

    def vision_enabled(self):
        s = self.settings
        return self.anonymize and self.engine is not None and any(
            s.get(k, True) for k in ("enable_faces", "enable_signatures", "enable_plate_vision", "enable_ocr")
        )

    @contextlib.contextmanager
    def tempdir(self):
        os.makedirs(common.WORK_TMP_DIR, exist_ok=True)
        d = tempfile.mkdtemp(prefix="w_", dir=common.WORK_TMP_DIR)
        try:
            yield d
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------------------------------
# Dispatcher
# ------------------------------------------------------------------------------------------
TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".log", ".ini", ".cfg", ".conf", ".yaml", ".yml", ".sql", ".py", ".js",
    ".ts", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".php", ".rb", ".go", ".rs", ".sh", ".bat", ".cmd",
    ".ps1", ".properties", ".srt", ".vtt", ".rst", ".tex", ".css", ".kt", ".swift", ".vb", ".r", ".m",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
OOXML_EXTS = {
    ".docx", ".docm", ".dotx", ".dotm", ".xlsx", ".xlsm", ".xltx", ".xltm",
    ".pptx", ".pptm", ".potx", ".potm", ".ppsx", ".ppsm",
}
ODF_EXTS = {".odt", ".ods", ".odp", ".ott", ".ots", ".otp", ".odg"}


def processor_for(ext):
    ext = ext.lower()
    if ext in TEXT_EXTS:
        from .textlike import process_text
        return process_text
    if ext in (".csv", ".tsv"):
        from .textlike import process_csv
        return process_csv
    if ext in (".json", ".jsonl", ".ndjson"):
        from .textlike import process_json
        return process_json
    if ext == ".xml":
        from .markup import process_xml
        return process_xml
    if ext in (".html", ".htm", ".xhtml"):
        from .markup import process_html
        return process_html
    if ext == ".pdf":
        from .pdf import process_pdf
        return process_pdf
    if ext in IMAGE_EXTS:
        from .images import process_image
        return process_image
    if ext in OOXML_EXTS:
        from .ooxml import process_ooxml
        return process_ooxml
    if ext in ODF_EXTS:
        from .odf import process_odf
        return process_odf
    if ext == ".eml":
        from .eml import process_eml
        return process_eml
    if ext == ".zip":
        from .archive import process_zip
        return process_zip
    if ext == ".rtf":
        from .rtf import process_rtf
        return process_rtf
    if ext in (".doc", ".dot"):
        from .legacy import process_doc
        return process_doc
    if ext in (".ppt", ".pps", ".pot"):
        from .legacy import process_ppt
        return process_ppt
    if ext == ".xls":
        from .legacy import process_xls
        return process_xls
    if ext == ".p7m":
        from .p7m import process_p7m
        return process_p7m
    return None


def is_supported(path):
    return processor_for(os.path.splitext(path)[1]) is not None


def process_file(in_path, out_path, ctx):
    """Elabora un file. Restituisce il percorso effettivo dell'output (es. .p7m -> file interno)."""
    ext = os.path.splitext(in_path)[1].lower()
    fn = processor_for(ext)
    if fn is None:
        raise UnsupportedFormat(f"Formato file non supportato: {ext or '(senza estensione)'}")
    result = fn(in_path, out_path, ctx)
    return result or out_path


def process_bytes(data, filename, ctx):
    """Elabora un contenuto in memoria (allegati, file incorporati). Restituisce (bytes, nome_output)."""
    name = common.safe_filename(filename or "allegato.bin")
    with ctx.tempdir() as d:
        in_dir = os.path.join(d, "in")
        out_dir = os.path.join(d, "out")
        os.makedirs(in_dir)
        os.makedirs(out_dir)
        src = os.path.join(in_dir, name)
        dst = os.path.join(out_dir, name)
        with open(src, "wb") as f:
            f.write(data)
        real_out = process_file(src, dst, ctx)
        with open(real_out, "rb") as f:
            out = f.read()
        return out, os.path.basename(real_out)


def transform_filename(name, ctx):
    """Anonimizza (o ripristina) un nome di file: 'CV_Mario_Rossi.pdf' -> 'CV_[PERSONA_1].pdf'.
    Un nome di una sola parola senza contesto viene modificato solo se e' gia' stato rilevato nel documento
    (evita falsi positivi come 'dati.bin')."""
    from ..vault import restore_text
    stem, ext = os.path.splitext(name)
    if not stem.strip():
        return name
    if not ctx.anonymize:
        return common.safe_filename(restore_text(stem, ctx.tag_map) + ext)
    spaced = "".join(" " if c in "_-.+" else c for c in stem)
    if len(spaced.split()) >= 2:
        repl = ctx.analyze([Unit(spaced)])[0]
    else:
        repl = []
        deanon = bool(ctx.settings.get("enable_deanonymize", True))
        for a, b, label, group, _key in ctx.propagator.find(spaced):
            word = stem[a:b]
            lab = ctx.vault.label_for(word, label) if (deanon and ctx.vault is not None) else label
            ctx.audit_add(word, lab, group, 1.0)
            repl.append((a, b, lab))
    if not repl:
        return name
    return common.safe_filename(apply_replacements(stem, repl) + ext)


def sample_text(path, max_chars=3_000_000):
    """Testo del documento per riconoscere i file "di ritorno dall'AI" (con etichette del vault)."""
    from .detection import sample_text as _st
    try:
        return _st(path, max_chars)
    except Exception:
        return ""
