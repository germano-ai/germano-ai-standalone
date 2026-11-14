# Germano AI 0.90 — Suite completa per Windows

## Installazione
Scarica **`germano-0.90.exe`** da https://download.germano.ai/ e fai doppio clic: è un solo file con tutto il
necessario (programma, Python 3.11 con le librerie e le DLL di Microsoft Visual C++, gli 8 modelli IA) e non scarica
nulla. **Appena si apre chiede i permessi di amministratore** (richiesta UAC di Windows: scegli **Sì**): servono a
consentire l'accesso dalla rete locale, sempre attivo, con una regola del firewall di Windows solo per il Python di
Germano e solo per le reti private e di dominio. Si installa per l'utente corrente in
`%LOCALAPPDATA%\Programs\Germano AI` e crea i collegamenti sul Desktop e nel menu Start, la voce in Impostazioni › App e
le cartelle di lavoro in `Documenti\Germano AI`; alla fine la finestra dell'installer si chiude e **Germano si apre da
solo**, senza pagine di istruzioni. L'installer non ha ancora una firma digitale: se compare «Windows ha protetto il PC»
scegli **Ulteriori informazioni › Esegui comunque**.

## Come si usa (plug & play)
Apri **Germano AI** dal Desktop o dal menu Start: è l'**unico** programma (`Germano.exe`). Si apre una **finestra
applicativa dedicata** (niente finestra nera del terminale, niente browser con barra degli indirizzi o schede) con
quattro schede in alto:

- **Chatbot e Agenti AI** (predefinita): scrivi alla tua AI come in un assistente moderno e scegli il modello **in basso a
  destra** (solo le AI rilevate: Claude Code, i modelli di Ollama, LM Studio e Jan, i servizi via API con una chiave;
  le altre restano in grigio con il motivo). Germano oscura i dati personali prima dell'invio e li rimette nella
  risposta. Il pulsante **Glass Window** mostra in tempo reale tutto ciò che viene comunicato al modello (testo
  originale, dati oscurati, decisioni del Sistema 2, testo inviato, payload grezzo, risposta grezza) e **Interrompi
  operazione** ferma tutto;
- **Sanitizzazione Manuale & Vault**: quattro riquadri (`input`, `output`, `processed`, `failed`) mostrano, come un
  file manager, i file che entrano, vengono elaborati e si spostano, in tempo reale; per anonimizzare dei documenti
  trascinali sul riquadro **input**. Qui ci sono anche la sanitizzazione manuale di un testo e il Vault;
- **Impostazioni**: modalità e rete, protezione e modelli, AI e chiavi, Proxy e API, sistema, aggiornamenti;
- **Guida**: il manuale completo, anche senza Internet.

Modalità operative (si scelgono e si cambiano in qualsiasi momento in Impostazioni › Modalità e rete):

- **Standalone** (predefinita): tutto offline su questo computer;
- **Server LAN**: offre motore, Proxy, AI condivise e il **Remote Control** (da qualsiasi browser della rete:
  `http://<IP-del-server>:8181/`, senza installare nulla, con la stessa interfaccia: Chatbot e Agenti AI con Glass
  Window e sanitizzazione manuale) agli altri PC e dispositivi dell'ufficio; accesso libero di base, oppure con utente e
  password (Impostazioni › Modalità e rete › Accesso dalla rete › Gestione utenti);
- **Client**: affida il calcolo a un Germano Server della rete (Vault e file restano qui); fino a tre file della
  cartella `input` vengono elaborati insieme e il server viene messo alla prova con dati finti all'aggancio e ogni 10
  minuti: se non riconosce i dati, non viene usato.

Per chiudere **tutto** basta la **X rossa**: si fermano anche il server Flask e il motore IA, senza lasciare processi in
memoria.

## Novità della 0.90: più veloce e in parallelo
A parità di protezione (stessi dati oscurati della 0.80), misurato su un PC con Intel i5-4570, 4 core e 16 GB di RAM:

- **motore in parallelo**: Privacy Filter e Italian NER analizzano insieme lo stesso testo e ogni modello ha il proprio
  lock; Italian NER e OCR si caricano mentre si carica il Privacy Filter;
- **corsia preferenziale**: Chatbot e Agenti AI, Proxy, API, Remote Control e client della rete passano davanti ai
  documenti in coda nella cartella `input`;
- **Sistema 2 senza domande superflue**: un PDF digitale di 12 pagine passa da 234,6 a 132,0 secondi (-44%); su un
  documento di 56 testi il Sistema 2 scende da 214,3 a 52,3 secondi con le stesse decisioni;
- **PDF scansionati a finestre di 8 pagine** e immagini dei documenti Office a lotti;
- **Vault su SQLite**: con 100.000 voci un dato nuovo si salva in circa 2 ms invece di 300;
- **audio a lotti**: 284 secondi di registrazioni trascritti in 66 secondi invece di 107-126;
- **Proxy blindato**: anonimizzati anche gli argomenti degli strumenti degli agenti AI, con un controllo finale che
  blocca la richiesta se un dato rilevato è rimasto in chiaro.

