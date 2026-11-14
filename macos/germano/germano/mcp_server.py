"""Server MCP (Model Context Protocol) di Germano AI (0.95, turno 30).

Protocollo: JSON-RPC 2.0 con l'handshake initialize -> notifications/initialized delle revisioni 2025-11-25,
2025-06-18, 2025-03-26 e 2024-11-05 (versione negoziata: quella chiesta dal client se supportata, altrimenti la piu'
recente). Metodi: initialize, ping, tools/list, tools/call, resources/list, resources/read, resources/templates/list,
prompts/list, prompts/get, logging/setLevel. Strumenti, schemi e gestori arrivano dal registro canonico
germano/integrations.py (gli stessi di UTCP, OpenAPI e REST).

La revisione 2026-07-28 elimina l'handshake (richieste «stateless»): i client che la supportano sono «dual-era» e,
quando un server risponde come questo (server/discover sconosciuto; su HTTP 400 senza un errore «moderno"), tornano da
soli a initialize con una revisione precedente. Per questo server/discover risponde -32601 e una richiesta moderna senza
sessione riceve 400 con un errore JSON-RPC classico.

Trasporti
- Streamable HTTP: POST /mcp (risposta JSON; notifiche e risposte -> 202), GET /mcp con Accept text/event-stream -> 405
  (nessun flusso server->client: non servono notifiche spontanee), GET /mcp senza SSE -> descrizione JSON, DELETE /mcp
  chiude la sessione (Mcp-Session-Id). Le rotte Flask sono in server.py.
- SSE legacy (2024-11-05): GET /mcp/sse apre il flusso e annuncia l'endpoint, POST /mcp/messages?session_id=... -> 202 e
  la risposta arriva sul flusso (n8n e client meno recenti).
- stdio: «server.py --mcp-stdio» (o «python -m germano.mcp_server»). Messaggi JSON su righe; sullo stdout SOLO il
  protocollo (tutto il resto va su stderr). Se il Germano di questa cartella dati e' aperto, fa da ponte verso
  http://127.0.0.1:<porta>/mcp (stesso motore, stesse statistiche e stessi ambiti di ripristino); altrimenti lavora nel
  proprio processo con il motore e il Vault della stessa cartella dati: il motore (daemon.py) si avvia alla prima
  richiesta che lo richiede e si chiude con il client MCP. Il blocco della cartella dati (state/daemon.lock) garantisce
  un solo motore per cartella; se il motore e' gia' in esecuzione (Dashboard aperta in un secondo momento, altro client
  stdio) lo si usa tramite state/daemon.json. Il Vault e' scritto solo dal motore (SQLite in WAL); i processi server lo
  leggono soltanto. Opzioni: --mcp-bridge (solo ponte), --mcp-inprocess (mai ponte).
"""
import json
import os
import queue
import sys
import threading
import time
import uuid

from . import common
from . import integrations as gint

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
LATEST = PROTOCOL_VERSIONS[0]
DEFAULT_HTTP_VERSION = "2025-03-26"     # senza intestazione MCP-Protocol-Version (regola della 2025-06-18)
MODERN_VERSIONS = ("2026-07-28",)       # revisioni senza handshake: non supportate, i client dual-era ripiegano

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
RESOURCE_NOT_FOUND = -32002

INSTRUCTIONS = (
    "Germano AI protects personal data locally (anonymization with reversible placeholders such as [PERSONA_1]). "
    "INPUT: call germano_anonymize_text / germano_anonymize_file BEFORE sending data to any external system or AI and "
    "use only the anonymized result; germano_leak_check verifies an outgoing payload, germano_inspect_entities audits "
    "without changing anything. OUTPUT: germano_deanonymize_text / germano_deanonymize_file restore the original data "
    "only for the placeholders present in the reply. Restored data are personal data: if you run in the cloud, prefer "
    "output_path so they are written on the user's computer instead of being returned to you. If a tool answers "
    "status \"blocked\" the engine is not ready: do not send the data elsewhere.")


