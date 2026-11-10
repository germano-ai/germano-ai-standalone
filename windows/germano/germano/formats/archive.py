"""Archivi compressi: apertura sicura, sanitizzazione ricorsiva e ricomposizione.

Formati: ZIP; TAR (anche .tar.gz/.tgz, .tar.bz2/.tbz2, .tar.xz/.txz); GZ, BZ2 e XZ di un solo file; 7Z e RAR.
ZIP, TAR e i file compressi singoli si leggono e si scrivono con la libreria standard di Python; 7Z e RAR con la
console ufficiale di 7-Zip distribuita con Germano (runtime/7zip). Il formato si riconosce dal contenuto (firma del
file), non dall'estensione.

Sicurezza (l'archivio e' un dato non fidato):
- nessun file viene mai estratto con il nome o il percorso scritto nell'archivio: ogni file interno viene copiato in
  un'area temporanea di Germano (state/tmp) con un nome neutro, un file alla volta, e cancellato subito dopo. 7-Zip
  non scrive mai su disco: i dati arrivano in flusso (-so) e li scrive Germano, controllando dimensione e CRC di
  ogni file. Il Path Traversal e' quindi impossibile per costruzione; in piu' gli archivi che contengono percorsi
  assoluti, unita' («C:») o componenti «..» vengono rifiutati per intero;
- bomba di decompressione: limite al numero di elementi, alla dimensione di ogni file interno, al totale dei dati
  decompressi (archivi annidati compresi) e al rapporto di espansione rispetto alla dimensione dell'archivio. I
  limiti si applicano ai byte realmente letti, non solo a quelli dichiarati nelle intestazioni;
- collegamenti simbolici, collegamenti fisici e file speciali non vengono mai seguiti ne' ricreati;
- annidamento limitato (formats.MAX_DEPTH), anche attraverso email e documenti con allegati.

Principio «fail-safe»: in anonimizzazione un file interno che non si puo' elaborare (formato non supportato, protetto
da password, danneggiato) NON viene copiato in chiaro nel nuovo archivio; viene escluso e l'esclusione e' scritta nel
report. Se nessun file interno puo' essere elaborato l'archivio finisce tra i non riusciti.

Ricomposizione: il nuovo archivio ha lo stesso formato e la stessa gerarchia di cartelle dell'originale, con ogni
file sostituito dalla sua versione bonificata (o ripristinata). Il formato RAR e' proprietario e non si puo' creare:
un archivio RAR viene restituito come ZIP (nome.rar.zip). Nel nuovo archivio non restano commenti, campi extra,
nomi utente o gruppi del sistema di origine (TAR), ne' il nome originale nell'intestazione GZ.
"""
import bz2
import gzip
import lzma
import os
import re
import shutil
import stat
import subprocess
import tarfile
import time
import uuid
import zipfile
import zlib

from .. import common
from ..engine import CancelledError
from . import ProcessingError, is_supported, process_file, reraise_control, transform_filename

# ------------------------------------------------------------------------------------------ limiti
MAX_ENTRIES = 20000                      # elementi di un archivio
MAX_ENTRIES_TOTAL = 60000                # elementi in totale, archivi annidati compresi
MAX_TOTAL_BYTES = 4 * 1024 ** 3          # dati decompressi in totale (archivi annidati compresi)
MAX_MEMBER_BYTES = 2 * 1024 ** 3         # un singolo file interno
MAX_RATIO = 200                          # espansione massima rispetto alla dimensione dell'archivio...
RATIO_MIN_BYTES = 50 * 1024 ** 2         # ...valutata solo oltre questa quantita' di dati decompressi
MAX_NAME_BYTES = 4096                    # percorso di un elemento
MAX_COMPONENT_BYTES = 255                # un nome di file o di cartella
SAMPLE_MEMBERS = 500                     # anteprima del testo (file di ritorno dall'AI, allegati dell'Harness)
SAMPLE_MEMBER_BYTES = 64 * 1024 ** 2
SEVENZIP_LIST_TIMEOUT = 300

_COMP_EXT = {"gz": ".gz", "bz2": ".bz2", "xz": ".xz"}
_TAR_SHORT = {".tgz": "gz", ".tbz2": "bz2", ".tbz": "bz2", ".txz": "xz"}
ARCHIVE_EXTS = {".zip", ".tar", ".tgz", ".tbz2", ".tbz", ".txz", ".gz", ".bz2", ".xz", ".7z", ".rar"}
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


class Member:
    """Elemento di un archivio. kind: file | dir | link | special."""
    __slots__ = ("name", "kind", "size", "mtime", "mode", "encrypted", "crc", "raw")

    def __init__(self, name, kind="file", size=0, mtime=None, mode=None, encrypted=False, crc=None, raw=None):
        self.name, self.kind, self.size, self.mtime = name, kind, int(size or 0), mtime
        self.mode, self.encrypted, self.crc, self.raw = mode, encrypted, crc, raw


class Budget:
    """Conteggio condiviso con gli archivi annidati: elementi e byte realmente decompressi."""

    def __init__(self):
        self.bytes = 0
        self.entries = 0

    def add_entries(self, n=1):
        self.entries += n
        if self.entries > MAX_ENTRIES_TOTAL:
            raise ProcessingError(f"Archivio con troppi elementi (oltre {MAX_ENTRIES_TOTAL:,}, archivi annidati "
                                  "compresi): elaborazione bloccata.".replace(",", "."))

    def add_bytes(self, n):
        self.bytes += n
        if self.bytes > MAX_TOTAL_BYTES:
            raise ProcessingError("Archivio sospetto o troppo grande: i dati decompressi superano "
                                  f"{MAX_TOTAL_BYTES / 1024 ** 3:.0f} GB (possibile bomba di decompressione). "
                                  "Elaborazione bloccata.")


