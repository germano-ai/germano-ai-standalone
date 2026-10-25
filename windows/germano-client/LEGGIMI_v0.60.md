# Germano AI 0.60 — Client leggero per Windows

Installer leggero (~22 MB, **senza modelli IA**) per i PC che si collegano a un **Germano Server** della rete (la suite
completa installata sul PC più potente dell'ufficio, in modalità Server).

## Installazione
Scarica **`germano-client-0.60.exe`** da https://download.germano.ai/ e fai doppio clic: contiene il proprio Python e
non scarica nulla. Si installa per l'utente corrente in `%LOCALAPPDATA%\Programs\Germano AI Client`, **senza diritti di
amministratore**, con i collegamenti **Germano AI Client** sul Desktop e nel menu Start; alla fine il client si apre da
solo. Le impostazioni del client (server e token) sono in `%LOCALAPPDATA%\Germano AI Client`. Disinstallazione:
Impostazioni › App › App installate › Germano AI Client.

## Come si usa (plug & play)
1. Apri **Germano AI Client** dal Desktop o dal menu Start: si apre il **pannello del client** in una finestra dedicata
   (niente console, niente browser con l'indirizzo).
2. **Server Germano**: lascia vuoto l'indirizzo e premi «Cerca in rete», oppure scrivi l'indirizzo del server (es.
   `192.168.1.10`) e il **token** che il server mostra nelle sue Impostazioni › Accesso dalla rete; poi «Salva».
3. Usa le funzioni:
   - **AI del server** — elenca le AI installate sul server e quali puoi usare da qui;
   - **Chiedi a un'AI del server** — la richiesta viene eseguita sul server e anonimizzata prima di uscire;
   - **Proteggi un testo o dei file** — ricevi il testo protetto (etichette al posto dei dati personali).
4. Per chiudere tutto: la **X rossa**.

Prima di inviare qualsiasi dato il client verifica, **senza inviare dati personali**, che risponda un vero Germano
Server, che il token sia valido e che il motore sia pronto; altrimenti non invia nulla.

## Riga di comando (facoltativa)
Per automazioni e script si usa il Python incluso, ad esempio:
`"%LOCALAPPDATA%\Programs\Germano AI Client\runtime\python.exe" client.py status` (dalla cartella del programma;
anche `models`, `ask claude-code "..."` o il lancio di agenti locali protetti dal server). Dettagli in `README.md`.

## Requisiti
- Windows 10/11 a 64 bit, Microsoft Edge (di serie) per la finestra dedicata.
- Un Germano Server (v0.52 / v0.60 o successivi) attivo in modalità Server sulla stessa rete locale.

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti; il runtime del client è in `dipendenze\windows\runtime-germano-client` e
l'installer si costruisce con `sorgenti\windows\germano\build\costruisci_installer_windows.py client`.