def _ver_at_least(version, minimum):
    return (version or DEFAULT_HTTP_VERSION) >= minimum


def negotiate(requested):
    return requested if requested in PROTOCOL_VERSIONS else LATEST


def error(rid, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": err}


def result(rid, res):
    return {"jsonrpc": "2.0", "id": rid, "result": res}


# ------------------------------------------------------------------------------------------------ sessioni
class Session:
    def __init__(self, principal="local", transport="mcp-http"):
        self.id = uuid.uuid4().hex
        self.principal = principal
        self.transport = transport
        self.protocol_version = None
        self.client_info = {}
        self.initialized = False
        self.created = self.last_seen = time.time()


class SessionStore:
    """Sessioni Streamable HTTP (Mcp-Session-Id): versione negoziata e identita' di chi l'ha aperta. Scadono dopo 24
    ore di inattivita' o al riavvio di Germano (il client riceve 404 e ripete initialize, come prevede la specifica)."""

    TTL = 24 * 3600
    MAX = 1000

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}

    def create(self, principal, transport="mcp-http"):
        s = Session(principal, transport)
        with self._lock:
            now = time.time()
            for sid in [k for k, v in self._items.items() if now - v.last_seen > self.TTL]:
                self._items.pop(sid, None)
            if len(self._items) >= self.MAX:
                oldest = min(self._items.values(), key=lambda v: v.last_seen)
                self._items.pop(oldest.id, None)
            self._items[s.id] = s
        return s

    def get(self, sid):
        with self._lock:
            s = self._items.get(sid or "")
            if s is None or time.time() - s.last_seen > self.TTL:
                self._items.pop(sid or "", None)
                return None
            s.last_seen = time.time()
            return s

    def delete(self, sid):
        with self._lock:
            return self._items.pop(sid or "", None) is not None

    def count(self):
        with self._lock:
            return len(self._items)


HTTP_SESSIONS = SessionStore()


class SseSession(Session):
    def __init__(self, principal):
        super().__init__(principal, "mcp-sse")
        self.queue = queue.Queue(maxsize=1000)
        self.closed = False


class SseHub:
    """Sessioni del trasporto SSE legacy: le risposte ai POST su /mcp/messages viaggiano sul flusso aperto."""

    MAX = 32

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}

    def open(self, principal):
        with self._lock:
            if len(self._items) >= self.MAX:
                return None
            s = SseSession(principal)
            self._items[s.id] = s
            return s

    def get(self, sid):
        with self._lock:
            s = self._items.get(sid or "")
            if s is not None:
                s.last_seen = time.time()
            return s

    def close(self, sid):
        with self._lock:
            s = self._items.pop(sid or "", None)
        if s is not None:
            s.closed = True

    def count(self):
        with self._lock:
            return len(self._items)


SSE_HUB = SseHub()


# ------------------------------------------------------------------------------------------------ dispatcher
def tool_list(version):
    out = []
    for t in gint.TOOLS:
        item = {"name": t["name"], "description": t["description"], "inputSchema": t["input"]}
        if _ver_at_least(version, "2025-03-26"):
            item["annotations"] = dict(t["annotations"], title=t["title"])
        if _ver_at_least(version, "2025-06-18"):
            item["title"] = t["title"]
            item["outputSchema"] = t["output"]
        out.append(item)
    return out


def _tool_call_result(res, version, is_error):
    text = json.dumps(res, ensure_ascii=False, indent=2)
    out = {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}
    if not is_error and _ver_at_least(version, "2025-06-18"):
        out["structuredContent"] = res
    return out


def _resources(version):
    out = []
    for r in gint.RESOURCES:
        item = {k: r[k] for k in ("uri", "name", "description", "mimeType")}
        if _ver_at_least(version, "2025-06-18"):
            item["title"] = r["title"]
        out.append(item)
    return out


