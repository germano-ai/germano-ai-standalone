# Changelog

🌍 *Read this in other languages: [English](CHANGELOG.en.md)*

Tutte le modifiche a questo progetto saranno documentate in questo file.
Il formato è basato su [Keep a Changelog](https://keepachangelog.com/it-IT/1.0.0/).

## [0.60] - 2026-10-25
Germano diventa una **vera applicazione desktop**, distribuita con **installer in un solo file** per Windows, macOS e
Linux che contengono tutto il necessario e **non scaricano nulla da Internet**. Un solo programma, **`Germano`**
(`Germano.exe` su Windows, `Germano.app` su macOS, voce di menu «Germano AI» su Linux): niente finestra nera del
terminale, niente browser con barra degli indirizzi o schede, e la **X rossa chiude tutto**. L'architettura interna non
cambia (stesso motore Python + Flask, demone locale, modelli IA offline, OCR, Proxy API).

### Aggiunto - Installer in un solo file
- **Windows**: `germano-0.60.exe` (suite, ~2,8 GB) e `germano-client-0.60.exe` (~22 MB). L'installer della suite
  **chiede subito i permessi di amministratore** (richiesta UAC appena si apre, con nome e icona di Germano) e consente
  **sempre** l'accesso dalla rete locale: nessuna casella da spuntare, una sola regola del firewall di Windows per il
  Python di Germano, solo reti private e di dominio (le regole aperte delle versioni 0.51/0.52 vengono tolte). Il
  programma si installa comunque per l'utente corrente in `%LOCALAPPDATA%\Programs\…` (gli aggiornamenti automatici non
  chiedono permessi), con collegamenti sul Desktop e nel menu Start, voce in Impostazioni › App e cartelle di lavoro in
  `Documenti\Germano AI`; alla fine la finestra si chiude e **Germano si apre da solo**, con i permessi normali
  dell'utente, senza pagine di istruzioni. Il **disinstallatore** (Impostazioni › App) chiede i permessi all'avvio per
  togliere la regola del firewall e rimuove programma, collegamenti, voce in Impostazioni › App e file tecnici (a scelta
  anche cartelle di lavoro e Vault). Il client non chiede permessi e ha collegamenti propri («Germano AI Client»), così
  le due edizioni possono stare sullo stesso computer. Il runtime include le DLL di Microsoft Visual C++: nessun
  ridistribuibile da installare.
- **macOS**: `germano-0.60.pkg` (Apple Silicon, macOS 14 o successivo) e `germano-client-0.60.pkg` (Apple Silicon e
  Intel, macOS 11 o successivo): pacchetti dell'Installer di macOS con `Germano.app` autosufficiente; con «Installa
  solo per me» nessuna password di amministratore; alla fine Germano si apre da solo (non nelle installazioni da riga di
  comando).
- **Linux**: `germano-0.60.deb` e `germano-client-0.60.deb` per Ubuntu 26.04 LTS e le distribuzioni Debian/Ubuntu a 64
  bit: programma in `/opt`, voce di menu e comando `germano-ai` / `germano-ai-client`, nessuna dipendenza da altri
  pacchetti.
- I pacchetti per macOS e Linux contengono Python 3.11 con le stesse versioni delle librerie collaudate su Windows.

### Aggiunto - Applicazione desktop
- **`Germano.exe`**, unico eseguibile su Windows: lanciatore grafico (nessuna console) che avvia il runtime incluso
  (`runtime\pythonw.exe`) sul gestore della finestra `germano_desktop.py`.
