import os
import sys
import json
import subprocess
import time
import shutil

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_server_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), 'mcp_server.py'))

def generate_cursor_config():
    server_path = get_server_path()
    python_exe = sys.executable
    print("\n[Cursor IDE]")
    print("Cursor supporta l'MCP nativamente. Segui questi passi:")
    print("1. Apri Cursor e vai su Settings (Impostazioni)")
    print("2. Cerca 'MCP' o vai nella sezione Features -> MCP")
    print("3. Clicca su '+ Add New MCP Server'")
    print("4. Inserisci i seguenti dati:")
    print("   - Type: command")
    print("   - Name: GermanoAI")
    print(f"   - Command: {python_exe} {server_path}")
    print("\nEcco fatto! Cursor invierà tutti i file al demone Germano AI per l'anonimizzazione.")
    input("\nPremi Invio per continuare...")

def generate_windsurf_config():
    server_path = get_server_path()
    python_exe = sys.executable
    config = {
        "mcpServers": {
            "GermanoAI": {
                "command": python_exe,
                "args": [server_path]
            }
        }
    }
    config_str = json.dumps(config, indent=4)
    print("\n[Windsurf (Cascade)]")
    print("Windsurf utilizza un file di configurazione per i server MCP.")
    print("Copia il seguente JSON e incollalo nel tuo file `mcp_config.json` (solitamente in `~/.codeium/windsurf/mcp_config.json`):")
    print("\n" + config_str)
    input("\nPremi Invio per continuare...")

def generate_claude_code_config():
    server_path = get_server_path()
    python_exe = sys.executable
    print("\n[Claude Code]")
    print("Sto tentando di registrare il plugin nativamente in Claude Code...")
    cmd = f'claude mcp add germano-ai "{python_exe}" "{server_path}"'
    print(f"Esecuzione: {cmd}")
    try:
        subprocess.run(cmd, shell=True)
        print("Registrazione completata (se claude-code è installato nel PATH).")
    except Exception as e:
        print(f"Errore: {e}")
        print("Assicurati di avere `claude` installato globalmente via npm.")
    input("\nPremi Invio per continuare...")

def generate_copilot_config():
    server_path = get_server_path()
    python_exe = sys.executable
    config = {
        "github.copilot.chat.mcp.server": {
            "GermanoAI": {
                "command": python_exe,
                "args": [server_path]
            }
        }
    }
    config_str = json.dumps(config, indent=4)
    print("\n[GitHub Copilot Extensions (VS Code)]")
    print("Copilot in VS Code supporta i server MCP locali.")
    print("1. Apri VS Code")
    print("2. Apri il file `settings.json` (Preferenze: Apri Impostazioni Utente JSON)")
    print("3. Aggiungi o unisci questa configurazione:")
    print("\n" + config_str)
    input("\nPremi Invio per continuare...")

def generate_opencode_config():
    server_path = get_server_path()
    python_exe = sys.executable
    print("\n[OpenCode]")
    print("Se OpenCode supporta il protocollo standard MCP via STDIO, usa i seguenti parametri per la connessione:")
    print(f"- Tipo connessione: STDIO")
    print(f"- Comando di avvio: {python_exe}")
    print(f"- Argomenti: {server_path}")
    print("\nIn alternativa, se usa una configurazione JSON stile VS Code:")
    config = {
        "mcpServers": {
            "GermanoAI": {
                "command": python_exe,
                "args": [server_path]
            }
        }
    }
    print(json.dumps(config, indent=4))
    input("\nPremi Invio per continuare...")

def scan_editors():
    print("\n[Scansione Automatica Editor Supportati]")
    found_any = False
    
    appdata = os.environ.get('APPDATA', '')
    localappdata = os.environ.get('LOCALAPPDATA', '')
    userprofile = os.environ.get('USERPROFILE', os.path.expanduser('~'))
    
    # Check Cursor
    cursor_path = os.path.join(localappdata, 'Programs', 'cursor')
    if os.path.exists(cursor_path) or os.path.exists(os.path.join(appdata, 'Cursor')):
        print("- Trovato: Cursor IDE")
        found_any = True
        
    # Check VS Code
    vscode_path = os.path.join(localappdata, 'Programs', 'Microsoft VS Code')
    if os.path.exists(vscode_path) or os.path.exists(os.path.join(appdata, 'Code')):
        print("- Trovato: VS Code (Copilot)")
        found_any = True
        
    # Check Windsurf
    windsurf_path = os.path.join(userprofile, '.codeium', 'windsurf')
    if os.path.exists(windsurf_path) or os.path.exists(os.path.join(localappdata, 'Programs', 'windsurf')):
        print("- Trovato: Windsurf")
        found_any = True
        
    # Check Claude Code
    if shutil.which('claude'):
        print("- Trovato: Claude Code")
        found_any = True
        
    if not found_any:
        print("\n=== Code editor non trovato ===")
        print("Il sistema non ha rilevato alcun editor compatibile installato nelle posizioni standard.")
        print("Puoi comunque configurarlo manualmente dal menu principale se il tuo editor è portable o installato altrove.")
    else:
        print("\nEditor trovati! Usa il menu principale per generare la configurazione per il tuo editor.")
        
    input("\nPremi Invio per tornare al menu...")

def main():
    while True:
        clear_screen()
        print("="*50)
        print("   INSTALLATORE PLUGIN MULTIPIATTAFORMA GERMANO AI   ")
        print("="*50)
        print("Seleziona la tua IA / Editor per vedere come attivare il plugin:")
        print("1. Cursor IDE")
        print("2. Windsurf")
        print("3. Claude Code")
        print("4. GitHub Copilot (VS Code)")
        print("5. OpenCode")
        print("6. Google Antigravity")
        print("7. Esegui Scansione Automatica Editor")
        print("0. Esci")
        print("="*50)
        
        choice = input("Scelta: ")
        
        if choice == '1':
            generate_cursor_config()
        elif choice == '2':
            generate_windsurf_config()
        elif choice == '3':
            generate_claude_code_config()
        elif choice == '4':
            generate_copilot_config()
        elif choice == '5':
            generate_opencode_config()
        elif choice == '6':
            print("\n[Google Antigravity]")
            print("Per Antigravity, usa il comando nativo di importazione o incolla i dati del server STDIO:")
            print(f"- Comando: {sys.executable}")
            print(f"- Argomenti: {get_server_path()}")
            input("\nPremi Invio per continuare...")
        elif choice == '7':
            scan_editors()
        elif choice == '0':
            break
        else:
            print("\nScelta non valida.")
            time.sleep(1)

if __name__ == "__main__":
    scan_editors() # Esegui una scansione automatica all'avvio
    main()
