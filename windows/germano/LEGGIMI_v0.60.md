# Germano AI 0.60 — Suite completa per Windows

## Installazione
Scarica **`germano-0.60.exe`** da https://download.germano.ai/ e fai doppio clic: è un solo file con tutto il
necessario (programma, Python 3.11 con le librerie e le DLL di Microsoft Visual C++, i 6 modelli IA). Si installa per
l'utente corrente in `%LOCALAPPDATA%\Programs\Germano AI`, **senza diritti di amministratore e senza scaricare nulla**,
e crea i collegamenti sul Desktop e nel menu Start, la voce in Impostazioni › App e le cartelle di lavoro in
`Documenti\Germano AI`. L'installer non ha ancora una firma digitale: se compare «Windows ha protetto il PC» scegli
**Ulteriori informazioni › Esegui comunque**.

## Come si usa (plug & play)
Apri **Germano AI** dal Desktop o dal menu Start: è l'**unico** programma (`Germano.exe`). Si apre una **finestra
applicativa dedicata** (niente finestra nera del terminale, niente browser con barra degli indirizzi o schede) con la
**Dashboard unificata**, che contiene tutte le funzionalità:

- **Standalone** (predefinita): tutto offline su questo computer;
- **Server LAN**: offre motore, Proxy e AI condivise agli altri PC dell'ufficio (con token);
- **Client**: affida il calcolo a un Germano Server della rete (Vault e file restano qui).

La modalità si sceglie e si cambia in qualsiasi momento dalle **Impostazioni** della finestra. Per chiudere **tutto**
basta la **X rossa**: si fermano anche il server Flask e il motore IA, senza lasciare processi in memoria.

## Dati e privacy
- Cartelle di lavoro in `Documenti\Germano AI`: `input`, `output`, `processed`, `failed`, `extracted` (se Documenti è
  sincronizzata con OneDrive, in `%USERPROFILE%\Germano AI`).
- Il **Vault** (la tabella etichette ↔ dati originali che permette il ripristino) è `extracted\deanonymize_vault.json`:
  è un file locale **non cifrato**, da proteggere come i documenti originali.
- Impostazioni in `Documenti\Germano AI\config.json`; file tecnici (finestra, registri, aggiornamenti scaricati) in
  `%LOCALAPPDATA%\Germano AI`.
- Aggiornamenti solo da https://download.germano.ai/ (version.json), e solo quando Windows segnala la connessione a
  Internet. Tutto il resto avviene al 100% in locale.

## Disinstallazione
Impostazioni › App › App installate › Germano AI, a scelta conservando le cartelle di lavoro e il Vault.

## Client leggero per i colleghi
Per i notebook che si collegano a questo PC c'è l'installer separato **`germano-client-0.60.exe`** (~22 MB, senza
modelli): anche lì il programma si chiama **`Germano.exe`** e apre il pannello del client.

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti (pubblicabili su GitHub). Il runtime Windows con le DLL di Visual C++ e
`vc_redist.x64.exe` sono in `dipendenze\windows`, i modelli in `modelli`; l'installer si costruisce con
`build\costruisci_installer_windows.py` (nella stessa cartella `costruisci_deb.py` e `costruisci_pkg.py` costruiscono
i pacchetti per Linux e macOS). Esecuzione dai sorgenti: `pip install -r requirements.txt`, poi
`python germano_desktop.py`.
