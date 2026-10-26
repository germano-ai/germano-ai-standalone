"""Motore remoto: delega l'inferenza (modelli NER, OCR, visione) a un Germano Server della rete locale.

Vault, etichette, file e ripristino restano su QUESTO computer: al server si inviano solo i testi e le
immagini da analizzare e si ricevono soltanto posizioni, categorie e punteggi dei dati trovati. Il server
esegue lo stesso codice del motore locale con le impostazioni di questo computer (modelli e soglia), quindi i
risultati coincidono con quelli che si avrebbero in locale.

Interfaccia identica a germano.engine.Engine (load, classify_many, ocr, detect_faces, detect_signatures,
detect_plates, clear_cache, info, ocr_reader): il resto del programma non sa se il motore e' locale o remoto.
"""
import hashlib
import http.client
import io
import json
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict

from . import common
from .engine import NO_CANCEL

API_PATH = "/api/engine/v1"
API_VERSION = 1
# Impostazioni che influiscono sull'analisi del testo: le altre si applicano comunque su questo computer.
TEXT_SETTINGS = ("enable_model_velvet", "enable_model_italian_ner", "ai_threshold")
_MAX_BATCH_TEXTS = 64
_MAX_BATCH_CHARS = 200_000


class EngineUnavailable(RuntimeError):
    """Il motore remoto non risponde o rifiuta la richiesta. Nessun dato e' stato inoltrato al cloud:
    l'operazione va ripetuta piu' tardi (i documenti in coda restano nella cartella input)."""


def _error_text(err):
    try:
        data = json.loads(err.read().decode("utf-8", errors="replace"))
        return str(data.get("error") or data.get("message") or err.reason)
    except Exception:
        return str(getattr(err, "reason", err))


def _network_problem(reason, base, timeout):
    """Messaggio comprensibile per i problemi di rete (gli stessi di Germano Client), invece del testo tecnico
    di Windows: dice cosa controllare."""
    import socket
    import urllib.parse
    u = urllib.parse.urlsplit(base)
    where = f"{u.hostname}:{u.port}" if u.port else (u.hostname or base)
    win = getattr(reason, "winerror", None)
    if isinstance(reason, (socket.timeout, TimeoutError)) or win == 10060:
        return (f"nessuna risposta da {where} entro {timeout:g} s: server spento o sovraccarico, firewall di Windows "
                "o indirizzo sbagliato")
    if isinstance(reason, ConnectionRefusedError) or win == 10061:
        return (f"{where} rifiuta la connessione: Germano non e' avviato su quel computer, non e' in modalita' Server "
                "o la porta e' sbagliata")
    if isinstance(reason, socket.gaierror):
        return f"il nome «{u.hostname}» non corrisponde a nessun computer raggiungibile"
    if isinstance(reason, ConnectionResetError) or win == 10054:
        return f"{where} ha interrotto la connessione"
    if win in (10051, 10065):
        return f"{where} non e' raggiungibile da questa rete"
    return f"collegamento a {where} non riuscito ({reason})"