## Aggiornamenti silenziosi (come Google Chrome)
Attivi di default. Solo quando Windows segnala la connessione a Internet, Germano controlla
https://download.germano.ai/version.json, scarica la nuova versione in background a bassa priorità, la prepara accanto a
quella in uso e la applica al **successivo avvio** in pochi secondi: nessuna finestra, nessun avviso che interrompe. Al
massimo compare un discreto **«Riavvia per aggiornare»** in alto. Stato e opzioni in Impostazioni › Aggiornamenti.

## Formati audio e archivi compressi (dalla 0.80)
- **File audio** (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac` e altri): il parlato viene trascritto offline con il modello
  integrato Whisper Small INT8 (a lotti per le registrazioni lunghe) e i metadati incorporati vengono bonificati; in
  `output` esce la trascrizione anonimizzata `<nome>.trascrizione.txt` con marcatura oraria `[hh:mm:ss]`, l'audio
  originale va in `processed`.
- **Archivi compressi** (`.zip`, `.tar`, `.tar.gz`, `.tgz`, `.gz`, `.bz2`, `.xz`, `.7z`, `.rar`): apertura sicura
  (nessun file estratto con il percorso originale, protezione dalle «bombe» di decompressione fino a 4 GB), documenti
  interni anonimizzati uno per uno e archivio ricomposto in `output` con la stessa struttura (i `.rar` escono come
  `.rar.zip`).

## Dati e privacy
- Cartelle di lavoro in `Documenti\Germano AI`: `input`, `output`, `processed`, `failed`, `extracted` (se Documenti è
  sincronizzata con OneDrive, in `%USERPROFILE%\Germano AI`).
- Il **Vault** (la tabella etichette ↔ dati originali che permette il ripristino) è in `extracted`: dalla 0.90 è il
  database `deanonymize_vault.db` (SQLite), con la copia portabile `deanonymize_vault.json` nel formato di sempre. È
  locale e **non cifrato**: proteggilo come i documenti originali. Per trasferirlo su un altro PC basta copiare
  `deanonymize_vault.json` nella nuova cartella `extracted`: al primo avvio le sue voci vengono importate.
- Impostazioni in `Documenti\Germano AI\config.json`; file tecnici (finestra, registri, aggiornamenti scaricati) in
  `%LOCALAPPDATA%\Germano AI`.
- All'AI scelta in Chatbot e Agenti AI (o tramite il Proxy) arriva solo testo anonimizzato; la Glass Window non salva
  nulla. Aggiornamenti solo da https://download.germano.ai/. Tutto il resto avviene al 100% in locale.

## Disinstallazione
Impostazioni › App › App installate › Germano AI, a scelta conservando le cartelle di lavoro e il Vault. Chiede i
permessi di amministratore per togliere la regola del firewall; rimuove programma, collegamenti, voce in Impostazioni ›
App e file tecnici.

## Windows Server e macchine virtuali
- Supportati **Windows Server 2019, 2022 e 2025** (Standard e Datacenter) e le macchine virtuali **VMware, Hyper-V,
  Proxmox VE (KVM), VirtualBox** e cloud: nessuna GPU e nessun ridistribuibile (le DLL di Visual C++ sono incluse).
  Consigliati 12 GB di RAM e 4 vCPU; thread e precisione si adattano da soli (dettagli nella Guida, capitolo 9).
- **Senza finestra** (server, Server Core, avvio automatico con un'attività pianificata):
  `Germano.exe --no-browser --mode=server`; per arrestarlo `Germano.exe --stop`. Gli indirizzi locali e di rete sono
  nel registro `%LOCALAPPDATA%\Germano AI\desktop.log`. Su Windows Server 2019, che non ha Microsoft Edge, Germano
  propone da solo di restare attivo così.
- **Rete**: la regola del firewall vale per le reti private e di dominio. Se una scheda è «Pubblica», se la regola
  manca o se i criteri di gruppo ignorano le regole locali, la Dashboard del server lo dice con il comando per
  correggerlo; nelle VM con NAT serve l'inoltro della porta TCP 8181 (o una scheda in modalità bridge).

## Client leggero per i colleghi
Per i notebook che si collegano a questo PC c'è l'installer separato **`germano-client-0.90.exe`** (circa 22 MB, senza
modelli, nessun permesso di amministratore): anche lì il programma si chiama **`Germano.exe`** e apre il pannello del
client (collegamento **Germano AI Client**), che è lo stesso Remote Control del browser, con Chatbot e Agenti AI e Glass
Window. Chi non vuole installare nulla apre direttamente nel browser `http://<IP-di-questo-PC>:8181/`.

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti (pubblicabili su GitHub). Il runtime Windows con le DLL di Visual C++ e
`vc_redist.x64.exe` sono in `dipendenze\windows`, i modelli in `modelli`; l'installer si costruisce con
`build\costruisci_installer_windows.py` (nella stessa cartella `costruisci_deb.py` e `costruisci_pkg.py` costruiscono
i pacchetti per Linux e macOS, dopo il controllo `coerenza_sorgenti.py`, e `crea_version_json.py` scrive l'indice
per download.germano.ai). Esecuzione dai sorgenti: `pip install -r requirements.txt`, poi `python germano_desktop.py`.
