"""Installer di Germano AI 0.60 per Windows, senza console.

Si distribuisce come UN SOLO FILE, germano-<versione>.exe (germano-client-<versione>.exe per il client): un piccolo
avviatore che estrae in una cartella temporanea l'interprete Python minimo e questo script, che a sua volta legge
i file del programma dall'archivio contenuto nello stesso .exe e li installa. Nel programma installato questo script
resta come disinstallatore (Germano.exe --uninstall, anche da Impostazioni > App).

Permessi: la suite consente SEMPRE l'accesso dalla rete locale (modalità Server LAN), con una regola del firewall di
Windows solo per il Python di questa installazione e solo per le reti private e di dominio. Per questo l'avviatore
chiede i permessi di amministratore SUBITO, appena si apre (richiesta UAC di Windows), e tutta l'installazione avviene
con quei permessi; la disinstallazione li chiede all'avvio per togliere la regola. Il client non ne ha bisogno.
Gli aggiornamenti automatici non li chiedono: la regola esiste già dall'installazione.
Germano invece gira sempre con i permessi normali dell'utente: alla fine dell'installazione lo apre l'avviatore
(la copia non elevata, che ha chiesto i permessi), senza pagine di istruzioni.
Se i permessi sono stati concessi con le credenziali di un altro account (utente standard), l'avviatore passa le
cartelle e il SID dell'utente che ha avviato l'installazione (--user-context), perché il programma sia suo.

Cartelle (per utente):
- programma:  %LOCALAPPDATA%\\Programs\\Germano AI   (la cartella standard di Windows per le app di un utente:
              Germano e i suoi aggiornamenti automatici la aggiornano senza permessi di amministratore)
- dati:       Documenti\\Germano AI\\  input, output, processed, failed, extracted (Vault), config.json, daemon.log
              (se Documenti è sincronizzata con OneDrive si usa C:\\Users\\<utente>\\Germano AI: i documenti
              originali e il Vault, che contiene i dati in chiaro, non devono finire nel cloud)
- tecnici:    %LOCALAPPDATA%\\Germano AI   (profilo della finestra dell'app, registri, aggiornamenti scaricati)
Crea i collegamenti (Desktop e menu Start) con l'icona ufficiale e registra il programma in Impostazioni > App, da
dove si disinstalla. Nessun servizio.

Interfaccia: le finestre native di Windows (TaskDialog), una sola finestra che passa da conferma ad avanzamento; a
installazione completata si chiude e Germano si apre. In italiano o in inglese secondo la lingua di Windows. Ogni
pagina mostrata è annotata nel registro %TEMP%\\germano_install.log. Fino alla comparsa della finestra l'avviatore
mostra subito una schermata di avvio (richiesta UAC, estrazione), che poi si chiude da sola; la richiesta UAC riguarda
un piccolo avviatore (pochi KB), così Windows non deve prima verificare l'intero file da 3 GB.
Nessuna nota sul firewall: la regola si crea in silenzio e l'esito resta nel registro.

Uso:  germano-0.60.exe [opzioni]           (installer in un solo file)
      Germano.exe --uninstall [opzioni]    (disinstallazione del programma installato)
Opzioni: --silent (nessuna finestra)  --update (aggiornamento avviato da Germano: niente conferma, Germano si chiude
         e si riapre da solo)  --result FILE (esito in JSON)  --data-dir CARTELLA  --no-desktop  --remove-data
         --lang it|en; passate dall'avviatore: --launch-file=FILE (dove scrivere il programma da aprire alla fine)
         --user-context=FILE (cartelle e SID dell'utente)  --elevated (copia con i permessi di amministratore)
Collaudo senza richiesta UAC: variabile GERMANO_SETUP_NO_ELEVATION=1 (la regola del firewall non viene creata).
Codici di uscita: 0 riuscito, 1 errore, 2 annullato, 3 Germano è aperto (solo con --silent).
"""
import ctypes
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import winreg
import zipfile
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))


def _read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


SETUP = _read_json(os.path.join(HERE, "setup.json"))   # presente solo nell'installer in un solo file
EDITION = SETUP.get("edition") or ("suite" if os.path.isfile(os.path.join(HERE, "server.py")) else "client")
SUITE = EDITION == "suite"
PRODUCT = "Germano AI" if SUITE else "Germano AI Client"
UNINSTALL_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
REG_KEY = UNINSTALL_ROOT + "\\" + ("GermanoAI" if SUITE else "GermanoAIClient")
SUITE_REG_KEY = UNINSTALL_ROOT + "\\GermanoAI"
APP_FOLDER = PRODUCT            # %LOCALAPPDATA%\Programs\<APP_FOLDER> (programma) e %LOCALAPPDATA%\<APP_FOLDER> (tecnici)
DATA_FOLDER = "Germano AI"      # Documenti\<DATA_FOLDER> (cartelle di lavoro della suite)
# Suite «Germano AI», client «Germano AI Client»: le due edizioni possono stare sullo stesso computer e nessuna
# deve sovrascrivere (o, disinstallandosi, eliminare) i collegamenti dell'altra.
SHORTCUT = PRODUCT + ".lnk"
START_FOLDER = PRODUCT
OLD_SHORTCUT, OLD_START_FOLDER = "Germano AI.lnk", "Germano AI"   # nomi usati dal client nelle build di prova
FIREWALL_RULE = "Germano AI (Server LAN)"
# Regole create da versioni precedenti (0.51/0.52): aperte a qualsiasi programma o su tutte le reti, si tolgono.
LEGACY_FIREWALL_RULES = ("Germano AI HTTP (8181)", "Germano AI Discovery (UDP 8182)", "Germano AI Python Runtime")
TEST_NO_ELEVATION = os.environ.get("GERMANO_SETUP_NO_ELEVATION") == "1"   # solo collaudi: nessuna richiesta UAC
WORK_FOLDERS = ("input", "output", "processed", "failed", "extracted")
# Non vengono copiati nel programma installato: impostazioni (vanno nella cartella dati) e dati di un uso portatile.
EXCLUDE_TOP = {"__pycache__", "state", "cache", "update", "config.json", "desktop.log", "server_stdout.log",
               "daemon.log", "germano_install.json", "setup.json", *WORK_FOLDERS}
META_PREFIX = "__germano_setup__/"   # voci tecniche dell'archivio (date originali dei file), non vengono installate
# Elementi di Germano nella cartella dati: sono gli unici che la disinstallazione può eliminare.
DATA_ITEMS = {*WORK_FOLDERS, "state", "config.json", "daemon.log", "leggimi.txt", "readme.txt", "desktop.ini"}
ICON_REL = os.path.join("static", "favicon.ico") if SUITE else "favicon.ico"
SFX_MAGIC = b"GERMANO.SFX.0001"
SFX_TRAILER = struct.Struct("<16sQQQQ")   # firma, avviatore+kit (inizio, lunghezza), archivio (inizio, lunghezza)
LOG_FILE = os.path.join(tempfile.gettempdir(), "germano_install.log")
SILENT = False


# ----------------------------------------------------------------------------------------- lingua e registro
def _arg_value(name):
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


LAUNCH_FILE = _arg_value("--launch-file")      # l'avviatore apre il programma scritto qui (con i permessi normali)
USER_CTX = _read_json(_arg_value("--user-context")) if _arg_value("--user-context") else {}


def _language():
    lang = (_arg_value("--lang") or "").lower()[:2]
    if lang in ("it", "en"):
        return lang
    try:
        return "it" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x10 else "en"
    except Exception:
        return "it"


LANG = _language()


def T(it, en):
    return it if LANG == "it" else en


def fmt_int(n):
    s = f"{n:,}"
    return s.replace(",", ".") if LANG == "it" else s


def fmt_size(n):
    for unit, div in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= div:
            s = f"{n / div:.1f}"
            return (s.replace(".", ",") if LANG == "it" else s) + " " + unit
    return f"{n} B"


def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{EDITION}] {msg}\n")
    except OSError:
        pass


def version():
    if SETUP.get("version"):
        return str(SETUP["version"])
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8-sig") as f:
            return f.read().strip() or "0.60"
    except OSError:
        return "0.60"


def icon_file():
    for path in (os.path.join(HERE, "favicon.ico"), os.path.join(HERE, "static", "favicon.ico")):
        if os.path.isfile(path):
            return path
    return None


# ------------------------------------------------------------------------------------------------ Win32
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ole32 = ctypes.OleDLL("ole32")           # funzioni HRESULT: un errore diventa un'eccezione OSError
ole32_void = ctypes.WinDLL("ole32")      # CoTaskMemFree e CoUninitialize non restituiscono un HRESULT


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]


def _proto(fn, restype, *argtypes):
    fn.restype, fn.argtypes = restype, list(argtypes)


