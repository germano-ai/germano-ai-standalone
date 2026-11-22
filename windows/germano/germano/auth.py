"""Gestione utenti per l'accesso dalla rete locale (Remote Control dal browser e Germano Client).

- Di base (auth_enabled = false) dalla rete si accede senza credenziali. Con la gestione utenti attiva servono utente e
  password; dal computer del server (127.0.0.1) si amministra sempre, senza credenziali.
- Password: mai salvate, solo l'impronta PBKDF2-HMAC-SHA256 con sale casuale (600.000 iterazioni) in config.json.
- Sessioni: token casuale (256 bit) consegnato al browser (cookie HttpOnly) o al client (client_config.json); sul
  server se ne conserva solo l'impronta SHA-256, con scadenza (30 giorni dall'ultimo uso) in state/remote_sessions.json.
- Accesso: dopo 5 tentativi falliti in 10 minuti lo stesso indirizzo resta bloccato per 10 minuti.
"""
import hashlib
import hmac
import os
import re
import secrets
import threading
import time

from . import common

ITERATIONS = 600_000
MIN_PASSWORD = 8
MAX_PASSWORD = 256
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,63}$")
SESSION_SECONDS = 30 * 24 * 3600
SESSIONS_FILE = os.path.join(common.STATE_DIR, "remote_sessions.json")
MAX_FAILURES = 5
FAIL_WINDOW = 600
BLOCK_SECONDS = 600
COOKIE = "germano_session"
MAX_SESSIONS_PER_USER = 30
MAX_SESSIONS_TOTAL = 500
MAX_CONCURRENT_LOGINS = 3

_lock = threading.RLock()
_limiter_lock = threading.Lock()
_pbkdf2_sem = threading.Semaphore(MAX_CONCURRENT_LOGINS)
_revoke_hook = None


def set_revoke_hook(fn):
    """Callback notificata quando un utente o tutte le sessioni vengono revocati: fn(username | None)."""
    global _revoke_hook
    _revoke_hook = fn


def _notify_revoke(username):
    fn = _revoke_hook
    if fn is not None:
        try:
            fn(username)
        except Exception:
            pass


class AuthError(ValueError):
    """Dato non valido (nome utente, password): messaggio gia' comprensibile, in italiano e in inglese."""

    def __init__(self, it, en):
        super().__init__(it)
        self.it, self.en = it, en


# ------------------------------------------------------------------ password
def hash_password(password, salt=None, iterations=ITERATIONS):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {"algo": "pbkdf2_sha256", "iterations": iterations, "salt": salt.hex(), "hash": digest.hex()}


def verify_password(password, record):
    try:
        salt = bytes.fromhex(record["salt"])
        iterations = int(record["iterations"])
        expected = bytes.fromhex(record["hash"])
    except (KeyError, TypeError, ValueError):
        return False
    if record.get("algo") != "pbkdf2_sha256" or not 1000 <= iterations <= 10_000_000:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)


# Impronta fittizia: un nome utente inesistente costa quanto uno vero (nessun indizio dai tempi di risposta)
_DUMMY = hash_password(secrets.token_hex(16))


def check_username(name):
    name = str(name or "").strip()
    if not USERNAME_RE.match(name):
        raise AuthError("Nome utente non valido: da 1 a 64 caratteri tra lettere, cifre e . _ @ - (inizia con una "
                        "lettera o una cifra).",
                        "Invalid user name: 1 to 64 characters among letters, digits and . _ @ - (starting with a "
                        "letter or a digit).")
    return name


def check_password(password):
    password = str(password or "")
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"La password deve avere almeno {MIN_PASSWORD} caratteri.",
                        f"The password must have at least {MIN_PASSWORD} characters.")
    if len(password) > MAX_PASSWORD:
        raise AuthError(f"La password puo' avere al massimo {MAX_PASSWORD} caratteri.",
                        f"The password can have at most {MAX_PASSWORD} characters.")
    return password


# ------------------------------------------------------------------ utenti (in config.json)
def users_public():
    return [{"username": u["username"], "created": u.get("created")} for u in common.load_users()]


