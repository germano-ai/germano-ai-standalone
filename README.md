# 🛡️ Germano AI - La Privacy Documentale, nell'Era dell'Intelligenza Artificiale.

🌍 *Read this in other languages: [English](README.en.md)*

**💡 Esempio di uso:** *Tu vuoi usare la potenza di un'LLM online (chatgpt, gemini, claude, copilot, deepseek..) ma i tuoi documenti contengono dati personali che non vuoi o non puoi inviare all'AI (come da normativa vigente per la Pubblica Amministrazione). Germano anonimizza questi dati per te. Germano è un'applicazione windows locale e offline che anonimizza i tuoi documenti. In questo modo l'AI online avrà in input solo i documenti anonimizzati. germano.ai anonimizza testo e volti ed è compatibile con il GDPR oltre che essere adattabile a requisiti di privacy specifici;  si integra perfettamente tramite plugin con gli strumenti che già usi: Claude Code, Google Antigravity, OpenCode e tutti gli altri tramite plugin e server MCP.*

Germano AI è una potente suite open-source progettata per **l'anonimizzazione intelligente** e massiva di documenti. Basata su motori di Intelligenza Artificiale locale, garantisce la totale privacy dei dati elaborando i file offline (senza inviare dati al cloud).

> Sviluppato orgogliosamente in Italia da **[Yes Consulting](https://www.yesc.it/)**

---

## ⚡ Quickstart (Come funziona)

Germano AI lavora in modo completamente autonomo "ascoltando" le sue cartelle. Il funzionamento base è semplicissimo:
1. Inserisci i documenti (e le eventuali sottocartelle) che vuoi anonimizzare all'interno della cartella **`input`**.
2. Fai doppio clic sul file **`START.bat`** per avviare il motore IA e aprire la Dashboard nel browser.
3. Dalla Dashboard, clicca su "START DAEMON". Il software prenderà i file da `input`, li censurerà, e salverà i documenti puliti nella cartella **`output`**, preservando intatta l'eventuale struttura delle tue cartelle e sottocartelle interne.
4. I file originali verranno parcheggiati in **`processed`**, mentre eventuali file non supportati andranno in **`failed`**. 

💡 **Tip Produttività:** Puoi tranquillamente trascinare nuovi file o intere cartelle dentro `input` *mentre il software sta già lavorando*! Verranno messi in coda ed elaborati in tempo reale senza dover riavviare nulla.

👉 **[SCARICA GERMANO AI STANDALONE (~4 GB)](https://drive.google.com/drive/folders/1uyRyW-zgqkEy5QmMmylQZ6k7-wzuEleD)**

---

## 🏛️ Profili di Conformità (PA vs PD)

Germano AI è progettato per adattarsi sia ad ambienti altamente regolamentati che a professionisti privati tramite due profili specifici selezionabili dalla Dashboard:

### 🔴 Germano PA (Pubblica Amministrazione)
- A norma **CAD** e **GDPR**.
- Nessuna possibilità per l'operatore di disabilitare filtri di sicurezza cruciali come l'OCR o la biometria facciale.
- Sicurezza assoluta "by design" per gestire dati ipersensibili dei cittadini.

### 🟢 Germano PD (Pubblico Dominio)
- Totalmente sbloccato.
- Permette di bilanciare la potenza dei filtri IA e disattivare la censura delle immagini per ottimizzare i tempi di elaborazione sui PC meno potenti.

---

## 🚀 Funzionalità Principali

*   **100% Offline & Locale:** I tuoi dati non lasciano mai il tuo ufficio.
*   **Gestione Multi-Formato Avanzata:**
    *   📄 **PDF:** Censura testuale e *censura visiva* (disegna maschere nere oscuranti preservando il layout).
    *   📝 **DOCX / DOCM:** Anonimizza testi, tabelle, intestazioni e piè di pagina.
    *   📊 **XLSX / XLSM / XLS:** Oscura i dati nelle celle e persino nei commenti, preservando eventuali Macro VBA.
*   **Censura Intelligente & RegEx:** Combina NLP Transformer (`openai/privacy-filter`) con Espressioni Regolari (RegEx) italiane (Email, Codici Fiscali, P.IVA, ecc.).
*   **OCR e Biometria Integrata:** Integra `EasyOCR` per estrarre e censurare testi nelle scansioni e `OpenCV` per riconoscere e offuscare automaticamente i volti sulle fototessere.
*   **Accelerazione Hardware:** Supporta CPU, GPU NVIDIA (CUDA) e GPU AMD/Intel (tramite `torch_directml`).

---

## 🔌 Integrazione REST API

Germano AI non è solo una Dashboard. Integra il motore di anonimizzazione direttamente nei tuoi flussi documentali (CRM, ERP, Protocollo Informatico) tramite le veloci **API locali sincrone**.

### Endpoint di Anonimizzazione
```http
POST http://127.0.0.1:8000/api/v1/anonymize
```
Restituisce direttamente il flusso binario del file "pulito". Consulta la **[Documentazione Ufficiale](https://germano.ai/guide.html)** sul nostro sito per esempi di utilizzo (cURL, Postman).

---

## 🤖 Integrazione AI Multipiattaforma (Cursor, Windsurf, Claude Code, Copilot, Antigravity)

L'anonimizzazione dei documenti non è più limitata alla Dashboard web. Germano AI include ora una suite di integrazione ufficiale progettata per connettere il nostro motore privacy locale direttamente con i più popolari e potenti **Assistenti di Programmazione IA**. 

Sfruttando lo standard **Model Context Protocol (MCP)** (creato da Anthropic e adottato da tutto il settore), abbiamo sviluppato un plugin universale in Python capace di fare da "scudo" tra i tuoi file e l'Intelligenza Artificiale.

### Come funziona lo "Scudo Privacy"
Normalmente, quando chiedi a un'IA come Claude, Antigravity o Cursor di "Leggere questo documento e farne un riassunto", l'IA utilizza i suoi tool standard per leggere l'intero file originale in chiaro e inviarlo ai propri server cloud.

Installando questo plugin:
1. Al momento dell'avvio dell'editor, il plugin si connette in background a Germano AI (avviando il demone locale `START.bat` se non è già attivo).
2. Fornisce all'IA un nuovo strumento chiamato `read_anonymized_file`.
3. Insegna dinamicamente all'IA una regola fondamentale: **"Ogni volta che l'utente ti chiede di leggere un file, sei obbligato a usare read_anonymized_file al posto del tuo lettore standard"**.
4. Quando l'IA invoca questo tool, il nostro script locale prende in carico il file originale, lo passa al filtro privacy in locale, salva la versione censurata in locale e restituisce all'IA **solo i dati anonimizzati**.

L'Intelligenza Artificiale non entrerà **mai** in contatto con i dati originali!

### Installazione Facilissima
Non devi impazzire a configurare JSON a mano. 
Fai doppio clic sul file **`INSTALL_AI_PLUGINS.bat`** (oppure esegui `python ai_plugins/install_ai_plugins.py` da terminale).

Si aprirà un programma interattivo che scansionerà il tuo computer alla ricerca di editor compatibili (Cursor, Windsurf, VS Code, ecc.) e ti guiderà passo-passo fornendoti la configurazione esatta pronta per il copia-incolla, o nel caso di Claude Code, installerà tutto automaticamente con un solo clic. Se non troverà editor compatibili nel sistema, ti avviserà con un messaggio chiaro, permettendoti comunque di forzare le configurazioni manualmente.

---

## 📂 Struttura Cartelle di Lavoro
- `/input`: Trascina qui i file.
- `/output`: I file anonimizzati, con formato e layout originale intatti.
- `/processed`: File originali spostati a fine lavoro.
- `/failed`: Documenti corrotti, bloccati o illeggibili.
- `/extracted`: File JSON con i log di cosa è stato sostituito (per Audit).

## 📜 Licenza e Contribuzione
Questo progetto è orgogliosamente distribuito sotto licenza **GNU GPL v3**. Puoi usarlo gratuitamente anche per scopi commerciali, a patto di mantenere Open Source le tue eventuali modifiche. 
Sei uno sviluppatore? Apri una Pull Request! Vogliamo che la privacy sia un diritto accessibile a tutti.

## 📞 Contatti
Hai bisogno di supporto Enterprise, integrazioni personalizzate o assistenza?
- **Sito Web**: [germano.ai](https://germano.ai)
- **Sviluppato da**: [Yes Consulting](https://www.yesc.it/)
- **Email**: [info@germano.ai](mailto:info@germano.ai)
