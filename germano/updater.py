"""Aggiornamento automatico di Germano AI.

Unico riferimento: https://download.germano.ai, l'indirizzo ufficiale di download, che rimanda alla cartella
pubblica di Google Drive con i pacchetti. Solo se Windows segnala che il PC è connesso a Internet (Network List
Manager: lo stato già noto al sistema, nessuna connessione aperta da Germano per scoprirlo) l'indirizzo viene
seguito fino alla cartella, dove si cerca lo ZIP «GermanoAI_Release_v<versione>.zip» con la versione più alta.
Se è più recente di quella installata viene scaricato in update/ e controllato (download completo, impronta
SHA-256 se nella cartella c'è anche «<nome dello ZIP>.sha256», CRC di ogni file dello ZIP, VERSION uguale alla
versione del nome), poi estratto e preparato.

La sostituzione avviene a programma chiuso (germano/tools/update_install.py): al successivo avvio di START.bat
oppure subito con «Installa e riavvia». Vengono sostituiti solo i file del programma: cartelle di lavoro, Vault,
config.json e la cartella update/ restano intatti. La versione precedente resta in update/old finché la nuova
non si avvia; se l'installazione non riesce viene ripristinata.
"""
import hashlib
import html.parser
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import zipfile

from . import common

DOWNLOAD_PAGE = "https://download.germano.ai/"  # unico riferimento per le nuove versioni
FOLDER_VIEW_URL = "https://drive.google.com/embeddedfolderview?id={id}"  # elenco dei file di una cartella pubblica
FILE_DOWNLOAD_URL = "https://drive.usercontent.google.com/download?id={id}&export=download&confirm=t"
PACKAGE_RE = re.compile(r"^GermanoAI_Release_v(\d+(?:\.\d+)+(?:-[A-Za-z]+\d*)?)\.zip$", re.IGNORECASE)
MAX_REDIRECTS = 5
SIZE_ESTIMATE = 3.5 * 1024 ** 3  # se Google non indica la dimensione: stima prudente per lo spazio su disco
UPDATE_DIR = os.path.join(common.BASE_DIR, "update")
DOWNLOAD_DIR = os.path.join(UPDATE_DIR, "download")
NEW_DIR = os.path.join(UPDATE_DIR, "new")
OLD_DIR = os.path.join(UPDATE_DIR, "old")
INSTALLER_DIR = os.path.join(UPDATE_DIR, "installer")
READY_FILE = os.path.join(UPDATE_DIR, "ready.json")
RESULT_FILE = os.path.join(UPDATE_DIR, "install_result.json")
LOG_FILE = os.path.join(UPDATE_DIR, "update.log")
FIRST_CHECK_DELAY = 20          # secondi dopo l'avvio
CHECK_INTERVAL = 6 * 3600       # controllo periodico
SITE_HOSTS = ("germano.ai",)
DOWNLOAD_HOSTS = ("google.com", "googleusercontent.com")
REQUIRE_HTTPS = True
REQUIRED_FILES = ("START.bat", "server.py", "daemon.py", "VERSION", os.path.join("runtime", "python.exe"),
                  os.path.join("germano", "__init__.py"))
NLM_CLSID = "{DCB00C01-570F-4A9B-8D69-199FDBA5723B}"  # Network List Manager di Windows


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


def drive_folder_id(url):
    """ID della cartella da un indirizzo di Google Drive (.../drive/folders/ID, anche .../drive/u/0/folders/ID)."""
    m = re.search(r"/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]{10,})", url or "")
    return m.group(1) if m else None


def drive_download_url(file_id):
    return FILE_DOWNLOAD_URL.format(id=urllib.parse.quote(file_id))


class _FolderParser(html.parser.HTMLParser):
    """File elencati nella vista incorporata di una cartella pubblica di Google Drive: (id, nome)."""

    def __init__(self):
        super().__init__()
        self.files = []
        self._id = None
        self._title = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "div" and "flip-entry" in classes and (a.get("id") or "").startswith("entry-"):
            self._id = a["id"][len("entry-"):]
        elif tag == "a" and self._id is None:
            m = re.search(r"/file/d/([A-Za-z0-9_-]{10,})", a.get("href") or "")
            if m:
                self._id = m.group(1)
        elif tag == "div" and "flip-entry-title" in classes and self._id:
            self._title = []

    def handle_data(self, data):
        if self._title is not None:
            self._title.append(data)

    def handle_endtag(self, tag):
        if tag == "div" and self._title is not None:
            self.files.append((self._id, "".join(self._title).strip()))
            self._id = self._title = None


def parse_drive_folder(page):
    p = _FolderParser()
    try:
        p.feed(page)
    except Exception:
        return []
    return [(fid, name) for fid, name in p.files if fid and name]


