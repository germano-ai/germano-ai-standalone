"""Germano AI - server locale: Dashboard web, API REST e Proxy API per IDE/agenti IA.

Ascolta sempre su 127.0.0.1; solo con la parte Server della modalita' operativa si aggiunge un secondo ascolto
sulla rete locale (token obbligatorio per Proxy, Studio e motore condiviso). Avvia il demone IA (daemon.py) su
richiesta e lo controlla tramite i file in state/ e un'API interna protetta da token.
"""
import io
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
import atexit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from germano import common  # noqa: E402

common.setup_offline_env()
common.force_utf8_stdio()

import json  # noqa: E402
import logging  # noqa: E402

import psutil  # noqa: E402
import requests  # noqa: E402
from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context  # noqa: E402

from germano.vault import VaultReader, contains_tags, restore_text  # noqa: E402
from germano import updater as gupdater  # noqa: E402

APP_VERSION = common.get_version()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 ** 3
logging.getLogger("werkzeug").setLevel(logging.ERROR)

CFG = common.load_config()
PORT = int(os.environ.get("GERMANO_PORT") or CFG.get("port") or 8181)
# Il server principale ascolta SEMPRE solo su 127.0.0.1 (Dashboard e CLI di questo computer). La parte "Server"
# della modalita' operativa aggiunge un secondo listener sulla rete (0.0.0.0, oppure l'IP indicato in bind_host)
# che si accende e si spegne dalle Impostazioni senza riavviare: in Standalone e in Client nessuna porta di
# Germano e' aperta verso la rete.
MAIN_HOST = "127.0.0.1"
_cfg_host = (os.environ.get("GERMANO_HOST") or CFG.get("bind_host") or "").strip()
LAN_HOST = _cfg_host if _cfg_host and _cfg_host not in ("127.0.0.1", "localhost", "::1") else "0.0.0.0"
DISCOVERY_PORT = common.discovery_port(CFG)
LAN_MODE = False                                     # True mentre il listener di rete e' attivo
LAN_TOKEN = CFG.get("lan_token") or ""              # generato quando si attiva la parte Server
MACHINE_NAME = socket.gethostname().lower()
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MODE_LABELS = {"standalone": "Standalone", "server": "Server", "client": "Client", "server+client": "Server + Client"}


def _lang():
    """Lingua dei messaggi: intestazione X-Germano-Lang (API, script) oppure il cookie germano_lang che la Dashboard
    imposta con le bandierine IT/EN. Senza indicazioni si risponde in italiano, come nelle versioni precedenti."""
    try:
        value = request.headers.get("X-Germano-Lang") or request.cookies.get("germano_lang") or ""
    except RuntimeError:   # fuori da una richiesta HTTP (es. all'avvio)
        return "it"
    return "en" if value.strip().lower().startswith("en") else "it"


def _L(it, en):
    return en if _lang() == "en" else it

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
# Dalla LAN SENZA token: sola lettura, nessun dato personale.
_LAN_OPEN = ("/", "/guide", "/guide.html", "/static/", "/favicon.ico",
             "/api/status", "/api/ai/detect", "/api/discovery")
# Dalla LAN CON token condiviso: Proxy verso le AI, protezione dello Studio e motore condiviso.
_LAN_TOKEN_PATHS = ("/v1/messages", "/messages", "/v1/chat/completions", "/chat/completions",
                    "/v1/responses", "/responses", "/v1/models", "/models", "/api/studio/send",
                    "/api/engine/v1/", "/api/harness/v1/")
# Tutto il resto (controllo motore, impostazioni, modalita', vault, de-anonimizzazione, file) resta SOLO locale.


def _path_matches(path, prefixes):
    for p in prefixes:
        if p == "/":
            if path == "/":        # la radice e' solo esatta, non un prefisso di tutto
                return True
        elif p.endswith("/"):
            if path.startswith(p):
                return True
        elif path == p or path.startswith(p + "/"):
            return True
    return False


def _remote_is_local():
    ra = request.remote_addr or ""
    return ra in _LOOPBACK or ra.startswith("127.") or ra == "::1"


def _host_allowed(hostname):
    """Anti DNS-rebinding: si accettano solo loopback, IP letterali e il nome di questo computer
    (un dominio controllato da un attaccante non corrisponde a nessuno di questi)."""
    if hostname in _LOOPBACK or hostname == "[::1]":
        return True
    h = hostname.strip("[]")
    try:
        import ipaddress
        ipaddress.ip_address(h)
        return True
    except ValueError:
        pass
    sn = (CFG.get("server_name") or "").lower()
    return hostname == MACHINE_NAME or (bool(sn) and hostname == sn)


def _origin_allowed(origin):
    from urllib.parse import urlparse
    try:
        o = urlparse(origin)
    except Exception:
        return False
    hn = (o.hostname or "").lower()
    if not hn:
        return False
    if hn in _LOOPBACK or hn.startswith("127."):
        return True
    return hn == (request.host or "").split(":")[0].lower()   # stessa origine del server (LAN)


def _lan_token_ok():
    import hmac
    tok = request.environ.get("germano.token") or request.headers.get("X-Germano-Auth", "")
    return bool(LAN_TOKEN) and hmac.compare_digest(str(tok), LAN_TOKEN)


# Prefisso opzionale /g/<token> nel percorso: permette a qualunque client (anche CLI che non inviano header
# personalizzati) di autenticarsi alla LAN tramite il solo Base URL, es. http://<server>:8181/g/<token>/v1
_real_wsgi_app = app.wsgi_app


