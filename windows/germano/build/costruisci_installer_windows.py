"""Costruisce gli installer Windows IN UN SOLO FILE della release:
  germano.ai-0.60/releases/windows/germano-0.60.exe          suite completa (runtime, 6 modelli IA, interfaccia)
  germano.ai-0.60/releases/windows/germano-client-0.60.exe   client leggero
partendo da sorgenti/windows/<edizione> (programma), dipendenze/windows/runtime-<edizione> (Python 3.11 con tutte
le librerie e le DLL di Visual C++ accanto all'interprete: nessun ridistribuibile da installare) e modelli/ (suite).
Germano.exe (l'unico programma) viene creato qui da build_exe.py e messo solo nell'installer: i sorgenti restano
senza binari.

Struttura dell'eseguibile:  [avviatore .NET] [kit ZIP] [archivio ZIP del programma] [coda di 48 byte]
- avviatore: sfx_stub.cs compilato con il csc.exe di .NET Framework 4 (presente in ogni Windows 10/11), con l'icona
  ufficiale e le informazioni di versione; nessuna console. Quello della suite chiede subito i permessi di
  amministratore (UAC) e alla fine apre Germano con i permessi normali; quello del client non chiede permessi;
- kit: interprete Python minimo (dal runtime leggero del client: interprete, libreria standard, psutil) +
  germano_install.py + favicon.ico + setup.json (edizione e versione);
- archivio: il programma installato (deflate; i file che non si comprimono vengono solo archiviati) e
  __germano_setup__/mtimes.json con le date originali dei file (la cache dei moduli Python gia' compilati resta valida);
- coda: firma "GERMANO.SFX.0001" + posizione/lunghezza del kit e dell'archivio.
Alla fine l'eseguibile viene riletto per intero: controllo del CRC di ogni file dell'archivio e del kit.

Uso: python costruisci_installer_windows.py [suite|client|tutti]
"""
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import build_exe  # noqa: E402

RELEASE = os.path.abspath(os.path.join(TOOLS, "..", "..", "..", ".."))       # germano.ai-0.60
SOURCES = os.path.join(RELEASE, "sorgenti", "windows")
DEPS = os.path.join(RELEASE, "dipendenze", "windows")
MODELS = os.path.join(RELEASE, "modelli")
OUT_DIR = os.path.join(RELEASE, "releases", "windows")
CSC = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Microsoft.NET", "Framework64", "v4.0.30319", "csc.exe")
SFX_MAGIC = b"GERMANO.SFX.0001"
SFX_TRAILER = struct.Struct("<16sQQQQ")
META_PREFIX = "__germano_setup__/"
# elevate: l'avviatore chiede subito i permessi di amministratore (suite: regola del firewall per la rete locale)
EDITIONS = {
    "suite": {"folder": "germano", "runtime": "runtime-germano", "models": True, "product": "Germano AI",
              "file": "germano-{v}.exe", "elevate": True},
    "client": {"folder": "germano-client", "runtime": "runtime-germano-client", "models": False,
               "product": "Germano AI Client", "file": "germano-client-{v}.exe", "elevate": False},
}
# Mai nell'archivio: strumenti di costruzione, dati e file tecnici di un uso portatile, vecchi avviatori.
EXCLUDE_TOP = {"build", "__pycache__", "state", "cache", "update", "input", "output", "processed", "failed",
               "extracted", "runtime", "models", "germano.exe", "desktop.log", "server_stdout.log", "daemon.log",
               "germano_install.json", "start.bat", "start_server.bat", "installa_germano.exe", "prerequisites"}
# Kit: solo cio' che serve a germano_install.py (niente OpenSSL, SQLite, pywin32).
KIT_SKIP = {"libcrypto-3.dll", "libssl-3.dll", "_ssl.pyd", "_hashlib.pyd", "sqlite3.dll", "_sqlite3.pyd",
            "pythoncom311.dll", "pywintypes311.dll", "python.cat", "license.txt"}


