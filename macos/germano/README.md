# Germano AI - La Privacy Documentale, nell'Era dell'Intelligenza Artificiale.

 *Read this in other languages: [English](README.en.md)*

**Versione 0.90** (14 novembre 2026): più veloce e in parallelo, a parità di protezione. Vedi [Novità della 0.90](#novità-della-090-più-veloce-e-in-parallelo) e il [CHANGELOG](CHANGELOG.md).

*<span style="color: #007bff; font-weight: bold;">Caso d'Uso 1</span>: Hai semplicemente un gran numero di documenti da anonimizzare sul tuo computer o server o NAS. Germano funziona in modalità standalone e restituisce i documenti anonimizzati; supporta molti formati ed è altamente configurabile. Tu semplicemente copi la cartella contenente i file dentro ad input e ricevi i file anonimizzati nella cartella output. Germano mantiene la struttura della directory e delle sottocartelle originali. Germano anonimizza testo, prompt e volti ed è compatibile con il GDPR; Germano è un'applicazione Windows locale e offline (non richiede accesso ad internet per funzionare).*

*<span style="color: #007bff; font-weight: bold;">Caso d'Uso 2</span>: Vuoi usare la potenza di un LLM online (chatgpt, gemini, claude, copilot, deepseek..) ma i tuoi documenti o il testo che scrivi nel prompt contengono dati personali che non vuoi o non puoi inviare all'AI (come da normativa vigente per la Pubblica Amministrazione)? Germano anonimizza questi dati per te: con **Chatbot e Agenti AI** parli direttamente con l'AI che preferisci (e con la **Glass Window** vedi in tempo reale cosa le arriva), oppure si integra come Proxy API Locale con gli strumenti che già usi e che permettono di cambiare l'indirizzo del servizio: Claude Code, Codex, OpenCode, Aider e gli altri. Se sul prompt scrivi "Mario Rossi" se ne accorge e lo sostituisce con [PERSONA_1] prima che venga inviato all'LLM online. In questo modo l'AI online avrà in input solo i documenti e i testi anonimizzati.*

Germano AI è una potente suite open-source progettata per **l'anonimizzazione intelligente** e massiva di documenti e flussi di testo. Basata su motori di Intelligenza Artificiale locale, garantisce la totale privacy dei dati elaborando i file **100% offline** (senza inviare dati al cloud) ed è pronta all'uso al primo colpo anche su un PC con **Windows 11 Vanilla** appena installato, senza richiedere connessione Internet né installazioni preliminari.

> Sviluppato orgogliosamente in Italia da **[Yes Consulting](https://www.yesc.it/)**

---

## Quickstart (Come funziona)

Germano si apre sulla scheda **Chatbot e Agenti AI**, dove parli con l'AI che preferisci e Germano oscura i dati personali prima che escano. Accanto, la scheda **Sanitizzazione Manuale & Vault** conserva tutto il lavoro in blocco sui file.

1. Apri **Germano AI** dal collegamento sul Desktop o dal menu Start (Windows), da Launchpad o dalla cartella Applicazioni (macOS) oppure dal menu delle applicazioni (Linux): si apre direttamente in una finestra dedicata (senza finestre nere di terminale né browser esterni; la **X rossa** in alto a destra chiude completamente l'intero programma e tutti i processi di calcolo in background). Alla prima apertura scegli la modalità operativa (nel dubbio lascia **Standalone**: tutto resta sul tuo computer).
2. **Parla con un'AI, protetto:** scegli il modello **in basso a destra** (sono selezionabili solo le AI rilevate: Claude Code, i modelli locali di Ollama, LM Studio e Jan, i servizi via API con una chiave; le altre restano in grigio con il motivo), scrivi (**Invio** invia, **Maiusc+Invio** va a capo) e allega file con la graffetta o trascinandoli. All'AI arrivano solo le etichette (es. `[PERSONA_1]`); la risposta arriva in streaming, con Markdown e codice evidenziato, già con i tuoi dati veri.
3. **Verifica con la Glass Window:** il pulsante **Glass Window** in alto a destra apre un pannello trasparente che mostra in tempo reale tutto ciò che viene comunicato al modello (testo originale, dati intercettati dal filtro di privacy e dal Vault, testo effettivamente inviato, payload HTTP/CLI grezzo, stream della risposta) e permette di **interrompere l'operazione** in qualsiasi momento.
4. **Anonimizza file in blocco:** nella scheda **Sanitizzazione Manuale & Vault** trascina documenti o intere cartelle sul riquadro **input** (oppure copiali nella cartella **`input`**): Germano li anonimizza e salva i documenti puliti in **`output`**, con la stessa struttura di sottocartelle; gli originali vanno in **`processed`**, i file non elaborabili in **`failed`** con il motivo e il pulsante **Rimetti in coda**. I quattro riquadri sono un'anteprima delle cartelle vere, come in un file manager.

 **Tip Produttività:** il motore di protezione si avvia da solo al primo invio o quando aggiungi documenti; finché è spento nessun dato esce. Puoi aggiungere file *mentre il software sta già lavorando*: vengono messi in coda senza riavviare nulla. **Esporta elenco** salva in CSV (per Excel) l'elenco dei documenti pronti o non riusciti, e il riquadro **«Sanitizzazione manuale di un testo»** anonimizza al volo un testo da incollare in qualsiasi AI (e ripristina la risposta).

 **[SCARICA GERMANO AI STANDALONE](https://download.germano.ai)**

---

## Novità della 0.90: più veloce e in parallelo

La 0.90 lavora in parallelo dove prima aspettava, senza cambiare ciò che viene protetto. Misure sullo stesso PC (Intel i5-4570, 4 core, 16 GB di RAM, nessuna GPU) con gli stessi file: i dati oscurati coincidono con quelli della 0.80.

| Prova | 0.80 | 0.90 |
|---|---|---|
| PDF digitale di 12 pagine | 234,6 s | **132,0 s** (-44%) |
| Sistema 2 su un documento di 56 testi | 214,3 s (75 domande al modello) | **52,3 s** (22 domande) |
| Vault con 100.000 voci: salvataggio / lettura | 308 ms / 496 ms | **2 ms / 4 ms** |
| Trascrizione di 284 s di registrazioni | 107-126 s | **66 s** |
| Pagina scansionata (volti, firme, targhe, OCR) | 29,6 s | **26,7 s** |

- **Motore in parallelo:** Privacy Filter e Italian NER analizzano insieme lo stesso testo; ogni modello ha il proprio lock, così OCR, volti, firme e targhe servono richieste diverse nello stesso momento; Italian NER e OCR si caricano mentre si carica il Privacy Filter.
- **Corsia preferenziale (Fast-Lane):** le richieste interattive (Chatbot e Agenti AI, Proxy, API REST, Remote Control, client della rete) passano davanti ai documenti in coda nella cartella `input`.
- **Sistema 2 senza domande superflue:** i dubbi su parole già oscurate altrove nel documento non vengono più chiesti al modello locale (sul corpus di prova erano il 70%); un dubbio non chiesto resta sempre oscurato.
- **Documenti a lotti:** PDF scansionati a finestre di 8 pagine e immagini dei documenti Office a lotti, analizzati in un'unica chiamata.
- **Vault su SQLite (WAL):** `extracted/deanonymize_vault.db` con scritture e letture incrementali, più la copia portabile `deanonymize_vault.json` nel formato di sempre.
- **File per percorso e cache:** fra server e motore i file passano per percorso (niente base64); cronologia e allegati già protetti arrivano dalla cache del Proxy.
- **Audio a lotti:** le registrazioni da 60 secondi in su vengono trascritte da Whisper a lotti di 8 segmenti.
- **Client in parallelo e verificato:** fino a tre file insieme sul Germano Server, che viene messo alla prova con dati finti all'aggancio e ogni 10 minuti.
- **Proxy blindato:** anonimizzati anche gli argomenti degli strumenti degli agenti (`tool_use.input`, `function.arguments`, `functionCall.args`), con un controllo finale che blocca la richiesta se un dato rilevato è rimasto in chiaro.
- **Linux e macOS allineati:** i sorgenti e i pacchetti `.deb` e `.pkg` sono di nuovo identici a quelli Windows in tutti i file comuni.

Dettagli e misure complete nel [CHANGELOG](CHANGELOG.md).

---

## Installazione Multipiattaforma

Tutti gli installer ufficiali sono singoli file pronti all'uso su **[download.germano.ai](https://download.germano.ai/)** e contengono tutto il necessario: il programma, il proprio Python con tutte le librerie e (nella suite) gli 8 modelli IA. L'installazione non scarica nulla da Internet e funziona su un sistema appena installato.

| Sistema | Suite completa | Client leggero |
|---|---|---|
| Windows 10/11 e Windows Server 2019/2022/2025 a 64 bit (anche in macchina virtuale) | `germano-0.90.exe` | `germano-client-0.90.exe` |
| macOS | `germano-0.90.pkg` (Apple Silicon, macOS 14 o successivo) | `germano-client-0.90.pkg` (Apple Silicon e Intel, macOS 11 o successivo) |
| Linux Ubuntu/Debian a 64 bit | `germano-0.90.deb` | `germano-client-0.90.deb` |

### Windows (10 / 11 a 64 bit)
1. **Download:** scarica `germano-0.90.exe`.
2. **Installazione:** doppio clic sull'installer. **Appena si apre chiede i permessi di amministratore** (richiesta UAC di Windows: scegli **Sì**): servono a consentire l'accesso dalla rete locale, sempre attivo, con una regola del firewall di Windows valida solo per il Python di Germano e solo per le reti private e di dominio (modalità Server LAN). Il programma si installa per l'utente corrente in `%LOCALAPPDATA%\Programs\Germano AI`, con i collegamenti sul Desktop e nel menu Start, la voce in Impostazioni > App e le cartelle di lavoro in `Documenti\Germano AI`; al termine la finestra dell'installer si chiude e **Germano AI si apre da solo**, con i permessi normali dell'utente. Le librerie Microsoft Visual C++ sono già incluse: non serve installare altro.
3. **Avvio:** collegamento **Germano AI** sul Desktop o nel menu Start (finestra dedicata, senza finestre nere di terminale).
4. **Disinstallazione:** Impostazioni > App > App installate > Germano AI (chiede i permessi di amministratore per togliere la regola del firewall); puoi scegliere se conservare le cartelle di lavoro e il Vault.

### Windows Server e macchine virtuali
- **Windows Server 2019, 2022 e 2025** (Standard e Datacenter) e macchine virtuali **VMware, Hyper-V, Proxmox VE (KVM), VirtualBox** e cloud (AWS, Azure, Google Cloud): nessuna GPU e nessun ridistribuibile da installare (le DLL di Visual C++ sono incluse). Consigliati 12 GB di RAM e 4 vCPU: i thread si adattano alle vCPU e la precisione al processore (FP32, oppure BF16 con poca RAM).
- **Senza finestra** (server, Server Core, attività pianificate): `Germano.exe --no-browser --mode=server` avvia server e motore senza finestre e scrive gli indirizzi locali e di rete nel registro e nella console; `Germano.exe --stop` lo arresta. Su Windows Server 2019, che non ha Microsoft Edge, Germano propone da solo di restare attivo così (Internet Explorer non viene usato).
- **Rete**: la regola del firewall vale per le reti private e di dominio; se una scheda è classificata come «Pubblica» (frequente nelle VM), se la regola manca o se i criteri di gruppo ignorano le regole locali, la Dashboard del server lo segnala con il comando per correggerlo. Nelle VM con rete NAT servono l'inoltro della porta TCP 8181 o una scheda in modalità bridge.

L'installer della suite pesa circa 3,8 GB (contiene tutti i modelli IA): al primo doppio clic Microsoft Defender lo analizza e la finestra può comparire dopo qualche secondo. L'installer non ha ancora una firma digitale: se compare «Windows ha protetto il PC» scegli **Ulteriori informazioni > Esegui comunque**.

### macOS
1. **Download:** scarica `germano-0.90.pkg`. La suite completa richiede un Mac con **Apple Silicon** (M1 o successivo) e **macOS 14 Sonoma** o successivo, perché PyTorch non è più pubblicato per i Mac Intel; sui Mac Intel si usa il client leggero `germano-client-0.90.pkg`.
2. **Installazione:** doppio clic sul pacchetto. Alla scelta della destinazione seleziona **Installa solo per me**: `Germano.app` va in `~/Applications` **senza password di amministratore**. Con «Installa per tutti gli utenti» va in `/Applications` e macOS chiede la password. Al termine Germano si apre da solo.
3. **Avvio:** apri **Germano** (`Germano.app`) da Launchpad o dalla cartella Applicazioni. Al primo avvio crea le cartelle di lavoro in `~/Documents/Germano AI` (in `~/Germano AI` se Documenti è sincronizzata con iCloud).
4. **Disinstallazione:** trascina `Germano.app` nel Cestino; le cartelle di lavoro restano dove sono.

Il pacchetto non è ancora firmato da Apple: se macOS ne blocca l'apertura, vai in **Impostazioni di Sistema > Privacy e sicurezza** e scegli **Apri comunque**.

### Linux (Ubuntu / Debian a 64 bit)
1. **Download:** scarica `germano-0.90.deb`, pensato per **Ubuntu 26.04 LTS** e adatto alle distribuzioni basate su Debian con glibc 2.34 o successiva (Ubuntu 22.04 o successive, Debian 12 o successive).
2. **Installazione:** doppio clic sul file (Centro app) oppure da terminale `sudo apt install ./germano-0.90.deb`. Come per ogni pacchetto di sistema viene chiesta la password di amministratore. Il programma va in `/opt/germano`, con la voce **Germano AI** nel menu delle applicazioni e il comando `germano-ai`; non servono altri pacchetti.
3. **Avvio:** dal menu delle applicazioni. Al primo avvio crea le cartelle di lavoro in `Documenti/Germano AI` (la cartella Documenti nella lingua del sistema).
4. **Disinstallazione:** `sudo apt remove germano-ai`; le cartelle di lavoro restano dove sono.

---

## Profili di Conformità (PA vs PD)

Germano AI è progettato per adattarsi sia ad ambienti altamente regolamentati che a professionisti privati tramite due profili specifici selezionabili in tempo reale dalla Dashboard:

### Germano PA (Pubblica Amministrazione)
- A norma **CAD** e **GDPR**.
- Nessuna possibilità per l'operatore di disabilitare filtri di sicurezza cruciali come l'OCR, la biometria facciale o le categorie di dati personali.
- Sicurezza assoluta "by design" per gestire dati ipersensibili dei cittadini.

### Germano PD (Pubblico Dominio)
- Totalmente sbloccato e personalizzabile in tempo reale (Hot-Reload senza riavvio del demone).
- Permette di bilanciare la soglia dei filtri IA, selezionare singolarmente le 18 categorie di dati e i 6 modelli IA (es. disattivare la scansione delle immagini) per ottimizzare i tempi di elaborazione.

---

## Architettura & Modalità Operative (Tri-Mode & Dual Mode)

Germano AI implementa un'architettura ibrida e modulare, configurabile al primo avvio e modificabile in qualsiasi momento nelle Impostazioni (con effetto immediato, senza riavvio):

### Le Tre Modalità Operative:
*   **Standalone (Predefinita e 100% Offline):** tutto viene eseguito in locale su questa macchina in modo ermeticamente isolato. Nessuna porta aperta verso la rete esterna e nessuna ricerca di client. I modelli IA locali sono caricati nella memoria del PC, il Vault delle chiavi resta su disco locale e nessun dato lascia la workstation.
*   **Server LAN (Inference Engine Condiviso):** Germano si mette in ascolto sulla rete locale (porta predefinita **8181**) e risponde al protocollo di rilevamento automatico broadcast UDP (porta **8182**). Offre il motore di inferenza locale, il Proxy AI e il **Remote Control** (da qualsiasi browser della rete, senza installare nulla) a tutte le postazioni e i dispositivi dell'ufficio o dello studio: accesso libero di base, oppure con **utente e password** se l'amministratore attiva la gestione utenti. Si avvia direttamente con `Germano.exe`.
*   **Client (Germano Client Leggero ~28 MB):** applicazione snella e portatile pensata per notebook o postazioni prive di GPU o con risorse limitate. All'avvio individua automaticamente il Germano Server in rete locale e gli delega il calcolo inferenziale dei modelli pesanti. **I documenti originali, i file anonimizzati e il Vault di de-anonimizzazione rimangono rigorosamente sul client**: se il server non è raggiungibile nessun dato lascia la postazione e i file restano in coda.
*   **Server + Client insieme:** la macchina principale condivide il calcolo con la LAN e contemporaneamente elabora la propria coda locale.

### Interfaccia: Chatbot e Agenti AI, più la sanitizzazione manuale
*   **Quattro schede in alto:** **Chatbot e Agenti AI** (predefinita), **Sanitizzazione Manuale & Vault**, **Impostazioni**, **Guida**. La stessa interfaccia è nel **Remote Control** (browser dei dispositivi della rete) e in **Germano Client**. Tema scuro (`#0b0f19`, `#0f172a`, `#1e293b`, accenti `#38bdf8` e `#818cf8`).
*   **Chatbot e Agenti AI:** conversazioni nella barra laterale (ricerca, rinomina, elimina, esporta in Markdown), istruzioni per l'assistente, risposte in streaming con Markdown, evidenziazione della sintassi e **Copia codice**, indicatori di tempo, token, dati oscurati e ripristinati, riquadro di scrittura che cresce con il testo (Invio / Maiusc+Invio), allegati con graffetta o trascinamento, indicatore di protezione e **selettore del modello in basso a destra**: rilevamento automatico ogni 12 secondi delle AI installate (Claude Code, Ollama, LM Studio e Jan con ogni modello installato, servizi via API come OpenAI, Anthropic, Meta Muse, Kimi, DeepSeek, Qwen, Mistral, Grok, Perplexity, Gemini, OpenRouter e Groq); si scelgono solo quelle utilizzabili, le altre (Cursor, Antigravity, Windsurf, agenti che eseguirebbero comandi…) restano in grigio con il motivo.
*   **Glass Window (Ispezione Trasparente):** pannello in vetro smerigliato che mostra in tempo reale le cinque fasi di ogni richiesta (testo originale, filtro di privacy e corrispondenze del Vault, testo effettivo inviato, payload HTTP/CLI grezzo con le chiavi oscurate, stream della risposta prima del ripristino), con **Interrompi operazione** (chiude la connessione con il servizio o termina la CLI: «Operazione interrotta dall'utente tramite Glass Window: nessun dato ulteriore è stato trasmesso o ricevuto.»), revisione facoltativa prima dell'invio (**Invia ora**/ **Blocca invio**) e anteprima della protezione mentre scrivi.
*   **Sanitizzazione Manuale & Vault:** l'elaborazione massiva di lotti con i quattro riquadri `input`, `output`, `processed`, `failed` come in un file manager, statistiche in tempo reale (file/minuto, PII rimosse, CPU/RAM), motivi di scarto con **Rimetti in coda**, esportazione in CSV, sanitizzazione manuale di un testo e archivio delle corrispondenze (Vault).
*   **Interfaccia e Tooltips Bilingui al 100% (Italiano / Inglese):** rilevamento automatico della lingua (`it` -> italiano, altrimenti inglese), commutatore IT / EN nella barra superiore e suggerimenti contestuali al passaggio del mouse, disattivabili nelle Impostazioni.

---

## Remote Control: Germano da qualsiasi dispositivo della rete, senza installare nulla

Con la modalità **Server** attiva, da un PC Windows, Mac o Linux, da un tablet o da uno smartphone collegati alla stessa rete locale basta aprire il browser su **`http://<IP-del-server>:8181/`** (si apre il Remote Control, anche all'indirizzo `/remote`; gli indirizzi esatti sono nelle Impostazioni del server). Come il Remote Control di Google Antigravity, il lavoro resta sul server: il dispositivo è una finestra sicura, con **la stessa interfaccia della Dashboard** (Chatbot e Agenti AI, Sanitizzazione manuale, Impostazioni, Guida). Germano Client mostra la stessa pagina sui PC della rete.

- **Chatbot e Agenti AI con la Glass Window:** si sceglie in basso a destra una delle **AI del server, rilevate automaticamente** — le CLI condivise (eseguite dal server senza strumenti: gli agenti che eseguirebbero comandi o modificherebbero file sul server non vengono mai eseguiti per i client), i **servizi di AI via API** filtrati da Germano (Meta Muse con Muse Wonder e Muse Spark, Kimi, DeepSeek, Qwen, Mistral, Grok, Perplexity, Google Gemini, OpenAI, Anthropic, OpenRouter, Groq) e i **modelli locali del server** (Ollama, LM Studio, Jan: nessun dato esce dalla rete locale). Prompt e fino a **12 allegati** vengono anonimizzati dal motore del server prima di uscire; la risposta torna in streaming con i dati originali **della sola richiesta**, e la Glass Window mostra anche da qui ogni passaggio con **Interrompi operazione**. Chiave API: quella dell'utente (resta sul dispositivo, il server non la salva) oppure quella del server, se l'amministratore condivide le AI di questo computer.
- **Sanitizzazione manuale:** file trascinati e restituiti anonimizzati nel loro formato, ripristino di un file restituito da un'AI, testo protetto da copiare in qualsiasi AI e ripristino della risposta, sempre con le corrispondenze conservate solo sul dispositivo.
- **Opzioni di elaborazione del client** (in Impostazioni): soglia di confidenza, modelli attivi, le 18 categorie di dati personali, mascheramento (etichette numerate `[PERSONA_1]` ripristinabili, etichette generiche `[PERSONA]` o oscuramento `████` irreversibili). Valgono solo per le richieste di quel dispositivo, mai per la configurazione del server. **Con il profilo PA (o `lock_settings`) sono disabilitate e in grigio** e il server respinge ogni modifica con `403 Forbidden` (Compliance Lock).
- **Collega gli strumenti del dispositivo:** gli indirizzi del Proxy da usare come Base URL: `/v1` (formato OpenAI), la radice (formato Anthropic) e `/p/<servizio>/v1` per Meta, Kimi, DeepSeek, Qwen, Mistral, Grok, Perplexity, Gemini, ecc.

**Gestione utenti (facoltativa).** Di base dalla rete si accede senza credenziali. Nella Dashboard del server, in Impostazioni › Modalità e rete › Accesso dalla rete, l'amministratore può creare uno o più utenti e attivare l'accesso con **utente e password**: vale per il Remote Control nel browser (schermata di accesso, cookie di sessione `HttpOnly`) e per Germano Client (`client login`). Le password sono salvate solo come impronta **PBKDF2-SHA256** (600.000 iterazioni, sale casuale); le sessioni durano 30 giorni dall'ultimo uso e si chiudono cambiando la password o eliminando l'utente; dopo 5 tentativi sbagliati l'indirizzo resta bloccato per 10 minuti. Dal computer del server (127.0.0.1) si amministra sempre senza credenziali.

**Sicurezza.** Dalla rete il ripristino dei dati riguarda soltanto le etichette della richiesta stessa: nessun dispositivo può farsi restituire i dati di altri documenti del Vault (nemmeno chiedendo a un'AI di «ripetere [PERSONA_1]»). Dashboard completa, impostazioni, Vault e file restano accessibili solo dal server. In rete locale il collegamento è HTTP, non cifrato: usa Germano su reti fidate.

---

## Funzionalità Principali

*   **100% Offline & pronto su un sistema appena installato:** ogni installer include il proprio Python 3.11 con tutte le librerie (su Windows anche le librerie Microsoft Visual C++ x64, accanto all'interprete: nessun ridistribuibile da installare), l'interfaccia Web priva di CDN esterni e **8 modelli IA locali pre-installati**.
*   **Impostazioni in un solo posto:** **Modalità e rete** (Standalone, Server, Client, accesso dalla rete, gestione utenti), **Protezione e modelli** (profilo, sensibilità, **18 categorie e 7 motori di analisi**: Nomi, Professioni/Titoli, Indirizzi, Catasto, Codici Fiscali/P.IVA, Email/PEC, Telefoni, IBAN/Conti, Importi/Finanza, Date, Aziende/Enti, Targhe/Documenti, Dati Sanitari (Art. 9 GDPR), Farmaci/Terapie, Dati Giudiziari (Art. 10 GDPR), Stato Civile, Password/Segreti e URL/IP), **AI, chiavi e Chatbot**, **Proxy e API** (indirizzi del Proxy, configurazione per ogni strumento, servizi di destinazione, esempi REST), **Sistema e registro**, **Aggiornamenti** (come la pagina «Informazioni» di Google Chrome) e **Informazioni**.
*   **Guida Completa & Documentazione Offline:** scheda *"Guida"* integrata nella Dashboard (disponibile su `/guide` e come file autonomo `GUIDA_OFFLINE.html`), bilingue (italiano e inglese commutabile all'istante), con spiegazioni a prova di errore, guida alle 5 cartelle, specifiche REST API e setup passo-passo per Google Antigravity, OpenAI Codex, Cursor e Claude Code.
*   **De-Anonimizzazione Automatica tramite Proxy API e Cartelle Interne:** Con l'interruttore *"Ripristino automatico dei dati originali"* attivo (predefinito), Germano memorizza nel Vault locale (`extracted/deanonymize_vault.db`, con la copia portabile `deanonymize_vault.json`) i dati associati a `[PERSONA_1]`, `[INDIRIZZO_1]`, ecc. Nelle integrazioni via Proxy API locale (`/v1/chat/completions`, `/v1/responses`, `/v1/messages` per **Google Antigravity, Codex, Cursor, Claude Code, OpenCode**) e nella cartella interna `input/`, le risposte e i file restituiti dall'AI vengono rimessi in chiaro con tutti i dati veri in modo **completamente automatico** (senza mai controllare cartelle esterne al programma).
*   **8 Modelli di Intelligenza Artificiale 100% Offline Integrati (`models/`):**
    1. **Velvet Privacy Filter (1.5B, pesi BF16):** Modello linguistico contestuale multilingue per dati personali (basato su OpenAI Privacy Filter, licenza Apache-2.0).
    2. **Italian NER XXL v2 (58 classi):** Modello specializzato nel dominio legale, sanitario, bancario, catastale e burocratico italiano.
    3. **EasyOCR (CRAFT + Latin G2):** Riconoscimento ottico dei caratteri su PDF scansionati e foto.
    4. **YuNet Face Detector (OpenCV 5 DNN):** Oscuramento biometrico dei volti e fototessere (`[VOLTO]`).
    5. **YOLOS-Tiny Signature Detector:** Rilevamento visivo e oscuramento delle firme autografe manoscritte (`[FIRMA]`).
    6. **YOLOS-Small License Plate Detector:** Rilevamento visivo e oscuramento delle targhe di veicoli nelle foto (`[TARGA]`).
    7. **Whisper Small INT8 (CTranslate2, 240 MB):** trascrizione offline delle registrazioni audio, a lotti per quelle lunghe.
    8. **Qwen3.5-0.8B (GGUF Q8_0, 812 MB, eseguito da llama.cpp) - Sistema 2:** decide nel contesto i casi dubbi del riconoscimento: lascia in chiaro un dubbio solo se è sicuro che non sia un dato personale, altrimenti resta oscurato.
*   **Gestione Multi-Formato Avanzata con Preservazione Formattazione:**
    *   **PDF & Portfolio PDF:** Censura a livello di carattere, OCR e *censura visiva* sulle scansioni (anche miste con timbro digitale), campi modulo, commenti, segnalibri, metadati e anonimizzazione ricorsiva degli allegati incorporati. Firme digitali PAdES rimosse per evitare inconsistenze.
    *    **Immagini (`PNG`, `JPG`, `JPEG`, `BMP`, `TIFF`, `WEBP`, `GIF`):** OCR locale e oscuramento biometrico di volti, firme e targhe con formato e risoluzione originali; metadati EXIF/GPS rimossi.
    *    **Word (`DOCX`, `DOCM`, `DOC`, `RTF`) & OpenDocument (`ODT`, `ODS`, `ODP`):** Anonimizza e de-anonimizza testi, tabelle, intestazioni, piè di pagina, note, caselle di testo, commenti, note del relatore e oggetti incorporati senza alterare la formattazione, font, grassetti o immagini. `DOC`/`PPT` richiedono Microsoft Office o LibreOffice (salvo che siano RTF/DOCX/HTML rinominati).
    *    **Fogli di Calcolo & Presentazioni (`XLSX`, `XLSM`, `XLS`, `CSV`, `TSV`, `PPTX`, `PPT`):** Oscura e ripristina i dati in celle, nomi dei fogli, grafici, slide, note del relatore e commenti, preservando formule e Macro VBA.
    *   **Audio e Trascrizione Vocale Offline (`MP3`, `WAV`, `M4A`, `OGG`, `FLAC`, `OPUS`, `AAC`, `WMA`, `AMR`, `AIFF`):** Trascrizione automatica 100% in locale tramite modello integrato **Whisper Small INT8** (240 MB), bonifica dei metadati ID3/Vorbis/MP4 ed esportazione della trascrizione anonimizzata `<nome>.trascrizione.txt` con marcatura oraria `[hh:mm:ss]`.
    *   **Web, Dati, Email & Archivi Compressi (`HTML`, `XML`/FatturaPA, `JSON`, `EML`, `P7M`, `ZIP`, `7Z`, `RAR`, `TAR`, `GZ`, `BZ2`, `XZ`):** Elaborazione DOM/MIME nativa, allegati email, file firmati `.p7m` e decompressione sicura ricorsiva multi-formato (con **7-Zip** integrato e protezione anti Path-Traversal / anti Zip-Bomb fino a 4 GB) con ricostruzione dell'albero di cartelle.
*   **Affidabilità e Concorrenza:** motore in parallelo con un lock per modello e corsia preferenziale per le richieste interattive, Vault su SQLite in modalità WAL protetto da accessi concorrenti, elaborazione dei file solo a copia completata per evitare letture parziali, chiusura pulita del motore al termine della sessione.

**Requisiti:** Windows 10/11 o Windows Server 2019 o successivo a 64 bit (anche in macchina virtuale), macOS 14 o successivo su Apple Silicon, oppure Linux Ubuntu/Debian a 64 bit; 8 GB di RAM (16 GB consigliati), almeno 4 processori o vCPU e circa 6 GB di spazio libero (più lo spazio dei documenti); nessuna GPU necessaria. Su Windows l'installer della suite chiede i permessi di amministratore appena si apre (regola del firewall per l'accesso dalla rete locale; il client non li chiede); su macOS («Installa solo per me») non servono; su Linux, come per ogni pacchetto .deb, serve la password di amministratore.

## Integrazione REST API

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

## Integrazione AI Multipiattaforma: API Proxy Locale

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

In **Impostazioni › Proxy e API** la Dashboard mostra gli indirizzi da copiare e, strumento per strumento, dove impostarli (o perché uno strumento non si può proteggere).

1. Avvia Germano AI (collegamento sul Desktop o menu Start su Windows, Launchpad su macOS, menu delle applicazioni su Linux).
2. Configura lo strumento perché usi Germano come indirizzo base del servizio:
   - **Claude Code**: prima di avviarlo imposta `ANTHROPIC_BASE_URL=http://127.0.0.1:8181` (in PowerShell: `$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8181"`).
   - **OpenAI Codex CLI**: imposta `OPENAI_BASE_URL=http://127.0.0.1:8181/v1`.
   - **Aider, Qwen Code, OpenCode, Continue, SDK OpenAI e Anthropic**: indica come Base URL `http://127.0.0.1:8181/v1` (formato OpenAI) oppure `http://127.0.0.1:8181` (formato Anthropic).
   - **Cursor, Google Antigravity, Windsurf, Claude Desktop**: **non sono proteggibili** con il Proxy (costruiscono i prompt sui propri server o non accettano un indirizzo locale): per lavorare protetto usa **Chatbot e Agenti AI** di Germano.
3. Assicurati di inserire la tua vera API Key (OpenAI o Anthropic) nello strumento. Lo strumento la invierà a Germano AI, che la utilizzerà localmente **esclusivamente** per inoltrare la richiesta al servizio dopo aver concluso l'anonimizzazione dei prompt e dei file.

### "Fail-Safe Privacy" (Hard Block Attivo)
Il nostro Proxy API è progettato con una tolleranza zero per gli errori (Hard Block). 
Se per qualsiasi motivo (es. demone IA spento, formato illeggibile, o file immagine corrotto) il filtro privacy fallisce la scansione, **il Proxy non invierà i tuoi dati originali all'LLM**. La richiesta verrà istantaneamente distrutta e riceverai un messaggio di errore all'interno del tuo editor. Questo garantisce che in nessun caso i tuoi dati in chiaro possano fuggire verso Internet a causa di un malfunzionamento software. Dalla 0.90 vengono anonimizzati anche gli argomenti degli strumenti degli agenti (`tool_use.input`, `function.arguments`, `functionCall.args`) e un controllo finale blocca la richiesta (errore `422`, nulla viene inviato) se un dato rilevato è rimasto in un campo che Germano non può anonimizzare.

---

## Aggiornamenti silenziosi, come Google Chrome

Di default Germano si aggiorna da solo **in silenzio**, senza finestre né avvisi che interrompono il lavoro e senza rinunciare al funzionamento offline:

1. **Solo se il sistema segnala che il PC è connesso a Internet** (circa 20 secondi dopo l'avvio e poi ogni 6 ore), Germano consulta direttamente `https://download.germano.ai/version.json` (l'unica fonte degli aggiornamenti). Su un PC scollegato non avviene alcun tentativo di connessione.
2. Se c'è una versione più recente, l'installer ufficiale (`germano-<versione>.exe`) viene scaricato **in background a bassa priorità** nella cartella tecnica dell'utente (`%LOCALAPPDATA%\Germano AI\update`), controllandone dimensione e struttura (i file di `download.germano.ai` sono considerati attendibili: nessuna verifica manuale).
3. Su Windows l'installer prepara subito la nuova versione, in silenzio e a bassa priorità, in una cartella accanto a quella del programma (`Germano AI.nuovo`), mentre Germano resta aperto e la versione in uso non viene toccata.
4. Al **successivo avvio** la nuova versione prende il posto della vecchia in pochi secondi e Germano si apre già aggiornato. Chi vuole applicarla subito trova soltanto un discreto **«Riavvia per aggiornare»** in alto. Cartelle di lavoro in `Documenti\Germano AI`, Vault (`extracted\deanonymize_vault.db` e la copia `deanonymize_vault.json`) e preferenze `config.json` restano intatti; se qualcosa non va, resta la versione in uso.

In **Impostazioni › Aggiornamenti**, come nella pagina «Informazioni» di Chrome, si vede lo stato: «Germano AI è aggiornato (v0.90)» con l'ora dell'ultimo controllo, «Download dell'aggiornamento in background…» con la barra di avanzamento, «Riavvia Germano per applicare l'aggiornamento». Su macOS e Linux il pacchetto `.pkg` / `.deb` si scarica allo stesso modo e si apre con il programma di installazione del sistema quando lo decidi tu. Germano Client si aggiorna nello stesso modo.

Opzioni (in Impostazioni o in `config.json`): `"auto_update": false` si limita a segnalare la nuova versione, `"check_updates": false` disattiva il controllo. Durante il controllo non viene inviato alcun dato dei documenti né dei testi.

---

## Struttura Cartelle di Lavoro

Per garantire la massima sicurezza, evitare conflitti di permessi amministrativi (UAC) e prevenire sincronizzazioni cloud involontarie dei dati non cifrati, le cartelle operative di Germano risiedono nella cartella personale dell'utente (`Documenti\Germano AI` su Windows, `~/Documents/Germano AI` su macOS e Linux):

- `Documenti\Germano AI\input`: Trascina qui i file da elaborare.
- `Documenti\Germano AI\output`: I file anonimizzati, con formato e layout originale intatti.
- `Documenti\Germano AI\processed`: File originali archiviati a fine lavoro.
- `Documenti\Germano AI\failed`: Documenti corrotti, bloccati o non conformi (visibili nella scheda *Non riusciti* con il motivo).
- `Documenti\Germano AI\extracted`: Report JSON con i log di audit GDPR di cosa è stato anonimizzato e il **Vault**, la tabella che associa le etichette (`[PERSONA_1]`...) ai dati originali e permette di ripristinarli: dalla 0.90 è un database SQLite (`deanonymize_vault.db`) con la copia portabile `deanonymize_vault.json` nel formato di sempre. Il Vault è locale e **non cifrato**: proteggilo come i documenti originali (resta su questo computer e non viene mai inviato a nessun servizio).


---

## Guida per Sviluppatori: Esecuzione dai Sorgenti GitHub

Questo repository GitHub contiene **esclusivamente il codice sorgente pulito** dell'applicazione e gli asset grafici. Per mantenere il repository leggero (< 30 MB) e veloce da clonare, i modelli neurali e i runtime binari **non sono inclusi nei commit di GitHub**.

### Cosa scaricare prima di avviare il codice in locale:

1. **Modelli di Intelligenza Artificiale (`models/`):**
   - Germano richiede gli 8 modelli IA locali (filtro privacy, NER, EasyOCR, biometria facciale YuNet, rilevamento targhe e firme, Whisper per l'audio e Qwen3.5 per il Sistema 2).
   -  **[Scarica il pacchetto completo dei Modelli](https://download.germano.ai/)** ed estrailo nella cartella `models/` della piattaforma scelta (es. `windows/germano/models/` o `linux/germano/models/`).
   - *In alternativa:* puoi estrarre la cartella `models/` direttamente da qualsiasi installer ufficiale scaricato da [download.germano.ai](https://download.germano.ai).

2. **Dipendenze e Runtime di Sistema:**
   - **Windows:** Richiede Python 3.11+ a 64 bit e le librerie runtime **[Microsoft Visual C++ Redistributable 64-bit](https://aka.ms/vs/17/release/vc_redist.x64.exe)** (`vc_redist.x64.exe`).
   - **Linux:** Richiede Python 3.11+ (`sudo apt install python3 python3-pip python3-venv`).
   - **macOS:** Richiede Python 3.11+ (Apple Silicon o Intel).

### Come avviare l'ambiente di sviluppo in 4 passi:

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

### Costruire gli installer

Ogni release ha la stessa struttura: `sorgenti/{windows,linux,macos}/{germano,germano-client}` (il contenuto di questo repository), `modelli/` (gli 8 modelli), `dipendenze/{windows,linux,macos}` (Python e librerie per ogni sistema, llama.cpp, 7-Zip) e `releases/`. Gli script di `windows/germano/build/` si eseguono su Windows con il Python del runtime, con `-B` (nessuna cache nei sorgenti), e producono i sei pacchetti autosufficienti:

```bash
python -B build/coerenza_sorgenti.py                    # sorgenti Linux e macOS identici a quelli Windows nei file comuni
python -B build/costruisci_installer_windows.py tutti   # releases/windows/germano-0.90.exe e germano-client-0.90.exe
python -B build/costruisci_deb.py tutti                 # releases/linux/germano-0.90.deb e germano-client-0.90.deb
python -B build/costruisci_pkg.py tutti                 # releases/macos/germano-0.90.pkg e germano-client-0.90.pkg
python -B build/crea_version_json.py                    # releases/version.json: dimensioni e SHA-256 lette dai file
```

I costruttori `.deb` e `.pkg` si fermano se gli alberi Linux o macOS non sono allineati ai sorgenti Windows (il riferimento); l'installer Windows della suite deve restare sotto i 4 GB, il limite degli eseguibili di Windows, e il costruttore lo controlla. `version.json` si pubblica su download.germano.ai per ultimo, dopo i sei pacchetti.

## Licenza e Contribuzione
Questo progetto è orgogliosamente distribuito sotto licenza **GNU GPL v3**. Puoi usarlo gratuitamente anche per scopi commerciali, a patto di mantenere Open Source le tue eventuali modifiche. 
Sei uno sviluppatore? Apri una Pull Request! Vogliamo che la privacy sia un diritto accessibile a tutti.

## Contatti
Hai bisogno di supporto Enterprise, integrazioni personalizzate o assistenza?
- **Sito Web**: [germano.ai](https://germano.ai)
- **Sviluppato da**: [Yes Consulting](https://www.yesc.it/)
- **Email**: [info@germano.ai](mailto:info@germano.ai)