def _wsgi_token_prefix(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if path.startswith("/g/"):
        tok, _, tail = path[3:].partition("/")
        environ["germano.token"] = tok
        environ["PATH_INFO"] = "/" + tail
    return _real_wsgi_app(environ, start_response)


app.wsgi_app = _wsgi_token_prefix

vault_reader = VaultReader()
UPDATER = gupdater.Updater()
_spawn_lock = threading.Lock()
_cache = {}
_DISCOVERY = None  # responder UDP di rilevamento (avviato in main() quando il server ascolta sulla LAN)
_daemon_http = requests.Session()
_daemon_http.trust_env = False  # le chiamate a 127.0.0.1 non devono mai passare da un proxy aziendale
_upstream = requests.Session()  # verso gli LLM: usa proxy di sistema/ambiente se configurati
common.ensure_dirs()


def cached(key, ttl, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


# ------------------------------------------------------------------------------------------------
# Modalita' operativa: Standalone / Server / Client / Server + Client
# ------------------------------------------------------------------------------------------------
_MODE_LOCK = threading.RLock()
_LAN_SERVER = None   # listener werkzeug sulla rete (parte Server)


def _ensure_identity():
    """instance_id univoco per installazione e computer (serve a non rilevare se stessi in rete). Se la cartella
    del programma e' stata copiata da un altro PC, l'identificativo viene rigenerato."""
    cfg = common.load_config()
    if not cfg.get("instance_id") or (cfg.get("instance_host") or "") != MACHINE_NAME:
        common.save_config({"instance_id": uuid.uuid4().hex, "instance_host": MACHINE_NAME}, admin=True)


def _ensure_lan_token():
    global LAN_TOKEN
    if not LAN_TOKEN:
        LAN_TOKEN = common.load_config().get("lan_token") or uuid.uuid4().hex
        common.save_config({"lan_token": LAN_TOKEN}, admin=True)
    return LAN_TOKEN


def _start_lan_listener():
    """Parte Server: secondo listener sulla rete + rilevamento UDP. Restituisce un messaggio d'errore o None."""
    global _LAN_SERVER, LAN_MODE, _DISCOVERY
    with _MODE_LOCK:
        if _LAN_SERVER is not None:
            return None
        _ensure_lan_token()
        from werkzeug.serving import make_server
        try:
            srv = make_server(LAN_HOST, PORT, app, threaded=True)
        except OSError as e:
            return _L(f"impossibile mettersi in ascolto sulla rete ({LAN_HOST}:{PORT}): {e}",
                      f"cannot listen on the network ({LAN_HOST}:{PORT}): {e}")
        threading.Thread(target=srv.serve_forever, name="germano-lan", daemon=True).start()
        _LAN_SERVER = srv
        LAN_MODE = True
        if common.load_config().get("discovery_enabled", True) and _DISCOVERY is None:
            try:
                from germano import discovery as gdiscovery
                _DISCOVERY = gdiscovery.DiscoveryResponder(_server_info, DISCOVERY_PORT)
                _DISCOVERY.start()
            except Exception as e:
                _DISCOVERY = None
                return _L(f"in ascolto sulla rete, ma il rilevamento automatico (UDP {DISCOVERY_PORT}) non e' partito: {e}",
                          f"listening on the network, but auto-discovery (UDP {DISCOVERY_PORT}) did not start: {e}")
        return None


def _stop_lan_listener():
    """Spegne la parte Server: da quel momento i computer della rete non raggiungono piu' Germano."""
    global _LAN_SERVER, LAN_MODE, _DISCOVERY
    with _MODE_LOCK:
        LAN_MODE = False
        if _DISCOVERY is not None:
            try:
                _DISCOVERY.stop()
            except Exception:
                pass
            _DISCOVERY = None
        if _LAN_SERVER is not None:
            srv, _LAN_SERVER = _LAN_SERVER, None
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass


def _apply_operating_mode():
    """Applica dal vivo la modalita' in vigore (rete accesa/spenta). Restituisce (modalita', avvisi)."""
    mode = common.effective_operating_mode(common.load_config())
    server_on, _client_on = common.mode_flags(mode)
    notes = []
    if server_on:
        err = _start_lan_listener()
        if err:
            notes.append(err)
    else:
        _stop_lan_listener()
    return mode, notes


def _restart_daemon():
    try:
        stop_daemon()
        time.sleep(0.5)
        start_daemon()
    except Exception as e:
        common.log(f"Riavvio del motore non riuscito: {e}")


def _sync_engine(prev_mode, new_mode, prev_remote, cfg):
    """Il tipo di motore (locale o remoto) si sceglie all'avvio del demone: se cambia la parte Client, o i dati
    del server remoto, il motore in esecuzione si riavvia. Server e Client avviano il motore da soli."""
    prev_client = common.mode_flags(prev_mode)[1]
    new_client = common.mode_flags(new_mode)[1]
    remote_now = (cfg.get("remote_server"), cfg.get("remote_token"), cfg.get("client_fallback_local"))
    running = is_daemon_running()
    if running and (prev_client != new_client or (new_client and remote_now != prev_remote)):
        threading.Thread(target=_restart_daemon, name="germano-restart", daemon=True).start()
        return "restart"
    if not running and new_mode != "standalone":
        start_daemon()
        return "start"
    return None


# ------------------------------------------------------------------------------------------------
# Sicurezza: solo host locali (anti DNS-rebinding) e nessuna azione da siti web esterni (anti CSRF)
# ------------------------------------------------------------------------------------------------
@app.before_request
def _guard():
    host = (request.host or "").lower()
    hostname = host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]
    if not _host_allowed(hostname):
        return jsonify({"error": _L("Host non consentito: usa l'indirizzo IP del server.",
                                    "Host not allowed: use the server's IP address.")}), 403

    if not _remote_is_local():
        # Richiesta da un altro computer della rete locale.
        if not LAN_MODE:
            return jsonify({"error": _L("Germano non e' in ascolto sulla rete locale: accetta solo connessioni dal server.",
                                        "Germano is not listening on the local network: it only accepts connections "
                                        "from the server itself.")}), 403
        path = request.path
        if _path_matches(path, _LAN_OPEN):
            pass  # sola lettura, nessun dato personale
        elif _path_matches(path, _LAN_TOKEN_PATHS):
            if not _lan_token_ok():   # senza un token valido (o se il server non ne ha) l'accesso e' sempre negato
                return jsonify({"error": _L("Accesso negato: token di Germano Server mancante o errato. "
                                            "Imposta il Base URL come http://<server>:%d/g/<token>/v1 oppure "
                                            "l'intestazione X-Germano-Auth." % PORT,
                                            "Access denied: Germano Server token missing or wrong. Set the Base URL "
                                            "as http://<server>:%d/g/<token>/v1 or the X-Germano-Auth header." % PORT)}), 401
        else:
            return jsonify({"error": _L("Operazione riservata al computer del server (accessibile solo in locale).",
                                        "Operation reserved to the server computer (local access only).")}), 403

    # Anti-CSRF: nessuna azione di modifica avviata da un sito web esterno.
    if request.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("Origin")
        if origin and not _origin_allowed(origin):
            return jsonify({"error": _L("Richiesta da un sito esterno bloccata.", "Request from an external site blocked.")}), 403
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return jsonify({"error": _L("Richiesta da un sito esterno bloccata.", "Request from an external site blocked.")}), 403
    return None


@app.after_request
def _headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.path in ("/", "/guide", "/guide.html"):
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ------------------------------------------------------------------------------------------------
# Demone IA
# ------------------------------------------------------------------------------------------------
def daemon_state():
    return common.read_json(common.DAEMON_STATE_FILE, {}) or {}


def is_daemon_running():
    st = daemon_state()
    pid = st.get("pid")
    if not pid:
        return False
    try:
        p = psutil.Process(int(pid))
        if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
            try:
                cmd = " ".join(p.cmdline() or [])
            except psutil.AccessDenied:
                return True
            if "daemon.py" in cmd:
                return True
    except (psutil.NoSuchProcess, ValueError):
        pass
    except psutil.AccessDenied:
        return True
    for f in (common.DAEMON_STATE_FILE, common.READY_FLAG, common.STATUS_FILE):
        common.remove_quietly(f)
    return False


def daemon_call(path, payload=None, timeout=60, method="POST"):
    st = daemon_state()
    port, token = st.get("port"), st.get("token")
    if not port or not token or not is_daemon_running():
        raise RuntimeError("Il motore IA di Germano non e' in esecuzione.")
    url = f"http://127.0.0.1:{port}{path}"
    headers = {"X-Germano-Token": token}
    if method == "GET":
        return _daemon_http.get(url, headers=headers, timeout=timeout)
    return _daemon_http.post(url, json=payload or {}, headers=headers, timeout=timeout)


def daemon_ready():
    return is_daemon_running() and os.path.exists(common.READY_FLAG) and bool(daemon_state().get("port"))


def _daemon_error(r):
    """Messaggio d'errore restituito dal motore (es. in modalita' Client: Germano Server non raggiungibile)."""
    try:
        msg = str((r.json() or {}).get("error") or "")
    except Exception:
        msg = r.text or ""
    return msg[:300].strip().rstrip(".")


def _rotate_log():
    try:
        if os.path.exists(common.LOG_FILE) and os.path.getsize(common.LOG_FILE) > 5 * 1024 ** 2:
            old = common.LOG_FILE + ".1"
            common.remove_quietly(old)
            os.replace(common.LOG_FILE, old)
    except Exception:
        pass


def start_daemon():
    with _spawn_lock:
        if is_daemon_running():
            return False
        for f in (common.STOP_FLAG, common.READY_FLAG, common.LAST_ERROR_FILE, common.STATUS_FILE):
            common.remove_quietly(f)
        _rotate_log()
        token = uuid.uuid4().hex
        env = os.environ.copy()
        env["GERMANO_PARENT_PID"] = str(os.getpid())
        env["GERMANO_TOKEN"] = token
        log_f = open(common.LOG_FILE, "a", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                [sys.executable, os.path.join(BASE_DIR, "daemon.py")],
                stdout=log_f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                env=env, cwd=BASE_DIR, creationflags=NO_WINDOW,
            )
        finally:
            log_f.close()
        common.atomic_write_json(common.DAEMON_STATE_FILE, {"pid": proc.pid, "token": token, "port": None,
                                                            "status": "starting", "started": time.time()})
        return True


def stop_daemon(wait=6.0):
    st = daemon_state()
    pid = st.get("pid")
    with open(common.STOP_FLAG, "w", encoding="utf-8") as f:
        f.write("1")
    try:
        if st.get("port"):
            daemon_call("/internal/stop", timeout=2)
    except Exception:
        pass
    if pid:
        try:
            p = psutil.Process(int(pid))
            try:
                p.wait(timeout=wait)
            except psutil.TimeoutExpired:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except psutil.TimeoutExpired:
                    p.kill()
        except (psutil.NoSuchProcess, ValueError):
            pass
        except Exception:
            pass
    for f in (common.DAEMON_STATE_FILE, common.READY_FLAG, common.STOP_FLAG, common.STATUS_FILE):
        common.remove_quietly(f)


def _same_data_dir(proc):
    """True se il demone usa la stessa cartella dati di questo server: con GERMANO_DATA_DIR piu' istanze possono
    condividere la stessa installazione e il demone di un'altra istanza NON e' un processo orfano."""
    try:
        env = proc.environ()
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
        return False   # nel dubbio non lo si considera nostro (mai chiudere il demone di un'altra istanza)
    other = os.path.abspath(env.get("GERMANO_DATA_DIR") or BASE_DIR)
    return os.path.normcase(other) == os.path.normcase(common.DATA_DIR)


def _orphans():
    """Processi daemon.py di QUESTA installazione non registrati (es. finestra chiusa in modo anomalo)."""
    current = daemon_state().get("pid")
    exe = os.path.normcase(sys.executable)
    out = []
    for p in psutil.process_iter(["pid", "exe", "cmdline"]):
        try:
            cmd = p.info.get("cmdline") or []
            if p.info["pid"] == current or not any(c.endswith("daemon.py") for c in cmd):
                continue
            if os.path.normcase(p.info.get("exe") or "") != exe:
                continue
            if not _same_data_dir(p):
                continue
            out.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return out


# ------------------------------------------------------------------------------------------------
# Pagine
# ------------------------------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", version=APP_VERSION)


@app.route("/guide")
@app.route("/guide.html")
def guide():
    return render_template("guide.html", version=APP_VERSION)


@app.route("/favicon.ico")
def favicon():
    """Icona ufficiale di Germano AI (finestra dell'app, barra delle applicazioni)."""
    return send_file(os.path.join(BASE_DIR, "static", "favicon.ico"), mimetype="image/x-icon", max_age=86400)


# ------------------------------------------------------------------------------------------------
# Stato, impostazioni, controllo motore
# ------------------------------------------------------------------------------------------------
def _is_document(root, name):
    """File di lavoro da contare e mostrare: esclusi i temporanei di Germano e i file di sistema che il motore
    ignora (Thumbs.db, desktop.ini, file nascosti), altrimenti risulterebbero «in attesa» per sempre."""
    return not name.startswith(common.TMP_PREFIX) and not common.is_ignored_file(os.path.join(root, name))


def _count(folder):
    n = dirs = size = 0
    for root, ds, files in os.walk(folder):
        dirs += len(ds)
        for f in files:
            if not _is_document(root, f):
                continue
            n += 1
            try:
                size += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return n, dirs, size


@app.route("/api/status")
def api_status():
    running = is_daemon_running()
    if running and os.path.exists(common.STOP_FLAG):
        state = "shutting_down"
    elif running:
        state = "running" if daemon_ready() else "loading_models"
    else:
        common.remove_quietly(common.STOP_FLAG)
        state = "stopped"
    err = None
    if not running:
        le = common.read_json(common.LAST_ERROR_FILE, None)
        if isinstance(le, dict) and le.get("message"):
            state = "error"
            err = le["message"]

    def stats():
        p, pf, pb = _count(common.INPUT_DIR)
        return {
            "pending": p, "pending_folders": pf, "pending_bytes": pb,
            "processed": _count(common.PROCESSED_DIR)[0], "outputs": _count(common.OUTPUT_DIR)[0],
            "failed": _count(common.FAILED_DIR)[0], "extracted": _count(common.EXTRACTED_DIR)[0],
            "vault_count": vault_reader.count(),
        }
    st = cached("stats", 1.5, stats)
    try:
        mem = psutil.virtual_memory()
        system = {"cpu_percent": round(psutil.cpu_percent(interval=None), 1), "ram_percent": round(mem.percent, 1),
                  "ram_used_gb": round(mem.used / 1024 ** 3, 1), "ram_total_gb": round(mem.total / 1024 ** 3, 1)}
    except Exception:
        system = {"cpu_percent": 0, "ram_percent": 0, "ram_used_gb": 0, "ram_total_gb": 0}
    progress = common.read_json(common.STATUS_FILE, {}) if running else {}
    cfg = common.load_config()
    eff = common.effective_operating_mode(cfg)
    return jsonify({
        "version": APP_VERSION, "running": running, "status": state, "error": err,
        "stats": st, "system": system, "progress": progress or {},
        "engine": daemon_state().get("engine") if running else None,
        "profile": cfg.get("compliance_mode"), "locked": bool(cfg.get("lock_settings")),
        "update": UPDATER.snapshot(),
        "mode": {"effective": eff, "label": MODE_LABELS.get(eff, eff), "server": LAN_MODE,
                 "client": common.mode_flags(eff)[1], "forced_by": common.mode_forced_by()},
    })


@app.route("/api/ai/detect")
def api_ai_detect():
    """Elenco delle AI/CLI installate su questo computer. Solo file system e porte locali (nessun processo
    avviato, nessuna rete): il risultato e' in cache per 30 s, con ?refresh=1 si forza una nuova scansione."""
    from germano import ai_detect
    if request.args.get("refresh") in ("1", "true", "yes"):
        _cache.pop("ai_detect", None)
    data = cached("ai_detect", 30.0, ai_detect.detect)
    if not _remote_is_local():
        # dalla rete solo nomi e versioni: i percorsi rivelerebbero il nome utente di Windows del server
        data = {**data, "tools": [{k: v for k, v in t.items() if k != "path"} for t in data["tools"]]}
    return jsonify(data)


def _server_info():
    """Metadati del server per il rilevamento (UDP e /api/discovery). Mai il token, mai dati personali."""
    cfg = common.load_config()
    eng = (daemon_state().get("engine") or {}) if is_daemon_running() else {}
    engine_mode = eng.get("mode") or "local"
    return {
        "service": "germano-server",
        "version": APP_VERSION,
        "port": PORT,
        "name": (cfg.get("server_name") or MACHINE_NAME),
        "instance_id": cfg.get("instance_id") or "",
        "operating_mode": common.effective_operating_mode(cfg),
        "lan": LAN_MODE,
        "token_required": True,   # dalla rete Proxy, Studio e motore richiedono sempre il token
        "engine_ready": daemon_ready(),
        "engine_mode": engine_mode,
        # un server che delega a sua volta il calcolo non offre il proprio motore (niente catene)
        "engine_shared": bool(LAN_MODE and engine_mode != "remote"),
        "device": eng.get("device") if engine_mode != "remote" else None,
    }


@app.route("/api/discovery")
def api_discovery():
    return jsonify(_server_info())


# ------------------------------------------------------------------------------------------------
# AI condivise (parte Server): i client della rete usano le CLI di AI installate su questo computer. L'esecuzione
# passa sempre dal Proxy locale (verso il cloud solo testo anonimizzato, dati ripristinati nella risposta) e va
# attivata dall'amministratore (share_ai_tools). Dalla rete richiede il token (vedi _LAN_TOKEN_PATHS).
# ------------------------------------------------------------------------------------------------
def _host_of(url):
    from urllib.parse import urlsplit
    try:
        return urlsplit(url or "").hostname or ""
    except ValueError:
        return ""


@app.route("/api/harness/v1/tools")
def api_harness_tools():
    from germano import ai_detect, harness
    cfg = common.load_config()
    sharing = bool(cfg.get("share_ai_tools"))
    data = cached("ai_detect", 30.0, ai_detect.detect)
    return jsonify({
        "api": 1,
        "server": {"name": cfg.get("server_name") or MACHINE_NAME, "version": APP_VERSION, "engine_ready": daemon_ready()},
        "sharing": sharing,
        # servizi a cui il Proxy di questo server inoltra le richieste (solo il nome del servizio, mai chiavi)
        "proxy": {"anthropic": _host_of(cfg.get("target_anthropic_url")), "openai": _host_of(cfg.get("target_api_url"))},
        "tools": harness.catalog(data["tools"], sharing),
    })


@app.route("/api/harness/v1/run", methods=["POST"])
def api_harness_run():
    from germano import ai_detect, harness
    if not common.load_config().get("share_ai_tools"):
        return jsonify({"status": "error", "message": _L(
            "Questo server non condivide le sue AI con i client: l'amministratore puo' attivarle in Impostazioni > "
            "Accesso dalla rete («Condividi con i client le AI di questo computer»).",
            "This server does not share its AI tools with the clients: the administrator can enable them in Settings > "
            "Network access («Share this computer's AI tools with the clients»).")}), 403
    data = request.get_json(silent=True) or {}
    tool = str(data.get("tool") or "").strip().lower()[:40]
    prompt = str(data.get("prompt") or "")
    model = str(data.get("model") or "").strip()
    if not prompt.strip():
        return jsonify({"status": "error", "message": _L("Scrivi un prompt.", "Write a prompt.")}), 400
    if len(prompt) > harness.MAX_PROMPT:
        return jsonify({"status": "error", "message": _L(f"Prompt troppo lungo (massimo {harness.MAX_PROMPT} caratteri).",
                                                         f"Prompt too long (at most {harness.MAX_PROMPT} characters).")}), 413
    if not harness.valid_model(model):
        return jsonify({"status": "error", "message": _L("Nome del modello non valido.", "Invalid model name.")}), 400
    if tool not in harness.PROFILES:
        reason = harness.NOT_REMOTE.get(tool)
        return jsonify({"status": "error", "message": _L(f"«{tool}» non e' utilizzabile dai client",
                                                         f"«{tool}» cannot be used by the clients")
                        + (f": {reason}." if reason else ".")}), 404
    info = next((t for t in cached("ai_detect", 30.0, ai_detect.detect)["tools"] if t.get("id") == tool), None)
    if not info or not info.get("detected") or not info.get("path"):
        return jsonify({"status": "error", "message": _L(f"{tool} non e' installata su questo server.",
                                                         f"{tool} is not installed on this server.")}), 404
    if not daemon_ready():
        return jsonify({"status": "blocked", "message": _L(
            "Il motore di Germano su questo server non e' pronto: richiesta bloccata, nessun dato inviato.",
            "The Germano engine on this server is not ready: request blocked, no data sent.")}), 503
    try:
        res = harness.run(tool, info["path"], prompt, PORT, model=model or None)
    except harness.HarnessError as e:
        common.log(f"AI condivise: {tool} per {request.remote_addr} non riuscita ({e.status}).")
        return jsonify({"status": "blocked" if e.status == 503 else "error", "message": str(e)}), e.status
    common.log(f"AI condivise: {tool} eseguita per {request.remote_addr} ({len(prompt)} caratteri, {res['seconds']} s).")
    return jsonify({"status": "success", "tool": tool, "tool_name": info.get("name"), "version": info.get("version"),
                    "answer": res["answer"], "seconds": res["seconds"]})


# ------------------------------------------------------------------------------------------------
# Motore condiviso (parte Server): inferenza per i client Germano della rete. Mai il Vault: si restituiscono
# solo posizioni, categorie e punteggi. Dalla rete richiede il token (vedi _LAN_TOKEN_PATHS).
# ------------------------------------------------------------------------------------------------
_ENGINE_KINDS = ("ocr", "faces", "signatures", "plates")


def _engine_forward(path, payload, timeout):
    if not daemon_ready():
        return jsonify({"error": _L("Il motore di questo Germano Server non e' ancora pronto.",
                                    "The engine of this Germano Server is not ready yet.")}), 503
    try:
        r = daemon_call(path, payload, timeout=timeout)
    except Exception as e:
        return jsonify({"error": _L(f"Motore non raggiungibile: {e}", f"Engine unreachable: {e}")}), 503
    return Response(r.content, status=r.status_code, content_type="application/json")


@app.route("/api/engine/v1/info")
def api_engine_info():
    cfg = common.load_config()
    base = {"api": 1, "name": cfg.get("server_name") or MACHINE_NAME, "version": APP_VERSION,
            "engine_ready": False, "engine_mode": "local"}
    if not daemon_ready():
        return jsonify(base)
    try:
        r = daemon_call("/internal/engine/info", method="GET", timeout=10)
    except Exception:
        return jsonify(base)
    if r.status_code == 409:
        base["engine_mode"] = "remote"
        return jsonify(base), 409
    if r.status_code != 200:
        return jsonify(base)
    info = r.json()
    info.update(name=base["name"], version=APP_VERSION)
    return jsonify(info)


@app.route("/api/engine/v1/classify", methods=["POST"])
def api_engine_classify():
    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": _L("Corpo della richiesta non valido (JSON atteso).",
                                    "Invalid request body (JSON expected).")}), 400
    return _engine_forward("/internal/engine/classify", payload, timeout=3600)


