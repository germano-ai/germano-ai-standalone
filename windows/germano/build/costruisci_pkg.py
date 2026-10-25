"""Costruisce i pacchetti di installazione macOS (.pkg) AUTOSUFFICIENTI (nessun download all'installazione):
  germano.ai-0.60/releases/macos/germano-0.60.pkg          suite completa (Apple Silicon)
  germano.ai-0.60/releases/macos/germano-client-0.60.pkg   client leggero (Apple Silicon e Intel)
partendo da sorgenti/macos/<edizione>, dipendenze/macos (Python portabile + librerie per macOS) e modelli/.

Il .pkg e' un «product archive» scritto direttamente, senza gli strumenti di Apple (pkgbuild/productbuild), quindi
si costruisce anche su Windows. Struttura identica a quella prodotta da pkgbuild + productbuild:
- archivio xar: indice (TOC) compresso con zlib, impronta SHA-1 dell'indice e di ogni file;
- Distribution: destinazione «Installa solo per me» (~/Applications: l'Installer lavora come utente corrente,
  nessuna password di amministratore) oppure «per tutti gli utenti» (/Applications, chiede la password);
  architetture ammesse e versione minima di macOS (la piu' alta richiesta dalle librerie incluse);
- germano.pkg/PackageInfo, Bom (distinta dei file nel formato di mkbom/bomutils: albero di pagine da 256 voci,
  checksum POSIX cksum), Payload (cpio «odc» compresso gzip), Scripts (postinstall).
Germano.app contiene tutto: Contents/MacOS/Germano (lanciatore), Contents/Resources/germano.icns e
Contents/Resources/app (programma, runtime/ con Python 3.11 e le librerie, models/ per la suite). Il client si
installa in «Germano AI Client/Germano.app» per non sovrascrivere la suite. Il postinstall compila la cache dei moduli
Python. Il pacchetto non e' firmato da Apple (serve un Developer ID): al primo avvio macOS chiede conferma
(Impostazioni di Sistema > Privacy e sicurezza > Apri comunque).

Uso: python costruisci_pkg.py [germano|germano-client|tutti]
"""
import gzip
import hashlib
import io
import math
import os
import re
import struct
import sys
import tarfile
import time
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections import deque
from xml.sax.saxutils import escape

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BUILD = os.path.dirname(os.path.abspath(__file__))
RELEASE = os.path.abspath(os.path.join(BUILD, "..", "..", "..", ".."))
DEPS = os.path.join(RELEASE, "dipendenze", "macos")
MODELS = os.path.join(RELEASE, "modelli")
EDITIONS = {
    "germano": {"title": "Germano AI", "bundle": "Germano.app", "file": "germano-{v}.pkg", "archs": ("arm64",)},
    "germano-client": {"title": "Germano AI Client", "bundle": "Germano AI Client/Germano.app",
                       "file": "germano-client-{v}.pkg", "archs": ("arm64", "x86_64")},
}
PBS = {"arm64": "aarch64-apple-darwin", "x86_64": "x86_64-apple-darwin"}
RUNTIME_DIR = {"arm64": "runtime", "x86_64": "runtime-x86_64"}
BASE_MIN_OS = (11, 0)   # Python portabile per Apple Silicon: macOS 11 o successivo
APP_EXCLUDE_TOP = {"germano.app", "build", "__pycache__", "runtime", "runtime-x86_64", "models", "state", "cache",
                   "update", "input", "output", "processed", "failed", "extracted", "desktop.log", "server_stdout.log",
                   "daemon.log", "germano_install.json"}
PBS_SKIP = re.compile(r"^python/lib/python3\.11/(test|idlelib|turtledemo|tkinter/test|lib2to3/tests|ensurepip/_bundled)/")
UID, GID = 0, 80     # root:admin, come le app in /Applications; con «solo per me» i file sono dell'utente
S_IFDIR, S_IFREG, S_IFLNK = 0o040000, 0o100000, 0o120000
CHUNK = 1 << 22


# ------------------------------------------------------------------------------------------- cksum POSIX
_CRC = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if _c & 0x80000000 else (_c << 1) & 0xFFFFFFFF
    _CRC.append(_c)
_REV8 = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))


def cksum_reference(data):
    """cksum POSIX byte per byte, come crc32.cpp di bomutils (solo per il controllo dell'implementazione veloce)."""
    crc = 0
    for b in data:
        crc = _CRC[b ^ (crc >> 24)] ^ ((crc << 8) & 0xFFFFFFFF)
    n = len(data)
    while n:
        crc = _CRC[(n & 0xFF) ^ (crc >> 24)] ^ ((crc << 8) & 0xFFFFFFFF)
        n >>= 8
    return crc ^ 0xFFFFFFFF