def pick_latest(files):
    """Pacchetto con la versione più alta tra i file della cartella, con l'eventuale file .sha256 abbinato."""
    best = None
    for fid, name in files:
        m = PACKAGE_RE.match(name)
        key = parse_version(m.group(1)) if m else None
        if key and (best is None or key > best[0]):
            best = (key, m.group(1), fid, name)
    if not best:
        return None
    by_name = {name.lower(): fid for fid, name in files}
    return {"version": best[1], "file_id": best[2], "name": best[3],
            "sha256_file_id": by_name.get(best[3].lower() + ".sha256")}


class _FormParser(html.parser.HTMLParser):
    """Raccoglie i moduli della pagina di conferma di Google Drive ("impossibile analizzare il file")."""

    def __init__(self):
        super().__init__()
        self.forms = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.forms.append({"action": a.get("action") or "", "id": a.get("id") or "", "fields": {}})
        elif tag == "input" and self.forms and a.get("name") and (a.get("type") or "").lower() == "hidden":
            self.forms[-1]["fields"][a["name"]] = a.get("value") or ""


def drive_confirm_url(page):
    """Indirizzo di download dal modulo di conferma che Google Drive mostra per i file grandi."""
    p = _FormParser()
    try:
        p.feed(page)
    except Exception:
        return None
    for form in sorted(p.forms, key=lambda f: f["id"] != "download-form"):
        action, fields = form["action"], form["fields"]
        looks_like_download = form["id"] == "download-form" or "download" in action or (
            "id" in fields and ("confirm" in fields or "export" in fields))
        if action and fields and looks_like_download:
            return action + ("&" if "?" in action else "?") + urllib.parse.urlencode(fields)
    return None


def _host_ok(url, hosts):
    parsed = urllib.parse.urlparse(url)
    if REQUIRE_HTTPS and parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in hosts)


def _allowed_host(url):
    """Indirizzi da cui si accettano elenco della cartella e file: solo Google, solo HTTPS."""
    return _host_ok(url, DOWNLOAD_HOSTS)


def find_package_root(base):
    """Cartella dell'aggiornamento estratto che contiene START.bat (direttamente o un livello sotto)."""
    if os.path.isfile(os.path.join(base, "START.bat")):
        return base
    dirs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))] if os.path.isdir(base) else []
    for d in dirs:
        if os.path.isfile(os.path.join(base, d, "START.bat")):
            return os.path.join(base, d)
    return None


def validate_package(root, version):
    missing = [f for f in REQUIRED_FILES if not os.path.isfile(os.path.join(root, f))]
    if missing:
        raise UpdateError("Pacchetto di aggiornamento incompleto: mancano " + ", ".join(missing))
    with open(os.path.join(root, "VERSION"), encoding="utf-8-sig") as f:
        found = f.read().strip()
    if found != version:
        raise UpdateError(f"Il pacchetto scaricato contiene la versione {found} invece di {version}.")


def read_ready():
    data = common.read_json(READY_FILE, None)
    if not isinstance(data, dict) or not data.get("root") or not os.path.isfile(os.path.join(data["root"], "START.bat")):
        return None
    return data


