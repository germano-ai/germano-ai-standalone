# Germano AI 0.95 — Client leggero per Windows

Installer leggero (circa 22 MB, **senza modelli IA**) per i PC che si collegano a un **Germano Server** della rete (la
suite completa installata sul PC più potente dell'ufficio, in modalità Server).

## Installazione
Scarica **`germano-client-0.95.exe`** da https://download.germano.ai/ e fai doppio clic: contiene il proprio Python e
non scarica nulla. Si installa per l'utente corrente in `%LOCALAPPDATA%\Programs\Germano AI Client`, **senza diritti di
amministratore**, con i collegamenti **Germano AI Client** sul Desktop e nel menu Start; alla fine il client si apre da
solo. Le impostazioni del client (server, sessione e opzioni) sono in `%LOCALAPPDATA%\Germano AI Client`.
Disinstallazione: Impostazioni › App › App installate › Germano AI Client.

## Come si usa (plug & play)
1. Apri **Germano AI Client** dal Desktop o dal menu Start: si apre il **pannello del client** in una finestra dedicata
   (niente console, niente browser con l'indirizzo). È lo stesso **Remote Control** che il server offre a qualsiasi
   browser della rete (`http://<IP-del-server>:8181/`): chi non installa il client può usare direttamente il browser.
2. **Germano Server**: se il server non risponde compare la pagina di collegamento; lascia vuoto l'indirizzo e premi
   «Cerca in rete», oppure scrivi l'indirizzo del server (es. `192.168.1.10`) e premi «Collega» (si cambia poi in
   Impostazioni › Server). Di base l'accesso è libero; se sul server la **gestione utenti** è attiva, accedi con l'utente
   e la password impostati dall'amministratore (il client conserva solo la sessione, mai la password).
3. Usa le schede:
   - **Chatbot e Agenti AI** — scrivi alla tua AI e scegli il modello **in basso a destra** tra le AI del server
     rilevate automaticamente (CLI condivise, servizi via API filtrati da Germano come Meta Muse, Kimi, DeepSeek, Qwen
     (anche Qwen 4 Max), GLM 5.3, Mistral, Grok, Perplexity, Gemini, OpenAI, Anthropic, e i modelli locali del
     server); le altre restano in grigio e
     l'elenco si aggiorna da solo. Messaggio e fino a 12 allegati (anche audio e archivi compressi) vengono anonimizzati
     dal server prima di uscire; la risposta arriva in streaming con i tuoi dati. Il pulsante **Glass Window** mostra in
     tempo reale tutto ciò che il server comunica al modello, comprese le decisioni del Sistema 2, e **Interrompi
     operazione** lo ferma;
   - **Sanitizzazione manuale** — trascina file da anonimizzare (restano nel loro formato), ripristina i file
     restituiti da un'AI, proteggi un testo e ripristina la risposta;
   - **Impostazioni** — AI e chiavi, opzioni di elaborazione di questo PC (soglia, modelli, le 18 categorie e il
     mascheramento: in grigio e non modificabili se il server usa il profilo PA), indirizzi del Proxy del server per
     le CLI e gli SDK di questo PC, indirizzo del server e aggiornamenti;
   - **Guida** — il manuale completo, anche senza Internet.
4. Per chiudere tutto: la **X rossa**.

Prima di inviare qualsiasi dato il client verifica, **senza inviare dati personali**, che risponda un vero Germano
Server, che l'accesso sia consentito e che il motore sia pronto; altrimenti non invia nulla.

## Novità della 0.95
- **`client mcp`**: un Server MCP stdio su questo PC che inoltra al Server MCP del Germano Server, per usare Germano
  da Claude Desktop, Claude Code, Cursor o Antigravity installati qui. Serve il token delle integrazioni del server
  (Dashboard del server › Impostazioni › Integrazioni MCP e UTCP): `client config --api-token <token>`.
- **`client utcp`**: indirizzi MCP, UTCP e OpenAPI del server e strumenti del manuale UTCP (`--json` per il manuale).
- Pannello allineato a quello del Germano Server 0.95.

## Novità della 0.91
- Pannello allineato a quello del Germano Server 0.91: con un server 0.91 compaiono i nuovi servizi **Qwen Token Plan
  (Qwen4-Max)**, **Qwen Coding Plan**, **GLM (Z.ai)** e **GLM Coding Plan (Z.ai)**, con la tua chiave o, se
  l'amministratore condivide le AI del server, con quella del server.
- L'Assistente di configurazione e Antigravity CLI della suite restano sul computer del server (Antigravity CLI usa
  l'account Google di chi è davanti al server): il client non li mostra e non li esegue. `client launch agy` spiega
  perché la CLI non si può indirizzare al Proxy e indica le alternative (per i modelli Gemini il servizio «Google
  Gemini»).

## Novità della 0.90
- Pannello allineato a quello del Germano Server 0.90 (allegati audio e archivi, Sistema 2 nella Glass Window).
- Con un server 0.90 le richieste del client passano nella **corsia preferenziale**, davanti ai documenti in coda sul
  server, e il server lavora in parallelo; il Proxy del server protegge anche gli argomenti degli strumenti degli
  agenti avviati con `client launch` e blocca la richiesta se un dato rilevato è rimasto in chiaro.

## Aggiornamenti silenziosi (come Google Chrome)
Attivi di default: solo quando Windows segnala la connessione a Internet, il client controlla
https://download.germano.ai/, scarica la nuova versione in background a bassa priorità e la applica al successivo
avvio in pochi secondi, senza finestre. Al massimo compare un discreto **«Riavvia per aggiornare»** in alto. Stato e
opzioni in Impostazioni › Aggiornamenti; l'indirizzo del server e la sessione restano com'erano.

## Riga di comando (facoltativa)
Per automazioni e script si usa il Python incluso, ad esempio:
`"%LOCALAPPDATA%\Programs\Germano AI Client\runtime\python.exe" client.py status` (dalla cartella del programma;
anche `login --user mario`, `models`, `ask claude-code "..."`, `ask deepseek "..." --model deepseek-chat --key ...`,
`options`, `utcp`, `mcp` o il lancio di agenti locali protetti dal server). Dettagli in `README.md`.

## Requisiti
- Windows 10/11 o Windows Server 2019 o successivo a 64 bit (anche in macchina virtuale), Microsoft Edge per la
  finestra dedicata (di serie su Windows 10/11; su Windows Server 2019 va installato, altrimenti il client indica
  l'indirizzo del pannello e si può usare la riga di comando).
- Un Germano Server attivo in modalità Server sulla stessa rete locale, versione 0.70 o successiva (consigliata la
  0.95): Chatbot e Agenti AI e la sanitizzazione dei file del pannello usano API del server introdotte con la 0.70; con
  un server 0.60 resta utilizzabile la riga di comando (`client ask`, `client send`, `client launch`).

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti; il runtime del client è in `dipendenze\windows\runtime-germano-client` e
l'installer si costruisce con `sorgenti\windows\germano\build\costruisci_installer_windows.py client`.
