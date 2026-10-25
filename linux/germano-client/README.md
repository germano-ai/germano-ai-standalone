# 🛡️ Germano AI Client

👉 *Read this in other languages: [English](README.en.md)*

**Germano AI Client** è l'applicazione client ultraleggera (~26 MB) progettata per connettere qualsiasi postazione di lavoro (notebook, PC standard) a un **Germano Server** attivo sulla rete locale (LAN).

Non richiede modelli di intelligenza artificiale pesanti né GPU dedicate in locale: tutto il carico computazionale, l'OCR e l'inferenza IA vengono delegati al Server centrale, mentre i documenti originali e il Vault di de-anonimizzazione rimangono saldamente e sovranamente sulla postazione client locale.

---

## ⚡ Caratteristiche Principali

1. **Rilevamento Automatico del Server (Broadcast UDP 8182)**:
   All'avvio, il Client ricerca automaticamente sulla rete locale i Server Germano attivi, stabilendo una connessione istantanea protetta da Bearer Token di sicurezza.
2. **Esposizione delle AI e dei Modelli del Server**:
   Il Client interroga il Server ed elenca tutte le intelligenze artificiali e gli agenti CLI configurati (es. Claude Code, Google Antigravity, OpenAI Codex, Aider, Qwen, DeepSeek). Permette di interrogarli ed eseguirli direttamente dalla propria postazione, anche se non sono installati localmente.
3. **Instradamento Trasparente per Agenti AI Locali**:
   Per gli agenti installati localmente, configura automaticamente le variabili d'ambiente (`ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`) reindirizzando il traffico verso il Proxy di Privacy del Server con de-anonimizzazione trasparente al ritorno.
4. **Protezione dei Documenti e dei File**:
   Tratta file e testi al volo prima della trasmissione: il server riceve unicamente dati con placeholder anonimizzati (`[PERSONA_1]`, `[COD.FISCALE_1]`, ecc.), garantendo la piena conformità GDPR e CAD.
5. **Nuova Interfaccia Applicativa Dedicata**:
   Disponibile sia in finestra grafica dedicata (senza barre di navigazione generiche né console nera) sia tramite interfaccia a riga di comando (`client.py`) per automazioni e script.

---

## 🏗️ Architettura del Flusso

```
  [ Postazione Client: Notebook / PC Ufficio ]
     │  Interfaccia Grafica o CLI (Claude / Antigravity / Codex / Aider)
     │  Instradamento con Bearer Token protetto
     ▼
  [ GERMANO SERVER sulla LAN :8181 ]  (Workstation con i 6 modelli IA locali)
     1. Riceve le richieste e applica i modelli di privacy locali offline
     2. Anonimizza prompt e documenti (sostituzione PII con token)
     3. Registra i mapping nel Vault locale del client
     4. Inoltra all'LLM di destinazione solo il testo anonimizzato
     5. Ripristina i dati reali nella risposta e la restituisce in chiaro al Client
```

---

## 📦 Installazione Multipiattaforma