_proto(user32.SendMessageW, ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_proto(user32.LoadImageW, wintypes.HANDLE, wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
       ctypes.c_int, wintypes.UINT)
_proto(user32.MessageBoxW, ctypes.c_int, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
_proto(user32.SetForegroundWindow, wintypes.BOOL, wintypes.HWND)
_proto(kernel32.SetFileAttributesW, wintypes.BOOL, wintypes.LPCWSTR, wintypes.DWORD)
_proto(kernel32.GetFileAttributesW, wintypes.DWORD, wintypes.LPCWSTR)
_proto(kernel32.WaitForSingleObject, wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
_proto(kernel32.GetExitCodeProcess, wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
_proto(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
_proto(kernel32.CreateMutexW, wintypes.HANDLE, ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
_proto(shell32.SHGetKnownFolderPath, ctypes.c_long, ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
       ctypes.POINTER(ctypes.c_wchar_p))
_proto(shell32.ShellExecuteExW, wintypes.BOOL, ctypes.POINTER(SHELLEXECUTEINFOW))
_proto(shell32.SHChangeNotify, None, ctypes.c_long, wintypes.UINT, wintypes.LPCWSTR, ctypes.c_void_p)
_proto(ole32_void.CoTaskMemFree, None, ctypes.c_void_p)
FILE_ATTRIBUTE_READONLY, FILE_ATTRIBUTE_HIDDEN, FILE_ATTRIBUTE_SYSTEM, FILE_ATTRIBUTE_NORMAL = 0x1, 0x2, 0x4, 0x80


def guid(text):
    g = GUID()
    ole32.CLSIDFromString(text, ctypes.byref(g))
    return g


FOLDERID = {
    "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "LocalAppData": "{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}",
    "UserProgramFiles": "{5CD7AEE2-2219-4A67-B85D-6C9CE15660CB}",
    "Programs": "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}",
    "Profile": "{5E6C858F-0E22-4760-9AFE-EA3317B67173}",
}
FOLDER_FALLBACK = {
    "Documents": ("USERPROFILE", "Documents"), "Desktop": ("USERPROFILE", "Desktop"),
    "LocalAppData": ("LOCALAPPDATA", ""), "UserProgramFiles": ("LOCALAPPDATA", "Programs"),
    "Programs": ("APPDATA", r"Microsoft\Windows\Start Menu\Programs"), "Profile": ("USERPROFILE", ""),
}
_folders = {}


def known_folder(name):
    """Cartelle reali dell'utente (anche se rinominate, spostate su un altro disco o in un'altra lingua). Con
    --user-context sono quelle dell'utente che ha avviato l'installazione, anche se i permessi di amministratore
    sono stati concessi con un altro account."""
    given = (USER_CTX.get("folders") or {}).get(name)
    if given:
        return os.path.normpath(given)
    if name not in _folders:
        p = ctypes.c_wchar_p()
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(guid(FOLDERID[name])), 0x8000, None, ctypes.byref(p))
        path = p.value if hr == 0 else None   # 0x8000 = KF_FLAG_CREATE
        ole32_void.CoTaskMemFree(ctypes.cast(p, ctypes.c_void_p))
        if not path:
            var, sub = FOLDER_FALLBACK[name]
            path = os.path.join(os.environ.get(var) or os.path.expanduser("~"), sub)
        _folders[name] = os.path.normpath(path)
    return _folders[name]


def user_env(name):
    """Variabile d'ambiente dell'utente che ha avviato l'installazione (passata dall'avviatore con --user-context)."""
    if USER_CTX:
        return (USER_CTX.get("env") or {}).get(name)
    return os.environ.get(name)


def in_cloud_sync(path):
    """True se il percorso è dentro una cartella sincronizzata con OneDrive."""
    p = os.path.normcase(os.path.abspath(path))
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        root = user_env(var)
        if root:
            r = os.path.normcase(os.path.abspath(root))
            if p == r or p.startswith(r + os.sep):
                return True
    return False


# --------------------------------------------------------------------------------- COM: collegamenti .lnk
def _method(ptr, index, restype, *argtypes):
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])
    return lambda *a: fn(ptr, *a)


def _create(clsid, iid):
    ptr = ctypes.c_void_p()
    ole32.CoCreateInstance(ctypes.byref(guid(clsid)), None, 1, ctypes.byref(guid(iid)), ctypes.byref(ptr))
    return ptr


def _release(ptr):
    if ptr:
        _method(ptr, 2, wintypes.ULONG)()


CLSID_SHELLLINK, IID_SHELLLINKW = "{00021401-0000-0000-C000-000000000046}", "{000214F9-0000-0000-C000-000000000046}"
IID_PERSISTFILE = "{0000010B-0000-0000-C000-000000000046}"


def _link_and_file():
    link = _create(CLSID_SHELLLINK, IID_SHELLLINKW)
    pf = ctypes.c_void_p()
    try:
        _method(link, 0, ctypes.HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
            ctypes.byref(guid(IID_PERSISTFILE)), ctypes.byref(pf))
    except OSError:
        _release(link)
        raise
    return link, pf


def create_shortcut(lnk, target, workdir="", icon="", description=""):
    """IShellLinkW: SetDescription 7, SetWorkingDirectory 9, SetIconLocation 17, SetPath 20; IPersistFile::Save 6."""
    link, pf = _link_and_file()
    try:
        _method(link, 20, ctypes.HRESULT, wintypes.LPCWSTR)(target)
        if workdir:
            _method(link, 9, ctypes.HRESULT, wintypes.LPCWSTR)(workdir)
        if description:
            _method(link, 7, ctypes.HRESULT, wintypes.LPCWSTR)(description)
        if icon:
            _method(link, 17, ctypes.HRESULT, wintypes.LPCWSTR, ctypes.c_int)(icon, 0)
        os.makedirs(os.path.dirname(lnk), exist_ok=True)
        _method(pf, 6, ctypes.HRESULT, wintypes.LPCWSTR, wintypes.BOOL)(lnk, True)
    finally:
        _release(pf)
        _release(link)
    log(f"collegamento: {lnk} -> {target}")


def shortcut_target(lnk):
    """IPersistFile::Load 5, IShellLinkW::GetPath 3 (percorso così come è stato salvato)."""
    link, pf = _link_and_file()
    try:
        _method(pf, 5, ctypes.HRESULT, wintypes.LPCWSTR, wintypes.DWORD)(lnk, 0)
        buf = ctypes.create_unicode_buffer(1024)
        _method(link, 3, ctypes.HRESULT, wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)(
            buf, 1024, None, 0x4)   # SLGP_RAWPATH
        return buf.value
    finally:
        _release(pf)
        _release(link)


def start_folders():
    return [os.path.join(known_folder("Programs"), f) for f in dict.fromkeys((START_FOLDER, OLD_START_FOLDER))]


def own_links(targets):
    """Collegamenti sul Desktop e nel menu Start che puntano a QUESTA installazione (anche con i nomi delle build di
    prova); mai quelli dell'altra edizione."""
    targets = {os.path.normcase(t) for t in targets if t}
    paths = [os.path.join(known_folder("Desktop"), n) for n in dict.fromkeys((SHORTCUT, OLD_SHORTCUT))]
    for start in start_folders():
        if os.path.isdir(start):
            paths += [os.path.join(start, n) for n in os.listdir(start) if n.lower().endswith(".lnk")]
    out = []
    for lnk in paths:
        try:
            if os.path.isfile(lnk) and os.path.normcase(shortcut_target(lnk)) in targets:
                out.append(lnk)
        except OSError as e:
            log(f"collegamento {lnk}: {e}")
    return out


def remove_links(links):
    for lnk in links:
        try:
            os.remove(lnk)
            log(f"rimosso il collegamento {lnk}")
        except OSError as e:
            log(f"collegamento {lnk}: {e}")
    for start in start_folders():
        try:
            os.rmdir(start)       # solo se vuota (l'altra edizione può avere qui i suoi collegamenti)
        except OSError:
            pass


# -------------------------------------------------------------------------------------------- file e cartelle
def _on_rm_error(func, path, _exc):
    try:
        os.chmod(path, stat.S_IWRITE)   # file in sola lettura
        func(path)
    except OSError:
        pass


def clear_readonly(path):
    attrs = kernel32.GetFileAttributesW(path)
    if attrs != 0xFFFFFFFF and attrs & FILE_ATTRIBUTE_READONLY:
        kernel32.SetFileAttributesW(path, attrs & ~FILE_ATTRIBUTE_READONLY)


def remove_tree(path):
    if os.path.isdir(path):
        clear_readonly(path)
        shutil.rmtree(path, onerror=_on_rm_error)
    return not os.path.exists(path)


def remove_item(path):
    if os.path.isdir(path):
        return remove_tree(path)
    try:
        kernel32.SetFileAttributesW(path, FILE_ATTRIBUTE_NORMAL)
        os.remove(path)
    except OSError:
        pass
    return not os.path.exists(path)


def cmd_exe():
    return os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "cmd.exe")


def schedule_removal(path):
    """Cancella una cartella DOPO la fine di questo processo (che ne usa i file), con il cmd.exe di sistema in una
    console nascosta: nessun file .bat, nessuna finestra. Riprova per un minuto (antivirus, indicizzazione)."""
    loop = (f'for /l %i in (1,1,60) do (ping -n 2 127.0.0.1 >nul & rmdir /s /q "{path}" 2>nul & '
            f'if not exist "{path}" exit 0)')
    subprocess.Popen(f'"{cmd_exe()}" /d /c {loop}', cwd=os.path.dirname(path), close_fds=True,
                     creationflags=0x08000000)   # CREATE_NO_WINDOW (la console di cmd esiste ma resta invisibile)
    log(f"rimozione programmata dopo la chiusura: {path}")


def rename_retry(src, dst, attempts=20):
    """Spostamento con nuovi tentativi: l'antivirus può tenere aperto per un attimo un file appena scritto."""
    for i in range(attempts):
        try:
            os.rename(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.25 * min(i + 1, 8))


def folder_in_use(path):
    """True se la cartella non si può spostare: un file è aperto (programma in esecuzione) o bloccato."""
    if not os.path.isdir(path):
        return False
    probe = path + ".verifica"
    try:
        os.rename(path, probe)
    except OSError:
        return True
    rename_retry(probe, path)
    return False


def folder_free(path, attempts=12):
    for i in range(attempts):
        if not folder_in_use(path):
            return True
        time.sleep(0.5 * min(i + 1, 4))
    return False


def tree_stats(paths):
    count = size = 0
    for p in paths:
        if os.path.isdir(p):
            for base, _dirs, names in os.walk(p):
                for n in names:
                    try:
                        size += os.path.getsize(os.path.join(base, n))
                        count += 1
                    except OSError:
                        pass
        elif os.path.isfile(p):
            count += 1
            size += os.path.getsize(p)
    return count, size


# ------------------------------------------------------------------------------------ origine dei file
class SubFile:
    """Una porzione di un file vista come file a sé (l'archivio ZIP accodato all'installer in un solo file)."""

    def __init__(self, path, offset, length):
        self._f = open(path, "rb")
        self._off, self._len, self._pos = offset, length, 0
        self.name = path

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self._pos

    def seek(self, pos, whence=0):
        base = {0: 0, 1: self._pos, 2: self._len}[whence]
        self._pos = max(0, base + pos)
        return self._pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self._len - self._pos
        n = max(0, min(n, self._len - self._pos))
        self._f.seek(self._off + self._pos)
        data = self._f.read(n)
        self._pos += len(data)
        return data

    def close(self):
        self._f.close()


class ArchiveSource:
    """File del programma nell'archivio dell'installer in un solo file (germano-<versione>.exe)."""

    def __init__(self, exe):
        self.exe = exe
        with open(exe, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size < SFX_TRAILER.size:
                raise SetupError(T("L'installer è danneggiato o incompleto: scaricalo di nuovo.",
                                   "The installer is damaged or incomplete: download it again."))
            f.seek(size - SFX_TRAILER.size)
            magic, _ko, _kl, offset, length = SFX_TRAILER.unpack(f.read(SFX_TRAILER.size))
        if magic != SFX_MAGIC or offset + length > size - SFX_TRAILER.size:
            raise SetupError(T("L'installer è danneggiato o incompleto: scaricalo di nuovo.",
                               "The installer is damaged or incomplete: download it again."))
        self.zip = zipfile.ZipFile(SubFile(exe, offset, length))
        self.mtimes = {}
        try:
            self.mtimes = json.loads(self.zip.read(META_PREFIX + "mtimes.json"))
        except KeyError:
            pass
        self.files, self.total, self.longest = [], 0, 0
        for info in self.zip.infolist():
            name = info.filename
            parts = name.rstrip("/").split("/")
            if name.startswith(META_PREFIX) or not parts[0] or ".." in parts or ":" in name:
                continue
            if parts[0].lower() in EXCLUDE_TOP:
                continue
            rel = os.path.join(*parts)
            self.files.append((info, rel, info.file_size))
            self.total += info.file_size
            self.longest = max(self.longest, len(rel))

    def install(self, item, dst):
        info, rel, _size = item
        if info.is_dir():
            os.makedirs(dst, exist_ok=True)
            return
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with self.zip.open(info) as src, open(dst, "wb") as out:   # lo ZIP controlla il CRC di ogni file
            shutil.copyfileobj(src, out, 1 << 20)
        mtime = self.mtimes.get(info.filename)
        if mtime:   # data originale: serve anche alla cache dei moduli Python già compilati
            os.utime(dst, ns=(mtime, mtime))

    def default_config(self):
        try:
            return self.zip.read("config.json")
        except KeyError:
            return None

    def close(self):
        self.zip.close()


class FolderSource:
    """File del programma in una cartella del pacchetto (sviluppo e collaudo dai sorgenti)."""

    def __init__(self, folder):
        self.folder = folder
        self.files, self.total, self.longest = [], 0, 0
        for base, dirs, names in os.walk(folder):
            rel = os.path.relpath(base, folder)
            top = rel == "."
            if top:
                dirs[:] = [d for d in dirs if d.lower() not in EXCLUDE_TOP]
            for n in names:
                if top and n.lower() in EXCLUDE_TOP:
                    continue
                src = os.path.join(base, n)
                r = n if top else os.path.join(rel, n)
                size = os.path.getsize(src)
                self.files.append((src, r, size))
                self.total += size
                self.longest = max(self.longest, len(r))

    def install(self, item, dst):
        src, _rel, _size = item
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, "rb") as fi, open(dst, "wb") as fo:
            shutil.copyfileobj(fi, fo, 1 << 20)
        shutil.copystat(src, dst)

    def default_config(self):
        try:
            with open(os.path.join(self.folder, "config.json"), "rb") as f:
                return f.read()
        except OSError:
            return None

    def close(self):
        pass


# ------------------------------------------------------------------------------------------- utilità varie
def is_admin():
    """True se questo processo ha i permessi di amministratore (copia elevata dopo la richiesta UAC)."""
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def current_user_sid():
    """SID dell'account con cui gira questo processo (S-1-5-21-...)."""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(wintypes.HANDLE(-1), 0x0008, ctypes.byref(token)):   # TOKEN_QUERY
        return None
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))           # TokenUser
        buf = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
            return None
        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(ctypes.c_void_p(sid), ctypes.byref(text)):
            return None
        try:
            return text.value
        finally:
            kernel32.LocalFree(text)
    finally:
        kernel32.CloseHandle(token)


