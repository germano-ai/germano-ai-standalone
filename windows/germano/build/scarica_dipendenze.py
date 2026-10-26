"""Scarica le dipendenze OFFLINE per Linux e macOS in germano.ai-0.60/dipendenze/<os>/:
- l'interprete Python portabile (python-build-standalone, CPython 3.11 come il runtime Windows), verificato con
  l'impronta SHA256SUMS pubblicata nella release;
- tutte le librerie (wheel binari) nelle STESSE versioni del runtime Windows collaudato, piu' quelle della finestra
  dell'app: pywebview con Qt WebEngine (Linux) o con WebKit di sistema via PyObjC (macOS).

pip download --platform valuta i marcatori delle dipendenze per il sistema su cui gira (Windows), non per quello di
destinazione: qui le dipendenze di ogni wheel si leggono dal suo METADATA e si valutano per Linux o macOS, fino a
ottenere l'insieme completo. Nessun file viene eseguito: si scaricano solo archivi.

Per Linux anche le poche librerie di sistema che Qt usa con X11 e che Ubuntu 26.04 Desktop non installa
(dipendenze/linux/librerie-xcb, dai pacchetti ufficiali dell'archivio Ubuntu): con Wayland, predefinito su Ubuntu
26.04, non servono, ma cosi' la finestra funziona anche in una sessione X11 senza installare nulla.

Uso: python scarica_dipendenze.py linux|macos|linux-xcb
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
import zipfile

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BUILD = os.path.dirname(os.path.abspath(__file__))
RELEASE = os.path.abspath(os.path.join(BUILD, "..", "..", "..", ".."))           # germano.ai-0.60
WIN_RUNTIME = os.path.join(RELEASE, "dipendenze", "windows", "runtime-germano")
WIN_CLIENT_RUNTIME = os.path.join(RELEASE, "dipendenze", "windows", "runtime-germano-client")
PYTHON = os.path.join(WIN_RUNTIME, "python.exe")
sys.path.insert(0, os.path.join(WIN_RUNTIME, "Lib", "site-packages", "pip", "_vendor"))
from packaging.requirements import Requirement  # noqa: E402
from packaging.utils import canonicalize_name  # noqa: E402
from packaging.version import Version  # noqa: E402

PBS_RELEASE = "20261021"
PBS_VERSION = "3.11.17"
PBS_URL = "https://github.com/astral-sh/python-build-standalone/releases/download/{rel}/{name}"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
NOT_FOR_UNIX = {"pywin32", "pip"}            # solo Windows / non serve all'app

TARGETS = {
    "linux": [{"arch": "x86_64", "editions": ("germano", "germano-client"),
               "pbs": "x86_64-unknown-linux-gnu",
               "platforms": [f"manylinux_2_{v}_x86_64" for v in (39, 35, 34, 31, 28, 27, 24, 17, 12, 5)] +
                            ["manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64", "linux_x86_64"],
               "env": {"sys_platform": "linux", "platform_system": "Linux", "platform_machine": "x86_64",
                       "os_name": "posix"},
               "window": ["pywebview", "QtPy", "PySide6-Essentials", "PySide6-Addons", "PySide6-WebEngine",
                          "shiboken6"]}],
    "macos": [{"arch": "arm64", "editions": ("germano", "germano-client"),
               "pbs": "aarch64-apple-darwin",
               "platforms": [f"macosx_{v}_0_arm64" for v in (15, 14, 13, 12, 11)] +
                            [f"macosx_{v}_0_universal2" for v in (15, 14, 13, 12, 11)] +
                            [f"macosx_10_{v}_universal2" for v in (16, 15, 14, 13, 12, 11, 10, 9)],
               "env": {"sys_platform": "darwin", "platform_system": "Darwin", "platform_machine": "arm64",
                       "os_name": "posix"},
               "window": ["pywebview"]},
              # Mac Intel: solo il client (PyTorch non pubblica piu' torch per macOS Intel dalla 2.3)
              {"arch": "x86_64", "editions": ("germano-client",),
               "pbs": "x86_64-apple-darwin",
               "platforms": [f"macosx_{v}_0_x86_64" for v in (15, 14, 13, 12, 11)] +
                            [f"macosx_10_{v}_x86_64" for v in (16, 15, 14, 13, 12, 11, 10, 9)] +
                            [f"macosx_{v}_0_universal2" for v in (15, 14, 13, 12, 11)] +
                            [f"macosx_10_{v}_universal2" for v in (16, 15, 14, 13, 12, 11, 10, 9)],
               "env": {"sys_platform": "darwin", "platform_system": "Darwin", "platform_machine": "x86_64",
                       "os_name": "posix"},
               "window": ["pywebview"]}],
}
BASE_ENV = {"python_version": "3.11", "python_full_version": PBS_VERSION, "implementation_name": "cpython",
            "platform_python_implementation": "CPython", "implementation_version": PBS_VERSION, "extra": ""}
# Librerie richieste dal plugin X11 (xcb) di Qt e assenti nel manifesto di Ubuntu 26.04.1 Desktop (controllo delle
# dipendenze ELF di tutti i binari del pacchetto: tutte le altre sono gia' nel sistema). Si prendono da Ubuntu 22.04
# LTS: stesso soname, ma compilate con glibc 2.35, quindi si caricano su tutte le distribuzioni che Qt 6.12 supporta
# (glibc 2.34 o successiva); quelle della 26.04 richiedono glibc 2.38 (libxcb-cursor) e sui sistemi meno recenti
# impedirebbero al plugin X11 di caricarsi.
UBUNTU = {"mirror": "https://archive.ubuntu.com/ubuntu/", "dist": "jammy", "name": "Ubuntu 22.04 LTS",
          "max_glibc": (2, 34),
          "packages": ("libxcb-cursor0", "libxcb-icccm4", "libxcb-image0", "libxcb-keysyms1", "libxcb-render-util0",
                       "libxcb-xkb1", "libxkbcommon-x11-0")}


def windows_lock(runtime):
    """{nome canonico: (nome, versione)} delle distribuzioni del runtime Windows collaudato."""
    out = subprocess.run([os.path.join(runtime, "python.exe"), "-B", "-I", "-c",
                          "import importlib.metadata as m, json; print(json.dumps([(d.metadata['Name'], d.version) "
                          "for d in m.distributions()]))"], capture_output=True, text=True, check=True).stdout
    return {canonicalize_name(n): (n, v) for n, v in json.loads(out)}


def wheel_meta(path):
    with zipfile.ZipFile(path) as z:
        meta = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA") and n.count("/") == 1)
        text = z.read(meta).decode("utf-8", errors="replace")
    name = re.search(r"^Name: (.+)$", text, re.M).group(1).strip()
    version = re.search(r"^Version: (.+)$", text, re.M).group(1).strip()
    requires = [m.group(1).strip() for m in re.finditer(r"^Requires-Dist: (.+)$", text, re.M)]
    return name, version, requires


def pip_download(req, dest, target, index=None):
    cmd = [PYTHON, "-B", "-m", "pip", "download", "--no-deps", "--only-binary=:all:", "--no-cache-dir",
           "--disable-pip-version-check", "--python-version", PBS_VERSION, "--implementation", "cp",
           "--abi", "cp311", "--abi", "abi3", "--abi", "none", "-d", dest]
    for p in target["platforms"]:
        cmd += ["--platform", p]
    if index:
        cmd += ["--index-url", index]
    r = subprocess.run(cmd + [req], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr)[-600:]


def pure_wheel_from_sdist(req, dest):
    """Per i rari pacchetti Python PURI pubblicati solo come sorgente (es. proxy_tools, richiesto da pywebview): la
    wheel si compone copiando i file .py, SENZA eseguire setup.py; l'archivio deve avere l'impronta SHA-256 indicata
    da PyPI e non contenere codice da compilare."""
    import base64
    import tarfile
    r = Requirement(req)
    info = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{r.name}/json", timeout=60))
    versions = sorted((v for v in info["releases"] if r.specifier.contains(v)), key=Version)
    if not versions:
        return False, f"nessuna versione di {req} su PyPI"
    version = versions[-1]
    sdist = next((u for u in info["releases"][version] if u["packagetype"] == "sdist"), None)
    if not sdist:
        return False, f"{r.name} {version}: nessun sorgente"
    data = urllib.request.urlopen(sdist["url"], timeout=120).read()
    if hashlib.sha256(data).hexdigest() != sdist["digests"]["sha256"]:
        return False, f"{r.name} {version}: impronta diversa da quella di PyPI"
    tar = tarfile.open(fileobj=io.BytesIO(data))
    names = [m.name for m in tar.getmembers() if m.isfile()]
    if any(n.endswith((".c", ".cc", ".cpp", ".pyx", ".so", ".pyd", ".rs", ".f90")) for n in names):
        return False, f"{r.name} {version}: contiene codice da compilare"
    root = names[0].split("/")[0]
    top = next((n for n in names if n.endswith(".egg-info/top_level.txt") and n.count("/") == 2), None)
    packages = tar.extractfile(top).read().decode().split() if top else []
    files = {}
    for m in tar.getmembers():
        rel = m.name[len(root) + 1:]
        if m.isfile() and rel.endswith(".py") and rel.split("/")[0].removesuffix(".py") in packages:
            files[rel] = tar.extractfile(m).read()
    if not files:
        return False, f"{r.name} {version}: nessun modulo Python trovato"
    pkg_info = tar.extractfile(f"{root}/PKG-INFO").read()
    dist = f"{re.sub(r'[-_.]+', '_', r.name)}-{version}"
    files[f"{dist}.dist-info/METADATA"] = pkg_info
    files[f"{dist}.dist-info/WHEEL"] = (b"Wheel-Version: 1.0\nGenerator: germano-build (copia del sorgente puro)\n"
                                        b"Root-Is-Purelib: true\nTag: py3-none-any\n")
    files[f"{dist}.dist-info/top_level.txt"] = ("\n".join(packages) + "\n").encode()
    record = "".join(f"{n},sha256={base64.urlsafe_b64encode(hashlib.sha256(b).digest()).rstrip(b'=').decode()},{len(b)}\n"
                     for n, b in sorted(files.items()))
    files[f"{dist}.dist-info/RECORD"] = (record + f"{dist}.dist-info/RECORD,,\n").encode()
    with zipfile.ZipFile(os.path.join(dest, f"{dist}-py3-none-any.whl"), "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items():
            z.writestr(n, b)
    return True, f"{r.name} {version}: wheel composta dal sorgente puro (sha256 {sdist['digests']['sha256'][:16]}...)"


def downloaded(dest):
    out = {}
    for f in os.listdir(dest):
        if f.endswith(".whl"):
            name, version, requires = wheel_meta(os.path.join(dest, f))
            out[canonicalize_name(name)] = (name, version, requires, f)
    return out


def fetch(target, wanted, dest, lock, notes):
    """Scarica i requisiti e poi, a ripetizione, le dipendenze mancanti valutate per il sistema di destinazione."""
    env = dict(BASE_ENV, **target["env"])
    os.makedirs(dest, exist_ok=True)
    queue = list(wanted)
    while queue:
        have = downloaded(dest)
        missing = []
        for req in queue:
            r = Requirement(req)
            key = canonicalize_name(r.name)
            if key in have:
                continue
            index = TORCH_CPU_INDEX if target["env"]["sys_platform"] == "linux" and key in ("torch", "torchvision") else None
            pin = lock.get(key)
            tries = []
            if pin and (not r.specifier or r.specifier.contains(Version(pin[1]).public, prereleases=True)):
                tries.append(f"{r.name}=={pin[1]}")
            tries.append(f"{r.name}{r.specifier}")
            for attempt in tries:
                ok, out = pip_download(attempt, dest, target, index)
                if ok:
                    if pin and attempt != f"{r.name}=={pin[1]}":
                        notes.append(f"{r.name}: versione {pin[1]} non disponibile per {target['arch']}, scaricata "
                                     f"la piu' recente compatibile")
                    print(f"  scaricato {attempt}")
                    break
            else:
                ok, why = pure_wheel_from_sdist(req, dest)     # solo per pacchetti puri senza wheel
                if not ok:
                    raise SystemExit(f"ERRORE: impossibile scaricare {req} per {target['arch']}:\n{out}\n{why}")
                notes.append(why)
                print(f"  {why}")
        have = downloaded(dest)
        for key, (name, version, requires, _f) in sorted(have.items()):
            for line in requires:
                r = Requirement(line)
                if r.marker and not r.marker.evaluate(env):
                    continue
                dep = canonicalize_name(r.name)
                if dep in NOT_FOR_UNIX:
                    continue
                if dep not in have:
                    missing.append(str(Requirement(f"{r.name}{r.specifier}")))
                elif r.specifier and not r.specifier.contains(Version(have[dep][1]).public, prereleases=True):
                    notes.append(f"ATTENZIONE {name} {version} richiede {r.name}{r.specifier}, scaricato {have[dep][1]}")
        queue = sorted(set(missing))
    return downloaded(dest)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_python(target, folder):
    name = f"cpython-{PBS_VERSION}+{PBS_RELEASE}-{target['pbs']}-install_only_stripped.tar.gz"
    path = os.path.join(folder, name)
    sums = urllib.request.urlopen(PBS_URL.format(rel=PBS_RELEASE, name="SHA256SUMS"), timeout=60).read().decode()
    expected = re.search(r"^([0-9a-f]{64})\s+" + re.escape(name) + r"$", sums, re.M).group(1)
    if not (os.path.isfile(path) and sha256(path) == expected):
        os.makedirs(folder, exist_ok=True)
        print(f"  scarico {name}...")
        urllib.request.urlretrieve(PBS_URL.format(rel=PBS_RELEASE, name=name.replace("+", "%2B")), path + ".part")
        if sha256(path + ".part") != expected:
            os.remove(path + ".part")
            raise SystemExit(f"ERRORE: impronta di {name} diversa da SHA256SUMS della release")
        os.replace(path + ".part", path)
    print(f"  Python {PBS_VERSION} per {target['pbs']}: verificato con SHA256SUMS ({expected[:16]}...)")
    return path


def fetch_ubuntu_libs(base):
    """Librerie xcb dai pacchetti ufficiali di Ubuntu (HTTPS), con la catena di impronte SHA256 InRelease -> indice
    Packages -> pacchetto .deb. Da ogni pacchetto si prende la libreria (col nome soname, es. libxcb-cursor.so.0) e
    il file copyright; data.tar.zst si apre con il tar di Windows (bsdtar, con zstd)."""
    import gzip
    import shutil
    import tarfile
    import tempfile
    dest = os.path.join(base, "librerie-xcb")
    mirror, dist = UBUNTU["mirror"], UBUNTU["dist"]
    print(f"== librerie X11 per Qt da {UBUNTU['name']} ({mirror})")
    inrelease = urllib.request.urlopen(f"{mirror}dists/{dist}/InRelease", timeout=60).read().decode("utf-8")
    sums = inrelease.split("SHA256:", 1)[1]
    stanzas = {}
    for comp in ("main", "universe"):
        rel = f"{comp}/binary-amd64/Packages.gz"
        m = re.search(r"^\s*([0-9a-f]{64})\s+(\d+)\s+" + re.escape(rel) + r"\s*$", sums, re.M)
        data = urllib.request.urlopen(f"{mirror}dists/{dist}/{rel}", timeout=600).read()
        if not m or hashlib.sha256(data).hexdigest() != m.group(1) or len(data) != int(m.group(2)):
            raise SystemExit(f"ERRORE: {rel} non corrisponde all'impronta di InRelease")
        for block in gzip.decompress(data).decode("utf-8", "replace").split("\n\n"):
            fields = dict(re.findall(r"^([A-Za-z0-9-]+): (.*)$", block, re.M))
            if fields.get("Package") in UBUNTU["packages"] and fields.get("Architecture") == "amd64":
                stanzas.setdefault(fields["Package"], dict(fields, Component=comp))
        if all(p in stanzas for p in UBUNTU["packages"]):
            break
    missing = [p for p in UBUNTU["packages"] if p not in stanzas]
    if missing:
        raise SystemExit(f"ERRORE: pacchetti non trovati in {dist}: {missing}")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    origin = [f"Librerie X11 (xcb) per Qt, dai pacchetti ufficiali di {UBUNTU['name']} ({dist}, amd64).",
              "Servono solo al plugin xcb di Qt (sessioni X11); con Wayland non vengono caricate. Mancano in Ubuntu",
              "26.04 Desktop; prese dalla 22.04 perche' richiedono al massimo glibc "
              f"{'.'.join(map(str, UBUNTU['max_glibc']))} (minimo gia' richiesto da Qt 6.12).",
              "Il pacchetto .deb di Germano le installa in runtime/lib/python3.11/site-packages/PySide6/Qt/lib.", ""]
    with tempfile.TemporaryDirectory() as tmp:
        for pkg in UBUNTU["packages"]:
            st = stanzas[pkg]
            deb = urllib.request.urlopen(mirror + st["Filename"], timeout=300).read()
            if hashlib.sha256(deb).hexdigest() != st["SHA256"]:
                raise SystemExit(f"ERRORE: impronta di {st['Filename']} diversa dall'indice Packages")
            assert deb[:8] == b"!<arch>\n"
            pos, members = 8, {}
            while pos < len(deb):
                name = deb[pos:pos + 16].decode().strip().rstrip("/")
                size = int(deb[pos + 48:pos + 58].decode().strip())
                members[name] = deb[pos + 60:pos + 60 + size]
                pos += 60 + size + (size % 2)
            data_name = next(n for n in members if n.startswith("data.tar"))
            packed, plain = os.path.join(tmp, f"{pkg}-{data_name}"), os.path.join(tmp, f"{pkg}.tar")
            with open(packed, "wb") as f:
                f.write(members[data_name])
            subprocess.run(["tar", "-c", "-f", plain, "--format", "pax", "@" + packed], check=True)
            with tarfile.open(plain) as tar:
                entries = {m.name.lstrip("./"): m for m in tar.getmembers()}
                libs = {n: m for n, m in entries.items()
                        if n.startswith("usr/lib/x86_64-linux-gnu/") and re.search(r"\.so\.\d+$", n)}
                for name, m in libs.items():
                    real = m
                    while real.issym():
                        real = entries[os.path.normpath(os.path.join(os.path.dirname(name), real.linkname)).replace(os.sep, "/")]
                    lib = tar.extractfile(real).read()
                    need = max((tuple(int(x) for x in v.split(b".")) for v in re.findall(rb"GLIBC_(2\.\d+(?:\.\d+)?)", lib)),
                               default=(2, 0))
                    if need[:2] > UBUNTU["max_glibc"]:
                        raise SystemExit(f"ERRORE: {os.path.basename(name)} richiede glibc {'.'.join(map(str, need))}")
                    with open(os.path.join(dest, os.path.basename(name)), "wb") as f:
                        f.write(lib)
                    origin.append(f"{os.path.basename(name)}  <- {pkg} {st['Version']} ({st['Component']}), "
                                  f"{os.path.basename(st['Filename'])} sha256 {st['SHA256']}")
                cr = entries.get(f"usr/share/doc/{pkg}/copyright")
                if cr is not None and cr.isfile():
                    with open(os.path.join(dest, f"{pkg}.copyright"), "wb") as f:
                        f.write(tar.extractfile(cr).read())
                print(f"  {pkg} {st['Version']}: {', '.join(sorted(os.path.basename(n) for n in libs))}")
    with open(os.path.join(dest, "ORIGINE.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(origin) + "\n")
    print(f"  {len(os.listdir(dest))} file in {dest}")


def main():
    which = sys.argv[1]
    if which == "linux-xcb":
        fetch_ubuntu_libs(os.path.join(RELEASE, "dipendenze", "linux"))
        return
    base = os.path.join(RELEASE, "dipendenze", which)
    locks = {"germano": windows_lock(WIN_RUNTIME), "germano-client": windows_lock(WIN_CLIENT_RUNTIME)}
    report = {}
    for target in TARGETS[which]:
        print(f"== {which} {target['arch']}")
        fetch_python(target, os.path.join(base, "python"))
        dest = os.path.join(base, f"wheels-{target['arch']}")
        notes = []
        for edition in target["editions"]:
            wanted = [f"{n}=={v}" for key, (n, v) in sorted(locks[edition].items()) if key not in NOT_FOR_UNIX]
            wanted += target["window"]
            have = fetch(target, wanted, dest, locks["germano"], notes)
            # insieme della singola edizione (il client usa solo le sue librerie)
            env = dict(BASE_ENV, **target["env"])
            closure, todo = set(), [canonicalize_name(Requirement(w).name) for w in wanted]
            while todo:
                key = todo.pop()
                if key in closure or key not in have:
                    continue
                closure.add(key)
                for line in have[key][2]:
                    r = Requirement(line)
                    if (not r.marker or r.marker.evaluate(env)) and canonicalize_name(r.name) not in NOT_FOR_UNIX:
                        todo.append(canonicalize_name(r.name))
            lock_file = os.path.join(base, f"requisiti-{edition}-{target['arch']}.txt")
            with open(lock_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(f"# {edition} per {which} {target['arch']} - Python {PBS_VERSION} - wheel in "
                        f"wheels-{target['arch']}/\n")
                for key in sorted(closure):
                    f.write(f"{have[key][0]}=={have[key][1]}  # {have[key][3]}\n")
            report[f"{edition}-{target['arch']}"] = len(closure)
        for n in sorted(set(notes)):
            print("  nota:", n)
        size = sum(os.path.getsize(os.path.join(dest, f)) for f in os.listdir(dest))
        print(f"  {len(os.listdir(dest))} wheel, {size / 2**20:.0f} MB in {dest}")
    print("pacchetti per edizione:", report)
    if which == "linux":
        fetch_ubuntu_libs(base)


if __name__ == "__main__":
    main()
