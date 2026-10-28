"""Germano AI v0.60 - launcher come APPLICAZIONE DESKTOP (niente finestra nera di console, niente browser con barra URL).

NON cambia l'architettura: avvia lo stesso server Flask (server.py) o il pannello del client (client_ui.py) in un
sottoprocesso, attende che sia pronto e apre l'interfaccia in una FINESTRA DEDICATA, con la X rossa e titolo/icona
propri. Alla chiusura della finestra TUTTO si chiude: finestra, server Flask e demone IA (solo l'albero dei NOSTRI
sottoprocessi, senza toccare altri processi del sistema). La finestra:
- Windows: Microsoft Edge (presente in Windows 10/11 e in Windows Server 2022/2025 con Esperienza desktop; su Windows
  Server 2019 va installato) o Google Chrome, in modalità applicazione `--app`;
- macOS: finestra nativa con il WebKit di sistema (pywebview + PyObjC, inclusi nel programma), nello stesso processo
  dell'app, così nel Dock compare Germano;
- Linux: finestra Qt WebEngine (pywebview + PySide6, inclusi nel programma) in un processo separato (germano_window.py);
- ripiego, se la finestra dedicata non si può aprire: un browser Chromium in modalità app, altrimenti il browser
  predefinito (Linux, macOS). Su Windows senza Edge né Chrome (es. Windows Server 2019, Server Core) Germano NON apre
  Internet Explorer, che non sa mostrare la Dashboard: resta attivo come server senza finestra e spiega dove collegarsi.

SERVER SENZA FINESTRA (Windows Server, macchine virtuali, avvio come attività pianificata): `--no-browser` (o
`--headless`, o GERMANO_HEADLESS=1) avvia server e motore senza aprire finestre né messaggi e scrive nel registro (e
nella console, se c'è) gli indirizzi locali e di rete; resta attivo finché non si esegue `--stop` (o Ctrl+C).

UN SOLO LANCIATORE PER TUTTI I PACCHETTI (Germano.exe / Germano.app / germano.sh): la suite completa (contiene
server.py) apre la Dashboard unificata (Standalone, Server LAN, Client); il client leggero apre il pannello del client.

CARTELLE (dalla 0.60):
- Programma installato (installer Windows, pacchetto .deb o .pkg: c'e' germano_install.json accanto al programma):
  i dati di lavoro (input, output, processed, failed, extracted con il Vault, config.json) stanno nella cartella dati
  indicata li', o in mancanza in «Documenti/Germano AI»; i file tecnici (profilo della finestra, registri, cache,
  aggiornamenti scaricati) nella cartella tecnica dell'utente (%LOCALAPPDATA%\\Germano AI, ~/Library/Application
  Support/Germano AI, ~/.local/state/germano). Nessuna scrittura nella cartella del programma per dati e cache.
- Copia portatile (sorgenti, senza installazione): i dati restano accanto al programma, come nelle versioni
  precedenti; se la cartella del programma non e' scrivibile si usano le cartelle dell'utente.

Uso: germano_desktop.py [auto|server|client] [--no-browser | --headless] [--stop] [--uninstall [--silent]]
     (Germano.exe accetta le stesse opzioni; GERMANO_DATA_DIR e GERMANO_TECH_DIR scelgono cartella dati e tecnica)
"""
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
APP_DIR = os.environ.get("GERMANO_APP_DIR") or os.path.dirname(os.path.abspath(__file__))
ARGS = sys.argv[1:]
_ROLE_ARG = (ARGS[0] if ARGS and not ARGS[0].startswith("--") else os.environ.get("GERMANO_DESKTOP_ROLE") or "auto").lower()
FLAGS = [a for a in ARGS if a.startswith("--")]
# Senza finestra: Windows Server (anche Server Core), macchine virtuali, attività pianificate, servizi
HEADLESS = bool({"--no-browser", "--headless"} & set(FLAGS)) or os.environ.get("GERMANO_HEADLESS") == "1"
_MODE_FLAG = next((a.split("=", 1)[1].strip().lower() for a in FLAGS if a.startswith("--mode=")), "")
if _ROLE_ARG in ("server", "client"):
    ROLE = _ROLE_ARG
else:   # auto: suite completa se c'e' server.py, altrimenti pacchetto client leggero
    ROLE = "server" if os.path.isfile(os.path.join(APP_DIR, "server.py")) else "client"