def user_reg(key):
    """(radice, chiave) del registro dell'utente per cui si installa: HKCU, oppure HKEY_USERS\\<SID> quando i
    permessi di amministratore sono stati concessi con un altro account."""
    sid = USER_CTX.get("sid")
    if sid and sid != current_user_sid():
        return winreg.HKEY_USERS, sid + "\\" + key
    return winreg.HKEY_CURRENT_USER, key


def read_registry(key):
    try:
        with winreg.OpenKey(*user_reg(key)) as k:
            out = {}
            for name in ("InstallLocation", "DisplayVersion"):
                try:
                    out[name] = winreg.QueryValueEx(k, name)[0]
                except OSError:
                    pass
            return out
    except OSError:
        return {}


def read_install_info(app):
    return _read_json(os.path.join(app, "germano_install.json")) if app else {}


def data_items(data):
    """Elementi di Germano presenti nella cartella dati (mai altri file che l'utente vi avesse messo)."""
    if not data or not os.path.isdir(data):
        return []
    out = []
    for n in os.listdir(data):
        low = n.lower()
        if low in DATA_ITEMS or low.startswith(("config.json.", "daemon.log.")):
            out.append(os.path.join(data, n))
    return out


def set_folder_icon(folder, icon, tip):
    """Icona di Germano sulla cartella dei dati (desktop.ini nascosto; l'attributo «sola lettura» della cartella
    serve solo a Esplora file per leggere desktop.ini e non impedisce di scriverci)."""
    ini = os.path.join(folder, "desktop.ini")
    try:
        if os.path.exists(ini):
            kernel32.SetFileAttributesW(ini, FILE_ATTRIBUTE_NORMAL)
        with open(ini, "w", encoding="utf-16", newline="") as f:
            f.write(f"[.ShellClassInfo]\r\nIconResource={icon},0\r\nInfoTip={tip}\r\n")
        kernel32.SetFileAttributesW(ini, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
        attrs = kernel32.GetFileAttributesW(folder)
        if attrs != 0xFFFFFFFF:
            kernel32.SetFileAttributesW(folder, attrs | FILE_ATTRIBUTE_READONLY)
        shell32.SHChangeNotify(0x00001000, 0x0005, folder, None)   # SHCNE_UPDATEDIR, SHCNF_PATHW
    except OSError as e:
        log(f"icona della cartella dati non impostata: {e}")


def clear_folder_icon(folder):
    ini = os.path.join(folder, "desktop.ini")
    if os.path.isfile(ini):
        remove_item(ini)
    clear_readonly(folder)
    shell32.SHChangeNotify(0x00001000, 0x0005, folder, None)


def write_data_readme(data):
    if LANG == "it":
        name, text = "LEGGIMI.txt", (
            "GERMANO AI - CARTELLE DI LAVORO\r\n\r\n"
            "input       Metti qui i documenti da anonimizzare (anche intere cartelle).\r\n"
            "output      Qui trovi i documenti anonimizzati, con la stessa struttura di cartelle.\r\n"
            "processed   Gli originali, spostati qui dopo l'elaborazione.\r\n"
            "failed      I documenti che non è stato possibile elaborare (il motivo è nella Dashboard).\r\n"
            "extracted   Il Vault (deanonymize_vault.json: l'archivio delle corrispondenze che permette di\r\n"
            "            ripristinare i dati originali) e, per ogni documento, l'elenco dei dati trovati.\r\n\r\n"
            "ATTENZIONE: il Vault e le cartelle input e processed contengono dati personali in chiaro.\r\n"
            "Non condividerli e non sincronizzarli con servizi cloud; proteggi il disco (es. BitLocker).\r\n\r\n"
            "config.json contiene le impostazioni, daemon.log il registro del motore di anonimizzazione.\r\n"
            "La cartella nascosta \"state\" contiene solo file tecnici temporanei.\r\n"
            "Disinstallando Germano AI queste cartelle restano qui, a meno che tu non scelga di eliminarle.\r\n")
    else:
        name, text = "README.txt", (
            "GERMANO AI - WORK FOLDERS\r\n\r\n"
            "input       Put the documents to anonymize here (whole folders too).\r\n"
            "output      The anonymized documents, with the same folder structure.\r\n"
            "processed   The originals, moved here after processing.\r\n"
            "failed      Documents that could not be processed (the reason is shown in the Dashboard).\r\n"
            "extracted   The Vault (deanonymize_vault.json: the mapping archive used to restore the original\r\n"
            "            data) and, for each document, the list of data found.\r\n\r\n"
            "WARNING: the Vault and the input and processed folders contain personal data in clear text.\r\n"
            "Do not share them or sync them with cloud services; protect the disk (e.g. BitLocker).\r\n\r\n"
            "config.json holds the settings, daemon.log the anonymization engine log.\r\n"
            "The hidden \"state\" folder only holds temporary technical files.\r\n"
            "Uninstalling Germano AI keeps these folders, unless you choose to delete them.\r\n")
    with open(os.path.join(data, name), "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)


def write_result(path, status, plan, error=None):
    """Esito per Germano (modalità aggiornamento): letto all'avvio successivo e mostrato nella Dashboard."""
    if not path:
        return
    data = {"status": status, "from": plan.get("previous") or "", "target": plan["version"],
            "to": plan["version"] if status == "ok" else (plan.get("previous") or ""), "error": error,
            "time": time.time()}
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(path + ".tmp", path)
    except OSError as e:
        log(f"esito non scritto in {path}: {e}")


# ----------------------------------------------------------------------------------------- processi di Germano
_BROWSERS = {"msedge.exe", "chrome.exe", "brave.exe", "chromium.exe"}


def germano_processes(app, tech):
    """Processi del programma installato (eseguibili dentro la sua cartella) e la sua finestra (il browser in
    modalità app con il profilo dedicato di Germano). Mai altri processi; escluso questo installer."""
    import psutil
    me = os.getpid()
    root = os.path.normcase(os.path.abspath(app)) + os.sep
    needle = ("--user-data-dir=" + os.path.join(tech, "webview")).lower()
    own, windows = [], []
    for p in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            if p.info["pid"] == me:
                continue
            cmd = " ".join(p.info["cmdline"] or [])
            if os.path.normcase(p.info["exe"] or "").startswith(root):
                if "germano_install.py" not in cmd and "--uninstall" not in cmd:
                    own.append(p)
            elif (p.info["name"] or "").lower() in _BROWSERS and needle in cmd.lower():
                windows.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return own, windows


def germano_running(app, tech):
    try:
        own, windows = germano_processes(app, tech)
        return bool(own or windows)
    except Exception as e:
        log(f"controllo dei processi non riuscito: {e}")
        return False


def close_germano(app, tech):
    """Chiude Germano come la X rossa: si chiude la finestra e il launcher spegne server e motore. Solo se dopo 30
    secondi qualcosa è ancora aperto, viene terminato."""
    import psutil
    own, windows = germano_processes(app, tech)
    log(f"chiusura di Germano: {len(own)} processi, {len(windows)} della finestra")
    for p in windows:
        try:
            p.terminate()
        except psutil.Error:
            pass
    psutil.wait_procs(windows, timeout=5)
    deadline = time.time() + 30
    while time.time() < deadline:
        own, windows = germano_processes(app, tech)
        if not own and not windows:
            return True
        time.sleep(0.5)
    rest = own + windows
    for p in rest:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _gone, alive = psutil.wait_procs(rest, timeout=8)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass
    own, windows = germano_processes(app, tech)
    return not own and not windows


# --------------------------------------------------------------------------- firewall e permessi (UAC all'avvio)
def netsh(arguments):
    """netsh di sistema in una console nascosta: (codice di uscita, testo)."""
    exe = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "netsh.exe")
    r = subprocess.run(f'"{exe}" {arguments}', capture_output=True, creationflags=0x08000000)
    raw = (r.stdout or b"") + (r.stderr or b"")
    try:          # Windows 11 scrive in UTF-8 su una pipe; altrimenti la codifica OEM della console (cp850)
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("oem", errors="replace")
    return r.returncode, text.strip()


def set_firewall(app, add):
    """Accesso dalla rete locale per la modalità Server LAN: regola per programma (solo il Python di QUESTA
    installazione, che esegue server e motore; solo reti private e di dominio), valida anche se le porte 8181/TCP e
    8182/UDP vengono cambiate. Servono i permessi di amministratore, chiesti all'avvio dell'installer."""
    if not is_admin():
        log("firewall: nessun permesso di amministratore" + (" (collaudo)" if TEST_NO_ELEVATION else "") +
            ": regola non modificata")
        return False
    code, out = netsh(f'advfirewall firewall delete rule name="{FIREWALL_RULE}"')
    log(f"firewall, rimozione della regola precedente: codice {code}")
    if not add:
        return code == 0 or "nessuna regola" in out.lower() or "no rules" in out.lower()
    for old in LEGACY_FIREWALL_RULES:
        code, _out = netsh(f'advfirewall firewall delete rule name="{old}"')
        if code == 0:
            log(f"firewall: tolta la regola di una versione precedente «{old}»")
    program = os.path.join(app, "runtime", "python.exe")
    code, out = netsh(f'advfirewall firewall add rule name="{FIREWALL_RULE}" dir=in action=allow program="{program}" '
                      f'enable=yes profile=private,domain')
    log(f"firewall, regola «{FIREWALL_RULE}» per {program}: codice {code} {out}")
    return code == 0


def write_user_context():
    """Cartelle, variabili e SID dell'utente corrente in un file temporaneo per la copia elevata (--user-context)."""
    ctx = {"sid": current_user_sid(), "folders": {n: known_folder(n) for n in FOLDERID},
           "env": {v: os.environ[v] for v in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer") if os.environ.get(v)}}
    path = os.path.join(tempfile.gettempdir(), f"germano_utente_{os.getpid()}_{int(time.time())}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ctx, f, ensure_ascii=False)
    return path


def relaunch_uninstall_elevated(args):
    """La disinstallazione toglie la regola del firewall: chiede SUBITO i permessi di amministratore riavviando
    Germano.exe (nome e icona di Germano nella richiesta UAC) con gli stessi argomenti. Restituisce il codice di
    uscita di questa copia (la disinstallazione prosegue nella copia elevata)."""
    exe = os.path.join(HERE, "Germano.exe")
    params = ["--uninstall", "--elevated", f"--user-context={write_user_context()}", f"--lang={LANG}"]
    params += [a for a in args if a.startswith("--") and a not in params and a != "--uninstall"
               and not a.startswith(("--user-context", "--lang"))]
    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask = 0x00000100                  # SEE_MASK_NOASYNC
    sei.lpVerb = "runas"
    sei.lpFile = exe
    sei.lpParameters = " ".join(f'"{p}"' if " " in p else p for p in params)
    sei.lpDirectory = HERE
    sei.nShow = 1
    if shell32.ShellExecuteExW(ctypes.byref(sei)):
        log("disinstallazione: riavviata con i permessi di amministratore")
        return 0
    err = ctypes.get_last_error()
    log(f"disinstallazione: permessi di amministratore non concessi (errore {err})")
    message(T("Servono i permessi di amministratore", "Administrator permission is required"),
            T(f"Per disinstallare {PRODUCT} bisogna togliere la regola del firewall di Windows che consente l'accesso "
              "dalla rete locale. Avvia di nuovo la disinstallazione e scegli «Sì».",
              f"To uninstall {PRODUCT} the Windows Firewall rule that allows access from the local network must be "
              "removed. Start the uninstall again and choose “Yes”."), "warn")
    return 2


# --------------------------------------------------------------------------------------------- installazione
class Cancelled(Exception):
    pass


class SetupError(Exception):
    pass


def make_plan(opts, source):
    ver = version()
    previous = read_registry(REG_KEY)
    location = previous.get("InstallLocation")
    app = location if location and os.path.isdir(location) else os.path.join(known_folder("UserProgramFiles"),
                                                                              APP_FOLDER)
    app = os.path.normpath(app)
    info = read_install_info(app)
    tech = info.get("tech_dir") or os.path.join(known_folder("LocalAppData"), APP_FOLDER)
    docs = known_folder("Documents")
    cloud = False
    if not SUITE:
        data = tech                      # il client leggero non ha cartelle di lavoro
    elif opts.get("data_dir"):
        data = os.path.abspath(opts["data_dir"])
    elif info.get("data_dir"):
        data = info["data_dir"]          # aggiornamento: i dati restano dove sono
    elif in_cloud_sync(docs):
        data, cloud = os.path.join(known_folder("Profile"), DATA_FOLDER), True
    else:
        data = os.path.join(docs, DATA_FOLDER)
    installed = bool(previous) or os.path.isfile(os.path.join(app, "Germano.exe"))
    return {"version": ver, "previous": (previous.get("DisplayVersion") or info.get("version") or "?") if installed
            else None, "app": app, "staging": app + ".nuovo", "old": app + ".vecchio", "tech": tech,
            "data": os.path.normpath(data), "cloud": cloud, "source": source, "files": source.files,
            "total": source.total, "longest": source.longest, "firewall_before": bool(info.get("firewall")),
            "suite_installed": not SUITE and bool(read_registry(SUITE_REG_KEY)), "no_desktop": opts.get("no_desktop")}


def plan_problem(plan):
    """Motivo per cui non si può installare (titolo, testo), oppure None."""
    folder = getattr(plan["source"], "folder", None)
    if folder and os.path.normcase(folder) == os.path.normcase(plan["app"]):
        return (T(f"{PRODUCT} è già installato in questa cartella", f"{PRODUCT} is already installed in this folder"),
                T("Per reinstallarlo avvia l'installer scaricato (germano-<versione>.exe).",
                  "To reinstall it, run the downloaded installer (germano-<version>.exe)."))
    if not plan["files"]:
        return (T("L'installer non contiene il programma", "The installer does not contain the program"),
                T("Scarica di nuovo l'installer da https://download.germano.ai/",
                  "Download the installer again from https://download.germano.ai/"))
    if len(plan["app"]) + 1 + plan["longest"] > 259:
        return (T("Percorso di installazione troppo lungo", "Installation path too long"),
                T(f"{plan['app']}\n\nAlcuni file supererebbero il limite di Windows di 260 caratteri.",
                  f"{plan['app']}\n\nSome files would exceed the Windows limit of 260 characters."))
    probe = plan["app"]
    while not os.path.isdir(probe):
        probe = os.path.dirname(probe)
    free = shutil.disk_usage(probe).free
    need = plan["total"] + 300 * (1 << 20)
    if free < need:
        drive = os.path.splitdrive(plan["app"])[0]
        return (T("Spazio su disco insufficiente", "Not enough disk space"),
                T(f"Servono circa {fmt_size(need)} liberi sul disco {drive}, ne sono disponibili {fmt_size(free)}.",
                  f"About {fmt_size(need)} of free space is needed on drive {drive}, {fmt_size(free)} available."))
    return None


class InstallJob:
    """L'installazione vera e propria (in un thread quando c'è la finestra): file in una cartella nuova, poi
    sostituzione istantanea della versione precedente, dati, collegamenti, registro e, se richiesto, firewall."""

    def __init__(self, plan):
        self.plan = plan
        self.phase = "start"
        self.shown = None
        self.cancel = False
        self.close_first = False
        self.firewall = False
        self.firewall_ok = None
        self.files_done = self.bytes_done = 0
        self.changed = False
        self.error = ""
        self.hwnd = None

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        com = False
        try:
            ole32.CoInitializeEx(None, 0x2 | 0x4)    # APARTMENTTHREADED | DISABLE_OLE1DDE (collegamenti, UAC)
            com = True
        except OSError:
            pass
        try:
            self._run()
            self.phase = "done"
        except Cancelled:
            log("installazione annullata dall'utente")
            self.phase = "cancelled"
        except Exception as e:
            log("ERRORE: " + traceback.format_exc())
            self.error = str(e) if isinstance(e, SetupError) else f"{type(e).__name__}: {e}"
            self.phase = "error"
        finally:
            if os.path.isdir(self.plan["staging"]):
                remove_tree(self.plan["staging"])
            if com:
                ole32_void.CoUninitialize()

    def _run(self):
        p = self.plan
        log(f"installazione {PRODUCT} {p['version']} (precedente: {p['previous']}): origine="
            f"{getattr(p['source'], 'exe', None) or getattr(p['source'], 'folder', '')} programma={p['app']} "
            f"dati={p['data']} tecnici={p['tech']} file={len(p['files'])} byte={p['total']}")
        if self.close_first:
            self.phase = "closing"
            if not close_germano(p["app"], p["tech"]):
                raise SetupError(T("Non è stato possibile chiudere Germano AI. Chiudilo e riprova.",
                                   "Germano AI could not be closed. Close it and try again."))
        if self.cancel:
            raise Cancelled
        self.phase = "copy"
        for leftover in (p["staging"], p["old"]):
            if os.path.isdir(leftover) and not remove_tree(leftover):
                raise SetupError(T(f"Impossibile eliminare la cartella {leftover} rimasta da un'installazione "
                                   "precedente.", f"Cannot delete the folder {leftover} left by a previous setup."))
        for item in p["files"]:
            if self.cancel:
                raise Cancelled
            p["source"].install(item, os.path.join(p["staging"], item[1]))
            self.files_done += 1
            self.bytes_done += item[2]
        if self.cancel:
            raise Cancelled
        log(f"installati {self.files_done} file ({self.bytes_done} byte) nella cartella provvisoria")

        self.phase = "final"
        if os.path.isdir(p["app"]):
            if not folder_free(p["app"]):
                raise SetupError(T("La cartella del programma installato è in uso. Chiudi Germano AI e le finestre "
                                   f"di Esplora file aperte su:\n{p['app']}",
                                   "The installed program folder is in use. Close Germano AI and any File Explorer "
                                   f"window showing:\n{p['app']}"))
            keep = os.path.join(p["app"], "client_config.json")   # il client conserva il collegamento al server
            if not SUITE and os.path.isfile(keep):
                shutil.copy2(keep, os.path.join(p["staging"], "client_config.json"))
            rename_retry(p["app"], p["old"])
        try:
            rename_retry(p["staging"], p["app"])
        except Exception:
            if os.path.isdir(p["old"]) and not os.path.exists(p["app"]):
                rename_retry(p["old"], p["app"])
            raise
        self.changed = True
        if os.path.isdir(p["old"]) and not remove_tree(p["old"]):
            schedule_removal(p["old"])

        self.write_record(p["firewall_before"])
        os.makedirs(p["tech"], exist_ok=True)
        self.prepare_data()
        self.create_shortcuts()
        self.register()
        if self.firewall and (is_admin() or not p["firewall_before"]):
            self.phase = "firewall"           # accesso dalla rete locale consentito (regola del firewall)
            self.firewall_ok = set_firewall(p["app"], True)
            if self.firewall_ok:
                self.write_record(True)
        log("installazione completata")

    def write_record(self, firewall):
        p = self.plan
        info = {"edition": EDITION, "version": p["version"], "app_dir": p["app"], "data_dir": p["data"],
                "tech_dir": p["tech"], "firewall": bool(firewall), "language": LANG,
                "installed_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(os.path.join(p["app"], "germano_install.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)

    def prepare_data(self):
        data = self.plan["data"]
        os.makedirs(data, exist_ok=True)
        if not SUITE:
            return
        for name in WORK_FOLDERS:
            os.makedirs(os.path.join(data, name), exist_ok=True)
        state = os.path.join(data, "state")
        os.makedirs(state, exist_ok=True)
        kernel32.SetFileAttributesW(state, FILE_ATTRIBUTE_HIDDEN)   # solo file tecnici
        cfg = os.path.join(data, "config.json")
        default = self.plan["source"].default_config()
        if not os.path.exists(cfg) and default:
            with open(cfg, "wb") as f:                                # impostazioni predefinite del pacchetto
                f.write(default)
        write_data_readme(data)
        set_folder_icon(data, os.path.join(self.plan["app"], ICON_REL),
                        T("Cartelle di lavoro di Germano AI: input, output, failed e Vault",
                          "Germano AI work folders: input, output, failed and Vault"))

    def create_shortcuts(self):
        p = self.plan
        exe = os.path.join(p["app"], "Germano.exe")
        icon = os.path.join(p["app"], ICON_REL)
        desc = (T("Germano AI: anonimizzazione dei documenti, 100% offline",
                  "Germano AI: document anonymization, 100% offline") if SUITE else
                T("Germano AI Client: collega questo PC al Server Germano AI della rete locale",
                  "Germano AI Client: connects this PC to the Germano AI Server on the local network"))
        start = os.path.join(known_folder("Programs"), START_FOLDER)
        if not SUITE:     # build di prova: il client usava i nomi della suite
            remove_links([lnk for lnk in own_links([exe]) if os.path.basename(lnk) == OLD_SHORTCUT])
        if not p.get("no_desktop"):
            create_shortcut(os.path.join(known_folder("Desktop"), SHORTCUT), exe, p["app"], icon, desc)
        create_shortcut(os.path.join(start, SHORTCUT), exe, p["app"], icon, desc)
        if SUITE:
            create_shortcut(os.path.join(start, T("Cartelle di lavoro di Germano AI.lnk", "Germano AI work folders.lnk")),
                            p["data"], p["data"], "", T("Cartelle input, output, failed e Vault di Germano AI",
                                                        "Germano AI input, output, failed and Vault folders"))

    def register(self):
        """Voce in Impostazioni > App > App installate (solo per questo utente)."""
        p = self.plan
        exe = os.path.join(p["app"], "Germano.exe")
        values = (("DisplayName", PRODUCT), ("DisplayVersion", p["version"]), ("Publisher", "germano.ai"),
                  ("InstallLocation", p["app"]), ("DisplayIcon", os.path.join(p["app"], ICON_REL)),
                  ("UninstallString", f'"{exe}" --uninstall'),
                  ("QuietUninstallString", f'"{exe}" --uninstall --silent'),
                  ("URLInfoAbout", "https://germano.ai"), ("URLUpdateInfo", "https://download.germano.ai/"),
                  ("InstallDate", time.strftime("%Y%m%d")),
                  ("Comments", T("Anonimizzazione dei documenti, 100% offline", "Document anonymization, 100% offline")
                   if SUITE else T("Client della rete locale di Germano AI", "Germano AI local network client")))
        root, key = user_reg(REG_KEY)
        with winreg.CreateKey(root, key) as k:
            for name, value in values:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
            for name, value in (("NoModify", 1), ("NoRepair", 1), ("EstimatedSize", min(p["total"] // 1024, 0x7FFFFFFF))):
                winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)
        log(f"registrato in Impostazioni > App: {'HKCU' if root == winreg.HKEY_CURRENT_USER else 'HKU'}\\{key}")


def launch(app):
    exe = os.path.join(app, "Germano.exe")
    log(f"avvio di {exe}")
    subprocess.Popen([exe], cwd=app, close_fds=True)


def open_germano(app):
    """Apre Germano a fine installazione. Con l'avviatore (--launch-file) lo apre l'avviatore stesso, con i permessi
    normali dell'utente anche quando questa copia ha quelli di amministratore."""
    exe = os.path.join(app, "Germano.exe")
    if LAUNCH_FILE:
        try:
            with open(LAUNCH_FILE, "w", encoding="utf-8") as f:
                f.write(exe)
            log(f"programma da aprire alla fine (dall'avviatore): {exe}")
            return
        except OSError as e:
            log(f"file di avvio non scritto ({e}): avvio diretto")
    launch(app)


# ------------------------------------------------------------------------------------------ disinstallazione
class UninstallJob:
    def __init__(self, app, info):
        self.app = app
        self.info = info
        self.data = info.get("data_dir") or ""
        self.tech = info.get("tech_dir") or os.path.join(known_folder("LocalAppData"), APP_FOLDER)
        self.remove_data = False
        self.close_first = False
        self.phase = "start"
        self.shown = None
        self.error = ""
        self.firewall_removed = None
        self.data_left = []
        self.hwnd = None

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        com = False
        try:
            ole32.CoInitializeEx(None, 0x2 | 0x4)
            com = True
        except OSError:
            pass
        try:
            self._run()
            self.phase = "done"
        except Exception as e:
            log("ERRORE: " + traceback.format_exc())
            self.error = str(e) if isinstance(e, SetupError) else f"{type(e).__name__}: {e}"
            self.phase = "error"
        finally:
            if com:
                ole32_void.CoUninitialize()

    def _run(self):
        log(f"disinstallazione: programma={self.app} dati={self.data} tecnici={self.tech} "
            f"elimina dati={self.remove_data}")
        if self.close_first:
            self.phase = "closing"
            if not close_germano(self.app, self.tech):
                raise SetupError(T("Non è stato possibile chiudere Germano AI. Chiudilo e riprova.",
                                   "Germano AI could not be closed. Close it and try again."))
        self.phase = "remove"
        remove_links(own_links([os.path.join(self.app, "Germano.exe"), self.data]))
        try:
            winreg.DeleteKey(*user_reg(REG_KEY))
            log(f"rimossa la voce di Impostazioni > App {REG_KEY}")
        except OSError:
            pass
        if self.info.get("firewall"):
            self.phase = "firewall"
            self.firewall_removed = set_firewall(self.app, False)
            self.phase = "remove"
        if os.path.normcase(self.tech) != os.path.normcase(self.app) and not remove_tree(self.tech):
            schedule_removal(self.tech)
        if SUITE and self.data and os.path.isdir(self.data):
            if self.remove_data:
                self.phase = "data"
                for item in data_items(self.data):
                    remove_item(item)
                clear_readonly(self.data)
                try:
                    os.rmdir(self.data)       # solo se non contiene altri file dell'utente
                except OSError:
                    pass
                self.data_left = data_items(self.data)
                log(f"cartelle di lavoro eliminate; rimasti: {self.data_left}")
            else:
                clear_folder_icon(self.data)
        log("disinstallazione completata; la cartella del programma si elimina alla chiusura")


# ------------------------------------------------------------------------------- finestre (TaskDialog nativo)
TDF_ENABLE_HYPERLINKS, TDF_USE_HICON_MAIN, TDF_ALLOW_DIALOG_CANCELLATION = 0x0001, 0x0002, 0x0008
TDF_USE_COMMAND_LINKS, TDF_VERIFICATION_FLAG_CHECKED = 0x0010, 0x0100
TDF_SHOW_PROGRESS_BAR, TDF_SHOW_MARQUEE_PROGRESS_BAR, TDF_CALLBACK_TIMER = 0x0200, 0x0400, 0x0800
TDCBF_CANCEL_BUTTON, TDCBF_CLOSE_BUTTON = 0x0008, 0x0020
TDN_CREATED, TDN_NAVIGATED, TDN_BUTTON_CLICKED, TDN_HYPERLINK_CLICKED, TDN_TIMER = 0, 1, 2, 3, 4
TDN_VERIFICATION_CLICKED = 8
WM_USER, WM_SETICON = 0x0400, 0x0080
TDM_NAVIGATE_PAGE, TDM_CLICK_BUTTON = WM_USER + 101, WM_USER + 102
TDM_SET_PROGRESS_BAR_RANGE, TDM_SET_PROGRESS_BAR_POS = WM_USER + 105, WM_USER + 106
TDM_SET_PROGRESS_BAR_MARQUEE, TDM_ENABLE_BUTTON, TDM_UPDATE_ELEMENT_TEXT = WM_USER + 107, WM_USER + 111, WM_USER + 114
TDE_CONTENT = 0
TD_ICONS = {"warn": 0xFFFF, "error": 0xFFFE, "info": 0xFFFD, "shield": 0xFFFC}
IDCANCEL = 2
BTN_INSTALL, BTN_FINISH, BTN_CLOSE_APP, BTN_UNINSTALL, BTN_DELETE, BTN_KEEP, BTN_RETRY = range(100, 107)


class TASKDIALOG_BUTTON(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("nButtonID", ctypes.c_int), ("pszButtonText", wintypes.LPCWSTR)]


TD_CALLBACK = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                 ctypes.c_ssize_t)


class TASKDIALOGCONFIG(ctypes.Structure):
    _pack_ = 1      # commctrl.h la dichiara con allineamento a 1 byte
    _fields_ = [("cbSize", wintypes.UINT), ("hwndParent", wintypes.HWND), ("hInstance", wintypes.HINSTANCE),
                ("dwFlags", ctypes.c_int), ("dwCommonButtons", ctypes.c_int), ("pszWindowTitle", wintypes.LPCWSTR),
                ("hMainIcon", ctypes.c_void_p), ("pszMainInstruction", wintypes.LPCWSTR),
                ("pszContent", wintypes.LPCWSTR), ("cButtons", wintypes.UINT),
                ("pButtons", ctypes.POINTER(TASKDIALOG_BUTTON)), ("nDefaultButton", ctypes.c_int),
                ("cRadioButtons", wintypes.UINT), ("pRadioButtons", ctypes.POINTER(TASKDIALOG_BUTTON)),
                ("nDefaultRadioButton", ctypes.c_int), ("pszVerificationText", wintypes.LPCWSTR),
                ("pszExpandedInformation", wintypes.LPCWSTR), ("pszExpandedControlText", wintypes.LPCWSTR),
                ("pszCollapsedControlText", wintypes.LPCWSTR), ("hFooterIcon", ctypes.c_void_p),
                ("pszFooter", wintypes.LPCWSTR), ("pfCallback", TD_CALLBACK), ("lpCallbackData", ctypes.c_ssize_t),
                ("cxWidth", wintypes.UINT)]


_task_dialog_indirect = None


def _ui_setup():
    """Stile moderno (Common Controls 6), nitidezza sugli schermi ad alta risoluzione e un'identità propria nella
    barra delle applicazioni (non quella di Python)."""
    global _task_dialog_indirect
    for call in (lambda: user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)),
                 lambda: user32.SetProcessDPIAware()):
        try:
            if call():
                break
        except Exception:
            continue
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID("GermanoAI.Setup")
    except Exception:
        pass

    class ACTCTXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.ULONG), ("dwFlags", wintypes.DWORD), ("lpSource", wintypes.LPCWSTR),
                    ("wProcessorArchitecture", wintypes.USHORT), ("wLangId", wintypes.USHORT),
                    ("lpAssemblyDirectory", wintypes.LPCWSTR), ("lpResourceName", ctypes.c_void_p),
                    ("lpApplicationName", wintypes.LPCWSTR), ("hModule", wintypes.HMODULE)]
    manifest = os.path.join(tempfile.gettempdir(), f"germano_setup_{os.getpid()}.manifest")
    try:
        with open(manifest, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0"><dependency>'
                    '<dependentAssembly><assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" '
                    'version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"/>'
                    '</dependentAssembly></dependency></assembly>')
        _proto(kernel32.CreateActCtxW, wintypes.HANDLE, ctypes.POINTER(ACTCTXW))
        _proto(kernel32.ActivateActCtx, wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t))
        act = ACTCTXW(ctypes.sizeof(ACTCTXW), 0, manifest)
        handle = kernel32.CreateActCtxW(ctypes.byref(act))
        if handle and handle != ctypes.c_void_p(-1).value:
            kernel32.ActivateActCtx(handle, ctypes.byref(ctypes.c_size_t()))
        fn = ctypes.WinDLL("comctl32").TaskDialogIndirect
        _proto(fn, ctypes.HRESULT, ctypes.POINTER(TASKDIALOGCONFIG), ctypes.POINTER(ctypes.c_int),
               ctypes.POINTER(ctypes.c_int), ctypes.POINTER(wintypes.BOOL))
        _task_dialog_indirect = fn
    except Exception as e:
        log(f"finestre moderne non disponibili ({e}): uso le finestre di messaggio semplici")
    finally:
        try:
            os.remove(manifest)
        except OSError:
            pass


