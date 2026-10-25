# Germano AI 0.60 — Suite completa per Linux

## Installazione
Scarica **`germano-0.60.deb`** da https://download.germano.ai/ (pensato per **Ubuntu 26.04 LTS**; adatto alle
distribuzioni Debian/Ubuntu a 64 bit con glibc 2.34 o successiva) e fai doppio clic (Centro app), oppure da terminale:

```bash
sudo apt install ./germano-0.60.deb
```

Il pacchetto contiene tutto (programma, Python 3.11 con le librerie, Qt WebEngine per la finestra, i 6 modelli IA) e
**non dipende da altri pacchetti**: non scarica nulla. Come ogni pacchetto di sistema chiede la password di
amministratore. Installa il programma in `/opt/germano`, la voce **Germano AI** nel menu delle applicazioni (con
l'azione «Cartelle di lavoro») e il comando `germano-ai`.

## Come si usa
Apri **Germano AI** dal menu delle applicazioni: si apre una **finestra dedicata** (niente terminale né browser) con la
**Dashboard unificata** (Standalone, Server LAN, Client). La **X rossa** chiude tutto: finestra, server e motore IA
(nessun processo orfano). Nella sezione **Cartelle di lavoro** quattro riquadri (`input`, `output`, `processed`,
`failed`) mostrano in tempo reale i file di ogni cartella, con il percorso completo sopra: trascina i documenti sul
riquadro **input**; un clic su un riquadro apre la cartella nel file manager.

Il pacchetto `.deb` non apre Germano alla fine dell'installazione: apt e il Centro app installano come amministratore,
fuori dalla sessione grafica dell'utente.

## Dati e privacy
- Cartelle di lavoro in `Documenti/Germano AI` (la cartella Documenti nella lingua del sistema): `input`, `output`,
  `processed`, `failed`, `extracted`.
- Il **Vault** è `extracted/deanonymize_vault.json`: file locale **non cifrato**, da proteggere come i documenti
  originali.
- File tecnici in `~/.local/state/germano`.
- Aggiornamenti: dalla Dashboard; il nuovo `germano-<versione>.deb` si scarica da https://download.germano.ai/ e si
  installa come sopra (cartelle di lavoro, Vault e impostazioni restano intatti).

## Disinstallazione

```bash
sudo apt remove germano-ai
```

Le cartelle di lavoro restano dove sono.

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti: `germano.sh` (lanciatore), `germano_window.py` (finestra con pywebview e Qt
WebEngine), `icons/`, `Germano.desktop` (voce di menu per la copia di sviluppo) e il programma (stessi `server.py`,
`germano_desktop.py`, `germano/` di Windows). Il pacchetto si costruisce, anche da Windows, con
`sorgenti/windows/germano/build/costruisci_deb.py`, che aggiunge il Python per Linux e le librerie di
`dipendenze/linux` (comprese le poche librerie X11 per Qt che Ubuntu 26.04 non installa) e i modelli di `modelli/`.
Esecuzione dai sorgenti:
`pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu`, poi `./germano.sh`.
