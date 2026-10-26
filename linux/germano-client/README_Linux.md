# Germano AI 0.60 — Client leggero per Linux

Pacchetto leggero (**senza modelli IA**) per i PC Linux che si collegano a un **Germano Server** della rete: apre il
**pannello del client** in una finestra dedicata, lo stesso **Remote Control** che il server offre a qualsiasi browser
della rete (AI del server, chat protetta con allegati, proteggi e ripristina, opzioni, collegamento delle CLI), più la
ricerca del server in rete. Accesso libero oppure, se il server lo richiede, con utente e password.

## Installazione
Scarica **`germano-client-0.60.deb`** da https://download.germano.ai/ (pensato per **Ubuntu 26.04 LTS**; adatto alle
distribuzioni Debian/Ubuntu a 64 bit con glibc 2.34 o successiva) e fai doppio clic (Centro app), oppure:

```bash
sudo apt install ./germano-client-0.60.deb
```

Contiene il proprio Python e Qt WebEngine per la finestra, **non dipende da altri pacchetti** e non scarica nulla;
chiede la password di amministratore come ogni pacchetto di sistema. Installa il programma in `/opt/germano-client`,
la voce **Germano AI Client** nel menu delle applicazioni e il comando `germano-ai-client`; le impostazioni (server,
sessione e opzioni) sono in `~/.local/state/germano-client`.

## Avvio
- Dal menu delle applicazioni: pannello del client in finestra dedicata, **nessun terminale**.
- La **X rossa** chiude tutto.
- Riga di comando (facoltativa): `cd /opt/germano-client && runtime/bin/python3 client.py status | login --user <nome> | models | ask <ai> "..." | options | send "..."`.

## Disinstallazione

```bash
sudo apt remove germano-ai-client
```

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti (`germano.sh`, `germano_window.py`, `icons/`, `Germano.desktop` e il
client). Il pacchetto si costruisce con `sorgenti/windows/germano/build/costruisci_deb.py germano-client`.
