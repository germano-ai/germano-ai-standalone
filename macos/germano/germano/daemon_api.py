"""API interna del demone: solo 127.0.0.1, porta dinamica, richieste autenticate con token.
Usata dal server web per Proxy API, API REST e strumento testo della dashboard."""
import base64
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import common, formats
from .analyzer import Unit, apply_replacements
from .engine import CancelledError, CancelToken
from .remote_engine import API_VERSION, TEXT_SETTINGS, EngineUnavailable
from .vault import contains_tags, restore_text

MAX_BODY = 700 * 1024 * 1024
REQUEST_TIMEOUT = 900
ENGINE_MAX_TEXTS = 256              # motore condiviso: limiti per richiesta di un client della LAN
ENGINE_MAX_CHARS = 2_000_000
ENGINE_MAX_IMAGE = 80 * 1024 * 1024


class EngineDelegated(Exception):
    """Questo computer usa a sua volta un motore remoto: non puo' condividere il proprio (niente catene)."""


# ------------------------------------------------------------------ motore condiviso (modalita' Server)
# Inferenza pura sul motore locale: nessun accesso al Vault, nessuna etichetta, nessun dato salvato.
# La cache del motore conserva solo posizioni, categorie e punteggi, mai il testo.
def _local_engine(daemon):
    if getattr(daemon.engine, "is_remote", False):
        raise EngineDelegated()
    return daemon.engine


def handle_engine_info(daemon):
    eng = _local_engine(daemon)
    info = dict(getattr(eng, "info", {}) or {})
    info.update(api=API_VERSION, engine_ready=True, engine_mode="local")
    return info


def handle_engine_classify(daemon, body):
    eng = _local_engine(daemon)
    texts = body.get("texts")
    if not isinstance(texts, list) or len(texts) > ENGINE_MAX_TEXTS:
        raise ValueError(f"'texts' deve essere una lista di al massimo {ENGINE_MAX_TEXTS} stringhe")
    texts = [t if isinstance(t, str) else "" for t in texts]
    if sum(len(t) for t in texts) > ENGINE_MAX_CHARS:
        raise ValueError("richiesta troppo grande per il motore condiviso")
    raw = body.get("settings") if isinstance(body.get("settings"), dict) else {}
    # Vale la politica del client (modelli e soglia), validata come se fosse in config.json.
    settings = {k: common._validate_value(k, raw.get(k, daemon.settings.get(k)), common.DEFAULT_SETTINGS[k])
                for k in TEXT_SETTINGS}
    cancel = CancelToken(deadline=time.time() + REQUEST_TIMEOUT, stop_check=daemon.should_stop)
    res = eng.classify_many(texts, settings, cancel)
    return {"results": [[[int(s[0]), int(s[1]), str(s[2]), float(s[3])] for s in spans] for spans in res]}


def handle_engine_image(daemon, body, kind):
    import base64 as b64
    import io
    eng = _local_engine(daemon)
    try:
        data = b64.b64decode(body.get("png_b64") or "", validate=True)
    except Exception:
        raise ValueError("immagine non valida")
    if not data or len(data) > ENGINE_MAX_IMAGE:
        raise ValueError("immagine mancante o troppo grande")
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if kind == "ocr":
        out = eng.ocr(np.asarray(img))
        return {"results": [[[[float(p[0]), float(p[1])] for p in box], str(text), float(conf)]
                            for box, text, conf in out or []]}
    if kind == "faces":
        out = eng.detect_faces(np.asarray(img))
    elif kind == "signatures":
        out = eng.detect_signatures(img)
    elif kind == "plates":
        out = eng.detect_plates(img)
    else:
        raise ValueError("tipo di analisi sconosciuto")
    return {"results": [[float(v) for v in b[:5]] for b in out or []]}


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False  # su Windows SO_REUSEADDR permetterebbe a due processi di condividere la porta
    daemon_threads = True


def _ctx(daemon, mode, tag_map=None, settings=None):
    return formats.Ctx(
        mode, settings or dict(daemon.settings), engine=daemon.engine, vault=daemon.vault, tag_map=tag_map or {},
        cancel=CancelToken(deadline=time.time() + REQUEST_TIMEOUT, stop_check=daemon.should_stop),
    )


def _client_settings(daemon, options):
    """Impostazioni per UNA richiesta con le opzioni scelte da un client della rete (Remote Control, Germano Client).
    Profilo PA o lock_settings: le opzioni dei client non valgono, restano quelle del server."""
    base = dict(daemon.settings)
    if not isinstance(options, dict) or common.options_locked(base):
        return base, None
    settings, label = common.options_to_settings(common.validate_options(options, base))
    base.update(settings)
    return base, label


def handle_texts(daemon, body):
    texts = body.get("texts") or []
    if not isinstance(texts, list):
        raise ValueError("'texts' deve essere una lista di stringhe")
    settings, label = _client_settings(daemon, body.get("options"))
    ctx = _ctx(daemon, "anonymize", settings=settings)
    ctx.label_override = label
    units = [Unit(t if isinstance(t, str) else "") for t in texts]
    t0 = time.time()
    res = ctx.analyze(units, batch_context=bool(body.get("batch_context", False)))
    out = []
    k = 0
    for u, r in zip(units, res):
        n = len(r)
        out.append({"anonymized": apply_replacements(u.text, r), "extracted_data": ctx.audit[k:k + n]})
        k += n
    daemon.vault.flush()
    return {"results": out, "elapsed": round(time.time() - t0, 3)}


