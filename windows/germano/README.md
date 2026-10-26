# 🛡️ Germano AI - La Privacy Documentale, nell'Era dell'Intelligenza Artificiale.

🌍 *Read this in other languages: [English](README.en.md)*

*<span style="color: #007bff; font-weight: bold;">Caso d'Uso 1</span>: Hai semplicemente un gran numero di documenti da anonimizzare sul tuo computer o server o NAS. Germano funziona in modalità standalone e restituisce i documenti anonimizzati; supporta molti formati ed è altamente configurabile. Tu semplicemente copi la cartella contenente i file dentro ad input e ricevi i file anonimizzati nella cartella output. Germano mantiene la struttura della directory e delle sottocartelle originali. Germano anonimizza testo, prompt e volti ed è compatibile con il GDPR; Germano è un'applicazione Windows locale e offline (non richiede accesso ad internet per funzionare).*

*<span style="color: #007bff; font-weight: bold;">Caso d'Uso 2</span>: Vuoi usare la potenza di un LLM online (chatgpt, gemini, claude, copilot, deepseek..) ma i tuoi documenti o il testo che scrivi nel prompt contengono dati personali che non vuoi o non puoi inviare all'AI (come da normativa vigente per la Pubblica Amministrazione)? Germano anonimizza questi dati per te integrandosi perfettamente fungendo da Proxy API Locale con gli strumenti che già usi: Claude Code, Google Antigravity, OpenCode, Cursor e tutti gli altri. Se sul prompt scrivi "Mario Rossi" se ne accorge e lo sostituisce con [PERSONA_1] prima che venga inviato all'LLM online. In questo modo l'AI online avrà in input solo i documenti e i testi anonimizzati.*

Germano AI è una potente suite open-source progettata per **l'anonimizzazione intelligente** e massiva di documenti e flussi di testo. Basata su motori di Intelligenza Artificiale locale, garantisce la totale privacy dei dati elaborando i file **100% offline** (senza inviare dati al cloud) ed è pronta all'uso al primo colpo anche su un PC con **Windows 11 Vanilla** appena installato, senza richiedere connessione Internet né installazioni preliminari.

