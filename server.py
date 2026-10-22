"""Germano AI - server locale: Dashboard web, API REST e Proxy API per IDE/agenti IA.

Ascolta solo su 127.0.0.1. Avvia il demone IA (daemon.py) su richiesta e lo controlla tramite i file
in state/ e un'API interna protetta da token.
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
PORT = int(os.environ.get("GERMANO_PORT") or CFG.get("port") or 8000)
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}", f"http://[::1]:{PORT}"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

vault_reader = VaultReader()
UPDATER = gupdater.Updater()
_spawn_lock = threading.Lock()
_cache = {}
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
# Sicurezza: solo host locali (anti DNS-rebinding) e nessuna azione da siti web esterni (anti CSRF)
# ------------------------------------------------------------------------------------------------
@app.before_request
def _guard():
    host = (request.host or "").lower()
    hostname = host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]
    if hostname not in ALLOWED_HOSTS:
        return jsonify({"error": "Host non consentito: Germano AI accetta solo connessioni locali."}), 403
    if request.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("Origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return jsonify({"error": "Richiesta da un sito esterno bloccata."}), 403
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return jsonify({"error": "Richiesta da un sito esterno bloccata."}), 403
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


# ------------------------------------------------------------------------------------------------
# Stato, impostazioni, controllo motore
# ------------------------------------------------------------------------------------------------
def _count(folder):
    n = dirs = size = 0
    for root, ds, files in os.walk(folder):
        dirs += len(ds)
        for f in files:
            if f.startswith(common.TMP_PREFIX):
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
    return jsonify({
        "version": APP_VERSION, "running": running, "status": state, "error": err,
        "stats": st, "system": system, "progress": progress or {},
        "engine": daemon_state().get("engine") if running else None,
        "profile": cfg.get("compliance_mode"), "locked": bool(cfg.get("lock_settings")),
        "update": UPDATER.snapshot(),
    })


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        settings = data.get("settings", data)
        cfg, err = common.save_config(settings)
        resp = {"status": "success" if not err else "locked", "settings": cfg}
        if err:
            resp["message"] = err
        return jsonify(resp)
    return jsonify(common.load_config())


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}
    if isinstance(data.get("settings"), dict) and data["settings"]:
        common.save_config(data["settings"])
    common.remove_quietly(common.STOP_FLAG)
    started = start_daemon()
    return jsonify({"status": "success", "message": "Motore avviato" if started else "Motore gia' in esecuzione"})


@app.route("/api/stop", methods=["POST"])
@app.route("/api/stop_daemon", methods=["POST"])
def api_stop():
    stop_daemon()
    return jsonify({"status": "success", "message": "Motore fermato"})


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


def _germano_pids():
    """PID da attendere prima di sostituire i file: server, motore, processi rimasti e la finestra di START.bat."""
    pids = [os.getpid()]
    if is_daemon_running():  # verifica che il PID registrato sia davvero il motore di Germano
        pids.append(int(daemon_state()["pid"]))
    for p in _orphans():
        pids.append(p.pid)
        try:
            p.terminate()
        except Exception:
            pass
    try:
        parent = psutil.Process(os.getppid())
        cmd = " ".join(parent.cmdline() or []).lower()
        if parent.name().lower() == "cmd.exe" and "start.bat" in cmd:
            pids.append(parent.pid)  # la finestra di START.bat deve chiudersi prima di sostituire START.bat
    except Exception:
        pass
    return pids


@app.route("/api/update/install", methods=["POST"])
def api_update_install():
    if not gupdater.read_ready():
        return jsonify({"status": "error", "message": "Nessun aggiornamento pronto da installare."}), 400
    try:
        UPDATER.launch_install(_germano_pids(), restart=True)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Impossibile avviare l'installazione: {e}"}), 500

    def shutdown():
        time.sleep(1.0)
        try:
            stop_daemon(wait=4.0)
        finally:
            os._exit(10)  # START.bat riconosce il codice 10 e si chiude senza messaggi di errore
    threading.Thread(target=shutdown, daemon=True).start()
    return jsonify({"status": "success"})


@app.route("/api/update/ack", methods=["POST"])
def api_update_ack():
    gupdater.acknowledge_install()
    return jsonify({"status": "success"})


@app.route("/api/open_folder", methods=["POST"])
def api_open_folder():
    data = request.get_json(silent=True) or {}
    folder = data.get("folder", "output")
    if folder not in common.WORK_FOLDERS:
        return jsonify({"status": "error", "message": "Cartella non valida."}), 400
    path = common.WORK_FOLDERS[folder]
    os.makedirs(path, exist_ok=True)
    try:
        os.startfile(path)
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
        return jsonify({"status": "error", "message": "Nessun file selezionato."}), 400
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
                    if f.startswith(common.TMP_PREFIX):
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
        return jsonify({"status": "error", "message": "File non trovato."}), 404
    action = data.get("action")
    try:
        if action == "reveal":
            subprocess.Popen(f'explorer.exe /select,"{path}"')
        elif action == "open":
            if os.path.splitext(path)[1].lower() not in OPENABLE_EXTS:
                return jsonify({"status": "error", "message": "Per sicurezza questo tipo di file non viene aperto "
                                                              "direttamente: usa «Mostra nella cartella»."}), 400
            os.startfile(path)
        else:
            return jsonify({"status": "error", "message": "Azione non valida."}), 400
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
                 for f in files if not f.startswith(common.TMP_PREFIX)]
    else:
        names = [n for n in (data.get("names") or []) if isinstance(n, str)]
    moved, errors = [], []
    for name in names:
        src = _work_file("failed", name)
        if not src:
            errors.append(f"{name}: file non trovato")
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
        return jsonify({"error": "Cartella non autorizzata"}), 403
    base = os.path.abspath(common.WORK_FOLDERS[folder])
    target = os.path.abspath(os.path.join(base, filename))
    if os.path.commonpath([base, target]) != base or not os.path.isfile(target):
        return jsonify({"error": "File non trovato"}), 404
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
        return jsonify({"logs": [f"Errore lettura registro: {e}"]})


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
        return jsonify({"status": "success", "message": "Archivio corrispondenze azzerato."})
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
        return jsonify({"error": "Fornire un JSON con il campo 'text'."}), 400
    tag_map = vault_reader.tag_map()
    return jsonify({"status": "success", "restored": restore_text(str(data["text"]), tag_map), "vault_count": len(tag_map)})


@app.route("/api/v1/deanonymize_file", methods=["POST"])
def api_deanonymize_file():
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return jsonify({"status": "error", "message": "Nessun file selezionato per il ripristino."}), 400
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
            return jsonify({"status": "error", "message": f"Impossibile ripristinare {name}: {e}"}), 400
        finally:
            common.remove_quietly(staged)
    if not out:
        return jsonify({"status": "error", "message": "Impossibile ripristinare il file."}), 400
    if request.args.get("raw") == "1" and len(out) == 1:
        return send_file(os.path.join(common.OUTPUT_DIR, out[0]["name"]), as_attachment=True, download_name=out[0]["name"])
    return jsonify({"status": "success", "restored_count": len(out), "files": out, "vault_count": len(tag_map)})


@app.route("/api/v1/anonymize_text", methods=["POST"])
def api_anonymize_text():
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict) or "text" not in data:
        return jsonify({"error": "Fornire un JSON con il campo 'text'."}), 400
    text = str(data["text"])
    force = bool(data.get("force_anonymize", False))
    if not force and common.load_config().get("enable_deanonymize", True):
        tag_map = vault_reader.tag_map()
        if contains_tags(text, tag_map):
            restored = restore_text(text, tag_map)
            return jsonify({"anonymized": restored, "restored": restored, "auto_restored": True, "extracted_data": []})
    if not daemon_ready():
        return jsonify({"error": "Il motore IA non e' pronto: avvialo dalla Dashboard e attendi il caricamento."}), 503
    try:
        r = daemon_call("/internal/anonymize_text", {"text": text, "force_anonymize": True}, timeout=900)
        if r.status_code == 200:
            return jsonify(r.json())
        return jsonify({"error": f"Errore del motore IA ({r.status_code}): {r.text[:300]}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/anonymize", methods=["POST"])
def api_anonymize_file():
    import base64
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"error": "Nessun file fornito. Usa multipart/form-data con la chiave 'file'."}), 400
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
        return jsonify({"error": "Il motore IA non e' pronto: avvialo dalla Dashboard e attendi il caricamento."}), 503
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
        return jsonify({"error": f"Elaborazione non riuscita: {msg}"}), 415 if r.status_code == 415 else 500
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
        s.bind(("127.0.0.1", port))
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
    """Chiamata da START.bat (server.py --install-update) se c'è un aggiornamento già scaricato e preparato.
    Restituisce 10 se l'installazione è partita (START.bat si chiude e il programma si riavvia da solo)."""
    if not gupdater.read_ready():
        return 0
    if not _port_free(PORT):
        print("Germano AI e' gia' in esecuzione: l'aggiornamento verra' installato al prossimo avvio.")
        return 0
    try:
        UPDATER.launch_install(_germano_pids(), restart=True)
    except Exception as e:
        print(f"Impossibile installare l'aggiornamento: {e}")
        return 0
    print("Installazione dell'aggiornamento avviata in una nuova finestra: Germano si riavviera' da solo.")
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
    print(f"Avvio Germano AI v{APP_VERSION} - Server locale")
    print(f"Dashboard:   {url}")
    print(f"Proxy API:   {url}/v1")
    print("Chiudere questa finestra per arrestare Germano AI.")
    if os.environ.get("GERMANO_NO_BROWSER") != "1":
        _open_browser_when_ready(url)
    UPDATER.start_background()  # controlla solo se Windows segnala una connessione a Internet
    try:
        from werkzeug.serving import run_simple
        run_simple("127.0.0.1", PORT, app, threaded=True, use_reloader=False, use_debugger=False)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