def handle_text(daemon, body):
    text = body.get("text", "")
    if not isinstance(text, str):
        text = str(text)
    force = bool(body.get("force_anonymize", False))
    if not force and daemon.settings.get("enable_deanonymize", True):
        daemon.vault.refresh()
        tm = daemon.vault.tag_map()
        if contains_tags(text, tm):
            restored = restore_text(text, tm)
            return {"anonymized": restored, "restored": restored, "auto_restored": True, "extracted_data": []}
    r = handle_texts(daemon, {"texts": [text]})["results"][0]
    return {"anonymized": r["anonymized"], "extracted_data": r["extracted_data"]}


def handle_file(daemon, body):
    try:
        data = base64.b64decode(body.get("data_b64") or "", validate=False)
    except Exception:
        raise ValueError("contenuto del file non valido (base64)")
    name = common.safe_filename(body.get("filename") or "file.bin")
    mode = body.get("mode", "auto")
    daemon.vault.refresh()
    tm = daemon.vault.tag_map()
    ctx0 = _ctx(daemon, "anonymize")
    with ctx0.tempdir() as d:
        src_dir = os.path.join(d, "in")
        out_dir = os.path.join(d, "out")
        os.makedirs(src_dir)
        os.makedirs(out_dir)
        src = os.path.join(src_dir, name)
        with open(src, "wb") as f:
            f.write(data)
        if mode == "auto":
            mode = "anonymize"
            if daemon.settings.get("enable_deanonymize", True) and tm:
                try:
                    if contains_tags(formats.sample_text(src), tm):
                        mode = "restore"
                except Exception:
                    pass
        ctx = _ctx(daemon, mode, tm)
        out = formats.process_file(src, os.path.join(out_dir, name), ctx)
        with open(out, "rb") as f:
            new_data = f.read()
    daemon.vault.flush()
    return {
        "filename": os.path.basename(out),
        "mode": mode,
        "data_b64": base64.b64encode(new_data).decode("ascii"),
        "extracted_data": ctx.audit if mode == "anonymize" else [],
        "notes": ctx.notes,
    }


def start_api(daemon):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _json(self, code, obj):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _auth(self):
            if self.headers.get("X-Germano-Token") != daemon.token:
                self._json(403, {"error": "token non valido"})
                return False
            return True

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("richiesta troppo grande")
            raw = self.rfile.read(n) if n else b"{}"
            obj = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(obj, dict):
                raise ValueError("JSON non valido")
            return obj

        def do_GET(self):
            if not self._auth():
                return
            if self.path == "/internal/health":
                self._json(200, {"status": "ok", "pid": os.getpid(), "engine": daemon.engine.info})
            elif self.path == "/internal/engine/info":
                try:
                    self._json(200, handle_engine_info(daemon))
                except EngineDelegated:
                    self._json(409, {"error": "questo computer usa a sua volta un motore remoto", "engine_mode": "remote"})
            else:
                self._json(404, {"error": "endpoint sconosciuto"})

        def do_POST(self):
            if not self._auth():
                return
            try:
                body = self._body()
            except Exception as e:
                self._json(400, {"error": str(e)})
                return
            reload = getattr(daemon, "reload_settings", None)
            if reload:
                reload()     # impostazioni attuali anche subito dopo un cambio (es. profilo PA/PD, opzioni dei client)
            try:
                if self.path == "/internal/anonymize_texts":
                    self._json(200, handle_texts(daemon, body))
                elif self.path == "/internal/anonymize_text":
                    self._json(200, handle_text(daemon, body))
                elif self.path == "/internal/process_file":
                    self._json(200, handle_file(daemon, body))
                elif self.path == "/internal/vault/clear":
                    daemon.vault.clear()
                    daemon.engine.clear_cache()
                    self._json(200, {"status": "ok"})
                elif self.path == "/internal/stop":
                    daemon.stop_event.set()
                    self._json(200, {"status": "ok"})
                elif self.path == "/internal/engine/classify":
                    self._json(200, handle_engine_classify(daemon, body))
                elif self.path.startswith("/internal/engine/") and self.path.rsplit("/", 1)[-1] in (
                        "ocr", "faces", "signatures", "plates"):
                    self._json(200, handle_engine_image(daemon, body, self.path.rsplit("/", 1)[-1]))
                else:
                    self._json(404, {"error": "endpoint sconosciuto"})
            except EngineDelegated:
                self._json(409, {"error": "questo computer usa a sua volta un motore remoto", "engine_mode": "remote"})
            except EngineUnavailable as e:
                # Modalita' Client: il server remoto non risponde. Nulla e' stato inviato al cloud.
                self._json(503, {"error": str(e)})
            except CancelledError as e:
                self._json(503, {"error": f"elaborazione annullata ({e.reason})"})
            except formats.UnsupportedFormat as e:
                self._json(415, {"error": str(e)})
            except ValueError as e:
                if self.path.startswith("/internal/engine/"):
                    self._json(400, {"error": str(e)})
                else:
                    common.log(f"API interna: errore su {self.path}: {type(e).__name__}: {e}")
                    self._json(500, {"error": f"{type(e).__name__}: {e}"})
            except Exception as e:
                common.log(f"API interna: errore su {self.path}: {type(e).__name__}: {e}")
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

    srv = _Server(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True, name="internal-api").start()
    return port
