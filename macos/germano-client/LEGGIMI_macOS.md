# Germano AI 0.90 — Client leggero per macOS

Pacchetto leggero (**senza modelli IA**) per i Mac che si collegano a un **Germano Server** della rete: apre il
**pannello del client** in una finestra dedicata, lo stesso **Remote Control** che il server offre a qualsiasi browser
della rete: **Chatbot e Agenti AI** con il selettore del modello in basso a destra (AI del server) e la **Glass Window**
per vedere e interrompere in tempo reale ciò che viene inviato, **sanitizzazione manuale** di file e testi (anche audio
e archivi compressi), impostazioni e guida, più la ricerca del server in rete e gli aggiornamenti silenziosi. Accesso
libero oppure, se il server lo richiede, con utente e password. Con un Germano Server 0.90 le richieste del client
passano nella corsia preferenziale del server, davanti ai documenti in coda.

## Installazione
Scarica **`germano-client-0.90.pkg`** da https://download.germano.ai/ (Apple Silicon e Intel, macOS 11 o successivo) e
fai doppio clic: contiene il proprio Python e non scarica nulla. Alla scelta della destinazione seleziona **Installa
solo per me**: l'app va in `~/Applications/Germano AI Client/Germano.app` **senza password di amministratore** (con
«Installa per tutti gli utenti» in `/Applications/Germano AI Client`, con la password); alla fine il client si apre da
solo. Le impostazioni (server, sessione e opzioni) sono in `~/Library/Application Support/Germano AI Client`. Se macOS
blocca il pacchetto, non ancora firmato da Apple: **Impostazioni di Sistema › Privacy e sicurezza › Apri comunque**.

## Avvio
- Apri **Germano** da Launchpad o dalla cartella Applicazioni › Germano AI Client: pannello del client in finestra
  dedicata (WebKit di sistema), senza terminale.
- La **X rossa** (o ⌘Q) chiude tutto.
- Aggiornamenti silenziosi: il nuovo `germano-client-<versione>.pkg` si scarica in background e si apre quando
  vuoi (Impostazioni › Aggiornamenti); server e sessione restano com'erano.
- Riga di comando (facoltativa), dalla cartella `Germano.app/Contents/Resources/app`:
  `runtime/bin/python3 client.py status | login --user <nome> | models | ask <ai> "..." | options | send "..."` (sui Mac
  Intel `runtime-x86_64/bin/python3`).

## Disinstallazione
Trascina la cartella `Germano AI Client` nel Cestino.

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti (`Germano.app` con Info.plist, lanciatore e icona, e il client). Il pacchetto
si costruisce con `sorgenti/windows/germano/build/costruisci_pkg.py germano-client`, che aggiunge il Python per Apple
Silicon e per Intel con le librerie di `dipendenze/macos`.