> Sviluppato orgogliosamente in Italia da **[Yes Consulting](https://www.yesc.it/)**

---

## ⚡ Quickstart (Come funziona)

Germano AI lavora in modo completamente autonomo "ascoltando" le sue cartelle. Il funzionamento base è semplicissimo:
1. Apri **Germano AI** dal collegamento sul Desktop o dal menu Start (Windows), da Launchpad o dalla cartella Applicazioni (macOS) oppure dal menu delle applicazioni (Linux): si apre direttamente in una finestra dedicata (senza finestre nere di terminale né browser esterni; la **X rossa** in alto a destra chiude completamente l'intero programma e tutti i processi di calcolo in background). Alla prima apertura scegli la modalità operativa (nel dubbio lascia **Standalone**: tutto resta sul tuo computer).
2. Aggiungi i documenti (anche intere cartelle con sottocartelle): nella sezione **Cartelle di lavoro** della Dashboard trascinali sul riquadro **input** («Trascina i file qui nella cartella di input»), usa **Seleziona file** / **Seleziona cartella**, oppure copiali nella cartella **`input`**. I quattro riquadri **input**, **output**, **processed** e **failed** sono un'anteprima delle cartelle vere, come in un file manager: sopra ognuno c'è il percorso completo e un clic sul riquadro (o sul percorso) apre la cartella in Esplora file (Finder su macOS, il file manager su Linux).
3. Clicca **Avvia motore** in alto a destra (se aggiungi i file dalla Dashboard il motore parte da solo). Germano prende i file da `input`, li anonimizza e salva i documenti puliti nella cartella **`output`**, preservando la struttura delle cartelle e sottocartelle; nei riquadri vedi in tempo reale i file che arrivano, quello in elaborazione e quelli che si spostano in `output`, `processed` o `failed`.
4. Ritira i risultati con **Apri cartella output** o dalla tabella **Documenti**. Gli originali vengono archiviati in **`processed`**; i file danneggiati o non supportati finiscono in **`failed`** e compaiono nella scheda **Non riusciti** con il motivo e il pulsante **Rimetti in coda**. I report JSON di audit vengono salvati in **`extracted`**.

💡 **Tip Produttività:** Puoi aggiungere nuovi file o intere cartelle *mentre il software sta già lavorando*: vengono messi in coda ed elaborati senza riavviare nulla. **Esporta elenco** salva in CSV (per Excel) l'elenco dei documenti pronti o non riusciti. Dalla Dashboard puoi anche anonimizzare "al volo" un testo incollandolo nel riquadro **«Testo da inviare a un servizio di AI»**.

👉 **[SCARICA GERMANO AI STANDALONE](https://download.germano.ai)**

---

## 📦 Installazione Multipiattaforma

Tutti gli installer ufficiali sono singoli file pronti all'uso su **[download.germano.ai](https://download.germano.ai/)** e contengono tutto il necessario: il programma, il proprio Python con tutte le librerie e (nella suite) i 6 modelli IA. L'installazione non scarica nulla da Internet e funziona su un sistema appena installato.

| Sistema | Suite completa | Client leggero |
|---|---|---|
| Windows 10/11 a 64 bit | `germano-0.60.exe` | `germano-client-0.60.exe` |
| macOS | `germano-0.60.pkg` (Apple Silicon, macOS 14 o successivo) | `germano-client-0.60.pkg` (Apple Silicon e Intel, macOS 11 o successivo) |
| Linux Ubuntu/Debian a 64 bit | `germano-0.60.deb` | `germano-client-0.60.deb` |

### 🪟 Windows (10 / 11 a 64 bit)
1. **Download:** scarica `germano-0.60.exe`.
2. **Installazione:** doppio clic sull'installer. **Appena si apre chiede i permessi di amministratore** (richiesta UAC di Windows: scegli **Sì**): servono a consentire l'accesso dalla rete locale, sempre attivo, con una regola del firewall di Windows valida solo per il Python di Germano e solo per le reti private e di dominio (modalità Server LAN). Il programma si installa per l'utente corrente in `%LOCALAPPDATA%\Programs\Germano AI`, con i collegamenti sul Desktop e nel menu Start, la voce in Impostazioni > App e le cartelle di lavoro in `Documenti\Germano AI`; al termine la finestra dell'installer si chiude e **Germano AI si apre da solo**, con i permessi normali dell'utente. Le librerie Microsoft Visual C++ sono già incluse: non serve installare altro.
3. **Avvio:** collegamento **Germano AI** sul Desktop o nel menu Start (finestra dedicata, senza finestre nere di terminale).
4. **Disinstallazione:** Impostazioni > App > App installate > Germano AI (chiede i permessi di amministratore per togliere la regola del firewall); puoi scegliere se conservare le cartelle di lavoro e il Vault.

L'installer della suite pesa circa 3 GB: al primo doppio clic Microsoft Defender lo analizza e la finestra può comparire dopo qualche secondo. L'installer non ha ancora una firma digitale: se compare «Windows ha protetto il PC» scegli **Ulteriori informazioni > Esegui comunque**.

### 🍎 macOS
1. **Download:** scarica `germano-0.60.pkg`. La suite completa richiede un Mac con **Apple Silicon** (M1 o successivo) e **macOS 14 Sonoma** o successivo, perché PyTorch non è più pubblicato per i Mac Intel; sui Mac Intel si usa il client leggero `germano-client-0.60.pkg`.
2. **Installazione:** doppio clic sul pacchetto. Alla scelta della destinazione seleziona **Installa solo per me**: `Germano.app` va in `~/Applications` **senza password di amministratore**. Con «Installa per tutti gli utenti» va in `/Applications` e macOS chiede la password. Al termine Germano si apre da solo.
3. **Avvio:** apri **Germano** (`Germano.app`) da Launchpad o dalla cartella Applicazioni. Al primo avvio crea le cartelle di lavoro in `~/Documents/Germano AI` (in `~/Germano AI` se Documenti è sincronizzata con iCloud).
4. **Disinstallazione:** trascina `Germano.app` nel Cestino; le cartelle di lavoro restano dove sono.

Il pacchetto non è ancora firmato da Apple: se macOS ne blocca l'apertura, vai in **Impostazioni di Sistema > Privacy e sicurezza** e scegli **Apri comunque**.

### 🐧 Linux (Ubuntu / Debian a 64 bit)
1. **Download:** scarica `germano-0.60.deb`, pensato per **Ubuntu 26.04 LTS** e adatto alle distribuzioni basate su Debian con glibc 2.34 o successiva (Ubuntu 22.04 o successive, Debian 12 o successive).
2. **Installazione:** doppio clic sul file (Centro app) oppure da terminale `sudo apt install ./germano-0.60.deb`. Come per ogni pacchetto di sistema viene chiesta la password di amministratore. Il programma va in `/opt/germano`, con la voce **Germano AI** nel menu delle applicazioni e il comando `germano-ai`; non servono altri pacchetti.
3. **Avvio:** dal menu delle applicazioni. Al primo avvio crea le cartelle di lavoro in `Documenti/Germano AI` (la cartella Documenti nella lingua del sistema).
4. **Disinstallazione:** `sudo apt remove germano-ai`; le cartelle di lavoro restano dove sono.

---

## 🏛️ Profili di Conformità (PA vs PD)

Germano AI è progettato per adattarsi sia ad ambienti altamente regolamentati che a professionisti privati tramite due profili specifici selezionabili in tempo reale dalla Dashboard:

### 🔴 Germano PA (Pubblica Amministrazione)
- A norma **CAD** e **GDPR**.
- Nessuna possibilità per l'operatore di disabilitare filtri di sicurezza cruciali come l'OCR, la biometria facciale o le categorie di dati personali.
- Sicurezza assoluta "by design" per gestire dati ipersensibili dei cittadini.

### 🟢 Germano PD (Pubblico Dominio)
- Totalmente sbloccato e personalizzabile in tempo reale (Hot-Reload senza riavvio del demone).
- Permette di bilanciare la soglia dei filtri IA, selezionare singolarmente le 18 categorie di dati e i 6 modelli IA (es. disattivare la scansione delle immagini) per ottimizzare i tempi di elaborazione.

---

## 🏛️ Architettura & Modalità Operative (Tri-Mode & Dual Mode)

Germano AI implementa un'architettura ibrida e modulare, configurabile al primo avvio e modificabile in qualsiasi momento nelle Impostazioni (con effetto immediato, senza riavvio):

### Le Tre Modalità Operative:
*   **🖥️ Standalone (Predefinita e 100% Offline):** tutto viene eseguito in locale su questa macchina in modo ermeticamente isolato. Nessuna porta aperta verso la rete esterna e nessuna ricerca di client. I 6 modelli IA locali sono caricati nella memoria del PC, il Vault delle chiavi resta su disco locale e nessun dato lascia la workstation.
*   **📡 Server LAN (Inference Engine Condiviso):** Germano si mette in ascolto sulla rete locale (porta predefinita **8181**) e risponde al protocollo di rilevamento automatico broadcast UDP (porta **8182**). Offre il motore di inferenza locale, il Proxy AI e il **Remote Control** (da qualsiasi browser della rete, senza installare nulla) a tutte le postazioni e i dispositivi dell'ufficio o dello studio: accesso libero di base, oppure con **utente e password** se l'amministratore attiva la gestione utenti. Si avvia direttamente con `Germano.exe`.
*   **🌐 Client (Germano Client Leggero ~28 MB):** applicazione snella e portatile pensata per notebook o postazioni prive di GPU o con risorse limitate. All'avvio individua automaticamente il Germano Server in rete locale e gli delega il calcolo inferenziale dei modelli pesanti. **I documenti originali, i file anonimizzati e il Vault di de-anonimizzazione rimangono rigorosamente sul client**: se il server non è raggiungibile nessun dato lascia la postazione e i file restano in coda.
*   **Server + Client insieme:** la macchina principale condivide il calcolo con la LAN e contemporaneamente elabora la propria coda locale.

### Dual Mode & Interfaccia Utente:
*   **Dual Mode (Batch + Studio AI):** passaggio istantaneo con un clic tra:
    *   **📁 Anonimizza file (Batch Processing):** vista sobria per l'elaborazione massiva di lotti con pulsanti rapidi per aprire le cartelle `input` e `output`, schede interattive per `input`, `output`, `failed`, `processed`, `extracted`, statistiche di throughput in tempo reale (file/minuto, PII rimosse), monitoraggio hardware (CPU/RAM), visualizzazione dei motivi di scarto con pulsante **Rimetti in coda** ed esportazione elenco in CSV.
    *   **🤖 Studio AI (Local Harness):** interfaccia interattiva stile Google Antigravity con rilevamento automatico delle AI installate sul sistema (Claude Code, OpenAI Codex CLI, ChatGPT, Google Antigravity e Gemini CLI, Meta Muse Code, Kimi Code, Qwen Code, DeepSeek, Mistral Vibe, Grok Build, Perplexity, GitHub Copilot CLI, Cursor, Windsurf, Kiro, OpenCode, Aider, Ollama, LM Studio e altre) e configurazione granulare.
*   **Interfaccia e Tooltips Bilingui al 100% (Italiano / Inglese):** rilevamento automatico della lingua del browser (`it` -> italiano, altrimenti inglese di default), commutatore rapido con bandierine (🇮🇹 IT / 🇬🇧 EN) nella barra superiore e oltre 112 suggerimenti contestuali interattivi (tooltips) al passaggio del mouse su ogni controllo, disattivabili nelle Impostazioni.

---

## 📱 Remote Control: Germano da qualsiasi dispositivo della rete, senza installare nulla

Con la modalità **Server** attiva, da un PC Windows, Mac o Linux, da un tablet o da uno smartphone collegati alla stessa rete locale basta aprire il browser su **`http://<IP-del-server>:8181/`** (si apre il Remote Control, anche all'indirizzo `/remote`; gli indirizzi esatti sono nelle Impostazioni del server). Come il Remote Control di Google Antigravity, il lavoro resta sul server: il dispositivo è una finestra sicura.

- **AI del server, rilevate automaticamente:** le CLI e le app installate sul server (con il motivo per cui una CLI non si può eseguire da remoto: gli agenti che eseguirebbero comandi o modificherebbero file sul server non vengono mai eseguiti per i client) e i **servizi di AI via API** filtrati da Germano: Meta Muse (Muse Wonder, Muse Spark), Kimi (Moonshot AI), DeepSeek, Qwen, Mistral, Grok (xAI), Perplexity (Sonar), Google Gemini, OpenAI, Anthropic, OpenRouter, Groq e i **modelli locali del server** (Ollama, LM Studio: nessun dato esce dalla rete locale).
- **Chat protetta:** prompt e fino a **12 allegati** vengono anonimizzati dal motore del server prima di uscire; la risposta torna con i dati originali **della sola richiesta**. Per ogni risposta si vede esattamente il testo protetto ricevuto dall'AI. Chiave API: quella dell'utente (resta sul dispositivo, il server non la salva) oppure quella del server, se l'amministratore condivide le AI di questo computer.
- **Proteggi e ripristina:** testo protetto da copiare in qualsiasi AI e ripristino della risposta direttamente sul dispositivo.
- **Opzioni di elaborazione del client:** soglia di confidenza, modelli attivi, le 18 categorie di dati personali, mascheramento (etichette numerate `[PERSONA_1]` ripristinabili, etichette generiche `[PERSONA]` o oscuramento `████` irreversibili). Valgono solo per le richieste di quel dispositivo, mai per la configurazione del server. **Con il profilo PA (o `lock_settings`) sono disabilitate e in grigio** e il server respinge ogni modifica con `403 Forbidden` (Compliance Lock).
- **Collega gli strumenti del dispositivo:** gli indirizzi del Proxy da usare come Base URL: `/v1` (formato OpenAI), la radice (formato Anthropic) e `/p/<servizio>/v1` per Meta, Kimi, DeepSeek, Qwen, Mistral, Grok, Perplexity, Gemini, ecc.

**Gestione utenti (facoltativa).** Di base dalla rete si accede senza credenziali. Nella Dashboard del server, in Impostazioni › Accesso dalla rete, l'amministratore può creare uno o più utenti e attivare l'accesso con **utente e password**: vale per il Remote Control nel browser (schermata di accesso, cookie di sessione `HttpOnly`) e per Germano Client (`client login`). Le password sono salvate solo come impronta **PBKDF2-SHA256** (600.000 iterazioni, sale casuale); le sessioni durano 30 giorni dall'ultimo uso e si chiudono cambiando la password o eliminando l'utente; dopo 5 tentativi sbagliati l'indirizzo resta bloccato per 10 minuti. Dal computer del server (127.0.0.1) si amministra sempre senza credenziali.

**Sicurezza.** Dalla rete il ripristino dei dati riguarda soltanto le etichette della richiesta stessa: nessun dispositivo può farsi restituire i dati di altri documenti del Vault (nemmeno chiedendo a un'AI di «ripetere [PERSONA_1]»). Dashboard completa, impostazioni, Vault e file restano accessibili solo dal server. In rete locale il collegamento è HTTP, non cifrato: usa Germano su reti fidate.

---

## 🌟 Funzionalità Principali

*   **100% Offline & pronto su un sistema appena installato:** ogni installer include il proprio Python 3.11 con tutte le librerie (su Windows anche le librerie Microsoft Visual C++ x64, accanto all'interprete: nessun ridistribuibile da installare), l'interfaccia Web priva di CDN esterni e **6 modelli IA locali pre-installati**.
*   **Selettore Modalità Semplice / Avanzata:**
    *   **Modalità Semplice:** nessun termine tecnico; si aggiungono i documenti, il motore parte da solo e i risultati si ritirano con un clic.
    *   **Modalità Avanzata:** quattro schede. **Elaborazione** (anche gli originali archiviati), **Agenti AI e API** (indirizzi del Proxy, configurazione per ogni strumento, servizi di destinazione, esempi REST), **Filtri e modelli** (profilo, sensibilità, **18 categorie e 7 motori di analisi**: Nomi, Professioni/Titoli, Indirizzi, Catasto, Codici Fiscali/P.IVA, Email/PEC, Telefoni, IBAN/Conti, Importi/Finanza, Date, Aziende/Enti, Targhe/Documenti, Dati Sanitari (Art. 9 GDPR), Farmaci/Terapie, Dati Giudiziari (Art. 10 GDPR), Stato Civile, Password/Segreti e URL/IP), **Sistema e registro** (calcolo e precisione, cartelle di lavoro, aggiornamenti, Vault, registro in tempo reale).
*   **📖 Guida Completa & Documentazione Offline:** Pulsante *"Guida"* integrato nella Dashboard (disponibile su `/guide` e come file autonomo `GUIDA_OFFLINE.html`), bilingue (italiano e inglese commutabile all'istante), con spiegazioni a prova di errore, guida alle 5 cartelle, specifiche REST API e setup passo-passo per Google Antigravity, OpenAI Codex, Cursor e Claude Code.
*   **🔑 De-Anonimizzazione Automatica tramite Proxy API e Cartelle Interne:** Con l'interruttore *"Ripristino automatico dei dati originali"* attivo (predefinito), Germano memorizza nel Vault locale (`extracted/deanonymize_vault.json`) i dati associati a `[PERSONA_1]`, `[INDIRIZZO_1]`, ecc. Nelle integrazioni via Proxy API locale (`/v1/chat/completions`, `/v1/responses`, `/v1/messages` per **Google Antigravity, Codex, Cursor, Claude Code, OpenCode**) e nella cartella interna `input/`, le risposte e i file restituiti dall'AI vengono rimessi in chiaro con tutti i dati veri in modo **completamente automatico** (senza mai controllare cartelle esterne al programma).
*   **6 Motori di Intelligenza Artificiale 100% Offline Integrati (`models/`):**
    1. **Velvet Privacy Filter (1.5B, pesi BF16):** Modello linguistico contestuale multilingue per dati personali (basato su OpenAI Privacy Filter, licenza Apache-2.0).
    2. **Italian NER XXL v2 (58 classi):** Modello specializzato nel dominio legale, sanitario, bancario, catastale e burocratico italiano.
    3. **EasyOCR (CRAFT + Latin G2):** Riconoscimento ottico dei caratteri su PDF scansionati e foto.
    4. **YuNet Face Detector (OpenCV 5 DNN):** Oscuramento biometrico dei volti e fototessere (`[VOLTO]`).
    5. **YOLOS-Tiny Signature Detector:** Rilevamento visivo e oscuramento delle firme autografe manoscritte (`[FIRMA]`).
    6. **YOLOS-Small License Plate Detector:** Rilevamento visivo e oscuramento delle targhe di veicoli nelle foto (`[TARGA]`).
*   **Gestione Multi-Formato Avanzata con Preservazione Formattazione:**
    *   📄 **PDF & Portfolio PDF:** Censura a livello di carattere, OCR e *censura visiva* sulle scansioni (anche miste con timbro digitale), campi modulo, commenti, segnalibri, metadati e anonimizzazione ricorsiva degli allegati incorporati. Firme digitali PAdES rimosse per evitare inconsistenze.
    *   🖼️ **Immagini (`PNG`, `JPG`, `JPEG`, `BMP`, `TIFF`, `WEBP`, `GIF`):** OCR locale e oscuramento biometrico di volti, firme e targhe con formato e risoluzione originali; metadati EXIF/GPS rimossi.
    *   📝 **Word (`DOCX`, `DOCM`, `DOC`, `RTF`) & OpenDocument (`ODT`, `ODS`, `ODP`):** Anonimizza e de-anonimizza testi, tabelle, intestazioni, piè di pagina, note, caselle di testo, commenti, note del relatore e oggetti incorporati senza alterare la formattazione, font, grassetti o immagini. `DOC`/`PPT` richiedono Microsoft Office o LibreOffice (salvo che siano RTF/DOCX/HTML rinominati).
    *   📊 **Fogli di Calcolo & Presentazioni (`XLSX`, `XLSM`, `XLS`, `CSV`, `TSV`, `PPTX`, `PPT`):** Oscura e ripristina i dati in celle, nomi dei fogli, grafici, slide, note del relatore e commenti, preservando formule e Macro VBA.
    *   🌐 **Web, Dati, Email & Archivi (`HTML`, `XML`/FatturaPA, `JSON`, `EML`, `ZIP`, `P7M`):** Elaborazione DOM/MIME nativa, allegati email, ispezione ricorsiva di archivi `.zip` e file firmati `.p7m` (es. `fattura.xml.p7m`).
*   **Affidabilità e Concorrenza:** Vault protetto da accessi concorrenti, elaborazione file solo a copia completata per evitare letture parziali, chiusura pulita del motore al termine della sessione.

**Requisiti:** Windows 10/11 a 64 bit, macOS 14 o successivo su Apple Silicon, oppure Linux Ubuntu/Debian a 64 bit; 8 GB di RAM (16 GB consigliati) e circa 6 GB di spazio libero (più lo spazio dei documenti). Su Windows l'installer della suite chiede i permessi di amministratore appena si apre (regola del firewall per l'accesso dalla rete locale; il client non li chiede); su macOS («Installa solo per me») non servono; su Linux, come per ogni pacchetto .deb, serve la password di amministratore.

## 🔌 Integrazione REST API

Germano AI non è solo una Dashboard. Integra il motore di anonimizzazione direttamente nei tuoi flussi documentali (CRM, ERP, Protocollo Informatico) tramite le veloci **API locali sincrone**.

### Endpoint di Anonimizzazione File
```http
POST http://127.0.0.1:8181/api/v1/anonymize
```
Restituisce direttamente il flusso binario del file "pulito". Consulta la **[Documentazione Ufficiale](https://germano.ai/guide.html)** sul nostro sito per esempi di utilizzo.

### Endpoint di Anonimizzazione Testo
```http
POST http://127.0.0.1:8181/api/v1/anonymize_text
```
Riceve un JSON con il campo `{"text": "..."}` e restituisce il testo anonimizzato insieme alla mappa dettagliata delle entità estratte.

---

## 🤖 Integrazione AI Multipiattaforma: API Proxy Locale

L'anonimizzazione dei dati non è più limitata ai file! Germano AI include un **API Proxy Locale** universale (compatibile con il formato OpenAI) capace di fare da "scudo" totale tra il tuo IDE (Cursor, Windsurf, Claude Code, Copilot, Antigravity) e l'Intelligenza Artificiale.

### Come funziona lo "Scudo Privacy" Totale
Normalmente, l'IDE invia tutto quello che scrivi nel prompt (o che trascini nella chat) direttamente ai server online.
Configurando il tuo editor per puntare a Germano AI, il flusso cambia completamente:

1. **Intercettazione**: Quando chiedi all'IA qualcosa o alleghi un file, l'IDE invia la richiesta a Germano AI (che gira offline sul tuo PC alla porta 8181).
2. **Censura al Volo**: Germano intercetta la richiesta, estrae i tuoi prompt testuali, li passa al volo al filtro privacy locale, e sostituisce i dati sensibili con etichette indicizzate (es. `[PERSONA_1]`).
3. **Mappatura Tracciabile**: La mappa esatta delle parole sostituite viene salvata in un registro giornaliero (`extracted/proxy_sessions/AAAA-MM-GG.jsonl`), per permetterti di ricollegare facilmente le etichette dell'AI ai dati reali.
4. **Inoltro Sicuro**: Germano inoltra la richiesta "purificata" al vero fornitore LLM (es. OpenAI). Quando l'AI risponderà, utilizzerà a sua volta i tag anonimizzati (es. "Il contratto è intestato a [PERSONA_1]").

L'Intelligenza Artificiale non entrerà **mai** in contatto con i tuoi dati originali, permettendoti di usare prompt estremamente specifici senza violare il GDPR!

### Come Attivarlo (Impostazione Manuale Richiesta)

In Modalità Avanzata, la scheda **Agenti AI e API** della Dashboard mostra gli indirizzi da copiare e, strumento per strumento, dove impostarli.

1. Avvia Germano AI (collegamento sul Desktop o menu Start su Windows, Launchpad su macOS, menu delle applicazioni su Linux).
2. Apri il tuo editor AI preferito e modifica l'indirizzo base del server AI:
   - **Cursor**: Vai in `Impostazioni (Settings)` -> `Models` -> Scorri fino a `OpenAI API Key` e inserisci la tua chiave reale. Poi, appena sotto, attiva la levetta **Override OpenAI Base URL** e inserisci il seguente indirizzo: `http://127.0.0.1:8181/v1`.
   - **Windsurf / Antigravity / Altri IDE**: Nelle impostazioni del Provider AI (sotto la voce OpenAI o Provider Personalizzato), cerca il campo **Base URL** (o API Base URL / Custom URL) e inserisci: `http://127.0.0.1:8181/v1`.
   - **Claude Code**: prima di avviarlo imposta `ANTHROPIC_BASE_URL=http://127.0.0.1:8181` (in PowerShell: `$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8181"`).
   - **OpenAI Codex CLI**: imposta `OPENAI_BASE_URL=http://127.0.0.1:8181/v1`.
3. Assicurati di inserire la tua vera API Key (OpenAI o Anthropic) nell'editor. L'IDE la invierà a Germano AI, che la utilizzerà localmente in modo sicuro **esclusivamente** per inoltrare la richiesta ai server di OpenAI dopo aver concluso l'anonimizzazione dei prompt e dei file!

### 🛡️ "Fail-Safe Privacy" (Hard Block Attivo)
Il nostro Proxy API è progettato con una tolleranza zero per gli errori (Hard Block). 
Se per qualsiasi motivo (es. demone IA spento, formato illeggibile, o file immagine corrotto) il filtro privacy fallisce la scansione, **il Proxy non invierà i tuoi dati originali all'LLM**. La richiesta verrà istantaneamente distrutta e riceverai un messaggio di errore all'interno del tuo editor. Questo garantisce che in nessun caso i tuoi dati in chiaro possano fuggire verso Internet a causa di un malfunzionamento software.

---

## 🔄 Aggiornamenti automatici

Germano si mantiene aggiornato da solo, senza rinunciare al funzionamento offline:

1. **Solo se Windows segnala che il PC è connesso a Internet** (circa 20 secondi dopo l'avvio e poi ogni 6 ore), Germano consulta direttamente `https://download.germano.ai/version.json` (l'unica fonte degli aggiornamenti) e rileva se è disponibile una versione più recente dell'installer per la propria piattaforma. Su un PC scollegato non avviene alcun tentativo di connessione.
2. Se è disponibile un aggiornamento, l'installer ufficiale (`germano-<versione>.exe`) viene scaricato nella cartella tecnica dell'utente (`%LOCALAPPDATA%\Germano AI\update`). Non sono richieste verifiche SHA o passaggi manuali: i file di `download.germano.ai` sono considerati attendibili; si controlla solo che il download sia completo.
3. **Installa ora** (oppure il successivo avvio di Germano) esegue l'installer in modalità aggiornamento: chiude Germano, sostituisce il programma preservando intatti tutti i dati dell'utente (le cartelle di lavoro in `Documenti\Germano AI`, il Vault `extracted\deanonymize_vault.json` e le preferenze `config.json`) e lo riapre.

Su macOS e Linux il controllo si avvia dalla Dashboard: se c'è una versione più recente, Germano indica il nuovo `germano-<versione>.pkg` / `.deb` da scaricare da `download.germano.ai` e aprire con un doppio clic.

Le opzioni sono in Impostazioni, **Sistema e registro → Aggiornamenti** (oppure in `config.json`: `"check_updates": false` disattiva il controllo, `"auto_update": false` si limita a segnalare la nuova versione). Durante il controllo non viene inviato alcun dato dei documenti né dei testi.

---

## 📂 Struttura Cartelle di Lavoro

Per garantire la massima sicurezza, evitare conflitti di permessi amministrativi (UAC) e prevenire sincronizzazioni cloud involontarie dei dati non cifrati, le cartelle operative di Germano risiedono nella cartella personale dell'utente (`Documenti\Germano AI` su Windows, `~/Documents/Germano AI` su macOS e Linux):

- `Documenti\Germano AI\input`: Trascina qui i file da elaborare.
- `Documenti\Germano AI\output`: I file anonimizzati, con formato e layout originale intatti.
- `Documenti\Germano AI\processed`: File originali archiviati a fine lavoro.
- `Documenti\Germano AI\failed`: Documenti corrotti, bloccati o non conformi (visibili nella scheda *Non riusciti* con il motivo).
- `Documenti\Germano AI\extracted`: Report JSON con i log di audit GDPR di cosa è stato anonimizzato e il **Vault** (`deanonymize_vault.json`), la tabella che associa le etichette (`[PERSONA_1]`...) ai dati originali e permette di ripristinarli. Il Vault è un file locale **non cifrato**: proteggilo come i documenti originali (resta su questo computer e non viene mai inviato a nessun servizio).


---

## 🛠️ Guida per Sviluppatori: Esecuzione dai Sorgenti GitHub

Questo repository GitHub contiene **esclusivamente il codice sorgente pulito** dell'applicazione e gli asset grafici. Per mantenere il repository leggero (< 30 MB) e veloce da clonare, i modelli neurali e i runtime binari **non sono inclusi nei commit di GitHub**.

### 📦 Cosa scaricare prima di avviare il codice in locale:

1. **Modelli di Intelligenza Artificiale (`models/`):**
   - Germano richiede i 6 modelli IA locali (filtro privacy, NER, EasyOCR, biometria facciale YuNet, rilevamento targhe e firme).
   - 👉 **[Scarica il pacchetto completo dei Modelli](https://download.germano.ai/)** ed estrailo nella cartella `models/` della piattaforma scelta (es. `windows/germano/models/` o `linux/germano/models/`).
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

## 📜 Licenza e Contribuzione
Questo progetto è orgogliosamente distribuito sotto licenza **GNU GPL v3**. Puoi usarlo gratuitamente anche per scopi commerciali, a patto di mantenere Open Source le tue eventuali modifiche. 
Sei uno sviluppatore? Apri una Pull Request! Vogliamo che la privacy sia un diritto accessibile a tutti.

## 📞 Contatti
Hai bisogno di supporto Enterprise, integrazioni personalizzate o assistenza?
- **Sito Web**: [germano.ai](https://germano.ai)
- **Sviluppato da**: [Yes Consulting](https://www.yesc.it/)
- **Email**: [info@germano.ai](mailto:info@germano.ai)
