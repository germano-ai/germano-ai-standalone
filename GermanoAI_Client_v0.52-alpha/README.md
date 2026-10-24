# Germano Client v0.02

🌍 *Read this in other languages: [English](README.en.md)*

**Germano Client** è il compagno leggero di **Germano Server** (v0.52+). Non contiene modelli di AI: anonimizzazione,
Vault e ripristino dei dati avvengono sul Server. Il Client fa passare dal Proxy del Server le CLI di AI installate su
questo PC e permette di proteggere al volo testi e file.

## Come funziona

```
  [ CLI su questo PC: claude / codex / aider / qwen ]
                │  ANTHROPIC_BASE_URL / OPENAI_BASE_URL  ->  Germano Server (con /g/<token>)
                ▼
  [ GERMANO SERVER sulla LAN :8181 ]          (il PC con i modelli)
     1. anonimizza prompt e file (Vault + modelli locali)
     2. inoltra al servizio di AI configurato sul server solo i dati protetti
     3. rimette i dati veri nella risposta e la rimanda alla CLI
```

- Le CLI girano su **questo** PC: le AI installate solo sul server non si possono avviare da qui.
- **Il servizio di AI lo decide il server.** Il Proxy inoltra le richieste in formato OpenAI al suo «Servizio OpenAI o
  compatibile» e quelle in formato Anthropic al suo «Servizio Anthropic» (Dashboard del server, scheda *Agenti AI e
  API*). Una CLI pensata per un altro fornitore (es. Qwen) funziona solo se il server inoltra a quel fornitore.
- **Dove stanno i dati.** Con il Client il Vault (le corrispondenze etichetta ↔ dato reale) è sul **server**. Tra
  questo PC e il server i testi viaggiano in chiaro sulla rete locale (HTTP): usa il Client solo su una rete fidata.
  Il Client non salva testi né dati personali.

## Requisiti
- Windows 10/11. Nessuna installazione: il Client porta con sé un piccolo runtime Python (cartella `runtime`).
- Un **Germano Server** v0.52 o successivo in modalità **Server** (Impostazioni › Server, oppure `START_SERVER.bat`)
  sulla stessa rete locale. Sul server, quando Windows lo chiede, consenti Python sulle reti private.

## Avvio rapido
1. Doppio clic su **`START.bat`**: si apre il menu e il Client controlla subito il collegamento.
2. **1) Cerca il server sulla rete**: compare l'indirizzo del server (es. `http://192.168.1.10:8181`).
3. **5) Imposta server e token**: indica l'indirizzo e il token che il server mostra nella sua finestra o in
   Impostazioni › *Accesso dalla rete* (mentre lo scrivi il token non viene mostrato).
4. **2) Stato della connessione** deve rispondere «collegamento pronto».
5. **3) Avvia una CLI protetta** (es. `claude-code`) oppure **4) Proteggi un testo o dei file**.

## Riga di comando
```
START.bat discover                          cerca i server sulla rete locale
START.bat status                            server, motore e token: e' tutto pronto?
START.bat config --server 192.168.1.10 --token ABC123
START.bat config --server http://192.168.1.10:8181/g/ABC123/v1     (va bene anche il Base URL della Dashboard)
START.bat launch claude-code                avvia Claude Code protetto, in una nuova finestra
START.bat launch codex --dry-run            mostra cosa verrebbe impostato, senza avviare nulla
START.bat launch codex -- --model gpt-5     tutto cio' che segue -- arriva alla CLI
START.bat send "Scrivi a Mario Rossi" lettera.docx       protegge testo e file e mostra il risultato
```
`--server` e `--token` si possono scrivere prima o dopo il comando e prevalgono su `client_config.json`. Un indirizzo
senza porta usa la 8181. Con `send` si possono allegare fino a 12 file; le immagini non contengono testo da proteggere
qui: per oscurarle usa l'anonimizzazione dei file sul server.