class Cksum:
    """cksum POSIX (CRC-32 non riflesso, polinomio 0x04C11DB7, lunghezza in coda, bit invertiti) calcolato con
    zlib.crc32 (riflesso) sui byte a bit rovesciati: stesso risultato, velocita' del codice C."""

    def __init__(self):
        self.value, self.length = 0xFFFFFFFF, 0     # registro iniziale 0 (zlib applica xor 0xFFFFFFFF)

    def update(self, data):
        self.value = zlib.crc32(bytes(data).translate(_REV8), self.value)
        self.length += len(data)

    def digest(self):
        n, tail = self.length, bytearray()
        while n:
            tail.append(n & 0xFF)
            n >>= 8
        v = zlib.crc32(bytes(tail).translate(_REV8), self.value)
        return int(f"{v:032b}"[::-1], 2)


def cksum(data):
    c = Cksum()
    c.update(data)
    return c.digest()


def self_test():
    assert cksum(b"123456789") == cksum_reference(b"123456789") == 930766865   # printf 123456789 | cksum
    for sample in (b"", b"a", bytes(range(256)) * 3, os.urandom(70000)):
        assert cksum(sample) == cksum_reference(sample)


# ------------------------------------------------------------------------------------------- contenuto
class Node:
    __slots__ = ("kind", "mode", "mtime", "size", "link", "src", "cksum")

    def __init__(self, kind, mode, mtime, size=0, link="", src=None):
        self.kind, self.mode, self.mtime, self.size, self.link, self.src = kind, mode, int(mtime), size, link, src
        self.cksum = 0


def open_src(src):
    if isinstance(src, (bytes, bytearray)):
        return io.BytesIO(src)
    if isinstance(src, str):
        return open(src, "rb")
    z, info = src
    return z.open(info)


def add_dirs(nodes, path, mtime):
    parts = path.split("/")[:-1]
    for i in range(1, len(parts) + 1):
        d = "/".join(parts[:i])
        if d not in nodes:
            nodes[d] = Node("dir", 0o755, mtime)


def put(nodes, path, mode, mtime, size, src):
    add_dirs(nodes, path, mtime)
    nodes[path] = Node("file", mode, mtime, size, src=src)


def from_disk(nodes, src, dst, exclude_top=frozenset()):
    for base, dirs, files in os.walk(src):
        rel = os.path.relpath(base, src)
        if rel == ".":
            dirs[:] = [d for d in dirs if d.lower() not in exclude_top]
            files = [f for f in files if f.lower() not in exclude_top]
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                continue
            p = os.path.join(base, f)
            st = os.stat(p)
            put(nodes, f"{dst}/{os.path.relpath(p, src).replace(os.sep, '/')}", 0o644, st.st_mtime, st.st_size, p)


def from_python_tarball(nodes, tarball, dst):
    count = 0
    with tarfile.open(tarball, "r:gz") as tar:
        for m in tar:
            name = m.name
            if not name.startswith("python/") or PBS_SKIP.match(name + ("/" if m.isdir() else "")) \
                    or "/__pycache__/" in name or name.endswith((".pyc", ".pyo")):
                continue
            path = f"{dst}/{name[len('python/'):]}".rstrip("/")
            if m.isdir():
                add_dirs(nodes, path + "/x", m.mtime)
                nodes[path].mode = 0o755
            elif m.issym():
                add_dirs(nodes, path, m.mtime)
                nodes[path] = Node("link", 0o755, m.mtime, len(m.linkname.encode("utf-8")), m.linkname)
            elif m.isfile():
                data = tar.extractfile(m).read()
                put(nodes, path, (m.mode & 0o777) | 0o644, m.mtime, len(data), data)
                count += 1
    return count


def from_wheel(nodes, wheel, site, runtime):
    z = zipfile.ZipFile(wheel)
    count = 0
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
            else:
                continue      # scripts/headers: non servono al programma
        else:
            target = f"{site}/{name}"
        if "/__pycache__/" in target or target.endswith((".pyc", ".pyo")):
            continue
        dt = info.date_time
        mt = time.mktime((dt[0], dt[1], dt[2], dt[3], dt[4], dt[5], 0, 0, -1)) if dt[0] >= 1980 else time.time()
        mode = ((info.external_attr >> 16) & 0o777) | 0o644
        put(nodes, target, mode, mt, info.file_size, (z, info))
        count += 1
    return count


def lock_wheels(edition, arch):
    with open(os.path.join(DEPS, f"requisiti-{edition}-{arch}.txt"), encoding="utf-8") as f:
        return [line.split("#", 1)[1].strip() for line in f if "#" in line and not line.startswith("#")]


