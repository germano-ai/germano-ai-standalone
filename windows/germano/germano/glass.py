"""Glass Window: esecuzioni dell'Harness AI osservabili in tempo reale e interrompibili.

Ogni richiesta dell'Harness (Dashboard, Remote Control, Germano Client) e' una «esecuzione» (Run) con un identificativo
casuale. Il server la svolge passo per passo (protezione con il motore, eventuale revisione, invio, risposta in
streaming) e pubblica ogni passo come evento JSON nella coda dell'esecuzione: la pagina li riceve in un flusso NDJSON
e la Glass Window mostra esattamente cio' che succede. Anche il Proxy di Germano pubblica qui il payload HTTP reale
inviato al fornitore quando a chiamarlo e' una CLI eseguita dall'Harness (prefisso /s/run-<id>).

Interruzione: abort() chiude subito la connessione verso il servizio di AI o termina l'albero dei processi della CLI;
prima dell'invio l'esecuzione si ferma senza trasmettere nulla.

Solo libreria standard: nessuna dipendenza nuova.
"""
import collections
import hashlib
import json
import os
import queue
import re
import threading
import time
import uuid

MAX_EVENT_CHARS = 400_000         # testo massimo di un singolo campo di un evento (oltre si tronca, con l'avviso)
MAX_RUNS_PER_OWNER = 3            # esecuzioni contemporanee per dispositivo/utente
FINISHED_KEEP = 120               # secondi in cui un'esecuzione conclusa resta consultabile (abort tardivi, payload)
REVIEW_TIMEOUT = 15 * 60          # attesa massima della revisione manuale prima dell'invio

ABORT_IT = ("Operazione interrotta dall'utente tramite Glass Window: nessun dato ulteriore è stato trasmesso o "
            "ricevuto.")
ABORT_EN = "Operation stopped by the user via Glass Window: no further data was transmitted or received."

_SECRET_HEADERS = {"authorization", "x-api-key", "api-key", "x-goog-api-key", "proxy-authorization", "cookie",
                   "x-germano-provider-key", "x-germano-auth"}
_KEYISH_RE = re.compile(r"\b(sk|pk|rk|gsk|xai|pplx|AIza|sk-ant|sk-proj|sk-or)[-_A-Za-z0-9]{12,}\b")


def mask_secret(value):
    """Chiave o token mostrati in modo riconoscibile ma inutilizzabile: «Bearer sk-p…9fQ2 (nascosta)»."""
    v = str(value or "")
    scheme = ""
    if " " in v:
        scheme, _, v = v.partition(" ")
        scheme += " "
    if len(v) <= 8:
        return scheme + "••••"
    return f"{scheme}{v[:4]}…{v[-4:]}"


def redact_headers(headers):
    out = {}
    for k, v in (headers or {}).items():
        out[k] = mask_secret(v) + " (nascosta)" if k.lower() in _SECRET_HEADERS else v
    return out


def redact_text(text):
    """Toglie da un testo eventuali chiavi API rimaste (es. in un messaggio d'errore del fornitore)."""
    return _KEYISH_RE.sub(lambda m: m.group(0)[:6] + "…(nascosta)", str(text or ""))


def scrub_server_paths(obj, enabled):
    """Per chi guarda dalla rete: la cartella personale dell'utente del server (che contiene il suo nome di Windows)
    diventa «~». Vale per i payload catturati dal Proxy (es. il prompt di sistema di una CLI)."""
    if not enabled:
        return obj
    home = os.path.expanduser("~")
    names = {home, home.replace("\\", "/"), home.replace("\\", "\\\\")}
    user = os.path.basename(home.rstrip("\\/"))

    def fix(s):
        for n in names:
            if n and n in s:
                s = s.replace(n, "~")
        if user and len(user) > 2:
            s = re.sub(r"(?i)(users[\\/]+|home[\\/]+)" + re.escape(user), r"\1~", s)
        return s

    def walk(o):
        if isinstance(o, str):
            return fix(o)
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        return o
    return walk(obj)


def cap(value, limit=MAX_EVENT_CHARS):
    """Testi lunghi negli eventi: tagliati con un avviso esplicito (mai in silenzio)."""
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"\n[... {len(value) - limit} caratteri non mostrati nella Glass Window ...]"
    return value


def cap_obj(obj, limit=MAX_EVENT_CHARS):
    if isinstance(obj, str):
        return cap(obj, limit)
    if isinstance(obj, list):
        return [cap_obj(x, limit) for x in obj]
    if isinstance(obj, dict):
        return {k: cap_obj(v, limit) for k, v in obj.items()}
    return obj