def _budget(ctx):
    shared = getattr(ctx, "shared", None)
    if shared is None:
        return Budget()
    if "archive_budget" not in shared:
        shared["archive_budget"] = Budget()
    return shared["archive_budget"]


def _report(ctx):
    shared = getattr(ctx, "shared", None)
    return shared.setdefault("archive_report", []) if shared is not None else []


class _Guard:
    """Limiti applicati ai byte realmente letti da UN archivio (piu' il conteggio condiviso con gli annidati)."""

    def __init__(self, ctx, budget, packed_size):
        self.ctx, self.budget = ctx, budget
        self.packed = max(1, int(packed_size or 1))
        self.read = 0

    def chunk(self, n):
        self.read += n
        self.budget.add_bytes(n)
        if self.read > RATIO_MIN_BYTES and self.read / self.packed > MAX_RATIO:
            raise ProcessingError("Archivio sospetto (bomba di decompressione): i dati decompressi superano di oltre "
                                  f"{MAX_RATIO} volte la dimensione dell'archivio. Elaborazione bloccata.")
        self.ctx.check()

    def declared(self, total):
        """Controllo preventivo sulle dimensioni dichiarate nelle intestazioni (prima di leggere i dati)."""
        if self.budget.bytes + total > MAX_TOTAL_BYTES:
            raise ProcessingError("Archivio troppo grande o sospetto: dichiara "
                                  f"{total / 1024 ** 3:.1f} GB di dati decompressi (limite "
                                  f"{MAX_TOTAL_BYTES / 1024 ** 3:.0f} GB, archivi annidati compresi). Elaborazione "
                                  "bloccata.")
        if total > RATIO_MIN_BYTES and total / self.packed > MAX_RATIO:
            raise ProcessingError("Archivio sospetto (bomba di decompressione): dichiara dati decompressi oltre "
                                  f"{MAX_RATIO} volte la propria dimensione. Elaborazione bloccata.")


# ------------------------------------------------------------------------------------------ nomi
def safe_member_name(name):
    """Percorso di un elemento normalizzato con «/» (senza «./» e barre doppie). ProcessingError se il percorso e'
    pericoloso: assoluto, con un'unita' («C:»), di rete, con componenti «..» o con caratteri di controllo."""
    raw = str(name or "")
    shown = _CTRL_RE.sub("?", raw)[:120]
    if _CTRL_RE.search(raw):
        raise ProcessingError(f"Archivio rifiutato: un elemento ha caratteri di controllo nel nome («{shown}»).")
    n = raw.replace("\\", "/")
    if n.startswith("/") or _DRIVE_RE.match(n):
        raise ProcessingError(f"Archivio rifiutato: contiene un percorso assoluto («{shown}»). Possibile tentativo di "
                              "scrivere fuori dalla cartella di estrazione (Path Traversal).")
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ProcessingError(f"Archivio rifiutato: contiene un percorso con «..» («{shown}»). Possibile tentativo di "
                              "scrivere fuori dalla cartella di estrazione (Path Traversal).")
    out = "/".join(parts)
    if len(out.encode("utf-8", "surrogatepass")) > MAX_NAME_BYTES or any(
            len(p.encode("utf-8", "surrogatepass")) > MAX_COMPONENT_BYTES for p in parts):
        raise ProcessingError(f"Archivio rifiutato: un elemento ha un nome troppo lungo («{shown}...»).")
    return out


def _renamed(original, staged, produced):
    """Nome da dare a un elemento quando l'elaborazione ha prodotto un file con un nome diverso da quello copiato
    nell'area temporanea (es. «nota.mp3» -> «nota.mp3.trascrizione.txt», «atto.pdf.p7m» -> «atto.pdf»)."""
    if produced == staged:
        return original
    if produced.startswith(staged):
        return original + produced[len(staged):]
    if staged.startswith(produced) and len(staged) - len(produced) < len(original):
        return original[:len(original) - (len(staged) - len(produced))]
    return produced


def _show(name):
    """Nome mostrabile e scrivibile in JSON/UTF-8 (i byte non validi dei nomi TAR diventano «?»)."""
    return str(name).encode("utf-8", "replace").decode("utf-8")


def _friendly(err):
    name = type(err).__name__
    if isinstance(err, ProcessingError) or name == "UnsupportedFormat":
        return str(err)
    if name in ("BadZipFile", "BadGzipFile", "LZMAError", "ReadError", "EOFError") or isinstance(err, (zlib.error, OSError)):
        return "contenuto danneggiato o non leggibile"
    return f"{name}: {err}"


