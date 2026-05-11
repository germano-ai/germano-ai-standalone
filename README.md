# 🛡️ Germano AI - Standalone Document Anonymizer

Germano AI è una potente suite open-source progettada per **l'anonimizzazione intelligente** e massiva di documenti aziendali e della Pubblica Amministrazione. Basata su motori di Intelligenza Artificiale locale, garantisce la totale privacy dei dati elaborando i file offline.

## 🚀 Funzionalità Principali

*   **100% Offline & Standalone:** Non richiede XAMPP o altri server web. Il server Flask e il demone Python girano in totale autonomia sul tuo computer senza mai inviare dati all'esterno.
*   **Architettura a Demone:** Un processo in background persistente scansiona in tempo reale una cartella di input ed elabora i file. Ottimizza la memoria RAM caricando i pesanti modelli IA una sola volta.
*   **Gestione Multi-Formato Avanzata:**
    *   📄 **PDF:** Censura testuale e *censura visiva* (disegna maschere nere oscuranti preservando il layout e misurando esattamente la dimensione del font).
    *   📝 **DOCX / DOCM:** Anonimizza testi, tabelle, intestazioni (Header) e piè di pagina (Footer).
    *   📊 **XLSX / XLSM / XLS:** Oscura i dati nelle celle e persino nei commenti, preservando eventuali Macro VBA (`keep_vba`).
    *   🔤 **TXT / RTF:** Sostituzione sicura in-place.
*   **Censura Intelligente & RegEx:** Combina l'uso di modelli Transformer (`openai/privacy-filter`) per il riconoscimento delle entità (Nomi, Luoghi) con solide Espressioni Regolari (RegEx) per intercettare Email, Codici Fiscali, Partite IVA, Numeri di Telefono e Indirizzi italiani.
*   **OCR e Biometria Integrata:** Integra `EasyOCR` per estrarre e censurare testi nascosti nelle immagini, e `OpenCV` per riconoscere e offuscare automaticamente i volti.
*   **Accelerazione Hardware:** Supporta CPU, GPU NVIDIA (CUDA) e GPU AMD/Intel (tramite `torch_directml`).
*   **Dashboard di Controllo Interattiva:** Un'interfaccia moderna in CSS Grid che permette di avviare/fermare il demone, consultare la telemetria (file processati, dimensione coda) e visualizzare i log di sistema in tempo reale.

## 🛠️ Tecnologie e Software Utilizzati

*   **Backend & API:** `Python`, `Flask`
*   **Intelligenza Artificiale:** `Transformers` (Hugging Face), `PyTorch` (con DirectML)
*   **Elaborazione Documenti:** `PyMuPDF` (fitz) per i PDF, `python-docx` per Word, `openpyxl` / `xlrd` / `xlutils` per Excel.
*   **Elaborazione Immagini/Biometria:** `OpenCV` (`cv2`), `EasyOCR`, `Numpy`.
*   **Frontend UI:** Vanilla `HTML5`, `CSS Grid`, `JavaScript` asincrono.

## 📂 Struttura delle Cartelle
- `/input`: Trascina qui i file (anche in sottocartelle) che vuoi anonimizzare.
- `/processed`: I file originali verranno spostati qui dopo l'elaborazione.
- `/output`: I file anonimizzati, con lo stesso formato e layout originale.
- `/failed`: Documenti corrotti, bloccati o protetti da password che hanno generato errori.
- `/extracted`: File JSON con la lista dei dati sensibili rilevati e offuscati.

## 📜 Licenza
Questo progetto è distribuito sotto licenza **GNU GPL v3**. Consulta il file `LICENSE` per maggiori dettagli.