IS_CLIENT = ROLE == "client"
PRODUCT = "Germano AI Client" if IS_CLIENT else "Germano AI"
SLUG = "germano-client" if IS_CLIENT else "germano"
DATA_FOLDER_NAME = "Germano AI"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_BROWSER_NAMES = {"msedge.exe", "chrome.exe", "brave.exe", "chromium.exe", "msedge", "chrome", "chromium",
                  "chromium-browser", "brave", "brave-browser", "google chrome", "microsoft edge", "google-chrome"}
UPDATE_EXIT_CODE = 10   # il server esce con 10 quando lascia il posto all'installazione di un aggiornamento


# ---------------------------------------------------------------------------------------------- cartelle utente
def _documents_dir():
    """Cartella Documenti reale dell'utente (anche se rinominata, tradotta o reindirizzata)."""
    if IS_WIN:
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
            g = GUID()
            ctypes.oledll.ole32.CLSIDFromString("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}", ctypes.byref(g))
            p = ctypes.c_wchar_p()
            ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p))
            path = p.value
            ctypes.windll.ole32.CoTaskMemFree(p)
            if path:
                return path
        except Exception:
            pass
        return os.path.join(os.path.expanduser("~"), "Documents")
    if not IS_MAC:
        try:
            out = subprocess.run(["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True, timeout=5).stdout.strip()
            if out and os.path.isdir(out) and os.path.abspath(out) != os.path.expanduser("~"):
                return out
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def _in_cloud_sync(path):
    """True se il percorso e' sincronizzato con un servizio cloud (OneDrive; iCloud «Scrivania e Documenti»): i
    documenti originali e il Vault (dati in chiaro) non devono finire nel cloud."""
    p = os.path.normcase(os.path.abspath(path))
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        root = os.environ.get(var)
        if root and p.startswith(os.path.normcase(os.path.abspath(root)) + os.sep):
            return True
    if IS_MAC and p == os.path.join(os.path.expanduser("~"), "Documents"):
        return os.path.isdir(os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Documents"))
    return False


def default_data_dir():
    docs = _documents_dir()
    if _in_cloud_sync(docs):
        return os.path.join(os.path.expanduser("~"), DATA_FOLDER_NAME)
    return os.path.join(docs, DATA_FOLDER_NAME)


def default_tech_dir():
    """Cartella tecnica dell'utente (profilo della finestra, registri, cache, aggiornamenti scaricati)."""
    if IS_WIN:
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), PRODUCT)
    if IS_MAC:
        return os.path.join(os.path.expanduser("~/Library/Application Support"), PRODUCT)
    return os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), SLUG)