def min_macos(wheels):
    """Versione minima di macOS: la piu' alta richiesta dalle wheel (etichette macosx_<major>_<minor>_<arch>)."""
    best = BASE_MIN_OS
    for w in wheels:
        for major, minor in re.findall(r"macosx_(\d+)_(\d+)_", w):
            best = max(best, (int(major), int(minor)))
    return f"{best[0]}.{best[1]}"


def info_plist(src_plist, version, min_os, title):
    text = open(src_plist, encoding="utf-8").read().replace("\r\n", "\n")
    text = re.sub(r"\n\s*<key>LSMinimumSystemVersion</key><string>[^<]*</string>", "", text)
    text = re.sub(r"(<key>CFBundle(?:Display)?Name</key><string>)[^<]*", lambda m: m.group(1) + title, text)
    text = re.sub(r"(<key>CFBundle(?:ShortVersionString|Version)</key><string>)[^<]*", lambda m: m.group(1) + version,
                  text)
    extra = ("    <key>LSMinimumSystemVersion</key><string>%s</string>\n"
             "    <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>\n"
             "    <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>\n" % min_os)
    assert "</dict>\n</plist>" in text, "Info.plist inatteso"
    return text.replace("</dict>\n</plist>", extra + "</dict>\n</plist>").encode("utf-8")


def bundle_id(plist_bytes):
    return re.search(rb"<key>CFBundleIdentifier</key>\s*<string>([^<]+)</string>", plist_bytes).group(1).decode()


# ------------------------------------------------------------------------------------------- Bom (come mkbom)
class BomStorage:
    def __init__(self):
        self.blocks = []
        self.vars = []

    def add_block(self, data):
        self.blocks.append(bytearray(data))
        return len(self.blocks)            # l'indice 0 e' il blocco nullo

    def add_var(self, name, data):
        self.vars.append((name, self.add_block(data)))

    def write(self):
        vars_bytes = struct.pack(">I", len(self.vars)) + b"".join(
            struct.pack(">IB", idx, len(name)) + name.encode() for name, idx in self.vars)
        base = 512 + len(vars_bytes)
        pointers, offset = [], 0
        for b in self.blocks:
            pointers.append((base + offset, len(b)))
            offset += len(b)
        table = struct.pack(">I", len(self.blocks) + 1) + struct.pack(">II", 0, 0) + b"".join(
            struct.pack(">II", a, n) for a, n in pointers)
        free_list = struct.pack(">I", 0) + struct.pack(">II", 0, 0) * 2
        header = b"BOMStore" + struct.pack(">IIIIII", 1, len(self.blocks), base + offset, len(table) + len(free_list),
                                           512, len(vars_bytes))
        return header.ljust(512, b"\0") + vars_bytes + b"".join(bytes(b) for b in self.blocks) + table + free_list


def paths_block(is_leaf, indices, forward=0, backward=0):
    return struct.pack(">HHII", is_leaf, len(indices), forward, backward) + b"".join(
        struct.pack(">II", a, b) for a, b in indices)