@app.route("/api/engine/v1/<kind>", methods=["POST"])
def api_engine_image(kind):
    import base64
    if kind not in _ENGINE_KINDS:
        return jsonify({"error": _L("Analisi sconosciuta.", "Unknown analysis.")}), 404
    data = request.get_data(cache=False)
    if not data:
        return jsonify({"error": _L("Immagine mancante.", "Image missing.")}), 400
    if len(data) > 80 * 1024 * 1024:
        return jsonify({"error": _L("Immagine troppo grande.", "Image too large.")}), 413
    return _engine_forward(f"/internal/engine/{kind}", {"png_b64": base64.b64encode(data).decode("ascii")},
                           timeout=1800)


# ------------------------------------------------------------------------------------------------
# Modalita' operativa (solo da questo computer)
# ------------------------------------------------------------------------------------------------
def _mode_state():
    from germano import discovery as gdiscovery
    cfg = common.load_config()
    eff = common.effective_operating_mode(cfg)
    srv, cli = common.mode_flags(eff)
    running = is_daemon_running()
    return {
        "saved": cfg.get("operating_mode") or "standalone",
        "effective": eff,
        "label": MODE_LABELS.get(eff, eff),
        "forced_by": common.mode_forced_by(),
        "first_run_done": bool(cfg.get("first_run_done")),
        "locked": bool(cfg.get("lock_settings")),
        "enable_tooltips": cfg.get("enable_tooltips", True),
        "server": {
            "enabled": srv, "listening": LAN_MODE, "host": LAN_HOST, "port": PORT,
            "ips": gdiscovery.local_ipv4_addresses() if srv else [],
            "token": LAN_TOKEN if srv else "", "discovery": _DISCOVERY is not None, "discovery_port": DISCOVERY_PORT,
            "share_ai_tools": bool(cfg.get("share_ai_tools")),
        },
        "client": {
            "enabled": cli, "remote_server": cfg.get("remote_server") or "",
            "token_set": bool(cfg.get("remote_token")), "fallback_local": bool(cfg.get("client_fallback_local", True)),
        },
        "engine_running": running,
        "engine_ready": daemon_ready(),
        "engine": daemon_state().get("engine") if running else None,
    }


