# Germano AI 0.60 — Suite completa per Windows

## Installazione
Scarica **`germano-0.60.exe`** da https://download.germano.ai/ e fai doppio clic: è un solo file con tutto il
necessario (programma, Python 3.11 con le librerie e le DLL di Microsoft Visual C++, i 6 modelli IA) e non scarica
nulla. **Appena si apre chiede i permessi di amministratore** (richiesta UAC di Windows: scegli **Sì**): servono a
consentire l'accesso dalla rete locale, sempre attivo, con una regola del firewall di Windows solo per il Python di
Germano e solo per le reti private e di dominio. Si installa per l'utente corrente in
`%LOCALAPPDATA%\Programs\Germano AI` e crea i collegamenti sul Desktop e nel menu Start, la voce in Impostazioni › App e
le cartelle di lavoro in `Documenti\Germano AI`; alla fine la finestra dell'installer si chiude e **Germano si apre da
solo**, senza pagine di istruzioni. L'installer non ha ancora una firma digitale: se compare «Windows ha protetto il PC»
scegli **Ulteriori informazioni › Esegui comunque**.

## Come si usa (plug & play)
Apri **Germano AI** dal Desktop o dal menu Start: è l'**unico** programma (`Germano.exe`). Si apre una **finestra
applicativa dedicata** (niente finestra nera del terminale, niente browser con barra degli indirizzi o schede) con la
**Dashboard unificata**, che contiene tutte le funzionalità:

- **Standalone** (predefinita): tutto offline su questo computer;
- **Server LAN**: offre motore, Proxy, AI condivise e il **Remote Control** (da qualsiasi browser della rete:
  `http://<IP-del-server>:8181/`, senza installare nulla) agli altri PC e dispositivi dell'ufficio; accesso libero di
  base, oppure con utente e password (Impostazioni › Accesso dalla rete › Gestione utenti);
- **Client**: affida il calcolo a un Germano Server della rete (Vault e file restano qui).

La modalità si sceglie e si cambia in qualsiasi momento dalle **Impostazioni** della finestra. Per chiudere **tutto**
basta la **X rossa**: si fermano anche il server Flask e il motore IA, senza lasciare processi in memoria.

Nella sezione **Cartelle di lavoro** quattro riquadri (`input`, `output`, `processed`, `failed`) mostrano, come un file
manager, i file che entrano, vengono elaborati e si spostano, in tempo reale; sopra ogni riquadro c'è il percorso
completo della cartella e un clic la apre in Esplora file. Per anonimizzare dei documenti trascinali sul riquadro
**input** («Trascina i file qui nella cartella di input»).

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
Impostazioni › App › App installate › Germano AI, a scelta conservando le cartelle di lavoro e il Vault. Chiede i
permessi di amministratore per togliere la regola del firewall; rimuove programma, collegamenti, voce in Impostazioni ›
App e file tecnici.

## Client leggero per i colleghi
Per i notebook che si collegano a questo PC c'è l'installer separato **`germano-client-0.60.exe`** (~22 MB, senza
modelli, nessun permesso di amministratore): anche lì il programma si chiama **`Germano.exe`** e apre il pannello del
client (collegamento **Germano AI Client**), che è lo stesso Remote Control del browser. Chi non vuole installare nulla
apre direttamente nel browser `http://<IP-di-questo-PC>:8181/`.

## Per gli sviluppatori
Questa cartella contiene solo i sorgenti (pubblicabili su GitHub). Il runtime Windows con le DLL di Visual C++ e
`vc_redist.x64.exe` sono in `dipendenze\windows`, i modelli in `modelli`; l'installer si costruisce con
`build\costruisci_installer_windows.py` (nella stessa cartella `costruisci_deb.py` e `costruisci_pkg.py` costruiscono
i pacchetti per Linux e macOS). Esecuzione dai sorgenti: `pip install -r requirements.txt`, poi
`python germano_desktop.py`.