def make_bom(nodes):
    """Distinta dei file, porting fedele di mkbom.cpp (bomutils): visita in ampiezza dell'albero dei percorsi,
    pagine foglia da 256 voci collegate in avanti/indietro, radice con l'indice delle pagine se sono piu' d'una."""
    tree = {}
    for path in nodes:
        cur = tree.setdefault(".", {})
        if path == ".":
            continue
        for part in path[2:].split("/"):
            cur = cur.setdefault(part, {})
    num = len(nodes)
    for n in nodes.values():
        assert n.size < 2 ** 32, "file oltre 4 GB: servirebbe la tabella Size64"
    bom = BomStorage()
    bom.add_var("BomInfo", struct.pack(">III", 1, num + 1, 1 if num else 0) + (b"\0" * 16 if num else b""))
    num_pages = math.ceil(num / 256)
    root_indices = [(0, 0)] * num_pages
    queue = deque([(0, "", {".": tree["."]})])
    j = k = current = 0
    last_file = last_page = 0
    page, page_backward = None, 0
    while queue:
        parent_id, parent_path, children = queue.popleft()
        for name in sorted(children, key=lambda s: s.encode("utf-8")):
            path = name if parent_path == "" else f"{parent_path}/{name}"
            node = nodes[path]
            if k == 0:
                new_id = 0
                if page is not None:
                    new_id = bom.add_block(paths_block(1, page, 0, page_backward))
                    root_indices[current] = (new_id, last_file)
                    if last_page:
                        struct.pack_into(">I", bom.blocks[last_page - 1], 4, new_id)     # forward della precedente
                    current += 1
                page, page_backward, last_page = [], new_id, new_id
            ftype = {"dir": S_IFDIR, "file": S_IFREG, "link": S_IFLNK}[node.kind]
            link = (node.link.encode("utf-8") + b"\0") if node.kind == "link" else b""
            # campo «architettura»: 0x0F come pkgbuild di Apple per cartelle, file e collegamenti (bomutils usa 3);
            # tutti i campi sono valorizzati e il cksum e' identico a quello calcolato da Apple
            info2 = struct.pack(">BBHHIIIIBII", {"dir": 2, "file": 1, "link": 3}[node.kind], 1, 0x0F, ftype | node.mode,
                                UID, GID, node.mtime & 0xFFFFFFFF, 0 if node.kind == "dir" else node.size, 1,
                                node.cksum, len(link)) + link
            info1 = bom.add_block(struct.pack(">II", j + 1, bom.add_block(info2)))
            last_file = bom.add_block(struct.pack(">I", parent_id) + name.encode("utf-8") + b"\0")
            page.append((info1, last_file))
            if children[name]:
                queue.append((j + 1, path, children[name]))
            j += 1
            k = (k + 1) % 256
    if num_pages > 1:
        new_id = bom.add_block(paths_block(1, page, 0, page_backward))
        struct.pack_into(">I", bom.blocks[last_page - 1], 4, new_id)
        root_indices[current] = (new_id, last_file)
        child = bom.add_block(paths_block(0, root_indices))
    else:
        child = bom.add_block(paths_block(1, page or []))
    bom.add_var("Paths", struct.pack(">4sIIIIB", b"tree", 1, child, 4096, num, 0))
    empty = paths_block(1, [])
    bom.add_var("HLIndex", struct.pack(">4sIIIIB", b"tree", 1, bom.add_block(empty), 4096, 0, 0))
    vtree = bom.add_block(struct.pack(">4sIIIIB", b"tree", 1, bom.add_block(empty), 128, 0, 0))
    bom.add_var("VIndex", struct.pack(">IIIB", 1, vtree, 0, 0))
    bom.add_var("Size64", struct.pack(">4sIIIIB", b"tree", 1, bom.add_block(empty), 4096, 0, 0))
    return bom.write()


def read_bom(data):
    """Lettore della distinta (verifica): {percorso: (tipo, modo, dimensione, cksum)} seguendo l'albero «Paths»."""
    magic, _v, nblocks, index_off, index_len, vars_off, _vl = struct.unpack_from(">8sIIIIII", data, 0)
    assert magic == b"BOMStore" and index_off + index_len == len(data)
    count = struct.unpack_from(">I", data, index_off)[0]
    assert count == nblocks + 1
    ptrs = [struct.unpack_from(">II", data, index_off + 4 + 8 * i) for i in range(count)]
    block = lambda i: data[ptrs[i][0]:ptrs[i][0] + ptrs[i][1]]
    nvars = struct.unpack_from(">I", data, vars_off)[0]
    pos, variables = vars_off + 4, {}
    for _ in range(nvars):
        idx, ln = struct.unpack_from(">IB", data, pos)
        variables[data[pos + 5:pos + 5 + ln].decode()] = idx
        pos += 5 + ln
    assert set(variables) == {"BomInfo", "Paths", "HLIndex", "VIndex", "Size64"}
    tree = block(variables["Paths"])
    assert tree[:4] == b"tree"
    child, _bs, path_count = struct.unpack_from(">III", tree, 8)
    entries = []

    def leaf_items(b):
        is_leaf, n, forward, _back = struct.unpack_from(">HHII", b, 0)
        return is_leaf, forward, [struct.unpack_from(">II", b, 12 + 8 * i) for i in range(n)]

    is_leaf, forward, items = leaf_items(block(child))
    if not is_leaf:
        is_leaf, forward, items = leaf_items(block(items[0][0]))
    while True:
        for i0, i1 in items:
            pid, info2 = struct.unpack_from(">II", block(i0), 0)
            f = block(i1)
            parent = struct.unpack_from(">I", f, 0)[0]
            name = f[4:].split(b"\0")[0].decode("utf-8")
            kind, _u0, _arch, mode, _uid, _gid, _mt, size, _u1, ck, _ll = struct.unpack_from(">BBHHIIIIBII",
                                                                                          block(info2), 0)
            entries.append((pid, parent, name, (kind, mode, size, ck)))
        if not forward:
            break
        is_leaf, forward, items = leaf_items(block(forward))
    assert len(entries) == path_count
    names, out = {}, {}
    for pid, parent, name, meta in entries:
        names[pid] = name if parent == 0 else f"{names[parent]}/{name}"
        out[names[pid]] = meta
    return out