@app.route("/api/mode", methods=["GET", "POST"])
def api_mode():
    if request.method == "GET":
        return jsonify(_mode_state())
    data = request.get_json(silent=True) or {}
    cfg = common.load_config()
    mode = str(data.get("operating_mode") or "").strip().lower()
    if mode not in common.OPERATING_MODES:
        return jsonify({"status": "error", "message": _L("Modalita' operativa non valida.",
                                                         "Invalid operating mode.")}), 400
    updates = {"first_run_done": True}
    if "enable_tooltips" in data:
        updates["enable_tooltips"] = data["enable_tooltips"]
    if cfg.get("lock_settings") and mode != (cfg.get("operating_mode") or "standalone"):
        common.save_config(updates)   # le preferenze dell'interfaccia restano modificabili
        return jsonify({"status": "locked", "message": _L("Modalita' operativa bloccata dall'amministratore "
                                                          "(lock_settings in config.json).",
                                                          "Operating mode locked by the administrator "
                                                          "(lock_settings in config.json)."), **_mode_state()}), 403
    updates["operating_mode"] = mode
    if "client_fallback_local" in data:
        updates["client_fallback_local"] = data["client_fallback_local"]
    if "share_ai_tools" in data:
        updates["share_ai_tools"] = data["share_ai_tools"]
    # Indirizzo e token del server remoto con le stesse regole di Germano Client: '192.168.1.10' diventa
    # http://192.168.1.10:8181 e il Base URL copiato dalla Dashboard del server (.../g/<token>/v1) porta con se'
    # il token. Un valore non valido viene segnalato, non scartato in silenzio.
    token = str(data.get("remote_token") or "").strip()
    if token and not common.TOKEN_RE.match(token):
        return jsonify({"status": "error", "message": _L(
            "Il token contiene caratteri non validi: copia esattamente quello mostrato dal server (lettere, cifre, - e _).",
            "The token contains invalid characters: copy exactly the one shown by the server (letters, digits, - and _).")}), 400
    if "remote_server" in data:
        raw = str(data.get("remote_server") or "").strip()
        if raw:
            try:
                base, url_token = common.parse_server_url(raw)
            except ValueError:
                shown = raw[:80]
                return jsonify({"status": "error", "message": _L(
                    f"Indirizzo del server non valido: «{shown}». Esempi: 192.168.1.10, 192.168.1.10:8181 oppure "
                    "http://192.168.1.10:8181 (vuoto = ricerca automatica in rete).",
                    f"Invalid server address: «{shown}». Examples: 192.168.1.10, 192.168.1.10:8181 or "
                    "http://192.168.1.10:8181 (empty = automatic search on the network).")}), 400
            updates["remote_server"] = base
            if url_token and not token:
                token = url_token
        else:
            updates["remote_server"] = ""
    if token:
        updates["remote_token"] = token
    prev_mode = common.effective_operating_mode(cfg)
    prev_remote = (cfg.get("remote_server"), cfg.get("remote_token"), cfg.get("client_fallback_local"))
    new_cfg, _err = common.save_config(updates)
    eff, notes = _apply_operating_mode()
    engine_action = _sync_engine(prev_mode, eff, prev_remote, new_cfg)
    state = _mode_state()
    state.update(status="success", notes=notes, engine_action=engine_action)
    return jsonify(state)


@app.route("/api/mode/token", methods=["POST"])
def api_mode_token():
    """Nuovo token per i client della rete: quello precedente smette subito di funzionare."""
    global LAN_TOKEN
    if common.load_config().get("lock_settings"):
        return jsonify({"status": "locked", "message": _L("Impostazioni bloccate dall'amministratore.",
                                                          "Settings locked by the administrator.")}), 403
    LAN_TOKEN = uuid.uuid4().hex
    common.save_config({"lan_token": LAN_TOKEN}, admin=True)
    return jsonify({"status": "success", "token": LAN_TOKEN})


@app.route("/api/remote/servers")
def api_remote_servers():
    """Germano Server presenti sulla rete (ricerca UDP fatta da questo computer, esclusa questa installazione)."""
    from germano import discovery as gdiscovery
    cfg = common.load_config()
    try:
        found = gdiscovery.discover(timeout=1.5, port=DISCOVERY_PORT, broadcasts=gdiscovery.broadcast_addresses(),
                                    exclude_instance=cfg.get("instance_id") or None)
    except OSError as e:
        return jsonify({"servers": [], "error": str(e)})
    servers = [{
        "name": s.get("name"), "url": f"http://{s.get('ip')}:{s.get('port')}", "version": s.get("version"),
        "engine_ready": bool(s.get("engine_ready")), "engine_shared": bool(s.get("engine_shared")),
        "device": s.get("device"), "operating_mode": s.get("operating_mode"),
    } for s in found]
    return jsonify({"servers": servers})


# Rete e identita' si cambiano solo da /api/mode, che le applica dal vivo e in modo coerente. I token non tornano
# mai alla pagina con le impostazioni: quello per i client compare solo in /api/mode, con la parte Server attiva.
_MODE_ONLY_KEYS = ("operating_mode", "remote_server", "remote_token", "client_fallback_local",
                   "lan_token", "instance_id", "instance_host", "share_ai_tools")
_SECRET_KEYS = ("lan_token", "remote_token")


def _without_mode_keys(settings):
    if not isinstance(settings, dict):
        return settings
    return {k: v for k, v in settings.items() if k not in _MODE_ONLY_KEYS}


def _public_settings(cfg):
    return {k: v for k, v in cfg.items() if k not in _SECRET_KEYS}


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        cfg, err = common.save_config(_without_mode_keys(data.get("settings", data)))
        resp = {"status": "success" if not err else "locked", "settings": _public_settings(cfg)}
        if err:
            resp["message"] = _L(err, "Settings locked by the administrator (lock_settings): changes ignored.")
        return jsonify(resp)
    return jsonify(_public_settings(common.load_config()))


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}
    if isinstance(data.get("settings"), dict) and data["settings"]:
        common.save_config(_without_mode_keys(data["settings"]))
    common.remove_quietly(common.STOP_FLAG)
    started = start_daemon()
    return jsonify({"status": "success", "message": _L("Motore avviato", "Engine started") if started
                    else _L("Motore gia' in esecuzione", "Engine already running")})


@app.route("/api/stop", methods=["POST"])
@app.route("/api/stop_daemon", methods=["POST"])
def api_stop():
    stop_daemon()
    return jsonify({"status": "success", "message": _L("Motore fermato", "Engine stopped")})


@app.route("/api/check_update", methods=["GET"])
def api_check_update():
    """Compatibilità: nessuna richiesta di rete qui, solo lo stato del controllo in background."""
    snap = UPDATER.snapshot()
    online = bool(common.load_config().get("check_updates", True)) and gupdater.windows_reports_online()
    return jsonify({"current_version": APP_VERSION, "latest_version": snap.get("latest") or APP_VERSION,
                    "update_available": bool(snap.get("available")), "offline": not online})


