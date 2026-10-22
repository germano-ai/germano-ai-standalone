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
from .vault import contains_tags, restore_text

MAX_BODY = 700 * 1024 * 1024
REQUEST_TIMEOUT = 900


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False  # su Windows SO_REUSEADDR permetterebbe a due processi di condividere la porta
    daemon_threads = True


def _ctx(daemon, mode, tag_map=None):
    return formats.Ctx(
        mode, dict(daemon.settings), engine=daemon.engine, vault=daemon.vault, tag_map=tag_map or {},
        cancel=CancelToken(deadline=time.time() + REQUEST_TIMEOUT, stop_check=daemon.should_stop),
    )


def handle_texts(daemon, body):
    texts = body.get("texts") or []
    if not isinstance(texts, list):
        raise ValueError("'texts' deve essere una lista di stringhe")
    ctx = _ctx(daemon, "anonymize")
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
                else:
                    self._json(404, {"error": "endpoint sconosciuto"})
            except CancelledError as e:
                self._json(503, {"error": f"elaborazione annullata ({e.reason})"})
            except formats.UnsupportedFormat as e:
                self._json(415, {"error": str(e)})
            except Exception as e:
                common.log(f"API interna: errore su {self.path}: {type(e).__name__}: {e}")
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

    srv = _Server(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True, name="internal-api").start()
    return port
