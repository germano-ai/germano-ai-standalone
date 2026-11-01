"""Aggiornamenti silenziosi di Germano AI Client, come Google Chrome (solo libreria standard).

Unica fonte: https://download.germano.ai/version.json (voci «windows-client», «macos-client», «linux-client») e gli
installer accanto. Comportamento predefinito, senza finestre né avvisi che interrompono:
- controllo in background solo se il sistema segnala una connessione a Internet (Windows: InternetGetConnectedState,
  lo stato gia' noto al sistema, nessuna connessione aperta per scoprirlo), 30 secondi dopo l'avvio e poi ogni 6 ore;
- download a bassa priorita' nella cartella tecnica dell'utente, con il controllo di completezza (dimensione indicata
  da version.json e struttura dell'installer);
- Windows: al successivo avvio di Germano Client l'installer (pochi MB) aggiorna il programma in pochi secondi, senza
  finestre (--update --silent), e lo riapre da solo; con «Riavvia per aggiornare» subito;
- macOS e Linux: il pacchetto si scarica allo stesso modo e si apre con il programma di installazione del sistema
  quando lo decide l'utente (servono le sue conferme).
Il collegamento al server (client_config.json) resta com'e'. Per i collaudi: GERMANO_UPDATE_URL (mirror o server di
prova; HTTP solo verso questo computer) e GERMANO_OFFLINE=1 (nessun controllo).

Uso dal lanciatore: client_updater.py --install-update   (codice 10 = installer avviato, il lanciatore si chiude)
"""
import json
import os
import re
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_BASE = "https://download.germano.ai/"
OFFICIAL_HOSTS = ("germano.ai",)
FIRST_CHECK_DELAY = 30
CHECK_INTERVAL = 6 * 3600
MAX_REDIRECTS = 5
MAX_SIZE = 2 * 1024 ** 3
SFX_MAGIC = b"GERMANO.SFX.0001"
SFX_TRAILER = struct.Struct("<16sQQQQ")
INSTALLER_RE = re.compile(r"^germano-client-(\d+(?:\.\d+)+(?:-[A-Za-z]+\d*)?)\.(exe|pkg|deb)$", re.IGNORECASE)
UPDATE_EXIT_CODE = 10
EXT = {"windows": "exe", "macos": "pkg", "linux": "deb"}


def get_version():
    try:
        with open(os.path.join(BASE_DIR, "VERSION"), encoding="utf-8-sig") as f:
            return f.read().strip() or "0.70"
    except OSError:
        return "0.70"


def platform():
    if os.name == "nt":
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def _read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def update_dir():
    """Cartella tecnica dell'utente (indicata dal lanciatore o in germano_install.json), altrimenti accanto al
    programma (copia portatile)."""
    if os.environ.get("GERMANO_TECH_DIR"):
        return os.path.join(os.environ["GERMANO_TECH_DIR"], "update")
    info = _read_json(os.path.join(BASE_DIR, "germano_install.json")) or {}
    if info.get("tech_dir"):
        return os.path.join(info["tech_dir"], "update")
    return os.path.join(BASE_DIR, "update")


UPDATE_DIR = update_dir()
READY_FILE = os.path.join(UPDATE_DIR, "ready.json")
RESULT_FILE = os.path.join(UPDATE_DIR, "install_result.json")
LOG_FILE = os.path.join(UPDATE_DIR, "update.log")


def ulog(msg):
    try:
        os.makedirs(UPDATE_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def parse_version(v):
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)(?:[-.]?([A-Za-z]+)\.?(\d*))?\s*$", str(v or ""))
    if not m:
        return None
    nums = tuple(int(x) for x in m.group(1).split("."))[:4]
    nums += (0,) * (4 - len(nums))
    tag = (m.group(2) or "").lower()
    rank = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2}.get(tag, 3 if not tag else 0)
    return nums + (rank, int(m.group(3) or 0))


def is_newer(remote, local):
    r, l = parse_version(remote), parse_version(local)
    return r is not None and l is not None and r > l


def online():
    """True se il sistema segnala una connessione. Non apre connessioni."""
    if os.environ.get("GERMANO_OFFLINE") == "1":
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        flags = ctypes.c_ulong(0)
        return bool(ctypes.windll.wininet.InternetGetConnectedState(ctypes.byref(flags), 0))
    except Exception:
        return False


def background_priority():
    try:
        if os.name == "nt":
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.GetCurrentThread.restype = ctypes.c_void_p
            k32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
            k32.SetThreadPriority(k32.GetCurrentThread(), 0x00010000)   # THREAD_MODE_BACKGROUND_BEGIN
        elif sys.platform.startswith("linux") and hasattr(os, "setpriority"):
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 15)
    except Exception:
        pass


def source():
    custom = os.environ.get("GERMANO_UPDATE_URL")
    if custom:
        base = custom if custom.endswith("/") else custom + "/"
        host = (urllib.parse.urlparse(base).hostname or "").lower()
        return base, (host,), host not in ("127.0.0.1", "localhost", "::1")
    return DOWNLOAD_BASE, OFFICIAL_HOSTS, True