@app.route("/api/update/status", methods=["GET"])
def api_update_status():
    cfg = common.load_config()
    snap = UPDATER.snapshot()
    snap.update(check_updates=bool(cfg.get("check_updates", True)), auto_update=bool(cfg.get("auto_update", True)))
    return jsonify(snap)


@app.route("/api/update/check", methods=["POST"])
def api_update_check():
    UPDATER.request_check()  # controllo richiesto dall'utente: avviene anche se Windows non segnala la rete
    return jsonify({"status": "success"})


@app.route("/api/update/download", methods=["POST"])
def api_update_download():
    if UPDATER.busy():
        return jsonify({"status": "busy"})

    def run():
        try:
            UPDATER.check(manual=True, auto_download=True)
        except gupdater.UpdateError as e:
            UPDATER._set(state="error", error=str(e), progress=None)
        except Exception as e:
            UPDATER._set(state="error", error=f"Errore imprevisto: {e}", progress=None)
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "success"})


@app.route("/api/update/install", methods=["POST"])
def api_update_install():
    """Avvia l'installer scaricato (germano-<versione>.exe --update) e chiude Germano: l'installer sostituisce il
    programma e lo riapre da solo."""
    if not gupdater.read_ready():
        return jsonify({"status": "error", "message": _L("Nessun aggiornamento pronto da installare.",
                                                         "No update ready to install.")}), 400
    try:
        UPDATER.launch_install()
    except Exception as e:
        return jsonify({"status": "error", "message": _L(f"Impossibile avviare l'installazione: {e}",
                                                         f"Cannot start the installation: {e}")}), 500

    def shutdown():
        time.sleep(1.0)
        try:
            stop_daemon(wait=4.0)
        finally:
            os._exit(10)  # codice 10 = aggiornamento in corso: il launcher chiude la finestra senza errori
    threading.Thread(target=shutdown, daemon=True).start()
    return jsonify({"status": "success"})


@app.route("/api/update/ack", methods=["POST"])
def api_update_ack():
    gupdater.acknowledge_install()
    return jsonify({"status": "success"})


def _open_in_os(path, reveal=False):
    """Apre una cartella o un file con il file manager / il programma predefinito del sistema (Esplora file su
    Windows, Finder su macOS, il file manager del desktop su Linux); reveal=True mostra il file nella sua cartella."""
    if os.name == "nt":
        if reveal:
            subprocess.Popen(f'explorer.exe /select,"{path}"')
        else:
            os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path] if reveal else ["open", path], close_fds=True)
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) if reveal else path], close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


@app.route("/api/open_folder", methods=["POST"])
def api_open_folder():
    data = request.get_json(silent=True) or {}
    folder = data.get("folder", "output")
    if folder not in common.WORK_FOLDERS:
        return jsonify({"status": "error", "message": _L("Cartella non valida.", "Invalid folder.")}), 400
    path = common.WORK_FOLDERS[folder]
    os.makedirs(path, exist_ok=True)
    try:
        _open_in_os(path)
        return jsonify({"status": "success", "path": path})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ------------------------------------------------------------------------------------------------
# File
# ------------------------------------------------------------------------------------------------
def _restore_file_locally(src, dest, tag_map):
    """Ripristino dei dati veri (non richiede i modelli IA: avviene nel server)."""
    from germano import formats
    ctx = formats.Ctx("restore", common.load_config(), tag_map=tag_map)
    return formats.process_file(src, dest, ctx)


def _is_return_file(path, tag_map):
    if not tag_map:
        return False
    from germano import formats
    try:
        return contains_tags(formats.sample_text(path), tag_map)
    except Exception:
        return False


def _move_unique(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        dest = common.unique_path(dest)
    os.replace(src, dest)
    return dest


@app.route("/api/upload_files", methods=["POST"])
def api_upload_files():
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return jsonify({"status": "error", "message": _L("Nessun file selezionato.", "No file selected.")}), 400
    rel_paths = request.form.getlist("paths")
    cfg = common.load_config()
    tag_map = vault_reader.tag_map() if cfg.get("enable_deanonymize", True) else {}
    saved, restored, errors = [], [], []
    os.makedirs(common.UPLOAD_DIR, exist_ok=True)
    for i, f in enumerate(files):
        if not f or not f.filename:
            continue
        rel = common.safe_relpath(rel_paths[i] if i < len(rel_paths) and rel_paths[i] else f.filename)
        if not rel:
            continue
        staged = os.path.join(common.UPLOAD_DIR, uuid.uuid4().hex[:10] + "_" + os.path.basename(rel))
        f.save(staged)
        try:
            if _is_return_file(staged, tag_map):
                rel_dir, base = os.path.split(rel)
                out_rel = os.path.join(rel_dir, base if base.startswith("ripristinato_") else "ripristinato_" + base)
                tmp_out = os.path.join(common.UPLOAD_DIR, uuid.uuid4().hex[:10] + "_" + os.path.basename(out_rel))
                real = _restore_file_locally(staged, tmp_out, tag_map)
                final = _move_unique(real, os.path.join(common.OUTPUT_DIR, out_rel))
                _move_unique(staged, os.path.join(common.PROCESSED_DIR, rel))
                name = os.path.relpath(final, common.OUTPUT_DIR).replace("\\", "/")
                restored.append({"name": name, "download_url": "/api/download/output/" + requests.utils.quote(name)})
            else:
                dest = _move_unique(staged, os.path.join(common.INPUT_DIR, rel))
                saved.append(os.path.relpath(dest, common.INPUT_DIR).replace("\\", "/"))
        except Exception as e:
            errors.append(f"{rel}: {e}")
            common.remove_quietly(staged)
    _cache.pop("stats", None)
    _cache.pop("files", None)
    return jsonify({"status": "success", "saved_count": len(saved), "files": saved,
                    "auto_restored_count": len(restored), "auto_restored_files": restored, "errors": errors})


@app.route("/api/files", methods=["GET"])
def api_files():
    def build():
        reasons = common.read_json(common.FAILED_REASONS_FILE, {}) or {}
        outputs = common.read_json(common.OUTPUTS_FILE, {}) or {}
        result, totals = {}, {}
        for name in ("output", "input", "failed", "processed"):
            folder = common.WORK_FOLDERS[name]
            items = []
            for root, _dirs, files in os.walk(folder):
                for f in files:
                    if not _is_document(root, f):
                        continue
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, folder).replace("\\", "/")
                    try:
                        st = os.stat(full)
                    except OSError:
                        continue
                    item = {"name": rel, "size": st.st_size, "mtime": st.st_mtime}
                    if name == "failed" and rel in reasons:
                        item["reason"] = reasons[rel].get("reason")
                    elif name == "output" and isinstance(outputs.get(rel), dict):
                        info = outputs[rel]
                        item.update(mode=info.get("mode"), entities=info.get("entities"), notes=info.get("notes"))
                    items.append(item)
            items.sort(key=lambda x: x["mtime"], reverse=True)
            totals[name] = len(items)
            result[name] = items[:500]
        result["totals"] = totals
        return result
    return jsonify(cached("files", 1.5, build))


# Tipi di file che la Dashboard può aprire con il programma predefinito di Windows. Mai eseguibili o script
# (.exe, .bat, .ps1, .js...): per quelli resta solo "Mostra nella cartella".
OPENABLE_EXTS = {
    ".pdf", ".rtf", ".txt", ".csv", ".tsv", ".md", ".log", ".json", ".jsonl", ".xml", ".html", ".htm", ".eml",
    ".doc", ".docx", ".docm", ".dotx", ".xls", ".xlsx", ".xlsm", ".xltx", ".ppt", ".pptx", ".pptm", ".potx",
    ".ppsx", ".odt", ".ods", ".odp", ".png", ".jpg", ".jpeg", ".jfif", ".bmp", ".tif", ".tiff", ".webp", ".gif",
    ".zip", ".p7m",
}


def _work_file(folder, name):
    """Percorso di un file dentro una cartella di lavoro (None se inesistente o fuori dalla cartella)."""
    if folder not in common.WORK_FOLDERS or not isinstance(name, str) or not name:
        return None
    base = os.path.abspath(common.WORK_FOLDERS[folder])
    target = os.path.abspath(os.path.join(base, name))
    if os.path.commonpath([base, target]) != base or not os.path.isfile(target):
        return None
    return target


def _remove_empty_dirs(base):
    for root, _dirs, _files in os.walk(base, topdown=False):
        if os.path.abspath(root) != os.path.abspath(base):
            try:
                os.rmdir(root)  # riesce solo se la cartella è vuota
            except OSError:
                pass


@app.route("/api/folders", methods=["GET"])
def api_folders():
    return jsonify({name: path for name, path in common.WORK_FOLDERS.items()})


@app.route("/api/file_action", methods=["POST"])
def api_file_action():
    data = request.get_json(silent=True) or {}
    path = _work_file(data.get("folder"), data.get("name"))
    if not path:
        return jsonify({"status": "error", "message": _L("File non trovato.", "File not found.")}), 404
    action = data.get("action")
    try:
        if action == "reveal":
            _open_in_os(path, reveal=True)
        elif action == "open":
            if os.path.splitext(path)[1].lower() not in OPENABLE_EXTS:
                return jsonify({"status": "error", "message": _L(
                    "Per sicurezza questo tipo di file non viene aperto direttamente: usa «Mostra nella cartella».",
                    "For security this type of file is not opened directly: use «Show in folder».")}), 400
            _open_in_os(path)
        else:
            return jsonify({"status": "error", "message": _L("Azione non valida.", "Invalid action.")}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "success"})


