"""Costruisce i pacchetti Debian/Ubuntu AUTOSUFFICIENTI (nessuna dipendenza, nessun download all'installazione):
  germano.ai-0.60/releases/linux/germano-0.60.deb          suite completa  -> /opt/germano
  germano.ai-0.60/releases/linux/germano-client-0.60.deb   client leggero  -> /opt/germano-client
partendo da sorgenti/linux/<edizione>, dipendenze/linux (Python portabile + librerie in versione Linux) e modelli/.

Il .deb e' scritto direttamente (archivio «ar» con debian-binary, control.tar.gz e data.tar.gz), quindi si
costruisce anche su Windows, senza dpkg-deb. Permessi, proprietario (root) e collegamenti simbolici del runtime
vengono impostati qui, non dipendono dal disco di Windows. Contenuto:
  /opt/<cartella>/                  programma, runtime/ (CPython 3.11 + librerie), models/ (solo suite)
  /usr/bin/<comando>                germano-ai / germano-ai-client
  /usr/share/applications/          voce di menu (con l'azione «Cartelle di lavoro» per la suite)
  /usr/share/icons/hicolor/         icona ufficiale 48-512 px
  /usr/share/doc/<pacchetto>/       copyright
postinst compila la cache dei moduli Python (la cartella del programma non e' scrivibile dagli utenti, come per ogni
pacchetto Debian di Python) e aggiorna menu e icone; prerm toglie quella cache. I dati restano nella cartella
dell'utente (Documenti/Germano AI) e non vengono mai toccati dalla disinstallazione.

Uso: python costruisci_deb.py [germano|germano-client|tutti]
"""
import gzip
import hashlib
import io
import os
import re
import struct
import sys
import tarfile
import time
import zipfile

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BUILD = os.path.dirname(os.path.abspath(__file__))
RELEASE = os.path.abspath(os.path.join(BUILD, "..", "..", "..", ".."))
DEPS = os.path.join(RELEASE, "dipendenze", "linux")
MODELS = os.path.join(RELEASE, "modelli")
EDITIONS = {
    "germano": {"package": "germano-ai", "folder": "germano", "command": "germano-ai", "desktop": "germano-ai",
                "title": "Germano AI", "file": "germano-{v}.deb",
                "summary": "Germano AI - anonimizzazione dei documenti, 100% offline",
                "long": ["Germano AI anonimizza documenti e testi direttamente su questo computer: i dati personali",
                         "vengono sostituiti da etichette prima di qualsiasi uso con servizi di intelligenza",
                         "artificiale. Include il runtime Python, tutte le librerie e i 6 modelli IA: funziona",
                         "senza Internet e non scarica nulla durante l'installazione."]},
    "germano-client": {"package": "germano-ai-client", "folder": "germano-client", "command": "germano-ai-client",
                       "desktop": "germano-ai-client", "title": "Germano AI Client", "file": "germano-client-{v}.deb",
                       "summary": "Germano AI Client - collega questo PC al Server Germano AI della rete locale",
                       "long": ["Client leggero di Germano AI: collega questo computer al Server Germano AI della rete",
                                "locale, che anonimizza i dati prima che arrivino alle AI. Include il runtime Python e le",
                                "librerie: non scarica nulla durante l'installazione."]},
}
APP_EXCLUDE_TOP = {"build", "germano.desktop", "__pycache__", "runtime", "models", "state", "cache", "update", "input",
                   "output", "processed", "failed", "extracted", "desktop.log", "server_stdout.log", "daemon.log",
                   "germano_install.json"}
EXECUTABLE_APP = re.compile(r"(^|/)germano\.sh$")
PBS_SKIP = re.compile(r"^python/lib/python3\.11/(test|idlelib|turtledemo|tkinter/test|lib2to3/tests|ensurepip/_bundled)/")


class Entry:
    __slots__ = ("kind", "mode", "mtime", "size", "link", "loader")

    def __init__(self, kind, mode, mtime, size=0, link="", loader=None):
        self.kind, self.mode, self.mtime, self.size, self.link, self.loader = kind, mode, mtime, size, link, loader


def add_dirs(entries, path, mtime):
    parts = path.strip("/").split("/")[:-1]
    for i in range(1, len(parts) + 1):
        d = "/".join(parts[:i])
        if d not in entries:
            entries[d] = Entry("dir", 0o755, mtime)


