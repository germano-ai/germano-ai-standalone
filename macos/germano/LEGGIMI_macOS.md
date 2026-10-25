# Germano AI 0.60 — Suite completa per macOS

## Installazione
Scarica **`germano-0.60.pkg`** da https://download.germano.ai/ (Mac con **Apple Silicon**, M1 o successivo, e
**macOS 14 Sonoma** o successivo: PyTorch non è più pubblicato per i Mac Intel, che usano il client leggero) e fai
doppio clic. Il pacchetto contiene tutto (programma, Python 3.11 con le librerie, i 6 modelli IA) e non scarica nulla.
Alla scelta della destinazione seleziona **Installa solo per me**: `Germano.app` va in `~/Applications` **senza
password di amministratore** (con «Installa per tutti gli utenti» va in `/Applications` e macOS chiede la password).
Il pacchetto non è ancora firmato da Apple: se macOS ne blocca l'apertura, vai in **Impostazioni di Sistema › Privacy e
sicurezza** e scegli **Apri comunque**.

## Come si usa
Apri **Germano** da Launchpad o dalla cartella Applicazioni: si apre una **finestra dedicata** (WebKit di sistema,
niente terminale né browser) con la **Dashboard unificata** (Standalone, Server LAN, Client). La **X rossa** (o ⌘Q)
chiude tutto: finestra, server e motore IA.

## Dati e privacy
- Cartelle di lavoro in `~/Documents/Germano AI` (in `~/Germano AI` se Documenti è sincronizzata con iCloud): `input`,
  `output`, `processed`, `failed`, `extracted`.
- Il **Vault** è `extracted/deanonymize_vault.json`: file locale **non cifrato**, da proteggere come i documenti
  originali.
- File tecnici in `~/Library/Application Support/Germano AI`.
- Aggiornamenti: dalla Dashboard; il nuovo `germano-<versione>.pkg` si scarica da https://download.germano.ai/ e si
  apre con un doppio clic (cartelle di lavoro, Vault e impostazioni restano intatti).

## Disinstallazione
Trascina `Germano.app` nel Cestino; le cartelle di lavoro restano dove sono.

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti: `Germano.app` (Info.plist, lanciatore `Contents/MacOS/Germano`, icona) e il
programma (stessi `server.py`, `germano_desktop.py`, `germano/` di Windows; `germano_window.py` apre la finestra con
pywebview). Il pacchetto si costruisce, anche da Windows, con `sorgenti/windows/germano/build/costruisci_pkg.py`, che
mette in `Germano.app/Contents/Resources/app` il programma, il Python per macOS con le librerie di `dipendenze/macos` e
i modelli di `modelli/`. Esecuzione dai sorgenti: `pip install -r requirements.txt`, poi `python3 germano_desktop.py`.