def _dpi():
    try:
        return user32.GetDpiForSystem() or 96
    except Exception:
        return 96


def load_icon(size):
    path = icon_file()
    return user32.LoadImageW(None, path, 1, size, size, 0x10) if path else None   # LR_LOADFROMFILE


def message(instruction, content="", icon="info"):
    """Avviso semplice (anche senza TaskDialog). In modalità silenziosa finisce solo nel registro."""
    log(f"MESSAGGIO [{icon}] {instruction} | {content}")
    if SILENT:
        return
    if _task_dialog_indirect:
        try:
            Wizard(PRODUCT).run(Page(instruction, content, icon=icon, common=TDCBF_CLOSE_BUTTON))
            return
        except Exception as e:
            log(f"finestra non disponibile: {e}")
    flags = {"error": 0x10, "warn": 0x30}.get(icon, 0x40) | 0x10000
    user32.MessageBoxW(None, instruction + ("\n\n" + content if content else ""), PRODUCT, flags)


class Page:
    """Una pagina della finestra: testi, pulsanti e reazioni (on_button che restituisce False = la finestra resta
    aperta, di solito perché si passa a un'altra pagina)."""

    def __init__(self, instruction, content="", icon="app", buttons=(), common=0, default=0, verification=None,
                 checked=False, details=None, footer=None, progress=None, command_links=False, on_button=None,
                 on_timer=None, on_show=None):
        self.instruction, self.content, self.icon, self.buttons = instruction, content, icon, list(buttons)
        self.common, self.default, self.verification, self.checked = common, default, verification, checked
        self.details, self.footer, self.progress, self.command_links = details, footer, progress, command_links
        self.on_button, self.on_timer, self.on_show = on_button, on_timer, on_show


