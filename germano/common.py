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

INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
FAILED_DIR = os.path.join(BASE_DIR, "failed")
EXTRACTED_DIR = os.path.join(BASE_DIR, "extracted")
WORK_FOLDERS = {
    "input": INPUT_DIR,
    "output": OUTPUT_DIR,
    "processed": PROCESSED_DIR,
    "failed": FAILED_DIR,
    "extracted": EXTRACTED_DIR,
}

STATE_DIR = os.path.join(BASE_DIR, "state")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
UPLOAD_DIR = os.path.join(STATE_DIR, "uploads")
WORK_TMP_DIR = os.path.join(STATE_DIR, "tmp")
MODELS_DIR = os.path.join(BASE_DIR, "models")

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
VERSION_FILE = os.path.join(BASE_DIR, "VERSION")
LOG_FILE = os.path.join(BASE_DIR, "daemon.log")
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
    "port": 8000,
}
for _k in FEATURE_KEYS:
    DEFAULT_SETTINGS[_k] = True

_BOOL_KEYS = set(FEATURE_KEYS) | {
    "enable_deanonymize", "lock_settings", "anonymize_filenames", "save_proxy_logs", "check_updates",
    "auto_update",
}
_ENUM_KEYS = {
    "ui_mode": ("simple", "advanced"),
    "compliance_mode": ("PA", "PD"),
    "hardware_mode": ("gpu_fallback", "cpu", "gpu"),
    "precision": ("auto", "fp32", "bf16"),
}
_FLOAT_KEYS = {"ai_threshold": (0.0, 0.95)}
_INT_KEYS = {"file_timeout_minutes": (5, 1440), "port": (1024, 65535)}
_URL_KEYS = ("target_api_url", "target_anthropic_url")
# Chiavi modificabili anche quando l'amministratore ha bloccato le impostazioni.
_UNLOCKED_KEYS = {"ui_mode"}

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
    return "0.51-alpha"


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