# ------------------------------------------------------------------------------------------ riconoscimento
def sniff(path):
    """Formato reale dal contenuto: 'zip', '7z', 'rar', 'gz', 'bz2', 'xz', 'tar' oppure None."""
    try:
        with open(path, "rb") as f:
            head = f.read(600)
    except OSError:
        return None
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return "zip"
    if head[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    if head[:7] == b"Rar!\x1a\x07\x00" or head[:8] == b"Rar!\x1a\x07\x01\x00":
        return "rar"
    if head[:2] == b"\x1f\x8b":
        return "gz"
    if head[:3] == b"BZh":
        return "bz2"
    if head[:6] == b"\xfd7zXZ\x00":
        return "xz"
    if len(head) >= 262 and head[257:262] == b"ustar":
        return "tar"
    return None


def _open_stream(path, comp):
    if comp == "gz":
        return gzip.open(path, "rb")
    if comp == "bz2":
        return bz2.open(path, "rb")
    if comp == "xz":
        return lzma.open(path, "rb")
    return open(path, "rb")


def detect(path):
    """(contenitore, compressione): ('zip', None), ('7z', None), ('rar', None), ('tar', None|'gz'|'bz2'|'xz') oppure
    ('single', 'gz'|'bz2'|'xz') per un solo file compresso. ProcessingError se non e' un archivio leggibile."""
    kind = sniff(path)
    ext = os.path.splitext(path)[1].lower()
    if kind is None:
        if ext == ".zip" and zipfile.is_zipfile(path):
            return "zip", None          # ZIP con dati in testa (es. autoestraente)
        if ext == ".tar":
            try:
                if tarfile.is_tarfile(path):
                    return "tar", None  # vecchi TAR senza firma «ustar»
            except Exception:
                pass
        raise ProcessingError("Archivio non valido o danneggiato: il contenuto non corrisponde a nessun formato "
                              "supportato (ZIP, TAR, GZ, BZ2, XZ, 7Z, RAR).")
    if kind in ("zip", "7z", "rar", "tar"):
        return kind, None
    try:
        with _open_stream(path, kind) as f:
            head = f.read(600)
    except Exception:
        raise ProcessingError("File compresso danneggiato: non e' stato possibile leggerlo.") from None
    if len(head) >= 262 and head[257:262] == b"ustar":
        return "tar", kind
    if ext in _TAR_SHORT or os.path.splitext(path)[0].lower().endswith(".tar"):
        if not head.strip(b"\x00"):
            return "tar", kind          # TAR vuoto (solo blocchi di zeri)
    return "single", kind


# ------------------------------------------------------------------------------------------ 7-Zip
def sevenzip_path():
    """Console di 7-Zip distribuita con Germano (runtime/7zip; dai sorgenti dipendenze/<sistema>/7zip), altrimenti
    quella installata nel sistema. None se non c'e'."""
    names = ("7z.exe",) if os.name == "nt" else ("7zzs", "7zz", "7z")
    base = os.environ.get("GERMANO_7ZIP_DIR") or getattr(common, "SEVENZIP_DIR", "")
    for n in names:
        p = os.path.join(base, n) if base else ""
        if p and os.path.isfile(p):
            return p
    for n in names + ("7za",):
        p = shutil.which(n)
        if p:
            return p
    return None


def _popen_kw():
    return {"creationflags": 0x08000000} if os.name == "nt" else {}      # CREATE_NO_WINDOW


def _seven_error(text, what="Archivio"):
    low = (text or "").lower()
    if "password" in low or "encrypted" in low:
        return ProcessingError(f"{what} protetto da password: non e' possibile analizzarne il contenuto.")
    if "volume" in low or "unexpected end" in low:
        return ProcessingError(f"{what} incompleto o diviso in piu' volumi: servono tutte le parti in un solo file.")
    if "unsupported" in low or "not implemented" in low:
        return ProcessingError(f"{what} con un metodo di compressione non supportato.")
    return ProcessingError(f"{what} danneggiato o non riconosciuto: non e' stato possibile aprirlo.")


def _seven_list(exe, path):
    """Elenco tecnico degli elementi (7z l -slt). I nomi con a capo sono gia' resi innocui da 7-Zip («_»)."""
    try:
        r = subprocess.run([exe, "l", "-slt", "-ba", "-sccUTF-8", "-p", "-sns-", "--", path], capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=SEVENZIP_LIST_TIMEOUT, **_popen_kw())
    except subprocess.TimeoutExpired:
        raise ProcessingError("Archivio non leggibile: l'elenco del contenuto non e' arrivato in tempo.") from None
    err = r.stderr.decode("utf-8", "replace")
    if r.returncode not in (0, 1):
        raise _seven_error(err)
    members = []
    for block in r.stdout.decode("utf-8", "replace").replace("\r\n", "\n").split("\n\n"):
        fields = {}
        for line in block.split("\n"):
            key, sep, value = line.partition(" = ")
            if sep and key not in fields:
                fields[key] = value
        name = fields.get("Path")
        if not name:
            continue
        attrs = fields.get("Attributes") or ""
        if (fields.get("Symbolic Link") or "").strip() or (fields.get("Hard Link") or "").strip() or " l" in attrs:
            kind = "link"
        elif fields.get("Folder") == "+" or attrs.startswith("D"):
            kind = "dir"
        else:
            kind = "file"
        try:
            size = int(fields.get("Size") or 0)
        except ValueError:
            size = 0
        mtime = None
        m = re.match(r"(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)", fields.get("Modified") or "")
        if m:
            try:
                mtime = time.mktime(tuple(int(x) for x in m.groups()) + (0, 0, -1))
            except (OverflowError, ValueError):
                mtime = None
        crc = (fields.get("CRC") or "").strip().upper()
        members.append(Member(name, kind, size, mtime, None, (fields.get("Encrypted") or "").strip() == "+",
                              crc if re.fullmatch(r"[0-9A-F]{8}", crc) else None))
    return members


class _SevenReader:
    """7Z e RAR: elenco con «l -slt», poi i dati di tutti i file in un solo flusso («x -so»), nell'ordine
    dell'elenco. Ogni file viene letto per la dimensione dichiarata e verificato con il suo CRC: se il flusso non
    corrisponde all'elenco l'archivio viene rifiutato."""

    def __init__(self, path, fmt, workdir):
        self.path, self.fmt, self.workdir = path, fmt, workdir
        self.exe = sevenzip_path()
        if not self.exe:
            raise ProcessingError(f"Per aprire gli archivi {fmt.upper()} serve 7-Zip, che non e' stato trovato accanto "
                                  "a Germano (runtime/7zip).")
        self.members = _seven_list(self.exe, path)
        self.proc = None
        self._err = None
        self._pending = None            # elemento i cui dati sono i prossimi nel flusso

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        proc, self.proc = self.proc, None
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
                proc.stdout.close()
                proc.wait(10)
            except Exception:
                pass
        if self._err is not None:
            try:
                self._err.close()
            except Exception:
                pass
            self._err = None

    def total_declared(self):
        return sum(m.size for m in self.members if m.kind == "file")

    def _start(self):
        if any(m.encrypted for m in self.members if m.kind == "file"):
            raise ProcessingError("Archivio protetto da password: non e' possibile analizzarne il contenuto.")
        self._err = open(os.path.join(self.workdir, f"7z_{uuid.uuid4().hex[:8]}.err"), "w+b")
        self.proc = subprocess.Popen([self.exe, "x", "-so", "-y", "-p", "-sns-", "-bso0", "-bsp0", "-bse2", "--",
                                      self.path], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=self._err,
                                     cwd=self.workdir, **_popen_kw())

    def _stderr(self):
        try:
            self._err.seek(0)
            return self._err.read(8000).decode("utf-8", "replace")
        except Exception:
            return ""

    def _consume(self, m, dst, guard):
        """Legge dal flusso i dati dell'elemento (li scrive in dst, se indicato) e ne verifica dimensione e CRC."""
        if self.proc is None:
            self._start()
        left, crc = m.size, 0
        while left > 0:
            chunk = self.proc.stdout.read(min(1 << 20, left))
            if not chunk:
                raise _seven_error(self._stderr())
            left -= len(chunk)
            crc = zlib.crc32(chunk, crc)
            if guard is not None:
                guard.chunk(len(chunk))
            if dst is not None:
                dst.write(chunk)
        if m.crc and m.size and "%08X" % (crc & 0xFFFFFFFF) != m.crc:
            raise ProcessingError("Archivio danneggiato: il contenuto di un file interno non corrisponde al suo codice "
                                  "di controllo (CRC).")

    def iterate(self):
        for m in self.members:
            if m.kind == "file":
                self._pending = m
                yield m
                if self._pending is m:              # non estratto da chi consuma: i suoi dati vanno comunque letti
                    self._consume(m, None, None)
                    self._pending = None
            else:
                yield m
        if self.proc is not None:
            extra = self.proc.stdout.read(1)
            rc = self.proc.wait(60)
            if extra or rc not in (0, 1):
                raise _seven_error(self._stderr())

    def extract_to(self, m, dst, guard):
        if self._pending is not m:
            raise ProcessingError("Errore interno: estrazione fuori sequenza.")
        if m.size > MAX_MEMBER_BYTES:
            raise ProcessingError("Un file interno dell'archivio e' troppo grande (oltre "
                                  f"{MAX_MEMBER_BYTES / 1024 ** 3:.0f} GB).")
        self._consume(m, dst, guard)
        self._pending = None


class _SevenWriter:
    """Nuovo archivio 7Z: i file bonificati si raccolgono con nomi neutri in una cartella temporanea, 7-Zip li
    comprime e poi li rinomina DENTRO l'archivio con i percorsi originali («rn»): nessun percorso preso
    dall'archivio viene mai creato sul disco."""
    ext = ".7z"

    def __init__(self, out_path, workdir, threads=None):
        self.out, self.exe = out_path, sevenzip_path()
        if not self.exe:
            raise ProcessingError("Per creare gli archivi 7Z serve 7-Zip, che non e' stato trovato accanto a Germano.")
        self.stage = os.path.join(workdir, "7z_" + uuid.uuid4().hex[:8])
        os.makedirs(self.stage)
        self.prefix = "g" + uuid.uuid4().hex[:10] + "_"
        self.items = []
        self.threads = threads

    def _neutral(self):
        return f"{self.prefix}{len(self.items):07d}"

    @staticmethod
    def _touch(path, m):
        if m is not None and m.mtime:
            try:
                os.utime(path, (m.mtime, m.mtime))
            except (OSError, OverflowError, ValueError):
                pass

    def add_dir(self, name, m=None):
        neutral = self._neutral()
        os.mkdir(os.path.join(self.stage, neutral))
        self._touch(os.path.join(self.stage, neutral), m)
        self.items.append((neutral, name.rstrip("/")))

    def add_file(self, name, src, m=None):
        neutral = self._neutral()
        dst = os.path.join(self.stage, neutral)
        shutil.move(src, dst)
        self._touch(dst, m)
        self.items.append((neutral, name))

    def _run(self, args, what):
        r = subprocess.run([self.exe] + args, cwd=self.stage, capture_output=True, stdin=subprocess.DEVNULL,
                           **_popen_kw())
        if r.returncode != 0:
            common.log(f"7-Zip ({what}): codice {r.returncode}: {r.stderr.decode('utf-8', 'replace')[:300]}")
            raise ProcessingError("Non e' stato possibile ricomporre l'archivio 7Z.")

    def close(self, ok=True):
        try:
            if not ok:
                return
            if not self.items:
                raise ProcessingError("L'archivio non contiene nessun elemento da ricomporre.")
            listing = os.path.join(self.stage, self.prefix + "elenco.txt")
            renames = os.path.join(self.stage, self.prefix + "nomi.txt")
            with open(listing, "w", encoding="utf-8", newline="\n") as f:
                f.write("".join(n + "\n" for n, _ in self.items))
            with open(renames, "w", encoding="utf-8", newline="\n") as f:
                f.write("".join(f"{n}\n{final}\n" for n, final in self.items))
            common.remove_quietly(self.out)
            threads = [f"-mmt={int(self.threads)}"] if self.threads else []
            # niente «--»: fermerebbe anche la lettura dei file elenco (@). I percorsi passati qui sono solo quelli
            # di Germano (assoluti); i nomi presi dall'archivio stanno DENTRO i file elenco, dove sono solo testo.
            self._run(["a", "-t7z", "-y", "-bso0", "-bsp0", "-scsUTF-8", "-spd", "-mx=5"] + threads +
                      [os.path.abspath(self.out), "@" + listing], "creazione")
            self._run(["rn", "-t7z", "-y", "-bso0", "-bsp0", "-scsUTF-8", "-spd", os.path.abspath(self.out),
                       "@" + renames], "nomi")
            # rilettura: i percorsi nel nuovo archivio devono essere esattamente quelli voluti
            got = sorted(m.name.replace("\\", "/") for m in _seven_list(self.exe, self.out))
            if got != sorted(final for _, final in self.items):
                raise ProcessingError("Non e' stato possibile ricomporre l'archivio 7Z con i percorsi originali.")
        finally:
            shutil.rmtree(self.stage, ignore_errors=True)


# ------------------------------------------------------------------------------------------ ZIP
class _ZipReader:
    def __init__(self, path):
        try:
            self.z = zipfile.ZipFile(path, "r")
        except (zipfile.BadZipFile, OSError, ValueError):
            raise ProcessingError("Archivio ZIP non valido o danneggiato.") from None
        self.infos = self.z.infolist()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.z.close()

    def total_declared(self):
        return sum(i.file_size for i in self.infos if not i.is_dir())

    @staticmethod
    def _member(info):
        mode = (info.external_attr >> 16) & 0xFFFF
        if info.is_dir():
            kind = "dir"
        elif stat.S_ISLNK(mode):
            kind = "link"
        elif mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG):
            kind = "special"
        else:
            kind = "file"
        try:
            mtime = time.mktime(tuple(info.date_time) + (0, 0, -1))
        except (OverflowError, ValueError):
            mtime = None
        return Member(info.filename, kind, info.file_size, mtime, stat.S_IMODE(mode) or None,
                      bool(info.flag_bits & 0x1), None, info)

    def iterate(self):
        for info in self.infos:
            yield self._member(info)

    def extract_to(self, m, dst, guard):
        if m.size > MAX_MEMBER_BYTES:
            raise ProcessingError("Un file interno dell'archivio e' troppo grande (oltre "
                                  f"{MAX_MEMBER_BYTES / 1024 ** 3:.0f} GB).")
        done = 0
        with self.z.open(m.raw, "r") as src:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                done += len(chunk)
                if done > max(m.size, 0) + (1 << 16) or done > MAX_MEMBER_BYTES:
                    raise ProcessingError("Archivio sospetto: un file interno contiene piu' dati di quanti ne dichiara.")
                guard.chunk(len(chunk))
                dst.write(chunk)


