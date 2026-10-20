import os
import sys

# Ensure Base Directory & Offline Environment Variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

if hasattr(os, "add_dll_directory"):
    runtime_dir = os.path.dirname(sys.executable)
    if os.path.isdir(runtime_dir):
        try:
            os.add_dll_directory(runtime_dir)
        except Exception:
            pass

from flask import Flask, render_template, jsonify, request, Response, stream_with_context, send_file
import subprocess
import requests
import uuid
import time
import json
import psutil
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Disable verbose Werkzeug access logs for 1-second polling endpoints
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

def get_app_version():
    try:
        if os.path.exists("VERSION"):
            with open("VERSION", "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
    except Exception:
        pass
    return "0.50-alpha"

APP_VERSION = get_app_version()

DAEMON_PID_FILE = "daemon.pid"
STOP_FLAG = "stop.flag"
READY_FLAG = "ready.flag"
LOG_FILE = "daemon.log"
CONFIG_FILE = "config.json"

DEFAULT_SETTINGS = {
    "target_api_url": "https://api.openai.com/v1/chat/completions",
    "ui_mode": "simple",
    "compliance_mode": "PA",
    "enable_deanonymize": True,
    "enable_model_velvet": True,
    "enable_model_italian_ner": True,
    "enable_ocr": True,
    "enable_faces": True,
    "enable_signatures": True,
    "enable_plate_vision": True,
    "enable_regex": True,
    "ai_threshold": 0.0,
    "hardware_mode": "gpu_fallback",
    "censor_person": True,
    "censor_profession": True,
    "censor_address": True,
    "censor_cadastre": True,
    "censor_email": True,
    "censor_phone": True,
    "censor_account": True,
    "censor_financial": True,
    "censor_url": True,
    "censor_date": True,
    "censor_secret": True,
    "censor_cf_iva": True,
    "censor_org": True,
    "censor_plates_docs": True,
    "censor_medical": True,
    "censor_medicine": True,
    "censor_legal": True,
    "censor_civil_status": True
}

MODEL_AND_FEATURE_KEYS = [
    "enable_model_velvet", "enable_model_italian_ner", "enable_ocr",
    "enable_faces", "enable_signatures", "enable_plate_vision", "enable_regex",
    "censor_person", "censor_profession", "censor_address", "censor_cadastre",
    "censor_email", "censor_phone", "censor_account", "censor_financial",
    "censor_url", "censor_date", "censor_secret", "censor_cf_iva",
    "censor_org", "censor_plates_docs", "censor_medical", "censor_medicine",
    "censor_legal", "censor_civil_status"
]

for folder in ["input", "output", "processed", "failed", "extracted"]:
    os.makedirs(folder, exist_ok=True)


def load_config():
    cfg = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    cfg.update(data)
        except Exception:
            pass
    return cfg


def save_config(new_settings):
    cfg = load_config()
    if isinstance(new_settings, dict):
        cfg.update(new_settings)
        # Se l'utente disabilita un qualsiasi modello o una singola feature (o alza la soglia),
        # sblocca automaticamente in modalità personalizzata (PD) affinché la scelta sia rispettata.
        if any(not bool(cfg.get(k, True)) for k in MODEL_AND_FEATURE_KEYS) or float(cfg.get("ai_threshold", 0.0)) > 0:
            cfg["compliance_mode"] = "PD"
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)
    return cfg