class Wizard:
    """Una sola finestra TaskDialog che passa da una pagina all'altra (TDM_NAVIGATE_PAGE)."""

    def __init__(self, title):
        self.title = title
        self.hwnd = None
        self.page = None
        self.checked = False
        self.result = 2
        self.launch = False
        self._alive = []
        self._callback = TD_CALLBACK(self._proc)
        scale = _dpi() / 96
        self.icon = load_icon(round(32 * scale))
        self.icon_small = load_icon(round(16 * scale))

    def _config(self, page):
        cfg = TASKDIALOGCONFIG()
        cfg.cbSize = ctypes.sizeof(TASKDIALOGCONFIG)
        flags = TDF_ALLOW_DIALOG_CANCELLATION | TDF_CALLBACK_TIMER | TDF_ENABLE_HYPERLINKS
        if page.icon == "app" and self.icon:
            flags |= TDF_USE_HICON_MAIN
            cfg.hMainIcon = self.icon
        else:
            cfg.hMainIcon = TD_ICONS.get(page.icon, TD_ICONS["info"])
        if page.checked:
            flags |= TDF_VERIFICATION_FLAG_CHECKED
        if page.progress == "bar":
            flags |= TDF_SHOW_PROGRESS_BAR
        elif page.progress == "marquee":
            flags |= TDF_SHOW_MARQUEE_PROGRESS_BAR
        if page.command_links:
            flags |= TDF_USE_COMMAND_LINKS
        cfg.dwFlags = flags
        cfg.dwCommonButtons = page.common
        cfg.pszWindowTitle = self.title
        cfg.pszMainInstruction = page.instruction
        cfg.pszContent = page.content or None
        if page.buttons:
            arr = (TASKDIALOG_BUTTON * len(page.buttons))(*[TASKDIALOG_BUTTON(i, t) for i, t in page.buttons])
            self._alive.append(arr)
            cfg.cButtons = len(page.buttons)
            cfg.pButtons = ctypes.cast(arr, ctypes.POINTER(TASKDIALOG_BUTTON))
        cfg.nDefaultButton = page.default
        cfg.pszVerificationText = page.verification
        if page.details:
            cfg.pszExpandedInformation = page.details
            cfg.pszCollapsedControlText = T("Mostra i dettagli", "Show details")
            cfg.pszExpandedControlText = T("Nascondi i dettagli", "Hide details")
        if page.footer:
            cfg.pszFooter = page.footer
            cfg.hFooterIcon = TD_ICONS["info"]
        cfg.pfCallback = self._callback
        cfg.cxWidth = 290
        self._alive.append(cfg)
        return cfg

    @staticmethod
    def _log_page(page):
        log(f"PAGINA: {page.instruction}" + (f" [casella: {page.verification}]" if page.verification else ""))

    def run(self, page):
        cfg = self._config(page)
        self.page = page
        self._log_page(page)
        button, radio, verified = ctypes.c_int(), ctypes.c_int(), wintypes.BOOL()
        _task_dialog_indirect(ctypes.byref(cfg), ctypes.byref(button), ctypes.byref(radio), ctypes.byref(verified))
        return button.value

    def navigate(self, page):
        cfg = self._config(page)
        self.page = page
        self._log_page(page)
        user32.SendMessageW(self.hwnd, TDM_NAVIGATE_PAGE, 0, ctypes.addressof(cfg))

    def set_text(self, element, text):
        buf = ctypes.create_unicode_buffer(text)
        user32.SendMessageW(self.hwnd, TDM_UPDATE_ELEMENT_TEXT, element, ctypes.addressof(buf))

    def enable(self, button, on):
        user32.SendMessageW(self.hwnd, TDM_ENABLE_BUTTON, button, 1 if on else 0)

    def click(self, button):
        user32.SendMessageW(self.hwnd, TDM_CLICK_BUTTON, button, 0)

    def progress(self, fraction):
        user32.SendMessageW(self.hwnd, TDM_SET_PROGRESS_BAR_POS, int(max(0.0, min(1.0, fraction)) * 1000), 0)

    def _proc(self, hwnd, msg, wparam, lparam, _data):
        try:
            if msg in (TDN_CREATED, TDN_NAVIGATED):
                self.hwnd = hwnd
                if msg == TDN_CREATED:
                    if self.icon:
                        user32.SendMessageW(hwnd, WM_SETICON, 1, self.icon)
                    if self.icon_small:
                        user32.SendMessageW(hwnd, WM_SETICON, 0, self.icon_small)
                    user32.SetForegroundWindow(hwnd)
                self.checked = self.page.checked
                if self.page.progress == "bar":
                    user32.SendMessageW(hwnd, TDM_SET_PROGRESS_BAR_RANGE, 0, 1000 << 16)
                elif self.page.progress == "marquee":
                    user32.SendMessageW(hwnd, TDM_SET_PROGRESS_BAR_MARQUEE, 1, 30)
                if self.page.on_show:
                    self.page.on_show(self)
            elif msg == TDN_VERIFICATION_CLICKED:
                self.checked = bool(wparam)
            elif msg == TDN_HYPERLINK_CLICKED:
                target = ctypes.wstring_at(lparam)
                if os.path.exists(target):
                    os.startfile(target)
            elif msg == TDN_BUTTON_CLICKED:
                log(f"  pulsante {wparam}" + (" (casella selezionata)" if self.checked else ""))
                if self.page.on_button and self.page.on_button(self, wparam) is False:
                    return 1      # S_FALSE: la finestra resta aperta
            elif msg == TDN_TIMER and self.page.on_timer:
                self.page.on_timer(self)
        except Exception:
            log("ERRORE nell'interfaccia: " + traceback.format_exc())
        return 0