def _writable(folder):
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, f".germano_scrittura_{os.getpid()}")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _install_info():
    try:
        with open(os.path.join(APP_DIR, "germano_install.json"), encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


INSTALL = _install_info()      # presente = programma installato (installer Windows, .deb, .pkg)
if os.environ.get("GERMANO_DATA_DIR"):
    DATA_DIR = os.environ["GERMANO_DATA_DIR"]
elif INSTALL:
    DATA_DIR = INSTALL.get("data_dir") or (default_tech_dir() if IS_CLIENT else default_data_dir())
elif _writable(APP_DIR):
    DATA_DIR = APP_DIR                      # copia portatile, come nelle versioni precedenti
else:
    DATA_DIR = default_data_dir()           # programma in una cartella protetta senza installer
PORTABLE = not INSTALL and os.path.normcase(os.path.abspath(DATA_DIR)) == os.path.normcase(os.path.abspath(APP_DIR))
TECH_DIR = os.path.join(DATA_DIR, "state") if PORTABLE else (
    os.environ.get("GERMANO_TECH_DIR") or INSTALL.get("tech_dir") or default_tech_dir())
WEBVIEW_PROFILE = os.path.join(TECH_DIR, "webview_client" if IS_CLIENT else "webview")
LOG = os.path.join(DATA_DIR if PORTABLE else TECH_DIR, "desktop.log")
SERVER_LOG = os.path.join(DATA_DIR if PORTABLE else TECH_DIR, "server_stdout.log")
HEADLESS_FILE = os.path.join(TECH_DIR, "headless.json")      # Germano senza finestra in esecuzione (per --stop)
STOP_REQUEST = os.path.join(TECH_DIR, "headless.stop")       # scritto da --stop: il Germano senza finestra si chiude


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _lang_it():
    if IS_WIN:
        try:
            import ctypes
            return (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x10
        except Exception:
            return True
    return (os.environ.get("LANG") or os.environ.get("LC_ALL") or "it").lower().startswith("it")


def T(it, en):
    return it if _lang_it() else en


def _announce(lines):
    """Righe per l'amministratore: sempre nel registro, e nella console se Germano e' stato avviato da una console
    (python.exe; con pythonw/Germano.exe non c'e' console)."""
    for line in lines:
        log(line)
        try:
            if sys.stdout is not None:
                print(line, flush=True)
        except Exception:
            pass


def _message(text, flags=0x10):
    """Avviso all'utente senza console (Windows: finestra di messaggio; macOS: dialogo; Linux: zenity se c'e').
    Senza finestra (--no-browser) nessun dialogo: potrebbe non esserci nessuno a chiuderlo (servizio, sessione 0)."""
    if HEADLESS:
        _announce([text])
        return
    log(text)
    try:
        if IS_WIN:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, "Germano AI", flags | 0x10000)
        elif IS_MAC:
            safe = text.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(["osascript", "-e", f'display dialog "{safe}" buttons {{"OK"}} with title "Germano AI"'],
                           timeout=600)
        elif shutil.which("zenity"):
            subprocess.run(["zenity", "--error", "--title=Germano AI", "--width=480", f"--text={text}"], timeout=600)
    except Exception:
        pass


def _interpreter(windowless=False):
    if IS_WIN:
        pyw = os.path.join(APP_DIR, "runtime", "pythonw.exe")
        py = os.path.join(APP_DIR, "runtime", "python.exe")
        if windowless and os.path.isfile(pyw):
            return pyw
        return py if os.path.isfile(py) else sys.executable
    if os.path.normcase(os.path.abspath(sys.executable)).startswith(os.path.normcase(APP_DIR) + os.sep):
        return sys.executable    # gia' l'interprete del programma (macOS: quello giusto per Apple Silicon o Intel)
    for c in (os.path.join(APP_DIR, "runtime", "bin", "python3"), os.path.join(APP_DIR, "runtime", "bin", "python")):
        if os.path.isfile(c):
            return c
    return sys.executable


def _has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _icon():
    for rel in (os.path.join("icons", "256.png"), os.path.join("static", "favicon.ico"), "favicon.ico"):
        p = os.path.join(APP_DIR, rel)
        if os.path.isfile(p):
            return p
    return ""


def _free_port(preferred):
    for port in (preferred, 0):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    return preferred


def _find_browser():
    env = os.environ.get("GERMANO_BROWSER")
    if env and os.path.isfile(env):
        return env
    cands = []
    if IS_WIN:
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        la = os.environ.get("LOCALAPPDATA", "")
        cands = [os.path.join(pf86, r"Microsoft\Edge\Application\msedge.exe"),
                 os.path.join(pf, r"Microsoft\Edge\Application\msedge.exe"),
                 os.path.join(la, r"Microsoft\Edge\Application\msedge.exe"),     # Edge installato per l'utente
                 os.path.join(pf, r"Google\Chrome\Application\chrome.exe"),
                 os.path.join(pf86, r"Google\Chrome\Application\chrome.exe"),
                 os.path.join(la, r"Google\Chrome\Application\chrome.exe")]
    elif IS_MAC:
        cands = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                 "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    else:
        for name in ("microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable",
                     "chromium", "chromium-browser", "brave-browser"):
            p = shutil.which(name)
            if p:
                cands.append(p)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    for name in ("msedge", "chrome", "chromium", "brave"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _wait_server(port, proc, timeout=180):
    end = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/status"
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            with _OPENER.open(url, timeout=5) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.4)
    return False


def _browser_procs(psutil):
    needle = f"--user-data-dir={WEBVIEW_PROFILE}".lower()
    found = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() in _BROWSER_NAMES and needle in " ".join(p.info["cmdline"] or []).lower():
                found.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def _close_window(psutil):
    """Chiude la NOSTRA finestra (i processi del browser che usano il profilo dedicato di Germano)."""
    procs = _browser_procs(psutil)
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    psutil.wait_procs(procs, timeout=5)


def _terminate_tree(psutil, proc):
    try:
        parent = psutil.Process(proc.pid)
    except psutil.NoSuchProcess:
        return
    procs = []
    try:
        procs = parent.children(recursive=True)
    except psutil.Error:
        pass
    procs.append(parent)
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(procs, timeout=8)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass


def _stop_server_http(port):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/stop", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        _OPENER.open(req, timeout=20).read()
    except OSError:
        pass


def _prepare_data_dir():
    """Cartelle di lavoro pronte (anche se l'utente le avesse cancellate); 'state' nascosta, e' solo tecnica."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if IS_CLIENT or PORTABLE:
        return
    for name in ("input", "output", "processed", "failed", "extracted"):
        os.makedirs(os.path.join(DATA_DIR, name), exist_ok=True)
    state = os.path.join(DATA_DIR, "state")
    os.makedirs(state, exist_ok=True)
    try:
        if IS_WIN:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(state, 0x2)   # FILE_ATTRIBUTE_HIDDEN
        elif IS_MAC:
            subprocess.run(["chflags", "hidden", state], timeout=10)
    except Exception:
        pass


def _uninstall():
    """--uninstall. Windows: passa la mano al disinstallatore dell'installer (germano_install.py) e termina subito,
    cosi' la cartella del programma resta libera. macOS e Linux: la disinstallazione e' quella del sistema."""
    if not IS_WIN:
        _message("Per disinstallare Germano AI: su macOS trascina Germano nel Cestino dalla cartella Applicazioni; su "
                 "Linux usa «sudo apt remove germano-ai» (client: germano-ai-client). Le cartelle di lavoro in "
                 "Documenti/Germano AI restano dove sono.", 0x40)
        return 0
    script = os.path.join(APP_DIR, "germano_install.py")
    if not os.path.isfile(script):
        _message("Disinstallazione non disponibile: questa copia di Germano non è stata installata con l'installer.")
        return 1
    subprocess.Popen([_interpreter(windowless=True), "-B", script, "uninstall"] + [f for f in FLAGS if f != "--uninstall"],
                     cwd=os.path.dirname(APP_DIR) or None, close_fds=True,
                     creationflags=NO_WINDOW | 0x00000008)   # DETACHED_PROCESS
    return 0


# ------------------------------------------------------------------------------------------------- finestre
def _window_inprocess(url, srv):
    """macOS: finestra nativa (WebKit) nello stesso processo. None = non disponibile (si ripiega sul browser),
    altrimenti True se il server ha lasciato il posto a un aggiornamento."""
    try:
        sys.path.insert(0, APP_DIR)
        import germano_window
    except Exception as e:
        log(f"finestra nativa non disponibile ({type(e).__name__}: {e}): ripiego sul browser.")
        return None
    state = {"shown": False, "closed": False, "update": False}

    def watchdog(window):     # il server si e' fermato (aggiornamento o errore): si chiude anche la finestra
        while not state["closed"]:
            rc = srv.poll()
            if rc is not None:
                state["update"] = rc == UPDATE_EXIT_CODE
                log("il server lascia il posto all'aggiornamento: chiudo la finestra." if state["update"] else
                    f"il server si è chiuso (codice {rc}): chiudo la finestra.")
                try:
                    window.destroy()
                except Exception:
                    pass
                return
            time.sleep(1.0)

    def shown():
        state["shown"] = True
        log("finestra dell'app aperta (WebKit).")
    try:
        germano_window.run_window(url, PRODUCT, _icon(), WEBVIEW_PROFILE, "cocoa", watchdog=watchdog, on_shown=shown)
    except Exception as e:
        log(f"finestra nativa non riuscita ({type(e).__name__}: {e}).")
        if not state["shown"]:
            return None
    state["closed"] = True
    if not state["update"]:
        log("finestra chiusa (X rossa): spengo server e demone.")
    return state["update"]


def _window_helper(url, srv):
    """Linux: finestra Qt WebEngine in un processo separato. None = non disponibile (si ripiega sul browser),
    altrimenti True se il server ha lasciato il posto a un aggiornamento."""
    helper = os.path.join(APP_DIR, "germano_window.py")
    if not (os.path.isfile(helper) and _has_module("webview") and _has_module("PySide6")):
        return None
    env = dict(os.environ, GERMANO_WEBVIEW_STORAGE=WEBVIEW_PROFILE, QT_API="pyside6")
    proc = subprocess.Popen([_interpreter(), helper, url, PRODUCT, _icon()], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env, start_new_session=True)
    ready, lines = threading.Event(), []

    def reader():
        for line in proc.stdout:
            lines.append(line.strip())
            if line.strip() == "pronto":
                ready.set()
    threading.Thread(target=reader, daemon=True).start()
    end = time.time() + 90           # il primo avvio di Qt WebEngine puo' essere lento
    while not ready.is_set():
        if proc.poll() is not None or time.time() > end:
            log(f"finestra Qt non disponibile ({' | '.join(lines[-3:]) or 'nessun dettaglio'}): ripiego sul browser.")
            try:
                proc.kill()
            except OSError:
                pass
            return None
        time.sleep(0.2)
    log("finestra dell'app aperta (Qt WebEngine).")
    while True:
        if proc.poll() is not None:
            log("finestra chiusa (X rossa): spengo server e demone.")
            return False
        rc = srv.poll()
        if rc is not None:
            update = rc == UPDATE_EXIT_CODE
            log("il server lascia il posto all'aggiornamento: chiudo la finestra." if update else
                f"il server si è chiuso (codice {rc}): chiudo la finestra.")
            proc.terminate()
            return update
        time.sleep(1.0)


def _window_browser(url, srv, psutil):
    """Windows (Edge) e ripiego altrove: browser Chromium in modalita' app con un profilo dedicato, o il browser
    predefinito. Restituisce True se il server ha lasciato il posto a un aggiornamento; None su Windows se la finestra
    non si puo' aprire (nessun Edge/Chrome, oppure il browser non si e' aperto: criteri aziendali, Server Core)."""
    browser = _find_browser()
    if not browser:
        if IS_WIN:      # Windows Server 2019 / Server Core: c'e' al massimo Internet Explorer, che non va usato
            log("nessun Microsoft Edge o Google Chrome trovato.")
            return None
        log("nessun browser Chromium trovato: apro il browser predefinito.")
        import webbrowser
        webbrowser.open(url)
        return srv.wait() == UPDATE_EXIT_CODE
    os.makedirs(WEBVIEW_PROFILE, exist_ok=True)
    args = [browser, f"--app={url}", f"--user-data-dir={WEBVIEW_PROFILE}",
            "--no-first-run", "--no-default-browser-check", "--disable-sync",
            "--disable-background-networking", "--disable-component-update", "--disable-extensions",
            "--disable-session-crashed-bubble", "--hide-crash-restore-bubble", "--noerrdialogs",
            "--window-size=1280,860", f"--window-name={PRODUCT}"]
    dbg = os.environ.get("GERMANO_WEBVIEW_DEBUG_PORT")
    if dbg:
        args.append(f"--remote-debugging-port={dbg}")
    log(f"apro la finestra app: {browser} --app={url}")
    subprocess.Popen(args, **({"creationflags": NO_WINDOW} if IS_WIN else {"start_new_session": True}))
    end = time.time() + 25           # il primo avvio di Edge (profilo nuovo) puo' richiedere qualche secondo
    while not _browser_procs(psutil):
        if time.time() > end:
            log(f"la finestra di {os.path.basename(browser)} non si e' aperta.")
            if IS_WIN:
                return None
            import webbrowser
            webbrowser.open(url)
            return srv.wait() == UPDATE_EXIT_CODE
        if srv.poll() is not None:
            return srv.returncode == UPDATE_EXIT_CODE
        time.sleep(0.5)
    time.sleep(1.0)
    while True:          # finche' la finestra e' aperta e il server e' vivo, si resta qui
        if not _browser_procs(psutil):
            log("finestra chiusa (X rossa): spengo server e demone.")
            return False
        rc = srv.poll()
        if rc is not None:
            update = rc == UPDATE_EXIT_CODE
            log("il server lascia il posto all'aggiornamento: chiudo la finestra." if update else
                f"il server si è chiuso (codice {rc}): chiudo la finestra.")
            _close_window(psutil)
            return update
        time.sleep(1.0)


# ------------------------------------------------------------------------------------- senza finestra (server)
def _addresses(port):
    """Indirizzi da comunicare: la Dashboard su questo computer e, se la parte Server e' in ascolto, il Remote
    Control e il Proxy per i computer della rete (anche dietro schede di rete virtuali)."""
    lines = [T(f"Dashboard su questo computer:   http://127.0.0.1:{port}/",
               f"Dashboard on this computer:     http://127.0.0.1:{port}/")]
    st, end = {}, time.time() + 15
    while True:
        try:
            with _OPENER.open(f"http://127.0.0.1:{port}/api/mode", timeout=15) as r:
                st = json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError):
            return lines
        s = st.get("server") or {}
        # controllo di reti e firewall ancora in corso (circa 2 s dopo l'ascolto in rete): si aspetta un poco
        if not (s.get("listening") and s.get("network_warnings") is None) or time.time() > end:
            break
        time.sleep(1.0)
    s = st.get("server") or {}
    if s.get("listening"):
        p = s.get("port") or port
        for ip in s.get("ips") or []:
            lines.append(T(f"Remote Control dalla rete:      http://{ip}:{p}/remote   (Proxy per le CLI: http://{ip}:{p}/v1)",
                           f"Remote Control from the network: http://{ip}:{p}/remote   (Proxy for CLIs: http://{ip}:{p}/v1)"))
        for w in s.get("network_warnings") or []:
            lines.append(T("ATTENZIONE: ", "WARNING: ") + T(w.get("it", ""), w.get("en", ""))
                         + (f" {w['command']}" if w.get("command") else ""))
    elif not IS_CLIENT:
        lines.append(T("Accesso dalla rete spento (modalità Standalone): per offrirlo ai computer della rete scegli la "
                       "modalità Server nelle Impostazioni, oppure avvia con --mode=server.",
                       "Network access off (Standalone mode): to offer it to the network computers choose Server mode in "
                       "the Settings, or start with --mode=server."))
    return lines


def _read_json_file(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _run_headless(port, srv, headline):
    """Server e motore senza finestra finche' il server e' vivo, finche' arriva --stop o Ctrl+C. True se il server
    ha lasciato il posto a un aggiornamento."""
    common_lines = [headline] + _addresses(port) + [
        T("Per arrestarlo: Germano.exe --stop (oppure Ctrl+C se è stato avviato da questa console).",
          "To stop it: Germano.exe --stop (or Ctrl+C if it was started from this console).")]
    try:
        os.makedirs(TECH_DIR, exist_ok=True)
        if os.path.exists(STOP_REQUEST):
            os.remove(STOP_REQUEST)
        with open(HEADLESS_FILE, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "port": port, "server_pid": srv.pid, "started": time.time()}, f)
    except OSError as e:
        log(f"file di stato senza finestra non scritto ({e}).")
    _announce(common_lines)
    try:
        while True:
            rc = srv.poll()
            if rc is not None:
                update = rc == UPDATE_EXIT_CODE
                log("il server lascia il posto all'aggiornamento." if update else f"il server si è chiuso (codice {rc}).")
                return update
            if os.path.exists(STOP_REQUEST):
                _announce([T("Richiesta di arresto ricevuta (--stop): chiudo server e motore.",
                             "Stop request received (--stop): closing server and engine.")])
                return False
            time.sleep(1.0)
    except KeyboardInterrupt:
        _announce([T("Ctrl+C: chiudo server e motore.", "Ctrl+C: closing server and engine.")])
        return False
    finally:
        for p in (HEADLESS_FILE, STOP_REQUEST):
            try:
                os.remove(p)
            except OSError:
                pass


def _no_browser_window(port, srv):
    """Windows senza Microsoft Edge ne' Google Chrome (es. Windows Server 2019 con Internet Explorer, Server Core):
    un avviso con gli indirizzi; con OK Germano resta attivo come server senza finestra, con Annulla si chiude."""
    lines = _addresses(port)
    text = T("Su questo computer non c'è Microsoft Edge (né Google Chrome), che Germano usa per la sua finestra "
             "(Internet Explorer non sa mostrare la Dashboard).\n\nGermano può restare attivo come server senza "
             "finestra:\n\n", "This computer has no Microsoft Edge (nor Google Chrome), which Germano uses for its window "
             "(Internet Explorer cannot show the Dashboard).\n\nGermano can stay active as a server without a window:\n\n")
    text += "\n".join("  " + ln for ln in lines) + "\n\n" + T(
        "Apri questi indirizzi da un browser moderno (anche da un altro computer della rete). Per arrestare Germano: "
        "«Germano.exe --stop». Installando Microsoft Edge Germano avrà di nuovo la sua finestra.\n\nOK = resta attivo   "
        "Annulla = chiudi Germano",
        "Open these addresses from a modern browser (also from another computer of the network). To stop Germano: "
        "\"Germano.exe --stop\". After installing Microsoft Edge Germano will have its window again.\n\nOK = stay "
        "active   Cancel = close Germano")
    log("avviso: nessun browser compatibile, chiedo se restare attivo come server.")
    try:
        import ctypes
        answer = ctypes.windll.user32.MessageBoxW(0, text, PRODUCT, 0x1 | 0x40 | 0x10000)   # OKCANCEL, INFO, primo piano
    except Exception:
        answer = 1
    if answer != 1:
        log("scelto «Annulla»: chiudo Germano.")
        return False
    return _run_headless(port, srv, T("Germano AI attivo senza finestra (nessun browser compatibile su questo computer).",
                                      "Germano AI running without a window (no compatible browser on this computer)."))


def _stop_running():
    """--stop: chiude il Germano avviato senza finestra con la stessa cartella tecnica (stesso utente)."""
    info = _read_json_file(HEADLESS_FILE)
    pid = info.get("pid")
    sys.path.insert(0, APP_DIR)
    import psutil
    if not pid or not psutil.pid_exists(int(pid)):
        _announce([T("Nessun Germano AI senza finestra in esecuzione.", "No windowless Germano AI is running.")])
        return 1
    os.makedirs(TECH_DIR, exist_ok=True)
    with open(STOP_REQUEST, "w", encoding="utf-8") as f:
        f.write(str(time.time()))
    try:
        psutil.Process(int(pid)).wait(timeout=90)
    except psutil.TimeoutExpired:
        _announce([T("Germano AI non si è chiuso entro 90 secondi.", "Germano AI did not close within 90 seconds.")])
        return 1
    except psutil.NoSuchProcess:
        pass
    _announce([T("Germano AI arrestato.", "Germano AI stopped.")])
    return 0


def _headless_running():
    """Porta del Germano senza finestra gia' in esecuzione per questo utente (avviato con --no-browser), o None."""
    info = _read_json_file(HEADLESS_FILE)
    try:
        import psutil
        if info.get("pid") and psutil.pid_exists(int(info["pid"])) and info.get("port"):
            with _OPENER.open(f"http://127.0.0.1:{int(info['port'])}/api/status", timeout=5) as r:
                if r.status == 200:
                    return int(info["port"])
    except Exception:
        pass
    return None


