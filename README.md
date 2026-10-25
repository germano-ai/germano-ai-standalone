# 🛡️ Germano AI - La Privacy Documentale, nell'Era dell'Intelligenza Artificiale.



🌍 *Read this in other languages: [English](README.en.md)*



*<span style="color: #007bff; font-weight: bold;">Caso d'Uso 1</span>: Hai semplicemente un gran numero di documenti da anonimizzare sul tuo computer o server o NAS. Germano funziona in modalità standalone e restituisce i documenti anonimizzati; supporta molti formati ed è altamente configurabile. Tu semplicemente copi la cartella contenente i file dentro ad input e ricevi i file anonimizzati nella cartella output. Germano mantiene la struttura della directory e delle sottocartelle originali. Germano anonimizza testo, prompt e volti ed è compatibile con il GDPR; Germano è un'applicazione Windows locale e offline (non richiede accesso ad internet per funzionare).*



*<span style="color: #007bff; font-weight: bold;">Caso d'Uso 2</span>: Vuoi usare la potenza di un LLM online (chatgpt, gemini, claude, copilot, deepseek..) ma i tuoi documenti o il testo che scrivi nel prompt contengono dati personali che non vuoi o non puoi inviare all'AI (come da normativa vigente per la Pubblica Amministrazione)? Germano anonimizza questi dati per te integrandosi perfettamente fungendo da Proxy API Locale con gli strumenti che già usi: Claude Code, Google Antigravity, OpenCode, Cursor e tutti gli altri. Se sul prompt scrivi "Mario Rossi" se ne accorge e lo sostituisce con [PERSONA_1] prima che venga inviato all'LLM online. In questo modo l'AI online avrà in input solo i documenti e i testi anonimizzati.*



Germano AI è una potente suite open-source progettata per **l'anonimizzazione intelligente** e massiva di documenti e flussi di testo. Basata su motori di Intelligenza Artificiale locale, garantisce la totale privacy dei dati elaborando i file **100% offline** (senza inviare dati al cloud) ed è pronta all'uso al primo colpo anche su un PC con **Windows 11 Vanilla** appena installato, senza richiedere connessione Internet né installazioni preliminari.



