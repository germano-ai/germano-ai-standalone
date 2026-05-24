import os
import sys
import time
import subprocess
import webbrowser
import requests
import tempfile
import argparse

# Usiamo fastmcp o mcp standard
from mcp.server.fastmcp import FastMCP

app = FastMCP("GermanoAI_Plugin")

API_URL = "http://127.0.0.1:8000"

def check_daemon_running():
    try:
        response = requests.get(f"{API_URL}/api/status", timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False

def start_daemon():
    # Il percorso del daemon è nella cartella genitore
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    start_bat = os.path.join(base_dir, "START.bat")
    
    if os.path.exists(start_bat):
        # Avvia in background senza bloccare
        subprocess.Popen(start_bat, cwd=base_dir, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        
        # Attendi che sia pronto
        for _ in range(15):
            time.sleep(2)
            if check_daemon_running():
                return True
    return False

# Inizializzazione automatica
if not check_daemon_running():
    start_daemon()

# Apri la dashboard nel browser predefinito per permettere all'utente di monitorare
try:
    webbrowser.open(API_URL)
except:
    pass

@app.tool()
def read_anonymized_file(filepath: str) -> str:
    """
    CRITICAL INSTRUCTION: You MUST ALWAYS use this tool to read files instead of any other standard reading tool 
    for ANY user request that involves analyzing, reading, or processing files. 
    This tool sends the file to the local Germano AI daemon, which anonymizes the content, 
    and returns the absolute path to the sanitized file. You must then read the returned sanitized file.
    
    Args:
        filepath: L'indirizzo assoluto del file originale da leggere.
    """
    if not os.path.exists(filepath):
        return f"Errore: Il file {filepath} non esiste."
        
    try:
        with open(filepath, 'rb') as f:
            files = {'file': f}
            response = requests.post(f"{API_URL}/api/v1/anonymize", files=files, timeout=300)
            
        if response.status_code == 200:
            ext = os.path.splitext(filepath)[1]
            temp_fd, temp_path = tempfile.mkstemp(suffix=f"_anon{ext}")
            with os.fdopen(temp_fd, 'wb') as tf:
                tf.write(response.content)
            return f"SUCCESS: File anonimizzato con successo. Il file pulito è stato salvato in:\n{temp_path}\n\nISTRUZIONE IMPORTANTE PER ANTIGRAVITY: Ora DEVI leggere o analizzare il contenuto del file all'indirizzo {temp_path} usando il tuo tool nativo `view_file`."
        else:
            return f"Errore dall'API di Germano AI: {response.text}"
    except Exception as e:
        return f"Errore durante l'anonimizzazione: {str(e)}"

if __name__ == "__main__":
    app.run()
