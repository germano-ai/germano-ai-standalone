"""Percorsi, configurazione, I/O atomico e utilita' condivise tra server e demone.

Questo modulo non ha effetti collaterali all'import (nessun chdir, nessun atexit):
puo' essere importato sia dal server web sia dal demone IA.
"""
import json
import os
import re
import sys
import tempfile
import threading
import time
import unicodedata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Cartella dei DATI (configurazione, stato, Vault, cartelle di lavoro, registro). Di norma coincide con la
# cartella del programma; GERMANO_DATA_DIR permette di avviare una seconda istanza con dati separati usando
# la stessa installazione (programma, runtime e modelli condivisi), ad esempio per provare Server e Client
# sullo stesso computer senza copiare l'applicazione.
DATA_DIR = os.path.abspath(os.environ.get("GERMANO_DATA_DIR") or BASE_DIR)

INPUT_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
FAILED_DIR = os.path.join(DATA_DIR, "failed")
EXTRACTED_DIR = os.path.join(DATA_DIR, "extracted")
WORK_FOLDERS = {
    "input": INPUT_DIR,
    "output": OUTPUT_DIR,
    "processed": PROCESSED_DIR,
    "failed": FAILED_DIR,
    "extracted": EXTRACTED_DIR,
}

STATE_DIR = os.path.join(DATA_DIR, "state")
# Cache dei modelli e delle librerie: accanto al programma nella copia portatile; nei programmi installati (cartella
# del programma da non modificare o non scrivibile, es. /opt o /Applications) il launcher indica una cartella
# dell'utente con GERMANO_CACHE_DIR.
CACHE_DIR = os.path.abspath(os.environ.get("GERMANO_CACHE_DIR") or os.path.join(BASE_DIR, "cache"))
UPLOAD_DIR = os.path.join(STATE_DIR, "uploads")
WORK_TMP_DIR = os.path.join(STATE_DIR, "tmp")
# Modelli IA accanto al programma; dai sorgenti GERMANO_MODELS_DIR indica la cartella modelli/ della release (senza copie)
MODELS_DIR = os.path.abspath(os.environ.get("GERMANO_MODELS_DIR") or os.path.join(BASE_DIR, "models"))

CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
VERSION_FILE = os.path.join(BASE_DIR, "VERSION")
LOG_FILE = os.path.join(DATA_DIR, "daemon.log")
VAULT_FILE = os.path.join(EXTRACTED_DIR, "deanonymize_vault.json")

DAEMON_STATE_FILE = os.path.join(STATE_DIR, "daemon.json")
READY_FLAG = os.path.join(STATE_DIR, "ready.flag")
STOP_FLAG = os.path.join(STATE_DIR, "stop.flag")
STATUS_FILE = os.path.join(STATE_DIR, "status.json")
LAST_ERROR_FILE = os.path.join(STATE_DIR, "last_error.json")
FAILED_REASONS_FILE = os.path.join(STATE_DIR, "failed_reasons.json")
OUTPUTS_FILE = os.path.join(STATE_DIR, "outputs.json")  # documento pronto -> esito (per la Dashboard)

# Prefisso breve: i file temporanei di output non devono allungare troppo i percorsi (limite 260 caratteri)
TMP_PREFIX = "~gtmp_"

FEATURE_KEYS = [
    "enable_model_velvet", "enable_model_italian_ner", "enable_ocr",
    "enable_faces", "enable_signatures", "enable_plate_vision", "enable_regex",
    "censor_person", "censor_profession", "censor_address", "censor_cadastre",
    "censor_email", "censor_phone", "censor_account", "censor_financial",
    "censor_url", "censor_date", "censor_secret", "censor_cf_iva",
    "censor_org", "censor_plates_docs", "censor_medical", "censor_medicine",
    "censor_legal", "censor_civil_status",
]