> Sviluppato orgogliosamente in Italia da **[Yes Consulting](https://www.yesc.it/)**



---



## ⚡ Quickstart (Come funziona)



Germano AI lavora in modo completamente autonomo "ascoltando" le sue cartelle. Il funzionamento base è semplicissimo:

1. Fai doppio clic sul file **`START.bat`** per avviare il server locale e aprire la Dashboard nel browser (`http://127.0.0.1:8181`). Alla prima apertura scegli la modalità operativa (nel dubbio lascia **Standalone**: tutto resta sul tuo computer).

2. Aggiungi i documenti (anche intere cartelle con sottocartelle): trascinali nel riquadro **«Trascina qui file o cartelle»**, usa **Seleziona file** / **Seleziona cartella**, oppure copiali nella cartella **`input`** (il pulsante **Apri cartella input** la apre in Esplora file).

3. Clicca **Avvia motore** in alto a destra (se aggiungi i file dalla Dashboard il motore parte da solo). Germano prende i file da `input`, li anonimizza e salva i documenti puliti nella cartella **`output`**, preservando la struttura delle cartelle e sottocartelle; i contatori **In attesa / Pronti / Non riusciti** mostrano l'andamento del lotto.

4. Ritira i risultati con **Apri cartella output** o dalla tabella **Documenti**. Gli originali vengono archiviati in **`processed`**; i file danneggiati o non supportati finiscono in **`failed`** e compaiono nella scheda **Non riusciti** con il motivo e il pulsante **Rimetti in coda**. I report JSON di audit vengono salvati in **`extracted`**.



💡 **Tip Produttività:** Puoi aggiungere nuovi file o intere cartelle *mentre il software sta già lavorando*: vengono messi in coda ed elaborati senza riavviare nulla. **Esporta elenco** salva in CSV (per Excel) l'elenco dei documenti pronti o non riusciti. Dalla Dashboard puoi anche anonimizzare "al volo" un testo incollandolo nel riquadro **«Testo da inviare a un servizio di AI»**.



👉 **[SCARICA GERMANO AI STANDALONE](https://download.germano.ai)**



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

*   **📡 Server LAN (Inference Engine Condiviso):** Germano si mette in ascolto sulla rete locale (porta predefinita **8181**) e risponde al protocollo di rilevamento automatico broadcast UDP (porta **8182**). Offre il motore di inferenza locale e il Proxy AI a tutte le postazioni dell'ufficio o dello studio, protetto da Token di autenticazione Bearer. Si avvia direttamente con l'eseguibile dedicato `Germano`.

*   **🌐 Client (Germano Client Leggero ~28 MB):** applicazione snella e portatile pensata per notebook o postazioni prive di GPU o con risorse limitate. All'avvio individua automaticamente il Germano Server in rete locale e gli delega il calcolo inferenziale dei modelli pesanti. **I documenti originali, i file anonimizzati e il Vault di de-anonimizzazione rimangono rigorosamente sul client**: se il server non è raggiungibile nessun dato lascia la postazione e i file restano in coda.

*   **Server + Client insieme:** la macchina principale condivide il calcolo con la LAN e contemporaneamente elabora la propria coda locale.



### Dual Mode & Interfaccia Utente:

*   **Dual Mode (Batch + Studio AI):** passaggio istantaneo con un clic tra:

    *   **📁 Anonimizza file (Batch Processing):** vista sobria per l'elaborazione massiva di lotti con pulsanti rapidi per aprire le cartelle `input` e `output`, schede interattive per `input`, `output`, `failed`, `processed`, `extracted`, statistiche di throughput in tempo reale (file/minuto, PII rimosse), monitoraggio hardware (CPU/RAM), visualizzazione dei motivi di scarto con pulsante **Rimetti in coda** ed esportazione elenco in CSV.

    *   **🤖 Studio AI (Local Harness):** interfaccia interattiva stile Google Antigravity con rilevamento automatico degli agenti AI installati sul sistema (Claude Code, OpenAI Codex CLI, Google Antigravity, Aider, Qwen, Kimi, DeepSeek) e configurazione granulare.

*   **Interfaccia e Tooltips Bilingui al 100% (Italiano / Inglese):** rilevamento automatico della lingua del browser (`it` -> italiano, altrimenti inglese di default), commutatore rapido con bandierine (🇮🇹 IT / 🇬🇧 EN) nella barra superiore e oltre 112 suggerimenti contestuali interattivi (tooltips) al passaggio del mouse su ogni controllo, disattivabili nelle Impostazioni.



---



## 🌟 Funzionalità Principali



*   **100% Offline & Windows 11 Vanilla Ready:** Include Python 3.11 embedded, tutte le 12 librerie native Microsoft Visual C++ Redistributable (x64) pre-integrate nel runtime (zero privilegi di amministratore richiesti), interfaccia Web priva di CDN esterni e **6 modelli IA locali pre-installati**.

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



**Requisiti:** Windows 10/11 a 64 bit, 8 GB di RAM (16 GB consigliati), circa 6 GB di spazio libero. Nessuna installazione e nessun privilegio di amministratore.



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



1. Avvia Germano AI facendo doppio clic su `START.bat`.

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



1. **Solo se Windows segnala che il PC è connesso a Internet** (circa 20 secondi dopo l'avvio e poi ogni 6 ore), Germano apre `https://download.germano.ai` (l'indirizzo ufficiale di download, che rimanda alla cartella pubblica dei pacchetti) e cerca lo ZIP `GermanoAI_Release_v<versione>.zip` più recente. Su un PC scollegato non avviene alcun tentativo di connessione.

2. Se è più recente della versione installata, il pacchetto viene scaricato nella cartella `update/` e controllato: download completo, impronta **SHA-256** (se nella cartella c'è anche il file `.sha256`), integrità di ogni file dello ZIP e versione uguale a quella del nome. Un pacchetto che non supera i controlli viene scartato.

3. L'installazione avviene al successivo avvio di `START.bat` (oppure subito con **Installa ora e riavvia** nell'avviso della Dashboard). Le cartelle di lavoro, il Vault e `config.json` non vengono toccati; se qualcosa va storto viene rimessa al suo posto la versione precedente.



Le opzioni sono in Modalità Avanzata, **Sistema e registro → Aggiornamenti** (oppure in `config.json`: `"check_updates": false` disattiva il controllo, `"auto_update": false` si limita a segnalare la nuova versione). Durante il controllo non viene inviato alcun dato dei documenti.



---



## 📂 Struttura Cartelle di Lavoro

- `/input`: Trascina qui i file da elaborare.

- `/output`: I file anonimizzati, con formato e layout originale intatti.

- `/processed`: File originali spostati a fine lavoro.

- `/failed`: Documenti corrotti, bloccati o illeggibili (visibili nella scheda *Non riusciti* con il motivo).

- `/extracted`: File JSON con i log di cosa è stato sostituito (per Audit GDPR).

- `/update`: Creata solo quando serve: aggiornamento scaricato in attesa di installazione.



## 📜 Licenza e Contribuzione

Questo progetto è orgogliosamente distribuito sotto licenza **GNU GPL v3**. Puoi usarlo gratuitamente anche per scopi commerciali, a patto di mantenere Open Source le tue eventuali modifiche. 

Sei uno sviluppatore? Apri una Pull Request! Vogliamo che la privacy sia un diritto accessibile a tutti.



## 📞 Contatti

Hai bisogno di supporto Enterprise, integrazioni personalizzate o assistenza?

- **Sito Web**: [germano.ai](https://germano.ai)

- **Sviluppato da**: [Yes Consulting](https://www.yesc.it/)

- **Email**: [info@germano.ai](mailto:info@germano.ai)

