# Germano AI 0.60 — Client leggero per Windows

Installer leggero (~22 MB, **senza modelli IA**) per i PC che si collegano a un **Germano Server** della rete (la suite
completa installata sul PC più potente dell'ufficio, in modalità Server).

## Installazione
Scarica **`germano-client-0.60.exe`** da https://download.germano.ai/ e fai doppio clic: contiene il proprio Python e
non scarica nulla. Si installa per l'utente corrente in `%LOCALAPPDATA%\Programs\Germano AI Client`, **senza diritti di
amministratore**, con i collegamenti **Germano AI Client** sul Desktop e nel menu Start; alla fine il client si apre da
solo. Le impostazioni del client (server, sessione e opzioni) sono in `%LOCALAPPDATA%\Germano AI Client`.
Disinstallazione: Impostazioni › App › App installate › Germano AI Client.

## Come si usa (plug & play)
1. Apri **Germano AI Client** dal Desktop o dal menu Start: si apre il **pannello del client** in una finestra dedicata
   (niente console, niente browser con l'indirizzo). È lo stesso **Remote Control** che il server offre a qualsiasi
   browser della rete (`http://<IP-del-server>:8181/`): chi non installa il client può usare direttamente il browser.
2. **Germano Server**: lascia vuoto l'indirizzo e premi «Cerca in rete», oppure scrivi l'indirizzo del server (es.
   `192.168.1.10`) e premi «Salva». Di base l'accesso è libero; se sul server la **gestione utenti** è attiva, accedi
   con l'utente e la password impostati dall'amministratore (il client conserva solo la sessione, mai la password).
3. Usa le schede:
   - **AI** — le AI del server rilevate automaticamente: le CLI condivise, i servizi via API filtrati da Germano (Meta
     Muse, Kimi, DeepSeek, Qwen, Mistral, Grok, Perplexity, Gemini, OpenAI, Anthropic...) e i modelli locali del server;
   - **Chat** — prompt e fino a 12 allegati, anonimizzati dal server prima di uscire; la risposta torna con i tuoi dati;
   - **Proteggi** — il testo protetto da usare in qualsiasi AI, e il ripristino della risposta;
   - **Opzioni** — soglia, modelli, le 18 categorie e il mascheramento per le richieste di questo PC (in grigio e non
     modificabili se il server usa il profilo PA);
   - **Collega** — gli indirizzi del Proxy del server per le CLI e gli SDK di questo PC.
4. Per chiudere tutto: la **X rossa**.

Prima di inviare qualsiasi dato il client verifica, **senza inviare dati personali**, che risponda un vero Germano
Server, che l'accesso sia consentito e che il motore sia pronto; altrimenti non invia nulla.

## Riga di comando (facoltativa)
Per automazioni e script si usa il Python incluso, ad esempio:
`"%LOCALAPPDATA%\Programs\Germano AI Client\runtime\python.exe" client.py status` (dalla cartella del programma;
anche `login --user mario`, `models`, `ask claude-code "..."`, `ask deepseek "..." --model deepseek-chat --key ...`,
`options` o il lancio di agenti locali protetti dal server). Dettagli in `README.md`.

## Requisiti
- Windows 10/11 a 64 bit, Microsoft Edge (di serie) per la finestra dedicata.
- Un Germano Server v0.60 o successivo attivo in modalità Server sulla stessa rete locale (il pannello usa il Remote
  Control del server, che non esiste nelle versioni precedenti).

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti; il runtime del client è in `dipendenze\windows\runtime-germano-client` e
l'installer si costruisce con `sorgenti\windows\germano\build\costruisci_installer_windows.py client`.