def _open_existing(port):
    """Germano e' gia' attivo senza finestra: si apre solo una finestra sulla sua Dashboard (chiuderla non lo ferma),
    invece di avviare un secondo server sulla stessa cartella dati."""
    url = f"http://127.0.0.1:{port}/"
    browser = _find_browser()
    log(f"Germano senza finestra gia' attivo sulla porta {port}: " + ("apro una finestra." if browser else "avviso."))
    if browser:
        subprocess.Popen([browser, f"--app={url}", f"--user-data-dir={WEBVIEW_PROFILE}", "--no-first-run",
                          "--no-default-browser-check", "--window-size=1280,860"],
                         **({"creationflags": NO_WINDOW} if IS_WIN else {"start_new_session": True}))
        return 0
    _message(T(f"Germano AI è già attivo senza finestra: Dashboard su {url}. Per arrestarlo: Germano.exe --stop",
               f"Germano AI is already running without a window: Dashboard at {url}. To stop it: Germano.exe --stop"),
             0x40)
    return 0


def main():
    if "--uninstall" in FLAGS:
        return _uninstall()
    if "--stop" in FLAGS:
        return _stop_running()
    sys.path.insert(0, APP_DIR)
    existing = _headless_running()
    if existing:
        if HEADLESS:
            _announce([T(f"Germano AI è già attivo senza finestra sulla porta {existing}.",
                         f"Germano AI is already running without a window on port {existing}.")])
            return 0
        return _open_existing(existing)
    sys.path.insert(0, APP_DIR)
    import psutil

    _prepare_data_dir()
    os.makedirs(TECH_DIR, exist_ok=True)
    default_port = 8181
    try:
        cfgp = os.path.join(DATA_DIR, "config.json")
        if os.path.isfile(cfgp):
            with open(cfgp, encoding="utf-8-sig") as f:
                default_port = int(json.load(f).get("port") or 8181)
    except Exception:
        pass

    env = dict(os.environ)
    env["GERMANO_NO_BROWSER"] = "1"   # il server non apre il browser di sistema: la finestra la gestiamo noi
    env["GERMANO_PARENT_PID"] = str(os.getpid())
    env["GERMANO_DESKTOP_PID"] = str(os.getpid())
    if not PORTABLE:
        env["GERMANO_DATA_DIR"] = DATA_DIR
        env["GERMANO_TECH_DIR"] = TECH_DIR                       # aggiornamenti scaricati (germano/updater.py)
        env["GERMANO_CACHE_DIR"] = os.path.join(TECH_DIR, "cache")   # cache dei modelli fuori dal programma
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if _MODE_FLAG in ("standalone", "server", "client", "server+client"):
        env["GERMANO_MODE"] = _MODE_FLAG          # --mode=server: modalita' solo per questo avvio (es. server senza finestra)
    elif _MODE_FLAG:
        _message(T(f"Modalità «{_MODE_FLAG}» non valida: usa standalone, server, client o server+client.",
                   f"Invalid mode «{_MODE_FLAG}»: use standalone, server, client or server+client."))
        return 2
    run_kwargs = dict(cwd=APP_DIR, env=env, stdin=subprocess.DEVNULL)
    if IS_WIN:
        run_kwargs["creationflags"] = NO_WINDOW
    else:
        run_kwargs["start_new_session"] = True

    # Aggiornamento già scaricato (installer di download.germano.ai): si installa prima di avviare; l'installer
    # chiude e riapre Germano da solo a installazione finita (stessa posizione usata da germano/updater.py).
    # Senza finestra no: la riapertura avverrebbe con la finestra e senza le opzioni di questo avvio.
    update_ready = os.path.join(APP_DIR if PORTABLE else TECH_DIR, "update", "ready.json")
    if HEADLESS and not IS_CLIENT and os.path.isfile(update_ready):
        log("aggiornamento pronto: si installa al prossimo avvio con la finestra (o dalla Dashboard).")
    elif not IS_CLIENT and os.path.isfile(update_ready):
        log("aggiornamento pronto: avvio dell'installazione prima di aprire Germano.")
        rc = subprocess.run([_interpreter(), "-B", os.path.join(APP_DIR, "server.py"), "--install-update"],
                            **run_kwargs).returncode
        if rc == UPDATE_EXIT_CODE:
            log("installazione dell'aggiornamento avviata: Germano si riaprirà da solo.")
            return 0

    port = _free_port(default_port)
    env["GERMANO_PORT"] = str(port)
    target = "client_ui.py" if IS_CLIENT else "server.py"
    log(f"avvio {target} (ruolo={ROLE}) su 127.0.0.1:{port}; programma={APP_DIR}; dati={DATA_DIR}; tecnici={TECH_DIR}")
    out = open(SERVER_LOG, "a", encoding="utf-8", errors="replace")
    srv = subprocess.Popen([_interpreter(), "-B", os.path.join(APP_DIR, target)], stdout=out,
                           stderr=subprocess.STDOUT, **run_kwargs)
    update_exit = False
    try:
        if not _wait_server(port, srv):
            _message("Germano AI non è riuscito ad avviarsi. Dettagli nel file:\n" + SERVER_LOG)
            return 1
        url = f"http://127.0.0.1:{port}/"
        if HEADLESS:
            result = _run_headless(port, srv, T("Germano AI attivo senza finestra (--no-browser).",
                                                "Germano AI running without a window (--no-browser)."))
        else:
            result = None
            mode = os.environ.get("GERMANO_WINDOW", "auto")   # «browser» per forzare il ripiego (diagnostica)
            if not IS_WIN and mode != "browser":
                result = _window_inprocess(url, srv) if IS_MAC else _window_helper(url, srv)
            if result is None:
                result = _window_browser(url, srv, psutil)
            if result is None:              # Windows senza un browser compatibile (es. Windows Server 2019)
                result = _no_browser_window(port, srv)
        update_exit = bool(result)
    finally:
        if not update_exit:
            _stop_server_http(port)
            time.sleep(0.5)
            _terminate_tree(psutil, srv)
        try:
            out.close()
        except Exception:
            pass
        log("chiusura completata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