# ------------------------------------------------------------------------------------------- cpio odc
def cpio_header(name, mode, mtime, size, ino, nlink):
    raw = name.encode("utf-8") + b"\0"
    assert size < 8 ** 11
    return (b"070707" + b"%06o" % 0 + b"%06o" % (ino & 0o777777) + b"%06o" % mode + b"%06o" % UID + b"%06o" % GID +
            b"%06o" % nlink + b"%06o" % 0 + b"%011o" % (mtime & 0o77777777777) + b"%06o" % len(raw) +
            b"%011o" % size + raw)


def write_payload(path, nodes, order):
    """Payload: cpio «odc» compresso gzip, file letti a blocchi; calcola i cksum per la distinta."""
    done, total, t0, last = 0, sum(nodes[p].size for p in order if nodes[p].kind == "file"), time.time(), 0
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6, mtime=0) as gz:
        for ino, p in enumerate(order, start=1):
            node = nodes[p]
            if node.kind == "dir":
                gz.write(cpio_header(p, S_IFDIR | node.mode, node.mtime, 0, ino, 2))
            elif node.kind == "link":
                target = node.link.encode("utf-8")
                node.cksum = cksum(target)
                gz.write(cpio_header(p, S_IFLNK | 0o755, node.mtime, len(target), ino, 1) + target)
            else:
                gz.write(cpio_header(p, S_IFREG | node.mode, node.mtime, node.size, ino, 1))
                ck, written = Cksum(), 0
                with open_src(node.src) as f:
                    for chunk in iter(lambda: f.read(CHUNK), b""):
                        ck.update(chunk)
                        gz.write(chunk)
                        written += len(chunk)
                assert written == node.size, f"dimensione cambiata durante la lettura: {p}"
                node.cksum = ck.digest()
                done += written
                if done - last > 512 * 2 ** 20:
                    last = done
                    print(f"    Payload: {done / 2**30:.2f} / {total / 2**30:.2f} GB ({time.time() - t0:.0f} s)",
                          flush=True)
        gz.write(cpio_header("TRAILER!!!", 0, 0, 0, 0, 1))


def read_payload(path):
    """Lettore del Payload (verifica): {percorso: (modo, dimensione, cksum)} nell'ordine dell'archivio."""
    out = {}
    with gzip.open(path, "rb") as f:
        while True:
            h = f.read(76)
            assert h[:6] == b"070707", "intestazione cpio non valida"
            mode, namesize, size = int(h[18:24], 8), int(h[59:65], 8), int(h[65:76], 8)
            name = f.read(namesize)[:-1].decode("utf-8")
            if name == "TRAILER!!!":
                return out
            ck, left = Cksum(), size
            while left:
                chunk = f.read(min(left, CHUNK))
                assert chunk, f"Payload troncato: {name}"
                ck.update(chunk)
                left -= len(chunk)
            out[name] = (mode, size, ck.digest() if mode & 0o170000 in (S_IFREG, S_IFLNK) else 0)


def scripts_archive(path, postinstall):
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        now = int(time.time())
        gz.write(cpio_header(".", S_IFDIR | 0o755, now, 0, 1, 2))
        gz.write(cpio_header("./postinstall", S_IFREG | 0o755, now, len(postinstall), 2, 1) + postinstall)
        gz.write(cpio_header("TRAILER!!!", 0, 0, 0, 0, 1))


