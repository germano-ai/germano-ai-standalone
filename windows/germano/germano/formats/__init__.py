"""Elaborazione dei formati di file (anonimizzazione e ripristino) con un unico dispatcher."""
import contextlib
import os
import shutil
import tempfile

from .. import common
from ..analyzer import Anonymizer, Restorer, Unit, apply_replacements
from ..detect import Propagator
from ..engine import NO_CANCEL, CancelledError

MAX_DEPTH = 4


class UnsupportedFormat(Exception):
    pass


class ProcessingError(Exception):
    pass


def reraise_control(exc):
    """Da chiamare in un `except Exception` che tollera gli errori di un elemento annidato (allegato, file di un
    archivio, immagine incorporata): l'annullamento (arresto, tempo scaduto) e il motore remoto non disponibile non
    sono errori di quell'elemento e devono fermare l'intero documento. Altrimenti, con il server remoto caduto a
    meta' documento, gli elementi annidati verrebbero rimossi o lasciati in chiaro invece di attendere il server."""
    from ..remote_engine import EngineUnavailable
    if isinstance(exc, (CancelledError, EngineUnavailable)):
        raise exc


class Ctx:
    """Contesto di elaborazione di un documento (condiviso con i documenti annidati)."""

    def __init__(self, mode, settings, engine=None, vault=None, tag_map=None, cancel=None, progress=None,
                 depth=0, audit=None, notes=None, propagator=None, system2=None, shared=None):
        self.mode = mode
        self.settings = settings
        self.engine = engine
        self.vault = vault
        self.tag_map = tag_map or {}
        self.cancel = cancel or NO_CANCEL
        self.progress = progress
        self.depth = depth
        self.audit = audit if audit is not None else []           # dati oscurati: uno per sostituzione, in ordine
        self.notes = notes if notes is not None else []
        self.propagator = propagator if propagator is not None else Propagator()
        # decisioni del Sistema 2 sui casi dubbi (confermati, rilasciati, incerti): registro a parte, perche' i
        # rilasciati NON sono sostituzioni e l'audit deve restare uno a uno con i dati oscurati
        self.system2 = system2 if system2 is not None else []
        # stato condiviso con i documenti annidati: limiti degli archivi (byte ed elementi decompressi in totale),
        # report di estrazione degli archivi, informazioni sulle trascrizioni audio
        self.shared = shared if shared is not None else {}
        self.transformer = Anonymizer(self) if mode == "anonymize" else Restorer(self)

    @property
    def anonymize(self):
        return self.mode == "anonymize"

    def child(self):
        if self.depth + 1 > MAX_DEPTH:
            raise ProcessingError("Troppi livelli di file annidati (archivi/allegati).")
        c = Ctx(self.mode, self.settings, self.engine, self.vault, self.tag_map, self.cancel, self.progress,
                self.depth + 1, self.audit, self.notes, self.propagator, self.system2, self.shared)
        c.label_override = getattr(self, "label_override", None)   # es. ████ anche negli allegati annidati
        c.archive_label = getattr(self, "archive_label", None)     # percorso logico nell'archivio (per il report)
        return c

    @property
    def reports(self):
        """Voci di report oltre ai dati oscurati (estrazione degli archivi, trascrizioni audio): finiscono nel
        registro di audit accanto alle note. Non sono sostituzioni: restano fuori da `audit`."""
        return list(self.shared.get("archive_report") or []) + list(self.shared.get("audio_report") or [])

    def extend_deadline(self, seconds):
        """Per le elaborazioni la cui durata dipende dal contenuto (trascrizione di una registrazione lunga): sposta
        in avanti il tempo massimo del file, se ne ha uno. L'arresto richiesto dall'utente continua a valere."""
        deadline = getattr(self.cancel, "deadline", None)
        if deadline is not None and self.cancel is not NO_CANCEL:
            import time
            self.cancel.deadline = max(deadline, time.time() + float(seconds))

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

    def resolve_doubts(self, text, spans):
        """Sistema 2 sui casi dubbi del testo (solo con il motore locale; altrimenti i dubbi restano oscurati)."""
        resolve = getattr(self.engine, "resolve_doubts", None)
        if resolve is None or not spans:
            return spans
        kept, decisions = resolve(text, spans, self.settings, self.cancel)
        self.system2.extend(decisions)
        return kept

    # -------------------------------------------------------------- servizio
    def audit_add(self, word, label, entity, score, status="confirmed"):
        self.audit.append({"word": word, "label": label, "entity": str(entity), "score": round(float(score), 4), "status": status})

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
# Audio (v0.80): il parlato viene trascritto offline e il testo passa dal filtro di privacy; in uscita una trascrizione
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".oga", ".opus", ".aac", ".wma", ".amr", ".aiff", ".aif",
              ".m4b", ".mka", ".weba"}
# Archivi compressi (v0.80): contenuto elaborato file per file e archivio ricomposto (formats/archive.py)
ARCHIVE_EXTS = {".zip", ".tar", ".tgz", ".tbz2", ".tbz", ".txz", ".gz", ".bz2", ".xz", ".7z", ".rar"}


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
    if ext in ARCHIVE_EXTS:
        from .archive import process_archive
        return process_archive
    if ext in AUDIO_EXTS:
        from .audio import process_audio
        return process_audio
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
    """Testo del documento per riconoscere i file "di ritorno dall'AI" (con etichette del vault). I file audio non
    hanno testo finche' non vengono trascritti: qui valgono come vuoti (non sono mai file di ritorno)."""
    from .detection import sample_text as _st
    try:
        return _st(path, max_chars)
    except Exception:
        return ""


def extract_text(path, ctx, max_chars=200_000):
    """Testo di un file per gli allegati dell'Harness: come sample_text, ma i file audio vengono trascritti dal
    motore del contesto (anche dentro gli archivi) e i file di un archivio sono preceduti dal loro nome.
    Il testo restituito NON e' protetto: chi chiama lo deve anonimizzare prima di mostrarlo o inviarlo.
    Per un file audio gli errori (registrazione troppo lunga, file danneggiato) arrivano come ProcessingError."""
    from .detection import sample_text as _st

    def audio(p, label):
        from .audio import plain_text, transcribe
        res = transcribe(p, ctx)
        ctx.shared.setdefault("audio_info", []).append({
            "name": label, "duration": round(float(res.get("duration") or 0), 1), "language": res.get("language"),
            "segments": len(res.get("segments") or []), "seconds": res.get("seconds")})
        return plain_text(res)

    ext = os.path.splitext(path)[1].lower()
    if ext in AUDIO_EXTS:
        return audio(path, os.path.basename(path))[:max_chars]
    try:
        return _st(path, max_chars, audio=audio, headers=True)
    except CancelledError:
        raise
    except Exception as e:
        reraise_control(e)
        return ""