def _link(path, text=None):
    if any(c in path for c in '<>"'):
        return text or path
    return f'<a href="{path}">{text or path}</a>'


# -------------------------------------------------------------------------------------- flusso: installazione
def install_ui(plan, opts):
    p = plan
    update_mode = bool(opts.get("update"))
    update = p["previous"] is not None
    same = update and p["previous"] == p["version"]
    wiz = Wizard(T(f"Aggiornamento di {PRODUCT}", f"{PRODUCT} Update") if update_mode else
                 T(f"Installazione di {PRODUCT}", f"{PRODUCT} Setup"))
    jobs = []

    def new_job():
        job = InstallJob(plan)
        job.firewall = SUITE          # accesso dalla rete locale sempre consentito (nessuna casella da spuntare)
        jobs.append(job)
        return job

    def go(w, job):
        w.navigate(in_use_page(job) if germano_running(p["app"], p["tech"]) else progress_page(job))

    # --- conferma
    if SUITE:
        if update:
            title = (T(f"Reinstallare Germano AI {p['version']}?", f"Reinstall Germano AI {p['version']}?") if same else
                     T(f"Aggiornare Germano AI alla versione {p['version']}?",
                       f"Update Germano AI to version {p['version']}?"))
            content = T(f"È installata la versione {p['previous']}. Le cartelle di lavoro, il Vault e le impostazioni "
                        f"restano come sono:\n{_link(p['data'])}",
                        f"Version {p['previous']} is installed. Your work folders, Vault and settings stay as they "
                        f"are:\n{_link(p['data'])}")
        else:
            title = T(f"Installare Germano AI {p['version']}?", f"Install Germano AI {p['version']}?")
            content = T("Germano AI anonimizza i tuoi documenti direttamente su questo computer, 100% offline.\n\n"
                        f"Le cartelle di lavoro (input, output, failed e il Vault) saranno in:\n{p['data']}",
                        "Germano AI anonymizes your documents right on this computer, 100% offline.\n\n"
                        f"The work folders (input, output, failed and the Vault) will be in:\n{p['data']}")
            if p["cloud"]:
                content += T("\n\nLa cartella Documenti è sincronizzata con OneDrive: per non copiare nel cloud i "
                             "documenti originali e il Vault, le cartelle di lavoro vanno nella cartella del tuo "
                             "profilo.", "\n\nYour Documents folder is synced with OneDrive: to keep the original "
                             "documents and the Vault out of the cloud, the work folders go in your profile folder.")
        # nessuna nota sul firewall: la regola per l'accesso dalla rete locale (solo reti private e di dominio) si crea
        # comunque in silenzio con i permessi di amministratore concessi all'avvio; l'esito resta nel registro
        footer = None
    else:
        title = (T(f"Aggiornare Germano AI Client alla versione {p['version']}?",
                   f"Update Germano AI Client to version {p['version']}?") if update and not same else
                 T(f"Installare Germano AI Client {p['version']}?", f"Install Germano AI Client {p['version']}?"))
        content = T("Il client collega questo computer al Server Germano AI della tua rete locale, che anonimizza i "
                    "dati prima che arrivino alle AI.", "The client connects this computer to the Germano AI Server "
                    "on your local network, which anonymizes data before it reaches the AIs.")
        if update:
            content += T("\n\nIl collegamento al server già configurato resta com'è.",
                         "\n\nThe server connection already configured is kept.")
        if p["suite_installed"]:
            content += T("\n\nSu questo computer è già installata la versione completa di Germano AI, che comprende "
                         "anche le funzioni del client: il client non è necessario.",
                         "\n\nThe full version of Germano AI is already installed on this computer and also includes "
                         "the client features: the client is not needed.")
        footer = T("Non servono diritti di amministratore.", "No administrator rights required.")
    details = T(f"Programma: {p['app']}\nFile tecnici: {p['tech']}\nCollegamenti: Desktop e menu Start\n"
                f"Spazio richiesto: {fmt_size(p['total'])}\nDisinstallazione: Impostazioni > App > App installate",
                f"Program: {p['app']}\nTechnical files: {p['tech']}\nShortcuts: Desktop and Start menu\n"
                f"Space required: {fmt_size(p['total'])}\nUninstall: Settings > Apps > Installed apps")
    label = (T("Reinstalla", "Reinstall") if same else T("Aggiorna", "Update")) if update else T("Installa", "Install")

    def on_confirm(w, button):
        if button != BTN_INSTALL:
            return True
        go(w, new_job())
        return False

    confirm = Page(title, content, buttons=[(BTN_INSTALL, label)], common=TDCBF_CANCEL_BUTTON, default=BTN_INSTALL,
                   details=details, footer=footer, on_button=on_confirm)

    # --- programma aperto
    def in_use_page(job):
        def on_button(w, button):
            if button != BTN_CLOSE_APP:
                return True
            job.close_first = True
            w.navigate(progress_page(job))
            return False
        return Page(T("Germano AI è aperto", "Germano AI is running"),
                    T("Per continuare bisogna chiudere Germano AI. Se sta elaborando dei documenti, attendi che abbia "
                      "finito.", "Germano AI must be closed to continue. If it is processing documents, wait until "
                      "it has finished."), icon="warn",
                    buttons=[(BTN_CLOSE_APP, T("Chiudi Germano AI e continua", "Close Germano AI and continue"))],
                    common=TDCBF_CANCEL_BUTTON, default=BTN_CLOSE_APP, on_button=on_button)

    # --- avanzamento
    def progress_page(job):
        def on_show(w):
            job.hwnd = w.hwnd
            job.start()

        def on_button(w, button):
            if job.phase == "done":
                return True               # chiusura automatica a installazione completata
            if button == IDCANCEL and job.phase in ("start", "closing", "copy") and not job.cancel:
                job.cancel = True
                w.enable(IDCANCEL, False)
                w.set_text(TDE_CONTENT, T("Annullamento in corso...", "Cancelling...") + "\n ")
            return False

        def on_timer(w):
            if job.phase == "copy" and not job.cancel:
                w.progress(job.bytes_done / max(1, p["total"]))
                w.set_text(TDE_CONTENT, T(f"Installazione dei file: {fmt_int(job.files_done)} di "
                                          f"{fmt_int(len(p['files']))}\n{fmt_size(job.bytes_done)} di {fmt_size(p['total'])}",
                                          f"Installing files: {fmt_int(job.files_done)} of {fmt_int(len(p['files']))}\n"
                                          f"{fmt_size(job.bytes_done)} of {fmt_size(p['total'])}"))
            elif job.phase == "closing" and job.shown != "closing":
                job.shown = "closing"
                w.set_text(TDE_CONTENT, T("Chiusura di Germano AI...", "Closing Germano AI...") + "\n ")
            elif job.phase in ("final", "firewall") and job.shown != job.phase:
                job.shown = job.phase
                w.enable(IDCANCEL, False)
                w.progress(1.0)
                if job.phase == "final":
                    text = T("Creazione delle cartelle di lavoro e dei collegamenti...",
                             "Creating the work folders and shortcuts...") + "\n "
                else:                 # regola del firewall: in silenzio, senza avvisi
                    text = T("Completamento dell'installazione...", "Finishing setup...") + "\n "
                w.set_text(TDE_CONTENT, text)
            elif job.phase == "done" and job.shown != "done":
                job.shown = "done"            # niente pagina finale: la finestra si chiude e si apre Germano
                write_result(opts.get("result"), "ok", p)
                w.result = 0
                w.launch = True
                w.set_text(TDE_CONTENT, T("Apertura di Germano AI...", "Opening Germano AI...") + "\n ")
                w.enable(IDCANCEL, True)      # il clic simulato vale solo su un pulsante attivo
                w.click(IDCANCEL)
            elif job.phase == "cancelled":
                write_result(opts.get("result"), "cancelled", p, T("annullato dall'utente", "cancelled by the user"))
                w.navigate(Page(T("Installazione annullata", "Setup cancelled"),
                                T("Il computer non è stato modificato.", "Nothing was changed on this computer."),
                                icon="info", common=TDCBF_CLOSE_BUTTON))
            elif job.phase == "error":
                write_result(opts.get("result"), "error", p, job.error)
                w.navigate(error_page(job))

        if update_mode:
            title = T(f"Aggiornamento di {PRODUCT} alla versione {p['version']} in corso...",
                      f"Updating {PRODUCT} to version {p['version']}...")
        elif update:
            title = T(f"Aggiornamento di {PRODUCT} in corso...", f"Updating {PRODUCT}...")
        else:
            title = T(f"Installazione di {PRODUCT} in corso...", f"Installing {PRODUCT}...")
        return Page(title, T("Preparazione...", "Preparing...") + "\n ", progress="bar", common=TDCBF_CANCEL_BUTTON,
                    on_button=on_button, on_timer=on_timer, on_show=on_show)

    def error_page(job):
        content = job.error + "\n\n"
        content += (T(f"Germano AI è stato copiato in {p['app']}, ma la configurazione non è stata completata.",
                      f"Germano AI was copied to {p['app']}, but the configuration was not completed.") if job.changed
                    else T("Il computer non è stato modificato.", "Nothing was changed on this computer."))
        content += T(f"\nDettagli: {_link(LOG_FILE, 'registro dell’installazione')}",
                     f"\nDetails: {_link(LOG_FILE, 'setup log')}")

        def on_button(w, button):
            if button != BTN_RETRY:
                w.result = 1
                return True
            job2 = new_job()
            job2.close_first = update_mode
            go(w, job2)
            return False
        return Page(T("Installazione non riuscita", "Setup failed"), content, icon="error",
                    buttons=[(BTN_RETRY, T("Riprova", "Retry"))], common=TDCBF_CLOSE_BUTTON, default=BTN_RETRY,
                    on_button=on_button)

    if update_mode:          # già confermato in Germano: si parte subito, chiudendo Germano se è ancora aperto
        job = new_job()
        job.close_first = True
        wiz.run(progress_page(job))
    else:
        wiz.run(confirm)
    if jobs and jobs[-1].phase == "cancelled":
        wiz.result = 2
    if wiz.result == 0 and wiz.launch:
        open_germano(p["app"])
    elif update_mode and os.path.isfile(os.path.join(p["app"], "Germano.exe")):
        open_germano(p["app"])     # aggiornamento annullato o non riuscito: si riapre la versione installata
    return wiz.result