@app.route("/api/retry_failed", methods=["POST"])
def api_retry_failed():
    """Rimette in coda (cartella input) i documenti non riusciti, con lo stesso percorso relativo."""
    data = request.get_json(silent=True) or {}
    base = os.path.abspath(common.FAILED_DIR)
    if data.get("all"):
        names = [os.path.relpath(os.path.join(root, f), base) for root, _dirs, files in os.walk(base)
                 for f in files if _is_document(root, f)]
    else:
        names = [n for n in (data.get("names") or []) if isinstance(n, str)]
    moved, errors = [], []
    for name in names:
        src = _work_file("failed", name)
        if not src:
            errors.append(f"{name}: " + _L("file non trovato", "file not found"))
            continue
        rel = os.path.relpath(src, base)
        try:
            dest = _move_unique(src, os.path.join(common.INPUT_DIR, rel))
            moved.append(os.path.relpath(dest, common.INPUT_DIR).replace("\\", "/"))
        except Exception as e:
            errors.append(f"{rel}: {e}")
    _remove_empty_dirs(base)
    _cache.pop("stats", None)
    _cache.pop("files", None)
    return jsonify({"status": "success", "moved": moved, "errors": errors})


@app.route("/api/download/<folder>/<path:filename>", methods=["GET"])
def api_download(folder, filename):
    if folder not in ("output", "extracted", "processed", "failed"):
        return jsonify({"error": _L("Cartella non autorizzata", "Folder not allowed")}), 403
    base = os.path.abspath(common.WORK_FOLDERS[folder])
    target = os.path.abspath(os.path.join(base, filename))
    if os.path.commonpath([base, target]) != base or not os.path.isfile(target):
        return jsonify({"error": _L("File non trovato", "File not found")}), 404
    return send_file(target, as_attachment=True, download_name=os.path.basename(target))


@app.route("/api/clear_logs", methods=["POST"])
def api_clear_logs():
    try:
        with open(common.LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"[{common.ts()}] Registro pulito dall'utente.\n")
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/logs")
def api_logs():
    try:
        with open(common.LOG_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 96 * 1024))
            data = f.read().decode("utf-8", errors="replace")
        lines = data.splitlines(keepends=True)
        if size > 96 * 1024 and lines:
            lines = lines[1:]
        return jsonify({"logs": lines[-150:]})
    except FileNotFoundError:
        return jsonify({"logs": []})
    except Exception as e:
        return jsonify({"logs": [_L(f"Errore lettura registro: {e}", f"Cannot read the log: {e}")]})


@app.route("/api/vault", methods=["GET"])
def api_vault():
    items = [{"tag": k, "value": v} for k, v in vault_reader.items()]
    return jsonify({"status": "success", "count": len(items), "items": items})


@app.route("/api/clear_vault", methods=["POST"])
def api_clear_vault():
    try:
        if daemon_ready():
            r = daemon_call("/internal/vault/clear", timeout=30)
            if r.status_code != 200:
                raise RuntimeError(r.text)
        else:
            from germano.vault import Vault
            Vault().clear()
        _cache.pop("stats", None)
        return jsonify({"status": "success", "message": _L("Archivio corrispondenze azzerato.", "Mapping archive cleared.")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/check_orphans")
def api_check_orphans():
    try:
        return jsonify({"orphans": len(_orphans())})
    except Exception:
        return jsonify({"orphans": 0})


@app.route("/api/kill_orphans", methods=["POST"])
def api_kill_orphans():
    killed = 0
    for p in _orphans():
        try:
            p.terminate()
            killed += 1
        except Exception:
            pass
    return jsonify({"status": "success", "killed": killed})


# ------------------------------------------------------------------------------------------------
# API REST v1
# ------------------------------------------------------------------------------------------------
@app.route("/api/v1/deanonymize_text", methods=["POST"])
def api_deanonymize_text():
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict) or "text" not in data:
        return jsonify({"error": _L("Fornire un JSON con il campo 'text'.", "Send a JSON body with the 'text' field.")}), 400
    tag_map = vault_reader.tag_map()
    return jsonify({"status": "success", "restored": restore_text(str(data["text"]), tag_map), "vault_count": len(tag_map)})


@app.route("/api/v1/deanonymize_file", methods=["POST"])
def api_deanonymize_file():
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return jsonify({"status": "error", "message": _L("Nessun file selezionato per il ripristino.",
                                                         "No file selected for restoration.")}), 400
    tag_map = vault_reader.tag_map()
    out = []
    for f in files:
        if not f or not f.filename:
            continue
        name = common.safe_filename(f.filename)
        staged = os.path.join(common.UPLOAD_DIR, uuid.uuid4().hex[:10] + "_" + name)
        f.save(staged)
        try:
            out_name = name if name.startswith("ripristinato_") else "ripristinato_" + name
            tmp_out = os.path.join(common.UPLOAD_DIR, uuid.uuid4().hex[:10] + "_" + out_name)
            real = _restore_file_locally(staged, tmp_out, tag_map)
            final = _move_unique(real, os.path.join(common.OUTPUT_DIR, out_name))
            n = os.path.basename(final)
            out.append({"name": n, "download_url": "/api/download/output/" + requests.utils.quote(n)})
        except Exception as e:
            return jsonify({"status": "error", "message": _L(f"Impossibile ripristinare {name}: {e}",
                                                             f"Cannot restore {name}: {e}")}), 400
        finally:
            common.remove_quietly(staged)
    if not out:
        return jsonify({"status": "error", "message": _L("Impossibile ripristinare il file.", "Cannot restore the file.")}), 400
    if request.args.get("raw") == "1" and len(out) == 1:
        return send_file(os.path.join(common.OUTPUT_DIR, out[0]["name"]), as_attachment=True, download_name=out[0]["name"])
    return jsonify({"status": "success", "restored_count": len(out), "files": out, "vault_count": len(tag_map)})


@app.route("/api/v1/anonymize_text", methods=["POST"])
def api_anonymize_text():
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict) or "text" not in data:
        return jsonify({"error": _L("Fornire un JSON con il campo 'text'.", "Send a JSON body with the 'text' field.")}), 400
    text = str(data["text"])
    force = bool(data.get("force_anonymize", False))
    if not force and common.load_config().get("enable_deanonymize", True):
        tag_map = vault_reader.tag_map()
        if contains_tags(text, tag_map):
            restored = restore_text(text, tag_map)
            return jsonify({"anonymized": restored, "restored": restored, "auto_restored": True, "extracted_data": []})
    if not daemon_ready():
        return jsonify({"error": _L("Il motore IA non e' pronto: avvialo dalla Dashboard e attendi il caricamento.",
                                    "The AI engine is not ready: start it from the Dashboard and wait for it to load.")}), 503
    try:
        r = daemon_call("/internal/anonymize_text", {"text": text, "force_anonymize": True}, timeout=900)
        if r.status_code == 200:
            return jsonify(r.json())
        if r.status_code == 503:
            return jsonify({"error": _L(f"Motore IA non disponibile: {_daemon_error(r)}",
                                        f"AI engine not available: {_daemon_error(r)}")}), 503
        return jsonify({"error": _L(f"Errore del motore IA ({r.status_code}): {r.text[:300]}",
                                    f"AI engine error ({r.status_code}): {r.text[:300]}")}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/anonymize", methods=["POST"])
def api_anonymize_file():
    import base64
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"error": _L("Nessun file fornito. Usa multipart/form-data con la chiave 'file'.",
                                    "No file provided. Use multipart/form-data with the 'file' key.")}), 400
    name = common.safe_filename(f.filename)
    data = f.read()
    cfg = common.load_config()
    if cfg.get("enable_deanonymize", True):
        tag_map = vault_reader.tag_map()
        staged = os.path.join(common.UPLOAD_DIR, uuid.uuid4().hex[:10] + "_" + name)
        with open(staged, "wb") as fh:
            fh.write(data)
        try:
            if _is_return_file(staged, tag_map):
                tmp_out = os.path.join(common.UPLOAD_DIR, uuid.uuid4().hex[:10] + "_r_" + name)
                real = _restore_file_locally(staged, tmp_out, tag_map)
                with open(real, "rb") as fh:
                    out = fh.read()
                common.remove_quietly(real)
                return send_file(io.BytesIO(out), as_attachment=True, download_name=name)
        finally:
            common.remove_quietly(staged)
    if not daemon_ready():
        return jsonify({"error": _L("Il motore IA non e' pronto: avvialo dalla Dashboard e attendi il caricamento.",
                                    "The AI engine is not ready: start it from the Dashboard and wait for it to load.")}), 503
    try:
        r = daemon_call("/internal/process_file", {"filename": name, "mode": "anonymize",
                                                    "data_b64": base64.b64encode(data).decode("ascii")}, timeout=6 * 3600)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if r.status_code != 200:
        try:
            msg = r.json().get("error")
        except Exception:
            msg = r.text[:300]
        return jsonify({"error": _L(f"Elaborazione non riuscita: {msg}", f"Processing failed: {msg}")}), \
            r.status_code if r.status_code in (415, 503) else 500
    res = r.json()
    try:
        audit_dir = os.path.join(common.EXTRACTED_DIR, "api")
        os.makedirs(audit_dir, exist_ok=True)
        entries = list(res.get("extracted_data") or [])
        entries += [{"word": "", "label": "[NOTA]", "entity": "NOTE", "score": 1.0, "note": n} for n in res.get("notes") or []]
        common.atomic_write_json(os.path.join(audit_dir, time.strftime("%Y%m%d-%H%M%S_") + name + ".json"), entries, indent=4)
    except Exception:
        pass
    out_name = res.get("filename") or name
    return send_file(io.BytesIO(base64.b64decode(res["data_b64"])), as_attachment=True, download_name=out_name)