def allowed(url):
    _base, hosts, https = source()
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" and (https or p.scheme != "http"):
        return False
    host = (p.hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in hosts)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


class UpdateError(Exception):
    pass


def _get(url, timeout=30):
    """GET che segue i reindirizzamenti solo verso indirizzi ammessi."""
    for _ in range(MAX_REDIRECTS + 1):
        if not allowed(url):
            raise UpdateError(f"Indirizzo di aggiornamento non ammesso: {urllib.parse.urlparse(url).hostname}")
        req = urllib.request.Request(url, headers={"User-Agent": f"GermanoClient-Updater/{get_version()}"})
        try:
            return _OPENER.open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urllib.parse.urljoin(url, e.headers["Location"])
                continue
            raise UpdateError(f"download.germano.ai ha risposto con il codice {e.code}.") from None
        except (urllib.error.URLError, OSError) as e:
            raise UpdateError(f"{urllib.parse.urlparse(url).hostname} non raggiungibile: {e}") from None
    raise UpdateError("Troppi reindirizzamenti dal server degli aggiornamenti.")


def parse_index(data, base):
    if not isinstance(data, dict):
        return None
    ver = str(data.get("version") or "").strip()
    if not parse_version(ver):
        return None
    key = platform() + "-client"
    files = data.get("files") if isinstance(data.get("files"), dict) else {}
    entry = files.get(key)
    size = None
    if isinstance(entry, dict):
        size = entry.get("size")
        entry = entry.get("url") or entry.get("file")
    if not entry:
        entry = f"germano-client-{ver}.{EXT[platform()]}"
    url = urllib.parse.urljoin(base, str(entry))
    try:
        size = int(size) if size else None
    except (TypeError, ValueError):
        size = None
    return {"version": ver, "url": url, "name": os.path.basename(urllib.parse.urlparse(url).path), "size": size,
            "notes": data.get("notes")}


def check_package(path):
    try:
        with open(path, "rb") as f:
            if platform() == "windows":
                if f.read(2) != b"MZ":
                    return False
                size = f.seek(0, 2)
                if size < SFX_TRAILER.size + 1024:
                    return False
                f.seek(size - SFX_TRAILER.size)
                magic, ko, kl, po, pl = SFX_TRAILER.unpack(f.read(SFX_TRAILER.size))
                return magic == SFX_MAGIC and 0 < ko and ko + kl <= po and po + pl == size - SFX_TRAILER.size
            magic = {"macos": b"xar!", "linux": b"!<arch>\n"}[platform()]
            return f.read(len(magic)) == magic
    except OSError:
        return False


def read_ready():
    data = _read_json(READY_FILE)
    if not data or not data.get("installer") or not os.path.isfile(data["installer"]):
        return None
    if not is_newer(data.get("version"), get_version()):
        return None
    return data


def cleanup():
    """Installer gia' usati o superati e file di stato non piu' validi."""
    if not read_ready():
        _remove(READY_FILE)
    if not os.path.isdir(UPDATE_DIR):
        return
    current = get_version()
    for name in os.listdir(UPDATE_DIR):
        m = INSTALLER_RE.match(name[:-5] if name.endswith(".part") else name)
        if m and (name.endswith(".part") or not is_newer(m.group(1), current)):
            _remove(os.path.join(UPDATE_DIR, name))