def install_silent(plan, opts):
    if germano_running(plan["app"], plan["tech"]) and not opts.get("update"):
        log("Germano AI è aperto: installazione silenziosa non eseguita")
        write_result(opts.get("result"), "error", plan, "Germano AI è aperto")
        return 3
    job = InstallJob(plan)
    job.firewall = SUITE
    job.close_first = bool(opts.get("update"))
    job.run()
    status = {"done": "ok", "cancelled": "cancelled"}.get(job.phase, "error")
    write_result(opts.get("result"), status, plan, job.error or None)
    if status == "ok" and opts.get("update"):
        open_germano(plan["app"])
    return {"ok": 0, "cancelled": 2}.get(status, 1)


def run_install(opts):
    payload = opts.get("payload")
    source = ArchiveSource(payload) if payload else FolderSource(HERE)
    try:
        plan = make_plan(opts, source)
        problem = plan_problem(plan)
        if problem:
            message(problem[0], problem[1], "error")
            write_result(opts.get("result"), "error", plan, problem[0])
            return 1
        if SILENT:
            return install_silent(plan, opts)
        if not _task_dialog_indirect:     # ripiego: finestre di messaggio semplici, senza avanzamento
            if not opts.get("update") and user32.MessageBoxW(
                    None, T(f"Installare {PRODUCT} {plan['version']} in\n{plan['app']}?",
                            f"Install {PRODUCT} {plan['version']} in\n{plan['app']}?"),
                    PRODUCT, 0x1 | 0x20 | 0x10000) != 1:
                return 2
            opts = dict(opts, update=True)   # nessuna finestra di avanzamento: Germano si chiude e si riapre da solo
            rc = install_silent(plan, opts)
            message(T(f"{PRODUCT} è stato installato.", f"{PRODUCT} has been installed.") if rc == 0 else
                    T("Installazione non riuscita.", "Setup failed."), "" if rc == 0 else LOG_FILE,
                    "info" if rc == 0 else "error")
            return rc
        return install_ui(plan, opts)
    finally:
        source.close()


