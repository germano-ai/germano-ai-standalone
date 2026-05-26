from flask import Flask, render_template, jsonify
import subprocess
import os
import requests
import uuid
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
APP_VERSION = "0.18-alpha"

DAEMON_PID_FILE = "daemon.pid"
STOP_FLAG = "stop.flag"
READY_FLAG = "ready.flag"
LOG_FILE = "daemon.log"

def is_daemon_running():
    if os.path.exists(DAEMON_PID_FILE):
        try:
            with open(DAEMON_PID_FILE, "r") as f:
                pid = int(f.read().strip())
            
            # Use tasklist natively on Windows without needing psutil
            output = subprocess.check_output(f'tasklist /FI "PID eq {pid}"', shell=True).decode()
            if str(pid) in output:
                return True
        except:
            return False
    return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    # If stop flag is present, we are shutting down
    if os.path.exists(STOP_FLAG):
        return jsonify({'running': False, 'status': 'shutting_down'})
    
    running = is_daemon_running()
    
    current_status = 'stopped'
    if running:
        if os.path.exists(READY_FLAG):
            current_status = 'running'
        else:
            current_status = 'loading_models'
    
    # Get stats
    pending = 0
    pending_folders = 0
    pending_bytes = 0
    if os.path.exists("input"):
        for root, dirs, files in os.walk("input"):
            pending += len(files)
            pending_folders += len(dirs)
            for f in files:
                try:
                    pending_bytes += os.path.getsize(os.path.join(root, f))
                except:
                    pass
            
    processed = 0
    if os.path.exists("processed"):
        for root, dirs, files in os.walk("processed"):
            processed += len(files)
            
    outputs = 0
    if os.path.exists("output"):
        for root, dirs, files in os.walk("output"):
            outputs += len(files)
            
    return jsonify({
        'running': running,
        'status': current_status,
        'stats': {
            'pending': pending,
            'pending_folders': pending_folders,
            'pending_bytes': pending_bytes,
            'processed': processed,
            'outputs': outputs
        }
    })

from flask import request
import json

@app.route('/api/start', methods=['GET', 'POST'])
def start_daemon():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        settings = data.get('settings', {})
        if settings:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(settings, f)

    if os.path.exists(STOP_FLAG):
        os.remove(STOP_FLAG)
    
    if not is_daemon_running():
        # Start the background process
        import sys
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            subprocess.Popen([sys.executable, "daemon.py"], stdout=log, stderr=log, stdin=subprocess.DEVNULL, env=env)
            
    return jsonify({'status': 'success', 'message': 'Daemon started'})

@app.route('/api/stop')
def stop():
    with open(STOP_FLAG, "w") as f:
        f.write("1")
    if os.path.exists(READY_FLAG):
        try: os.remove(READY_FLAG)
        except: pass
    return jsonify({'status': 'success', 'message': 'Stop flag set'})