def put_file(entries, path, mode, mtime, size, loader):
    add_dirs(entries, path, mtime)
    entries[path] = Entry("file", mode, mtime, size, loader=loader)


def from_disk(entries, src_root, dst_root, exclude_top=frozenset()):
    for base, dirs, files in os.walk(src_root):
        rel = os.path.relpath(base, src_root)
        if rel == ".":
            dirs[:] = [d for d in dirs if d.lower() not in exclude_top]
            files = [f for f in files if f.lower() not in exclude_top]
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                continue
            p = os.path.join(base, f)
            r = os.path.relpath(p, src_root).replace(os.sep, "/")
            st = os.stat(p)
            if f.endswith(".sh"):      # script di avvio: fine riga Unix anche se il file e' stato salvato su Windows
                data = open(p, "rb").read().replace(b"\r\n", b"\n")
                put_file(entries, f"{dst_root}/{r}", 0o755, int(st.st_mtime), len(data), (lambda d=data: io.BytesIO(d)))
                continue
            mode = 0o755 if EXECUTABLE_APP.search(r) else 0o644
            put_file(entries, f"{dst_root}/{r}", mode, int(st.st_mtime), st.st_size,
                     (lambda p=p: open(p, "rb")))


def from_xcb_libs(entries, site, doc):
    """Librerie X11 per il plugin xcb di Qt assenti in Ubuntu 26.04 Desktop (vedi scarica_dipendenze.py): accanto
    alle librerie Qt, che le cercano li' (RUNPATH $ORIGIN); le licenze in /usr/share/doc/<pacchetto>/xcb."""
    src = os.path.join(DEPS, "librerie-xcb")
    qt_lib = f"{site}/PySide6/Qt/lib"
    assert qt_lib in entries, "PySide6 non incluso: le librerie xcb non servono"
    n = 0
    for f in sorted(os.listdir(src)):
        p = os.path.join(src, f)
        mt = int(os.path.getmtime(p))
        if re.search(r"\.so\.\d+$", f):
            target = f"{qt_lib}/{f}"
            assert target not in entries, f"{f} e' gia' nella wheel di Qt"
            put_file(entries, target, 0o644, mt, os.path.getsize(p), (lambda p=p: open(p, "rb")))
            n += 1
        elif f.endswith(".copyright") or f == "ORIGINE.txt":
            put_file(entries, f"{doc}/xcb/{f}", 0o644, mt, os.path.getsize(p), (lambda p=p: open(p, "rb")))
    assert n == 7, f"attese 7 librerie xcb, trovate {n}: eseguire scarica_dipendenze.py linux-xcb"
    return n


class HashingReader:
    """Legge un file a blocchi per tarfile calcolandone l'MD5 (md5sums del pacchetto) senza caricarlo in memoria."""

    def __init__(self, f):
        self.f, self.md5, self.count = f, hashlib.md5(), 0

    def read(self, n=-1):
        data = self.f.read(n)
        self.md5.update(data)
        self.count += len(data)
        return data


def from_python_tarball(entries, tarball, dst_root):
    """Runtime CPython portabile: si mantengono permessi e collegamenti simbolici dell'archivio originale."""
    count = 0
    with tarfile.open(tarball, "r:gz") as tar:
        for m in tar:
            name = m.name
            if not name.startswith("python/") or PBS_SKIP.match(name + ("/" if m.isdir() else "")) or "/__pycache__/" in name:
                continue
            path = f"{dst_root}/runtime/{name[len('python/'):]}".rstrip("/")
            if m.isdir():
                add_dirs(entries, path + "/x", m.mtime)
                entries[path] = Entry("dir", 0o755, m.mtime)
            elif m.issym():
                add_dirs(entries, path, m.mtime)
                entries[path] = Entry("link", 0o777, m.mtime, link=m.linkname)
            elif m.isfile():
                data = tar.extractfile(m).read()
                put_file(entries, path, m.mode & 0o777 or 0o644, m.mtime, len(data), (lambda d=data: io.BytesIO(d)))
                count += 1
    return count


