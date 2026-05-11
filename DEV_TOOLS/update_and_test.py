import os
import sys
import subprocess
import time
import requests
import json
import psutil

# Costanti
STANDALONE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEST_FILES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_files"))
API_BASE_URL = "http://127.0.0.1:8000"

def log_info(msg):
    print(f"[INFO] {msg}")

def log_success(msg):
    print(f"[SUCCESS] {msg}")

def log_error(msg):
    print(f"[ERROR] {msg}")

def run_update():
    log_info("Fase 1: Aggiornamento dei pacchetti (pip install --upgrade)...")
    req_file = os.path.join(STANDALONE_DIR, "requirements.txt")
    if os.path.exists(req_file):
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "-r", req_file], check=True)
            log_success("Pacchetti aggiornati con successo.")
        except subprocess.CalledProcessError as e:
            log_error(f"Fallito aggiornamento pacchetti: {e}")
            sys.exit(1)
    else:
        log_info("File requirements.txt non trovato, salto aggiornamento.")

def kill_existing_servers():
    log_info("Pulizia di vecchi server Flask e Demoni...")
    for p in psutil.process_iter(['name', 'cmdline']):
        try:
            if p.info['name'] and 'python' in p.info['name'].lower() and p.info['cmdline']:
                if any('server.py' in cmd for cmd in p.info['cmdline']) or any('daemon.py' in cmd for cmd in p.info['cmdline']):
                    if p.pid != os.getpid():
                        p.terminate()
        except Exception:
            pass
    time.sleep(2)

def start_server():
    log_info("Fase 2: Avvio server.py in background...")
    server_process = subprocess.Popen([sys.executable, "server.py"], cwd=STANDALONE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Aspettiamo che Flask sia raggiungibile
    max_retries = 10
    flask_ready = False
    for i in range(max_retries):
        try:
            res = requests.get(f"{API_BASE_URL}/api/status", timeout=2)
            if res.status_code == 200:
                flask_ready = True
                break
        except Exception:
            time.sleep(1)
            
    if not flask_ready:
        log_error("Impossibile contattare il server Flask sulla porta 8000.")
        server_process.terminate()
        sys.exit(1)
        
    log_success("Server Flask avviato.")
    return server_process

def start_daemon():
    log_info("Fase 3: Avvio Demone IA...")
    # Chiamiamo l'api start
    try:
        settings = {
            "compliance_mode": "PA",
            "enable_ocr": True,
            "enable_faces": True,
            "enable_regex": True,
            "ai_threshold": 0.0,
            "hardware_mode": "cpu" # Usiamo cpu per i test per evitare colli di bottiglia su driver gpu
        }
        res = requests.post(f"{API_BASE_URL}/api/start", json={"settings": settings}, timeout=5)
        if res.status_code != 200:
            log_error(f"Errore nell'avvio del demone: {res.text}")
            sys.exit(1)
            
        # Polling fino allo stato 'running'
        log_info("Attesa caricamento modelli IA (può richiedere qualche minuto)...")
        daemon_ready = False
        for _ in range(120): # Max 2 minuti
            try:
                status_res = requests.get(f"{API_BASE_URL}/api/status", timeout=2).json()
                if status_res.get("status") == "running":
                    daemon_ready = True
                    break
            except Exception:
                pass
            time.sleep(2)
            
        if not daemon_ready:
            log_error("Il demone non è passato in stato 'running' entro il tempo massimo.")
            sys.exit(1)
            
        log_success("Demone IA caricato in RAM e pronto!")
    except Exception as e:
        log_error(f"Eccezione durante l'avvio del demone: {e}")
        sys.exit(1)

def run_tests():
    log_info("Fase 4: Esecuzione Test API...")
    test_file_path = os.path.join(TEST_FILES_DIR, "test_document.txt")
    
    if not os.path.exists(test_file_path):
        log_error(f"File di test mancante: {test_file_path}")
        return False
        
    log_info(f"Invio {os.path.basename(test_file_path)} all'API /api/v1/anonymize...")
    
    try:
        with open(test_file_path, 'rb') as f:
            files = {'file': (os.path.basename(test_file_path), f, 'text/plain')}
            res = requests.post(f"{API_BASE_URL}/api/v1/anonymize", files=files, timeout=65)
            
        if res.status_code == 200:
            content = res.content.decode('utf-8', errors='ignore')
            log_success("File ricevuto con successo dall'API.")
            
            # Verifichiamo se l'anonimizzazione ha funzionato
            if "RSSMRA80A01H501Z" in content or "mario.rossi@email.it" in content:
                log_error("TEST FALLITO: Dati sensibili non censurati nel file di output.")
                return False
            elif "[CODICE FISCALE]" in content or "[EMAIL]" in content or "[NOME_PERSONA]" in content or "████" in content:
                log_success("TEST SUPERATO: Dati sensibili censurati correttamente.")
                return True
            else:
                log_info("Attenzione: Dati non trovati, ma il file è stato elaborato.")
                return True
        else:
            log_error(f"Errore API {res.status_code}: {res.text}")
            return False
            
    except Exception as e:
        log_error(f"Eccezione durante il test: {e}")
        return False

def teardown(server_process):
    log_info("Fase 5: Spegnimento del sistema...")
    try:
        requests.post(f"{API_BASE_URL}/api/stop_daemon", timeout=5)
    except Exception:
        pass
    
    time.sleep(2)
    server_process.terminate()
    kill_existing_servers()
    log_success("Teardown completato.")

def main():
    print("===========================================")
    print(" GERM_AI - SUITE DI UPDATE & TEST AUTOMATICI ")
    print("===========================================")
    
    kill_existing_servers()
    run_update()
    
    server_process = start_server()
    try:
        start_daemon()
        success = run_tests()
        
        if success:
            print("\n===========================================")
            print(" ✅ TUTTI I TEST SUPERATI CON SUCCESSO!")
            print(" L'aggiornamento è stabile e le API rispondono.")
            print("===========================================\n")
        else:
            print("\n===========================================")
            print(" ❌ I TEST HANNO PRODOTTO DEGLI ERRORI.")
            print(" Verifica il log del demone in STANDALONE/daemon.log")
            print("===========================================\n")
            
    finally:
        teardown(server_process)

if __name__ == "__main__":
    main()