def _dos_time(m):
    t = time.localtime(m.mtime if (m is not None and m.mtime) else time.time())[:6]
    return (1980, 1, 1, 0, 0, 0) if t[0] < 1980 else ((2107, 12, 31, 23, 59, 58) if t[0] > 2107 else t)


class _ZipWriter:
    ext = ".zip"

    def __init__(self, out_path):
        self.z = zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True)

    def add_dir(self, name, m=None):
        zi = zipfile.ZipInfo(name.rstrip("/") + "/", _dos_time(m))
        zi.external_attr = (0o40755 << 16) | 0x10
        self.z.writestr(zi, b"")

    def add_file(self, name, src, m=None):
        zi = zipfile.ZipInfo(name, _dos_time(m))
        zi.external_attr = 0o100644 << 16
        with open(src, "rb") as f:
            sample = f.read(1 << 18)
            f.seek(0)
            packed = len(zlib.compress(sample, 1)) if sample else 0
            zi.compress_type = zipfile.ZIP_STORED if (len(sample) > 4096 and packed > 0.97 * len(sample)) \
                else zipfile.ZIP_DEFLATED
            with self.z.open(zi, "w", force_zip64=os.path.getsize(src) >= (1 << 31)) as dst:
                shutil.copyfileobj(f, dst, 1 << 20)

    def close(self, ok=True):
        self.z.close()


