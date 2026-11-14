# Germano AI 0.91 — Suite completa per macOS

## Installazione
Scarica **`germano-0.91.pkg`** da https://download.germano.ai/ (Mac con **Apple Silicon**, M1 o successivo, e
**macOS 14 Sonoma** o successivo: PyTorch non è più pubblicato per i Mac Intel, che usano il client leggero) e fai
doppio clic. Il pacchetto contiene tutto (programma, Python 3.11 con le librerie, gli 8 modelli IA, llama.cpp per il
Sistema 2 e 7-Zip per gli archivi) e non scarica nulla.
Alla scelta della destinazione seleziona **Installa solo per me**: `Germano.app` va in `~/Applications` **senza
password di amministratore** (con «Installa per tutti gli utenti» va in `/Applications` e macOS chiede la password).
Alla fine dell'installazione Germano si apre da solo. Il pacchetto non è ancora firmato da Apple: se macOS ne blocca
l'apertura, vai in **Impostazioni di Sistema › Privacy e sicurezza** e scegli **Apri comunque**.

## Come si usa
Apri **Germano** da Launchpad o dalla cartella Applicazioni: si apre una **finestra dedicata** (WebKit di sistema,
niente terminale né browser). La **X rossa** (o ⌘Q) chiude tutto: finestra, server e motore IA.

- **Chatbot e Agenti AI** (scheda predefinita): scrivi alla tua AI e scegli il modello **in basso a destra** (solo le AI
  rilevate: Claude Code, Antigravity CLI, i modelli di Ollama, LM Studio e Jan, i servizi via API con una chiave;
  accanto alle altre, il pulsante dell'Assistente di configurazione); Germano oscura i dati personali prima
  dell'invio e li rimette nella risposta. La **Glass Window** mostra in tempo reale tutto ciò che viene
  comunicato al modello e **Interrompi operazione** ferma tutto.
- **Sanitizzazione Manuale & Vault**: quattro riquadri (`input`, `output`, `processed`, `failed`) mostrano in tempo
  reale i file di ogni cartella, con il percorso completo sopra: trascina i documenti sul riquadro **input**; un clic su
  un riquadro apre la cartella nel Finder.
- **Impostazioni** (modalità Standalone, Server LAN, Client e tutte le opzioni) e **Guida**.

In modalità **Server** gli altri computer, tablet e smartphone della rete usano dal browser, senza installare nulla, il
**Remote Control** (`http://<IP-di-questo-Mac>:8181/`) con la stessa interfaccia: Chatbot e Agenti AI con le AI di
questo computer filtrate da Germano e la Glass Window, sanitizzazione manuale di file e testi, opzioni (bloccate con il
profilo PA). Di base l'accesso è libero; con la gestione utenti (Impostazioni › Modalità e rete › Accesso dalla rete)
servono utente e password. Alla prima attivazione macOS può chiedere di consentire le connessioni in entrata a Python:
rispondi **Consenti**.

## Novità della 0.91: assistente di configurazione delle AI
Accanto a ogni AI un pulsante dice che cosa manca e lo fa con un clic: **Antigravity CLI** (`agy`, installata in
`~/.local/bin` dal manifesto ufficiale di Google con verifica SHA-512) si usa in Chatbot e Agenti AI con l'account di
Antigravity (Portachiavi di macOS), ricevendo solo il testo già protetto e senza strumenti (le sue istruzioni interne
vanno a Google senza passare dal Proxy, come dichiara la Glass Window; su macOS la sua cartella personale non viene
isolata, perché il Portachiavi la segue); **Qwen 4 Max** e **GLM 5.3** sono nuovi servizi e «Recupera configurazione»
collega senza copiarle le chiavi già impostate in altri strumenti; **Ollama, LM Studio e Jan** mostrano i modelli già
scaricati anche a servizio spento (per installare Ollama su macOS si apre la pagina ufficiale; Qwen Code anche con
Homebrew). Su macOS queste funzioni sono verificate solo staticamente. Dettagli nel CHANGELOG e nella Guida (capitolo 2).

## Novità della 0.90: più veloce e in parallelo
Stessi dati protetti della 0.80, tempi più brevi: Privacy Filter e Italian NER lavorano insieme e ogni modello ha il
proprio lock; le richieste interattive passano davanti ai documenti in coda; il Sistema 2 non fa più domande superflue
(un PDF di 12 pagine passa da 234,6 a 132,0 secondi sul PC di prova); PDF scansionati a finestre di 8 pagine; Vault su
SQLite; audio lungo trascritto a lotti; il Proxy anonimizza anche gli argomenti degli strumenti degli agenti, con un
controllo finale di non-uscita. Il pacchetto `.pkg` 0.90 è costruito da sorgenti identici a quelli Windows in tutti i
file comuni. Dettagli nel CHANGELOG e nella Guida (capitolo 9).

## Dati e privacy
- Cartelle di lavoro in `~/Documents/Germano AI` (in `~/Germano AI` se Documenti è sincronizzata con iCloud): `input`,
  `output`, `processed`, `failed`, `extracted`.
- Il **Vault** è in `extracted`: dalla 0.90 il database `deanonymize_vault.db` (SQLite), con la copia portabile
  `deanonymize_vault.json` nel formato di sempre. È locale e **non cifrato**: proteggilo come i documenti originali.
- File tecnici in `~/Library/Application Support/Germano AI`.
- Aggiornamenti silenziosi (attivi di default): solo quando il sistema segnala la connessione a Internet, Germano
  controlla https://download.germano.ai/ e scarica in background il nuovo `germano-<versione>.pkg`; quando vuoi lo apri
  con il pulsante in alto o in Impostazioni › Aggiornamenti (Installer di macOS). Cartelle di lavoro, Vault e
  impostazioni restano intatti.

## Disinstallazione
Trascina `Germano.app` nel Cestino; le cartelle di lavoro restano dove sono.

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti: `Germano.app` (Info.plist, lanciatore `Contents/MacOS/Germano`, icona) e il
programma (stessi `server.py`, `germano_desktop.py`, `germano/` di Windows; `germano_window.py` apre la finestra con
pywebview). Il pacchetto si costruisce, anche da Windows, con `sorgenti/windows/germano/build/costruisci_pkg.py`, che
prima controlla che i file comuni siano identici a quelli Windows (`coerenza_sorgenti.py`) e poi mette in
`Germano.app/Contents/Resources/app` il programma, il Python per macOS con le librerie di `dipendenze/macos`, llama.cpp,
7-Zip e i modelli di `modelli/`. Esecuzione dai sorgenti: `pip install -r requirements.txt`, poi
`python3 germano_desktop.py`.
