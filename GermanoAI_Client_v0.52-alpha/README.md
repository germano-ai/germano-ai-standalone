# Germano Client v0.52-alpha

👉 *Read this in other languages: [English](README.en.md)*

**Germano Client** è il compagno leggero (~28 MB) di **Germano Server**. Non richiede modelli di intelligenza artificiale pesanti in locale: il calcolo inferenziale viene delegato interamente al Server Germano presente sulla rete locale (LAN).

Il Client svolge tre compiti fondamentali:
1. **Esposizione dei Modelli del Server**: rileva ed elenca all'utente tutti i modelli e le AI/CLI installate ed esposte dal Germano Server (es. Claude Code, Google Antigravity, OpenAI Codex, Aider, Qwen, DeepSeek). Permette di interrogarle ed eseguirle direttamente dal client anche se non sono installate su questa macchina.
2. **Instradamento Trasparente delle CLI Locali**: per le AI installate localmente su questo PC, imposta le variabili d'ambiente (`ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`) per instradarle in modo sicuro attraverso il Proxy di Privacy del Server con autenticazione Bearer Token.
3. **Anonimizzazione Rapida e File Transfer**: protegge al volo testi e documenti prima della trasmissione, garantendo la totale privacy del dato.

## Come funziona

```
  [ Postazione Client: Claude / Antigravity / Codex / Aider / Qwen ]
                │  ANTHROPIC_BASE_URL / OPENAI_BASE_URL (con Token Bearer)
                ▼
  [ GERMANO SERVER sulla LAN :8181 ]  (la macchina con i 6 modelli locali)
     1. Riceve le richieste e applica i modelli di privacy locali
     2. Anonimizza prompt e documenti (sostituzione PII con token [PERSONA_1], ecc.)
     3. Registra i mapping nel Vault protetto
     4. Inoltra all'LLM di destinazione solo il contenuto cifrato/anonimizzato
     5. Ripristina i dati reali nella risposta e la restituisce in chiaro al Client
```

- **Due modalità operative principali:**
  - `launch`: avvia su **questo** PC una CLI o agente AI installato in locale, configurando automaticamente il routing verso il Proxy del Server.
  - `ask`: interroga ed esegue direttamente un'AI o modello installato sul **server** (eseguito dal server e protetto dal suo proxy), ideale quando la macchina client non dispone dell'ambiente o delle dipendenze necessarie.
  - `models`: interroga il Server Germano e mostra la lista completa delle AI, dei modelli e delle CLI disponibili sulla macchina server.

## Requisiti
- Windows 10/11 a 64 bit. Nessuna installazione complessa né privilegi di amministratore richiesti: il Client include un runtime Python autonomo e compatto.
- Un'istanza attiva di **Germano Server** raggiungibile sulla stessa rete locale (LAN) avviata tramite `START.bat`.

## Avvio rapido
1. Fai doppio clic su **`START.bat`**: il client esegue un pre-flight check e apre il menu interattivo.
2. **1) Cerca il server sulla rete**: individua automaticamente il Server Germano tramite broadcast UDP (porta 8182).
3. **5) Imposta server e token**: specifica l'indirizzo del server (es. `http://192.168.1.10:8181`) e il token di autorizzazione visualizzato sulla dashboard del Server.
4. **2) Stato della connessione**: verifica che il collegamento sia attivo e il motore pronto.
5. **3) AI e modelli del server**: visualizza i modelli installati sul server pronti per l'uso.
6. **4) Chiedi a un'AI del server**: esegue prompt e task delegando l'esecuzione al server.
7. **5) Avvia una CLI protetta**: avvia strumenti locali (Claude, Codex, Aider) instradati su Germano.
8. **6) Proteggi un testo o file**: invia documenti per l'anonimizzazione istantanea.

## Riga di comando
```bash
START.bat discover                          # Cerca i server Germano attivi sulla LAN (UDP 8182)
START.bat status                            # Verifica connessione, token e stato del motore
START.bat config --server 192.168.1.10 --token ABC123   # Configura indirizzo server e token
START.bat models                            # Elenca le AI e i modelli installati sul SERVER
START.bat ask claude-code "Riassumi: ..."   # Esegue la query su un'AI installata sul SERVER
START.bat launch claude-code                # Avvia Claude Code locale instradato sul Server
START.bat launch antigravity                # Avvia Google Antigravity instradato sul Server
START.bat launch codex --dry-run            # Mostra le variabili d'ambiente senza avviare
START.bat send "Lettera per Mario Rossi" doc.docx  # Anonimizza testo e file
```

## Compatibilità CLI e Agenti AI

| Strumento | Modalità di Instradamento | Stato |
|---|---|---|
| **Claude Code** (`claude-code`) | `ANTHROPIC_BASE_URL` + Header `X-Germano-Auth` | Supportato e collaudato |
| **Google Antigravity** | `OPENAI_BASE_URL` su endpoint proxy locale | Supportato e collaudato |
| **OpenAI Codex** (`codex`) | `OPENAI_BASE_URL` | Supportato nativamente |
| **Aider** (`aider`) | `OPENAI_API_BASE` / `OPENAI_BASE_URL` | Supportato nativamente |
| **Qwen Code** (`qwen`) | `OPENAI_BASE_URL` con inoltro provider | Supportato |
| **Kimi Code CLI** (`kimi`) | Variabili d'ambiente e parametri CLI | Supportato |
| **DeepSeek** (`deepseek`) | Compatibilità OpenAI / Anthropic proxy | Supportato |

## Sicurezza e Pre-flight Check
Prima di trasmettere qualsiasi informazione, il Client verifica:
- La raggiungibilità autentica del Server Germano e la validità del Bearer Token.
- Lo stato di prontezza del motore di anonimizzazione locale.
- Se il server non è raggiungibile o non è pronto, **nessun dato viene trasmesso** e i documenti restano protetti sul client.

## Configurazione manuale (`client_config.json`)
```json
{
  "server_url": "http://192.168.1.10:8181",
  "token": "il-tuo-token-server",
  "discovery_port": 8182
}
```

## Risoluzione Problemi
- **Nessun server trovato**: assicurati che Germano Server sia avviato con `START.bat` sulla stessa subnet LAN e che il firewall consenta il traffico su porta 8181 (TCP) e 8182 (UDP).
- **Token errato o mancante**: copia il token mostrato nella console del server o nelle Impostazioni (*Accesso dalla rete*).
- **Motore non pronto**: il server sta caricando i modelli IA in memoria; attendi qualche istante e ripeti con `START.bat status`.