# ------------------------------------------------------------------------------------------- xar
def xar_write(out, entries):
    """entries: lista di (percorso nell'archivio, contenuto: bytes, percorso su disco oppure None = cartella)."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    tree = {}
    for path, src in entries:
        cur, parts = tree, path.split("/")
        for d in parts[:-1]:
            cur = cur[d]
        cur[parts[-1]] = {} if src is None else src
    heap, offset, ids = [], 20, iter(range(1, 10 ** 6))    # l'impronta SHA-1 dell'indice occupa i primi 20 byte

    def digest(src):
        if isinstance(src, (bytes, bytearray)):
            return len(src), hashlib.sha1(src).hexdigest()
        h = hashlib.sha1()
        with open(src, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK), b""):
                h.update(chunk)
        return os.path.getsize(src), h.hexdigest()

    def file_xml(name, node, pad):
        nonlocal offset
        meta = (f"{pad} <ctime>{now}Z</ctime>\n{pad} <mtime>{now}Z</mtime>\n{pad} <atime>{now}Z</atime>\n"
                f"{pad} <group>wheel</group>\n{pad} <gid>0</gid>\n{pad} <user>root</user>\n{pad} <uid>0</uid>\n")
        fid = next(ids)
        if isinstance(node, dict):
            inner = "".join(file_xml(n, c, pad + " ") for n, c in node.items())
            return (f'{pad}<file id="{fid}">\n{meta}{pad} <mode>0755</mode>\n{pad} <type>directory</type>\n'
                    f"{pad} <name>{escape(name)}</name>\n{inner}{pad}</file>\n")
        size, sha = digest(node)
        heap.append(node)
        xml = (f'{pad}<file id="{fid}">\n{pad} <data>\n{pad}  <length>{size}</length>\n'
               f'{pad}  <encoding style="application/octet-stream"/>\n{pad}  <offset>{offset}</offset>\n'
               f"{pad}  <size>{size}</size>\n"
               f'{pad}  <extracted-checksum style="sha1">{sha}</extracted-checksum>\n'
               f'{pad}  <archived-checksum style="sha1">{sha}</archived-checksum>\n{pad} </data>\n'
               f"{meta}{pad} <mode>0644</mode>\n{pad} <type>file</type>\n{pad} <name>{escape(name)}</name>\n{pad}</file>\n")
        offset += size
        return xml

    body = "".join(file_xml(n, c, "  ") for n, c in tree.items())
    toc = (f'<?xml version="1.0" encoding="UTF-8"?>\n<xar>\n <toc>\n  <checksum style="sha1">\n   <offset>0</offset>\n'
           f"   <size>20</size>\n  </checksum>\n  <creation-time>{now}</creation-time>\n{body} </toc>\n</xar>\n").encode()
    ztoc = zlib.compress(toc, 9)
    with open(out, "wb") as f:
        f.write(struct.pack(">IHHQQI", 0x78617221, 28, 1, len(ztoc), len(toc), 1))
        f.write(ztoc)
        f.write(hashlib.sha1(ztoc).digest())
        for src in heap:
            if isinstance(src, (bytes, bytearray)):
                f.write(src)
            else:
                with open(src, "rb") as s:
                    for chunk in iter(lambda: s.read(CHUNK), b""):
                        f.write(chunk)


def xar_read(path):
    """Lettore dell'archivio (verifica): indice, impronta dell'indice e impronta di ogni file; restituisce
    {percorso: contenuto} per i file fino a 16 MB e {percorso: (posizione, lunghezza)} per gli altri."""
    with open(path, "rb") as f:
        magic, hsize, ver, zlen, ulen, alg = struct.unpack(">IHHQQI", f.read(28))
        assert magic == 0x78617221 and hsize == 28 and ver == 1 and alg == 1, "intestazione xar non valida"
        ztoc = f.read(zlen)
        toc = zlib.decompress(ztoc)
        assert len(toc) == ulen
        heap = 28 + zlen
        root = ET.fromstring(toc).find("toc")
        ck = root.find("checksum")
        f.seek(heap + int(ck.find("offset").text))
        assert f.read(int(ck.find("size").text)) == hashlib.sha1(ztoc).digest(), "impronta dell'indice errata"
        files = {}

        def walk(el, prefix):
            for fe in el.findall("file"):
                name = prefix + fe.find("name").text
                d = fe.find("data")
                if d is not None:
                    off, ln = int(d.find("offset").text), int(d.find("length").text)
                    f.seek(heap + off)
                    h, left, small, buf = hashlib.sha1(), ln, ln <= 2 ** 24, bytearray()
                    while left:
                        chunk = f.read(min(left, CHUNK))
                        assert chunk, f"archivio troncato: {name}"
                        h.update(chunk)
                        if small:
                            buf += chunk
                        left -= len(chunk)
                    assert h.hexdigest() == d.find("archived-checksum").text, f"impronta errata: {name}"
                    files[name] = bytes(buf) if small else (heap + off, ln)
                walk(fe, name + "/")
        walk(root, "")
        end = max(int(fe.find("data/offset").text) + int(fe.find("data/length").text)
                  for fe in root.iter("file") if fe.find("data") is not None)
        assert f.seek(0, 2) == heap + end, "dati in eccesso o mancanti in coda all'archivio"
    return files


# ------------------------------------------------------------------------------------------- pacchetto
def build(edition):
    ed = EDITIONS[edition]
    src = os.path.join(RELEASE, "sorgenti", "macos", edition)
    version = open(os.path.join(src, "VERSION"), encoding="utf-8-sig").read().strip()
    out = os.path.join(RELEASE, "releases", "macos", ed["file"].format(v=version))
    t0 = time.time()
    wheels = {arch: lock_wheels(edition, arch) for arch in ed["archs"]}
    min_os = min_macos([w for ws in wheels.values() for w in ws])
    print(f"== {ed['title']} {version} per macOS {min_os}+ ({', '.join(ed['archs'])}) -> {out}", flush=True)
    now = time.time()
    nodes = {".": Node("dir", 0o775, now)}     # «.» = la cartella Applicazioni: stessi permessi (rwxrwxr-x root:admin)
    app = f"./{ed['bundle']}"
    res = f"{app}/Contents/Resources/app"
    plist = info_plist(os.path.join(src, "Germano.app", "Contents", "Info.plist"), version, min_os, ed["title"])
    ident = bundle_id(plist)
    put(nodes, f"{app}/Contents/Info.plist", 0o644, now, len(plist), plist)
    put(nodes, f"{app}/Contents/PkgInfo", 0o644, now, 8, b"APPL????")
    launcher = open(os.path.join(src, "Germano.app", "Contents", "MacOS", "Germano"), "rb").read().replace(b"\r\n", b"\n")
    assert launcher.startswith(b"#!/bin/bash\n")
    put(nodes, f"{app}/Contents/MacOS/Germano", 0o755, now, len(launcher), launcher)
    icns = os.path.join(src, "Germano.app", "Contents", "Resources", "germano.icns")
    put(nodes, f"{app}/Contents/Resources/germano.icns", 0o644, os.path.getmtime(icns), os.path.getsize(icns), icns)
    from_disk(nodes, src, res, APP_EXCLUDE_TOP)
    meta = ('{\n  "edition": "%s",\n  "version": "%s",\n  "installer": "pkg",\n  "data_dir": null,\n'
            '  "tech_dir": null\n}\n' % ("suite" if edition == "germano" else "client", version)).encode()
    put(nodes, f"{res}/germano_install.json", 0o644, now, len(meta), meta)
    stats = []
    for arch in ed["archs"]:
        rt = f"{res}/{RUNTIME_DIR[arch]}"
        tbs = [f for f in os.listdir(os.path.join(DEPS, "python")) if f.endswith(f"{PBS[arch]}-install_only_stripped.tar.gz")]
        assert len(tbs) == 1, tbs
        n_py = from_python_tarball(nodes, os.path.join(DEPS, "python", tbs[0]), rt)
        site = f"{rt}/lib/python3.11/site-packages"
        n_lib = sum(from_wheel(nodes, os.path.join(DEPS, f"wheels-{arch}", w), site, rt) for w in wheels[arch])
        stats.append(f"{arch}: {n_py:,} file del Python, {n_lib:,} dalle {len(wheels[arch])} librerie")
        assert nodes[f"{rt}/bin/python3"].kind == "link"
    if edition == "germano":
        from_disk(nodes, MODELS, f"{res}/models")
    for need in ("germano_desktop.py", "germano_window.py", "VERSION"):
        assert f"{res}/{need}" in nodes, need
    order = sorted(nodes, key=lambda p: p.split("/"))
    files = [p for p in order if nodes[p].kind == "file"]
    total = sum(nodes[p].size for p in files)
    print(f"  {len(order):,} voci ({len(files):,} file; {'; '.join(stats)}), {total / 2**30:.2f} GB installati",
          flush=True)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    work = out + ".lavoro"
    os.makedirs(work, exist_ok=True)
    payload = os.path.join(work, "Payload")
    write_payload(payload, nodes, order)
    bom = make_bom(nodes)
    rel_app = ed["bundle"]
    postinstall = f"""#!/bin/bash