def get_daemon_pid():
    if os.path.exists(DAEMON_PID_FILE):
        try:
            with open(DAEMON_PID_FILE, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            return None
    return None


def is_daemon_running():
    pid = get_daemon_pid()
    if pid is not None:
        try:
            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        except Exception:
            pass
        # Stale PID file: clean up
        try:
            os.remove(DAEMON_PID_FILE)
        except Exception:
            pass
        try:
            if os.path.exists(READY_FLAG):
                os.remove(READY_FLAG)
        except Exception:
            pass
    return False


def count_folder_files(folder_name):
    count = 0
    folders = 0
    total_bytes = 0
    if os.path.exists(folder_name):
        for root, dirs, files in os.walk(folder_name):
            count += len(files)
            folders += len(dirs)
            for f in files:
                try:
                    total_bytes += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
    return count, folders, total_bytes


@app.route('/')
def index():
    return render_template('index.html', version=APP_VERSION)


@app.route('/guide')
@app.route('/guide.html')
def guide():
    return render_template('guide.html', version=APP_VERSION)


@app.route('/api/status')
def status():
    running = is_daemon_running()

    if os.path.exists(STOP_FLAG):
        if not running:
            try:
                os.remove(STOP_FLAG)
            except Exception:
                pass
            current_status = 'stopped'
        else:
            current_status = 'shutting_down'
    else:
        if running:
            if os.path.exists(READY_FLAG):
                current_status = 'running'
            else:
                current_status = 'loading_models'
        else:
            current_status = 'stopped'

    pending, pending_folders, pending_bytes = count_folder_files("input")
    processed, _, _ = count_folder_files("processed")
    outputs, _, _ = count_folder_files("output")
    failed, _, _ = count_folder_files("failed")
    extracted, _, _ = count_folder_files("extracted")

    vault_count = 0
    vault_path = os.path.join("extracted", "deanonymize_vault.json")
    if os.path.exists(vault_path):
        try:
            with open(vault_path, "r", encoding="utf-8") as vf:
                vdata = json.load(vf)
                vault_count = len(vdata.get("tag_to_word", {}))
        except Exception:
            pass

    try:
        mem = psutil.virtual_memory()
        ram_percent = round(mem.percent, 1)
        ram_used_gb = round(mem.used / (1024 ** 3), 1)
        ram_total_gb = round(mem.total / (1024 ** 3), 1)
        cpu_percent = round(psutil.cpu_percent(interval=None), 1)
    except Exception:
        ram_percent = 0
        ram_used_gb = 0
        ram_total_gb = 0
        cpu_percent = 0

    return jsonify({
        'version': APP_VERSION,
        'running': running,
        'status': current_status,
        'stats': {
            'pending': pending,
            'pending_folders': pending_folders,
            'pending_bytes': pending_bytes,
            'processed': processed,
            'outputs': outputs,
            'failed': failed,
            'extracted': extracted,
            'vault_count': vault_count
        },
        'system': {
            'cpu_percent': cpu_percent,
            'ram_percent': ram_percent,
            'ram_used_gb': ram_used_gb,
            'ram_total_gb': ram_total_gb
        }
    })


@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        settings = data.get('settings', data)
        updated = save_config(settings)
        return jsonify({'status': 'success', 'settings': updated})
    return jsonify(load_config())


@app.route('/api/start', methods=['GET', 'POST'])
def start_daemon():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        settings = data.get('settings', {})
        if settings:
            save_config(settings)

    if os.path.exists(STOP_FLAG):
        try:
            os.remove(STOP_FLAG)
        except Exception:
            pass

    if not is_daemon_running():
        if os.path.exists(READY_FLAG):
            try:
                os.remove(READY_FLAG)
            except Exception:
                pass
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        env["HF_HUB_DISABLE_TELEMETRY"] = "1"
        log_f = open(LOG_FILE, "a", encoding="utf-8")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            [sys.executable, "daemon.py"],
            stdout=log_f,
            stderr=log_f,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=BASE_DIR,
            creationflags=creationflags
        )
        # Registra subito il PID: evita che durante il caricamento di PyTorch (5-10 s)
        # un secondo clic o un auto-avvio lancino un secondo motore in parallelo.
        try:
            with open(DAEMON_PID_FILE, "w", encoding="utf-8") as pf:
                pf.write(str(proc.pid))
        except Exception:
            pass
        try:
            log_f.close()
        except Exception:
            pass

    return jsonify({'status': 'success', 'message': 'Daemon started'})


@app.route('/api/stop', methods=['GET', 'POST'])
def stop():
    with open(STOP_FLAG, "w", encoding="utf-8") as f:
        f.write("1")
    if os.path.exists(READY_FLAG):
        try:
            os.remove(READY_FLAG)
        except Exception:
            pass

    # If the daemon is still loading models or does not respond quickly, terminate the process safely
    pid = get_daemon_pid()
    if pid is not None:
        try:
            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                # Give it up to 1.5s to exit gracefully via stop.flag, then terminate
                try:
                    p.wait(timeout=1.5)
                except psutil.TimeoutExpired:
                    p.terminate()
                    try:
                        p.wait(timeout=2.0)
                    except psutil.TimeoutExpired:
                        p.kill()
        except Exception:
            pass

    for flag in [DAEMON_PID_FILE, READY_FLAG, STOP_FLAG]:
        if os.path.exists(flag):
            try:
                os.remove(flag)
            except Exception:
                pass

    return jsonify({'status': 'success', 'message': 'Daemon stopped'})