class RemoteEngine:
    is_remote = True

    def __init__(self, base_url, token="", log=common.log, timeout=180):
        raw = (base_url or "").strip()
        url_token = None
        try:   # '192.168.1.10' -> http://192.168.1.10:8181; il Base URL '.../g/<token>/v1' porta con se' il token
            self.base, url_token = common.parse_server_url(raw)
        except ValueError:
            self.base = raw.rstrip("/")
        self.token = token or url_token or ""
        self.log = log
        self.timeout = timeout
        self.lock = threading.RLock()
        self.ocr_reader = None   # sentinella letta da formats/images.py: non None se il server ha l'OCR
        self.info = {"mode": "remote", "server": self.base, "ok": False}
        self._cache = OrderedDict()
        self._cache_max = 4000
        # In LAN non si passa mai dal proxy di sistema o aziendale (come le chiamate interne a 127.0.0.1).
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.latency_ms = None
        self.last_ok = 0.0
        self.last_error = ""

    # ------------------------------------------------------------------ HTTP
    def _call(self, path, payload=None, png=None, timeout=None):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["X-Germano-Auth"] = self.token
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif png is not None:
            data = png
            headers["Content-Type"] = "image/png"
        req = urllib.request.Request(self.base + API_PATH + path, data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
        t0 = time.perf_counter()
        try:
            with self._opener.open(req, timeout=timeout or self.timeout) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            msg = _error_text(e)
            self.last_error = msg
            if e.code in (401, 403):
                raise EngineUnavailable(f"Il Germano Server {self.base} ha rifiutato l'accesso ({e.code}): sul server "
                                        "e' attiva la gestione utenti, accedi con utente e password nelle "
                                        "Impostazioni (Rete e modalita' operativa).") from None
            if e.code == 409:
                raise EngineUnavailable(f"Il Germano Server {self.base} delega a sua volta il motore a un altro "
                                        "server: scegline uno con il motore locale.") from None
            raise EngineUnavailable(f"Errore del Germano Server {self.base} ({e.code}): {msg}") from None
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            self.last_error = str(reason)
            problem = _network_problem(reason, self.base, timeout or self.timeout)
            raise EngineUnavailable(f"Germano Server non raggiungibile: {problem}.") from None
        except http.client.HTTPException as e:   # risponde qualcosa che non e' un server web
            self.last_error = str(e)
            raise EngineUnavailable(f"{self.base} non risponde come un Germano Server ({e.__class__.__name__}).") from None
        try:
            out = json.loads(body.decode("utf-8"))
        except ValueError:
            raise EngineUnavailable(f"Risposta non valida dal Germano Server {self.base}.") from None
        self.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        self.last_ok = time.time()
        self.last_error = ""
        return out

    # ------------------------------------------------------------------ ciclo di vita
    def load(self, settings=None):
        info = self._call("/info", timeout=10)
        if int(info.get("api") or 0) != API_VERSION:
            raise EngineUnavailable(f"Il Germano Server {self.base} usa una versione dell'API del motore non "
                                    "compatibile: aggiorna server e client alla stessa versione.")
        if info.get("engine_mode") == "remote":
            raise EngineUnavailable(f"Il Germano Server {self.base} delega a sua volta il motore a un altro "
                                    "server: scegline uno con il motore locale.")
        if not info.get("engine_ready"):
            raise EngineUnavailable(f"Il motore del Germano Server {self.base} non e' ancora pronto.")
        self.ocr_reader = True if info.get("ocr") else None
        self.info = {
            "mode": "remote", "server": self.base, "server_name": info.get("name"),
            "server_version": info.get("version"), "device": info.get("device"), "precision": info.get("precision"),
            "privacy_filter": bool(info.get("privacy_filter")), "italian_ner": bool(info.get("italian_ner")),
            "ocr": bool(info.get("ocr")), "latency_ms": self.latency_ms, "ok": True, "error": "",
        }
        return self.info

    def ping(self):
        """Controllo periodico (non solleva eccezioni): aggiorna latenza e raggiungibilita' del server."""
        try:
            self._call("/info", timeout=5)
            self.info.update(ok=True, latency_ms=self.latency_ms, error="")
        except EngineUnavailable as e:
            self.info.update(ok=False, error=str(e))
        return bool(self.info.get("ok"))

    def clear_cache(self):
        with self.lock:
            self._cache.clear()

    # ------------------------------------------------------------------ testo
    def classify_many(self, texts, settings, cancel=None):
        """Come Engine.classify_many: per ogni testo gli span grezzi [(start, end, gruppo, score)]."""
        cancel = cancel or NO_CANCEL
        sub = {k: settings.get(k) for k in TEXT_SETTINGS}
        flags = json.dumps(sub, sort_keys=True)
        results = [[] for _ in texts]
        pending = []
        for i, t in enumerate(texts):
            if not isinstance(t, str) or not t.strip():
                continue
            key = hashlib.sha1((flags + "\x00" + t).encode("utf-8", "surrogatepass")).hexdigest()
            with self.lock:
                hit = self._cache.get(key)
                if hit is not None:
                    self._cache.move_to_end(key)
            if hit is not None:
                results[i] = list(hit)
            else:
                pending.append((i, key))
        batch, size = [], 0
        for item in pending:
            tlen = len(texts[item[0]])
            if batch and (len(batch) >= _MAX_BATCH_TEXTS or size + tlen > _MAX_BATCH_CHARS):
                self._classify_batch(texts, batch, size, sub, results, cancel)
                batch, size = [], 0
            batch.append(item)
            size += tlen
        if batch:
            self._classify_batch(texts, batch, size, sub, results, cancel)
        return results

    def _classify_batch(self, texts, batch, size, sub, results, cancel):
        cancel.check()
        timeout = min(3600, max(60, size / 400))   # su CPU circa 400 token/s: margine ampio
        if getattr(cancel, "deadline", None):
            timeout = max(5, min(timeout, cancel.deadline - time.time()))
        out = self._call("/classify", {"texts": [texts[i] for i, _ in batch], "settings": sub}, timeout=timeout)
        res = out.get("results")
        if not isinstance(res, list) or len(res) != len(batch):
            raise EngineUnavailable("Risposta incompleta dal motore remoto.")
        for (i, key), spans in zip(batch, res):
            clean = tuple((int(s[0]), int(s[1]), str(s[2]), float(s[3])) for s in spans or [])
            results[i] = list(clean)
            with self.lock:
                self._cache[key] = clean
                if len(self._cache) > self._cache_max:
                    self._cache.popitem(last=False)

    # ------------------------------------------------------------------ immagini
    @staticmethod
    def _png(img):
        from PIL import Image
        if not isinstance(img, Image.Image):
            img = Image.fromarray(img)
        buf = io.BytesIO()
        img.save(buf, format="PNG", compress_level=1)   # senza perdita: OCR e riquadri identici al locale
        return buf.getvalue()

    def ocr(self, img_rgb):
        """[(box4punti, testo, confidenza)] come EasyOCR.readtext(detail=1)."""
        if self.ocr_reader is None:
            return []
        out = self._call("/ocr", png=self._png(img_rgb), timeout=900)
        return [([[float(p[0]), float(p[1])] for p in box], str(text), float(conf))
                for box, text, conf in out.get("results") or []]

    def _boxes(self, path, img):
        out = self._call(path, png=self._png(img), timeout=600)
        return [tuple(float(v) for v in b[:5]) for b in out.get("results") or []]

    def detect_faces(self, img_rgb):
        return self._boxes("/faces", img_rgb)

    def detect_signatures(self, pil_img):
        return self._boxes("/signatures", pil_img)

    def detect_plates(self, pil_img):
        return self._boxes("/plates", pil_img)


def find_server(settings, timeout=1.5):
    """Primo Germano Server della LAN che condivide un motore locale pronto, esclusa questa installazione.
    Restituisce (url | None, elenco_server_trovati). A parita' di condizioni si preferisce un server con GPU."""
    from . import discovery
    found = discovery.discover(timeout=timeout, port=common.discovery_port(settings), broadcasts=discovery.broadcast_addresses(),
                               exclude_instance=settings.get("instance_id") or None)
    usable = [s for s in found if s.get("engine_shared") and s.get("engine_ready")]
    usable.sort(key=lambda s: 0 if str(s.get("device") or "").startswith("cuda") else 1)
    if not usable:
        return None, found
    s = usable[0]
    return f"http://{s['ip']}:{s['port']}", found
