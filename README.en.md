# 🛡️ Germano AI - Document Privacy, in the Era of Artificial Intelligence.

🌍 *Leggi questo documento in altre lingue: [Italiano](README.md)*

*<span style="color: #007bff; font-weight: bold;">Use Case 1</span>: You simply have a large number of documents to anonymize on your computer or server or NAS. Germano works in standalone mode and returns the anonymized documents; it supports many formats and is highly configurable. You simply copy the folder containing the files into input and receive the anonymized files in the output folder. Germano maintains the original directory and subfolder structure. Germano anonymizes text, prompts and faces and is compatible with the GDPR; Germano is a local and offline Windows application (does not require internet access to work).*

*<span style="color: #007bff; font-weight: bold;">Use Case 2</span>: Want to use the power of an online LLM (chatgpt, gemini, claude, copilot, deepseek..) but your documents or the text you write in the prompt contain personal data that you do not want or cannot send to the AI (as per current regulations for the Public Administration)? Germano anonymizes this data for you, integrating perfectly by acting as a Local API Proxy with the tools you already use: Claude Code, Google Antigravity, OpenCode, Cursor, and all the others. If you write "Mario Rossi" on the prompt, it notices and replaces it with [PERSONA_1] before it is sent to the online LLM. In this way, the online AI will only receive as input the anonymized documents and texts.*

Germano AI is a powerful open-source suite designed for **intelligent and massive document and text anonymization**. Based on local Artificial Intelligence engines, it guarantees total data privacy by processing files **100% offline** (without sending data to the cloud) and works out-of-the-box on a fresh **Vanilla Windows 11** installation without requiring internet access or pre-installed system runtimes.