def _prompts(version):
    out = []
    for p in gint.PROMPTS:
        item = {"name": p["name"], "description": p["description"], "arguments": p["arguments"]}
        if _ver_at_least(version, "2025-06-18"):
            item["title"] = p["title"]
        out.append(item)
    return out


def _initialize(params, session):
    requested = params.get("protocolVersion") if isinstance(params, dict) else None
    version = negotiate(requested if isinstance(requested, str) else None)
    session.protocol_version = version
    info = params.get("clientInfo") if isinstance(params, dict) else None
    session.client_info = info if isinstance(info, dict) else {}
    server_info = {"name": gint.SERVICE, "version": gint.version()}
    if _ver_at_least(version, "2025-06-18"):
        server_info["title"] = gint.TITLE
    return {"protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False},
                             "resources": {"subscribe": False, "listChanged": False},
                             "prompts": {"listChanged": False}},
            "serverInfo": server_info,
            "instructions": INSTRUCTIONS}


def handle(msg, session, ctx_factory):
    """Un messaggio JSON-RPC -> risposta (dict) oppure None per notifiche e risposte del client.
    `ctx_factory()` crea il CallContext di integrations per le chiamate agli strumenti."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return error(msg.get("id") if isinstance(msg, dict) else None, INVALID_REQUEST, "Invalid Request")
    method = msg.get("method")
    rid = msg.get("id")
    has_id = "id" in msg
    if method is None:
        return None                      # risposta del client (questo server non invia richieste): ignorata
    if not isinstance(method, str):
        return error(rid, INVALID_REQUEST, "Invalid Request")
    if not has_id:                       # notifica: mai una risposta
        if method == "notifications/initialized":
            session.initialized = True
        return None
    if rid is None or isinstance(rid, (bool, dict, list)):
        return error(None, INVALID_REQUEST, "Invalid Request: id must be a string or a number")
    params = msg.get("params")
    if params is not None and not isinstance(params, dict):
        return error(rid, INVALID_PARAMS, "params must be an object")
    params = params or {}
    version = session.protocol_version or DEFAULT_HTTP_VERSION
    try:
        if method == "initialize":
            return result(rid, _initialize(params, session))
        if method == "ping":
            return result(rid, {})
        if method == "tools/list":
            return result(rid, {"tools": tool_list(version)})
        if method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str) or name not in gint.BY_NAME:
                return error(rid, INVALID_PARAMS, f"Unknown tool: {str(name)[:80]}")
            ctx = ctx_factory()
            try:
                res = gint.call_tool(name, params.get("arguments"), ctx)
                return result(rid, _tool_call_result(res, version, False))
            except gint.ToolError as e:
                return result(rid, _tool_call_result(e.payload(ctx.lang, name), version, True))
        if method == "resources/list":
            return result(rid, {"resources": _resources(version)})
        if method == "resources/templates/list":
            return result(rid, {"resourceTemplates": []})
        if method == "resources/read":
            uri = params.get("uri")
            try:
                mime, text = gint.read_resource(uri, ctx_factory())
            except KeyError:
                return error(rid, RESOURCE_NOT_FOUND, "Resource not found", {"uri": str(uri)[:200]})
            return result(rid, {"contents": [{"uri": uri, "mimeType": mime, "text": text}]})
        if method == "prompts/list":
            return result(rid, {"prompts": _prompts(version)})
        if method == "prompts/get":
            try:
                return result(rid, gint.get_prompt(params.get("name"), params.get("arguments")))
            except KeyError:
                return error(rid, INVALID_PARAMS, f"Unknown prompt: {str(params.get('name'))[:80]}")
        if method == "logging/setLevel":
            return result(rid, {})
        if method == "completion/complete":
            return result(rid, {"completion": {"values": [], "total": 0, "hasMore": False}})
        return error(rid, METHOD_NOT_FOUND, f"Method not found: {method[:80]}")
    except Exception as e:               # mai dati nel messaggio: solo il tipo dell'errore
        common.log(f"MCP: errore interno su {method}: {type(e).__name__}: {e}")
        return error(rid, INTERNAL_ERROR, f"Internal error ({type(e).__name__})")


def handle_payload(payload, session, ctx_factory):
    """Messaggio singolo o lotto (array, revisione 2025-03-26). Restituisce (risposta | elenco | None)."""
    if isinstance(payload, list):
        if not payload:
            return error(None, INVALID_REQUEST, "Invalid Request: empty batch")
        out = [r for r in (handle(m, session, ctx_factory) for m in payload) if r is not None]
        return out or None
    return handle(payload, session, ctx_factory)


def is_initialize(payload):
    msgs = payload if isinstance(payload, list) else [payload]
    return any(isinstance(m, dict) and m.get("method") == "initialize" and "id" in m for m in msgs)


def modern_request(payload, header_version=None):
    """True per le richieste della revisione 2026-07-28 (senza handshake): versione nell'intestazione o in _meta."""
    if header_version in MODERN_VERSIONS:
        return True
    for m in payload if isinstance(payload, list) else [payload]:
        meta = ((m or {}).get("params") or {}).get("_meta") if isinstance(m, dict) else None
        if isinstance(meta, dict) and meta.get("io.modelcontextprotocol/protocolVersion") is not None:
            return True
        if isinstance(m, dict) and m.get("method") == "server/discover":
            return True
    return False


