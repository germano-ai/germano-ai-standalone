# 🛡️ Germano AI - La Privacy Documentale, nell'Era dell'Intelligenza Artificiale.

🌍 *Read this in other languages: [English](README.en.md)*

**💡 Esempio di uso:** *Tu vuoi usare la potenza di un'LLM online (chatgpt, gemini, claude, copilot, deepseek..) ma i tuoi documenti o il testo che scrivi nel prompt contengono dati personali che non vuoi o non puoi inviare all'AI (come da normativa vigente per la Pubblica Amministrazione)? Germano anonimizza questi dati per te. Germano è un'applicazione windows locale e offline (non richiede accesso ad internet per funzionare). germano.ai anonimizza testo, prompt e volti ed è compatibile con il GDPR; si integra perfettamente fungendo da Proxy API Locale con gli strumenti che già usi: Claude Code, Google Antigravity, OpenCode, Cursor e tutti gli altri. In questo modo l'AI online avrà in input solo i documenti e i testi anonimizzati.
Questo è solo un caso d'uso, germano.ai può essere utilizzato in qualsiasi situazione ci sia un gran numero di documenti da anonimizzare, supporta molti formati, restituisce i documenti anonimizzati nella cartella di output ed è altamente configurabile.*

Germano AI è una potente suite open-source progettata per **l'anonimizzazione intelligente** e massiva di documenti e flussi di testo. Basata su motori di Intelligenza Artificiale locale, garantisce la totale privacy dei dati elaborando i file offline (senza inviare dati al cloud).

> Sviluppato orgogliosamente in Italia da **[Yes Consulting](https://www.yesc.it/)**

---

## ⚡ Quickstart (Come funziona)

Germano AI lavora in modo completamente autonomo "ascoltando" le sue cartelle. Il funzionamento base è semplicissimo:
1. Inserisci i documenti (e le eventuali sottocartelle) che vuoi anonimizzare all'interno della cartella **`input`**.
2. Fai doppio clic sul file **`START.bat`** per avviare il motore IA e aprire la Dashboard nel browser.
3. Dalla Dashboard, clicca su "START DAEMON". Il software prenderà i file da `input`, li censurerà, e salverà i documenti puliti nella cartella **`output`**, preservando intatta l'eventuale struttura delle tue cartelle e sottocartelle interne.
4. I file originali verranno parcheggiati in **`processed`**, mentre eventuali file non supportati andranno in **`failed`**. 

💡 **Tip Produttività:** Puoi tranquillamente trascinare nuovi file o intere cartelle dentro `input` *mentre il software sta già lavorando*! Verranno messi in coda ed elaborati in tempo reale senza dover riavviare nulla. Inoltre, dalla Dashboard puoi anonimizzare "al volo" porzioni di testo incollandole nell'apposita casella.

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

### Endpoint di Anonimizzazione File
```http
POST http://127.0.0.1:8000/api/v1/anonymize
```
Restituisce direttamente il flusso binario del file "pulito". Consulta la **[Documentazione Ufficiale](https://germano.ai/guide.html)** sul nostro sito per esempi di utilizzo.

### Endpoint di Anonimizzazione Testo
```http
POST http://127.0.0.1:8000/api/v1/anonymize_text
```
Riceve un JSON con il campo `{"text": "..."}` e restituisce il testo anonimizzato.

---

## 🤖 Integrazione AI Multipiattaforma: API Proxy Locale

L'anonimizzazione dei dati non è più limitata ai file! Germano AI include un **API Proxy Locale** universale (compatibile con il formato OpenAI) capace di fare da "scudo" totale tra il tuo IDE (Cursor, Windsurf, Claude Code, Copilot, Antigravity) e l'Intelligenza Artificiale.

### Come funziona lo "Scudo Privacy" Totale
Normalmente, l'IDE invia tutto quello che scrivi nel prompt (o che trascini nella chat) direttamente ai server online.
Configurando il tuo editor per puntare a Germano AI, il flusso cambia completamente:

1. **Intercettazione**: Quando chiedi all'IA qualcosa o alleghi un file, l'IDE invia la richiesta a Germano AI (che gira offline sul tuo PC alla porta 8000).
2. **Censura al Volo**: Germano intercetta la richiesta, estrae i tuoi prompt testuali, li passa al volo al filtro privacy locale, e sostituisce i dati sensibili con etichette (es. `[PERSONA_1]`).
3. **Mappatura Tracciabile**: La mappa esatta delle parole sostituite viene salvata in un log JSON nella cartella `extracted`, per permetterti di ricollegare facilmente le etichette dell'AI ai dati reali.
4. **Inoltro Sicuro**: Germano inoltra la richiesta "purificata" al vero fornitore LLM (es. OpenAI). Quando l'AI risponderà, utilizzerà a sua volta i tag anonimizzati (es. "Il contratto è intestato a [PERSONA_1]").

L'Intelligenza Artificiale non entrerà **mai** in contatto con i tuoi dati originali, permettendoti di usare prompt estremamente specifici senza violare il GDPR!

### Come Attivarlo (Impostazione Manuale Richiesta)

Poiché le impostazioni di sicurezza dei moderni IDE memorizzano le chiavi API e gli indirizzi proxy in database interni crittografati o protetti, l'integrazione non può essere automatizzata tramite script per motivi di sicurezza, ma **deve essere eseguita manualmente dall'utente nell'interfaccia grafica del software**. Si tratta di un'operazione sicura che va fatta una volta sola e richiede pochi secondi:

1. Avvia Germano AI facendo doppio clic su `START.bat`.
2. Apri il tuo editor AI preferito e modifica l'indirizzo base del server AI:
   - **Cursor**: Vai in `Impostazioni (Settings)` -> `Models` -> Scorri fino a `OpenAI API Key` e inserisci la tua chiave reale. Poi, appena sotto, attiva la levetta **Override OpenAI Base URL** e inserisci il seguente indirizzo: `http://127.0.0.1:8000/v1`.
   - **Windsurf / Antigravity / Altri IDE**: Nelle impostazioni del Provider AI (sotto la voce OpenAI o Provider Personalizzato), cerca il campo **Base URL** (o API Base URL / Custom URL) e inserisci: `http://127.0.0.1:8000/v1`.
3. Assicurati di inserire la tua vera API Key di OpenAI nell'editor. L'IDE la invierà a Germano AI, che la utilizzerà localmente in modo sicuro **esclusivamente** per inoltrare la richiesta ai server di OpenAI dopo aver concluso l'anonimizzazione dei prompt e dei file!

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