@app.route('/api/stop_daemon', methods=['POST'])
def stop_daemon():
    return stop()


@app.route('/api/check_update', methods=['GET'])
def check_update():
    try:
        response = requests.get(
            "https://raw.githubusercontent.com/germano-ai/germano-ai-standalone/master/VERSION",
            timeout=2
        )
        if response.status_code == 200:
            latest_version = response.text.strip()
            return jsonify({
                "current_version": APP_VERSION,
                "latest_version": latest_version,
                "update_available": (latest_version != APP_VERSION and len(latest_version) < 20),
                "offline": False
            })
    except Exception:
        # Normal condition when running 100% offline
        pass

    return jsonify({
        "current_version": APP_VERSION,
        "latest_version": APP_VERSION,
        "update_available": False,
        "offline": True
    })


@app.route('/api/open_folder', methods=['POST'])
def open_folder():
    data = request.get_json(silent=True) or {}
    folder = data.get("folder", "output")
    allowed = {"input", "output", "processed", "failed", "extracted"}
    if folder not in allowed:
        return jsonify({"status": "error", "message": "Cartella non valida."}), 400
    target_path = os.path.abspath(os.path.join(BASE_DIR, folder))
    os.makedirs(target_path, exist_ok=True)
    try:
        os.startfile(target_path)
        return jsonify({"status": "success", "path": target_path})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/upload_files', methods=['POST'])
def upload_files():
    if 'files' not in request.files and 'file' not in request.files:
        return jsonify({"status": "error", "message": "Nessun file selezionato."}), 400

    from daemon import file_contains_vault_tags, deanonymize_file, load_vault_tag_map
    cfg = load_config()
    enable_deanon = bool(cfg.get("enable_deanonymize", True))
    tag_map = load_vault_tag_map() if enable_deanon else {}

    uploaded = request.files.getlist('files') or request.files.getlist('file')
    saved_count = 0
    saved_names = []
    auto_restored_files = []
    os.makedirs("input", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    os.makedirs("processed", exist_ok=True)

    for f in uploaded:
        if f and f.filename:
            safe_name = secure_filename(os.path.basename(f.filename))
            if not safe_name:
                continue
            dest = os.path.join("input", safe_name)
            if os.path.exists(dest):
                base, ext = os.path.splitext(safe_name)
                safe_name = f"{base}_{str(uuid.uuid4())[:6]}{ext}"
                dest = os.path.join("input", safe_name)
            f.save(dest)

            # RILEVAMENTO E RIPRISTINO AUTOMATICO:
            # Se lo switch 'enable_deanonymize' è attivo e il file caricato contiene già etichette del Vault (es. [PERSONA_1]),
            # Germano capisce da solo che è un file di ritorno dall'AI e rimette subito a posto i dati veri!
            if enable_deanon and file_contains_vault_tags(dest, tag_map):
                out_name = safe_name if safe_name.startswith("ripristinato_") else f"ripristinato_{safe_name}"
                out_path = os.path.join("output", out_name)
                proc_path = os.path.join("processed", safe_name)
                try:
                    deanonymize_file(dest, out_path, tag_map)
                    if os.path.exists(proc_path):
                        os.remove(proc_path)
                    if os.path.exists(dest):
                        os.replace(dest, proc_path)
                    auto_restored_files.append({
                        "name": out_name,
                        "download_url": f"/api/download/output/{out_name}"
                    })
                    continue
                except Exception:
                    pass

            saved_count += 1
            saved_names.append(safe_name)

    return jsonify({
        "status": "success",
        "saved_count": saved_count,
        "files": saved_names,
        "auto_restored_count": len(auto_restored_files),
        "auto_restored_files": auto_restored_files
    })


@app.route('/api/files', methods=['GET'])
def list_recent_files():
    result = {}
    for folder in ["input", "output", "processed", "failed", "extracted"]:
        items = []
        if os.path.exists(folder):
            for root, _, files in os.walk(folder):
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, folder).replace("\\", "/")
                    try:
                        st = os.stat(full_p)
                        items.append({
                            "name": rel_p,
                            "size": st.st_size,
                            "mtime": st.st_mtime
                        })
                    except Exception:
                        pass
        items.sort(key=lambda x: x["mtime"], reverse=True)
        result[folder] = items[:50]
    return jsonify(result)