# ------------------------------------------------------------------------------------------ TAR
class _TarReader:
    def __init__(self, path):
        try:
            self.t = tarfile.open(path, "r:*")
        except (tarfile.TarError, OSError, EOFError, zlib.error, lzma.LZMAError, ValueError):
            raise ProcessingError("Archivio TAR non valido o danneggiato.") from None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.t.close()

    def total_declared(self):
        return None                      # si conosce solo leggendo tutto: i limiti valgono sui byte letti

    def iterate(self):
        try:
            for ti in self.t:
                if ti.isdir():
                    kind = "dir"
                elif ti.isreg():
                    kind = "file"
                elif ti.issym() or ti.islnk():
                    kind = "link"
                else:
                    kind = "special"
                yield Member(ti.name, kind, ti.size if kind == "file" else 0, ti.mtime, stat.S_IMODE(ti.mode), False,
                             None, ti)
        except (tarfile.TarError, EOFError, zlib.error, lzma.LZMAError, OSError) as e:
            if isinstance(e, ProcessingError):
                raise
            raise ProcessingError("Archivio TAR danneggiato o incompleto.") from None

    def extract_to(self, m, dst, guard):
        if m.size > MAX_MEMBER_BYTES:
            raise ProcessingError("Un file interno dell'archivio e' troppo grande (oltre "
                                  f"{MAX_MEMBER_BYTES / 1024 ** 3:.0f} GB).")
        src = self.t.extractfile(m.raw)
        if src is None:
            return
        done = 0
        with src:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_MEMBER_BYTES:
                    raise ProcessingError("Un file interno dell'archivio e' troppo grande.")
                guard.chunk(len(chunk))
                dst.write(chunk)


