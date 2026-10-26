"""Crea Germano.exe, l'UNICO programma di Germano AI su Windows (suite completa o client leggero, ruolo automatico),
SENZA compilatore ne' Internet.

Base: il launcher GUI 'w64.exe' di distlib (nessuna console) + un piccolo bootstrap (solo libreria standard) aggiunto
in coda come archivio zip: avvia il 'pythonw.exe' incluso su germano_desktop.py in modalita' 'auto'. Prima di
aggiungere il bootstrap si sostituiscono le risorse del launcher: icona ufficiale di Germano (favicon.ico, tutte le
dimensioni), informazioni di versione (Proprieta' > Dettagli) e lo stesso manifest originale (asInvoker).

Di norma lo crea costruisci_installer_windows.py direttamente nell'installer (i sorgenti restano senza binari).
Uso manuale: python build_exe.py <cartella_pacchetto> [template_w64.exe]
"""
import ctypes
import io
import os
import shutil
import struct
import sys
import zipfile
from ctypes import wintypes

sys.dont_write_bytecode = True

BOOT_APP = r'''# Bootstrap di Germano.exe (eseguito dal launcher GUI w64.exe: nessuna console).
import sys
sys.dont_write_bytecode = True
import os, subprocess
APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
pyw = os.path.join(APP_DIR, "runtime", "pythonw.exe")
py = os.path.join(APP_DIR, "runtime", "python.exe")
interp = pyw if os.path.isfile(pyw) else py
desktop = os.path.join(APP_DIR, "germano_desktop.py")
try:
    if not os.path.isfile(interp) or not os.path.isfile(desktop):
        raise FileNotFoundError("programma incompleto: manca runtime\\pythonw.exe o germano_desktop.py")
    CREATE_NO_WINDOW = 0x08000000
    DETACHED = 0x00000008
    subprocess.Popen([interp, "-B", desktop, "auto"] + sys.argv[1:], cwd=APP_DIR,
                     creationflags=CREATE_NO_WINDOW | DETACHED, close_fds=True)
except Exception as e:  # nessuna console: l'eventuale errore compare in una finestra di dialogo nativa
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "Impossibile avviare Germano AI:\n\n%s" % e, "Germano AI", 0x10)
    except Exception:
        pass
'''

RT_ICON, RT_GROUP_ICON, RT_VERSION, RT_MANIFEST = 3, 14, 16, 24
LANG_EN_US = 0x0409

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.BeginUpdateResourceW.restype, k32.BeginUpdateResourceW.argtypes = wintypes.HANDLE, [wintypes.LPCWSTR, wintypes.BOOL]
k32.UpdateResourceW.restype = wintypes.BOOL
k32.UpdateResourceW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD, ctypes.c_char_p,
                                wintypes.DWORD]
k32.EndUpdateResourceW.restype, k32.EndUpdateResourceW.argtypes = wintypes.BOOL, [wintypes.HANDLE, wintypes.BOOL]
k32.LoadLibraryExW.restype, k32.LoadLibraryExW.argtypes = wintypes.HMODULE, [wintypes.LPCWSTR, wintypes.HANDLE,
                                                                              wintypes.DWORD]
k32.FindResourceW.restype, k32.FindResourceW.argtypes = ctypes.c_void_p, [wintypes.HMODULE, ctypes.c_void_p,
                                                                          ctypes.c_void_p]
k32.SizeofResource.restype, k32.SizeofResource.argtypes = wintypes.DWORD, [wintypes.HMODULE, ctypes.c_void_p]
k32.LoadResource.restype, k32.LoadResource.argtypes = ctypes.c_void_p, [wintypes.HMODULE, ctypes.c_void_p]
k32.LockResource.restype, k32.LockResource.argtypes = ctypes.c_void_p, [ctypes.c_void_p]
k32.FreeLibrary.argtypes = [wintypes.HMODULE]


def read_resource(path, rtype, name):
    h = k32.LoadLibraryExW(path, None, 0x2 | 0x20)   # LOAD_LIBRARY_AS_DATAFILE | AS_IMAGE_RESOURCE
    if not h:
        raise OSError(ctypes.get_last_error(), "LoadLibraryExW", path)
    try:
        res = k32.FindResourceW(h, ctypes.c_void_p(name), ctypes.c_void_p(rtype))
        if not res:
            return None
        size = k32.SizeofResource(h, res)
        return ctypes.string_at(k32.LockResource(k32.LoadResource(h, res)), size)
    finally:
        k32.FreeLibrary(h)


def read_ico(path):
    """Immagini di un file .ico: (larghezza, altezza, colori, piani, bit, dati) per ognuna."""
    data = open(path, "rb").read()
    _reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    if kind != 1 or not count:
        raise ValueError(f"{path} non e' un file .ico valido")
    images = []
    for i in range(count):
        w, h, colors, _res, planes, bits, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        blob = data[offset:offset + size]
        if blob[:8] == b"\x89PNG\r\n\x1a\n":
            planes, bits = planes or 1, bits or 32
        else:   # BMP: la profondita' di colore e' nell'intestazione BITMAPINFOHEADER
            planes, bits = planes or 1, bits or struct.unpack_from("<H", blob, 14)[0]
        images.append((w, h, colors, planes, bits, blob))
    return images


