"""Aggiornamento automatico di Germano AI.

Unica fonte: https://download.germano.ai/ (nessun servizio di terzi). Il server pubblica gli installer in un solo
file e un piccolo indice:
- https://download.germano.ai/version.json
      {"version": "0.61", "notes": "...", "files": {"windows": "germano-0.61.exe", "macos": "germano-0.61.pkg",
       "linux": "germano-0.61.deb", "windows-client": "germano-client-0.61.exe", ...}}
  (i nomi dei file sono relativi a download.germano.ai; sono accettati anche indirizzi completi e, per ogni voce,
  {"url": ..., "size": ...});
- https://download.germano.ai/germano-<versione>.exe (.pkg per macOS, .deb per Linux).
Se version.json mancasse, si legge l'elenco dei file della pagina https://download.germano.ai/ e si sceglie
l'installer con la versione più alta.

Il controllo avviene solo se Windows segnala che il PC è connesso a Internet (Network List Manager: lo stato già noto
al sistema, nessuna connessione aperta da Germano per scoprirlo), 20 secondi dopo l'avvio e poi ogni 6 ore, oppure
quando l'utente lo chiede. Se c'è una versione più recente l'installer viene scaricato nella cartella tecnica
dell'utente (fuori dalla cartella del programma, che l'installer sostituisce) e ne viene controllata solo la
completezza: dimensione dichiarata dal server e struttura dell'installer in un solo file. Nessuna impronta SHA-256:
i file di download.germano.ai sono considerati attendibili.

Installazione: l'installer scaricato viene avviato in modalità aggiornamento (--update) con «Installa ora» oppure al
successivo avvio di Germano. Chiude Germano, sostituisce il programma (cartelle di lavoro, Vault e impostazioni
restano intatti), lo riapre e scrive l'esito in install_result.json, che la Dashboard mostra. Se un aggiornamento
automatico non va a buon fine non viene ripetuto a ogni avvio: si può riprovare dalla Dashboard.
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.parse

from . import common

DOWNLOAD_BASE = "https://download.germano.ai/"   # unica fonte degli aggiornamenti
INDEX_FILE = "version.json"
OFFICIAL_HOSTS = ("germano.ai",)                  # download.germano.ai e gli altri indirizzi del dominio ufficiale
MAX_REDIRECTS = 5
FIRST_CHECK_DELAY = 20          # secondi dopo l'avvio
CHECK_INTERVAL = 6 * 3600       # controllo periodico
SIZE_ESTIMATE = 3 * 1024 ** 3   # se il server non indica la dimensione: stima prudente per lo spazio su disco
INSTALL_SPACE = 5 * 1024 ** 3   # spazio che serve all'installer per la nuova copia del programma
SFX_MAGIC = b"GERMANO.SFX.0001"
SFX_TRAILER = struct.Struct("<16sQQQQ")
INSTALLER_RE = re.compile(r"^germano-(\d+(?:\.\d+)+(?:-[A-Za-z]+\d*)?)\.(exe|pkg|deb)$", re.IGNORECASE)
NLM_CLSID = "{DCB00C01-570F-4A9B-8D69-199FDBA5723B}"  # Network List Manager di Windows


def _update_dir():
    """Cartella degli aggiornamenti: quella tecnica dell'utente se Germano è installato (indicata dal launcher con
    GERMANO_TECH_DIR, oppure in germano_install.json), altrimenti update/ accanto al programma (copia portatile)."""
    if os.environ.get("GERMANO_TECH_DIR"):
        return os.path.join(os.environ["GERMANO_TECH_DIR"], "update")
    info = common.read_json(os.path.join(common.BASE_DIR, "germano_install.json"), None)
    if isinstance(info, dict) and info.get("tech_dir"):
        return os.path.join(info["tech_dir"], "update")
    return os.path.join(common.BASE_DIR, "update")


UPDATE_DIR = _update_dir()
READY_FILE = os.path.join(UPDATE_DIR, "ready.json")
RESULT_FILE = os.path.join(UPDATE_DIR, "install_result.json")
REJECTED_FILE = os.path.join(UPDATE_DIR, "rejected.json")   # versione annunciata ma con un installer diverso
LOG_FILE = os.path.join(UPDATE_DIR, "update.log")
# Resti del meccanismo precedente alla 0.60 (ZIP estratto e sostituzione file per file).
LEGACY_DIRS = [os.path.join(common.BASE_DIR, "update", d) for d in ("download", "new", "old", "installer")]


class UpdateError(Exception):
    pass


# ------------------------------------------------------------------------------------------------ utilità
def ulog(msg):
    try:
        os.makedirs(UPDATE_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def parse_version(v):
    """'0.51-alpha' -> tupla confrontabile; una versione stabile vale più della stessa alpha/beta/rc."""
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


def platform_key():
    if os.name == "nt":
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


PLATFORM_EXT = {"windows": "exe", "macos": "pkg", "linux": "deb"}


def windows_reports_online():
    """True solo se Windows indica una connessione a Internet attiva. Non apre connessioni."""
    if os.environ.get("GERMANO_OFFLINE") == "1":
        return False
    try:
        import pythoncom
        import win32com.client
    except Exception:
        return False
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass
    try:
        nlm = win32com.client.Dispatch(NLM_CLSID)
        try:
            return bool(nlm.IsConnectedToInternet)
        finally:
            del nlm
    except Exception:
        return False
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def source():
    """(indirizzo base, host ammessi, https obbligatorio). GERMANO_UPDATE_URL permette un mirror interno o un
    server di collaudo; in quel caso HTTP è ammesso solo verso questo stesso computer."""
    custom = os.environ.get("GERMANO_UPDATE_URL")
    if custom:
        base = custom if custom.endswith("/") else custom + "/"
        host = (urllib.parse.urlparse(base).hostname or "").lower()
        return base, (host,), host not in ("127.0.0.1", "localhost", "::1")
    return DOWNLOAD_BASE, OFFICIAL_HOSTS, True


def allowed(url):
    _base, hosts, https = source()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" and (https or parsed.scheme != "http"):
        return False
    host = (parsed.hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in hosts)


def parse_index(data, base):
    """Voce di version.json per questa piattaforma: {version, url, name, size, notes} oppure None."""
    if not isinstance(data, dict):
        return None
    ver = str(data.get("version") or "").strip()
    if not parse_version(ver):
        return None
    key = platform_key()
    files = data.get("files") if isinstance(data.get("files"), dict) else {}
    entry = files.get(key, data.get(key))
    size = None
    if isinstance(entry, dict):
        size = entry.get("size")
        entry = entry.get("url") or entry.get("file")
    if not entry:
        entry = f"germano-{ver}.{PLATFORM_EXT[key]}"   # convenzione dei nomi degli installer
    url = urllib.parse.urljoin(base, str(entry))
    try:
        size = int(size) if size else None
    except (TypeError, ValueError):
        size = None
    return {"version": ver, "url": url, "name": os.path.basename(urllib.parse.urlparse(url).path), "size": size,
            "notes": data.get("notes")}


def parse_listing(page, base):
    """Installer con la versione più alta tra i collegamenti della pagina di download (se manca version.json)."""
    ext = PLATFORM_EXT[platform_key()]
    best = None
    for href in re.findall(r"""href\s*=\s*["']?([^"'\s>]+)""", page or "", re.IGNORECASE):
        name = os.path.basename(urllib.parse.urlparse(urllib.parse.unquote(href)).path)
        m = INSTALLER_RE.match(name)
        if m and m.group(2).lower() == ext:
            key = parse_version(m.group(1))
            if key and (best is None or key > best[0]):
                best = (key, m.group(1), urllib.parse.urljoin(base, href), name)
    if not best:
        return None
    return {"version": best[1], "url": best[2], "name": best[3], "size": None, "notes": None}


def check_installer(path):
    """Completezza dell'installer scaricato (non è un controllo crittografico): eseguibile Windows con la coda
    dell'installer in un solo file e l'archivio per intero."""
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"MZ":
                return False
            size = f.seek(0, 2)
            if size < SFX_TRAILER.size + 1024:
                return False
            f.seek(size - SFX_TRAILER.size)
            magic, ko, kl, po, pl = SFX_TRAILER.unpack(f.read(SFX_TRAILER.size))
        return magic == SFX_MAGIC and 0 < ko and ko + kl <= po and po + pl == size - SFX_TRAILER.size
    except OSError:
        return False


def read_ready():
    """Aggiornamento scaricato e pronto da installare (più recente della versione in uso), oppure None."""
    data = common.read_json(READY_FILE, None)
    if not isinstance(data, dict) or not data.get("installer"):
        return None
    if not is_newer(data.get("version"), common.get_version()) or not os.path.isfile(data["installer"]):
        return None
    return data


def last_result():
    data = common.read_json(RESULT_FILE, None)
    return data if isinstance(data, dict) else None


def read_rejected():
    """Versione annunciata da version.json il cui installer conteneva un'altra versione (errore di pubblicazione)."""
    data = common.read_json(REJECTED_FILE, None)
    if not isinstance(data, dict) or not is_newer(data.get("version"), common.get_version()):
        return None
    return data


def rejected_message(rejected):
    return (f"Il server annuncia la versione {rejected['version']}, ma il suo installer contiene la versione "
            f"{rejected.get('found') or '?'}: l'aggiornamento non è stato applicato e non verrà riscaricato in "
            "automatico. Va corretto su download.germano.ai; puoi riprovare con «Controlla ora».")


# ------------------------------------------------------------------------------------------------ servizio
class Updater:
    """Controllo, download e avvio degli aggiornamenti (vive nel processo del server)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.check_now = threading.Event()
        self.worker = None
        self.state = {"state": "idle", "current": common.get_version(), "latest": None, "available": False,
                      "online": None, "checked_at": None, "error": None, "progress": None, "notes": None,
                      "url": None, "source": source()[0]}
        cleanup_after_install()
        ready = read_ready()
        rejected = read_rejected()
        if ready:
            self.state.update(state="ready", latest=ready.get("version"), available=True,
                              attempts=int(ready.get("attempts") or 0))
        elif rejected:
            self.state.update(state="error", latest=rejected["version"], error=rejected_message(rejected))

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)

    def snapshot(self):
        with self.lock:
            snap = dict(self.state)
        result = last_result()
        if result:
            snap["last_install"] = result
        return snap

    # -------------------------------------------------------------- controllo periodico
    def start_background(self):
        if self.worker and self.worker.is_alive():
            return

        def loop():
            timeout = FIRST_CHECK_DELAY
            while not self.stop_event.is_set():
                self.check_now.wait(timeout)
                timeout = CHECK_INTERVAL
                if self.stop_event.is_set():
                    return
                manual = self.check_now.is_set()
                self.check_now.clear()
                cfg = common.load_config()
                if not (manual or cfg.get("check_updates", True)):
                    continue
                try:
                    self.check(manual=manual, auto_download=bool(cfg.get("auto_update", True)))
                except UpdateError as e:
                    self._set(state="error", error=str(e), progress=None)
                    ulog(f"Aggiornamento non riuscito: {e}")
                except Exception as e:  # mai bloccare il server per un aggiornamento
                    self._set(state="error", error=f"Errore imprevisto: {e}", progress=None)
                    ulog(f"Errore imprevisto: {e}")

        self.worker = threading.Thread(target=loop, daemon=True, name="updater")
        self.worker.start()

    def request_check(self):
        self.check_now.set()

    def busy(self):
        return self.state.get("state") in ("checking", "downloading", "installing")

    def check(self, manual=False, auto_download=True):
        if self.busy():
            return self.snapshot()
        if self.state.get("state") == "ready" and read_ready():
            return self.snapshot()
        online = True if manual else windows_reports_online()
        self._set(online=online)
        if not online:
            self._set(state="idle", error=None)
            return self.snapshot()  # nessuna connessione: nessun tentativo di rete
        self._set(state="checking", error=None)
        latest = self.find_latest()
        current = common.get_version()
        self._set(checked_at=time.time(), latest=latest["version"] if latest else current,
                  notes=(latest or {}).get("notes"), url=(latest or {}).get("url"))
        if not latest or not is_newer(latest["version"], current):
            self._set(state="uptodate", available=False)
            return self.snapshot()
        rejected = read_rejected()
        if rejected and rejected["version"] == latest["version"] and not manual:
            self._set(state="error", available=True, error=rejected_message(rejected))
            return self.snapshot()   # stesso installer sbagliato: niente nuovo download automatico (si riprova a mano)
        by_hand = platform_key() != "windows"   # macOS/Linux: il nuovo installer si scarica e si avvia a mano
        self._set(state="available", available=True, manual=by_hand)
        ulog(f"Disponibile la versione {latest['version']} (installata {current}): {latest['url']}")
        if auto_download and not by_hand:
            self.download(latest)
        return self.snapshot()

    @staticmethod
    def _session():
        import requests
        s = requests.Session()
        s.headers["User-Agent"] = f"GermanoAI-Updater/{common.get_version()}"
        return s

    @staticmethod
    def _get(s, url, stream=False, timeout=30):
        """GET che segue i reindirizzamenti solo verso indirizzi ammessi (download.germano.ai, HTTPS)."""
        for _ in range(MAX_REDIRECTS + 1):
            if not allowed(url):
                raise UpdateError("Indirizzo di aggiornamento non ammesso: "
                                  f"{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).hostname}")
            try:
                r = s.get(url, allow_redirects=False, stream=stream, timeout=timeout)
            except Exception as e:
                raise UpdateError(f"{urllib.parse.urlparse(url).hostname} non raggiungibile: {e}") from None
            location = r.headers.get("Location")
            if r.status_code in (301, 302, 303, 307, 308) and location:
                r.close()
                url = urllib.parse.urljoin(url, location)
                continue
            return r
        raise UpdateError("Troppi reindirizzamenti dal server degli aggiornamenti.")

    def find_latest(self, s=None):
        """version.json di download.germano.ai; se manca, l'elenco dei file della pagina di download."""
        s = s or self._session()
        base = source()[0]
        r = self._get(s, urllib.parse.urljoin(base, INDEX_FILE), timeout=15)
        if r.status_code == 200:
            try:
                release = parse_index(json.loads(r.content.decode("utf-8-sig")), base)
            except ValueError:
                release = None
            if release:
                return release
            ulog("version.json presente ma non leggibile: provo l'elenco della pagina di download.")
        r = self._get(s, base, timeout=15)
        if r.status_code != 200:
            raise UpdateError(f"download.germano.ai ha risposto con il codice {r.status_code}.")
        return parse_listing(r.text, base)

    # -------------------------------------------------------------- download
    def download(self, release):
        version = release["version"]
        if platform_key() != "windows":
            how = ("aprilo con un doppio clic" if platform_key() == "macos" else
                   f"installalo con un doppio clic oppure con: sudo apt install ./{release['name']}")
            raise UpdateError(f"È disponibile la versione {version}: scarica {release['name']} da {source()[0]} e "
                              f"{how}. Cartelle di lavoro, Vault e impostazioni restano intatti.")
        s = self._session()
        try:
            os.makedirs(UPDATE_DIR, exist_ok=True)
            free = shutil.disk_usage(UPDATE_DIR).free
        except OSError as e:
            raise UpdateError(f"La cartella degli aggiornamenti non è scrivibile: {e}") from None
        path = os.path.join(UPDATE_DIR, release["name"])
        part = path + ".part"
        self._set(state="downloading", progress={"done": 0, "total": release.get("size") or 0}, error=None)
        ulog(f"Download di {release['url']}...")
        r = self._get(s, release["url"], stream=True, timeout=60)
        if r.status_code != 200:
            r.close()
            raise UpdateError(f"Download non riuscito (codice {r.status_code}).")
        size = int(r.headers.get("Content-Length") or 0) or (release.get("size") or 0)
        if free < (size or SIZE_ESTIMATE) + INSTALL_SPACE:
            r.close()
            raise UpdateError(f"Spazio insufficiente: servono circa {((size or SIZE_ESTIMATE) + INSTALL_SPACE) / 1024 ** 3:.1f}"
                              " GB liberi per scaricare e installare l'aggiornamento.")
        done, last = 0, 0.0
        try:
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    if self.stop_event.is_set():
                        raise UpdateError("Download interrotto.")
                    f.write(chunk)
                    done += len(chunk)
                    if time.time() - last > 0.5:
                        last = time.time()
                        self._set(progress={"done": done, "total": size})
        except UpdateError:
            common.remove_quietly(part)
            raise
        except Exception as e:
            common.remove_quietly(part)
            raise UpdateError(f"Download interrotto: {e}") from None
        expected = release.get("size") or size
        if expected and done != expected:
            common.remove_quietly(part)
            raise UpdateError(f"Download incompleto ({done} byte su {expected}): riprova più tardi.")
        if not check_installer(part):
            common.remove_quietly(part)
            raise UpdateError("Il file scaricato non è un installer di Germano AI completo: riprova più tardi.")
        os.replace(part, path)
        common.atomic_write_json(READY_FILE, {"version": version, "installer": path, "downloaded": time.time(),
                                              "attempts": 0})
        common.remove_quietly(RESULT_FILE)   # l'esito di un tentativo precedente non vale per il nuovo download
        self._set(state="ready", progress=None, latest=version, available=True, attempts=0)
        ulog(f"Installer {release['name']} scaricato ({done} byte): pronto per l'installazione.")

    # -------------------------------------------------------------- installazione
    def launch_install(self):
        """Avvia l'installer scaricato in modalità aggiornamento e restituisce subito: l'installer chiude Germano,
        lo aggiorna e lo riapre."""
        ready = read_ready()
        if not ready:
            raise UpdateError("Nessun aggiornamento pronto da installare.")
        ready["attempts"] = int(ready.get("attempts") or 0) + 1
        ready["launched"] = time.time()
        common.atomic_write_json(READY_FILE, ready)
        common.remove_quietly(RESULT_FILE)
        args = [ready["installer"], "--update", "--result", RESULT_FILE]
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(args, cwd=UPDATE_DIR, creationflags=flags, close_fds=True)
        self._set(state="installing", progress=None, attempts=ready["attempts"])
        ulog(f"Installazione della versione {ready['version']} avviata (tentativo {ready['attempts']}).")


def should_auto_install():
    """All'avvio: l'aggiornamento pronto si installa da solo, ma solo al primo tentativo (se un tentativo non è
    andato a buon fine si riprova dalla Dashboard, senza bloccare ogni avvio)."""
    ready = read_ready()
    return bool(ready) and int(ready.get("attempts") or 0) == 0


def cleanup_after_install():
    """All'avvio: elimina gli installer già usati o superati e i resti del meccanismo precedente alla 0.60."""
    for d in LEGACY_DIRS:
        shutil.rmtree(d, ignore_errors=True)
    for f in ("ready.json", "install_result.json", "update.log"):    # vecchia posizione accanto al programma
        legacy = os.path.join(common.BASE_DIR, "update", f)
        if os.path.normcase(legacy) != os.path.normcase(os.path.join(UPDATE_DIR, f)):
            common.remove_quietly(legacy)
    current = common.get_version()
    ready, result = read_ready(), last_result()
    if (ready and result and result.get("status") == "ok" and int(ready.get("attempts") or 0) >= 1
            and result.get("target") and result["target"] != ready.get("version")):
        # L'installer annunciato come nuova versione ne conteneva un'altra: si scarta (e non si riscarica da solo).
        common.atomic_write_json(REJECTED_FILE, {"version": ready["version"], "found": result["target"],
                                                 "time": time.time()})
        common.remove_quietly(ready["installer"])
        common.remove_quietly(READY_FILE)
        ulog(f"Scartato l'installer della versione {ready['version']}: conteneva la versione {result['target']}.")
    if not read_ready():
        common.remove_quietly(READY_FILE)
    if not read_rejected():
        common.remove_quietly(REJECTED_FILE)
    if not os.path.isdir(UPDATE_DIR):
        return
    for name in os.listdir(UPDATE_DIR):
        m = INSTALLER_RE.match(name[:-5] if name.endswith(".part") else name)
        if m and (name.endswith(".part") or not is_newer(m.group(1), current)):
            common.remove_quietly(os.path.join(UPDATE_DIR, name))


def acknowledge_install():
    common.remove_quietly(RESULT_FILE)