DEFAULT_SETTINGS = {
    "target_api_url": "https://api.openai.com/v1/chat/completions",
    "target_anthropic_url": "https://api.anthropic.com/v1",
    "ui_mode": "simple",
    "compliance_mode": "PA",
    "lock_settings": False,
    "enable_deanonymize": True,
    "ai_threshold": 0.0,
    "hardware_mode": "gpu_fallback",
    "precision": "auto",
    "file_timeout_minutes": 60,
    "anonymize_filenames": False,
    "save_proxy_logs": True,
    "check_updates": True,   # solo quando Windows segnala una connessione a Internet (germano/updater.py)
    "auto_update": True,     # scarica gli aggiornamenti e li installa al successivo avvio
    "port": 8181,
    # --- Server LAN (v0.52) ---
    "bind_host": "127.0.0.1",   # parte Server: IP di rete su cui ascoltare (127.0.0.1 o 0.0.0.0 = tutte le schede)
    "discovery_enabled": True,  # risponde ai ping UDP di rilevamento quando il server e' in ascolto sulla LAN
    "discovery_port": 8182,     # porta UDP del rilevamento automatico
    "lan_token": "",            # non piu' usato dalla 0.60 (sostituito dalla gestione utenti): conservato per compatibilita'
    "server_name": "",          # nome mostrato ai client nel rilevamento (vuoto = nome del computer)
    "share_ai_tools": False,    # i client possono usare le CLI di AI di questo computer (con le sue credenziali)
    # --- Remote Control e gestione utenti (v0.60) ---
    # False (predefinito): dalla rete locale si accede senza credenziali. True: servono utente e password (elenco
    # «users» in config.json, password solo come impronta PBKDF2-SHA256; si gestiscono dalla Dashboard del server).
    "auth_enabled": False,
    # --- Modalita' operativa (v0.52) ---
    "operating_mode": "standalone",  # standalone | server | client | server+client
    "first_run_done": False,         # False: alla prima apertura la Dashboard chiede la modalita' operativa
    "remote_server": "",             # Client: indirizzo del Germano Server (vuoto = ricerca automatica in rete)
    "remote_token": "",              # Client: sessione (o token) per il Germano Server remoto
    "remote_user": "",               # Client: utente con cui si e' acceduto al server remoto (gestione utenti attiva)
    "client_fallback_local": True,   # Client: se nessun server risponde si usa il motore di questo computer
    "instance_id": "",               # identificativo di questa installazione (per non rilevare se stessa)
    "instance_host": "",             # computer su cui e' stato generato instance_id
    "enable_tooltips": True,         # suggerimenti al passaggio del mouse nella Dashboard
    # --- Prestazioni (v0.60): 0 = automatico (processori disponibili, uno lasciato libero da 3 in su, massimo 16) ---
    "cpu_threads": 0,
}
for _k in FEATURE_KEYS:
    DEFAULT_SETTINGS[_k] = True

_BOOL_KEYS = set(FEATURE_KEYS) | {
    "enable_deanonymize", "lock_settings", "anonymize_filenames", "save_proxy_logs", "check_updates",
    "auto_update", "discovery_enabled", "first_run_done", "client_fallback_local", "enable_tooltips",
    "share_ai_tools", "auth_enabled",
}
OPERATING_MODES = ("standalone", "server", "client", "server+client")
_ENUM_KEYS = {
    "ui_mode": ("simple", "advanced"),
    "compliance_mode": ("PA", "PD"),
    "hardware_mode": ("gpu_fallback", "cpu", "gpu"),
    "precision": ("auto", "fp32", "bf16"),
    "operating_mode": OPERATING_MODES,
}
_FLOAT_KEYS = {"ai_threshold": (0.0, 0.95)}
_INT_KEYS = {"file_timeout_minutes": (5, 1440), "port": (1024, 65535), "discovery_port": (1024, 65535),
             "cpu_threads": (0, 256)}