def compile_stub(edition, version, icon, out):
    with open(os.path.join(TOOLS, "sfx_stub.cs"), encoding="utf-8") as f:
        code = f.read()
    v4 = ".".join(str(n) for n in build_exe.version_numbers(version))
    title = f"Installazione di {edition['product']} {version}"
    code = (code.replace("@TITLE@", title).replace("@PRODUCT@", edition["product"])
            .replace("@VERSION4@", v4).replace("@VERSION@", version)
            .replace("@ELEVATE@", "true" if edition["elevate"] else "false"))
    for placeholder in ("@TITLE@", "@PRODUCT@", "@VERSION4@", "@VERSION@", "@ELEVATE@"):
        assert placeholder not in code, f"segnaposto non sostituito: {placeholder}"
    src = out + ".cs"
    with open(src, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        r = subprocess.run([CSC, "/nologo", "/codepage:65001", "/target:winexe", "/optimize+", "/platform:anycpu",
                            f"/win32icon:{icon}", "/r:System.IO.Compression.dll", "/r:System.Windows.Forms.dll",
                            f"/out:{out}", src], capture_output=True, text=True)
    finally:
        os.remove(src)
    if r.returncode != 0:
        raise SystemExit(f"ERRORE di compilazione dell'avviatore:\n{r.stdout}\n{r.stderr}")
    return out


def build_kit(pkg, edition_key, version, product, icon):
    """ZIP in memoria con l'interprete minimo, l'installer e i suoi metadati."""
    runtime = os.path.join(DEPS, EDITIONS["client"]["runtime"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(os.listdir(runtime)):
            path = os.path.join(runtime, name)
            if os.path.isfile(path) and name.lower() not in KIT_SKIP:
                z.write(path, "runtime/" + name)
        psutil_dir = os.path.join(runtime, "Lib", "site-packages", "psutil")
        for base, dirs, names in os.walk(psutil_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests")]
            for n in names:
                p = os.path.join(base, n)
                z.write(p, "runtime/" + os.path.relpath(p, runtime).replace(os.sep, "/"))
        z.write(os.path.join(pkg, "germano_install.py"), "germano_install.py")
        z.write(icon, "favicon.ico")
        z.writestr("setup.json", json.dumps({"edition": edition_key, "version": version, "product": product},
                                            ensure_ascii=False, indent=2))
    return buf.getvalue()


class OffsetWriter:
    """Il file di uscita visto a partire da una posizione: l'archivio accodato ha posizioni relative a se stesso
    (e' uno ZIP valido anche estratto dall'eseguibile)."""

    def __init__(self, f, base):
        self.f, self.base = f, base

    def write(self, data):
        return self.f.write(data)

    def tell(self):
        return self.f.tell() - self.base

    def seek(self, pos, whence=0):
        if whence == 0:
            return self.f.seek(self.base + pos) - self.base
        return self.f.seek(pos, whence) - self.base

    def flush(self):
        self.f.flush()


def compress_type(path, size):
    """I file che non si comprimono (gia' compressi o pesi di modelli poco comprimibili) vengono solo archiviati."""
    if size < (1 << 20):
        return zipfile.ZIP_DEFLATED
    with open(path, "rb") as f:
        sample = f.read(1 << 20)
    return zipfile.ZIP_STORED if len(zlib.compress(sample, 1)) > 0.97 * len(sample) else zipfile.ZIP_DEFLATED


def payload_items(ed, extra):
    """(file su disco, nome nell'archivio) e cartelle vuote: programma, runtime/, models/ e i file creati qui."""
    roots = [(os.path.join(SOURCES, ed["folder"]), "", EXCLUDE_TOP), (os.path.join(DEPS, ed["runtime"]), "runtime/", ())]
    if ed["models"]:
        roots.append((MODELS, "models/", ()))
    files, empty_dirs = [], []
    for root, prefix, exclude in roots:
        for base, dirs, names in os.walk(root):
            rel = os.path.relpath(base, root)
            if rel == ".":
                dirs[:] = [d for d in dirs if d.lower() not in exclude]
                names = [n for n in names if n.lower() not in exclude]
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            names = [n for n in names if not n.endswith((".pyc", ".pyo"))]
            arc_dir = prefix + ("" if rel == "." else rel.replace(os.sep, "/") + "/")
            if rel != "." and not dirs and not names:
                empty_dirs.append((base, arc_dir))
            for n in sorted(names):
                files.append((os.path.join(base, n), arc_dir + n))
    files += extra
    arcs = [a for _, a in files]
    assert len(arcs) == len(set(arcs)), "nomi doppi nell'archivio"
    return files, empty_dirs


def write_payload(out_file, base, files, empty_dirs):
    total = sum(os.path.getsize(p) for p, _ in files)
    mtimes, done, last, t0 = {}, 0, 0.0, time.time()
    stored = 0
    with zipfile.ZipFile(OffsetWriter(out_file, base), "w", zipfile.ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True, strict_timestamps=False) as z:
        for path, arc in empty_dirs:
            z.write(path, arc)
        for path, arc in files:
            st = os.stat(path)
            kind = compress_type(path, st.st_size)
            stored += kind == zipfile.ZIP_STORED
            z.write(path, arc, compress_type=kind)
            mtimes[arc] = st.st_mtime_ns
            done += st.st_size
            if time.time() - last > 10:
                last = time.time()
                print(f"    {done / total:6.1%}  {done / 2**30:.2f} di {total / 2**30:.2f} GB  ({time.time() - t0:.0f} s)",
                      flush=True)
        z.writestr(META_PREFIX + "mtimes.json", json.dumps(mtimes, separators=(",", ":")))
    return len(files), len(empty_dirs), total, stored


def verify(exe, n_files, required):
    """Rilettura completa: coda, kit e CRC di ogni file dell'archivio (come fara' l'installer)."""
    with open(exe, "rb") as f:
        f.seek(-SFX_TRAILER.size, 2)
        magic, ko, kl, po, pl = SFX_TRAILER.unpack(f.read(SFX_TRAILER.size))
        size = f.seek(0, 2)
        assert magic == SFX_MAGIC and po + pl == size - SFX_TRAILER.size and ko + kl == po, "coda non valida"
        f.seek(ko)
        kit = f.read(kl)
    with zipfile.ZipFile(io.BytesIO(kit)) as z:
        assert z.testzip() is None, "kit danneggiato"
        assert {"germano_install.py", "setup.json", "favicon.ico", "runtime/pythonw.exe"} <= set(z.namelist())
    with open(exe, "rb") as raw:
        raw.seek(po)

        class Sub:   # stessa vista usata dall'installer (SubFile)
            pos = 0

            def seekable(self):
                return True

            def tell(self):
                return self.pos

            def seek(self, p, whence=0):
                self.pos = {0: 0, 1: self.pos, 2: pl}[whence] + p
                return self.pos

            def read(self, n=-1):
                n = pl - self.pos if n is None or n < 0 else min(n, pl - self.pos)
                raw.seek(po + self.pos)
                data = raw.read(n)
                self.pos += len(data)
                return data
        with zipfile.ZipFile(Sub()) as z:
            names = [i for i in z.infolist() if not i.is_dir() and not i.filename.startswith(META_PREFIX)]
            assert len(names) == n_files, f"{len(names)} file nell'archivio invece di {n_files}"
            missing = set(required) - {i.filename for i in names}
            assert not missing, f"mancano nell'archivio: {sorted(missing)}"
            bad = z.testzip()
            assert bad is None, f"CRC errato: {bad}"
    return True


def build(edition_key):
    ed = EDITIONS[edition_key]
    pkg = os.path.join(SOURCES, ed["folder"])
    version = open(os.path.join(pkg, "VERSION"), encoding="utf-8-sig").read().strip()
    icon = os.path.join(pkg, "static", "favicon.ico") if edition_key == "suite" else os.path.join(pkg, "favicon.ico")
    out = os.path.join(OUT_DIR, ed["file"].format(v=version))
    print(f"== {ed['product']} {version} -> {out}", flush=True)
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        germano_exe = build_exe.build_germano_exe(pkg, build_exe.default_template(), os.path.join(tmp, "Germano.exe"))
        # stesso nome del file finale (Proprieta' > Dettagli > Nome originale)
        stub = open(compile_stub(ed, version, icon, os.path.join(tmp, os.path.basename(out))), "rb").read()
        kit = build_kit(pkg, edition_key, version, ed["product"], icon)
        files, empty_dirs = payload_items(ed, [(germano_exe, "Germano.exe")])
        print(f"  avviatore {len(stub):,} byte, kit {len(kit):,} byte", flush=True)
        part = out + ".part"
        with open(part, "wb") as f:
            f.write(stub)
            kit_off = f.tell()
            f.write(kit)
            pay_off = f.tell()
            n_files, n_dirs, total, stored = write_payload(f, pay_off, files, empty_dirs)
            f.seek(0, 2)
            pay_len = f.tell() - pay_off
            f.write(SFX_TRAILER.pack(SFX_MAGIC, kit_off, len(kit), pay_off, pay_len))
    print(f"  archivio: {n_files:,} file ({stored} solo archiviati) + {n_dirs} cartelle vuote, "
          f"{total / 2**30:.2f} GB -> {pay_len / 2**30:.2f} GB in {time.time() - t0:.0f} s", flush=True)
    print("  verifica completa (CRC di ogni file)...", flush=True)
    required = ["Germano.exe", "germano_desktop.py", "VERSION", "runtime/python.exe", "runtime/pythonw.exe"]
    if ed["models"]:
        required += ["server.py", "models/privacy-filter/config.json", "models/italian-ner-xxl/config.json"]
    verify(part, n_files, required)
    os.replace(part, out)
    others = sorted(set(os.listdir(OUT_DIR)) - {e["file"].format(v=version) for e in EDITIONS.values()})
    if others:
        print(f"  ATTENZIONE: in {OUT_DIR} ci sono anche: {others}")
    print(f"  OK {out}: {os.path.getsize(out):,} byte ({os.path.getsize(out) / 2**30:.2f} GB) in {time.time() - t0:.0f} s")
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "tutti"
    for key in (["client", "suite"] if which == "tutti" else [which]):
        build(key)