def legacy_only_error(rid=None):
    return error(rid, INVALID_REQUEST,
                 "This MCP server uses the initialize handshake (protocol revisions " + ", ".join(PROTOCOL_VERSIONS)
                 + "): send initialize first.", {"supported": list(PROTOCOL_VERSIONS)})


def server_description(base):
    """Descrizione per GET /mcp senza SSE (persone, strumenti di diagnosi)."""
    return {"name": gint.TITLE, "service": gint.SERVICE, "version": gint.version(), "protocol": "Model Context Protocol",
            "protocol_versions": list(PROTOCOL_VERSIONS),
            "transports": {"streamable_http": base + "/mcp", "sse": base + "/mcp/sse",
                           "stdio": "server.py --mcp-stdio"},
            "tools": [t["name"] for t in gint.TOOLS], "resources": [r["uri"] for r in gint.RESOURCES],
            "prompts": [p["name"] for p in gint.PROMPTS],
            "utcp": base + "/utcp", "openapi": base + "/openapi.json",
            "usage": "POST JSON-RPC 2.0 messages to /mcp (initialize first). Germano's guide: " + base + "/guide"}


# ------------------------------------------------------------------------------------------------ stdio
_STDIO = {"started": False, "proto": None}


def _isolate_stdout():
    """Lo stdout del processo porta SOLO messaggi del protocollo: il descrittore 1 viene rediretto su stderr (stampe,
    registri, processi figli) e il vero stdout resta riservato ai messaggi JSON-RPC."""
    if _STDIO["proto"] is not None:
        return _STDIO["proto"]
    try:
        sys.stdout.flush()
    except Exception:
        pass
    proto_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    _STDIO["proto"] = os.fdopen(proto_fd, "wb", buffering=0)
    return _STDIO["proto"]