_URL_KEYS = ("target_api_url", "target_anthropic_url", "remote_server")
_HOST_KEYS = {"bind_host"}                       # 0.0.0.0, loopback o un IP letterale
# stringhe libere (lunghezza massima)
_STR_KEYS = {"lan_token": 128, "remote_token": 128, "server_name": 48, "instance_id": 64, "instance_host": 128,
             "remote_user": 64}
_TOKEN_KEYS = {"lan_token", "remote_token", "instance_id"}   # solo caratteri sicuri in URL e intestazioni
# Chiavi modificabili anche quando l'amministratore ha bloccato le impostazioni (preferenze dell'interfaccia).
# La modalita' operativa NO: decide se il computer si espone alla rete.
_UNLOCKED_KEYS = {"ui_mode", "first_run_done", "enable_tooltips"}


def mode_flags(mode):
    """(server, client) per una modalita' operativa: 'server+client' attiva entrambe le parti."""
    m = str(mode or "standalone").lower()
    return ("server" in m, "client" in m)


def effective_operating_mode(cfg=None):
    """Modalita' in vigore per QUESTO avvio. GERMANO_MODE (variabile d'ambiente) prevale sulla
    configurazione salvata; per compatibilita' GERMANO_HOST non di loopback attiva la parte Server."""
    forced = (os.environ.get("GERMANO_MODE") or "").strip().lower()
    if forced in OPERATING_MODES:
        return forced
    mode = (cfg or {}).get("operating_mode") or "standalone"
    if mode not in OPERATING_MODES:
        mode = "standalone"
    host = (os.environ.get("GERMANO_HOST") or "").strip()
    if host and host not in ("127.0.0.1", "localhost", "::1"):
        return "server+client" if mode_flags(mode)[1] else "server"
    return mode


def mode_forced_by():
    """Origine di un'eventuale modalita' imposta all'avvio (None se vale quella salvata)."""
    if (os.environ.get("GERMANO_MODE") or "").strip().lower() in OPERATING_MODES:
        return "GERMANO_MODE"
    host = (os.environ.get("GERMANO_HOST") or "").strip()
    if host and host not in ("127.0.0.1", "localhost", "::1"):
        return "GERMANO_HOST"
    return None


def discovery_port(cfg=None):
    """Porta UDP del rilevamento, uguale per chi risponde e per chi cerca: GERMANO_DISCOVERY_PORT prevale su
    config.json (come GERMANO_PORT per la porta HTTP)."""
    try:
        port = int(os.environ.get("GERMANO_DISCOVERY_PORT") or (cfg or {}).get("discovery_port") or 8182)
    except (TypeError, ValueError):
        return 8182
    return port if 1024 <= port <= 65535 else 8182


DEFAULT_SERVER_PORT = 8181
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")   # token di Germano Server: caratteri sicuri in URL e intestazioni


def parse_server_url(text, default_port=DEFAULT_SERVER_PORT):
    """Indirizzo di un Germano Server come lo scrive una persona: '192.168.1.10', '192.168.1.10:8181',
    'http://pc-server:8181/' oppure il Base URL copiato dalla Dashboard del server ('.../g/<token>/v1').
    Restituisce (base 'http://host:porta', token_trovato_nel_percorso | None); ValueError se non e' un indirizzo.
    Stesse regole di Germano Client (parse_server in client.py)."""
    import urllib.parse
    raw = (text or "").strip()
    if not raw or any(c.isspace() for c in raw):
        raise ValueError(raw)
    if "://" not in raw:
        raw = "http://" + raw
    u = urllib.parse.urlsplit(raw)
    try:
        port = u.port
    except ValueError:
        raise ValueError(raw) from None
    scheme = (u.scheme or "").lower()
    if scheme not in ("http", "https") or not u.hostname:
        raise ValueError(raw)
    host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
    base = f"{scheme}://{host}:{port or (443 if scheme == 'https' else default_port)}"
    m = re.match(r"^/g/([^/]+)", u.path or "")
    token = m.group(1) if m and TOKEN_RE.match(m.group(1)) else None
    return base, token