def from_wheel(entries, wheel, site, runtime):
    z = zipfile.ZipFile(wheel)
    mtime = int(time.mktime(time.localtime()))
    n = 0
    for info in z.infolist():
        if info.is_dir():
            continue
        name = info.filename
        m = re.match(r"^[^/]+\.data/([^/]+)/(.*)$", name)
        if m:
            kind, rest = m.groups()
            if kind in ("purelib", "platlib"):
                target = f"{site}/{rest}"
            elif kind == "data":
                target = f"{runtime}/{rest}"
            else:            # scripts e headers: non servono all'app
                continue
        else:
            target = f"{site}/{name}"
        mode = (info.external_attr >> 16) & 0o777 or 0o644
        mode |= 0o644
        dt = info.date_time
        mt = int(time.mktime((dt[0], dt[1], dt[2], dt[3], dt[4], dt[5], 0, 0, -1))) if dt[0] >= 1980 else mtime
        put_file(entries, target, mode, mt, info.file_size, (lambda z=z, info=info: z.open(info)))
        n += 1
    return n


def lock_wheels(edition):
    lock = os.path.join(DEPS, f"requisiti-{edition}-x86_64.txt")
    with open(lock, encoding="utf-8") as f:
        return [line.split("#", 1)[1].strip() for line in f if "#" in line and not line.startswith("#")]


def ar_member(name, data_size, mtime, mode=0o100644):
    header = (f"{name:<16}{mtime:<12}{0:<6}{0:<6}{mode:<8o}{data_size:<10}").encode("ascii") + b"`\n"
    assert len(header) == 60
    return header