# {ed['title']} {version}: compila la cache dei moduli Python (avvio piu' rapido). Mai bloccante.
# Con "Installa solo per me" lo script gira come utente corrente, con "per tutti gli utenti" come root.
APP=""
for BASE in "$2" "$3/Applications" "$HOME/Applications" /Applications; do
  if [ -f "$BASE/{rel_app}/Contents/Resources/app/germano_desktop.py" ]; then APP="$BASE/{rel_app}"; break; fi
done
[ -n "$APP" ] || exit 0
for PY in "$APP/Contents/Resources/app/runtime/bin/python3" "$APP/Contents/Resources/app/runtime-x86_64/bin/python3"; do
  if [ -x "$PY" ] && "$PY" -c "import sys" >/dev/null 2>&1; then
    "$PY" -m compileall -q -j 0 "$APP/Contents/Resources/app" >/dev/null 2>&1 || true
    break
  fi
done
touch "$APP" 2>/dev/null || true
exit 0
""".encode()
    scripts = os.path.join(work, "Scripts")
    scripts_archive(scripts, postinstall)
    install_kb = (total + 1023) // 1024 + len(order) // 4
    package_info = f"""<?xml version="1.0" encoding="utf-8"?>
<pkg-info overwrite-permissions="true" relocatable="false" identifier="{ident}" postinstall-action="none" version="{version}" format-version="2" install-location="/Applications" auth="root">
    <payload numberOfFiles="{len(order)}" installKBytes="{install_kb}"/>
    <bundle path="{app}" id="{ident}" CFBundleShortVersionString="{version}" CFBundleVersion="{version}"/>
    <bundle-version>
        <bundle id="{ident}"/>
    </bundle-version>
    <upgrade-bundle>
        <bundle id="{ident}"/>
    </upgrade-bundle>
    <update-bundle/>
    <atomic-update-bundle/>
    <strict-identifier>
        <bundle id="{ident}"/>
    </strict-identifier>
    <relocate/>
    <scripts>
        <postinstall file="./postinstall" timeout="600"/>
    </scripts>
