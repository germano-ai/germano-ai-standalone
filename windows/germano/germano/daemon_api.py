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
from .engine import CancelledError, CancelToken, interactive_scope
from .remote_engine import API_VERSION, TEXT_SETTINGS, EngineUnavailable
from .vault import contains_tags, restore_text

MAX_BODY = 700 * 1024 * 1024
REQUEST_TIMEOUT = 900
ENGINE_MAX_TEXTS = 256              # motore condiviso: limiti per richiesta di un client della LAN
ENGINE_MAX_CHARS = 2_000_000
ENGINE_MAX_IMAGE = 80 * 1024 * 1024
ENGINE_MAX_AUDIO = 200 * 1024 * 1024
EXTRACT_MAX_CHARS = 3_000_000


class EngineDelegated(Exception):
    """Questo computer usa a sua volta un motore remoto: non puo' condividere il proprio (niente catene)."""


# ------------------------------------------------------------------ file per percorso (turno 26)
# Server e demone girano sullo stesso computer e condividono la cartella dati: un file grande passa per percorso
# (state/uploads -> state/tmp) invece che in base64 dentro JSON, che costava ~4 copie in memoria per parte e la
# codifica/decodifica di ogni byte. Il base64 resta per compatibilita'. Si accettano solo percorsi dentro le cartelle
# temporanee di Germano (mai un file qualsiasi del disco, anche se l'API e' gia' protetta dal token).
def output_dir():
    return os.path.join(common.WORK_TMP_DIR, "out")


def _inside(path, roots):
    real = os.path.realpath(path)
    for root in roots:
        try:
            if os.path.commonpath([real, os.path.realpath(root)]) == os.path.realpath(root):
                return real
        except ValueError:                       # unita' diverse (Windows)
            continue
    return None


def local_input(path):
    """Percorso di un file d'ingresso preparato dal server: solo in state/uploads o state/tmp, solo file regolari."""
    real = _inside(path, (common.UPLOAD_DIR, common.WORK_TMP_DIR)) if isinstance(path, str) and path else None
    if real is None or not os.path.isfile(real):
        raise ValueError("percorso del file non consentito")
    return real


def _stage_input(body, dest, missing_msg="contenuto del file non valido (base64)"):
    """Scrive in `dest` il file della richiesta: dal percorso locale (collegamento o copia) oppure dal base64."""
    if body.get("src_path"):
        real = local_input(body["src_path"])
        try:
            os.link(real, dest)                  # stesso disco: istantaneo, nessuna copia
        except OSError:
            import shutil
            shutil.copyfile(real, dest)
        return
    try:
        data = base64.b64decode(body.get("data_b64") or "", validate=False)
    except Exception:
        raise ValueError(missing_msg)
    with open(dest, "wb") as f:
        f.write(data)


def _deliver_output(body, path):
    """File prodotto: per percorso in state/tmp/out (il server lo legge e lo cancella) o in base64."""
    if body.get("return_path"):
        import uuid
        os.makedirs(output_dir(), exist_ok=True)
        dest = os.path.join(output_dir(), uuid.uuid4().hex[:12] + os.path.splitext(path)[1][:16])
        os.replace(path, dest)
        return {"out_path": dest}
    with open(path, "rb") as f:
        return {"data_b64": base64.b64encode(f.read()).decode("ascii")}


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


def handle_engine_transcribe(daemon, body):
    """Motore condiviso: trascrizione di un file audio per un Germano in modalita' Client. Il file resta solo per
    la durata della richiesta in state/tmp; non viene salvato nulla, il Vault non viene toccato."""
    eng = _local_engine(daemon)
    data = None
    if body.get("src_path"):
        size = os.path.getsize(local_input(body["src_path"]))
    else:
        try:
            data = base64.b64decode(body.get("data_b64") or "", validate=True)
        except Exception:
            raise ValueError("file audio non valido")
        size = len(data)
    if not size or size > ENGINE_MAX_AUDIO:
        raise ValueError("file audio mancante o troppo grande")
    raw = body.get("settings") if isinstance(body.get("settings"), dict) else {}
    settings = {k: common._validate_value(k, raw.get(k, daemon.settings.get(k)), common.DEFAULT_SETTINGS[k])
                for k in ("speech_language", "speech_max_minutes")}
    name = common.safe_filename(body.get("filename") or "audio.bin", max_len=80)
    ctx = _ctx(daemon, "anonymize", op=body.get("op"))
    with ctx.tempdir() as d:
        src = os.path.join(d, name)
        if data is None:
            _stage_input(body, src)
        else:
            with open(src, "wb") as f:
                f.write(data)
            del data
        from .speech import SpeechError
        try:
            res = eng.transcribe(src, settings, ctx.cancel, extend=ctx.extend_deadline)
        except SpeechError as e:
            raise ValueError(str(e)) from None
    res["segments"] = [[float(s), float(e), str(t)] for s, e, t in res.get("segments") or []]
    return res


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False  # su Windows SO_REUSEADDR permetterebbe a due processi di condividere la porta
    daemon_threads = True


# Operazioni lunghe annullabili dal server web (es. l'utente interrompe dalla Glass Window mentre un allegato audio
# viene trascritto): il server indica un identificativo «op» nella richiesta e, se serve, lo annulla.
_CANCELLED_OPS = {}
_OPS_LOCK = threading.Lock()


def cancel_op(op):
    if isinstance(op, str) and 0 < len(op) <= 80:
        with _OPS_LOCK:
            now = time.time()
            for k in [k for k, t in _CANCELLED_OPS.items() if now - t > 6 * 3600]:
                _CANCELLED_OPS.pop(k, None)
            _CANCELLED_OPS[op] = now