class _TarWriter:
    def __init__(self, out_path, comp):
        self.ext = ".tar" + (_COMP_EXT[comp] if comp else "")
        kw = {"compresslevel": 6} if comp in ("gz", "bz2") else {}
        self.t = tarfile.open(out_path, "w:" + comp if comp else "w", format=tarfile.PAX_FORMAT, **kw)

    @staticmethod
    def _info(name, m, kind):
        ti = tarfile.TarInfo(name)
        ti.type = kind
        ti.mtime = int(m.mtime) if (m is not None and m.mtime and m.mtime > 0) else int(time.time())
        # niente proprietario ne' gruppo del sistema di origine (uid/gid 0, nomi vuoti): sono dati personali
        return ti

    def add_dir(self, name, m=None):
        ti = self._info(name.rstrip("/"), m, tarfile.DIRTYPE)
        ti.mode = 0o755
        self.t.addfile(ti)

    def add_file(self, name, src, m=None):
        ti = self._info(name, m, tarfile.REGTYPE)
        ti.mode = ((m.mode if (m is not None and m.mode) else 0o644) & 0o777) or 0o644
        ti.size = os.path.getsize(src)
        with open(src, "rb") as f:
            self.t.addfile(ti, f)

    def close(self, ok=True):
        self.t.close()


def _open_reader(container, path, workdir):
    if container == "zip":
        return _ZipReader(path)
    if container == "tar":
        return _TarReader(path)
    return _SevenReader(path, container, workdir)


# ------------------------------------------------------------------------------------------ elaborazione
def _out_name(name, is_dir, ctx, used, dir_map):
    """Percorso dell'elemento nel nuovo archivio: identico all'originale; con «Anonimizza i nomi dei file» attivo (o
    in ripristino) ogni componente passa dal filtro dei nomi. I nomi doppi vengono resi unici."""
    if not (ctx.settings.get("anonymize_filenames") if ctx.anonymize else True):
        return name
    parts = name.split("/")
    out, walked = [], ""
    for i, p in enumerate(parts):
        last = i == len(parts) - 1
        walked = walked + "/" + p if walked else p
        if not last or is_dir:
            if walked not in dir_map:
                dir_map[walked] = transform_filename(p + ".d", ctx)[:-2] or p
            out.append(dir_map[walked])
        else:
            out.append(transform_filename(p, ctx) or p)
    new = "/".join(out)
    if is_dir:
        return new
    cand, k = new, 2
    while cand.lower() in used:
        stem, ext = os.path.splitext(new)
        cand = f"{stem} ({k}){ext}"
        k += 1
    used.add(cand.lower())
    return cand


def _label(ctx, path):
    """Percorso logico dell'archivio per il report (gli annidati mostrano la catena «esterno › interno»)."""
    return getattr(ctx, "archive_label", None) or os.path.basename(path)