## Quali CLI si possono proteggere

| CLI | Come passa da Germano | Stato |
|---|---|---|
| Claude Code (`claude-code`) | `ANTHROPIC_BASE_URL` + intestazione `X-Germano-Auth` | collaudata (con chiave API) |
| Codex (`codex`) | `OPENAI_BASE_URL` | secondo la documentazione: vale per il fornitore OpenAI predefinito con chiave API; con un altro fornitore nel suo `config.toml` o con l'accesso tramite account ChatGPT il traffico può non passare da Germano |
| Aider (`aider`) | `OPENAI_API_BASE`, `OPENAI_BASE_URL`, `--openai-api-base` | secondo la documentazione: usa i modelli come `openai/<nome>` |
| Qwen Code (`qwen`) | `OPENAI_BASE_URL` | secondo la documentazione: il server deve inoltrare a DashScope (modalità compatibile) |
| Kimi Code CLI (`kimi`) | non legge l'indirizzo dalle variabili d'ambiente | da configurare a mano nel suo `config.toml`, poi `launch kimi --forza` |
| DeepSeek (`deepseek`) | non esiste una CLI ufficiale | usa Claude Code, con il «Servizio Anthropic» del server su `https://api.deepseek.com/anthropic` |
| Gemini CLI (`gemini-cli`) | usa il protocollo Gemini, che il Proxy non gestisce | **non viene avviata**: non sarebbe protetta |
| Antigravity, Cursor, Windsurf, Claude Desktop | applicazioni grafiche | il Client spiega cosa impostare, quando è possibile |

Nell'ambiente della CLI avviata il Client inoltre:
- aggiunge l'indirizzo del server a `NO_PROXY`, così le richieste verso Germano non passano da un proxy aziendale;
- per Claude Code toglie `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX` e `CLAUDE_CODE_USE_FOUNDRY`, che lo
  porterebbero fuori da Germano;
- per Aider toglie le chiavi degli altri fornitori (es. `ANTHROPIC_API_KEY`), con cui uscirebbe direttamente.

La chiave del servizio di AI resta la tua: il server la inoltra soltanto, dopo aver protetto i contenuti.

## A prova di errore
Prima di inviare un testo o di avviare una CLI il Client verifica, **senza inviare dati personali**, che all'indirizzo
risponda davvero un Germano Server, che il token sia valido e (per `send`) che il motore sia pronto. Se qualcosa non
va non invia nulla e spiega il motivo. Se il motore del server si ferma mentre lavori, il server blocca le richieste:
nessun dato esce in chiaro. Il Client si collega al server sempre direttamente, mai attraverso un proxy di sistema.

Codici di uscita: `0` tutto bene, `1` server non raggiungibile o non valido, `2` uso errato, `3` token mancante o
errato, `4` motore del server non pronto, `5` CLI non installata o non proteggibile.

## Configurazione manuale (`client_config.json`)
```json
{
  "server_url": "http://192.168.1.10:8181",
  "token": "il-token-mostrato-dal-server",
  "discovery_port": 8182
}
```
Consiglio: dopo la prima ricerca fissa l'indirizzo con `config --server`. Il rilevamento automatico accetta la
risposta di qualunque computer della rete: fissare l'indirizzo evita di mandare token e testi a un PC sbagliato.

## Problemi frequenti
- **Nessun server trovato**: sul server attiva la modalità Server e consenti Python sulle reti private; oppure indica
  l'indirizzo con `config --server`.
- **Token ERRATO o MANCANTE**: copia il token dalla finestra del server o da Impostazioni › *Accesso dalla rete*. Se
  sul server qualcuno ha generato un «Nuovo token», va aggiornato su tutti i client.
- **Motore NON PRONTO**: il motore del server si sta avviando o è fermo; riprova dopo qualche istante.

Vedi anche la documentazione di **Germano Server** per la configurazione lato server.