def _log(msg):
    try:
        sys.stderr.write(f"[germano-mcp] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


def _local_port():
    """Porta del Germano aperto con QUESTA cartella dati: state/server.json (scritto dal server all'avvio), poi
    GERMANO_PORT, poi config.json."""
    info = common.read_json(os.path.join(common.STATE_DIR, "server.json"), {}) or {}
    ports = []
    for p in (info.get("port"), os.environ.get("GERMANO_PORT"), common.load_config().get("port"), 8181):
        try:
            p = int(p)
        except (TypeError, ValueError):
            continue
        if 1024 <= p <= 65535 and p not in ports:
            ports.append(p)
    return ports


def _http(method, url, body=None, headers=None, timeout=3700):
    import urllib.error
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # mai attraverso un proxy di sistema
    req = urllib.request.Request(url, data=body, headers=dict(headers or {}), method=method)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        try:
            data = e.read()
        except OSError:
            data = b""
        return e.code, dict(e.headers.items()) if e.headers else {}, data


def find_local_germano():
    """Indirizzo del Germano aperto (stessa cartella dati) che risponde a /mcp, oppure None."""
    for port in _local_port():
        base = f"http://127.0.0.1:{port}"
        try:
            st, _h, body = _http("GET", base + "/api/status", timeout=3)
            if st != 200 or "version" not in json.loads(body.decode("utf-8", "replace") or "{}"):
                continue
            st2, _h2, body2 = _http("GET", base + "/mcp", headers={"Accept": "application/json"}, timeout=3)
            if st2 == 200 and json.loads(body2.decode("utf-8", "replace") or "{}").get("service") == gint.SERVICE:
                return base
        except Exception:
            continue
    return None


class _Bridge:
    """Inoltra i messaggi al Germano aperto (POST /mcp) conservando sessione e versione negoziata."""

    def __init__(self, base):
        self.base = base
        self.session_id = None
        self.version = None
        self.init_msg = None
        self._lock = threading.Lock()

    def _post(self, obj):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "X-Germano-Client": "mcp-stdio"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.version:
            headers["MCP-Protocol-Version"] = self.version
        return _http("POST", self.base + "/mcp", json.dumps(obj, ensure_ascii=False).encode("utf-8"), headers)

    def _reinit(self):
        """Sessione scaduta (Germano riavviato): nuova sessione con la stessa richiesta initialize del client."""
        self.session_id = None
        st, h, body = self._post(self.init_msg)
        if st != 200:
            raise ConnectionError(f"initialize HTTP {st}")
        self.session_id = h.get("Mcp-Session-Id") or h.get("mcp-session-id")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def send(self, payload):
        if is_initialize(payload):
            first = payload[0] if isinstance(payload, list) else payload
            self.init_msg = first
        st, h, body = self._post(payload)
        if st == 404 and self.init_msg is not None and not is_initialize(payload):
            with self._lock:
                self._reinit()
            st, h, body = self._post(payload)
        if st == 202:
            return None
        sid = h.get("Mcp-Session-Id") or h.get("mcp-session-id")
        if sid:
            self.session_id = sid
        data = json.loads(body.decode("utf-8")) if body else None
        if is_initialize(payload) and isinstance(data, dict) and isinstance(data.get("result"), dict):
            self.version = data["result"].get("protocolVersion")
        return data


def _serve(dispatch, on_exit=None):
    """Ciclo stdio: una riga JSON per messaggio. initialize, notifiche e ping in ordine; il resto in parallelo."""
    from concurrent.futures import ThreadPoolExecutor
    out = _STDIO["proto"]
    lock = threading.Lock()

    def write(obj):
        if obj is None:
            return
        data = (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        with lock:
            out.write(data)
            out.flush()

    def run(payload):
        try:
            write(dispatch(payload))
        except Exception as e:
            _log(f"errore: {type(e).__name__}: {e}")
            ids = [m.get("id") for m in (payload if isinstance(payload, list) else [payload])
                   if isinstance(m, dict) and "id" in m and m.get("method")]
            for rid in ids:
                write(error(rid, INTERNAL_ERROR, f"Internal error ({type(e).__name__})"))

    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="germano-mcp")
    try:
        for raw in sys.stdin.buffer:
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                write(error(None, PARSE_ERROR, "Parse error"))
                continue
            first = payload[0] if isinstance(payload, list) and payload else payload
            method = first.get("method") if isinstance(first, dict) else None
            if method in ("initialize", "ping") or (isinstance(first, dict) and "id" not in first):
                run(payload)
            else:
                pool.submit(run, payload)
    finally:
        pool.shutdown(wait=True)
        if on_exit:
            try:
                on_exit()
            except Exception:
                pass
    return 0


class _InProcess:
    """Dispatcher nel processo: stesso registro, motore e Vault della cartella dati di Germano."""

    def __init__(self, backend, port, version=None):
        self.backend = backend
        self.session = Session("local", "mcp-stdio")
        if version:
            self.session.protocol_version = version
            self.session.initialized = True
        self.base = f"http://127.0.0.1:{port}"

    def ctx(self):
        lang = "en" if (os.environ.get("GERMANO_LANG") or "").lower().startswith("en") else "it"
        return gint.CallContext(self.backend, local=True, principal="local", lang=lang, transport="mcp-stdio",
                                base_url=self.base)

    def __call__(self, payload):
        # server/discover (sonda dei client dual-era 2026-07-28) riceve -32601 come ogni metodo sconosciuto: il client
        # torna da solo a initialize con una revisione supportata
        return handle_payload(payload, self.session, self.ctx)


def _inprocess_port():
    ports = _local_port()
    return ports[0] if ports else 8181


def stdio_main_early():
    """Da chiamare all'inizio di server.py con --mcp-stdio, PRIMA degli import pesanti. Ponte verso il Germano aperto
    (non ritorna) oppure ritorna per la modalita' nel processo (il chiamante completa il caricamento e chiama
    stdio_main_inprocess)."""
    if _STDIO["started"]:
        return
    _STDIO["started"] = True
    _isolate_stdout()
    if "--mcp-inprocess" in sys.argv:
        _log("modalita' nel processo (--mcp-inprocess)")
        return
    base = find_local_germano()
    if base is None:
        if "--mcp-bridge" in sys.argv:
            _log("nessun Germano aperto con questa cartella dati: impossibile fare da ponte (--mcp-bridge).")
            sys.exit(1)
        _log("nessun Germano aperto: modalita' nel processo (motore e Vault della cartella dati)")
        return
    _log(f"ponte verso {base}/mcp")
    sys.exit(_run_bridge(base))


def _run_bridge(base):
    bridge = _Bridge(base)
    state = {"local": None}

    def dispatch(payload):
        if state["local"] is not None:
            return state["local"](payload)
        try:
            return bridge.send(payload)
        except (OSError, ConnectionError, ValueError) as e:
            _log(f"Germano non raggiungibile ({type(e).__name__}): passo alla modalita' nel processo")
            state["local"] = _InProcess(_load_backend(), _inprocess_port(), bridge.version)
            return state["local"](payload)

    def on_exit():
        if state["local"] is not None:
            state["local"].backend.shutdown()

    return _serve(dispatch, on_exit)


def _load_backend():
    """Backend del server (stesse funzioni della Dashboard) caricato come modulo, senza aprire porte."""
    import importlib
    base = common.BASE_DIR
    if base not in sys.path:
        sys.path.insert(0, base)
    srv = sys.modules.get("server") or importlib.import_module("server")
    return srv.integration_backend()


def stdio_main_inprocess(backend):
    """Modalita' nel processo (server.py --mcp-stdio senza Germano aperto, o --mcp-inprocess)."""
    _isolate_stdout()
    dispatcher = _InProcess(backend, _inprocess_port())
    return _serve(dispatcher, backend.shutdown)


def main():
    """python -m germano.mcp_server [--mcp-bridge | --mcp-inprocess] (dalla cartella del programma)."""
    common.setup_offline_env()
    _STDIO["started"] = True
    _isolate_stdout()
    base = None if "--mcp-inprocess" in sys.argv else find_local_germano()
    if base:
        _log(f"ponte verso {base}/mcp")
        return _run_bridge(base)
    if "--mcp-bridge" in sys.argv:
        _log("nessun Germano aperto con questa cartella dati: impossibile fare da ponte (--mcp-bridge).")
        return 1
    _log("modalita' nel processo (motore e Vault della cartella dati)")
    backend = _load_backend()
    return stdio_main_inprocess(backend)


if __name__ == "__main__":
    sys.exit(main())