def process_archive(in_path, out_path, ctx):
    container, comp = detect(in_path)
    budget = _budget(ctx)
    if container == "single":
        return _process_single(in_path, out_path, ctx, comp, budget)
    guard = _Guard(ctx, budget, os.path.getsize(in_path))
    report, label = _report(ctx), _show(_label(ctx, in_path))
    real_out = out_path + ".zip" if container == "rar" else out_path
    counts = {"ok": 0, "copied": 0, "excluded": 0, "dirs": 0, "entities": 0}
    excluded, t0 = [], time.time()
    used, dir_map = set(), {}
    verb = "bonificato" if ctx.anonymize else "ripristinato"
    with ctx.tempdir() as work:
        reader = _open_reader(container, in_path, work)
        writer = None
        ok = False
        try:
            with reader:
                declared = reader.total_declared()
                listing = getattr(reader, "members", None) or getattr(reader, "infos", None)
                if listing is not None:
                    if len(listing) > MAX_ENTRIES:
                        raise ProcessingError(f"Archivio con troppi elementi ({len(listing)}): elaborazione bloccata.")
                    budget.add_entries(len(listing))
                    # prima di toccare qualunque dato: tutti i percorsi devono essere sicuri
                    for item in listing:
                        safe_member_name(getattr(item, "name", None) or getattr(item, "filename", ""))
                if declared is not None:
                    guard.declared(declared)
                if container == "7z":
                    writer = _SevenWriter(real_out, work, common.cpu_threads(ctx.settings)[0])
                elif container == "tar":
                    writer = _TarWriter(real_out, comp)
                else:
                    writer = _ZipWriter(real_out)
                n_items = len(listing) if listing is not None else None
                for k, m in enumerate(reader.iterate()):
                    ctx.check()
                    if listing is None:
                        if k >= MAX_ENTRIES:
                            raise ProcessingError(f"Archivio con troppi elementi (oltre {MAX_ENTRIES}): elaborazione "
                                                  "bloccata.")
                        budget.add_entries(1)
                    name = safe_member_name(m.name)
                    if not name:
                        continue
                    if m.kind == "dir":
                        writer.add_dir(_out_name(name, True, ctx, used, dir_map), m)
                        counts["dirs"] += 1
                        continue
                    base = name.rsplit("/", 1)[-1]
                    shown = _show(name)
                    where = f"{label} › {shown}"
                    if m.kind != "file":
                        excluded.append((shown, "collegamento o file speciale: non viene seguito ne' copiato"))
                        report.append(_entry(where, "escluso", excluded[-1][1]))
                        continue
                    if m.encrypted:
                        excluded.append((shown, "protetto da password"))
                        report.append(_entry(where, "escluso", "protetto da password"))
                        continue
                    ctx.report(f"archivio: file {k + 1}" + (f"/{n_items}" if n_items else "") + f" ({_show(base)[:60]})")
                    supported = is_supported(base)
                    if not supported and ctx.anonymize:
                        guard.chunk(m.size)      # non estratto, ma la sua dimensione conta nei limiti
                        excluded.append((shown, "formato non supportato"))
                        report.append(_entry(where, "escluso", "formato non supportato"))
                        continue
                    item_dir = os.path.join(work, f"e{k:06d}")
                    os.makedirs(os.path.join(item_dir, "in"))
                    os.makedirs(os.path.join(item_dir, "out"))
                    staged = common.safe_filename(base, max_len=100)
                    src = os.path.join(item_dir, "in", staged)
                    try:
                        with open(src, "wb") as f:
                            reader.extract_to(m, f, guard)
                    except (zipfile.BadZipFile, zlib.error, lzma.LZMAError, EOFError, NotImplementedError,
                            RuntimeError) as e:
                        if container != "zip":
                            raise ProcessingError("Archivio danneggiato: un file interno non e' leggibile.") from None
                        # ZIP: ogni file e' indipendente, uno danneggiato non impedisce di leggere gli altri
                        reason = "metodo di compressione non supportato" if isinstance(e, NotImplementedError) \
                            else "contenuto danneggiato o non leggibile"
                        excluded.append((shown, reason))
                        report.append(_entry(where, "escluso", reason))
                        shutil.rmtree(item_dir, ignore_errors=True)
                        continue
                    if not supported:                     # ripristino: quello che non contiene etichette resta com'e'
                        writer.add_file(_out_name(name, False, ctx, used, dir_map), src, m)
                        counts["copied"] += 1
                        report.append(_entry(where, "copiato", "formato senza testo da ripristinare"))
                        shutil.rmtree(item_dir, ignore_errors=True)
                        continue
                    child = ctx.child()
                    child.archive_label = where
                    n0 = len(ctx.audit)
                    try:
                        produced = process_file(src, os.path.join(item_dir, "out", staged), child)
                    except Exception as e:
                        reraise_control(e)
                        if ctx.anonymize:
                            reason = _friendly(e)
                            excluded.append((shown, reason))
                            report.append(_entry(where, "escluso", reason))
                        else:
                            writer.add_file(_out_name(name, False, ctx, used, dir_map), src, m)
                            counts["copied"] += 1
                            report.append(_entry(where, "copiato", f"non ripristinabile ({_friendly(e)})"))
                        shutil.rmtree(item_dir, ignore_errors=True)
                        continue
                    found = len(ctx.audit) - n0
                    for e in ctx.audit[n0:]:
                        e["source"] = shown + (" › " + e["source"] if e.get("source") else "")
                    new_base = _renamed(base, staged, os.path.basename(produced))
                    new_name = name[:len(name) - len(base)] + new_base
                    final_name = _out_name(new_name, False, ctx, used, dir_map)
                    writer.add_file(final_name, produced, m)
                    counts["ok"] += 1
                    counts["entities"] += found
                    report.append(_entry(where, verb, "", found, _show(final_name) if final_name != name else None))
                    shutil.rmtree(item_dir, ignore_errors=True)
                counts["excluded"] = len(excluded)
                if ctx.anonymize and excluded and not counts["ok"]:
                    shown = "; ".join(f"{n} ({r})" for n, r in excluded[:5]) + (" ..." if len(excluded) > 5 else "")
                    raise ProcessingError("Nessun file dell'archivio e' stato elaborato, quindi non viene prodotto un "
                                          f"archivio vuoto. Esclusi: {shown}")
                if not (counts["ok"] or counts["copied"] or counts["dirs"]):
                    raise ProcessingError("L'archivio non contiene nessun file.")
                ok = True
        finally:
            if writer is not None:
                try:
                    writer.close(ok)
                except Exception:
                    if ok:
                        raise
            if not ok:
                common.remove_quietly(real_out)
    what = "bonificati" if ctx.anonymize else "ripristinati"
    summary = (f"Archivio {label} ({container.upper()}{'.' + comp.upper() if comp else ''}): {counts['ok']} file {what}"
               + (f", {counts['copied']} copiati senza modifiche" if counts["copied"] else "")
               + (f", {counts['excluded']} esclusi" if excluded else "")
               + f", {counts['entities']} dati {'oscurati' if ctx.anonymize else 'ripristinati'} in "
               f"{time.time() - t0:.1f} s.")
    common.log(summary)
    report.append({"word": "", "label": "[ARCHIVIO]", "entity": "ARCHIVE", "score": 1.0, "file": label,
                   "action": "riepilogo", "format": container + ("." + comp if comp else ""),
                   "processed": counts["ok"], "copied": counts["copied"], "excluded": counts["excluded"],
                   "folders": counts["dirs"], "entities": counts["entities"], "unpacked_bytes": guard.read,
                   "seconds": round(time.time() - t0, 1), "note": summary})
    if excluded:
        shown = "; ".join(f"{n} ({r})" for n, r in excluded[:10]) + (" ..." if len(excluded) > 10 else "")
        kind = "non anonimizzabili" if ctx.anonymize else "non leggibili"
        ctx.note(f"Dall'archivio {label} sono stati esclusi {len(excluded)} file {kind}: {shown}")
    if container == "rar":
        ctx.note("Il formato RAR e' proprietario e non si puo' creare: l'archivio bonificato e' stato salvato come ZIP "
                 "con la stessa struttura di cartelle.")
    return real_out if real_out != out_path else None


def _entry(where, action, detail="", entities=0, output=None):
    e = {"word": "", "label": "[ARCHIVIO]", "entity": "ARCHIVE", "score": 1.0, "file": where, "action": action,
         "entities": entities}
    if detail:
        e["note"] = detail
    if output:
        e["output"] = output
    return e


