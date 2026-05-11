from flask import Flask, render_template, jsonify
import subprocess
import os

app = Flask(__name__)

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
def stop_daemon():
    with open(STOP_FLAG, "w") as f:
        f.write("1")
    if os.path.exists(READY_FLAG):
        try: os.remove(READY_FLAG)
        except: pass
    return jsonify({'status': 'success', 'message': 'Stop flag set'})

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

if __name__ == '__main__':
    print("Avvio Privacy Filter AI Server locale...")
    print("Apri il tuo browser all'indirizzo: http://127.0.0.1:8000")
    import webbrowser
    webbrowser.open("http://127.0.0.1:8000")
    app.run(host='127.0.0.1', port=8000, debug=False)