Gli installer ufficiali del Client sono singoli file su **[download.germano.ai](https://download.germano.ai/)** e includono il proprio Python con tutte le librerie: l'installazione non scarica nulla da Internet. Il client non crea cartelle di lavoro in Documenti: le sue impostazioni (indirizzo del server, token) restano nella cartella tecnica dell'utente.

### 🪟 Windows (10 / 11 a 64 bit)
1. **Download:** scarica `germano-client-0.60.exe` (circa 22 MB).
2. **Installazione:** doppio clic sull'installer. Si installa per l'utente corrente in `%LOCALAPPDATA%\Programs\Germano AI Client` **senza diritti di amministratore (nessuna richiesta UAC)**, con i collegamenti sul Desktop e nel menu Start e la voce in Impostazioni > App. Le impostazioni del client sono in `%LOCALAPPDATA%\Germano AI Client`.
3. **Avvio:** collegamento **Germano AI** sul Desktop o nel menu Start (finestra dedicata, senza terminale).
4. **Disinstallazione:** Impostazioni > App > App installate > Germano AI Client.

### 🍎 macOS (Apple Silicon e Intel, macOS 11 o successivo)
1. **Download:** scarica `germano-client-0.60.pkg`.
2. **Installazione:** doppio clic sul pacchetto e, alla scelta della destinazione, **Installa solo per me**: l'app va in `~/Applications/Germano AI Client/Germano.app` **senza password di amministratore** (con «Installa per tutti gli utenti» va in `/Applications/Germano AI Client` e macOS chiede la password). Le impostazioni sono in `~/Library/Application Support/Germano AI Client`.
3. **Avvio:** apri **Germano** da Launchpad o dalla cartella Applicazioni > Germano AI Client.
4. **Disinstallazione:** trascina la cartella `Germano AI Client` nel Cestino.

Il pacchetto non è ancora firmato da Apple: se macOS ne blocca l'apertura, vai in **Impostazioni di Sistema > Privacy e sicurezza** e scegli **Apri comunque**.

### 🐧 Linux (Ubuntu / Debian a 64 bit)
1. **Download:** scarica `germano-client-0.60.deb`, pensato per **Ubuntu 26.04 LTS** e adatto alle distribuzioni basate su Debian con glibc 2.34 o successiva.
2. **Installazione:** doppio clic sul file (Centro app) oppure da terminale `sudo apt install ./germano-client-0.60.deb` (password di amministratore, come per ogni pacchetto di sistema). Il programma va in `/opt/germano-client`, con la voce **Germano AI Client** nel menu delle applicazioni e il comando `germano-ai-client`; le impostazioni sono in `~/.local/state/germano-client`.
3. **Avvio:** dal menu delle applicazioni.
4. **Disinstallazione:** `sudo apt remove germano-ai-client`.

---

## 💻 Utilizzo da Riga di Comando (Opzionale)

Per script, pipeline CI/CD o utenti avanzati, il Client offre una completa interfaccia CLI:

```bash
# Mostra la lista dei server attivi sulla LAN
python client.py discover

# Mostra i modelli e le AI esposte dal server
python client.py models

# Chiede direttamente a un'AI del server
python client.py ask "Spiega il principio di privacy by design"

# Avvia un agente locale reindirizzandolo verso il server
python client.py launch claude
python client.py launch antigravity

# Anonimizza un documento locale tramite il server
python client.py send documento.pdf
```

---

## 📖 Documentazione Completa
Per tutti i dettagli tecnici su API, token di sicurezza e configurazione avanzata, consulta il manuale integrato:
- **[GUIDA_OFFLINE.html](GUIDA_OFFLINE.html)** (100% offline, inclusa in ogni pacchetto)
- **[Guida Online Ufficiale](https://germano.ai/guide.html)**

---

<p align="center">
  <b>Germano AI Client</b> — Un progetto Open Source distribuito con licenza <b>GNU GPL v3</b>.<br>
  Sviluppato con orgoglio da <a href="https://www.yesc.it/">Yes Consulting</a>.
</p>


---

## 🛠️ Guida per Sviluppatori: Esecuzione dai Sorgenti GitHub

Questo repository GitHub contiene **esclusivamente il codice sorgente pulito** dell'applicazione e gli asset grafici. Per mantenere il repository leggero (< 30 MB) e veloce da clonare, i modelli neurali e i runtime binari **non sono inclusi nei commit di GitHub**.

### 📦 Cosa scaricare prima di avviare il codice in locale:

1. **Modelli di Intelligenza Artificiale (`models/`):**
   - Germano richiede i 6 modelli IA locali (filtro privacy, NER, EasyOCR, biometria facciale YuNet, rilevamento targhe e firme).
   - 👉 **[Scarica il pacchetto completo dei Modelli](https://download.germano.ai/modelli/)** ed estrailo nella cartella `models/` della piattaforma scelta (es. `windows/germano/models/` o `linux/germano/models/`).
   - *In alternativa:* puoi estrarre la cartella `models/` direttamente da qualsiasi installer ufficiale scaricato da [download.germano.ai](https://download.germano.ai).

2. **Dipendenze e Runtime di Sistema:**
   - **Windows:** Richiede Python 3.11+ a 64 bit e le librerie runtime **[Microsoft Visual C++ Redistributable 64-bit](https://aka.ms/vs/17/release/vc_redist.x64.exe)** (`vc_redist.x64.exe`).
   - **Linux:** Richiede Python 3.11+ (`sudo apt install python3 python3-pip python3-venv`).
   - **macOS:** Richiede Python 3.11+ (Apple Silicon o Intel).

### 🚀 Come avviare l'ambiente di sviluppo in 4 passi:

```bash
# 1. Clona il repository ed entra nella cartella della piattaforma desiderata
git clone https://github.com/germano-ai/germano-ai-standalone.git
cd germano-ai-standalone/windows/germano  # oppure linux/germano o macos/germano

# 2. Crea e attiva un ambiente virtuale (consigliato)
python -m venv venv
# Su Windows:
venv\Scripts\activate
# Su Linux/macOS:
source venv/bin/activate

# 3. Installa le dipendenze Python
pip install -r requirements.txt

# 4. Posiziona la cartella 'models/' scaricata nella directory corrente e avvia:
python server.py
```
Per avviare invece la versione client leggera:
```bash
cd germano-ai-standalone/windows/germano-client
pip install -r requirements.txt
python client.py
```
