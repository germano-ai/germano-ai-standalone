# Changelog

Tutte le modifiche a questo progetto saranno documentate in questo file.
Il formato è basato su [Keep a Changelog](https://keepachangelog.com/it-IT/1.0.0/).

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