> Proudly developed in Italy by **[Yes Consulting](https://www.yesc.it/)**

---

## ⚡ Quickstart (How it works)

Germano AI works completely autonomously by "listening" to its folders. The basic operation is extremely simple (the Dashboard labels are in Italian; their meaning is given in brackets):
1. Double-click the **`START.bat`** file to start the local server and open the Dashboard in your browser (`http://127.0.0.1:8181`). On the first launch choose the operating mode (if in doubt keep **Standalone**: everything stays on your computer).
2. Add the documents (whole folders with subfolders too): drag them into the **«Trascina qui file o cartelle»** (Drop files or folders here) box, use **Seleziona file** / **Seleziona cartella** (Select files / Select folder), or copy them into the **`input`** folder (the **Apri cartella input** button opens it in File Explorer).
3. Click **Avvia motore** (Start engine) in the top right corner (when you add files from the Dashboard the engine starts on its own). Germano takes the files from `input`, redacts them and saves the clean documents in the **`output`** folder, preserving the folder and subfolder structure; the **In attesa / Pronti / Non riusciti** (pending / ready / failed) counters show the batch progress.
4. Collect the results with **Apri cartella output** (Open output folder) or from the **Documenti** table. Originals are archived in **`processed`**; damaged or unsupported files go to **`failed`** and appear in the **Non riusciti** tab with the reason and a **Rimetti in coda** (Queue again) button. JSON audit logs are saved in **`extracted`**.

💡 **Productivity Tip:** You can add new files or entire folders *while the software is already working*: they are queued and processed without restarting anything. **Esporta elenco** (Export list) saves the list of ready or failed documents as CSV (for Excel). From the Dashboard you can also anonymize a text "on the fly" by pasting it into the **«Testo da inviare a un servizio di AI»** (Text to send to an AI service) box.

👉 **[DOWNLOAD GERMANO AI STANDALONE](https://download.germano.ai)**

---

## 🏛️ Compliance Profiles (PA vs PD)

Germano AI is designed to adapt to both highly regulated environments and private professionals through two specific profiles selectable in real time from the Dashboard:

### 🔴 Germano PA (Public Administration)
- **GDPR** & **CAD** compliant.
- No possibility for the operator to disable crucial security filters like OCR, facial biometrics, or personal data categories.
- Absolute "by design" security for handling hypersensitive citizen data.

### 🟢 Germano PD (Public Domain)
- Completely unlocked and customizable in real time (Hot-Reload without restarting the daemon).
- Allows you to balance the AI filter threshold and individually toggle the 18 data categories and the 6 AI models (e.g. turn off image scanning) to optimize processing times.

---

## 🏛️ Architecture & Operating Modes (Tri-Mode & Dual Mode)

Germano AI implements a modular hybrid architecture, selectable on initial launch and configurable at any time in Settings (taking effect immediately, zero restarts required):

### Three Native Operating Modes:
*   **🖥️ Standalone (Default & 100% Offline):** everything runs locally on this computer in complete isolation. Zero open ports to the external network and zero client discovery. All 6 local AI models load into local memory, the encryption Vault remains on local disk, and zero packets leave the workstation.
*   **📡 LAN Server (Shared Inference Engine):** Germano listens on the local network (default port **8181**) and responds to UDP broadcast auto-discovery (port **8182**). It exposes the local inference engine and the AI Proxy to authorized workstations across the office or studio, protected by Bearer Token authentication. Launches directly via `START.bat`.
*   **🌐 Client (Lightweight Germano Client ~28 MB):** an agile, portable executable designed for laptops or workstations with limited resources. On launch, it automatically discovers the LAN Germano Server and offloads heavy model inference. **Original documents, anonymized files, and the de-anonymization vault strictly reside on the client workstation**: if the server is unreachable, zero data leaves the client and documents remain queued.
*   **Server + Client together:** the host workstation shares inference across the LAN while concurrently processing its own local queue.

### Dual Mode & User Interface:
*   **Dual Mode (Batch + AI Studio):** toggle instantly with a single click between:
    *   **📁 Anonymize files (Batch Processing):** clear and focused interface for massive batch processing, featuring quick-access buttons to open `input` and `output` folders, interactive tabs for `input`, `output`, `failed`, `processed`, and `extracted`, real-time throughput metrics (files/min, redacted PII), hardware monitoring (CPU/RAM), detailed error diagnostics with a **Re-queue** button, and CSV export.
    *   **🤖 AI Studio (Local Harness):** interactive workbench styled after Google Antigravity, featuring automatic detection of installed local AI agents and CLIs (Claude Code, OpenAI Codex CLI, Google Antigravity, Aider, Qwen, Kimi, DeepSeek) with granular model configuration.
*   **100% Bilingual Interface & Contextual Tooltips (Italian / English):** automatic browser language detection (`it` -> Italian, otherwise English by default), quick flag toggle (🇮🇹 IT / 🇬🇧 EN) in the top navigation bar, and over 112 localized interactive hover tooltips across all controls, toggled in Settings.

---

## 🌟 Main Features

*   **100% Offline & Vanilla Windows 11 Ready:** Bundles embedded Python 3.11, all 12 native 64-bit Microsoft Visual C++ Redistributable DLLs pre-integrated (zero admin privileges required), an offline Web UI free of external CDNs, and **6 pre-installed local AI models**.
*   **Simple / Advanced Mode selector:**
    *   **Simple Mode:** zero technical jargon; add documents, the engine processes automatically, and results are retrieved with one click.
    *   **Advanced Mode:** four comprehensive tabs. **Processing** (including archived original files), **AI Agents and API** (Proxy URLs, per-tool setup, target services, REST examples), **Filters and models** (compliance profiles, sensitivity, **18 categories and 7 analysis engines**: Names, Professions/Titles, Addresses, Cadastral, Tax Codes/VAT, Email/PEC, Phone Numbers, IBAN/Bank accounts, Amounts/Finance, Dates, Companies/Entities, License Plates/IDs, Health Data (GDPR Art. 9), Medications/Therapies, Judicial Data (GDPR Art. 10), Marital Status, Passwords/Secrets, and URLs/IPs), **System and logs** (compute precision, working directories, update checks, Vault, live log console).
*   **📖 Complete Offline Guide & Technical Documentation:** *"Guida"* (Guide) button integrated into the Dashboard (available at `/guide` and as standalone file `GUIDA_OFFLINE.html`), fully bilingual (Italian and English), featuring step-by-step guides, 5-folder workflow breakdown, REST API specifications, and setup instructions for Google Antigravity, OpenAI Codex, Cursor, and Claude Code.
*   **🔑 Automatic De-Anonymization via API Proxy and Internal Folders:** When *"Ripristino automatico dei dati originali"* (Automatic data restoration) is active (default), Germano logs entity mappings in the local Vault (`extracted/deanonymize_vault.json`). In API Proxy integrations (`/v1/chat/completions`, `/v1/responses`, `/v1/messages` for **Google Antigravity, Codex, Cursor, Claude Code, OpenCode**) and in the local `input/` folder, AI responses and returned documents are **automatically de-anonymized** with their true original values.
*   **6 Integrated 100% Offline AI Engines (`models/`):**
    1. **Velvet Privacy Filter (1.5B, BF16 weights):** Multilingual contextual Transformer model for PII (based on OpenAI Privacy Filter, Apache-2.0 license).
    2. **Italian NER XXL v2 (58 classes):** Specialized NER model for legal, medical, banking, cadastral, and administrative Italian documents.
    3. **EasyOCR (CRAFT + Latin G2):** Local Optical Character Recognition on scanned PDFs and photos.
    4. **YuNet Face Detector (OpenCV 5 DNN):** Biometric face detection and redaction (`[VOLTO]`).
    5. **YOLOS-Tiny Signature Detector:** Visual detection and redaction of handwritten signatures (`[FIRMA]`).
    6. **YOLOS-Small License Plate Detector:** Visual detection and redaction of vehicle license plates (`[TARGA]`).
*   **Advanced Multi-Format Management with Layout Preservation:**
    *   📄 **PDF & PDF Portfolios:** Character-level redaction, OCR and *visual redaction* on scans (including stamped scans), form fields, comments, bookmarks, metadata, and recursive redaction of embedded attachments. PAdES digital signatures cleanly stripped to prevent visual validation conflicts.
    *   🖼️ **Images (`PNG`, `JPG`, `JPEG`, `BMP`, `TIFF`, `WEBP`, `GIF`):** Local OCR and visual redaction of faces, signatures, and license plates retaining original dimensions and resolution; EXIF/GPS metadata removed.
    *   📝 **Word (`DOCX`, `DOCM`, `DOC`, `RTF`) & OpenDocument (`ODT`, `ODS`, `ODP`):** Anonymizes and de-anonymizes body text, tables, headers, footers, footnotes, text frames, comments, speaker notes, and embedded objects without altering document layout, fonts, bolding, or images. `DOC`/`PPT` require Microsoft Office or LibreOffice (unless renamed RTF/DOCX/HTML).
    *   📊 **Spreadsheets & Presentations (`XLSX`, `XLSM`, `XLS`, `CSV`, `TSV`, `PPTX`, `PPT`):** Redacts and restores cell data, sheet names, charts, slides, presenter notes, and comments, preserving underlying formulas and VBA Macros.
    *   🌐 **Web, Data, Email & Archives (`HTML`, `XML`/FatturaPA, `JSON`, `EML`, `ZIP`, `P7M`):** Native DOM/MIME handling, email attachment recursion, archive traversal for `.zip`, and PKCS#7 signed file parsing (`.p7m`).
*   **Reliability & Concurrency:** Thread-safe Vault operations, atomic file processing only after copy completion, and clean graceful shutdown.

**Requirements:** Windows 10/11 64-bit, 8 GB RAM (16 GB recommended), about 6 GB of free disk space. Zero installation and zero administrator privileges required.

## 🔌 REST API Integration

Germano AI is not just a Dashboard. Integrate the anonymization engine directly into your document workflows (CRM, ERP, Document Management Systems) via fast **synchronous local APIs**.

### File Anonymization Endpoint
```http
POST http://127.0.0.1:8181/api/v1/anonymize
```
Directly returns the binary stream of the "clean" file. Check the **[Official Documentation](https://germano.ai/guide.html)** on our website for usage examples.

### Text Anonymization Endpoint
```http
POST http://127.0.0.1:8181/api/v1/anonymize_text
```
Expects a JSON payload with the `{"text": "..."}` field and returns the anonymized text along with the detailed map of extracted entities.

---

## 🤖 Cross-Platform AI Integration: Local API Proxy

Data anonymization is no longer limited to files! Germano AI includes a universal **Local API Proxy** (compatible with the OpenAI format) capable of acting as a total "shield" between your IDE (Cursor, Windsurf, Claude Code, Copilot, Antigravity) and the Artificial Intelligence.

### How the Total "Privacy Shield" works
Normally, the IDE sends everything you write in the prompt (or drag into the chat) directly to online servers.
By configuring your editor to point to Germano AI, the flow changes completely:

1. **Interception**: When you ask the AI something or attach a file, the IDE sends the request to Germano AI (running offline on your PC at port 8181).
2. **On-the-Fly Censorship**: Germano intercepts the request, extracts your text prompts, passes them instantly to the local privacy filter, and replaces sensitive data with indexed labels (e.g. `[PERSONA_1]`).
3. **Traceable Mapping**: The exact map of replaced words is saved in a daily log (`extracted/proxy_sessions/YYYY-MM-DD.jsonl`), allowing you to easily link the AI labels back to real data.
4. **Secure Forwarding**: Germano forwards the "purified" request to the real LLM provider (e.g. OpenAI). When the AI responds, it will in turn use the anonymized tags (e.g. "The contract is registered to [PERSONA_1]").

The Artificial Intelligence will **never** come into contact with your original data, allowing you to use extremely specific prompts without violating the GDPR!

### How to Activate It (Manual Setup Required)

In Advanced Mode, the Dashboard's **Agenti AI e API** (AI agents and API) tab shows the addresses to copy and, tool by tool, where to set them.

1. Start Germano AI by double-clicking on `START.bat`.
2. Open your preferred AI editor and change the AI server base address:
   - **Cursor**: Go to `Settings` -> `Models` -> Scroll to `OpenAI API Key` and insert your real key. Then, just below it, toggle on **Override OpenAI Base URL** and insert the following address: `http://127.0.0.1:8181/v1`.
   - **Windsurf / Antigravity / Other IDEs**: In the AI Provider settings (under OpenAI or Custom Provider), find the **Base URL** (or API Base URL / Custom URL) field and insert: `http://127.0.0.1:8181/v1`.
   - **Claude Code**: before starting it, set `ANTHROPIC_BASE_URL=http://127.0.0.1:8181` (in PowerShell: `$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8181"`).
   - **OpenAI Codex CLI**: set `OPENAI_BASE_URL=http://127.0.0.1:8181/v1`.
3. Make sure you enter your real API Key (OpenAI or Anthropic) in the editor. The IDE will send it to Germano AI, which will safely use it locally **exclusively** to forward the request to OpenAI's servers after finishing the anonymization of prompts and files!

### 🛡️ "Fail-Safe Privacy" (Hard Block Active)
Our API Proxy is designed with a zero-tolerance policy for errors (Hard Block). 
If for any reason (e.g., AI daemon stopped, unreadable format, or corrupted image file) the privacy filter fails the scan, **the Proxy will NOT send your original data to the LLM**. The request will be instantly destroyed, and you will receive an error message inside your editor. This guarantees that under no circumstances can your clear-text data leak to the internet due to a software malfunction.

---

## 🔄 Automatic updates

Germano keeps itself up to date without giving up offline operation:

1. **Only when Windows reports that the PC is connected to the Internet** (about 20 seconds after startup and then every 6 hours), Germano opens `https://download.germano.ai` (the official download address, which points to the public package folder) and looks for the most recent `GermanoAI_Release_v<version>.zip`. On a disconnected PC no connection attempt is made.
2. If it is newer than the installed version, the package is downloaded into the `update/` folder and checked: complete download, **SHA-256** fingerprint (when the folder also holds the `.sha256` file), integrity of every file in the ZIP and version matching the file name. A package that fails the checks is discarded.
3. Installation happens at the next `START.bat` start (or right away with **Installa ora e riavvia**, install now and restart, in the Dashboard notice). Working folders, the Vault and `config.json` are left untouched; if anything goes wrong, the previous version is put back.

The options are in Advanced Mode, **Sistema e registro → Aggiornamenti** (System and log → Updates), or in `config.json`: `"check_updates": false` turns the check off, `"auto_update": false` only reports the new version. No document data is sent during the check.

---

## 📂 Working Folders Structure
- `/input`: Drag files here.
- `/output`: Anonymized files, with original format and layout intact.
- `/processed`: Original files moved at the end of the job.
- `/failed`: Corrupted, blocked, or unreadable documents (listed in the *Non riusciti* tab with the reason).
- `/extracted`: JSON files with logs of what was replaced (for GDPR Audit).
- `/update`: Created only when needed: a downloaded update waiting to be installed.

## 📜 License and Contribution
This project is proudly distributed under the **GNU GPL v3** license. You can use it for free even for commercial purposes, as long as you keep any modifications Open Source. 
Are you a developer? Open a Pull Request! We want privacy to be a right accessible to everyone.

## 📞 Contacts
Do you need Enterprise support, custom integrations, or assistance?
- **Website**: [germano.ai](https://germano.ai)
- **Developed by**: [Yes Consulting](https://www.yesc.it/)
- **Email**: [info@germano.ai](mailto:info@germano.ai)