</pkg-info>
""".encode()
    distribution = f"""<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>{ed['title']} {version}</title>
    <options customize="never" require-scripts="false" hostArchitectures="{','.join(ed['archs'])}"/>
    <domains enable_anywhere="false" enable_currentUserHome="true" enable_localSystem="true"/>
    <volume-check>
        <allowed-os-versions>
            <os-version min="{min_os}"/>
        </allowed-os-versions>
    </volume-check>
    <choices-outline>
        <line choice="default">
            <line choice="{ident}"/>
        </line>
    </choices-outline>
    <choice id="default"/>
    <choice id="{ident}" visible="false">
        <pkg-ref id="{ident}"/>
    </choice>
    <pkg-ref id="{ident}" version="{version}" onConclusion="none" installKBytes="{install_kb}">#germano.pkg</pkg-ref>
    <pkg-ref id="{ident}">
        <bundle-version>
            <bundle CFBundleShortVersionString="{version}" CFBundleVersion="{version}" id="{ident}" path="{rel_app}"/>
        </bundle-version>
    </pkg-ref>
    <product id="{ident}" version="{version}"/>
</installer-gui-script>
""".encode()
    part = out + ".part"
    xar_write(part, [("Distribution", distribution), ("germano.pkg", None), ("germano.pkg/PackageInfo", package_info),
                     ("germano.pkg/Bom", bom), ("germano.pkg/Payload", payload), ("germano.pkg/Scripts", scripts)])

    # ---- verifica del file prodotto, riletto da capo con lettori indipendenti dalla scrittura
    x = xar_read(part)
    assert set(x) == {"Distribution", "germano.pkg/PackageInfo", "germano.pkg/Bom", "germano.pkg/Payload",
                      "germano.pkg/Scripts"}, sorted(x)
    dist = ET.fromstring(x["Distribution"])
    assert dist.find("domains").get("enable_currentUserHome") == "true"
    assert dist.find("options").get("hostArchitectures") == ",".join(ed["archs"])
    pi = ET.fromstring(x["germano.pkg/PackageInfo"])
    assert pi.get("identifier") == ident and pi.get("install-location") == "/Applications"
    assert int(pi.find("payload").get("numberOfFiles")) == len(order)
    listed = read_bom(x["germano.pkg/Bom"])
    assert x["germano.pkg/Payload"][1] == os.path.getsize(payload)    # stesso contenuto: impronta SHA-1 verificata
    cpio = read_payload(payload)
    assert list(cpio) == order, "Payload diverso dall'elenco atteso"
    assert set(listed) == set(order), f"distinta con {len(listed)} voci invece di {len(order)}"
    bad = [p for p in order if listed[p][1] != cpio[p][0] or
           (nodes[p].kind != "dir" and (listed[p][2], listed[p][3]) != cpio[p][1:])]
    assert not bad, f"distinta e Payload non coincidono: {bad[:5]}"
    assert cpio[f"{app}/Contents/MacOS/Germano"][0] & 0o777 == 0o755
    sc = gzip.decompress(x["germano.pkg/Scripts"])
    assert b"./postinstall" in sc and b"exit 0" in sc
    for p in os.listdir(work):
        os.remove(os.path.join(work, p))
    os.rmdir(work)
    os.replace(part, out)
    print(f"  verifica: indice xar e impronte SHA-1, Distribution e PackageInfo, distinta Bom ({len(listed):,} voci) "
          f"e Payload cpio ({len(cpio):,} voci): dimensioni, permessi e cksum di ogni file coincidenti")
    print(f"  OK {os.path.basename(out)}: {os.path.getsize(out) / 2**30:.2f} GB in {time.time() - t0:.0f} s", flush=True)
    return out


if __name__ == "__main__":
    self_test()
    which = sys.argv[1] if len(sys.argv) > 1 else "tutti"
    for key in (["germano-client", "germano"] if which == "tutti" else [which]):
        build(key)