def _process_single(in_path, out_path, ctx, comp, budget):
    """GZ, BZ2 o XZ di un solo file: il contenuto viene elaborato col proprio formato e ricompresso."""
    ext = os.path.splitext(in_path)[1]
    inner = os.path.basename(in_path)[:-len(ext)] if ext else os.path.basename(in_path)
    label = _show(_label(ctx, in_path))
    report = _report(ctx)
    where = f"{label} › {_show(inner)}"
    if not os.path.splitext(inner)[1] or not is_supported(inner):
        if ctx.anonymize:
            raise ProcessingError(f"Il file compresso {comp.upper()} contiene un formato non supportato "
                                  f"(«{inner[:80]}»): rinominalo con l'estensione del contenuto, es. documento.pdf"
                                  f"{_COMP_EXT[comp]}.")
        shutil.copyfile(in_path, out_path)
        return None
    guard = _Guard(ctx, budget, os.path.getsize(in_path))
    budget.add_entries(1)
    t0 = time.time()
    with ctx.tempdir() as work:
        os.makedirs(os.path.join(work, "in"))
        os.makedirs(os.path.join(work, "out"))
        staged = common.safe_filename(inner, max_len=100)
        src = os.path.join(work, "in", staged)
        mtime = None
        try:
            with _open_stream(in_path, comp) as z, open(src, "wb") as f:
                done = 0
                while True:
                    chunk = z.read(1 << 20)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > MAX_MEMBER_BYTES:
                        raise ProcessingError("Il file compresso e' troppo grande (oltre "
                                              f"{MAX_MEMBER_BYTES / 1024 ** 3:.0f} GB decompresso).")
                    guard.chunk(len(chunk))
                    f.write(chunk)
                mtime = getattr(z, "mtime", None)
        except (OSError, EOFError, zlib.error, lzma.LZMAError, ValueError) as e:
            if isinstance(e, ProcessingError):
                raise
            raise ProcessingError(f"File compresso {comp.upper()} danneggiato o incompleto.") from None
        child = ctx.child()
        child.archive_label = where
        n0 = len(ctx.audit)
        produced = process_file(src, os.path.join(work, "out", staged), child)
        found = len(ctx.audit) - n0
        for e in ctx.audit[n0:]:
            e["source"] = inner + (" › " + e["source"] if e.get("source") else "")
        new_inner = _renamed(inner, staged, os.path.basename(produced))
        real_out = out_path
        if new_inner != inner:
            out_base = os.path.basename(out_path)
            stem = out_base[:-len(ext)] if ext and out_base.lower().endswith(ext.lower()) else out_base
            real_out = os.path.join(os.path.dirname(out_path), _renamed(stem, inner, new_inner) + _COMP_EXT[comp])
        with open(produced, "rb") as f:
            if comp == "gz":
                # intestazione senza il nome originale del file (potrebbe contenere dati personali)
                with open(real_out, "wb") as raw, gzip.GzipFile(filename="", mode="wb", compresslevel=6, fileobj=raw,
                                                               mtime=int(mtime or 0)) as z:
                    shutil.copyfileobj(f, z, 1 << 20)
            else:
                opener = bz2.open if comp == "bz2" else lzma.open
                with opener(real_out, "wb") as z:
                    shutil.copyfileobj(f, z, 1 << 20)
    verb = "bonificato" if ctx.anonymize else "ripristinato"
    report.append(_entry(where, verb, "", found, new_inner if new_inner != inner else None))
    common.log(f"File compresso {label} ({comp.upper()}): contenuto {verb}, {found} dati in {time.time() - t0:.1f} s.")
    return real_out if real_out != out_path else None


# ------------------------------------------------------------------------------------------ anteprima del testo
def sample_members(path, workdir, max_members=SAMPLE_MEMBERS, max_member_bytes=SAMPLE_MEMBER_BYTES):
    """Per formats.detection: genera (nome, percorso temporaneo) dei file di un archivio, con gli stessi controlli di
    sicurezza dell'elaborazione ma senza mai sollevare errori (un archivio non leggibile non ha testo)."""

    class _Quiet:
        @staticmethod
        def check():
            return None

    try:
        container, comp = detect(path)
        guard = _Guard(_Quiet, Budget(), os.path.getsize(path))
        if container == "single":
            ext = os.path.splitext(path)[1]
            inner = os.path.basename(path)[:-len(ext)] if ext else os.path.basename(path)
            dst = os.path.join(workdir, "s_" + common.safe_filename(inner, max_len=80))
            with _open_stream(path, comp) as z, open(dst, "wb") as f:
                done = 0
                while done <= max_member_bytes:
                    chunk = z.read(1 << 20)
                    if not chunk:
                        break
                    done += len(chunk)
                    guard.chunk(len(chunk))
                    f.write(chunk)
            if done <= max_member_bytes:
                yield inner, dst
            return
        with _open_reader(container, path, workdir) as reader:
            declared = reader.total_declared()
            if declared is not None:
                guard.declared(declared)
            n = 0
            for k, m in enumerate(reader.iterate()):
                if k >= MAX_ENTRIES or n >= max_members:
                    break
                if m.kind != "file" or m.encrypted or m.size > max_member_bytes:
                    continue
                name = safe_member_name(m.name)
                base = name.rsplit("/", 1)[-1]
                if not is_supported(base):
                    continue
                dst = os.path.join(workdir, f"s{k:06d}_" + common.safe_filename(base, max_len=80))
                with open(dst, "wb") as f:
                    reader.extract_to(m, f, guard)
                n += 1
                yield name, dst
                common.remove_quietly(dst)
    except CancelledError:
        raise
    except Exception:
        return


# compatibilita' con il nome usato fino alla 0.70
process_zip = process_archive