_config_lock = threading.RLock()


def ts():
    return time.strftime("%H:%M:%S")


def log(msg):
    """Stampa una riga di log con orario (stdout del demone viene rediretto su daemon.log)."""
    try:
        print(f"[{ts()}] {msg}", flush=True)
    except Exception:
        pass


def get_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:
        pass
    return "0.52-alpha"


def ensure_dirs():
    for d in list(WORK_FOLDERS.values()) + [STATE_DIR, CACHE_DIR, UPLOAD_DIR, WORK_TMP_DIR]:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass


def setup_offline_env():
    """Variabili d'ambiente per un'esecuzione 100% offline e portatile (nessuna cache nel profilo utente)."""
    env = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
        "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        "HF_HUB_DISABLE_UPDATE_CHECK": "1",
        "DO_NOT_TRACK": "1",
        "TRANSFORMERS_VERBOSITY": "error",
        "TRANSFORMERS_NO_ADVISORY_WARNINGS": "1",
        "OPENCV_LOG_LEVEL": "ERROR",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "EASYOCR_MODULE_PATH": os.path.join(MODELS_DIR, "easyocr"),
        "HF_HOME": os.path.join(CACHE_DIR, "huggingface"),
        "TORCH_HOME": os.path.join(CACHE_DIR, "torch"),
        "XDG_CACHE_HOME": CACHE_DIR,
        "MPLCONFIGDIR": os.path.join(CACHE_DIR, "matplotlib"),
    }
    for k, v in env.items():
        os.environ[k] = v
    if hasattr(os, "add_dll_directory"):
        runtime_dir = os.path.dirname(sys.executable)
        if os.path.isdir(runtime_dir):
            try:
                os.add_dll_directory(runtime_dir)
            except Exception:
                pass