# ------------------------------------------------------------------------------------------------ servizio
class Updater:
    """Controllo, download e preparazione degli aggiornamenti (vive nel processo del server)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.check_now = threading.Event()
        self.worker = None
        self.state = {"state": "idle", "current": common.get_version(), "latest": None, "available": False,
                      "online": None, "checked_at": None, "error": None, "progress": None, "notes": None}
        ready = read_ready()
        if ready:
            self.state.update(state="ready", latest=ready.get("version"), available=True)

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)

    def snapshot(self):
        with self.lock:
            snap = dict(self.state)
        result = common.read_json(RESULT_FILE, None)
        if isinstance(result, dict):
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
        return self.state.get("state") in ("checking", "downloading", "verifying", "extracting", "installing")

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
        self._set(checked_at=time.time(), latest=latest["version"] if latest else common.get_version(), notes=None)
        if not latest or not is_newer(latest["version"], common.get_version()):
            self._set(state="uptodate", available=False)
            return self.snapshot()
        self._set(state="available", available=True)
        ulog(f"Disponibile la versione {latest['version']} (installata {common.get_version()}): {latest['name']}.")
        if auto_download:
            self.download(latest)
        return self.snapshot()

    @staticmethod
    def _session():
        import requests
        s = requests.Session()
        s.headers["User-Agent"] = f"GermanoAI-Updater/{common.get_version()}"
        return s

    def find_latest(self, s=None):
        """Segue download.germano.ai fino alla cartella di Google Drive e vi cerca il pacchetto più recente.
        Restituisce None se nella cartella non c'è nessun pacchetto di Germano AI."""
        s = s or self._session()
        url, folder = DOWNLOAD_PAGE, None
        for _ in range(MAX_REDIRECTS):
            try:
                r = s.get(url, allow_redirects=False, timeout=15, stream=True)
                r.close()
            except Exception as e:
                raise UpdateError(f"download.germano.ai non raggiungibile: {e}") from None
            location = r.headers.get("Location")
            if r.status_code not in (301, 302, 303, 307, 308) or not location:
                break
            url = urllib.parse.urljoin(url, location)
            if not (_host_ok(url, SITE_HOSTS) or _allowed_host(url)):
                raise UpdateError("download.germano.ai rimanda a un indirizzo non previsto "
                                  f"({urllib.parse.urlparse(url).hostname}).")
            folder = drive_folder_id(url) if _allowed_host(url) else None
            if folder:
                break
        if not folder:
            raise UpdateError("download.germano.ai non rimanda a una cartella di Google Drive.")
        try:
            r = s.get(FOLDER_VIEW_URL.format(id=folder), timeout=20)
        except Exception as e:
            raise UpdateError(f"Google Drive non raggiungibile: {e}") from None
        if r.status_code != 200 or not _allowed_host(r.url):
            raise UpdateError(f"La cartella di download non è accessibile (codice {r.status_code}): "
                              "deve essere condivisa con «Chiunque abbia il link».")
        latest = pick_latest(parse_drive_folder(r.text))
        if latest:
            latest["download_url"] = drive_download_url(latest["file_id"])
        return latest

    def _published_sha256(self, s, release):
        """Impronta dal file «<nome dello ZIP>.sha256» della cartella, se presente."""
        if not release.get("sha256_file_id"):
            return None
        try:
            r = s.get(drive_download_url(release["sha256_file_id"]), timeout=30)
        except Exception as e:
            raise UpdateError(f"Impronta SHA-256 non scaricabile: {e}") from None
        m = re.search(r"\b([0-9a-fA-F]{64})\b", r.text[:4096]) if r.status_code == 200 and _allowed_host(r.url) else None
        if not m:
            raise UpdateError(f"Il file {release['name']}.sha256 della cartella di download non contiene "
                              "un'impronta SHA-256 valida.")
        return m.group(1).lower()

    # -------------------------------------------------------------- download e preparazione
    def download(self, release):
        version = release["version"]
        s = self._session()
        try:
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            free = shutil.disk_usage(UPDATE_DIR).free
        except OSError as e:
            raise UpdateError(f"La cartella del programma non è scrivibile: {e}") from None
        expected = self._published_sha256(s, release)
        zip_path = os.path.join(DOWNLOAD_DIR, f"GermanoAI_{version}.zip")
        part = zip_path + ".part"
        self._set(state="downloading", progress={"done": 0, "total": 0}, error=None)
        ulog(f"Download di {release['name']} dalla cartella di download (download.germano.ai)...")
        r = s.get(release["download_url"], stream=True, timeout=60)
        if "text/html" in (r.headers.get("Content-Type") or ""):
            url2 = drive_confirm_url(r.text)
            if not url2 or not _allowed_host(url2):
                raise UpdateError("Google Drive non ha fornito il file: la cartella deve essere condivisa con "
                                  "«Chiunque abbia il link» (oppure è stato superato il limite di download).")
            r = s.get(url2, stream=True, timeout=60)
            if "text/html" in (r.headers.get("Content-Type") or ""):
                raise UpdateError("Google Drive ha restituito una pagina invece del file: riprova più tardi.")
        if r.status_code != 200 or not _allowed_host(r.url):
            raise UpdateError(f"Download non riuscito (codice {r.status_code}).")
        size = int(r.headers.get("Content-Length") or 0)
        if free < (size or SIZE_ESTIMATE) * 2.6:
            r.close()
            raise UpdateError(f"Spazio insufficiente: servono circa {(size or SIZE_ESTIMATE) * 2.6 / 1024 ** 3:.1f} GB "
                              "liberi per scaricare e preparare l'aggiornamento.")
        h = hashlib.sha256()
        done = 0
        last = 0.0
        with open(part, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                if self.stop_event.is_set():
                    raise UpdateError("Download interrotto.")
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if time.time() - last > 0.5:
                    last = time.time()
                    self._set(progress={"done": done, "total": size})
        self._set(state="verifying", progress={"done": done, "total": size})
        if size and done != size:
            common.remove_quietly(part)
            raise UpdateError(f"Download incompleto ({done} byte su {size}): riprova più tardi.")
        if expected and h.hexdigest() != expected:
            common.remove_quietly(part)
            raise UpdateError("Il file scaricato non corrisponde all'originale pubblicato (impronta SHA-256 "
                              "diversa): è stato scartato.")
        os.replace(part, zip_path)
        ulog(f"Download completato ({done} byte, SHA-256 {h.hexdigest()}"
             + (", uguale a quella pubblicata)." if expected else ")."))
        self.prepare(zip_path, version)

    def prepare(self, zip_path, version):
        self._set(state="extracting", progress={"done": 0, "total": 1})
        shutil.rmtree(NEW_DIR, ignore_errors=True)
        os.makedirs(NEW_DIR, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path) as z:
                members = z.infolist()
                total = sum(m.file_size for m in members) or 1
                done = 0
                last = 0.0
                for m in members:
                    if self.stop_event.is_set():
                        raise UpdateError("Preparazione interrotta.")
                    z.extract(m, NEW_DIR)  # zipfile ignora percorsi assoluti e ".." e controlla il CRC di ogni file
                    done += m.file_size
                    if time.time() - last > 0.5:
                        last = time.time()
                        self._set(progress={"done": done, "total": total})
        except (zipfile.BadZipFile, EOFError) as e:
            common.remove_quietly(zip_path)
            shutil.rmtree(NEW_DIR, ignore_errors=True)
            raise UpdateError(f"Lo ZIP scaricato è danneggiato ({e}): è stato scartato.") from None
        root = find_package_root(NEW_DIR)
        if not root:
            raise UpdateError("Lo ZIP scaricato non contiene Germano AI (START.bat non trovato).")
        validate_package(root, version)
        common.atomic_write_json(READY_FILE, {"version": version, "root": root, "prepared": time.time()})
        common.remove_quietly(zip_path)  # libera spazio: resta solo la copia estratta
        self._set(state="ready", progress=None, latest=version, available=True)
        ulog(f"Versione {version} pronta per l'installazione.")

    # -------------------------------------------------------------- installazione
    def launch_install(self, wait_pids, restart=True, dry_run=False):
        """Avvia l'installazione in un processo separato, con un interprete Python minimo copiato in
        update/installer (la cartella runtime viene sostituita) e restituisce subito."""
        ready = read_ready()
        if not ready:
            raise UpdateError("Nessun aggiornamento pronto da installare.")
        shutil.rmtree(INSTALLER_DIR, ignore_errors=True)
        os.makedirs(INSTALLER_DIR)
        runtime = os.path.dirname(sys.executable)
        stdlib = None
        for name in os.listdir(runtime):
            low = name.lower()
            if low in ("python.exe", "python3.dll") or (low.endswith(".dll") and low.startswith(("python3", "vcruntime"))):
                shutil.copy2(os.path.join(runtime, name), INSTALLER_DIR)
            elif low.startswith("python3") and low.endswith(".zip"):
                shutil.copy2(os.path.join(runtime, name), INSTALLER_DIR)
                stdlib = name
        if not stdlib:
            raise UpdateError("Libreria standard di Python non trovata nel runtime.")
        with open(os.path.join(INSTALLER_DIR, stdlib[:-4] + "._pth"), "w", encoding="ascii") as f:
            f.write(f"{stdlib}\n.\n")
        shutil.copy2(os.path.join(common.BASE_DIR, "germano", "tools", "update_install.py"), INSTALLER_DIR)
        args = [os.path.join(INSTALLER_DIR, "python.exe"), "-I", os.path.join(INSTALLER_DIR, "update_install.py"),
                "--app", common.BASE_DIR, "--source", ready["root"], "--version", ready["version"],
                "--from-version", common.get_version(), "--wait", ",".join(str(p) for p in wait_pids if p)]
        if restart:
            args.append("--restart")
        if dry_run:
            args.append("--dry-run")
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(args, cwd=UPDATE_DIR, creationflags=flags, close_fds=True)
        self._set(state="installing", progress=None)
        ulog(f"Installazione della versione {ready['version']} avviata (attesa dei processi {wait_pids}).")


def cleanup_after_install():
    """All'avvio: se l'ultima installazione è riuscita e questa è la nuova versione, elimina la copia di
    sicurezza della versione precedente e l'interprete temporaneo."""
    result = common.read_json(RESULT_FILE, None)
    if not isinstance(result, dict):
        return
    if result.get("status") == "ok" and result.get("to") == common.get_version():
        for d in (OLD_DIR, INSTALLER_DIR, NEW_DIR):
            shutil.rmtree(d, ignore_errors=True)


def acknowledge_install():
    common.remove_quietly(RESULT_FILE)
