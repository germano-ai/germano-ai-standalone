# Germano AI 0.90 — Client leggero per Linux

Pacchetto leggero (**senza modelli IA**) per i PC Linux che si collegano a un **Germano Server** della rete: apre il
**pannello del client** in una finestra dedicata, lo stesso **Remote Control** che il server offre a qualsiasi browser
della rete: **Chatbot e Agenti AI** con il selettore del modello in basso a destra (AI del server) e la **Glass Window**
per vedere e interrompere in tempo reale ciò che viene inviato, **sanitizzazione manuale** di file e testi (anche audio
e archivi compressi), impostazioni e guida, più la ricerca del server in rete e gli aggiornamenti silenziosi. Accesso
libero oppure, se il server lo richiede, con utente e password. Con un Germano Server 0.90 le richieste del client
passano nella corsia preferenziale del server, davanti ai documenti in coda.

## Installazione
Scarica **`germano-client-0.90.deb`** da https://download.germano.ai/ (pensato per **Ubuntu 26.04 LTS**; adatto alle
distribuzioni Debian/Ubuntu a 64 bit con glibc 2.34 o successiva) e fai doppio clic (Centro app), oppure:

```bash
sudo apt install ./germano-client-0.90.deb
```

Contiene il proprio Python e Qt WebEngine per la finestra, **non dipende da altri pacchetti** e non scarica nulla;
chiede la password di amministratore come ogni pacchetto di sistema. Installa il programma in `/opt/germano-client`,
la voce **Germano AI Client** nel menu delle applicazioni e il comando `germano-ai-client`; le impostazioni (server,
sessione e opzioni) sono in `~/.local/state/germano-client`.

## Avvio
- Dal menu delle applicazioni: pannello del client in finestra dedicata, **nessun terminale**.
- La **X rossa** chiude tutto.
- Aggiornamenti silenziosi: il nuovo `germano-client-<versione>.deb` si scarica in background e si apre quando
  vuoi (Impostazioni › Aggiornamenti); server e sessione restano com'erano.
- Riga di comando (facoltativa): `cd /opt/germano-client && runtime/bin/python3 client.py status | login --user <nome> | models | ask <ai> "..." | options | send "..."`.

## Disinstallazione

```bash
sudo apt remove germano-ai-client
```

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti (`germano.sh`, `germano_window.py`, `icons/`, `Germano.desktop` e il
client). Il pacchetto si costruisce con `sorgenti/windows/germano/build/costruisci_deb.py germano-client`.