# ------------------------------------------------------------------------------------------------
# Studio AI: protezione di prompt e allegati prima dell'invio a un'AI
# ------------------------------------------------------------------------------------------------
STUDIO_MAX_PROMPT = 400_000      # caratteri del prompt
STUDIO_MAX_ATTACH = 12           # numero di allegati per invio
STUDIO_ATTACH_CHARS = 200_000    # caratteri estratti per allegato


def _studio_attachment_text(filename, data):
    """Estrae il testo di un allegato (per usarlo come contesto del prompt). Offline, nel processo server.
    Restituisce '' per i contenuti non testuali (es. immagini: vanno elaborate come file, non come testo)."""
    from germano import formats
    name = common.safe_filename(filename or "allegato")
    os.makedirs(common.UPLOAD_DIR, exist_ok=True)
    staged = os.path.join(common.UPLOAD_DIR, uuid.uuid4().hex[:10] + "_" + name)
    try:
        with open(staged, "wb") as f:
            f.write(data)
        return formats.sample_text(staged, max_chars=STUDIO_ATTACH_CHARS) or ""
    except Exception:
        return ""
    finally:
        common.remove_quietly(staged)


def _studio_compose(clean_prompt, clean_attachments):
    """Messaggio unico protetto: prompt + testo anonimizzato degli allegati."""
    out = clean_prompt or ""
    for a in clean_attachments:
        out += f"\n\n----- {a['name']} -----\n{a['anonymized']}"
    return out.strip()


@app.route("/api/studio/send", methods=["POST"])
def api_studio_send():
    """Protegge il contenuto dello Studio: anonimizza prompt e allegati con il motore locale e restituisce il
    testo pronto da inoltrare a un'AI, con l'elenco dei dati oscurati. Nessun dato lascia il computer da qui:
    l'inoltro vero e proprio avviene tramite il Proxy (con la chiave dell'utente) o copiando il testo protetto."""
    prompt = (request.form.get("prompt") or "").strip()
    target = (request.form.get("target") or "clipboard").strip()
    files = [f for f in request.files.getlist("files") if f and f.filename][:STUDIO_MAX_ATTACH]
    if not prompt and not files:
        return jsonify({"status": "error", "message": _L("Scrivi un prompt o allega un file.",
                                                         "Write a prompt or attach a file.")}), 400
    if len(prompt) > STUDIO_MAX_PROMPT:
        return jsonify({"status": "error", "message": _L("Il prompt e' troppo lungo.", "The prompt is too long.")}), 413
    if not daemon_ready():
        return jsonify({"status": "blocked",
                        "message": _L("Il motore IA non e' pronto: avvialo dalla Dashboard. Nessun dato lascia il computer.",
                                      "The AI engine is not ready: start it from the Dashboard. No data leaves the "
                                      "computer.")}), 503

    attachments, parts = [], []
    for f in files:
        name = common.safe_filename(f.filename)
        text = _studio_attachment_text(f.filename, f.read())
        textual = bool(text.strip())
        attachments.append({"name": name, "chars": len(text), "textual": textual})
        if textual:
            parts.append((name, text))

    texts = ([prompt] if prompt else []) + [t for _, t in parts]
    if not texts:
        return jsonify({"status": "error",
                        "message": _L("Gli allegati non contengono testo: usa l'anonimizzazione dei file (modalita' "
                                      "Anonimizza file).",
                                      "The attachments contain no text: use file anonymization (Anonymize files "
                                      "mode).")}), 400
    try:
        r = daemon_call("/internal/anonymize_texts", {"texts": texts}, timeout=1800)
    except Exception as e:
        return jsonify({"status": "error", "message": _L(f"Motore IA non raggiungibile: {e}",
                                                         f"AI engine unreachable: {e}")}), 502
    if r.status_code == 503:
        return jsonify({"status": "blocked", "message": _L(f"Motore IA non disponibile: {_daemon_error(r)}. "
                                                           "Nessun dato lascia il computer.",
                                                           f"AI engine not available: {_daemon_error(r)}. "
                                                           "No data leaves the computer.")}), 503
    if r.status_code != 200:
        return jsonify({"status": "error", "message": _L(f"Anonimizzazione non riuscita ({r.status_code}).",
                                                         f"Anonymization failed ({r.status_code}).")}), 502
    results = r.json().get("results") or []
    if len(results) != len(texts):
        return jsonify({"status": "error", "message": _L("Risposta incompleta del motore IA.",
                                                         "Incomplete answer from the AI engine.")}), 502

    idx = 0
    clean_prompt = ""
    entities = []
    if prompt:
        clean_prompt = results[0]["anonymized"]
        entities.extend(results[0].get("extracted_data") or [])
        idx = 1
    clean_attachments = []
    for (name, _), res in zip(parts, results[idx:]):
        clean_attachments.append({"name": name, "anonymized": res["anonymized"]})
        entities.extend(res.get("extracted_data") or [])

    _session_log(entities)
    return jsonify({
        "status": "success",
        "target": target,
        "clean_prompt": clean_prompt,
        "clean_attachments": clean_attachments,
        "composed": _studio_compose(clean_prompt, clean_attachments),
        "attachments": attachments,
        "entity_count": len(entities),
        "labels": sorted({e["label"] for e in entities if e.get("label")}),
        "vault_count": vault_reader.count(),
    })


# ------------------------------------------------------------------------------------------------
# Proxy API per IDE e agenti IA
# ------------------------------------------------------------------------------------------------
from germano import proxy as gproxy  # noqa: E402

_FWD_REQ_HEADERS = ("authorization", "x-api-key", "anthropic-version", "anthropic-beta", "openai-organization",
                    "openai-project", "openai-beta", "api-key", "x-goog-api-key", "accept", "user-agent",
                    "anthropic-dangerous-direct-browser-access")
_FWD_RESP_PREFIXES = ("x-ratelimit-", "anthropic-ratelimit-", "retry-after", "x-request-id", "request-id",
                      "openai-processing-ms", "openai-version", "openai-organization")
_SUFFIXES = ("/chat/completions", "/responses", "/messages", "/completions")


def _strip_suffix(url):
    url = (url or "").strip().rstrip("/")
    for s in _SUFFIXES:
        if url.endswith(s):
            return url[: -len(s)]
    return url


def _target(kind, sub):
    cfg = common.load_config()
    base = _strip_suffix(cfg.get("target_api_url"))
    if kind == "anthropic":
        anth = _strip_suffix(cfg.get("target_anthropic_url") or "https://api.anthropic.com/v1")
        if "anthropic.com" in base:
            anth = base
        url = anth + "/messages" + sub
    elif kind == "responses":
        url = base + "/responses" + sub
    else:
        url = base + "/chat/completions"
    qs = request.query_string.decode("latin-1")
    return url + ("?" + qs if qs else "")


def _proxy_error(kind, status, message):
    if kind == "anthropic":
        body = {"type": "error", "error": {"type": "api_error", "message": message}}
    else:
        body = {"error": {"message": message, "type": "germano_privacy_block", "code": status}}
    return jsonify(body), status


def _forward_headers():
    h = {"Content-Type": "application/json"}
    for k, v in request.headers.items():
        if k.lower() in _FWD_REQ_HEADERS:
            h[k] = v
    return h


def _resp_headers(r):
    out = {}
    for k, v in r.headers.items():
        lk = k.lower()
        if any(lk.startswith(p) for p in _FWD_RESP_PREFIXES):
            out[k] = v
    return out