- Un solo nome per entrambe le edizioni: nella **suite completa** apre la **Dashboard unificata** (Standalone offline,
  Server LAN, modalità Client); nel **client leggero** apre il pannello del client (`client_ui.py`: cerca server,
  stato, AI del server, «chiedi a un'AI del server», «proteggi testo/file»).
- **Finestra applicativa dedicata**: Microsoft Edge in modalità app su Windows, WebKit di sistema su macOS, Qt WebEngine
  (incluso nel pacchetto) su Linux; profilo isolato, senza schede né barra degli indirizzi.
- **Chiusura totale con la X rossa**: il gestore ferma in modo pulito **solo** i processi di Germano (server Flask +
  demone IA), senza processi orfani e senza toccare altri processi del sistema.

### Aggiunto - Remote Control: Germano da qualsiasi browser della rete, senza installare nulla
- Con la modalità Server attiva, qualsiasi PC, tablet o smartphone della rete locale apre
  `http://<IP-del-server>:8181/` (pagina `/remote`, mobile e bilingue) e trova: le **AI del server** rilevate
  automaticamente, la **chat protetta** (prompt e fino a 12 allegati anonimizzati dal server prima di uscire, risposta
  con i dati ripristinati e il testo esatto ricevuto dall'AI), **Proteggi e ripristina** per qualsiasi AI (ripristino
  sul dispositivo), le **opzioni di elaborazione** e gli indirizzi del Proxy per gli strumenti del dispositivo.
- **Servizi di AI via API** attraverso Germano: Meta Muse (Muse Wonder, Muse Spark), Kimi (Moonshot AI), DeepSeek, Qwen,
  Mistral, Grok (xAI), Perplexity (Sonar), Google Gemini, OpenAI, Anthropic, OpenRouter, Groq e i modelli locali del
  server (Ollama, LM Studio). Chiave API dell'utente (usata solo per quella richiesta, mai salvata dal server) oppure
  quella del server, se l'amministratore condivide le AI di questo computer. Le CLI del server si eseguono per i client solo se verificate e
  senza strumenti (Claude Code): gli agenti che eseguirebbero comandi o modificherebbero file sul server non vengono mai
  eseguiti, e il Remote Control indica l'alternativa protetta.
- Il **Proxy** inoltra anche ai servizi indicati nel percorso: `http://<server>:8181/p/<servizio>/v1` (es. `/p/deepseek/v1`,
  `/p/moonshot/v1`, `/p/meta/v1`), cosi' Kimi Code, Mistral Vibe, Qwen Code, OpenCode e gli SDK passano da Germano.
- **Germano Client** usa la stessa interfaccia (servita dal client, che inoltra al server): stesse capacità del browser,
  piu' la ricerca del server in rete e l'avvio protetto delle CLI del PC. Nuovi comandi: `client login`, `client logout`,
  `client options`; `client ask` anche con i servizi (`--model`, `--key`).

### Aggiunto - Gestione utenti per l'accesso dalla rete
- Di base dalla rete si accede **senza credenziali**. Nella Dashboard del server (Impostazioni › Accesso dalla rete ›
  Gestione utenti) l'amministratore crea gli utenti e attiva l'accesso con **utente e password**, per il browser
  (schermata di accesso, cookie di sessione `HttpOnly` e `SameSite=Strict`) e per Germano Client (`client login`).
- Password salvate solo come impronta **PBKDF2-SHA256** (600.000 iterazioni, sale casuale) in `config.json`; sessioni
  casuali a 256 bit conservate sul server solo come impronta SHA-256, valide 30 giorni dall'ultimo uso, chiuse cambiando
  la password o eliminando l'utente; 5 tentativi sbagliati in 10 minuti bloccano l'indirizzo per 10 minuti; tempi di risposta uguali
  per utenti esistenti e inesistenti. Senza credenziali le richieste dalla rete ricevono `401`. Dal computer del server
  (127.0.0.1) si amministra sempre senza credenziali.
- La modalità Client della Dashboard accede a un server con la gestione utenti attiva con utente e password (si conserva
  solo la sessione). Se il server rifiuta l'accesso (sessione assente o scaduta) il motore si ferma subito con il
  motivo, senza tentativi ripetuti, e nessun dato viene elaborato; con il ripiego locale attivo si usano i modelli di
  questo computer.

### Aggiunto - Opzioni di elaborazione dei client e blocco del profilo PA
- Dal Remote Control e da Germano Client si scelgono soglia di confidenza, modelli attivi, le 18 categorie di dati
  personali e il mascheramento (etichette numerate ripristinabili, etichette generiche o il nuovo oscuramento `████`):
  valgono solo per le richieste di quel client, la configurazione del server non cambia.
- **Profilo PA o `lock_settings`**: le opzioni sono disabilitate e in grigio nei client, con l'avviso «Bloccato dal
  profilo di conformità PA del Server» (o del blocco dell'amministratore); il server respinge ogni modifica con
  `403 Forbidden` (Compliance Lock) e anche il motore ignora le opzioni dei client.
- Il motore rilegge le impostazioni a ogni richiesta: un cambio di profilo (PA/PD) vale subito, anche per le opzioni
  dei client.

### Aggiunto - Rilevamento delle AI esteso
- Riconosciute anche: Meta Muse Code (Muse Wonder, Muse Spark), Kimi Code CLI, Qwen Code, DeepSeek (Deep Code, Reasonix),
  Mistral Vibe, Grok Build (xAI), Perplexity (pplx), GitHub Copilot CLI, ChatGPT, Jules, Cursor CLI, Kiro e Kiro CLI,
  Trae, Zed, OpenCode, Goose, Cline, Kilo Code, Amp, Droid, Crush, llama.cpp e Jan, oltre a quelle gia' note.
- Il rilevamento legge anche il PATH salvato nel registro (CLI installate dopo l'avvio di Germano) e funziona anche su
  macOS e Linux (eseguibili senza estensione, app in `/Applications`).

### Sicurezza
- Dalla rete (Proxy, Remote Control, AI condivise) il ripristino usa **solo le etichette della richiesta stessa**: un
  dispositivo non può più farsi restituire i dati di altri documenti del Vault (es. chiedendo a un'AI di «ripetere
  [PERSONA_1]»). Le richieste fatte dal computer del server continuano a usare l'intero Vault.
- Rimosso il **token condiviso** per i client della rete (`lan_token`, «Nuovo token»): sostituito dall'accesso libero o
  dalla gestione utenti. Il prefisso `/g/<token>/` del Base URL resta, con il token personale della sessione.

### Modificato - Dashboard: anteprima delle cartelle di lavoro
- Al posto della sezione «Elaborazione dei documenti» (area di trascinamento e contatori In attesa / Pronti / Non
  riusciti) c'è un'**anteprima in stile file manager**: quattro riquadri `input`, `output`, `processed` e `failed` con
  il **percorso completo** della cartella sopra ognuno e i file che contengono, aggiornati in tempo reale (i file appena
  arrivati evidenziati, quello in elaborazione in cima a `input`, il motivo dei non riusciti con «Rimetti in coda»).
- I documenti si trascinano direttamente sul riquadro **input** («Trascina i file qui nella cartella di input»); un clic
  su un riquadro o sul suo percorso apre la cartella in Esplora file (Finder su macOS, il file manager su Linux). Testi
  in italiano e in inglese.

### Modificato - Aggiornamenti
- Unica fonte: **https://download.germano.ai/** (`version.json`, in mancanza l'elenco dei file). Niente più Google Drive
  e nessuna impronta SHA-256: i file del server ufficiale sono considerati attendibili, si controlla solo che il
  download sia completo.
- Windows: l'installer della nuova versione si scarica nella cartella tecnica dell'utente e, con «Installa ora» o al
  successivo avvio, aggiorna Germano mantenendo cartelle di lavoro, Vault e impostazioni, poi lo riapre; un
  aggiornamento non riuscito non viene ripetuto a ogni avvio.
- macOS e Linux: la Dashboard indica il nuovo `.pkg` / `.deb` da scaricare e aprire con un doppio clic.

### Modificato
- `VERSION` → `0.60`; `config.json` ai valori predefiniti puliti; testi della Dashboard, della Guida e dei README
  aggiornati (installazione, cartelle di lavoro, Vault in `extracted/deanonymize_vault.json`).
- Struttura della release: `sorgenti/` (solo il codice pubblicabile su GitHub, per Windows, macOS e Linux),
  `dipendenze/` (runtime e librerie per l'uso offline, per sistema operativo), `modelli/` (i 6 modelli IA) e
  `releases/` (i soli installer).

### Rimosso
- Gli eseguibili con nomi diversi (`GermanoServer.exe`, `GermanoClient.exe`, `GermanoClient.app`, `GermanoClient.desktop`):
  esiste solo `Germano`.
- `START.bat` e `START_SERVER.bat`: Germano si installa con l'installer e si avvia dal collegamento; la modalità Server
  si sceglie nelle Impostazioni dell'app.
- I file del client separato (`client.py`, `client_ui.py`, …) dalla suite completa: la suite usa la propria modalità
  Client integrata nella Dashboard.

## [0.52-alpha] - 2026-10-24
Germano lavora ora in quattro **modalità operative**, scelte alla prima apertura e modificabili in qualsiasi momento:
**Standalone** (predefinita, tutto su questo computer), **Server** (offre motore e Proxy agli altri PC dell'ufficio),
**Client** (affida il calcolo dei modelli a un Germano Server della rete) oppure **Server + Client**. Ogni elemento
della Dashboard ha un suggerimento al passaggio del mouse. Runtime e modelli invariati rispetto alla 0.51; funziona
offline su Windows 11 appena installato.

### Aggiunto - Interfaccia bilingue (italiano/inglese)
- Tutta la Dashboard e la Guida offline sono **bilingui**. All'avvio la lingua è scelta dall'indirizzo (`?lang=it|en`),
  poi dalla scelta salvata, infine dalla lingua del browser (italiano se inizia per `it`, altrimenti inglese).
  Le **bandierine 🇮🇹 IT / 🇬🇧 EN** in alto cambiano lingua all'istante, tooltip compresi; la scelta è ricordata e
  condivisa tra Dashboard e Guida. Le etichette usate nei documenti (`[PERSONA]`, …) e i messaggi del *Registro
  attività* restano in italiano. I messaggi del server verso l'interfaccia seguono l'intestazione `X-Germano-Lang`.

### Aggiunto - AI del Server condivise con i client
- Il Germano Server può **eseguire per i client le proprie CLI di AI** (es. Claude Code): nuovi endpoint
  `GET /api/harness/v1/tools` (elenco delle AI del server e di quali sono usabili da remoto) e
  `POST /api/harness/v1/run` (esecuzione non interattiva, sempre attraverso il Proxy: verso l'AI esce solo testo
  anonimizzato, la risposta torna con i dati reali). Un client senza quella CLI in locale la usa con `client ask`;
  `client models` mostra il catalogo. La condivisione è **disattivata per impostazione predefinita** e si attiva in
  *Impostazioni › Accesso dalla rete* (`share_ai_tools`), perché usa l'account e le credenziali del server. Gli
  strumenti grafici (Antigravity, Cursor, Claude Desktop, Windsurf) sono elencati come non utilizzabili da remoto con
  il motivo. La modalità Client e il motore remoto accettano l'indirizzo del server anche in forma breve
  (`192.168.1.10`) o come Base URL con token copiato dalla Dashboard, con messaggi di rete comprensibili.

### Aggiunto - Modalità operativa all'avvio
- **Finestra di benvenuto** alla prima apertura della Dashboard: tre caselle — **[x] Standalone** (predefinita),
  **[ ] Server**, **[ ] Client** — con la spiegazione di ciascuna; Server e Client si possono scegliere insieme.
  La finestra ricorda che *«Questa modalità è sempre modificabile in qualsiasi momento nelle Impostazioni»*.
  Chiudendola senza scegliere si conferma Standalone e non viene più riproposta.
- Nuovo pulsante **Impostazioni** e indicatore della modalità nella barra in alto (verde = Server, blu = Client,
  arancione = attenzione, es. server non raggiungibile); in Avanzata, il riquadro **Sistema › Rete e modalità
  operativa** riassume ascolto in rete, collegamento al server e token.
- La modalità **si applica subito, senza riavviare Germano**: la Dashboard ascolta sempre e solo su `127.0.0.1`; la
  parte Server aggiunge e toglie dal vivo un secondo ascolto sulla rete (`0.0.0.0`, o l'IP di `bind_host`) e il
  rilevamento UDP. In **Standalone** e in **Client** nessuna porta di Germano è aperta verso la rete. Server e
  Client avviano il motore da soli; cambiando la parte Client il motore si riavvia con il tipo giusto (locale o remoto).
- Con la parte Server attiva le Impostazioni mostrano indirizzi IP, token per i client (con **Nuovo token**, che
  invalida subito il precedente) e stato del rilevamento automatico.
- **`Germano.exe`** ora imposta `GERMANO_MODE=server`: forza la modalità Server solo per quell'avvio, senza
  modificare la scelta salvata (la Dashboard lo segnala). Resta compatibile `GERMANO_HOST=0.0.0.0`.
- Il cambio di modalità, il token e la ricerca dei server sono riservati al computer stesso (`/api/mode`,
  `/api/mode/token`, `/api/remote/servers`, mai dalla rete) e rispettano `lock_settings`: con le impostazioni
  bloccate dall'amministratore la modalità non si cambia, le preferenze dell'interfaccia sì.

### Aggiunto - Modalità Client (motore remoto)
- Nuovo `germano/remote_engine.py`: in modalità Client il demone **non carica i modelli** (pochi MB di memoria
  invece di alcuni GB) e invia al Germano Server soltanto i testi e le immagini da analizzare; riceve posizioni,
  categorie e punteggi. **Vault, etichette, file e ripristino restano su questo computer**: il server non conserva
  nulla dei client e non ne registra i nomi dei file. Il server applica le impostazioni del client (modelli e
  soglia), quindi il risultato coincide con quello del motore locale.
- Il server si trova da solo con il rilevamento UDP (preferendo un server con GPU) oppure si indica l'indirizzo
  nelle Impostazioni, con il pulsante **Cerca server in rete**. Il token del server è obbligatorio.
- **A prova di guasto**: se il server non risponde Germano non invia nulla, il Proxy e lo Studio bloccano la
  richiesta con un messaggio chiaro (HTTP 503) e i documenti restano nella cartella `input` (non tra i non riusciti)
  finché il server torna disponibile; l'elaborazione riprende da sola. Facoltativo: ripiego sul motore locale se
  nessun server risponde all'avvio (`client_fallback_local`).
- Motore condiviso del server: `GET /api/engine/v1/info`, `POST /api/engine/v1/classify` e
  `/api/engine/v1/{ocr,faces,signatures,plates}`, sempre con token. Un server che a sua volta delega il calcolo non
  condivide il proprio motore (niente catene) e nessuna installazione rileva se stessa (`instance_id`).

### Aggiunto - Suggerimenti (tooltips)
- Spiegazione al passaggio del mouse (e con il tasto Tab) su ogni elemento della Dashboard: pulsanti, card delle
  cartelle, statistiche in tempo reale (CPU, RAM, velocità), stato del motore e della modalità, selettori
  Anonimizza file / Studio AI e Semplice / Avanzata, campi degli indirizzi API, modelli, categorie di dati e soglia.
  Attivi per impostazione predefinita, si disattivano nelle Impostazioni (`enable_tooltips`).

### Aggiunto - Modalità Server LAN
- **Rilevamento automatico sulla LAN** (`germano/discovery.py`): un leggero responder UDP sulla porta **8182**
  risponde ai ping `GERMANO_DISCOVERY_PING` con le informazioni del server (servizio, versione, porta, nome, stato del
  motore condiviso) — mai il token, mai dati personali. Anche `GET /api/discovery` restituisce le stesse informazioni.
  La porta predefinita della Dashboard è ora **8181**.
- **Sicurezza a livelli per l'accesso di rete** (il modello non cambia per chi usa solo `127.0.0.1`):
  - dalla rete, in sola lettura e senza token: Dashboard, `/api/status`, `/api/ai/detect`, `/api/discovery`;
  - dalla rete, con **token condiviso**: il Proxy verso le AI (`/v1/messages`, `/v1/chat/completions`, …),
    `POST /api/studio/send` e il motore condiviso (`/api/engine/v1/…`). Il token si passa nell'intestazione
    `X-Germano-Auth` **oppure** nel Base URL come prefisso `/g/<token>` (così funziona con qualunque CLI, senza
    modificarla). Senza un token valido l'accesso è sempre negato;
  - **solo dal computer del server**: controllo del motore, impostazioni, modalità, file, archivio delle
    corrispondenze e de-anonimizzazione (`/api/v1/deanonymize_*`). I dati reali non sono mai esposti alla rete.
  - Protezione anti DNS-rebinding estesa: si accettano solo host loopback, IP letterali e il nome del computer.
- Il token condiviso viene generato in modo casuale alla prima attivazione della parte Server e salvato in
  `config.json`; `/api/settings` non restituisce più alcun token.
- Nuove impostazioni in `config.json`: `operating_mode`, `first_run_done`, `remote_server`, `remote_token`,
  `client_fallback_local`, `enable_tooltips`, `bind_host`, `discovery_enabled`, `discovery_port`, `lan_token`,
  `server_name`, `instance_id`, `instance_host`.
- Variabile `GERMANO_DATA_DIR`: sposta configurazione, cartelle di lavoro, Vault e registro in un'altra cartella
  (modelli e runtime restano nel programma); consente più istanze indipendenti della stessa installazione.
- La Dashboard, se aperta da un altro computer, mostra gli indirizzi del Proxy con l'IP reale del server.
- **Integrazione Kimi, DeepSeek e Qwen**: aggiunti al catalogo di rilevamento locale (`ai_detect.py`) sia sul server che sul client. Nello Studio AI sono disponibili direttamente come destinazioni di inoltro; nella scheda *Agenti AI e API* sono presenti pulsanti di pre-configurazione rapida a 1 clic per impostare come target OpenAI: OpenAI, DeepSeek (`api.deepseek.com`), Kimi (`api.moonshot.cn`), Qwen (`dashscope.aliyuncs.com`) e Ollama.

### Corretto - dal collaudo client/server del 24/10
- **Privacy: documenti Office e OpenDocument danneggiati non vengono piu' segnati «Pronti» con i dati in chiaro.**
  Se una parte interna con testo (es. `word/document.xml`, `styles.xml`) non e' leggibile, il file va tra i
  *Non riusciti* con il motivo, invece di essere copiato in uscita senza anonimizzazione.
- Un PDF danneggiato o troncato restava bloccato per sempre nella cartella `input` (con una copia in `failed` e
  senza motivo): ora finisce tra i *Non riusciti* con un messaggio chiaro.
- Immagini e scansioni: quando il dato occupa solo una parte della riga letta dall'OCR, il riquadro nero poteva
  lasciare scoperti il primo o l'ultimo carattere (es. le prime due lettere del codice fiscale dopo «Codice
  fiscale:», l'iniziale di un nome). La posizione ora tiene conto della diversa larghezza dei caratteri.
- Messaggi comprensibili per PDF, immagini e archivi danneggiati (prima: errori tecnici con il percorso completo).
- `Thumbs.db`, `desktop.ini` e i file nascosti non contano piu' come documenti «In attesa»: prima il lotto non
  risultava mai completato e la Dashboard restava su «Documenti in arrivo».
- `GET /api/ai/detect` chiesto dalla rete restituisce nomi e versioni delle AI ma non i percorsi di installazione
  (rivelavano il nome utente di Windows del server).
- **Rilevamento automatico in rete** (modalità Client e Germano Client): su un PC senza un server locale la ricerca si
  interrompeva subito, al primo avviso «porta irraggiungibile» che Windows restituisce per il ping a 127.0.0.1, e
  spesso non trovava i server della LAN. Ora ascolta le risposte per tutto il tempo previsto; vengono scartate anche
  le risposte con una porta non valida.
- `Germano.exe` usa i fine riga di Windows (CRLF), come `Germano.exe`.

### Aggiunto - Germano Client v0.01 (prodotto separato)
- Nuova applicazione **`germano_client`** (cartella a parte), leggerissima: **non contiene modelli** (28 MB di
  runtime). Trova il server sulla LAN da solo (broadcast UDP) con ripiego su `client_config.json` o parametro
  da riga di comando, e incanala le CLI locali (Claude Code, Codex, Aider, Gemini CLI) verso il Proxy del server
  impostando `ANTHROPIC_BASE_URL`/`OPENAI_BASE_URL` con il prefisso `/g/<token>`.
- Lanciatore **`START_CLIENT.bat`** con menu interattivo e comandi `discover`, `status`, `launch <cli>`, `send`,
  `config`. Documentazione in `README.md` e `README.en.md`.

## [0.51-alpha] - 2026-10-22
Versione di consolidamento: audit completo del codice 0.50 (bug verificati con test riproducibili), riscrittura
modulare del motore (`germano/`), Dashboard completamente rinnovata e aggiornamenti automatici. Runtime, librerie e
modelli invariati: funziona offline su Windows 11 appena installato.

### Aggiunto - Nuova Dashboard
- Interfaccia ridisegnata, chiara e sobria, con il logo ufficiale. Selettore **Semplice / Avanzata**; in Modalità
  Avanzata quattro schede: *Elaborazione*, *Agenti AI e API*, *Filtri e modelli*, *Sistema e registro*.
- **Lavoro in blocco**: aggiunta di file o di intere cartelle (trascinamento oppure *Seleziona file* /
  *Seleziona cartella*), pulsanti **Apri cartella input** e **Apri cartella output** (Esplora file), contatori
  *In attesa* / *Pronti* / *Non riusciti*, avanzamento del lotto e riepilogo finale, avviso con *Avvia elaborazione*
  quando ci sono documenti in attesa e il motore è in pausa.
- Tabella **Documenti** con schede *Pronti*, *In attesa*, *Non riusciti* e *Originali* (in Avanzata), filtro per
  nome, cartella o motivo e azioni *Apri*, *Mostra nella cartella*, *Scarica*. I documenti non riusciti mostrano il
  motivo e si rimettono in coda singolarmente o tutti insieme (**Rimetti in coda**); **Esporta elenco** salva la
  tabella in CSV per Excel (separatore `;`, protezione dalla formula injection).
- Per ogni documento elaborato vengono registrati modalità, numero di dati oscurati e tempo (`state/outputs.json`),
  visibili nella tabella.
- Scheda **Agenti AI e API**: indirizzi del Proxy da copiare (formato OpenAI `/v1` e formato Anthropic), tabella con
  dove impostarli in Claude Code, Codex CLI, Cursor, Antigravity, Windsurf, OpenCode, Continue, Aider e negli SDK
  OpenAI e Anthropic, servizi di destinazione ed esempi delle API REST con `curl.exe`.
- Scheda *Sistema e registro*: percorsi delle cartelle di lavoro con i pulsanti *Apri* e *Copia percorso*,
  impostazioni degli aggiornamenti, archivio delle corrispondenze e registro in tempo reale.
- Nuove API locali: `GET /api/folders`, `POST /api/file_action` (mostra/apre un file; si aprono solo documenti, mai
  eseguibili o script), `POST /api/retry_failed`, `GET /api/update/status`, `POST /api/update/check|download|install`.

### Aggiunto - Doppia modalità e Studio AI
- La Dashboard ha ora un commutatore principale **📂 Anonimizza file** / **🧠 Studio AI** (la scelta è ricordata).
- **Anonimizza file**: in cima alla vista, una griglia di **card delle cartelle** (In attesa, Pronti, Errori,
  Originali, Vault/estratti) con i contatori in tempo reale; cliccando una card si apre quella cartella in Esplora
  file. Striscia di **statistiche live**: file elaborati/totali del lotto, PII oscurate, documenti al minuto,
  uso di CPU e RAM, con barra di avanzamento.
- **Studio AI**: si scrive un prompt e si allegano file; il testo e il contenuto degli allegati vengono
  **anonimizzati dal motore locale prima** di essere inoltrati a un'AI. Se il motore non è attivo la richiesta è
  bloccata e **nessun dato lascia il computer**. La conversazione mostra sempre *cosa* viene inviato (già con le
  etichette) e l'elenco dei dati oscurati; pulsante per copiare il testo protetto.
- **Rileva AI**: pulsante che individua le AI e le CLI installate sul computer (Claude Code, Claude Desktop,
  Antigravity, Gemini CLI, Codex, Aider, Cursor, Windsurf, Ollama, LM Studio) leggendo file system e porte locali
  (nessun processo avviato, nessuna rete): chip con spunta verde per quelle pronte e selettore della destinazione.
  Il rilevamento non si limita al `PATH` (Claude Code e Antigravity si installano fuori dal `PATH`).
- **Configurazione Granulare**: pulsante nello Studio che apre un cassetto con i pannelli *Profilo di protezione*,
  *Modelli di analisi* (sensibilità compresa) e *Categorie di dati*, per regolare al volo cosa oscurare.
- Nuove API locali: `GET /api/ai/detect` (elenco delle AI installate, in cache 30 s, `?refresh=1` per riscansionare)
  e `POST /api/studio/send` (protegge prompt e allegati e restituisce il testo pronto da inviare, con i dati oscurati).

### Aggiunto - Aggiornamenti automatici
- **Solo quando Windows segnala che il PC è connesso a Internet** (Network List Manager: la verifica non invia
  pacchetti in rete), 20 secondi dopo l'avvio e poi ogni 6 ore, Germano apre `https://download.germano.ai`, unico
  riferimento per le nuove versioni, che rimanda alla cartella pubblica di Google Drive con i pacchetti, e vi cerca lo ZIP
  `GermanoAI_Release_v<versione>.zip` più recente. Su un PC scollegato non avviene alcun tentativo di connessione.
- Se è più recente della versione installata, il pacchetto viene scaricato (anche oltre la pagina di conferma di
  Google Drive per i file grandi), accettato solo via HTTPS da download.germano.ai e dai domini Google, controllato
  (download completo, impronta SHA-256 se nella cartella c'è anche `<nome dello ZIP>.sha256`, CRC di ogni file dello
  ZIP, VERSION uguale alla versione del nome), estratto e preparato nella cartella `update/`.
- Installazione al successivo avvio di `Germano.exe` oppure subito con *Installa ora e riavvia*: un installatore separato
  sostituisce i componenti del programma, conserva `input`, `output`, `processed`, `failed`, `extracted`, `state` e
  `config.json`, rimette al suo posto la versione precedente in caso di errore e riavvia Germano.
- Opzioni `check_updates` e `auto_update` (anche nella Dashboard, *Sistema e registro → Aggiornamenti*) e pulsante
  *Controlla ora*.

### Corretto - Perdita di dati e privacy
- **DOCX distrutti dall'anonimizzazione**: la v0.50 riscriveva ogni paragrafo con `paragraph.text = ...`, cancellando
  grassetti, font, collegamenti e **le immagini** del documento; l'autore restava nei metadati. Ora Word, Excel e
  PowerPoint vengono modificati direttamente nell'XML: cambia solo il testo personale, il resto resta identico.
- **Parti di documento mai analizzate**: note a piè di pagina, caselle di testo, tabelle annidate, commenti (e i loro
  autori), revisioni, controlli contenuto, forme raggruppate e SmartArt di PowerPoint, note del relatore, grafici,
  intestazioni/piè di pagina ODT (`styles.xml`), metadati (autore, ultimo modificatore, titolo), miniature di anteprima.
- **Modello Italian NER cieco oltre ~512 token**: sui testi lunghi non rilevava nulla dopo le prime righe (test: 0
  entità su 5.500 caratteri, 7 dopo la correzione). Ora il testo è diviso in blocchi sovrapposti.
- **PDF scansionati con timbro digitale** (tipici della PA: protocollo stampato su una scansione): niente OCR, quindi
  il contenuto restava leggibile. Ora l'OCR si attiva quando le immagini della pagina hanno poco testo digitale.
- **Scansioni "ricercabili"**: veniva rimosso solo il livello di testo invisibile, l'immagine restava visibile. Ora i
  pixel sottostanti vengono oscurati.
- **Pagine PDF ruotate**: volti/firme/OCR venivano oscurati nel punto sbagliato (coordinate non de-ruotate).
- **PDF**: campi modulo, commenti e relativo autore, segnalibri, metadati/XMP, link `mailto:`, allegati incorporati
  (anche in sottocartelle, prima causavano un errore) e firme digitali PAdES (con nome e codice fiscale del
  firmatario) ora vengono anonimizzati o rimossi. Un'occorrenza mancata non viene più confusa con un'altra
  (censura a livello di carattere invece di `search_for`).
- **Allegati in chiaro**: le email saltavano gli allegati; gli ZIP copiavano invariati i file non supportati o in
  errore; il Proxy inviava in chiaro immagini e PDF nei formati Anthropic e OpenAI Responses. Ora tutto viene
  anonimizzato, oppure escluso/bloccato (principio fail-safe).
- **Vault che poteva azzerarsi**: scritture concorrenti senza lock e lettura fallita trattata come vault vuoto, poi
  salvato sopra quello buono. Ora: lock, scritture atomiche, copia di sicurezza se il file è illeggibile.
- **Ripristino con dati sbagliati**: le etichette non numerate (`[PERSONA]`) venivano sostituite con l'ultimo nome
  visto. Ora si ripristinano solo le etichette numerate; con lo switch spento il vault non salva più i dati reali.
- **Testi ANSI**: TXT/CSV in codifica Windows-1252 perdevano le lettere accentate (`errors="ignore"`).
- **Commenti HTML** trasformati in testo visibile dopo l'anonimizzazione.
- Le immagini venivano riesportate a 72 dpi (perdita di risoluzione), solo la prima pagina dei TIFF multipagina,
  senza correggere la rotazione EXIF delle foto e mantenendo i metadati GPS.
- Gli originali in `processed/` potevano essere sovrascritti da un file omonimo.

### Corretto - Proxy API (Claude Code, Codex, Cursor, Antigravity)
- **Streaming rotto per Anthropic e OpenAI Responses**: la riga `event:` veniva separata dalla riga `data:`, quindi
  tutti gli eventi arrivavano vuoti e gli SDK andavano in errore al primo evento. Nuovo parser SSE conforme.
- Il testo trattenuto per ricomporre un'etichetta spezzata veniva perso a fine blocco; un unico buffer era
  condiviso tra testo e argomenti dei tool (JSON corrotti). Ora buffer per blocco, svuotati a fine blocco.
- Valori ripristinati negli argomenti JSON dei tool senza escape (virgolette/a capo rompevano il JSON).
- I blocchi `thinking` firmati di Claude venivano modificati (firma non più valida).
- Errori del servizio IA (es. 401) restituiti come stream 200 malformato; header `anthropic-beta` e parametri
  `?beta=true` non inoltrati; `/v1/messages/count_tokens` mancante.
- Prestazioni: una chiamata HTTP al motore per ogni messaggio e nessuna cache; ora un'unica chiamata a batch con
  cache dei blocchi già analizzati.

### Corretto - Stabilità
- Il motore restava attivo (circa 6 GB di RAM) dopo la chiusura della finestra di Germano: ora si chiude da solo.
- Importando `daemon.py`, il server cancellava alla chiusura il PID del motore ancora attivo (possibile doppio motore).
- `.doc`/`.ppt`/`.rtf` tramite Word fallivano sempre nel thread di lavoro (CoInitialize mancante) e rischiavano di
  chiudere il Word già aperto dall'utente; il `.ppt` veniva salvato in formato PPTX con estensione `.ppt`.
- Nomi dei fogli Excel con un dato personale: l'XLSX finiva in `failed` (carattere `[` non ammesso).
- `.xls`: le celle anonimizzate perdevano lo stile.
- File elaborati mentre erano ancora in copia; file temporanei di Office (`~$`) e `Thumbs.db` finivano in `failed`;
  file bloccati rielaborati all'infinito; output parziali in caso di arresto.
- Timeout fisso di 5 minuti: i documenti lunghi fallivano sempre (ora 60 minuti configurabili, annullamento
  cooperativo invece di thread lasciati in esecuzione).
- Accesso concorrente ai modelli da più thread (errori casuali "Already borrowed"): ora serializzato.
- Log letto per intero a ogni secondo e mai ruotato; scansione completa delle cartelle a ogni richiesta di stato.
- `Germano.exe`: controllo `%errorlevel%` dentro un blocco (sempre valutato prima), cartelle di rete non supportate.

### Sicurezza
- Protezione anti DNS-rebinding (solo host locali) e anti CSRF (nessuna azione da siti web esterni) sull'API locale,
  che espone il vault con i dati reali; `/api/start` e `/api/stop` solo in POST.
- API interna del motore su porta dinamica, protetta da token (prima porta 8001 fissa, senza autenticazione).
- Escape HTML nella Dashboard (nomi file e valori del vault).
- Nessun dato dei documenti viene inviato in rete. L'unica connessione automatica è il controllo degli
  aggiornamenti (vedi sopra), solo con Internet segnalato da Windows e disattivabile (`"check_updates": false`).
- Conversioni Office in un processo separato, con macro disattivate e timeout.

### Aggiunto
- **RTF nativo** senza Microsoft Word (su Windows 11 24H2 non c'è più nemmeno WordPad).
- **File firmati `.p7m` (CAdES)**: estrazione e anonimizzazione del documento interno (es. `fattura.xml.p7m`).
- `.doc`/`.ppt`/`.xls` che sono in realtà RTF, DOCX, HTML o XML rinominati vengono riconosciuti senza Office;
  conversione tramite LibreOffice se Microsoft Office non è presente.
- Nuovi formati: `.json`, `.jsonl`, `.tsv`, `.md`, `.log`, codice sorgente, `.gif`, modelli Office (`.dotx`, `.potx`...).
- RegEx validate: IBAN anche con spazi e di tutta Europa (checksum), codice fiscale con omocodia e variante tollerante
  agli errori OCR, P.IVA, carte di pagamento (Luhn), telefoni nei formati reali (`333 123 4567`, `+39`, `02/...`),
  date, targhe, CIE, catasto, ragioni sociali in maiuscolo (`ROSSI SRL`), chiavi API e password.
- **Propagazione**: un nome rilevato in un punto viene oscurato in tutte le altre occorrenze del documento.
- Campi FatturaPA (Nome, Cognome, CodiceFiscale, Indirizzo...) riconosciuti per struttura.
- Precisione automatica del modello principale: FP32 con almeno 12 GB di RAM, BF16 (metà memoria) sotto.
- Dashboard: avanzamento in tempo reale (file e pagina), motivo dei documenti non riusciti, banner di errore del
  motore e di server non raggiungibile, trascinamento di intere cartelle, profilo PA/PD visibile, nuove opzioni
  (precisione, timeout, nomi file anonimizzati, servizio Anthropic separato).
- Blocco amministrativo delle impostazioni (`"lock_settings": true` in `config.json`) per il profilo PA.
- Opzione per anonimizzare anche i nomi di file e cartelle (`anonymize_filenames`).
- Avvio di `Germano.exe` con Germano già aperto: apre la Dashboard esistente invece di dare errore di porta occupata.
- Avvisi di `Germano.exe` per Smart App Control, percorsi troppo lunghi e pacchetto incompleto.
- Proxy: certificati di Windows (reti aziendali con ispezione TLS), log di sessione giornalieri in JSONL.

### Modificato
- `check_updates` è ora attivo di default (prima era spento), con le garanzie descritte sopra; nuovo `auto_update`.
- Etichette della Dashboard: *Avvia motore* / *Arresta motore* al posto di *ATTIVA GERMANO* / *FERMA GERMANO*;
  l'interruttore *Ripristino automatico dei dati originali* si trova sotto il riquadro per aggiungere i documenti.

### Documentazione
- Guida offline bilingue aggiornata e con il tema chiaro della Dashboard: sezione "Novità della v0.51", uso in blocco
  passo per passo, le quattro schede della Modalità Avanzata, aggiornamenti automatici, istruzioni per passare dalla
  0.50 alla 0.51 conservando Vault e impostazioni, endpoint `/api/v1/deanonymize_file`, sicurezza delle API locali,
  campi per i servizi OpenAI e Anthropic nel setup di Claude Code, Codex, Cursor e Antigravity.
- README e changelog anche in inglese (`README.en.md`, `CHANGELOG.en.md`).

## [0.50-alpha] - 2026-10-20
### Architettura Standalone & Compatibilità Windows 11 Vanilla (100% Offline)
- **Zero-Admin Native C++ Runtime Bundling**: Estratte e integrate direttamente in `runtime/` e `runtime/Lib/site-packages/torch/lib/` tutte le 12 librerie dinamiche ufficiali a 64-bit del Microsoft Visual C++ Redistributable (`concrt140.dll`, `msvcp140.dll`, `msvcp140_1.dll`, `msvcp140_2.dll`, `msvcp140_atomic_wait.dll`, `msvcp140_codecvt_ids.dll`, `vcamp140.dll`, `vccorlib140.dll`, `vcomp140.dll`, `vcruntime140.dll`, `vcruntime140_1.dll`, `vcruntime140_threads.dll`) insieme alle librerie di sistema `pywin32` (`pythoncom311.dll`, `pywintypes311.dll`). Questo risolve definitivamente gli errori `ImportError: DLL load failed` / `WinError 126` su installazioni **Windows 11 Vanilla** appena formattate, anche quando l'utente avvia `Germano.exe` senza privilegi di Amministratore (UAC).
- **Configurazione `python311._pth` Isolata**: Aggiornato il file di path del runtime embedded per includere `..`, `Lib` e `Lib\site-packages` con `import site` attivo, garantendo la risoluzione deterministica dei moduli indipendentemente dalla working directory o da installazioni Python di sistema preesistenti.
- **Launcher `Germano.exe` Riprogettato**: Riscritto lo script di avvio con codifica UTF-8 (`chcp 65001`), variabili d'ambiente rigorose per l'isolamento offline (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`, `EASYOCR_MODULE_PATH`), pre-flight check dell'interprete embedded e verifica opzionale non bloccante delle librerie VC++.

### Aggiornamento Completo Software, Dipendenze e Modelli IA
- **Aggiornamento Integrale dello Stack Python (39 Pacchetti)**:
  - **AI & Deep Learning**: `torch` aggiornato a `2.14.1+cpu`, `torchvision` a `0.29.1`, `transformers` a `5.20.2`, `tokenizers` a `0.23.3`, `huggingface_hub` a `2.2.0`, `safetensors` a `0.7.0`, `numpy` a `2.4.4`, `scipy` a `1.17.1`, `scikit-image` a `0.26.0`.
  - **Documenti, PDF & Immagini**: `PyMuPDF` (`pymupdf`) aggiornato a `2.0.0`, `opencv-python-headless` a `5.0.0.93`, `pillow` a `13.0.0`, `lxml` a `6.1.3`, `beautifulsoup4` a `4.15.0`, `pypdfium2` a `5.7.0`, `python-bidi` a `0.6.7`, `pyclipper` a `1.4.0`, `shapely` a `2.1.2`.
  - **Web Server, Rete & Sistema**: `Werkzeug` a `3.1.9`, `requests` a `2.33.1`, `urllib3` a `2.8.0`, `certifi` a `2026.10.19`, `charset-normalizer` a `3.4.7`, `idna` a `3.11`, `pywin32` a `312`, `pip` a `26.2.1`, `setuptools` a `84.2.0`, `wheel` a `0.48.0`.
- **Rimozione Conflitti e Duplicati**: Rimosso il pacchetto obsoleto `torch-directml 0.2.5.dev240914` (che forzava il downgrade di PyTorch alla versione 2.4.1 impedendo il caricamento di `transformers >= 5.14`) e rimosso il duplicato `opencv-python` in favore di `opencv-python-headless 5.0.0.93`.
- **Suite Completa di 6 Modelli IA Pre-Impacchettati 100% Offline (`models/`)**:
  1. `models/privacy-filter` (**Velvet Privacy Filter 1.5B FP16**, `3000 MB`): Modello Transformer contestuale multilingue per il rilevamento semantico di PII.
  2. `models/italian-ner-xxl` (**DeepMount00 Italian NER XXL v2 FP16**, `210.2 MB`): Modello NER specializzato sul dominio legale, sanitario, catastale, bancario e amministrativo italiano (58 classi granulari tra cui `CODICE_FISCALE`, `PARTITA_IVA`, `IBAN`, `MALATTIA`, `FARMACO`, `CARTELLA_CLINICA`, `TRIBUNALE`, `SENTENZA`, `FOGLIO_CATASTALE`, `PARTICELLA_CATASTALE`, `RAGIONE_SOCIALE`). Opera in ensemble con `privacy-filter`.
  3. `models/easyocr` (**EasyOCR CRAFT + Latin G2**, `89.2 MB`): Rilevamento e lettura OCR su PDF scansionati e immagini.
  4. `models/face-detection` (**OpenCV 5.0 YuNet ONNX**, `0.23 MB`): Riconoscimento biometrico e oscuramento dei volti (`[VOLTO]`) tramite `cv2.FaceDetectorYN`.
  5. `models/signature-detection` (**YOLOS-Tiny Signature Detector FP16**, `12.4 MB`): Rilevamento visivo e oscuramento delle firme autografe e sigle manoscritte (`[FIRMA]`) su contratti e PDF scansionati.
  6. `models/plate-detection` (**YOLOS-Small License Plate Detector FP16**, `58.5 MB`): Rilevamento visivo e oscuramento delle targhe automobilistiche (`[TARGA]`) nelle fotografie e perizie.

### Nuove Funzionalità e Bugfix Backend (`daemon.py` & `server.py`)
- **Hot-Reload Dinamico della Configurazione (`reload_settings`)**: Il demone in background ora controlla il timestamp di modifica di `config.json` ad ogni ciclo e ad ogni richiesta API. Cambiare profilo (`PA` / `PD`), soglia IA o filtri selettivi nella Dashboard applica le modifiche **in tempo reale** senza dover riavviare il demone e ricaricare i modelli in RAM.
- **Correzione Elaborazione Immagini Raster in `process_pdf`**: Risolto l'errore `RuntimeError: is no PDF` durante l'applicazione delle annotazioni di censura (`add_redact_annot` / `apply_redactions`) su file immagine (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`, `.webp`) convertendo il buffer in PDF in-memory durante la fase di redazione e riesportando l'immagine nel suo formato nativo originale a fine elaborazione.
- **Miglioramento Precisione NLP & Unione Token BPE**:
  - Rimossi gli spazi iniziali/finali inclusi dal tokenizzatore BPE di GPT-2 (`privacy-filter`), evitando che la sostituzione mangi gli spazi tra le parole (es. `"Il signor[PERSONA]"` -> `"Il signor [PERSONA]"`).
  - Unione automatica di token consecutivi appartenenti alla stessa categoria separati da spazio (es. Nome + Cognome uniti in un singolo `[PERSONA_1]` anziché `[PERSONA_1] [PERSONA_2]`).
  - Filtro anti-falsi positivi sui sub-token corti (<= 3 caratteri) interni alle parole comuni italiane (es. la sottostringa `ita` dentro il verbo `abita`).
  - Applicazione effettiva di `filter_and_format_spans` anche sui PDF digitali e sulle scansioni OCR, sostituendo i vecchi `[REDACTED]` generici con le etichette contestuali specifiche (`[PERSONA]`, `[EMAIL]`, `[COD.FISCALE/P.IVA]`, ecc.) e rispettando i 9 filtri selettivi.
- **Correzione Bug `PID_FILE` in `server.py`**: Risolto un `NameError` negli endpoint `/api/check_orphans` e `/api/kill_orphans` in cui `PID_FILE` non era definito nello scope globale di `server.py`.
- **Nuove API Dashboard in `server.py`**:
  - `POST /api/settings`: Salvataggio istantaneo della configurazione su `config.json` senza riavvio del demone.
  - `POST /api/upload_files`: Caricamento diretto di più file dalla Web UI alla cartella `input/`.
  - `GET /api/files`: Elenco dettagliato (nome, dimensione, data, conteggio entità censurate dal report di audit) dei file nelle cartelle `input`, `output`, `processed` e `failed`.
  - `GET /api/download/<folder>/<filename>`: Download immediato dei documenti elaborati direttamente dal browser.
  - `POST /api/open_folder`: Apertura nativa delle cartelle di lavoro in Esplora File di Windows.
  - `POST /api/clear_logs`: Pulizia immediata del log del terminale.

### Nuova Interfaccia Grafica Web (100% Offline, Slider Semplice/Avanzata & Zero CDN)
- **Slider Superiore `✨ Modalità Semplice` / `⚙️ Modalità Avanzata`**:
  - **Modalità Semplice ("A prova di errore", Zero Gergo Tecnico)**: Interfaccia guidata pensata per chiunque, priva di termini tecnici (niente parole come *"Demone"*, *"PID"*, *"OCR"*, *"Regex"*, *"Threshold"* o *"Proxy"*). Pulsante principale immediato (`▶ ATTIVA GERMANO` / `■ FERMA GERMANO`) con **Auto-Start intelligente** (se l'utente trascina un file o clicca su *"Proteggi Testo"* mentre il programma è in pausa, Germano si attiva da solo automaticamente).
  - **Modalità Avanzata con Controllo Totale dei 6 Modelli IA (+ RegEx) e delle 18 Singole Funzionalità/Categorie**:
    - **Blocco 1 — 7 Interruttori per i Singoli Modelli e Motori Locali**:
      1. 🧠 **Velvet Privacy Filter 1.5B FP16** (`enable_model_velvet`)
      2. 🇮🇹 **DeepMount00 Italian NER XXL v2 (58 Classi)** (`enable_model_italian_ner`)
      3. 🔍 **EasyOCR (CRAFT + Latin G2)** (`enable_ocr`)
      4. 🧑 **YuNet Biometria Volti (OpenCV 5 DNN)** (`enable_faces`)
      5. ✍️ **YOLOS-Tiny Signature Detector (Firme Autografe)** (`enable_signatures`)
      6. 🚗 **YOLOS-Small License Plate Detector (Targhe in Foto)** (`enable_plate_vision`)
      7. 📐 **Motore RegEx Italiano Deterministico** (`enable_regex`)
    - **Blocco 2 — 18 Grandi Schede Checkbox per le Singole Funzionalità e Categorie di Dati**:
      1. 👤 **Nomi Propri e Cognomi** (`censor_person` → `[PERSONA_N]`)
      2. 🎓 **Professioni, Avvocati, Notai e Titoli** (`censor_profession` → `[PROFESSIONE/TITOLO_N]`)
      3. 📍 **Indirizzi Fisici, Vie, CAP e Luoghi** (`censor_address` → `[INDIRIZZO_N]`)
      4. 🗺️ **Dati Catastali e Immobiliari (Foglio, Particella, Subalterno)** (`censor_cadastre` → `[CATASTO_N]`)
      5. 🪪 **Codici Fiscali e Partite IVA** (`censor_cf_iva` → `[COD.FISCALE/P.IVA_N]`)
      6. ✉️ **Email e Caselle PEC** (`censor_email` → `[EMAIL_N]`)
      7. 📞 **Telefoni, Cellulari e IMEI** (`censor_phone` → `[TELEFONO_N]`)
      8. 💳 **IBAN, Carte, Conti e Banche** (`censor_account` → `[CONTO/CARTA_N]`)
      9. 💶 **Importi Monetari, Valute e Tassi Mutuo** (`censor_financial` → `[IMPORTO/FINANZA_N]`)
      10. 📅 **Date di Nascita, Età, Scadenze e Orari** (`censor_date` → `[DATA_N]`)
      11. 🏢 **Aziende, Ragioni Sociali, Società ed Enti** (`censor_org` → `[AZIENDA/ENTE_N]`)
      12. 🪪 **Targhe Testuali, CIE, Passaporti e Patenti** (`censor_plates_docs` → `[TARGA/DOCUMENTO_N]`)
      13. 🏥 **Malattie, Diagnosi e Cartelle Cliniche (Art. 9 GDPR)** (`censor_medical` → `[DATO_SANITARIO_N]`)
      14. 💊 **Farmaci, Terapie, Dosaggi e Posologia** (`censor_medicine` → `[FARMACO/TERAPIA_N]`)
      15. ⚖️ **Tribunali, Sentenze e Procedimenti (Art. 10 GDPR)** (`censor_legal` → `[DATO_GIUDIZIARIO_N]`)
      16. 💍 **Stato Civile e Regime Patrimoniale** (`censor_civil_status` → `[STATO_CIVILE_N]`)
      17. 🔑 **Password, PIN e Chiavi Segrete** (`censor_secret` → `[SEGRETO_N]`)
      18. 🌐 **Indirizzi IP, MAC e Link Web (URL)** (`censor_url` → `[URL_N]`)
    - Pulsanti rapidi di preset: *"🛡️ Tutto Attivo (Profilo PA / GDPR)"*, *"⚡ Solo Dati Essenziali"*, *"🔓 Deseleziona Tutto"*.
- **Sistema Automatico di De-Anonimizzazione ("Rimetti a posto automaticamente i dati veri nel ritorno dall'AI")**:
  - **Switch Globale in Testata**: Permette di attivare/disattivare il ripristino automatico dei dati originali senza alcun passaggio manuale e senza mai accedere a cartelle esterne al programma.
  - **Vault Persistente delle Corrispondenze (`extracted/deanonymize_vault.json`)**: Ogni entità nascosta viene sostituita con un tag univoco numerato (`[PERSONA_1]`, `[PERSONA_2]`, `[EMAIL_1]`, `[INDIRIZZO_1]`) e salvata localmente nel Vault.
  - **Proxy API Bidirezionale Automatico per Harness AI (`/v1/chat/completions`, `/v1/responses`, `/v1/messages`)**: Integrazione nativa trasparente con **Google Antigravity**, **OpenAI Codex CLI**, **Cursor**, **Windsurf**, **Claude Code** e **OpenCode**. Il Proxy anonimizza i messaggi e i file in uscita verso il Cloud e **rimette automaticamente al loro posto tutti i dati veri** nelle risposte e negli argomenti `tool_calls` (`write_file`, `edit_file`, `apply_patch`) di ritorno dall'AI, incluso il supporto **Streaming SSE con buffer di ricomposizione (`StreamTagBuffer`)** per i tag spezzati tra più token.
  - **Riconoscimento Automatico nella Cartella Interna `input/` e Dropzone**: Caricando un file o incollando un testo contenente etichette del Vault nella Dropzone o nella cartella `input/`, Germano lo riconosce automaticamente e ripristina i dati originali.
- **Eliminazione Totale Dipendenze CDN Esterne**: Rimossi tutti i riferimenti a `cdnjs.cloudflare.com` (FontAwesome) e `fonts.googleapis.com` (Google Fonts) da `templates/index.html` e `static/style.css`. Tutte le icone sono ora **SVG/ vettoriali native** e la tipografia utilizza lo stack nativo di Windows 11 (`Segoe UI Variable Display`, `Cascadia Mono`, `Consolas`).
- **Pulsante e Manuale Offline Completo Bilingue (`/guide` & `GUIDA_OFFLINE.html`)**: Aggiunto nella testata della dashboard il pulsante *"📖 Guida & Docs"* che apre la guida offline bilingue (italiano e inglese commutabile all'istante). La guida illustra dapprima i concetti base a prova di errore della Modalità Semplice e il funzionamento delle 5 cartelle interne (`input`, `output`, `processed`, `failed`, `extracted`), prosegue con i controlli dettagliati della Modalità Avanzata (i 7 modelli IA locali e le 18 categorie granulari), e contiene le specifiche complete delle API REST e le istruzioni passo-passo per il Proxy con Google Antigravity, OpenAI Codex CLI, Cursor, Windsurf e Claude Code.

### Pre-Distribution Bug Audit & Certificazione Windows 11 Home 100% Offline (Air-Gapped)
- **Escape del Titolo Finestra in `Germano.exe`**: Sostituito `&` con `^&` in `TITLE Germano AI v0.50-alpha - Local Privacy Engine ^& API Proxy` per prevenire l'errore di sintassi della shell `cmd.exe` (`'API' non è riconosciuto come comando interno o esterno`) al doppio clic dell'utente.
- **Risoluzione Race Condition di Avvio & File Lock (`server.py` e `daemon.py`)**:
  - Scrittura immediata del PID (`proc.pid`) in `daemon.pid` al momento dello spawn del processo in `server.py` e alla prima riga di `main()` in `daemon.py` prima del caricamento di PyTorch (5–10s), evitando duplicazioni di processi in background dovute a doppi clic o upload immediati.
  - Chiusura esplicita del descrittore `log_f` nel processo padre in `server.py`, prevenendo lock su `daemon.log` e consentendo la pulizia dei log senza conflitti di condivisione file su Windows.
- **Filtro Post-Merge Etichette di Campo (`daemon.py`)**: Aggiunta la bonifica post-unione dei token su parole chiave di campo (`IBAN`, `CF`, `P.IVA`, `TEL`, `PEC`, `EMAIL`, `BIC`), evitando che frammentazioni sub-word del modello BERT italiano scambino tali etichette per nomi propri di persona (`[PERSONA]`).
- **Verifica Completa in Ambiente Air-Gapped Windows 11 Vanilla**:
  - Simulazione rigorosa con blocco a livello socket di qualsiasi traffico IP esterno a `127.0.0.1`.
  - Isolamento totale di `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `HF_HOME`, `TORCH_HOME` in directory temporanea vuota per certificare l'assenza di dipendenze da cache utente preesistenti o connessioni internet.
  - Test superato al 100% su caricamento dei 6 modelli, anonimizzazione e de-anonimizzazione automatica (file `DOCX`, testo e streaming SSE del Proxy API per Antigravity/Codex/Cursor/Claude Code), e rispetto del limite Windows `MAX_PATH` (percorso massimo di 148 caratteri).

## [0.48-alpha] - 2026-08-01
### Modelli IA & Esecuzione Offline
- **Aggiornamento Modello NLP (`models/privacy-filter`)**: Convertito il modello `velvet-privacy-filter` (1.5B parametri) da FP32 (`5.99 GB`) a `float16` nativo (`model.safetensors` da `3.00 GB`), dimezzando lo spazio su disco e l'occupazione di memoria senza perdita di accuratezza.
- **Integrazione Pesi OCR Offline (`models/easyocr`)**: Pre-impacchettati i modelli `craft_mlt_25k.pth` (rilevamento testo) e `latin_g2.pth` (riconoscimento caratteri) per l'esecuzione offline di EasyOCR.
- **Prerequisiti Windows**: Aggiunto l'installer ufficiale `vc_redist.x64.exe` nella cartella `prerequisites/` e forzate le variabili d'ambiente `HF_HUB_OFFLINE=1` e `TRANSFORMERS_OFFLINE=1`.

## [0.47-alpha] - 2026-05-26
### Refactoring & Bugfix
- **daemon.py**: Risolta la massiccia duplicazione del codice di oscuramento su tutti i formati file (TXT, DOCX, XLSX, PPTX, ecc.) delegando l'elaborazione ad una singola funzione unificata (`anonymize_string`).
- **daemon.py**: Corretto un grave bug nei PDF (falsi positivi) per cui venivano oscurate *tutte* le occorrenze testuali di una parola anche se l'IA ne aveva segnalata solo una specifica. Ora viene indicizzata e processata l'occorrenza corretta con tolleranza ai whitespace.
- **server.py**: Migliorate le prestazioni generali e la stabilità; eliminate chiamate shell lente e rischiose a `tasklist` e `taskkill` sostituendole con API native `psutil`.
- **server.py**: Risolto il rischio di file lock nell'API `api_anonymize` e migliorato il loop di polling (da 1 a 0.5 secondi, e controllo di chiusura atomico sul file di origine).
- Sincronizzata la versione dell'app (`APP_VERSION`) in `server.py` che era rimasta indietro alla 0.18.

## [0.46-alpha] - 2026-05-26
### Architettura Web
- Incorporato l'intero codice e dizionario di traduzione Javascript (`script.js`) all'interno dei tag `<script>` nei file HTML (`index.html` e `guide.html`), eliminando il file esterno per avere i file HTML completamente autonomi e auto-contenuti.

## [0.45-alpha] - 2026-05-26
### Bugfix & Web
- Terzo hotfix su `script.js`: corretta una doppia virgola (`,,`) sfuggita durante il fix precedente che impediva la validazione sintattica stretta di Node.js e manteneva rotto il rendering del sito per alcuni browser.

## [0.44-alpha] - 2026-05-26
### Bugfix & Web
- Secondo hotfix su `script.js`: ripristinata la virgola mancante a fine blocco JSON della traduzione "Casi d'uso" che mandava in errore di sintassi l'interprete Javascript bloccando il sito.

## [0.43-alpha] - 2026-05-26
### Documentazione e Testi
- Riscritti integralmente i testi per i Casi d'Uso 1 (Standalone) e 2 (Proxy API) nel sito web, inserendo esempi espliciti come "[PERSONA 1]" e "Mario Rossi", e aggiornate di conseguenza le traduzioni e i file README.

## [0.42-alpha] - 2026-05-26
### Bugfix & Web
- Hotfix critico su `script.js`: corretta la formattazione JSON (apici doppi all'interno di stringhe) che impediva il corretto caricamento del file Javascript e bloccava il rendering della lingua sulla pagina web.

## [0.41-alpha] - 2026-05-26
### Documentazione e UI
- Invertiti i due Casi d'Uso: il funzionamento "Standalone" massivo è ora il Caso d'Uso 1, mentre il funzionamento "Proxy API" è il Caso d'Uso 2.
- Uniformato lo stile dei due titoli e rimossa l'icona della lampadina per un aspetto più pulito.

## [0.40-alpha] - 2026-05-26
### Interfaccia Utente & Testi
- Sostituito "Esempio d'uso" con "Caso d'uso" nel sito web.
- Evidenziato testualmente il "Caso d'Uso 2" colorandolo di blu per dargli risalto visivo e rimosso il "Tu" iniziale per un tono più professionale.

## [0.39-alpha] - 2026-05-26
### Documentazione
- Aggiunta la dicitura "Caso d'Uso 2" nella descrizione, esplicitando il funzionamento offline per la scansione massiva di directory e cartelle.

## [0.38-alpha] - 2026-05-26
### Documentazione
- Corretta la descrizione del caso d'uso nei file README (it/en) e sulla landing page (it/en), per chiarire esplicitamente che l'applicativo funziona in modalità standalone.

## [0.37-alpha] - 2026-05-26
### Sicurezza
- **Fail-Safe Privacy (Hard Block) su Proxy API**: Implementato un blocco rigoroso nel `server.py`. Ora, se il demone IA fallisce l'anonimizzazione del testo o va in timeout durante l'offuscamento di un'immagine Base64, il Proxy distrugge la richiesta e solleva un errore 500, bloccando categoricamente l'invio dei dati originali all'LLM. Precedentemente l'API restituiva i dati in chiaro in caso di crash per non bloccare l'IDE.
- Aggiornata la documentazione e la guida web sul sito ufficiale per informare gli utenti di questa misura di sicurezza.

## [0.36-alpha] - 2026-05-26
### Documentazione
- **Migliorata Spiegazione Setup IDE**: Aggiunte istruzioni estremamente dettagliate (sia nei README che sul sito web) per guidare l'utente alla configurazione *manuale* dell'impostazione "Base URL" (o "Custom API URL") nei principali IDE come Cursor, Windsurf e Antigravity. È stato inoltre chiarito esplicitamente il motivo di sicurezza per cui non è possibile fornire uno script automatico per questa operazione.

## [0.35-alpha] - 2026-05-26
### Rimosso
- **Script di Installazione MCP Obsoleti**: Rimossi definitivamente i file `INSTALL_AI_PLUGINS.bat`, `UNINSTALL_AI_PLUGINS.bat` e la cartella `ai_plugins`. Con il passaggio all'architettura Proxy API locale, l'integrazione con gli IDE (Cursor, Windsurf, ecc.) avviene nativamente modificando l'URL di base dell'API nell'editor, rendendo questi script di configurazione MCP inutili.

## [0.34-alpha] - 2026-05-26
### Documentazione
- **Aggiornamento Casi d'Uso e Landing Page**: Rimossi definitivamente i riferimenti al vecchio protocollo MCP. La documentazione (README, Sito Web, Guide) è stata interamente riscritta per riflettere l'integrazione nativa tramite API Proxy Locale. Aggiunta menzione esplicita all'anonimizzazione dei prompt testuali.

## [0.33-alpha] - 2026-05-26
### Modificato
- **Comportamento Proxy**: Rimossa la logica di de-anonimizzazione al volo dalle risposte dell'LLM. Ora l'IA risponde esplicitamente usando i tag (es. `[PERSONA_1]`).
- **Log Sessione Proxy**: La mappa di anonimizzazione generata ad ogni intercettazione viene ora salvata all'interno della cartella `extracted` come file JSON (es. `proxy_session_timestamp.json`).

## [0.32-alpha] - 2026-05-26
### Aggiunto
- **Anonimizzatore Testo Manuale in Dashboard**: Aggiunta una nuova sezione nella UI web (`index.html`) che permette all'utente di incollare direttamente del testo, anonimizzarlo istantaneamente tramite la nuova API `/api/v1/anonymize_text` e copiare il risultato, rendendo l'anonimizzatore utilizzabile anche senza API o integrazioni IDE.

## [0.31-alpha] - 2026-05-26
### Aggiunto
- **API Proxy Locale Universale**: Germano AI ora funge da vero e proprio Proxy API compatibile con lo standard OpenAI. Intercetta automaticamente e anonimizza in RAM tutti i prompt testuali, prima che raggiungano l'LLM, e de-anonimizza al volo le risposte generate (supportando il Server Sent Events - Streaming).
- **Endpoint HTTP Interni in `daemon.py`**: Introdotto un mini-server HTTP su thread dedicato per elaborazioni in tempo reale senza latenze da I/O su disco.
- **Supporto Configurazione Proxy**: Aggiunto campo `target_api_url` in `config.json`.

## [0.30-alpha] - 2026-05-26
### Aggiunto
- **Plugin Installer**: Aggiunto il supporto per Lovable e le estensioni Cline / Roo Code in `install_ai_plugins.py`.
- **Plugin Uninstaller**: Creato lo script `UNINSTALL_AI_PLUGINS.bat` e il relativo backend Python per facilitare la rimozione delle configurazioni dei plugin IA.

## [0.29-alpha] - 2026-05-25
### Modificato
- **Esempio di uso**: Aggiornamento del testo dell'esempio per specificare l'assenza di necessità di connessione internet e generalizzare i casi d'uso.

## [0.28-alpha] - 2026-05-25
### Modificato
- **Esempio di uso**: Revisione del testo per includere l'applicazione Windows e server MCP.

## [0.27-alpha] - 2026-05-25
### Modificato
- **Esempio di uso**: Aggiornato il testo dell'esempio di utilizzo nella landing page e nei file README per riflettere meglio i LLM online e le normative della PA.

## [0.26-alpha] - 2026-05-25
### Aggiunto
- **Esempio di uso**: Aggiunto l'esempio di utilizzo dell'IA pubblica assieme allo scudo privacy di Germano direttamente nella homepage del sito (hero section) e in testa al README principale su GitHub.

## [0.25-alpha] - 2026-05-24
### Aggiunto
- **Controlli Pre-flight Build**: Aggiunto un controllo rigoroso nello script `build_release.py` che impedisce di generare lo zip finale se il Python portatile manca nella cartella `runtime`. Inoltra verifica e aggiorna automaticamente le dipendenze essenziali (`python-pptx`, `pywin32`, `beautifulsoup4`) scaricandole all'interno del runtime portatile prima di procedere al build, garantendo un pacchetto sempre funzionante e standalone al 100%.

## [0.24-alpha] - 2026-05-24
### Rimosso
- **install_deps.bat**: Eliminato lo script di installazione delle dipendenze via pip (`python-pptx`, `pywin32`, `beautifulsoup4`) per garantire che l'ambiente sia nativamente standalone al 100%, pre-impacchettando le librerie nel runtime senza richiedere connessione internet all'utente finale.

## [0.23-alpha] - 2026-05-24
### Aggiunto
- **Traduzione README**: Aggiunto il file `README.en.md` per il supporto in lingua inglese.
- **Language Switcher**: Aggiunti link in cima ai file README (sia in italiano che in inglese) per facilitare il passaggio da una lingua all'altra (`README.md` <-> `README.en.md`).

## [0.22-alpha] - 2026-05-24
### Aggiunto
- **Scansione Automatica Editor**: Aggiunta la funzione di scansione automatica all'avvio dell'installer multipiattaforma. Se non viene trovato alcun editor supportato, il sistema restituisce chiaramente l'errore "Code editor non trovato", ma permette comunque la configurazione manuale.
- **Documentazione Estesa**: Aggiunta la documentazione approfondita sulle integrazioni AI multipiattaforma (lo "Scudo Privacy") sia nel file README.md principale, sia nella Knowledge Base del sito (guide.html).

## [0.21-alpha] - 2026-05-24
### Aggiunto
- **Launcher BAT per l'Installer**: Aggiunto lo script rapido `INSTALL_AI_PLUGINS.bat` nella cartella root `STANDALONE` per permettere agli utenti di avviare l'installer multipiattaforma con un semplice doppio clic, senza dover usare il terminale.

## [0.20-alpha] - 2026-05-24
### Aggiunto
- **Supporto AI Universale (MCP)**: Esteso il supporto del plugin non solo ad Antigravity, ma anche a **Cursor IDE, Windsurf, Claude Code, GitHub Copilot e OpenCode**.
- **Installer Interattivo**: Aggiunto lo script multipiattaforma `install_ai_plugins.py` per generare automaticamente le configurazioni (json/comandi) necessarie ad abilitare il plugin privacy nei vari editor IA.
- **Rinominata la cartella**: La cartella del plugin è stata rinominata da `antigravity_plugin` in `ai_plugins` per riflettere il supporto universale.

## [0.19-alpha] - 2026-05-24
### Aggiunto
- **Plugin per Antigravity**: Aggiunto il supporto nativo ad Antigravity tramite un server MCP dedicato (`mcp_server.py`).
- **Autostart e Webview Automatica**: Il plugin verifica l'esecuzione del demone, lo avvia se necessario, e apre in automatico la Dashboard nel browser predefinito.
- **Tool di Anonimizzazione Obbligatoria**: Esposto il tool `read_anonymized_file` che intercetta i file letti dall'IA forzandoli attraverso le API di censura locale.

## [0.18-alpha] - 2026-05-20
### Modificato
- **Aggiornamento Librerie**: Aggiornate le dipendenze core a versioni stabili più recenti (`openpyxl` a `3.1.5`, `PyMuPDF` a `1.27.2.3`, `transformers` a `5.9.0`, `requests` a `2.34.2`, `numpy` a `2.4.6`, e `pandas` a `3.0.3`) per miglioramenti delle prestazioni e stabilità del demone.
- **Allineamento Versioni**: Allineata la variabile `APP_VERSION` nel backend `server.py` alla versione globale del rilascio (`0.18-alpha`).

## [0.17-alpha] - 2026-05-19
### Aggiunto
- **Supporto Esteso Dati e Web**: Implementata elaborazione nativa per file `.csv` (celle), `.xml` (nodi di testo e tail) e `.html`/`.htm` (manipolazione DOM tramite BeautifulSoup).
- **Archivi Compressi `.zip`**: Il demone ora decomprime automaticamente gli archivi `.zip`, processa iterativamente tutti i file supportati all'interno (immagini, documenti, ecc.) e li ri-assembla in un nuovo archivio `.zip` censurato, mantenendo intatta la struttura delle cartelle interne.
- **Supporto Email (`.eml`)**: Elaborazione nativa dei file email. Censurati gli header (`Oggetto`, `Mittente`, `Destinatario`) e il corpo del messaggio, sia esso in `text/plain` o formattato in `html`.
- **Supporto OpenDocument (`.odt`, `.ods`, `.odp`)**: Accesso diretto agli archivi OpenOffice/LibreOffice tramite modifica nativa del file `content.xml` interno all'archivio, evitando corruzioni o dipendenze esterne.
- **Supporto Legacy Word (`.doc`)**: Aggiunto supporto a documenti Word 97-2003 tramite conversione bidirezionale temporanea in background con `win32com`.

## [0.16-alpha] - 2026-05-19
### Aggiunto
- **Supporto Presentazioni PPTX e PPT**: Aggiunto il pieno supporto alle presentazioni PowerPoint (`.pptx`). Implementata inoltre una logica di conversione automatica "al volo" tramite `win32com` per i vecchi file `.ppt` binari.
- **Supporto Avanzato RTF**: Inserita la logica di fallback tramite `win32com` per convertire i file testuali `.rtf` in formato nativo `.docx` prima dell'anonimizzazione, azzerando le corruzioni della formattazione causate da regex dirette sui tag nativi.
- **PDF Incapsulati e Portfolio**: Implementata, tramite la libreria `PyMuPDF`, l'estrazione e l'anonimizzazione ricorsiva dei documenti `.pdf` allegati all'interno di altri documenti `.pdf` (Portfolio/Embfiles).
- **Oggetti OLE in Office**: Sviluppato l'accesso nativo agli archivi ZIP interni dei file `.docx` e `.xlsx` per individuare, estrarre e oscurare automaticamente i file `.pdf` trascinati o incorporati nelle pagine ("Oggetti OLE/Embeddings"), ri-assemblando poi il documento in modo trasparente.

## [0.15-alpha] - 2026-05-12
### Aggiunto
- **Anonimizzazione Contestuale**: Sostituita l'etichetta fissa `redacted` con tag contestuali dinamici forniti da `privacy-filter` e dalle regex (es. `[PERSONA]`, `[EMAIL]`, `[CODICE_FISCALE]`).
- **Censura Selettiva**: Introdotti 9 switch nella UI della Dashboard per permettere la scelta granulare di cosa anonimizzare e cosa lasciare in chiaro (Nomi, Indirizzi, Email, Telefoni, Carte, Segreti, ecc.).

## [0.14-alpha] - 2026-05-12
### Modificato
- **Design Logo**: Rimossa l'icona a forma di scudo (`fas fa-shield-alt`) e impostato il font a `Pixelify Sans` per un look più pulito, su richiesta esplicita.

## [0.13-alpha] - 2026-05-12
### Modificato
- **Responsività Mobile Completa**: Riscritta intera sezione responsive del CSS con tre breakpoint (900px, 768px, 400px). Navbar, Hero, Griglie PA/PD, Step Flow, Sezione API, Download e Footer ora si adattano perfettamente a smartphone e tablet. La pagina Guida (Knowledge Base) collassa sidebar sopra il contenuto su schermi piccoli.
- **Testi aggiornati**: Pulsante API rinominato in "Manuale e Documentazione" (centrato), titolo download cambiato in "Provalo! (è completamente gratis e Open Source)".
- **Navigazione**: Rimosso tasto Home dal menu, il logo è ora cliccabile e rimanda alla homepage.

## [0.12-alpha] - 2026-05-12
### Risolto
- **Deprecation Warning Transformers**: Risolto un warning a console generato dalla libreria `transformers` sostituendo il parametro deprecato `torch_dtype` con `dtype` durante l'inizializzazione del modello matematico in `daemon.py`.

## [0.11-alpha] - 2026-05-12
### Modificato
- **Miglioramento UI/UX nella Dashboard**: Quando viene selezionato il profilo "Germano PA", i filtri (OCR, Biometrica, Dati Sensibili e Soglia) vengono automaticamente disabilitati. Ora l'interfaccia rispecchia questo blocco "ingrigendo" visivamente i toggle (opacity: 0.5) e mostrando un cursore `not-allowed`. Al passaggio del mouse viene visualizzato un tooltip informativo che spiega all'utente di passare al profilo "Germano PD" per sbloccare le funzionalità.

## [0.10-alpha] - 2026-05-12
### Aggiunto
- **Suite di Sviluppo (Dev Tools)**: Creata la cartella `DEV_TOOLS` esterna al pacchetto dell'utente finale. Contiene lo script `update_and_test.py` che permette agli sviluppatori di aggiornare automaticamente le dipendenze, avviare il backend locale, e stressare l'API `/api/v1/anonymize` inviando documenti mock (generati in `test_files`). Valida infine che i dati sensibili siano stati censurati correttamente nel flusso binario di risposta.

## [0.09-alpha] - 2026-05-12
### Aggiunto
- **API REST Locale Sincrona**: Aggiunto l'endpoint `POST /api/v1/anonymize` al server Flask. Ora software di terze parti (CRM, Gestionali) possono inviare un file a Germano AI e ricevere come risposta HTTP diretta il file PDF/Word anonimizzato, delegando il calcolo asincrono al background.
- **Nuovo Layout Knowledge Base**: Riprogettata la pagina `guide.html` con un vero layout da Knowledge Base (sidebar sticky a sinistra per la navigazione rapida e contenuti estesi a destra).
- **Documentazione API**: Inserita nella KB una sezione dedicata per spiegare le chiamate API con esempi in cURL.
- **Scroll-spy Navigazione**: Aggiunto Intersection Observer in Javascript per evidenziare dinamicamente i link della sidebar durante lo scorrimento della documentazione.

## [0.08-alpha] - 2026-05-12
### Aggiunto
- **Pagina "Documentazione / Guida"**: Creata la pagina `guide.html` nel sito web ufficiale, completamente bilingue, contenente i Primi Passi, Struttura delle Cartelle, Requisiti di Sistema e Tecnologie Utilizzate.
- **Sistema Auto-Update**: Inserito un sistema di notifica automatica in `server.py` e `script.js` (Standalone). All'avvio della dashboard, il sistema verifica l'ultima release dal file `VERSION` su GitHub e mostra un banner se c'è un aggiornamento disponibile.

## [0.07-alpha] - 2026-05-12
### Modificato
- Scambiato l'ordine degli elementi nella navbar: il selettore lingua ora è al centro-destra e il pulsante Download è posizionato all'estrema destra.
- Migliorata la fluidità e il layout della navbar su dispositivi mobili.

## [0.06-alpha] - 2026-05-12
### Modificato
- Rimosse 3 voci superflue dal menu di navigazione ("Cos'è", "PA vs PD", "Casi d'Uso").
- Spostato a destra il pulsante principale "Download" sulla navbar.

## [0.05-alpha] - 2026-05-12
### Aggiunto
- Inserita firma "Sviluppato da Yes Consulting - www.yesc.it" sia nel file README.md del repository GitHub che nel footer dinamico (IT/EN) del sito web ufficiale.

## [0.04-alpha] - 2026-05-12
### Aggiunto
- **SEO Multilingua e Indicizzazione Inglese**: Inseriti tag `hreflang` e traduzione dinamica di `title` e `meta description` tramite manipolazione del DOM.
- **Supporto URL Parameter**: Aggiunta logica `?lang=en` o `?lang=it` con `history.pushState` al click sulle bandierine per permettere la condivisione diretta di una lingua specifica e aiutare l'indicizzazione dei motori di ricerca.

## [0.03-alpha] - 2026-05-12
### Aggiunto
- **Supporto Multilingua (IT/EN)**: Implementata architettura JSON `data-i18n` con rilevamento automatico della lingua via `navigator.language` e selettore bandierine (🇮🇹/🇬🇧).
- **SEO Optimization**: Aggiunti tag meta e Open Graph per una perfetta indicizzazione e condivisione sui social.
- **Spiegazione Licenza GNU GPL v3**: Aggiunto paragrafo esplicativo sui diritti e doveri del software libero.
- **Made in Sassari**: Aggiunto badge nel footer per evidenziare l'origine del progetto in Italia.

## [0.02-alpha] - 2026-05-12
### Aggiunto
- Aggiornamento della Landing Page con specifiche di legge (CAD e GDPR).
- Spiegazione estesa della differenza tra Pubblica Amministrazione (Germano PA) e Pubblico Dominio (Germano PD).
- Inserita sezione di collaborazione Open Source su GitHub.
- Esempio esplicito di censura biometria e OCR su documenti d'identità.

## [0.01-alpha] - 2026-05-11
### Aggiunto
- Prima release Standalone ufficiale.
- Riorganizzazione del layout UI in CSS Grid a colonne.
- Sistema "Killer" di processi orfani all'avvio.
- Gestione timeout, fallback CPU/GPU e quarantena documenti danneggiati.
- Supporto a file PDF, DOCX, XLSX, TXT, RTF.
