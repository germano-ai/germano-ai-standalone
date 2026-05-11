# 🛡️ Germano AI - La Privacy Documentale, nell'Era dell'Intelligenza Artificiale.

Germano AI è una potente suite open-source progettata per **l'anonimizzazione intelligente** e massiva di documenti. Basata su motori di Intelligenza Artificiale locale, garantisce la totale privacy dei dati elaborando i file offline (senza inviare dati al cloud).

> Sviluppato orgogliosamente in Italia da **[Yes Consulting](https://www.yesc.it/)**

---

## 📥 Inizia Subito (Gratis e Open Source)

Nessun installer complesso o configurazione. Estrai lo ZIP, fai doppio clic su `START.bat` e aprirai la fantastica **Dashboard di Controllo** locale nel tuo browser.

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