def open_package(path):
    if sys.platform == "darwin":
        subprocess.Popen(["open", path], close_fds=True)
    else:
        subprocess.Popen(["xdg-open", path], close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


class ClientUpdater:
    def __init__(self, settings=None):
        self.settings = settings or (lambda: {})
        self.lock = threading.Lock()
        self.check_now = threading.Event()
        self.worker = None
        cleanup()
        ready = read_ready()
        self.state = {"state": "ready" if ready else "idle", "current": get_version(),
                      "latest": ready.get("version") if ready else None, "available": bool(ready), "online": None,
                      "checked_at": None, "error": None, "progress": None, "source": source()[0],
                      "platform": platform(), "manual": platform() != "windows", "staged": bool(ready), "silent": True}
        result = _read_json(RESULT_FILE)
        if result:
            self.state["last_install"] = result

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)

    def snapshot(self):
        with self.lock:
            snap = dict(self.state)
        cfg = self.settings() or {}
        snap.update(check_updates=cfg.get("check_updates", True) is not False,
                    auto_update=cfg.get("auto_update", True) is not False)
        if snap.get("state") == "ready" and snap.get("manual"):
            ready = read_ready() or {}
            snap["package"] = os.path.basename(ready.get("installer") or "")
            if platform() == "linux" and snap["package"]:
                snap["install_command"] = f"sudo apt install ./{snap['package']}"
        return snap

    def busy(self):
        return self.state.get("state") in ("checking", "downloading", "installing")

    def start_background(self):
        if self.worker and self.worker.is_alive():
            return

        def loop():
            background_priority()
            timeout = FIRST_CHECK_DELAY
            while True:
                self.check_now.wait(timeout)
                timeout = CHECK_INTERVAL
                manual = self.check_now.is_set()
                self.check_now.clear()
                cfg = self.settings() or {}
                if not manual and cfg.get("check_updates", True) is False:
                    continue
                try:
                    self.check(manual, auto_download=cfg.get("auto_update", True) is not False or manual)
                except UpdateError as e:
                    self._set(state="error", error=str(e), progress=None)
                    ulog(f"Aggiornamento non riuscito: {e}")
                except Exception as e:  # mai bloccare il client per un aggiornamento
                    self._set(state="error", error=f"Errore imprevisto: {e}", progress=None)
                    ulog(f"Errore imprevisto: {e}")
        self.worker = threading.Thread(target=loop, daemon=True, name="client-updater")
        self.worker.start()

    def request_check(self):
        self.check_now.set()

    def check(self, manual=False, auto_download=True):
        if self.busy() or read_ready():
            return self.snapshot()
        is_online = True if manual else online()
        self._set(online=is_online)
        if not is_online:
            self._set(state="idle", error=None)
            return self.snapshot()
        self._set(state="checking", error=None)
        base = source()[0]
        with _get(urllib.parse.urljoin(base, "version.json"), timeout=15) as r:
            try:
                release = parse_index(json.loads(r.read(1 << 20).decode("utf-8-sig")), base)
            except ValueError:
                release = None
        self._set(checked_at=time.time(), latest=(release or {}).get("version") or get_version(),
                  notes=(release or {}).get("notes"), checked_manual=manual)
        if not release or not is_newer(release["version"], get_version()):
            self._set(state="uptodate", available=False)
            return self.snapshot()
        self._set(state="available", available=True)
        ulog(f"Disponibile Germano AI Client {release['version']}: {release['url']}")
        if auto_download:
            self.download(release)
        return self.snapshot()

    def download(self, release):
        background_priority()
        os.makedirs(UPDATE_DIR, exist_ok=True)
        path = os.path.join(UPDATE_DIR, release["name"])
        part = path + ".part"
        self._set(state="downloading", progress={"done": 0, "total": release.get("size") or 0}, error=None)
        done, last = 0, 0.0
        try:
            with _get(release["url"], timeout=60) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0) or (release.get("size") or 0)
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if done > MAX_SIZE:
                        raise UpdateError("File di aggiornamento troppo grande.")
                    if time.time() - last > 0.5:
                        last = time.time()
                        self._set(progress={"done": done, "total": total})
        except UpdateError:
            _remove(part)
            raise
        except Exception as e:
            _remove(part)
            raise UpdateError(f"Download interrotto: {e}") from None
        if release.get("size") and done != release["size"]:
            _remove(part)
            raise UpdateError(f"Download incompleto ({done} byte su {release['size']}): riprova più tardi.")
        if not check_package(part):
            _remove(part)
            raise UpdateError("Il file scaricato non è un installer di Germano AI Client completo.")
        os.replace(part, path)
        _write_json(READY_FILE, {"version": release["version"], "installer": path, "downloaded": time.time(),
                                 "attempts": 0})
        _remove(RESULT_FILE)
        self._set(state="ready", progress=None, latest=release["version"], available=True, staged=True,
                  ready_since=time.time())
        ulog(f"Germano AI Client {release['version']} scaricato ({done} byte): si installa al prossimo avvio.")

    def launch_install(self):
        return launch_install()


def launch_install():
    """Avvia l'installer scaricato e restituisce subito. Windows: aggiornamento silenzioso (pochi secondi, poi Germano
    Client si riapre). macOS e Linux: si apre il pacchetto con il programma di installazione del sistema."""
    ready = read_ready()
    if not ready:
        raise UpdateError("Nessun aggiornamento pronto da installare.")
    if platform() != "windows":
        open_package(ready["installer"])
        return "opened"
    ready["attempts"] = int(ready.get("attempts") or 0) + 1
    ready["launched"] = time.time()
    _write_json(READY_FILE, ready)
    _remove(RESULT_FILE)
    subprocess.Popen([ready["installer"], "--update", "--silent", "--result", RESULT_FILE], cwd=UPDATE_DIR,
                     creationflags=0x00000008 | 0x00000200, close_fds=True)   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    ulog(f"Aggiornamento silenzioso a Germano AI Client {ready['version']} avviato (tentativo {ready['attempts']}).")
    return "silent"


def should_auto_install():
    ready = read_ready()
    return platform() == "windows" and bool(ready) and int(ready.get("attempts") or 0) == 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--install-update" in argv:
        if not should_auto_install():
            return 0
        try:
            launch_install()
        except Exception as e:
            ulog(f"Aggiornamento non avviato: {e}")
            return 0
        return UPDATE_EXIT_CODE
    return 0


if __name__ == "__main__":
    sys.exit(main())