def _session_log(extracted):
    if not extracted or not common.load_config().get("save_proxy_logs", True):
        return
    try:
        d = os.path.join(common.EXTRACTED_DIR, "proxy_sessions")
        os.makedirs(d, exist_ok=True)
        line = json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "path": request.path,
                           "map": {e["label"]: e["word"] for e in extracted}}, ensure_ascii=False)
        with open(os.path.join(d, time.strftime("%Y-%m-%d") + ".jsonl"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _anonymize_payload(payload, kind):
    import base64
    job = gproxy.collect_payload(payload)
    if not job.texts and not job.media:
        return []
    if not daemon_ready():
        raise gproxy.ProxyBlock("Motore IA di Germano non attivo: richiesta bloccata per evitare l'invio di dati in chiaro. "
                                "Avvia Germano dalla Dashboard (http://127.0.0.1:%d)." % PORT, 503)
    extracted = []
    if job.texts:
        r = daemon_call("/internal/anonymize_texts", {"texts": job.texts}, timeout=1800)
        if r.status_code == 503:   # es. modalita' Client con il Germano Server non raggiungibile
            raise gproxy.ProxyBlock(f"Motore IA di Germano non disponibile ({_daemon_error(r)}): richiesta bloccata, "
                                    "nessun dato inviato.", 503)
        if r.status_code != 200:
            raise gproxy.ProxyBlock(f"Anonimizzazione non riuscita ({r.status_code}): richiesta bloccata.", 500)
        results = r.json().get("results") or []
        if len(results) != len(job.texts):
            raise gproxy.ProxyBlock("Risposta incompleta del motore IA: richiesta bloccata.", 500)
        for setter, res in zip(job.setters, results):
            setter(res["anonymized"])
            extracted.extend(res.get("extracted_data") or [])
    for mime, data, setter, fname in job.media:
        r = daemon_call("/internal/process_file", {"filename": fname, "mode": "anonymize",
                                                    "data_b64": base64.b64encode(data).decode("ascii")}, timeout=3600)
        if r.status_code == 503:
            raise gproxy.ProxyBlock(f"Motore IA di Germano non disponibile ({_daemon_error(r)}): richiesta bloccata, "
                                    "nessun dato inviato.", 503)
        if r.status_code != 200:
            raise gproxy.ProxyBlock(f"Allegato '{fname}' non anonimizzabile: richiesta bloccata.", 500)
        res = r.json()
        setter(base64.b64decode(res["data_b64"]))
        extracted.extend(res.get("extracted_data") or [])
    for fin in job.finalizers:
        fin()
    return extracted


def _proxy(kind, sub=""):
    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict):
        return _proxy_error(kind, 400, "Corpo della richiesta non valido (JSON atteso).")
    try:
        extracted = _anonymize_payload(payload, kind)
    except gproxy.ProxyBlock as e:
        return _proxy_error(kind, e.status, str(e))
    except Exception as e:
        return _proxy_error(kind, 500, f"Blocco di sicurezza: anonimizzazione non riuscita ({e}).")
    _session_log(extracted)
    url = _target(kind, sub)
    try:
        r = _upstream.post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                           headers=_forward_headers(), stream=True, timeout=(20, 900))
    except Exception as e:
        return _proxy_error(kind, 502, f"Impossibile contattare il servizio IA ({url}): {e}")
    deanon = bool(common.load_config().get("enable_deanonymize", True))
    tag_map = vault_reader.tag_map() if deanon else {}
    ctype = r.headers.get("Content-Type", "")
    if r.status_code >= 400 or "text/event-stream" not in ctype:
        body = r.content
        r.close()
        if deanon and "json" in ctype:
            try:
                obj = gproxy.restore_obj(json.loads(body.decode("utf-8")), tag_map)
                return Response(json.dumps(obj, ensure_ascii=False), status=r.status_code,
                                content_type="application/json", headers=_resp_headers(r))
            except Exception:
                pass
        return Response(body, status=r.status_code, content_type=ctype or "application/json", headers=_resp_headers(r))

    def generate():
        parser = gproxy.SSEParser()
        rewriter = gproxy.StreamRewriter(tag_map) if deanon else None
        try:
            for chunk in r.iter_content(chunk_size=None):
                if not chunk:
                    continue
                if rewriter is None:
                    yield chunk
                    continue
                for name, data, other in parser.feed(chunk):
                    for n2, d2 in rewriter.process(name, data):
                        yield gproxy.serialize_event(n2, d2, other)
                        other = ()
            if rewriter is not None:
                for name, data, other in parser.close():
                    for n2, d2 in rewriter.process(name, data):
                        yield gproxy.serialize_event(n2, d2, other)
                        other = ()
        except Exception as e:
            err = {"type": "error", "error": {"type": "api_error", "message": f"Stream interrotto: {e}"}}
            yield gproxy.serialize_event("error", json.dumps(err))
        finally:
            r.close()

    headers = _resp_headers(r)
    headers.update({"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    return Response(stream_with_context(generate()), status=r.status_code, content_type="text/event-stream", headers=headers)


@app.route("/v1/chat/completions", methods=["POST"])
@app.route("/chat/completions", methods=["POST"])
def proxy_chat():
    return _proxy("chat")


@app.route("/v1/responses", methods=["POST"])
@app.route("/responses", methods=["POST"])
def proxy_responses():
    return _proxy("responses")


@app.route("/v1/messages", methods=["POST"])
@app.route("/messages", methods=["POST"])
def proxy_messages():
    return _proxy("anthropic")


@app.route("/v1/messages/count_tokens", methods=["POST"])
@app.route("/messages/count_tokens", methods=["POST"])
def proxy_count_tokens():
    return _proxy("anthropic", "/count_tokens")


@app.route("/v1/models", methods=["GET"])
@app.route("/models", methods=["GET"])
def proxy_models():
    """Elenco modelli: richiesta inoltrata al fornitore (non contiene dati personali), con ripiego locale."""
    is_anthropic = "x-api-key" in {k.lower() for k in request.headers.keys()} and "authorization" not in {k.lower() for k in request.headers.keys()}
    cfg = common.load_config()
    base = _strip_suffix(cfg.get("target_anthropic_url") if is_anthropic else cfg.get("target_api_url"))
    try:
        r = _upstream.get(base + "/models", headers=_forward_headers(), timeout=15)
        if r.status_code == 200:
            return Response(r.content, status=200, content_type=r.headers.get("Content-Type", "application/json"))
    except Exception:
        pass
    return jsonify({"object": "list", "data": [{"id": "germano-proxy", "object": "model", "created": 1686935002, "owned_by": "germano"}]})


# ------------------------------------------------------------------------------------------------
# Avvio
# ------------------------------------------------------------------------------------------------
def _port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((MAIN_HOST, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _existing_germano(port):
    try:
        r = _daemon_http.get(f"http://127.0.0.1:{port}/api/status", timeout=3)
        return r.status_code == 200 and "version" in r.json()
    except Exception:
        return False


def _open_browser_when_ready(url):
    def _run():
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        import webbrowser
        webbrowser.open(url)
    threading.Thread(target=_run, daemon=True).start()


def _shutdown():
    try:
        if is_daemon_running():
            stop_daemon(wait=4.0)
    except Exception:
        pass


def _install_pending_update():
    """Chiamata all'avvio dal launcher (germano_desktop.py: server.py --install-update) se c'è un aggiornamento già
    scaricato. Restituisce 10 se l'installer è partito (il launcher si chiude e l'installer riapre Germano a
    installazione finita); 0 se Germano deve avviarsi normalmente (nessun aggiornamento, oppure un tentativo
    precedente non è andato a buon fine: si riprova dalla Dashboard)."""
    if not gupdater.should_auto_install():
        return 0
    if not _port_free(PORT):
        print("Germano AI e' gia' in esecuzione: l'aggiornamento verra' installato al prossimo avvio.")
        return 0
    try:
        UPDATER.launch_install()
    except Exception as e:
        print(f"Impossibile installare l'aggiornamento: {e}")
        return 0
    print("Installazione dell'aggiornamento avviata: Germano si riaprira' da solo.")
    return 10


def main():
    url = f"http://127.0.0.1:{PORT}"
    if "--install-update" in sys.argv:
        return _install_pending_update()
    gupdater.cleanup_after_install()
    if not _port_free(PORT):
        if _existing_germano(PORT):
            print(f"Germano AI e' gia' in esecuzione: apro la Dashboard ({url}).")
            if os.environ.get("GERMANO_NO_BROWSER") != "1":
                import webbrowser
                webbrowser.open(url)
            return 0
        print(f"ERRORE: la porta {PORT} e' occupata da un altro programma.")
        print("Chiudi il programma che la usa oppure imposta un'altra porta in config.json (\"port\": 8010).")
        return 2
    try:
        import truststore
        truststore.inject_into_ssl()  # certificati di Windows (proxy aziendali con ispezione TLS)
    except Exception:
        pass
    atexit.register(_shutdown)
    _ensure_identity()
    mode, notes = _apply_operating_mode()          # parte Server: rete + rilevamento UDP
    server_on, client_on = common.mode_flags(mode)
    forced = common.mode_forced_by()
    print(f"Avvio Germano AI v{APP_VERSION} - modalita' {MODE_LABELS.get(mode, mode)}"
          + (f" (impostata da {forced})" if forced else ""))
    print(f"Dashboard:   {url}")
    print(f"Proxy API:   {url}/v1")
    if server_on:
        from germano import discovery as gdiscovery
        print("=" * 64)
        if LAN_MODE:
            print(" SERVER: in ascolto sulla RETE LOCALE. I computer della rete possono raggiungerlo:")
            for ip in gdiscovery.local_ipv4_addresses() or ["<IP di questo computer>"]:
                print(f"   Dashboard:  http://{ip}:{PORT}")
                print(f"   Proxy CLI:  http://{ip}:{PORT}/v1")
            print("")
            print(" Token condiviso (richiesto dalla rete a Proxy, Studio e motore):")
            print(f"   {LAN_TOKEN}")
            print(f"   Base URL con token:  http://<IP-server>:{PORT}/g/{LAN_TOKEN}/v1")
            if _DISCOVERY is not None:
                print(f" Rilevamento automatico attivo (UDP {DISCOVERY_PORT}).")
        for n in notes:
            print(f" ATTENZIONE: {n}")
        print("=" * 64)
    if client_on:
        print(" CLIENT: all'avvio del motore Germano cerca in rete un Germano Server a cui delegare il calcolo")
        print("         (Vault, file ed etichette restano su questo computer).")
    if mode != "standalone":
        start_daemon()   # Server: offre subito il motore alla rete. Client: si collega subito al server.
    print("La modalita' si cambia in qualsiasi momento dalle Impostazioni della Dashboard.")
    print("Chiudere questa finestra per arrestare Germano AI.")
    if os.environ.get("GERMANO_NO_BROWSER") != "1":
        _open_browser_when_ready(url)
    UPDATER.start_background()  # controlla solo se Windows segnala una connessione a Internet
    try:
        from werkzeug.serving import run_simple
        run_simple(MAIN_HOST, PORT, app, threaded=True, use_reloader=False, use_debugger=False)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