def force_utf8_stdio():
    """Il runtime embedded (._pth) ignora PYTHONIOENCODING: forziamo UTF-8 su stdout/stderr
    per evitare UnicodeEncodeError con nomi di file non ANSI quando l'output e' rediretto su file."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ----------------------------------------------------------------------------------------
# Processore: thread dei modelli e macchina virtuale
# ----------------------------------------------------------------------------------------
MAX_AUTO_THREADS = 16   # oltre, su CPU l'inferenza non accelera (limite della memoria) e i server NUMA rallentano
_THREADS_CONFIGURED = []   # scelta fatta da configure_cpu_threads in questo processo (prima di importare torch)


def cpus_available():
    """Processori che il sistema concede a questo processo (vCPU di una VM, affinita' impostata
    dall'amministratore, quote dei container), non quelli fisici dell'host."""
    try:
        import psutil
        n = len(psutil.Process().cpu_affinity() or [])
        if n:
            return n
    except Exception:
        pass
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def cpu_threads(settings=None):
    """(thread per i modelli, origine). Ordine: GERMANO_CPU_THREADS, «cpu_threads» in config.json, OMP_NUM_THREADS
    gia' impostata dall'amministratore, automatico: tutti i processori disponibili fino a 2, poi uno lasciato libero
    per il server web, il sistema e gli altri servizi della macchina (misurato su 4 core: -2% di velocita'), al
    massimo 16. Dopo configure_cpu_threads vale la scelta fatta allora (le librerie di calcolo l'hanno gia' letta)."""
    if _THREADS_CONFIGURED:
        return _THREADS_CONFIGURED[0]
    avail = cpus_available()
    for source, raw in (("GERMANO_CPU_THREADS", os.environ.get("GERMANO_CPU_THREADS")),
                        ("config.json", (settings or {}).get("cpu_threads")),
                        ("OMP_NUM_THREADS", os.environ.get("OMP_NUM_THREADS"))):
        try:
            n = int(str(raw).strip())
        except (TypeError, ValueError):
            continue
        if n > 0:
            return min(n, 256), source
    return (avail if avail <= 2 else min(MAX_AUTO_THREADS, avail - 1)), "automatico"


def configure_cpu_threads(settings=None):
    """Da chiamare PRIMA di importare torch/numpy (demone): le librerie di calcolo (OpenMP, MKL, OpenBLAS) creano i
    loro thread all'avvio con questi valori. Le variabili gia' impostate dall'amministratore restano."""
    del _THREADS_CONFIGURED[:]
    n, source = cpu_threads(settings)
    os.environ["OMP_NUM_THREADS"] = str(n)          # sempre quello scelto (PyTorch usa OpenMP)
    for var in ("MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(var, str(n))
    _THREADS_CONFIGURED.append((n, source))
    return n, source


_VM_CACHE = []


def virtual_machine():
    """Nome dell'ambiente virtuale (VMware, Hyper-V, KVM/Proxmox, VirtualBox, cloud...) o '' su una macchina fisica.
    Solo informativo (registro e Dashboard): Germano funziona allo stesso modo, sempre su CPU."""
    if _VM_CACHE:
        return _VM_CACHE[0]
    text = ""
    try:
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as k:
                parts = []
                for name in ("SystemManufacturer", "SystemProductName", "BIOSVendor", "BaseBoardManufacturer"):
                    try:
                        parts.append(str(winreg.QueryValueEx(k, name)[0]))
                    except OSError:
                        pass
                text = " ".join(parts)
        elif sys.platform == "darwin":
            import subprocess
            out = subprocess.run(["sysctl", "-n", "kern.hv_vmm_present"], capture_output=True, text=True, timeout=5)
            text = "virtual machine (macOS)" if out.stdout.strip() == "1" else ""
        else:
            parts = []
            for name in ("sys_vendor", "product_name", "bios_vendor"):
                try:
                    with open(f"/sys/class/dmi/id/{name}", encoding="utf-8", errors="replace") as f:
                        parts.append(f.read().strip())
                except OSError:
                    pass
            text = " ".join(parts)
    except Exception:
        text = ""
    low = text.lower()
    rules = (("vmware", "VMware"), ("virtualbox", "VirtualBox"), ("innotek", "VirtualBox"),
             ("amazon ec2", "AWS EC2"), ("google compute engine", "Google Compute Engine"),
             ("proxmox", "Proxmox VE (KVM)"), ("qemu", "KVM/QEMU (es. Proxmox VE)"), ("kvm", "KVM/QEMU (es. Proxmox VE)"),
             ("openstack", "OpenStack"), ("nutanix", "Nutanix AHV"), ("xen", "Xen"), ("parallels", "Parallels"),
             ("bochs", "KVM/QEMU (es. Proxmox VE)"), ("virtual machine (macos)", "macchina virtuale"))
    name = next((label for key, label in rules if key in low), "")
    if not name and "microsoft corporation" in low and "virtual machine" in low:
        name = "Hyper-V (o Azure)"
    _VM_CACHE.append(name)
    return name


# ----------------------------------------------------------------------------------------
# Blocco della cartella dati: un solo motore per cartella, anche fra computer diversi
# ----------------------------------------------------------------------------------------
class DataFolderLock:
    """Blocco esclusivo del sistema operativo su state/daemon.lock: impedisce a due motori di scrivere lo stesso
    Vault, anche quando la cartella dati e' una condivisione di rete (SMB o NFS) usata da due computer. Il sistema lo
    rilascia da solo se il processo si chiude o termina in modo anomalo (nessun blocco «orfano»)."""

    def __init__(self, path=None):
        self.path = path or os.path.join(STATE_DIR, "daemon.lock")
        self.info_path = self.path + ".json"
        self._f = None

    def acquire(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        f = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        self._f = f
        try:
            import socket
            atomic_write_json(self.info_path, {"host": socket.gethostname(), "pid": os.getpid(), "since": time.time()})
        except Exception:
            pass
        return True

    def holder(self):
        """Chi tiene il blocco (computer, PID), se l'ha annotato."""
        return read_json(self.info_path, {}) or {}

    def release(self):
        if self._f is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._f.seek(0)
                msvcrt.locking(self._f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.lockf(self._f, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self._f.close()
        finally:
            self._f = None


# ----------------------------------------------------------------------------------------
# I/O atomico (Windows: os.replace puo' fallire se il file e' aperto da un altro processo)
# ----------------------------------------------------------------------------------------

def atomic_write_bytes(path, data, retries=20):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=TMP_PREFIX, dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        for i in range(retries):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                time.sleep(0.05 * (i + 1))
        # Ultima risorsa: scrittura diretta (non atomica) per non perdere i dati.
        with open(path, "wb") as f:
            f.write(data)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def atomic_write_json(path, obj, indent=2):
    data = json.dumps(obj, indent=indent, ensure_ascii=False).encode("utf-8")
    atomic_write_bytes(path, data)


def read_json(path, default=None, retries=5):
    """Legge un JSON tollerando letture concorrenti (file momentaneamente bloccato o in scrittura).
    'utf-8-sig': accetta anche i file salvati con BOM (Blocco note, PowerShell 5)."""
    for i in range(retries):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (PermissionError, json.JSONDecodeError, UnicodeDecodeError):
            time.sleep(0.05 * (i + 1))
        except Exception:
            return default
    return default


def remove_quietly(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# ----------------------------------------------------------------------------------------
# Configurazione
# ----------------------------------------------------------------------------------------

def _to_bool(v, default):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "si", "on"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
    return default


def _validate_value(key, value, current):
    """Restituisce il valore validato oppure `current` se non valido."""
    if key in _BOOL_KEYS:
        return _to_bool(value, current)
    if key in _ENUM_KEYS:
        return value if value in _ENUM_KEYS[key] else current
    if key in _FLOAT_KEYS:
        lo, hi = _FLOAT_KEYS[key]
        try:
            f = float(value)
        except (TypeError, ValueError):
            return current
        if f != f:  # NaN
            return current
        return round(min(max(f, lo), hi), 2)
    if key in _INT_KEYS:
        lo, hi = _INT_KEYS[key]
        try:
            n = int(float(value))
        except (TypeError, ValueError):
            return current
        return min(max(n, lo), hi)
    if key in _URL_KEYS:
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return DEFAULT_SETTINGS[key]
            if re.match(r"^https?://[^\s/$.?#][^\s]*$", s, re.I) and len(s) <= 500:
                return s
        return current
    if key in _HOST_KEYS:
        if isinstance(value, str):
            s = value.strip()
            if s in ("0.0.0.0", "127.0.0.1", "localhost", "::", "::1"):
                return s
            try:
                import ipaddress
                ipaddress.ip_address(s)   # accetta solo un IP letterale (niente nomi di dominio)
                return s
            except ValueError:
                pass
        return current
    if key in _STR_KEYS:
        if isinstance(value, str):
            s = value.strip()[: _STR_KEYS[key]]
            if key in _TOKEN_KEYS:
                s = re.sub(r"[^A-Za-z0-9_\-]", "", s)   # token: solo caratteri sicuri in URL/header
            else:
                s = re.sub(r"[\x00-\x1f]", "", s)
            return s
        return current
    return current


def normalize_settings(raw):
    cfg = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in DEFAULT_SETTINGS:
                cfg[k] = _validate_value(k, v, DEFAULT_SETTINGS[k])
            else:
                cfg[k] = v  # chiavi sconosciute: preservate ma ignorate
    if cfg.get("compliance_mode") == "PA":
        cfg["ai_threshold"] = 0.0
        for k in FEATURE_KEYS:
            cfg[k] = True
    return cfg


def load_config():
    with _config_lock:
        return normalize_settings(read_json(CONFIG_FILE, {}))


def _backup_unreadable_config():
    """Se config.json esiste ma non e' un JSON valido (es. modifica manuale errata) se ne conserva una copia
    prima di riscriverlo, cosi' le impostazioni dell'amministratore non vanno perse."""
    if os.path.exists(CONFIG_FILE) and read_json(CONFIG_FILE, None) is None:
        backup = CONFIG_FILE + time.strftime(".illeggibile-%Y%m%d-%H%M%S")
        try:
            import shutil
            shutil.copy2(CONFIG_FILE, backup)
            log(f"ATTENZIONE: config.json non valido, copia salvata in {os.path.basename(backup)}")
        except Exception:
            pass


def save_config(updates, admin=False):
    """Aggiorna config.json. Restituisce (config, errore_o_None)."""
    with _config_lock:
        _backup_unreadable_config()
        cfg = normalize_settings(read_json(CONFIG_FILE, {}))
        if not isinstance(updates, dict):
            return cfg, None
        locked = bool(cfg.get("lock_settings")) and not admin
        rejected = []
        for k, v in updates.items():
            if k not in DEFAULT_SETTINGS:
                continue
            if k == "lock_settings" and not admin:
                continue
            if locked and k not in _UNLOCKED_KEYS:
                if _validate_value(k, v, cfg[k]) != cfg[k]:
                    rejected.append(k)
                continue
            cfg[k] = _validate_value(k, v, cfg[k])
        if not locked:
            # Se l'utente disattiva un filtro o alza la soglia, il profilo passa automaticamente a PD.
            if any(not cfg.get(k, True) for k in FEATURE_KEYS) or float(cfg.get("ai_threshold", 0.0)) > 0:
                cfg["compliance_mode"] = "PD"
        cfg = normalize_settings(cfg)
        atomic_write_json(CONFIG_FILE, cfg, indent=4)
        err = None
        if rejected:
            err = "Impostazioni bloccate dall'amministratore (lock_settings): modifiche ignorate."
        return cfg, err


# ----------------------------------------------------------------------------------------
# Opzioni scelte dai client della rete (Remote Control e Germano Client): valgono solo per le richieste di quel client,
# mai per la configurazione del server. Profilo PA o lock_settings: non si cambiano (Compliance Lock).
# ----------------------------------------------------------------------------------------
CENSOR_KEYS = tuple(k for k in FEATURE_KEYS if k.startswith("censor_"))
CLIENT_OPTION_KEYS = ("ai_threshold", "enable_model_velvet", "enable_model_italian_ner", "enable_regex") + CENSOR_KEYS
# numbered: etichette numerate [PERSONA_1], ripristinabili; generic: [PERSONA], irreversibili; blackout: ████, irreversibile
MASKING_MODES = ("numbered", "generic", "blackout")
BLACKOUT_LABEL = "████"


def options_locked(cfg):
    """True se le opzioni di elaborazione dei client non si possono cambiare: profilo PA (protezione massima imposta)
    oppure impostazioni bloccate dall'amministratore (lock_settings)."""
    return cfg.get("compliance_mode") == "PA" or bool(cfg.get("lock_settings"))


def server_options(cfg):
    """Opzioni in vigore sul server, nel formato usato dai client."""
    out = {k: cfg.get(k, DEFAULT_SETTINGS[k]) for k in CLIENT_OPTION_KEYS}
    out["masking"] = "numbered" if cfg.get("enable_deanonymize", True) else "generic"
    return out


def validate_options(raw, cfg):
    """Opzioni inviate da un client, validate come config.json (valori non validi = quelli del server)."""
    base = server_options(cfg)
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for k in CLIENT_OPTION_KEYS:
        if k in raw:
            out[k] = _validate_value(k, raw[k], base[k])
    m = raw.get("masking")
    if m in MASKING_MODES:
        out["masking"] = m
    return out


def options_differ(opts, cfg):
    """True se le opzioni richieste cambiano qualcosa rispetto a quelle del server."""
    return validate_options(opts, cfg) != server_options(cfg)


def options_to_settings(opts):
    """Opzioni di un client -> impostazioni del motore per quella sola richiesta (+ etichetta sostitutiva)."""
    settings = {k: opts[k] for k in CLIENT_OPTION_KEYS if k in opts}
    masking = opts.get("masking", "numbered")
    settings["enable_deanonymize"] = masking == "numbered"
    return settings, (BLACKOUT_LABEL if masking == "blackout" else None)


def load_users():
    """Utenti per l'accesso dalla rete: [{"username", "pbkdf2": {...}, "created"}]. Mai restituiti alla rete."""
    users = (read_json(CONFIG_FILE, {}) or {}).get("users")
    if not isinstance(users, list):
        return []
    return [u for u in users if isinstance(u, dict) and isinstance(u.get("username"), str)
            and isinstance(u.get("pbkdf2"), dict)]


def save_users(users):
    """Scrive l'elenco degli utenti in config.json lasciando invariato tutto il resto."""
    with _config_lock:
        _backup_unreadable_config()
        cfg = normalize_settings(read_json(CONFIG_FILE, {}))
        cfg["users"] = list(users)
        if not users:
            cfg["auth_enabled"] = False      # senza utenti l'accesso con password non avrebbe nessun ingresso
        atomic_write_json(CONFIG_FILE, cfg, indent=4)
        return cfg


# ----------------------------------------------------------------------------------------
# Nomi file
# ----------------------------------------------------------------------------------------

_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
_INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name, max_len=150, fallback="file"):
    """Nome file sicuro per Windows che preserva lettere accentate e caratteri Unicode."""
    name = unicodedata.normalize("NFC", str(name or ""))
    name = name.replace("\\", "/").split("/")[-1]
    name = _INVALID_CHARS_RE.sub("_", name).strip().strip(".").strip()
    if not name:
        name = fallback
    base, ext = os.path.splitext(name)
    if base.upper().split(".")[0] in _WIN_RESERVED:
        base = "_" + base
    if len(ext) > 16:
        base, ext = base + ext, ""
    if len(base) + len(ext) > max_len:
        base = base[: max(1, max_len - len(ext))]
    return base + ext


def safe_relpath(rel, max_depth=12):
    """Percorso relativo sicuro (niente '..', unita', percorsi assoluti)."""
    parts = []
    for p in str(rel or "").replace("\\", "/").split("/"):
        p = p.strip()
        if not p or p in (".", ".."):
            continue
        parts.append(safe_filename(p))
    parts = parts[-max_depth:]
    return os.path.join(*parts) if parts else ""


IGNORED_NAMES = {"thumbs.db", "desktop.ini", ".ds_store", "ehthumbs.db", "ehthumbs_vista.db"}
IGNORED_SUFFIXES = (".tmp", ".temp", ".crdownload", ".part", ".partial", ".download", ".!ut", ".opdownload")
IGNORED_PREFIXES = ("~$", ".~lock.", "~wrl", "._", TMP_PREFIX)


def is_ignored_file(path):
    name = os.path.basename(path)
    low = name.lower()
    if low in IGNORED_NAMES or low.startswith(IGNORED_PREFIXES) or low.endswith(IGNORED_SUFFIXES):
        return True
    try:
        attrs = getattr(os.stat(path), "st_file_attributes", 0)
        # FILE_ATTRIBUTE_HIDDEN (0x2) | FILE_ATTRIBUTE_SYSTEM (0x4)
        if attrs & 0x6:
            return True
    except Exception:
        pass
    return False


def unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while True:
        cand = f"{base} ({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


def same_file_content(a, b, chunk=1 << 20):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                x = fa.read(chunk)
                y = fb.read(chunk)
                if x != y:
                    return False
                if not x:
                    return True
    except Exception:
        return False
