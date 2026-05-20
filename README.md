# 🛡️ Germano AI - La Privacy Documentale, nell'Era dell'Intelligenza Artificiale.

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