def _ctx(daemon, mode, tag_map=None, settings=None, op=None):
    stop = daemon.should_stop
    if isinstance(op, str) and op:
        def stop(op=op):
            return daemon.should_stop() or op in _CANCELLED_OPS
    return formats.Ctx(
        mode, settings or dict(daemon.settings), engine=daemon.engine, vault=daemon.vault, tag_map=tag_map or {},
        cancel=CancelToken(deadline=time.time() + REQUEST_TIMEOUT, stop_check=stop),
    )


def handle_extract_text(daemon, body):
    """Testo di un allegato per l'Harness: documenti e archivi come nell'anteprima, file audio trascritti dal
    motore (anche dentro gli archivi). Il testo NON e' ancora protetto: il server lo passa subito ad anonymize_texts
    e non lo mostra ne' lo invia prima. Nessun dato viene salvato."""
    name = common.safe_filename(body.get("filename") or "allegato.bin", max_len=100)
    try:
        max_chars = max(1000, min(int(body.get("max_chars") or 200_000), EXTRACT_MAX_CHARS))
    except (TypeError, ValueError):
        max_chars = 200_000
    ctx = _ctx(daemon, "anonymize", op=body.get("op"))
    ext = os.path.splitext(name)[1].lower()
    kind = "audio" if ext in formats.AUDIO_EXTS else ("archive" if ext in formats.ARCHIVE_EXTS else "document")
    with ctx.tempdir() as d:
        src = os.path.join(d, name)
        _stage_input(body, src)
        try:
            text = formats.extract_text(src, ctx, max_chars)
        except formats.ProcessingError as e:
            return {"text": "", "kind": kind, "error": str(e)}
    out = {"text": text, "kind": kind}
    audio = ctx.shared.get("audio_info") or []
    if audio:
        out["audio"] = audio
    return out


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
    for i, (u, r) in enumerate(zip(units, res)):
        n = len(r)
        out.append({"anonymized": apply_replacements(u.text, r), "extracted_data": ctx.audit[k:k + n],
                    "system2": [d for d in ctx.system2 if d.get("unit") == i]})
        k += n
    daemon.vault.flush()
    # decisioni del Sistema 2 sui casi dubbi (confermati, rilasciati, incerti) per la trasparenza (Glass Window)
    return {"results": out, "elapsed": round(time.time() - t0, 3), "system2": ctx.system2}


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
    res = handle_texts(daemon, {"texts": [text]})
    r = res["results"][0]
    return {"anonymized": r["anonymized"], "extracted_data": r["extracted_data"], "system2": res["system2"]}


def handle_file(daemon, body):
    name = common.safe_filename(body.get("filename") or "file.bin")
    mode = body.get("mode", "auto")
    # opzioni di un client della rete (Remote Control, Germano Client): valgono solo per questo file
    settings, label = _client_settings(daemon, body.get("options"))
    daemon.vault.refresh()
    tm = daemon.vault.tag_map()
    ctx0 = _ctx(daemon, "anonymize")
    with ctx0.tempdir() as d:
        src_dir = os.path.join(d, "in")
        out_dir = os.path.join(d, "out")
        os.makedirs(src_dir)
        os.makedirs(out_dir)
        src = os.path.join(src_dir, name)
        _stage_input(body, src)
        if mode == "auto":
            mode = "anonymize"
            if daemon.settings.get("enable_deanonymize", True) and tm:
                try:
                    if contains_tags(formats.sample_text(src), tm):
                        mode = "restore"
                except Exception:
                    pass
        ctx = _ctx(daemon, mode, tm, settings=settings if mode == "anonymize" else None, op=body.get("op"))
        ctx.label_override = label if mode == "anonymize" else None
        out = formats.process_file(src, os.path.join(out_dir, name), ctx)
        result = {"filename": os.path.basename(out), "mode": mode}
        result.update(_deliver_output(body, out))
    daemon.vault.flush()
    result.update({
        "extracted_data": ctx.audit if mode == "anonymize" else [],
        "system2": ctx.system2 if mode == "anonymize" else [],
        "notes": ctx.notes,
        "reports": ctx.reports,          # estrazione degli archivi e trascrizioni audio (per il registro di audit)
    })
    return result


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
            # Corsia preferenziale (turno 26): le richieste dell'API (Proxy, Harness, API, client della rete) passano
            # davanti ai documenti della cartella input/ sui modelli condivisi (Privacy Filter, OCR, Sistema 2)
            with interactive_scope():
                self._dispatch(body)

        def _dispatch(self, body):
            try:
                if self.path == "/internal/anonymize_texts":
                    self._json(200, handle_texts(daemon, body))
                elif self.path == "/internal/anonymize_text":
                    self._json(200, handle_text(daemon, body))
                elif self.path == "/internal/process_file":
                    self._json(200, handle_file(daemon, body))
                elif self.path == "/internal/extract_text":
                    self._json(200, handle_extract_text(daemon, body))
                elif self.path == "/internal/cancel":
                    cancel_op(body.get("op"))
                    self._json(200, {"status": "ok"})
                elif self.path == "/internal/engine/transcribe":
                    self._json(200, handle_engine_transcribe(daemon, body))
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
            except formats.ProcessingError as e:
                # errore «previsto» del file (password, archivio rifiutato, audio troppo lungo...): messaggio chiaro
                self._json(422, {"error": str(e)})
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