def version_block(key, value=b"", children=(), kind=1, value_len=None):
    """Blocco VS_VERSIONINFO: intestazione, chiave UTF-16, valore e figli allineati a 32 bit."""
    raw_key = key.encode("utf-16-le") + b"\0\0"
    body = raw_key + b"\0" * ((4 - (6 + len(raw_key)) % 4) % 4) + value
    kids, cursor = b"", 6 + len(body)
    for child in children:
        pad = b"\0" * ((4 - cursor % 4) % 4)
        kids += pad + child
        cursor += len(pad) + len(child)
    length = len(value) if value_len is None else value_len
    return struct.pack("<HHH", 6 + len(body) + len(kids), length, kind) + body + kids


def version_resource(strings, numbers):
    ms, ls = (numbers[0] << 16) | numbers[1], (numbers[2] << 16) | numbers[3]
    fixed = struct.pack("<13I", 0xFEEF04BD, 0x00010000, ms, ls, ms, ls, 0x3F, 0, 0x00040004, 1, 0, 0, 0)
    table = [version_block(k, (v + "\0").encode("utf-16-le"), value_len=len(v) + 1) for k, v in strings]
    string_info = version_block("StringFileInfo", children=[version_block("040904B0", children=table)])
    var_info = version_block("VarFileInfo", children=[version_block("Translation", struct.pack("<HH", LANG_EN_US, 1200),
                                                                     kind=0)])
    return version_block("VS_VERSION_INFO", fixed, [string_info, var_info], kind=0)


def update_resources(exe, icon_path, strings, numbers, manifest):
    h = k32.BeginUpdateResourceW(exe, True)   # True: si eliminano le risorse del launcher (icona e versione generiche)
    if not h:
        raise OSError(ctypes.get_last_error(), "BeginUpdateResourceW", exe)

    def put(rtype, name, data):
        if not k32.UpdateResourceW(h, ctypes.c_void_p(rtype), ctypes.c_void_p(name), LANG_EN_US, data, len(data)):
            raise OSError(ctypes.get_last_error(), f"UpdateResourceW tipo {rtype} nome {name}")

    images = read_ico(icon_path)
    group = struct.pack("<HHH", 0, 1, len(images))
    for i, (w, hgt, colors, planes, bits, blob) in enumerate(images, start=1):
        put(RT_ICON, i, blob)
        group += struct.pack("<BBBBHHIH", w, hgt, colors, 0, planes, bits, len(blob), i)
    put(RT_GROUP_ICON, 1, group)
    put(RT_VERSION, 1, version_resource(strings, numbers))
    if manifest:
        put(RT_MANIFEST, 1, manifest)
    if not k32.EndUpdateResourceW(h, False):
        raise OSError(ctypes.get_last_error(), "EndUpdateResourceW", exe)
    return len(images)


def version_numbers(ver):
    return [int(x) for x in (ver.split("-")[0].split(".") + ["0", "0", "0"])[:4]]


def build_germano_exe(pkg, template, exe_path=None):
    """Germano.exe (nella cartella indicata, altrimenti in quella del pacchetto) con icona e versione del pacchetto."""
    suite = os.path.isfile(os.path.join(pkg, "server.py"))
    icon = os.path.join(pkg, "static", "favicon.ico") if suite else os.path.join(pkg, "favicon.ico")
    product = "Germano AI" if suite else "Germano AI Client"
    ver = open(os.path.join(pkg, "VERSION"), encoding="utf-8-sig").read().strip()
    strings = [("FileDescription", product), ("InternalName", "Germano"), ("OriginalFilename", "Germano.exe"),
               ("CompanyName", "germano.ai"), ("LegalCopyright", "germano.ai - GNU GPL v3"), ("ProductName", product),
               ("ProductVersion", ver), ("FileVersion", ver)]
    exe_path = exe_path or os.path.join(pkg, "Germano.exe")
    tmp = exe_path + ".tmp"
    shutil.copyfile(template, tmp)
    try:
        n_icons = update_resources(tmp, icon, strings, version_numbers(ver), read_resource(template, RT_MANIFEST, 1))
        launcher = open(tmp, "rb").read()
    finally:
        os.remove(tmp)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("__main__.py", BOOT_APP)
    with open(exe_path, "wb") as f:
        f.write(launcher)
        # shebang relativo: il launcher lo risolve rispetto alla PROPRIA cartella (verificato anche avviandolo da
        # un'altra cartella di lavoro, es. da Impostazioni > App), quindi il programma funziona ovunque sia installato.
        f.write(b"#!runtime\\pythonw.exe\r\n")
        f.write(buf.getvalue())
    print(f"creato {exe_path} - {os.path.getsize(exe_path)} byte, icona con {n_icons} immagini, versione {ver}")
    return exe_path


def default_template():
    """Launcher GUI w64.exe di distlib (incluso in pip) dal runtime Windows in dipendenze/windows/runtime-germano."""
    release = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
    return os.path.join(release, "dipendenze", "windows", "runtime-germano", "Lib", "site-packages", "pip", "_vendor",
                        "distlib", "w64.exe")


if __name__ == "__main__":
    package = os.path.abspath(sys.argv[1])
    w64 = sys.argv[2] if len(sys.argv) > 2 else default_template()
    if not os.path.isfile(w64):
        sys.exit(f"ERRORE: template w64.exe non trovato: {w64}")
    build_germano_exe(package, w64)
