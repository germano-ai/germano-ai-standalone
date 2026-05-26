import os
import sys
import subprocess
import shutil

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def remove_claude_code():
    print("\n[Claude Code]")
    cmd = 'claude mcp remove germano-ai'
    print(f"Esecuzione: {cmd}")
    try:
        subprocess.run(cmd, shell=True)
        print("Rimozione da Claude Code completata.")
    except Exception as e:
        print(f"Errore: {e}")

def main():
    clear_screen()
    print("="*50)
    print("   DISINSTALLATORE PLUGIN MULTIPIATTAFORMA GERMANO AI   ")
    print("="*50)
    print("Avvio la ricerca e la rimozione del plugin dai sistemi compatibili...")
    
    found = False
    # Rimuovi da Claude Code se installato
    if shutil.which('claude'):
        remove_claude_code()
        found = True
        
    print("\n[Altri Editor: Cursor, Windsurf, VS Code, Lovable, Cline, Roo Code...]")
    print("Poiché il plugin GermanoAI non ha installato file eseguibili ma si è semplicemente registrato")
    print("tramite i file di configurazione JSON dei rispettivi editor, è necessario eliminare")
    print("manualmente la voce 'GermanoAI' dai loro file settings.json o mcp_settings.json.")
    print("\nNon c'è nulla da disinstallare a livello di sistema operativo.")
    print("La disinstallazione del motore IA locale avverrà eliminando questa intera cartella STANDALONE.")
    
    print("\nOperazione conclusa con successo!")

if __name__ == "__main__":
    main()
