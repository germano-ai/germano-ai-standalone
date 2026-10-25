# 🛡️ Germano AI Client

👉 *Read this in other languages: [English](README.en.md)*

**Germano AI Client** è l'applicazione client ultraleggera (~26 MB) progettata per connettere qualsiasi postazione di lavoro (notebook, PC standard) a un **Germano Server** attivo sulla rete locale (LAN).

Non richiede modelli di intelligenza artificiale pesanti né GPU dedicate in locale: tutto il carico computazionale, l'OCR e l'inferenza IA vengono delegati al Server centrale, mentre i documenti originali e il Vault di de-anonimizzazione rimangono saldamente e sovranamente sulla postazione client locale.

---

## ⚡ Caratteristiche Principali

1. **Rilevamento Automatico del Server (Broadcast UDP 8182)**:
   All'avvio, il Client ricerca automaticamente sulla rete locale i Server Germano attivi, stabilendo una connessione istantanea protetta da Bearer Token di sicurezza.
2. **Esposizione delle AI e dei Modelli del Server**:
   Il Client interroga il Server ed elenca tutte le intelligenze artificiali e gli agenti CLI configurati (es. Claude Code, Google Antigravity, OpenAI Codex, Aider, Qwen, DeepSeek). Permette di interrogarli ed eseguirli direttamente dalla propria postazione, anche se non sono installati localmente.
3. **Instradamento Trasparente per Agenti AI Locali**:
   Per gli agenti installati localmente, configura automaticamente le variabili d'ambiente (`ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`) reindirizzando il traffico verso il Proxy di Privacy del Server con de-anonimizzazione trasparente al ritorno.
4. **Protezione dei Documenti e dei File**:
   Tratta file e testi al volo prima della trasmissione: il server riceve unicamente dati con placeholder anonimizzati (`[PERSONA_1]`, `[COD.FISCALE_1]`, ecc.), garantendo la piena conformità GDPR e CAD.
5. **Nuova Interfaccia Applicativa Dedicata**:
   Disponibile sia in finestra grafica dedicata (senza barre di navigazione generiche né console nera) sia tramite interfaccia a riga di comando (`client.py`) per automazioni e script.

---

## 🏗️ Architettura del Flusso

```
  [ Postazione Client: Notebook / PC Ufficio ]
     │  Interfaccia Grafica o CLI (Claude / Antigravity / Codex / Aider)
     │  Instradamento con Bearer Token protetto
     ▼
  [ GERMANO SERVER sulla LAN :8181 ]  (Workstation con i 6 modelli IA locali)
     1. Riceve le richieste e applica i modelli di privacy locali offline
     2. Anonimizza prompt e documenti (sostituzione PII con token)
     3. Registra i mapping nel Vault protetto locale del client
     4. Inoltra all'LLM di destinazione solo il testo anonimizzato
     5. Ripristina i dati reali nella risposta e la restituisce in chiaro al Client
```

---

## 📦 Installazione Multipiattaforma

Tutti gli installer ufficiali del Client sono disponibili direttamente su **[download.germano.ai](https://download.germano.ai/)**:

### 🪟 Windows (10 / 11 64-bit)
1. **Download:** Scarica `germano-client-0.60.exe` (oppure `Installa_Germano.exe`).
2. **Installazione:** Doppio clic sull'eseguibile. L'applicazione si installa nello spazio utente `%LOCALAPPDATA%\Programs\Germano AI` **senza richiedere diritti di amministratore (zero UAC)** e crea automaticamente la cartella `Documenti\Germano AI` e il collegamento sul Desktop.
3. **Avvio:** Doppio clic sull'icona **Germano** per aprire il pannello grafico in finestra dedicata.

### 🍎 macOS (Apple Silicon & Intel)
1. **Download:** Scarica `germano-client-0.60.command`.
2. **Installazione:** Doppio clic per eseguire l'installer guidato nativo: installa `Germano.app` in `~/Applications` e predispone la cartella sicura `~/Documents/Germano AI` senza richiedere permessi root o sudo.
3. **Avvio:** Apri **Germano.app** da Launchpad o dalla cartella Applicazioni.

### 🐧 Linux (Ubuntu, Debian, Fedora, Arch)
1. **Download:** Scarica `germano-client-0.60.sh`.
2. **Installazione:** Esegui con doppio clic o da terminale con `bash germano-client-0.60.sh`. Si installa in `~/.local/share/germano`, integra il lanciatore sul Desktop e nel Menu Applicazioni, e crea `~/Documents/Germano AI`.
3. **Avvio:** Avvia Germano direttamente dal menu Applicazioni o dalla Scrivania.

---

## 💻 Utilizzo da Riga di Comando (Opzionale)

Per script, pipeline CI/CD o utenti avanzati, il Client offre una completa interfaccia CLI:

```bash
# Mostra la lista dei server attivi sulla LAN
python client.py discover

# Mostra i modelli e le AI esposte dal server
python client.py models

# Chiede direttamente a un'AI del server
python client.py ask "Spiega il principio di privacy by design"

# Avvia un agente locale reindirizzandolo verso il server
python client.py launch claude
python client.py launch antigravity

# Anonimizza un documento locale tramite il server
python client.py send documento.pdf
```

---

## 📖 Documentazione Completa
Per tutti i dettagli tecnici su API, token di sicurezza e configurazione avanzata, consulta il manuale integrato:
- **[GUIDA_OFFLINE.html](GUIDA_OFFLINE.html)** (100% offline, inclusa in ogni pacchetto)
- **[Guida Online Ufficiale](https://germano.ai/guide.html)**

---

<p align="center">
  <b>Germano AI Client</b> — Un progetto Open Source distribuito con licenza <b>GNU GPL v3</b>.<br>
  Sviluppato con orgoglio da <a href="https://www.yesc.it/">Yes Consulting</a>.
</p>