def tar_bytes(members):
    """control.tar.gz: (nome, contenuto, permessi)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tar:
        d = tarfile.TarInfo("./")
        d.type, d.mode, d.mtime, d.uname, d.gname = tarfile.DIRTYPE, 0o755, int(time.time()), "root", "root"
        tar.addfile(d)
        for name, content, mode in members:
            ti = tarfile.TarInfo(f"./{name}")
            ti.size, ti.mode, ti.mtime, ti.uname, ti.gname = len(content), mode, int(time.time()), "root", "root"
            tar.addfile(ti, io.BytesIO(content))
    return buf.getvalue()


def build(edition):
    ed = EDITIONS[edition]
    src = os.path.join(RELEASE, "sorgenti", "linux", edition)
    version = open(os.path.join(src, "VERSION"), encoding="utf-8-sig").read().strip()
    out = os.path.join(RELEASE, "releases", "linux", ed["file"].format(v=version))
    root = f"opt/{ed['folder']}"
    t0 = time.time()
    print(f"== {ed['package']} {version} -> {out}")
    entries = {}
    from_disk(entries, src, root, APP_EXCLUDE_TOP)
    info = ('{\n  "edition": "%s",\n  "version": "%s",\n  "installer": "deb",\n  "app_dir": "/%s",\n'
            '  "data_dir": null,\n  "tech_dir": null\n}\n' % ("suite" if edition == "germano" else "client", version, root))
    put_file(entries, f"{root}/germano_install.json", 0o644, int(time.time()), len(info),
             (lambda d=info.encode(): io.BytesIO(d)))
    pbs = [os.path.join(DEPS, "python", f) for f in os.listdir(os.path.join(DEPS, "python"))
           if f.endswith("x86_64-unknown-linux-gnu-install_only_stripped.tar.gz")][0]
    n_py = from_python_tarball(entries, pbs, root)
    site = f"{root}/runtime/lib/python3.11/site-packages"
    wheels = lock_wheels(edition)
    n_whl = sum(from_wheel(entries, os.path.join(DEPS, "wheels-x86_64", w), site, f"{root}/runtime") for w in wheels)
    n_xcb = from_xcb_libs(entries, site, f"usr/share/doc/{ed['package']}")
    if edition == "germano":
        from_disk(entries, MODELS, f"{root}/models")
    # comando, voce di menu, icone, copyright
    launcher = f"#!/bin/sh\n# {ed['title']}: avvia il programma installato in /{root}\nexec /{root}/germano.sh \"$@\"\n"
    put_file(entries, f"usr/bin/{ed['command']}", 0o755, int(time.time()), len(launcher),
             (lambda d=launcher.encode(): io.BytesIO(d)))
    actions = ""
    if edition == "germano":
        actions = ("Actions=cartelle;\n\n[Desktop Action cartelle]\nName=Cartelle di lavoro\nName[en]=Work folders\n"
                   "Exec=sh -c 'xdg-open \"$(xdg-user-dir DOCUMENTS)/Germano AI\" || xdg-open \"$HOME/Documents/Germano AI\"'\n")
    desktop = (f"[Desktop Entry]\nType=Application\nVersion=1.0\nName={ed['title']}\n"
               f"GenericName=Anonimizzazione dei documenti\nGenericName[en]=Document anonymization\n"
               f"Comment={ed['summary']}\nExec=/{root}/germano.sh\nIcon={ed['desktop']}\nTerminal=false\n"
               f"Categories=Office;Utility;Security;\nStartupNotify=true\nStartupWMClass={ed['desktop']}\n" +
               (actions and "" ) + actions)
    put_file(entries, f"usr/share/applications/{ed['desktop']}.desktop", 0o644, int(time.time()), len(desktop.encode()),
             (lambda d=desktop.encode(): io.BytesIO(d)))
    for size in (48, 128, 256, 512):
        icon = os.path.join(src, "icons", f"{size}.png")
        put_file(entries, f"usr/share/icons/hicolor/{size}x{size}/apps/{ed['desktop']}.png", 0o644,
                 int(os.path.getmtime(icon)), os.path.getsize(icon), (lambda p=icon: open(p, "rb")))
    copyright_text = (f"Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\nUpstream-Name: "
                      f"{ed['title']}\nSource: https://germano.ai\n\nFiles: *\nCopyright: germano.ai\nLicense: GPL-3\n"
                      f" Il testo completo della licenza e' in /{root}/LICENSE e in /usr/share/common-licenses/GPL-3.\n"
                      f" Il runtime Python (PSF License) e le librerie incluse hanno le proprie licenze, nelle\n"
                      f" rispettive cartelle *.dist-info sotto /{site}.\n"
                      f" Le librerie X11 libxcb-* e libxkbcommon-x11 in /{site}/PySide6/Qt/lib vengono dai\n"
                      f" pacchetti di Ubuntu 26.04 (licenze MIT/X11): testi e provenienza in\n"
                      f" /usr/share/doc/{ed['package']}/xcb.\n")
    put_file(entries, f"usr/share/doc/{ed['package']}/copyright", 0o644, int(time.time()), len(copyright_text.encode()),
             (lambda d=copyright_text.encode(): io.BytesIO(d)))

    files = [p for p, e in entries.items() if e.kind == "file"]
    installed_kb = sum(entries[p].size for p in files) // 1024 + len(entries) // 4
    print(f"  {len(files):,} file ({n_py:,} del runtime Python, {n_whl:,} dalle {len(wheels)} librerie, {n_xcb} "
          f"librerie X11 per Qt), {sum(entries[p].size for p in files) / 2**30:.2f} GB installati")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    part = out + ".part"
    md5 = []
    with open(part, "wb") as deb:
        deb.write(b"!<arch>\n")
        deb.write(ar_member("debian-binary", 4, int(time.time())) + b"2.0\n")
        # data.tar.gz prima, per conoscere md5sums e dimensioni; lo spazio per control.tar.gz si sistema dopo
        data_tmp = part + ".data"
        with open(data_tmp, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6, mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w|", format=tarfile.GNU_FORMAT) as tar:
                    root_ti = tarfile.TarInfo("./")
                    root_ti.type, root_ti.mode, root_ti.uname, root_ti.gname = tarfile.DIRTYPE, 0o755, "root", "root"
                    root_ti.mtime = int(time.time())
                    tar.addfile(root_ti)
                    for path in sorted(entries, key=lambda p: p.split("/")):
                        e = entries[path]
                        ti = tarfile.TarInfo("./" + path + ("/" if e.kind == "dir" else ""))
                        ti.mode, ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = e.mode, e.mtime, 0, 0, "root", "root"
                        if e.kind == "dir":
                            ti.type = tarfile.DIRTYPE
                            tar.addfile(ti)
                        elif e.kind == "link":
                            ti.type, ti.linkname = tarfile.SYMTYPE, e.link
                            tar.addfile(ti)
                        else:
                            ti.size = e.size
                            with e.loader() as fsrc:
                                reader = HashingReader(fsrc)
                                tar.addfile(ti, reader)
                                assert reader.count == e.size and not fsrc.read(1), f"dimensione cambiata: {path}"
                            md5.append(f"{reader.md5.hexdigest()}  {path}\n")
        control = (f"Package: {ed['package']}\nVersion: {version}\nArchitecture: amd64\n"
                   f"Maintainer: Germano AI <info@germano.ai>\nInstalled-Size: {installed_kb}\nSection: utils\n"
                   f"Priority: optional\nHomepage: https://germano.ai\nDescription: {ed['summary']}\n" +
                   "".join(f" {line}\n" for line in ed["long"]))
        postinst = ("#!/bin/sh\nset -e\nif [ \"$1\" = configure ]; then\n"
                    f"  # cache dei moduli Python: /{root} non e' scrivibile dagli utenti\n"
                    f"  /{root}/runtime/bin/python3 -m compileall -q -j 0 /{root} >/dev/null 2>&1 || true\n"
                    "  if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database -q "
                    "/usr/share/applications || true; fi\n"
                    "  if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -q -t -f "
                    "/usr/share/icons/hicolor || true; fi\nfi\nexit 0\n")
        prerm = ("#!/bin/sh\nset -e\ncase \"$1\" in\n  remove|upgrade|deconfigure)\n"
                 f"    find /{root} -type d -name __pycache__ -prune -exec rm -rf {{}} + 2>/dev/null || true ;;\n"
                 "esac\nexit 0\n")
        postrm = ("#!/bin/sh\nset -e\nif command -v update-desktop-database >/dev/null 2>&1; then "
                  "update-desktop-database -q /usr/share/applications || true; fi\nexit 0\n")
        ctrl = tar_bytes([("control", control.encode(), 0o644), ("md5sums", "".join(md5).encode(), 0o644),
                          ("postinst", postinst.encode(), 0o755), ("prerm", prerm.encode(), 0o755),
                          ("postrm", postrm.encode(), 0o755)])
        deb.write(ar_member("control.tar.gz", len(ctrl), int(time.time())) + ctrl + (b"\n" if len(ctrl) % 2 else b""))
        data_size = os.path.getsize(data_tmp)
        deb.write(ar_member("data.tar.gz", data_size, int(time.time())))
        with open(data_tmp, "rb") as raw:
            while True:
                chunk = raw.read(1 << 22)
                if not chunk:
                    break
                deb.write(chunk)
        if data_size % 2:
            deb.write(b"\n")
        os.remove(data_tmp)
    verify(part, ed, root, len(files))
    os.replace(part, out)
    print(f"  OK {os.path.basename(out)}: {os.path.getsize(out) / 2**30:.2f} GB in {time.time() - t0:.0f} s")
    return out


def verify(deb, ed, root, n_files):
    """Rilettura: struttura ar, campi di control, script, e ogni file di data.tar.gz (permessi chiave inclusi)."""
    with open(deb, "rb") as f:
        assert f.read(8) == b"!<arch>\n"
        members = {}
        while True:
            h = f.read(60)
            if not h:
                break
            name, size = h[:16].decode().strip(), int(h[48:58].decode().strip())
            members[name] = (f.tell(), size)
            f.seek(size + (size % 2), 1)
    assert list(members) == ["debian-binary", "control.tar.gz", "data.tar.gz"], list(members)
    with open(deb, "rb") as f:
        f.seek(members["control.tar.gz"][0])
        ctrl = tarfile.open(fileobj=io.BytesIO(f.read(members["control.tar.gz"][1])), mode="r:gz")
        control = ctrl.extractfile("./control").read().decode()
        assert f"Package: {ed['package']}" in control and "Architecture: amd64" in control
        assert ctrl.getmember("./postinst").mode == 0o755
        f.seek(members["data.tar.gz"][0])
        need = {f"./{root}/germano_desktop.py", f"./{root}/germano.sh", f"./{root}/runtime/bin/python3",
                f"./usr/bin/{ed['command']}", f"./usr/share/applications/{ed['desktop']}.desktop"}
        modes, n = {}, 0
        with tarfile.open(fileobj=f, mode="r|gz") as data:
            for m in data:
                if m.isfile():
                    n += 1
                if m.name in need or m.name.endswith(("/QtWebEngineProcess", "/python3.11")):
                    modes[m.name] = (m.type, oct(m.mode))
    missing = need - set(modes)
    assert not missing, f"mancano {missing}"
    assert n == n_files, f"{n} file in data.tar.gz invece di {n_files}"
    assert modes[f"./{root}/germano.sh"][1] == "0o755" and modes[f"./usr/bin/{ed['command']}"][1] == "0o755"
    print(f"  verifica: control, script e {n:,} file riletti; permessi: " +
          ", ".join(f"{k.split('/')[-1]}={v[1]}" for k, v in sorted(modes.items())))


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "tutti"
    for key in (["germano-client", "germano"] if which == "tutti" else [which]):
        build(key)