def set_user(username, password):
    """Crea l'utente o ne cambia la password (le sue sessioni aperte vengono chiuse). Restituisce True se nuovo."""
    username = check_username(username)
    record = hash_password(check_password(password))
    revoked = None
    with _lock:
        users = common.load_users()
        for u in users:
            if u["username"].lower() == username.lower():
                u["pbkdf2"] = record
                u["changed"] = time.strftime("%Y-%m-%d %H:%M:%S")
                common.save_users(users)
                SESSIONS.revoke_user(u["username"])
                revoked = u["username"]
                break
        else:
            users.append({"username": username, "pbkdf2": record, "created": time.strftime("%Y-%m-%d %H:%M:%S")})
            common.save_users(users)
            return True
    if revoked:
        _notify_revoke(revoked)
    return False


def delete_user(username):
    target = str(username or "").strip().lower()
    if not target:
        return False
    removed = []
    with _lock:
        users = common.load_users()
        keep = []
        for u in users:
            if u["username"].lower() == target:
                removed.append(u["username"])
            else:
                keep.append(u)
        if not removed:
            return False
        common.save_users(keep)
        for name in removed:
            SESSIONS.revoke_user(name)
    for name in removed:
        _notify_revoke(name)
    return True


def authenticate(username, password):
    """Nome utente canonico se le credenziali sono giuste, altrimenti None (stesso tempo nei due casi)."""
    name = str(username or "").strip().lower()
    user = next((u for u in common.load_users() if u["username"].lower() == name), None)
    with _pbkdf2_sem:
        ok = verify_password(password, user["pbkdf2"] if user else _DUMMY)
    return user["username"] if (user and ok) else None


# ------------------------------------------------------------------ sessioni
def _digest(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


class Sessions:
    def __init__(self, path=SESSIONS_FILE):
        self.path = path
        self._data = None

    def _load(self):
        if self._data is None:
            raw = common.read_json(self.path, {}) or {}
            if not isinstance(raw, dict):
                raw = {}                 # file valido ma non un oggetto (es. «[]»): prima era un errore a ogni richiesta

            def _num(v):
                return isinstance(v, (int, float)) and not isinstance(v, bool)
            # solo voci complete: una scadenza non numerica mandava in errore (ValueError) ogni controllo di sessione
            self._data = {k: v for k, v in raw.items()
                          if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("user"), str)
                          and _num(v.get("expires")) and _num(v.get("last", 0))}
        return self._data

    def _save(self):
        try:
            common.atomic_write_json(self.path, self._data, indent=1)
        except Exception as e:
            common.log(f"Sessioni del Remote Control non salvate: {e}")

    def _prune(self, now):
        dead = [k for k, v in self._data.items() if float(v.get("expires", 0)) < now]
        for k in dead:
            del self._data[k]
        return bool(dead)

    def create(self, user, kind="web", ip=""):
        token = secrets.token_urlsafe(32)
        now = time.time()
        with _lock:
            data = self._load()
            self._prune(now)
            mine = [k for k, v in data.items() if v.get("user", "").lower() == str(user).lower()]
            if len(mine) >= MAX_SESSIONS_PER_USER:
                mine.sort(key=lambda k: float(data[k].get("last", 0)))
                for k in mine[: len(mine) - MAX_SESSIONS_PER_USER + 1]:
                    data.pop(k, None)
            if len(data) >= MAX_SESSIONS_TOTAL:
                oldest = sorted(data.keys(), key=lambda k: float(data[k].get("last", 0)))
                for k in oldest[: len(data) - MAX_SESSIONS_TOTAL + 1]:
                    data.pop(k, None)
            data[_digest(token)] = {"user": user, "kind": kind, "created": now, "last": now,
                                    "expires": now + SESSION_SECONDS, "ip": str(ip)[:64]}
            self._save()
        return token

    def user_for(self, token):
        """Utente della sessione (prolungata di 30 giorni a ogni uso) oppure None."""
        if not token or not isinstance(token, str) or len(token) > 200:
            return None
        now = time.time()
        with _lock:
            data = self._load()
            s = data.get(_digest(token))
            if not s:
                return None
            if float(s.get("expires", 0)) < now:
                del data[_digest(token)]
                self._save()
                return None
            users = common.load_users()
            if not any(u["username"] == s["user"] for u in users):
                del data[_digest(token)]        # utente eliminato nel frattempo
                self._save()
                return None
            if now - float(s.get("last", 0)) > 600:      # aggiorna il file al massimo ogni 10 minuti
                s["last"], s["expires"] = now, now + SESSION_SECONDS
                self._save()
            return s["user"]

    def revoke(self, token):
        with _lock:
            if self._load().pop(_digest(token), None) is not None:
                self._save()

    def revoke_user(self, user):
        target = str(user or "").strip().lower()
        with _lock:
            data = self._load()
            dead = [k for k, v in data.items() if v.get("user", "").lower() == target]
            for k in dead:
                del data[k]
            if dead:
                self._save()

    def revoke_all(self):
        with _lock:
            self._load()
            self._data = {}
            self._save()
        _notify_revoke(None)

    def count(self):
        with _lock:
            data = self._load()
            if self._prune(time.time()):
                self._save()
            return len(data)