@app.route('/api/stop_daemon', methods=['POST'])
def stop_daemon():
    # Cerca il demone tramite pid o nome
    try:
        import subprocess
        subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/FI", f"WINDOWTITLE eq germano_daemon*"], shell=True)
        return jsonify({"status": "success", "message": "Demone fermato (se era in esecuzione)."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/check_update', methods=['GET'])
def check_update():
    try:
        response = requests.get("https://raw.githubusercontent.com/germano-ai/germano-ai-standalone/master/VERSION", timeout=5)
        if response.status_code == 200:
            latest_version = response.text.strip()
            return jsonify({
                "current_version": APP_VERSION,
                "latest_version": latest_version,
                "update_available": latest_version != APP_VERSION
            })
    except Exception as e:
        app.logger.error(f"Errore controllo aggiornamenti: {e}")
    
    return jsonify({
        "current_version": APP_VERSION,
        "latest_version": "unknown",
        "update_available": False
    })

@app.route('/api/v1/anonymize_text', methods=['POST'])
def api_anonymize_text():
    if not is_daemon_running():
        return jsonify({"error": "Il demone IA non è in esecuzione."}), 503
    
    data = request.get_json(force=True, silent=True)
    if not data or 'text' not in data:
        return jsonify({"error": "Fornire un JSON con il campo 'text'."}), 400
        
    try:
        resp = requests.post("http://127.0.0.1:8001/internal/anonymize_text", json={"text": data["text"]}, timeout=30)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"error": "Errore interno del demone."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/anonymize', methods=['POST'])
def api_anonymize():
    if not is_daemon_running():
        return jsonify({"error": "Il demone IA non è in esecuzione."}), 503
        
    if 'file' not in request.files:
        return jsonify({"error": "Nessun file fornito. Usa multipart/form-data con la chiave 'file'."}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nessun file selezionato."}), 400
        
    # Crea un identificatore unico
    uid = str(uuid.uuid4())[:8]
    original_name = secure_filename(file.filename)
    base_name, ext = os.path.splitext(original_name)
    safe_name = f"{base_name}_{uid}{ext}"
    
    input_path = os.path.join("input", safe_name)
    output_path = os.path.join("output", safe_name)
    failed_path = os.path.join("failed", safe_name)
    
    os.makedirs("input", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    
    # Salva il file nella cartella input
    file.save(input_path)
    
    # Attendi fino a 60 secondi
    timeout = 60
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if os.path.exists(output_path):
            from flask import send_file
            # Aspetta un secondo in più per sicurezza (per evitare file lock)
            time.sleep(1)
            return send_file(output_path, as_attachment=True, download_name=original_name)
            
        if os.path.exists(failed_path):
            return jsonify({"error": "Errore durante l'elaborazione del file."}), 500
            
        time.sleep(1)
        
    return jsonify({"error": "Timeout: l'elaborazione ha impiegato troppo tempo."}), 504

@app.route('/api/logs')
def get_logs():
    if not os.path.exists(LOG_FILE):
        return jsonify({'logs': []})
        
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return jsonify({'logs': lines[-50:]}) # return last 50 lines
    except Exception as e:
        return jsonify({'logs': [f"Error reading logs: {str(e)}"]})

@app.route('/api/settings')
def get_settings():
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        except:
            pass
    return jsonify({})

@app.route('/api/check_orphans')
def check_orphans():
    import psutil
    count = 0
    try:
        current_pid = -1
        if os.path.exists(PID_FILE):
            with open(PID_FILE, "r") as f:
                try: current_pid = int(f.read().strip())
                except: pass
                
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = p.info['cmdline']
                if cmdline and p.info['name']:
                    if "python" in p.info['name'].lower() and any("daemon.py" in cmd for cmd in cmdline):
                        if p.info['pid'] != current_pid:
                            count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        print(f"Error checking orphans: {e}")
    
    return jsonify({'orphans': count})

@app.route('/api/kill_orphans', methods=['POST'])
def kill_orphans():
    import psutil
    killed = 0
    try:
        current_pid = -1
        if os.path.exists(PID_FILE):
            with open(PID_FILE, "r") as f:
                try: current_pid = int(f.read().strip())
                except: pass
                
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = p.info['cmdline']
                if cmdline and p.info['name']:
                    if "python" in p.info['name'].lower() and any("daemon.py" in cmd for cmd in cmdline):
                        if p.info['pid'] != current_pid:
                            p.terminate()
                            killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
        
    return jsonify({'status': 'success', 'killed': killed})

from flask import Response, stream_with_context

@app.route('/v1/models', methods=['GET'])
def proxy_models():
    return jsonify({
        "object": "list",
        "data": [
            {"id": "germano-proxy", "object": "model", "created": 1686935002, "owned_by": "germano"}
        ]
    })

@app.route('/v1/chat/completions', methods=['POST'])
def proxy_chat_completions():
    payload = request.get_json(force=True, silent=True) or {}
    auth_header = request.headers.get("Authorization")
    
    target_api_url = "https://api.openai.com/v1/chat/completions"
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if "target_api_url" in cfg and cfg["target_api_url"]:
                    base_url = cfg["target_api_url"]
                    if base_url.endswith("/"): base_url = base_url[:-1]
                    if not base_url.endswith("/chat/completions"):
                        target_api_url = base_url + "/chat/completions"
                    else:
                        target_api_url = base_url
        except: pass

    session_map = {} 
    
    def anonymize_text_via_daemon(text):
        if not is_daemon_running():
            return text
        try:
            resp = requests.post("http://127.0.0.1:8001/internal/anonymize_text", json={"text": text}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("extracted_data", []):
                    session_map[item["label"]] = item["word"]
                return data.get("anonymized", text)
        except Exception as e:
            app.logger.error(f"Daemon proxy error: {e}")
        return text

    if "messages" in payload:
        for msg in payload.get("messages", []):
            content = msg.get("content")
            if isinstance(content, str):
                msg["content"] = anonymize_text_via_daemon(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        part["text"] = anonymize_text_via_daemon(part.get("text", ""))

    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
        
    is_stream = payload.get("stream", False)
    
    def replace_all(text):
        if not text: return text
        for label, real_word in session_map.items():
            text = text.replace(label, real_word)
        return text

    if not is_stream:
        try:
            r = requests.post(target_api_url, json=payload, headers=headers, timeout=120)
            if r.status_code != 200:
                return Response(r.content, status=r.status_code, content_type=r.headers.get('Content-Type'))
                
            resp_json = r.json()
            if "choices" in resp_json:
                for choice in resp_json["choices"]:
                    if "message" in choice and "content" in choice["message"]:
                        content = choice["message"]["content"]
                        if isinstance(content, str):
                            choice["message"]["content"] = replace_all(content)
            return jsonify(resp_json)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        def generate():
            buffer = ""
            try:
                with requests.post(target_api_url, json=payload, headers=headers, stream=True, timeout=120) as r:
                    for line in r.iter_lines():
                        if line:
                            line_str = line.decode('utf-8')
                            if line_str.startswith("data: ") and line_str != "data: [DONE]":
                                try:
                                    chunk_json = json.loads(line_str[6:])
                                    if "choices" in chunk_json:
                                        for choice in chunk_json["choices"]:
                                            if "delta" in choice and "content" in choice["delta"]:
                                                content = choice["delta"]["content"]
                                                if content:
                                                    buffer += content
                                                    last_open = buffer.rfind('[')
                                                    last_close = buffer.rfind(']')
                                                    if last_open != -1 and (last_close == -1 or last_open > last_close) and (len(buffer) - last_open < 35):
                                                        choice["delta"]["content"] = ""
                                                    else:
                                                        out_text = replace_all(buffer)
                                                        choice["delta"]["content"] = out_text
                                                        buffer = ""
                                    yield f"data: {json.dumps(chunk_json)}\n\n"
                                except:
                                    yield f"{line_str}\n\n"
                            elif line_str == "data: [DONE]":
                                if buffer:
                                    flush_json = {"choices": [{"delta": {"content": replace_all(buffer)}}]}
                                    yield f"data: {json.dumps(flush_json)}\n\n"
                                yield f"{line_str}\n\n"
                            else:
                                yield f"{line_str}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                
        return Response(stream_with_context(generate()), content_type='text/event-stream')

if __name__ == '__main__':
    print("Avvio Privacy Filter AI Server locale...")
    print("Apri il tuo browser all'indirizzo: http://127.0.0.1:8000")
    import webbrowser
    webbrowser.open("http://127.0.0.1:8000")
    app.run(host='127.0.0.1', port=8000, debug=False)