@app.route('/api/download/<folder>/<path:filename>', methods=['GET'])
def download_file(folder, filename):
    if folder not in {"output", "extracted", "processed", "failed"}:
        return jsonify({"error": "Folder non autorizzata"}), 403
    base_folder = os.path.abspath(os.path.join(BASE_DIR, folder))
    target = os.path.abspath(os.path.join(base_folder, filename))
    if not target.startswith(base_folder) or not os.path.isfile(target):
        return jsonify({"error": "File non trovato"}), 404
    return send_file(target, as_attachment=True, download_name=os.path.basename(target))


@app.route('/api/clear_logs', methods=['POST'])
def clear_logs():
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] Log puliti dall'utente.\n")
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/vault', methods=['GET'])
def get_vault():
    from daemon import load_vault_tag_map
    tag_map = load_vault_tag_map()
    items = [{"tag": k, "value": v} for k, v in tag_map.items() if "_" in k]
    return jsonify({"status": "success", "count": len(items), "items": items})


@app.route('/api/clear_vault', methods=['POST'])
def api_clear_vault():
    from daemon import clear_vault
    clear_vault()
    return jsonify({"status": "success", "message": "Archivio corrispondenze azzerato."})


@app.route('/api/v1/deanonymize_text', methods=['POST'])
def api_deanonymize_text():
    from daemon import deanonymize_string, load_vault_tag_map
    data = request.get_json(force=True, silent=True)
    if not data or 'text' not in data:
        return jsonify({"error": "Fornire un JSON con il campo 'text'."}), 400
    tag_map = load_vault_tag_map()
    restored = deanonymize_string(data["text"], tag_map)
    return jsonify({
        "status": "success",
        "restored": restored,
        "vault_count": len(tag_map)
    })


@app.route('/api/v1/deanonymize_file', methods=['POST'])
def api_deanonymize_file():
    from daemon import deanonymize_file, load_vault_tag_map
    if 'files' not in request.files and 'file' not in request.files:
        return jsonify({"status": "error", "message": "Nessun file selezionato per il ripristino."}), 400

    uploaded = request.files.getlist('files') or request.files.getlist('file')
    os.makedirs("output", exist_ok=True)
    os.makedirs("processed", exist_ok=True)
    tag_map = load_vault_tag_map()
    restored_files = []

    for f in uploaded:
        if f and f.filename:
            safe_name = secure_filename(os.path.basename(f.filename))
            if not safe_name:
                continue
            tmp_in = os.path.join("processed", f"tmp_{uuid.uuid4().hex[:6]}_{safe_name}")
            out_name = safe_name if safe_name.startswith("ripristinato_") else f"ripristinato_{safe_name}"
            out_path = os.path.join("output", out_name)
            f.save(tmp_in)
            try:
                deanonymize_file(tmp_in, out_path, tag_map)
                restored_files.append({
                    "name": out_name,
                    "download_url": f"/api/download/output/{out_name}"
                })
            finally:
                if os.path.exists(tmp_in):
                    try:
                        os.remove(tmp_in)
                    except Exception:
                        pass

    if not restored_files:
        return jsonify({"status": "error", "message": "Impossibile ripristinare il file."}), 400

    if request.args.get("raw") == "1" and len(restored_files) == 1:
        target = os.path.join("output", restored_files[0]["name"])
        return send_file(target, as_attachment=True, download_name=restored_files[0]["name"])

    return jsonify({
        "status": "success",
        "restored_count": len(restored_files),
        "files": restored_files,
        "vault_count": len(tag_map)
    })