SESSIONS = Sessions()


# ------------------------------------------------------------------ freno ai tentativi
class LoginLimiter:
    _MAX_TRACKED = 2000

    def __init__(self):
        self._fails = {}       # ip -> [(istante, username_lower)]
        self._blocked = {}     # ip -> fine del blocco
        self._inflight = {}    # ip -> numero di verifiche PBKDF2 in corso

    def _cleanup_locked(self, now):
        if len(self._fails) + len(self._blocked) <= self._MAX_TRACKED:
            return
        for k in [k for k, until in self._blocked.items() if until <= now]:
            self._blocked.pop(k, None)
        for k in [k for k, items in self._fails.items() if not any(now - t < FAIL_WINDOW for t, _ in items)]:
            self._fails.pop(k, None)

    def retry_after(self, ip):
        now = time.time()
        with _limiter_lock:
            until = self._blocked.get(ip, 0)
            left = until - now
            if left <= 0:
                self._blocked.pop(ip, None)
                return 0
            return int(left) + 1

    def begin_attempt(self, ip):
        """Prenota uno slot di login per `ip` prima di PBKDF2: impedisce che richieste parallele superino MAX_FAILURES."""
        now = time.time()
        with _limiter_lock:
            self._cleanup_locked(now)
            until = self._blocked.get(ip, 0)
            left = until - now
            if left > 0:
                return False, int(left) + 1
            self._blocked.pop(ip, None)
            recent = [x for x in self._fails.get(ip, []) if now - x[0] < FAIL_WINDOW]
            self._fails[ip] = recent
            inflight = self._inflight.get(ip, 0)
            if len(recent) + inflight >= MAX_FAILURES:
                return False, max(5, min(BLOCK_SECONDS, 15))
            self._inflight[ip] = inflight + 1
            return True, 0

    def end_attempt(self, ip):
        with _limiter_lock:
            cur = self._inflight.get(ip, 0)
            if cur <= 1:
                self._inflight.pop(ip, None)
            else:
                self._inflight[ip] = cur - 1

    def failed(self, ip, username=""):
        now = time.time()
        u = str(username or "").strip().lower()
        with _limiter_lock:
            self._cleanup_locked(now)
            recent = [x for x in self._fails.get(ip, []) if now - x[0] < FAIL_WINDOW] + [(now, u)]
            self._fails[ip] = recent
            if len(recent) >= MAX_FAILURES:
                self._blocked[ip] = now + BLOCK_SECONDS
                self._fails[ip] = []
                return True
            return False

    def succeeded(self, ip, username=""):
        u = str(username or "").strip().lower()
        with _limiter_lock:
            if not u:
                self._fails.pop(ip, None)
                return
            cur = self._fails.get(ip)
            if cur:
                rest = [x for x in cur if x[1] != u]
                if rest:
                    self._fails[ip] = rest
                else:
                    self._fails.pop(ip, None)


LIMITER = LoginLimiter()