# ---------------------------------------------------------------------------------- flusso: disinstallazione
def uninstall_ui(job):
    wiz = Wizard(T(f"Disinstallazione di {PRODUCT}", f"{PRODUCT} Uninstall"))
    items = data_items(job.data) if SUITE else []

    def go(w):
        w.navigate(in_use_page() if germano_running(job.app, job.tech) else progress_page())

    def on_confirm(w, button):
        if button != BTN_UNINSTALL:
            return True
        job.remove_data = bool(items) and w.checked
        if job.remove_data:
            w.navigate(data_page())
        else:
            go(w)
        return False

    def data_page():
        count, size = tree_stats(items)

        def on_button(w, button):
            if button not in (BTN_DELETE, BTN_KEEP):
                return True
            job.remove_data = button == BTN_DELETE
            go(w)
            return False
        return Page(T("Eliminare definitivamente le cartelle di lavoro?", "Permanently delete the work folders?"),
                    T(f"{job.data}\n\nContengono {fmt_int(count)} file ({fmt_size(size)}): documenti, risultati e il "
                      "Vault. Senza il Vault non potrai più ripristinare i dati originali nei documenti già "
                      "anonimizzati.", f"{job.data}\n\nThey contain {fmt_int(count)} files ({fmt_size(size)}): "
                      "documents, results and the Vault. Without the Vault you can no longer restore the original "
                      "data in documents already anonymized."), icon="warn",
                    buttons=[(BTN_KEEP, T("Mantieni le cartelle di lavoro\nVengono rimossi solo il programma e i "
                                          "collegamenti", "Keep the work folders\nOnly the program and shortcuts are "
                                          "removed")),
                             (BTN_DELETE, T("Elimina definitivamente\nI file non vanno nel Cestino e non si possono "
                                            "recuperare", "Delete permanently\nThe files do not go to the Recycle Bin "
                                            "and cannot be recovered"))],
                    common=TDCBF_CANCEL_BUTTON, default=BTN_KEEP, command_links=True, on_button=on_button)

    def in_use_page():
        def on_button(w, button):
            if button != BTN_CLOSE_APP:
                return True
            job.close_first = True
            w.navigate(progress_page())
            return False
        return Page(T("Germano AI è aperto", "Germano AI is running"),
                    T("Per disinstallarlo bisogna chiudere Germano AI. Se sta elaborando dei documenti, attendi che "
                      "abbia finito.", "Germano AI must be closed to uninstall it. If it is processing documents, "
                      "wait until it has finished."), icon="warn",
                    buttons=[(BTN_CLOSE_APP, T("Chiudi Germano AI e continua", "Close Germano AI and continue"))],
                    common=TDCBF_CANCEL_BUTTON, default=BTN_CLOSE_APP, on_button=on_button)

    def progress_page():
        def on_show(w):
            w.enable(IDCANCEL, False)     # la rimozione non si interrompe a metà
            job.hwnd = w.hwnd
            job.start()

        def on_timer(w):
            texts = {"closing": T("Chiusura di Germano AI...", "Closing Germano AI..."),
                     "firewall": T("Rimozione della regola del firewall di Windows...",
                                   "Removing the Windows Firewall rule..."),
                     "data": T("Eliminazione delle cartelle di lavoro...", "Deleting the work folders...")}
            if job.phase in texts and job.shown != job.phase:
                job.shown = job.phase
                w.set_text(TDE_CONTENT, texts[job.phase])
            elif job.phase == "done":
                w.navigate(finish_page())
            elif job.phase == "error":
                w.navigate(Page(T("Disinstallazione non completata", "Uninstall not completed"),
                                job.error + T(f"\n\nDettagli: {_link(LOG_FILE, 'registro')}",
                                              f"\n\nDetails: {_link(LOG_FILE, 'log')}"),
                                icon="error", common=TDCBF_CLOSE_BUTTON))
        return Page(T(f"Disinstallazione di {PRODUCT} in corso...", f"Uninstalling {PRODUCT}..."),
                    T("Rimozione del programma e dei collegamenti...", "Removing the program and shortcuts..."),
                    progress="marquee", common=TDCBF_CANCEL_BUTTON, on_button=lambda w, b: False,
                    on_timer=on_timer, on_show=on_show)

    def finish_page():
        content = ""
        if SUITE and job.data and os.path.isdir(job.data) and not job.remove_data:
            content = T(f"Le cartelle di lavoro e il Vault sono rimasti in:\n{_link(job.data)}",
                        f"The work folders and the Vault are still in:\n{_link(job.data)}")
        elif SUITE and job.remove_data:
            content = (T(f"Alcuni file non sono stati eliminati:\n{_link(job.data)}",
                         f"Some files could not be deleted:\n{_link(job.data)}") if job.data_left else
                       T("Le cartelle di lavoro sono state eliminate.", "The work folders have been deleted."))
        if job.firewall_removed is False:
            content += T(f"\n\nLa regola del firewall «{FIREWALL_RULE}» non è stata rimossa (permessi di "
                         "amministratore non disponibili): non ha effetto, perché il programma non esiste più.",
                         f"\n\nThe firewall rule “{FIREWALL_RULE}” was not removed (administrator permission not "
                         "available): it has no effect, because the program no longer exists.")

        def on_button(w, button):
            w.result = 0
            return True
        return Page(T(f"{PRODUCT} è stato disinstallato", f"{PRODUCT} has been uninstalled"), content.strip(),
                    buttons=[(BTN_FINISH, T("Fine", "Finish"))], default=BTN_FINISH, on_button=on_button)

    content = T("Verranno rimossi il programma, i collegamenti sul Desktop e nel menu Start e i file tecnici.",
                "The program, the Desktop and Start menu shortcuts and the technical files will be removed.")
    if items:
        content += T(f"\n\nLe cartelle di lavoro e il Vault restano in {_link(job.data)}, a meno che tu non scelga "
                     "di eliminarli.", f"\n\nThe work folders and the Vault stay in {_link(job.data)}, unless you "
                     "choose to delete them.")
    wiz.run(Page(T(f"Disinstallare {PRODUCT}?", f"Uninstall {PRODUCT}?"), content,
                 buttons=[(BTN_UNINSTALL, T("Disinstalla", "Uninstall"))], common=TDCBF_CANCEL_BUTTON,
                 default=BTN_UNINSTALL, verification=T("Elimina anche le cartelle di lavoro e il Vault",
                                                       "Also delete the work folders and the Vault") if items else None,
                 on_button=on_confirm))
    if job.phase == "start":
        return 2
    return 0 if job.phase == "done" else 1


def run_uninstall(opts):
    app = HERE
    info = read_install_info(app)
    if not info:
        message(T("Questa copia di Germano AI non è installata", "This copy of Germano AI is not installed"),
                T(f"{app}\n\nPer rimuoverla basta eliminare la sua cartella.",
                  f"{app}\n\nTo remove it, just delete its folder."), "info")
        return 1
    job = UninstallJob(app, info)
    time.sleep(1.0)     # il launcher che ci ha avviati si chiude
    if SILENT or not _task_dialog_indirect:
        if not SILENT and user32.MessageBoxW(None, T(f"Disinstallare {PRODUCT}?", f"Uninstall {PRODUCT}?"), PRODUCT,
                                             0x4 | 0x20 | 0x10000) != 6:
            return 2
        if germano_running(job.app, job.tech):
            if SILENT:
                log("Germano AI è aperto: disinstallazione silenziosa non eseguita")
                return 3
            job.close_first = True
        job.remove_data = bool(opts.get("remove_data"))
        job.run()
        rc = 0 if job.phase == "done" else 1
    else:
        rc = uninstall_ui(job)
    if job.phase == "done":
        schedule_removal(app)
    return rc


def main():
    global SILENT
    args = sys.argv[1:]
    action = args[0] if args and args[0] in ("install", "uninstall") else "install"
    SILENT = "--silent" in args
    opts = {"no_desktop": "--no-desktop" in args, "remove_data": "--remove-data" in args, "update": "--update" in args,
            "data_dir": _arg_value("--data-dir"), "payload": _arg_value("--payload"), "result": _arg_value("--result")}
    log(f"===== {action} {' '.join(args[1:])} (lingua {LANG}, script {HERE}, amministratore: {is_admin()})")
    try:
        ole32.CoInitializeEx(None, 0x2 | 0x4)
    except OSError:
        pass
    if not SILENT:
        _ui_setup()
    if action == "uninstall":
        if _arg_value("--user-context"):            # file temporaneo scritto dalla copia non elevata
            try:
                os.remove(_arg_value("--user-context"))
            except OSError:
                pass
        elif (read_install_info(HERE).get("firewall") and not is_admin() and not TEST_NO_ELEVATION
              and "--elevated" not in args):
            return relaunch_uninstall_elevated(args)   # permessi di amministratore chiesti SUBITO, all'avvio
    kernel32.CreateMutexW(None, False, "Local\\GermanoAI.Setup")
    if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS
        message(T("L'installazione di Germano AI è già in corso", "Germano AI Setup is already running"),
                T("Completa o chiudi la finestra già aperta.", "Complete or close the window already open."), "info")
        return 2
    try:
        rc = run_install(opts) if action == "install" else run_uninstall(opts)
    except Exception as e:
        log("ERRORE imprevisto: " + traceback.format_exc())
        message(T("Si è verificato un errore imprevisto", "An unexpected error occurred"),
                f"{type(e).__name__}: {e}\n\n" + T(f"Dettagli in {LOG_FILE}", f"Details in {LOG_FILE}"), "error")
        rc = 1
    log(f"===== fine {action}: codice {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