@app.route('/api/v1/anonymize_text', methods=['POST'])
def api_anonymize_text():
    data = request.get_json(force=True, silent=True)
    if not data or 'text' not in data:
        return jsonify({"error": "Fornire un JSON con il campo 'text'."}), 400

    text = data["text"]
    force_anon = bool(data.get("force_anonymize", False))
    cfg = load_config()

    # RILEVAMENTO E RIPRISTINO AUTOMATICO DEL TESTO DI RITORNO DALL'AI:
    if not force_anon and cfg.get("enable_deanonymize", True):
        from daemon import text_contains_vault_tags, deanonymize_string, load_vault_tag_map
        tag_map = load_vault_tag_map()
        if text_contains_vault_tags(text, tag_map):
            restored = deanonymize_string(text, tag_map)
            return jsonify({
                "anonymized": restored,
                "restored": restored,
                "auto_restored": True,
                "extracted_data": []
            })

    if not is_daemon_running():
        return jsonify({"error": "Il demone IA non è in esecuzione. Avvialo dalla Dashboard."}), 503

    try:
        resp = requests.post(
            "http://127.0.0.1:8001/internal/anonymize_text",
            json={"text": text, "force_anonymize": force_anon},
            timeout=60
        )
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"error": f"Errore interno del demone ({resp.status_code})."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/anonymize', methods=['POST'])
def api_anonymize():
    if 'file' not in request.files:
        return jsonify({"error": "Nessun file fornito. Usa multipart/form-data con la chiave 'file'."}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nessun file selezionato."}), 400

    uid = str(uuid.uuid4())[:8]
    original_name = secure_filename(file.filename)
    base_name, ext = os.path.splitext(original_name)
    safe_name = f"{base_name}_{uid}{ext}"

    input_path = os.path.join("input", safe_name)
    output_path = os.path.join("output", safe_name)
    output_pdf_fallback = os.path.join("output", f"{base_name}_{uid}.pdf")
    failed_path = os.path.join("failed", safe_name)

    os.makedirs("input", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    os.makedirs("processed", exist_ok=True)

    file.save(input_path)

    cfg = load_config()
    if cfg.get("enable_deanonymize", True):
        from daemon import file_contains_vault_tags, deanonymize_file, load_vault_tag_map
        tag_map = load_vault_tag_map()
        if file_contains_vault_tags(input_path, tag_map):
            deanonymize_file(input_path, output_path, tag_map)
            proc_path = os.path.join("processed", safe_name)
            try:
                if os.path.exists(proc_path):
                    os.remove(proc_path)
                os.replace(input_path, proc_path)
            except Exception:
                pass
            return send_file(output_path, as_attachment=True, download_name=original_name)

    if not is_daemon_running():
        try:
            os.remove(input_path)
        except Exception:
            pass
        return jsonify({"error": "Il demone IA non è in esecuzione."}), 503

    timeout = 120
    start_time = time.time()

    while time.time() - start_time < timeout:
        if not os.path.exists(input_path):
            if os.path.exists(output_path):
                return send_file(output_path, as_attachment=True, download_name=original_name)
            if os.path.exists(output_pdf_fallback):
                dl_name = os.path.splitext(original_name)[0] + ".pdf"
                return send_file(output_pdf_fallback, as_attachment=True, download_name=dl_name)
            if os.path.exists(failed_path):
                return jsonify({"error": "Errore durante l'elaborazione del file."}), 500

        time.sleep(0.3)

    return jsonify({"error": "Timeout: l'elaborazione ha impiegato troppo tempo."}), 504


@app.route('/api/logs')
def get_logs():
    if not os.path.exists(LOG_FILE):
        return jsonify({'logs': []})

    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return jsonify({'logs': lines[-100:]})
    except Exception as e:
        return jsonify({'logs': [f"Error reading logs: {str(e)}"]})


@app.route('/api/check_orphans')
def check_orphans():
    count = 0
    try:
        current_pid = get_daemon_pid() or -1
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = p.info.get('cmdline')
                name = p.info.get('name')
                if cmdline and name:
                    if "python" in name.lower() and any("daemon.py" in cmd for cmd in cmdline):
                        if p.info['pid'] != current_pid:
                            count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        print(f"Error checking orphans: {e}")

    return jsonify({'orphans': count})


@app.route('/api/kill_orphans', methods=['POST'])
def kill_orphans():
    killed = 0
    try:
        current_pid = get_daemon_pid() or -1
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = p.info.get('cmdline')
                name = p.info.get('name')
                if cmdline and name:
                    if "python" in name.lower() and any("daemon.py" in cmd for cmd in cmdline):
                        if p.info['pid'] != current_pid:
                            p.terminate()
                            killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

    return jsonify({'status': 'success', 'killed': killed})


@app.route('/v1/models', methods=['GET'])
@app.route('/models', methods=['GET'])
def proxy_models():
    return jsonify({
        "object": "list",
        "data": [
            {"id": "germano-proxy", "object": "model", "created": 1686935002, "owned_by": "germano"}
        ]
    })


class StreamTagBuffer:
    """Bufferizza i token SSE in streaming quando compare '[' per ricomporre e de-anonimizzare al volo tag spezzati (es. '[PER' + 'SONA_1]')."""
    def __init__(self, deanon_fn):
        self.deanon_fn = deanon_fn
        self.buf = ""

    def feed(self, chunk):
        if not isinstance(chunk, str) or not chunk:
            return chunk
        self.buf += chunk
        if "[" not in self.buf:
            out = self.buf
            self.buf = ""
            return self.deanon_fn(out)

        last_open = self.buf.rfind("[")
        last_close = self.buf.rfind("]")
        if last_close > last_open:
            out = self.deanon_fn(self.buf)
            self.buf = ""
            return out

        # C'è una '[' aperta non ancora chiusa da ']': se il frammento dopo '[' è troppo lungo (>36 char) o ha a-capo, rilascia
        tail = self.buf[last_open:]
        if len(tail) > 36 or "\n" in tail:
            out = self.deanon_fn(self.buf)
            self.buf = ""
            return out

        prefix = self.buf[:last_open]
        self.buf = tail
        return self.deanon_fn(prefix) if prefix else ""

    def flush(self):
        if not self.buf:
            return ""
        out = self.deanon_fn(self.buf)
        self.buf = ""
        return out


@app.route('/v1/chat/completions', methods=['POST'])
@app.route('/chat/completions', methods=['POST'])
@app.route('/v1/responses', methods=['POST'])
@app.route('/responses', methods=['POST'])
@app.route('/v1/messages', methods=['POST'])
@app.route('/messages', methods=['POST'])
def proxy_chat_completions():
    payload = request.get_json(force=True, silent=True) or {}
    auth_header = request.headers.get("Authorization")
    api_key_header = request.headers.get("x-api-key")
    anthropic_version = request.headers.get("anthropic-version")

    req_path = request.path
    cfg = load_config()
    raw_target = (cfg.get("target_api_url") or "https://api.openai.com/v1/chat/completions").strip().rstrip("/")

    # Risolve dinamicamente l'endpoint upstream per OpenAI Chat Completions, Codex Responses API o Anthropic Messages
    if req_path.endswith("/responses"):
        if raw_target.endswith("/chat/completions"):
            target_api_url = raw_target[:-len("/chat/completions")] + "/responses"
        elif not raw_target.endswith("/responses"):
            target_api_url = raw_target + "/responses"
        else:
            target_api_url = raw_target
    elif req_path.endswith("/messages"):
        if "openai.com" in raw_target and api_key_header:
            target_api_url = "https://api.anthropic.com/v1/messages"
        elif raw_target.endswith("/chat/completions"):
            target_api_url = raw_target[:-len("/chat/completions")] + "/messages"
        elif not raw_target.endswith("/messages"):
            target_api_url = raw_target + "/messages"
        else:
            target_api_url = raw_target
    else:
        if not raw_target.endswith("/chat/completions"):
            target_api_url = raw_target + "/chat/completions"
        else:
            target_api_url = raw_target

    session_map = {}

    def anonymize_text_via_daemon(text):
        if not isinstance(text, str) or not text.strip():
            return text
        if not is_daemon_running():
            raise Exception(
                "Germano IA Daemon non in esecuzione. Blocco di sicurezza attivato: "
                "richiesta interrotta per prevenire la fuga di dati in chiaro."
            )
        try:
            resp = requests.post(
                "http://127.0.0.1:8001/internal/anonymize_text",
                json={"text": text, "force_anonymize": True},
                timeout=60
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("extracted_data", []):
                    session_map[item["label"]] = item["word"]
                return data.get("anonymized", text)
            else:
                raise Exception(f"Il Demone IA ha restituito errore {resp.status_code}.")
        except Exception as e:
            app.logger.error(f"Daemon proxy error: {e}")
            raise Exception(f"Errore critico durante l'anonimizzazione del testo: {e}. Richiesta bloccata.")

    def anonymize_image_via_daemon(b64_string):
        if not is_daemon_running():
            raise Exception("Germano IA Daemon non in esecuzione. Blocco di sicurezza attivato per le immagini.")

        if not b64_string.startswith("data:image"):
            return b64_string

        import base64
        try:
            header, encoded = b64_string.split(",", 1)
            ext = ".jpg"
            if "png" in header.lower():
                ext = ".png"
            elif "webp" in header.lower():
                ext = ".webp"

            img_data = base64.b64decode(encoded)
            uid = str(uuid.uuid4())[:8]
            filename = f"proxy_image_{uid}{ext}"

            input_path = os.path.join("input", filename)
            output_path = os.path.join("output", filename)
            processed_path = os.path.join("processed", filename)
            failed_path = os.path.join("failed", filename)

            with open(input_path, "wb") as f:
                f.write(img_data)

            start_time = time.time()
            timeout = 60
            processed_ok = False
            failed_state = False

            while time.time() - start_time < timeout:
                if not os.path.exists(input_path):
                    if os.path.exists(output_path):
                        processed_ok = True
                        break
                    if os.path.exists(failed_path):
                        failed_state = True
                        break
                time.sleep(0.3)

            if processed_ok:
                with open(output_path, "rb") as f:
                    new_img_data = f.read()
                new_encoded = base64.b64encode(new_img_data).decode('utf-8')

                for p in [input_path, output_path, processed_path]:
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass

                return f"{header},{new_encoded}"
            else:
                try:
                    if os.path.exists(input_path):
                        os.remove(input_path)
                except Exception:
                    pass
                if failed_state:
                    raise Exception("Immagine rifiutata o corrotta (finita nella cartella failed). Impossibile procedere.")
                else:
                    raise Exception(f"Timeout durante l'elaborazione OCR e censura dell'immagine (> {timeout}s).")

        except Exception as e:
            app.logger.error(f"Image proxy error: {e}")
            raise Exception(f"Errore critico durante l'anonimizzazione visiva: {e}. Blocco di sicurezza attivato.")

    def _anonymize_outgoing_node(node):
        if isinstance(node, list):
            for idx, item in enumerate(node):
                if isinstance(item, str):
                    node[idx] = anonymize_text_via_daemon(item)
                else:
                    _anonymize_outgoing_node(item)
        elif isinstance(node, dict):
            for k in ["content", "text", "output", "instructions", "system"]:
                if k in node:
                    if isinstance(node[k], str):
                        node[k] = anonymize_text_via_daemon(node[k])
                    elif isinstance(node[k], (list, dict)):
                        _anonymize_outgoing_node(node[k])
            if node.get("type") == "image_url" and isinstance(node.get("image_url"), dict):
                url = node["image_url"].get("url", "")
                if isinstance(url, str) and url.startswith("data:image"):
                    node["image_url"]["url"] = anonymize_image_via_daemon(url)
            if "function" in node and isinstance(node["function"], dict) and isinstance(node["function"].get("arguments"), str):
                node["function"]["arguments"] = anonymize_text_via_daemon(node["function"]["arguments"])
            if "tool_calls" in node and isinstance(node["tool_calls"], list):
                _anonymize_outgoing_node(node["tool_calls"])

    try:
        if "messages" in payload:
            _anonymize_outgoing_node(payload["messages"])
        if "system" in payload:
            if isinstance(payload["system"], str):
                payload["system"] = anonymize_text_via_daemon(payload["system"])
            else:
                _anonymize_outgoing_node(payload["system"])
        if "instructions" in payload and isinstance(payload["instructions"], str):
            payload["instructions"] = anonymize_text_via_daemon(payload["instructions"])
        if "input" in payload:
            if isinstance(payload["input"], str):
                payload["input"] = anonymize_text_via_daemon(payload["input"])
            else:
                _anonymize_outgoing_node(payload["input"])
    except Exception as safety_error:
        return jsonify({
            "error": {
                "message": str(safety_error),
                "type": "safety_privacy_block",
                "code": 500
            }
        }), 500

    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    if api_key_header:
        headers["x-api-key"] = api_key_header
    if anthropic_version:
        headers["anthropic-version"] = anthropic_version

    is_stream = payload.get("stream", False)

    if session_map:
        os.makedirs("extracted", exist_ok=True)
        try:
            timestamp = int(time.time() * 1000)
            with open(f"extracted/proxy_session_{timestamp}.json", "w", encoding="utf-8") as f:
                json.dump(session_map, f, indent=4, ensure_ascii=False)
        except Exception as e:
            app.logger.error(f"Failed to save session map: {e}")

    enable_deanon = bool(cfg.get("enable_deanonymize", True))

    def _deanonymize_response_text(txt):
        if not enable_deanon or not isinstance(txt, str) or not txt:
            return txt
        from daemon import deanonymize_string, load_vault_tag_map
        merged_map = load_vault_tag_map()
        merged_map.update(session_map)
        return deanonymize_string(txt, merged_map)

    def _deanonymize_response_obj(obj):
        """Ripristina ricorsivamente i dati reali sia nei messaggi testuali sia negli argomenti tool_calls / function_call / file_edit di Antigravity, Codex, Cursor e Claude Code."""
        if isinstance(obj, str):
            return _deanonymize_response_text(obj)
        elif isinstance(obj, list):
            return [_deanonymize_response_obj(x) for x in obj]
        elif isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k in ("id", "object", "created", "model", "role", "finish_reason", "type", "index", "stop_reason"):
                    out[k] = v
                else:
                    out[k] = _deanonymize_response_obj(v)
            return out
        return obj

    if not is_stream:
        try:
            r = requests.post(target_api_url, json=payload, headers=headers, timeout=120)
            if r.status_code != 200:
                return Response(r.content, status=r.status_code, content_type=r.headers.get('Content-Type'))
            res_json = r.json()
            if enable_deanon:
                res_json = _deanonymize_response_obj(res_json)
            return jsonify(res_json)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        def generate():
            content_buf = StreamTagBuffer(_deanonymize_response_text)
            tool_bufs = {}
            try:
                with requests.post(target_api_url, json=payload, headers=headers, stream=True, timeout=120) as r:
                    for line in r.iter_lines():
                        if not line:
                            continue
                        decoded_line = line.decode('utf-8', errors='replace')
                        if not enable_deanon:
                            yield f"{decoded_line}\n\n"
                            continue

                        if decoded_line.startswith("data: "):
                            data_str = decoded_line[6:].strip()
                            if data_str == "[DONE]":
                                yield "data: [DONE]\n\n"
                                continue
                            try:
                                evt = json.loads(data_str)
                                # 1. OpenAI / Antigravity / Cursor Chat Completions SSE delta
                                if isinstance(evt, dict) and "choices" in evt:
                                    for ch in evt.get("choices", []):
                                        delta = ch.get("delta") if isinstance(ch, dict) else None
                                        if isinstance(delta, dict):
                                            if isinstance(delta.get("content"), str):
                                                delta["content"] = content_buf.feed(delta["content"])
                                            if isinstance(delta.get("tool_calls"), list):
                                                for tc in delta["tool_calls"]:
                                                    if isinstance(tc, dict) and isinstance(tc.get("function"), dict):
                                                        idx = tc.get("index", 0)
                                                        if idx not in tool_bufs:
                                                            tool_bufs[idx] = StreamTagBuffer(_deanonymize_response_text)
                                                        args_chunk = tc["function"].get("arguments")
                                                        if isinstance(args_chunk, str):
                                                            tc["function"]["arguments"] = tool_bufs[idx].feed(args_chunk)
                                        if isinstance(ch, dict) and ch.get("finish_reason"):
                                            rem = content_buf.flush()
                                            if rem and isinstance(delta, dict):
                                                delta["content"] = (delta.get("content") or "") + rem
                                            for idx, tbuf in tool_bufs.items():
                                                trem = tbuf.flush()
                                                if trem and isinstance(delta, dict):
                                                    tcs = delta.setdefault("tool_calls", [{"index": idx, "function": {"arguments": ""}}])
                                                    tcs[0].setdefault("function", {})["arguments"] = (tcs[0]["function"].get("arguments") or "") + trem
                                # 2. OpenAI Codex Responses API SSE delta
                                elif isinstance(evt, dict) and isinstance(evt.get("delta"), str):
                                    evt["delta"] = content_buf.feed(evt["delta"])
                                # 3. Claude Code / Anthropic SSE delta
                                elif isinstance(evt, dict) and isinstance(evt.get("delta"), dict):
                                    d_obj = evt["delta"]
                                    if isinstance(d_obj.get("text"), str):
                                        d_obj["text"] = content_buf.feed(d_obj["text"])
                                    if isinstance(d_obj.get("partial_json"), str):
                                        d_obj["partial_json"] = content_buf.feed(d_obj["partial_json"])
                                else:
                                    evt = _deanonymize_response_obj(evt)
                                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                                continue
                            except Exception:
                                pass

                        yield f"{_deanonymize_response_text(decoded_line)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return Response(stream_with_context(generate()), content_type='text/event-stream')


if __name__ == '__main__':
    print(f"Avvio Germano AI v{APP_VERSION} Server Locale...")
    print("Dashboard disponibile all'indirizzo: http://127.0.0.1:8000")
    if os.environ.get("GERMANO_NO_BROWSER") != "1":
        import webbrowser
        webbrowser.open("http://127.0.0.1:8000")
    app.run(host='127.0.0.1', port=8000, debug=False, threaded=True)