def ndjson(event):
    return (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


# ------------------------------------------------------------------------------------------------ esecuzioni
class Aborted(Exception):
    """L'esecuzione e' stata interrotta (dall'utente o perche' la pagina si e' chiusa)."""


class Run:
    """Una richiesta dell'Harness: eventi, stato, interruzione."""

    def __init__(self, owner, local, target="", model=""):
        self.id = uuid.uuid4().hex
        self.owner = owner                 # (indirizzo, utente) di chi l'ha avviata
        self.local = local                 # avviata da questo computer
        self.target = target
        self.model = model
        self.created = time.time()
        self.finished = None
        self.phase = "start"
        self.transmitted = False           # True appena il primo byte e' partito verso il servizio di AI
        self.received = 0                  # caratteri ricevuti dal modello
        self.reason = ""                   # motivo dell'interruzione: "user", "client", "timeout"
        self.queue = queue.Queue()
        self._cancel = threading.Event()
        self._approve = threading.Event()
        self._lock = threading.Lock()
        self._proc = None
        self._response = None

    # -- eventi
    def emit(self, kind, **data):
        data["type"] = kind
        data.setdefault("t", round((time.time() - self.created) * 1000))
        self.queue.put(data)

    def elapsed_ms(self):
        return round((time.time() - self.created) * 1000)

    # -- interruzione
    def is_set(self):
        return self._cancel.is_set()

    cancelled = property(is_set)

    def bind_process(self, proc):
        with self._lock:
            self._proc = proc
            kill = self._cancel.is_set()
        if kill:
            _kill_tree(proc)

    def bind_response(self, response):
        with self._lock:
            self._response = response
            close = self._cancel.is_set()
        if close:
            _close_quietly(response)

    def abort(self, reason="user"):
        """Ferma subito l'esecuzione: niente invio se non e' ancora partito, connessione chiusa o CLI terminata."""
        with self._lock:
            if self._cancel.is_set():
                return False
            self.reason = reason
            self._cancel.set()
            proc, resp = self._proc, self._response
        self._approve.set()               # sblocca l'eventuale attesa della revisione
        if proc is not None:
            _kill_tree(proc)
        if resp is not None:
            _close_quietly(resp)
        self.queue.put({"type": "_wake"})
        return True

    def check(self):
        if self._cancel.is_set():
            raise Aborted(self.reason or "user")

    # -- revisione manuale prima dell'invio
    def approve(self):
        self._approve.set()

    def wait_approval(self, timeout=REVIEW_TIMEOUT, tick=None):
        """True se l'utente approva l'invio; False se interrompe o se scade l'attesa. tick() ogni 5 s (battito)."""
        end = time.time() + timeout
        while time.time() < end:
            if self._approve.wait(5.0):
                return not self._cancel.is_set()
            if tick is not None:
                tick()
        return False


def _find_socket(resp):
    """Socket di una risposta HTTP in streaming (requests/urllib3 o http.client), se raggiungibile."""
    raw = getattr(resp, "raw", resp)
    candidates = []
    conn = getattr(raw, "_connection", None)
    if conn is not None:
        candidates.append(getattr(conn, "sock", None))
    fp = getattr(raw, "_fp", None) or getattr(raw, "fp", None)
    inner = getattr(fp, "fp", fp)
    inner = getattr(inner, "raw", inner)
    candidates.append(getattr(inner, "_sock", None))
    for s in candidates:
        if s is not None and hasattr(s, "shutdown"):
            return s
    return None


def _close_quietly(resp):
    """Chiude subito una risposta in streaming: shutdown() del socket sblocca anche la lettura in corso in un altro
    thread (close() da solo, su alcuni sistemi, la lascerebbe in attesa del prossimo dato)."""
    sock = _find_socket(resp)
    if sock is not None:
        try:
            import socket as _socket
            sock.shutdown(_socket.SHUT_RDWR)
        except Exception:
            pass
    try:
        resp.close()
    except Exception:
        pass


def _kill_tree(proc):
    try:
        import psutil
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        parent.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


class Registry:
    def __init__(self):
        self._runs = {}
        self._lock = threading.Lock()

    def _gc(self):
        now = time.time()
        for rid in [r for r, run in self._runs.items() if run.finished and now - run.finished > FINISHED_KEEP]:
            self._runs.pop(rid, None)

    def active_for(self, owner):
        with self._lock:
            return sum(1 for r in self._runs.values() if r.owner == owner and not r.finished)

    def register(self, owner, local, target="", model=""):
        with self._lock:
            self._gc()
            busy = sum(1 for r in self._runs.values() if r.owner == owner and not r.finished)
            if busy >= MAX_RUNS_PER_OWNER and not local:
                return None
            run = Run(owner, local, target, model)
            self._runs[run.id] = run
            return run

    def get(self, rid):
        with self._lock:
            return self._runs.get(str(rid or ""))

    def finish(self, run):
        run.finished = time.time()

    def abort_all(self):
        with self._lock:
            runs = list(self._runs.values())
        for r in runs:
            if not r.finished:
                r.abort("shutdown")


RUNS = Registry()


# ------------------------------------------------------------------------------------------------ cache
class AnonCache:
    """Risultati del motore per testi gia' protetti (cronologia della conversazione, anteprima della Glass Window):
    a ogni turno si rianalizza solo il testo nuovo. Chiave = impronta di testo + impostazioni effettive; svuotata
    quando si svuota il Vault (le etichette ripartirebbero da 1)."""

    def __init__(self, maxsize=768, ttl=3600):
        self.maxsize, self.ttl = maxsize, ttl
        self._d = collections.OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def key(text, settings_sig):
        return hashlib.sha256((settings_sig + "\0" + text).encode("utf-8", "surrogatepass")).hexdigest()

    def get(self, k):
        with self._lock:
            hit = self._d.get(k)
            if not hit:
                return None
            if time.time() - hit[0] > self.ttl:
                self._d.pop(k, None)
                return None
            self._d.move_to_end(k)
            return hit[1]

    def put(self, k, value):
        with self._lock:
            self._d[k] = (time.time(), value)
            self._d.move_to_end(k)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def clear(self):
        with self._lock:
            self._d.clear()

    def __len__(self):
        return len(self._d)


CACHE = AnonCache()


class MediaCache(AnonCache):
    """Allegati gia' protetti (immagini, PDF, documenti rimandati nella cronologia del Proxy a ogni turno): stessa
    politica della cache dei testi, con un tetto anche sulla memoria occupata (turno 26)."""

    def __init__(self, maxsize=128, ttl=3600, max_bytes=256 * 1024 * 1024):
        super().__init__(maxsize, ttl)
        self.max_bytes = max_bytes
        self._sizes = {}

    def put(self, k, value, size=0):
        size = int(size or 0)
        if size > self.max_bytes // 4:
            return                                   # un solo allegato enorme non svuota la cache
        with self._lock:
            self._d[k] = (time.time(), value)
            self._d.move_to_end(k)
            self._sizes[k] = size
            while len(self._d) > self.maxsize or sum(self._sizes.values()) > self.max_bytes:
                old, _ = self._d.popitem(last=False)
                self._sizes.pop(old, None)

    def get(self, k):
        hit = super().get(k)
        if hit is None:
            with self._lock:
                if k not in self._d:
                    self._sizes.pop(k, None)
        return hit

    def clear(self):
        with self._lock:
            self._d.clear()
            self._sizes.clear()


MEDIA_CACHE = MediaCache()


def settings_signature(cfg, options=None):
    """Impronta delle impostazioni che cambiano il risultato del motore (modelli, categorie, soglia, mascheramento)."""
    keys = sorted(k for k in cfg if k.startswith(("enable_model", "enable_regex", "censor_")) or
                  k in ("ai_threshold", "compliance_mode", "enable_deanonymize", "enable_system2"))
    base = {k: cfg.get(k) for k in keys}
    return hashlib.sha256(json.dumps([base, options or None], sort_keys=True, default=str).encode()).hexdigest()[:24]


# ------------------------------------------------------------------------------------------------ entita'
_LABEL_BASE_RE = re.compile(r"^\[\s*(.+?)(?:[ _]+\d{1,7})?\s*\]$")


def label_category(label):
    """[PERSONA_3] -> PERSONA; [COD.FISCALE/P.IVA_1] -> COD.FISCALE/P.IVA (per i colori della Glass Window)."""
    m = _LABEL_BASE_RE.match(str(label or ""))
    return (m.group(1) if m else str(label or "")).strip().upper()


def public_system2(decisions, source=None):
    """Decisioni del Sistema 2 sui casi dubbi per la Glass Window: frammento, tipo, decisione, probabilita', motivo."""
    out = []
    for d in decisions or []:
        item = {"word": d.get("word") or "", "entity": d.get("entity") or "", "decision": d.get("decision") or "",
                "p": d.get("p_personale"), "reason": d.get("reason") or "", "ms": d.get("ms")}
        if source:
            item["source"] = source
        out.append(item)
    return out


def public_entities(entities, source=None):
    """Entita' rilevate in forma compatta per la Glass Window (valore originale, etichetta, categoria, punteggio)."""
    out = []
    for e in entities or []:
        label = e.get("label") or ""
        if not label:
            continue
        item = {"label": label, "word": e.get("word") or "", "entity": e.get("entity") or "",
                "category": label_category(label), "score": e.get("score")}
        if source:
            item["source"] = source
        out.append(item)
    return out
