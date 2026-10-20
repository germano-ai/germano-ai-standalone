# 🛡️ Germano AI - Document Privacy, in the Era of Artificial Intelligence.

🌍 *Leggi questo documento in altre lingue: [Italiano](README.md)*

*<span style="color: #007bff; font-weight: bold;">Use Case 1</span>: You simply have a large number of documents to anonymize on your computer or server or NAS. Germano works in standalone mode and returns the anonymized documents; it supports many formats and is highly configurable. You simply copy the folder containing the files into input and receive the anonymized files in the output folder. Germano maintains the original directory and subfolder structure. Germano anonymizes text, prompts and faces and is compatible with the GDPR; Germano is a local and offline Windows application (does not require internet access to work).*

*<span style="color: #007bff; font-weight: bold;">Use Case 2</span>: Want to use the power of an online LLM (chatgpt, gemini, claude, copilot, deepseek..) but your documents or the text you write in the prompt contain personal data that you do not want or cannot send to the AI (as per current regulations for the Public Administration)? Germano anonymizes this data for you, integrating perfectly by acting as a Local API Proxy with the tools you already use: Claude Code, Google Antigravity, OpenCode, Cursor, and all the others. If you write "Mario Rossi" on the prompt, it notices and replaces it with [PERSONA_1] before it is sent to the online LLM. In this way, the online AI will only receive as input the anonymized documents and texts.*

Germano AI is a powerful open-source suite designed for **intelligent and massive document and text anonymization**. Based on local Artificial Intelligence engines, it guarantees total data privacy by processing files **100% offline** (without sending data to the cloud) and works out-of-the-box on a fresh **Vanilla Windows 11** installation without requiring internet access or pre-installed system runtimes.

> Proudly developed in Italy by **[Yes Consulting](https://www.yesc.it/)**

---

## ⚡ Quickstart (How it works)

Germano AI works completely autonomously by "listening" to its folders. The basic operation is extremely simple:
1. Place the documents (and any subfolders) you want to anonymize inside the **`input`** folder (or drag and drop them directly into the Web Dashboard **Dropzone**).
2. Double-click the **`START.bat`** file to start the local server and open the Dashboard in your browser (`http://127.0.0.1:8000`).
3. From the Dashboard, click on **"AVVIA MOTORE IA"** (Start AI Engine). The software will take the files from `input`, redact them, and save the clean documents in the **`output`** folder, preserving your internal folder and subfolder structure intact.
4. The original files will be parked in **`processed`**, while any unsupported or corrupted files will go to **`failed`**. JSON audit logs are saved in **`extracted`**.

💡 **Productivity Tip:** You can safely drag new files or entire folders into `input` (or via the Web Dropzone) *while the software is already working*! They will be queued and processed in real time without having to restart anything. Additionally, from the Dashboard, you can anonymize portions of text "on the fly" by pasting them into the dedicated text box and download processed files directly from the browser.

👉 **[DOWNLOAD GERMANO AI STANDALONE](https://drive.google.com/drive/folders/1uyRyW-zgqkEy5QmMmylQZ6k7-wzuEleD)**

---

## 🏛️ Compliance Profiles (PA vs PD)

Germano AI is designed to adapt to both highly regulated environments and private professionals through two specific profiles selectable in real time from the Dashboard:

### 🔴 Germano PA (Public Administration)
- **GDPR** & **CAD** compliant.
- No possibility for the operator to disable crucial security filters like OCR, facial biometrics, or personal data categories.
- Absolute "by design" security for handling hypersensitive citizen data.

### 🟢 Germano PD (Public Domain)
- Completely unlocked and customizable in real time (Hot-Reload without restarting the daemon).
- Allows you to balance the AI filter threshold, individually toggle the 9 redaction categories, and disable image censorship to optimize processing times.

---

## 🚀 Main Features (v0.50-alpha)

*   **100% Offline & Vanilla Windows 11 Ready:** Bundles embedded Python 3.11, all 12 native 64-bit Microsoft Visual C++ Redistributable DLLs directly in the runtime (zero administrator privileges required), a zero-CDN offline Web UI, and **6 pre-installed local AI models**.
*   **Simple Mode / Advanced Mode Slider:**
    *   **✨ Simple Mode (Foolproof UI):** Zero technical jargon, automatic engine startup when dropping a file, and a guided 2-step workflow.
    *   **⚙️ Advanced Mode:** Giant interactive grid of **18 Checkboxes and 7 AI Model Toggles** to individually configure Names, Professions/Titles, Addresses, Cadastre, Fiscal Codes/VAT, Emails/PEC, Phones, IBAN/Accounts, Amounts/Financials, Dates, Companies/Orgs, License Plates/Docs, Medical/Health Data (GDPR Art. 9), Medications/Therapies, Judicial/Legal Data (GDPR Art. 10), Civil Status, Passwords/Secrets, and URLs/IPs.
*   **📖 Complete Offline Guide & Technical Documentation:** Quick *"📖 Guida & Docs"* button directly integrated in the dashboard header (available at `/guide` and as a standalone `GUIDA_OFFLINE.html` file), bilingual (instant Italian/English toggle), featuring foolproof explanations, guide to the 5 internal folders, complete REST API specs, and step-by-step setup for Google Antigravity, OpenAI Codex, Cursor, and Claude Code.
*   **🔄 Automatic De-Anonymization via API Proxy and Internal Folders:** When the top switch is enabled, Germano stores the mapping for `[PERSONA_1]`, `[INDIRIZZO_1]`, etc. in the local Vault (`extracted/deanonymize_vault.json`). Across the local API Proxy (`/v1/chat/completions`, `/v1/responses`, `/v1/messages` for **Google Antigravity, Codex, Cursor, Claude Code, OpenCode**) and the internal `input/` folder, responses and files returned by the AI automatically have all original real data restored on the fly (without ever scanning folders outside the program directory).
*   **6 Integrated 100% Offline AI Engines (`models/`):**
    1. **Velvet Privacy Filter (1.5B FP16):** Multilingual contextual Transformer model for PII detection.
    2. **Italian NER XXL v2 (58 classes):** Specialized NER model for legal, medical, banking, cadastral, and administrative entities.
    3. **EasyOCR (CRAFT + Latin G2):** Local Optical Character Recognition on scanned PDFs and photos.
    4. **YuNet Face Detector (OpenCV 5 DNN):** Biometric face detection and redaction (`[VOLTO]`).
    5. **YOLOS-Tiny Signature Detector:** Visual detection and redaction of handwritten signatures (`[FIRMA]`).
    6. **YOLOS-Small License Plate Detector:** Visual detection and redaction of vehicle license plates (`[TARGA]`).
*   **Advanced Multi-Format Management:**
    *   📄 **PDF & PDF Portfolios:** Contextual textual redaction, *visual redaction* on scans, and recursive anonymization of embedded PDF attachments.
    *   🖼️ **Images (`PNG`, `JPG`, `JPEG`, `BMP`, `TIFF`, `WEBP`):** Local OCR and visual redaction of faces, signatures, and license plates preserving the native image format.
    *   📝 **Word (`DOCX`, `DOCM`, `DOC`, `RTF`) & OpenDocument (`ODT`, `ODS`, `ODP`):** Anonymizes and de-anonymizes texts, tables, headers, footers, and embedded OLE objects.
    *   📊 **Spreadsheets & Presentations (`XLSX`, `XLSM`, `XLS`, `CSV`, `PPTX`, `PPT`):** Redacts and restores data in cells, slides, and comments while preserving VBA Macros.
    *   🌐 **Web, Email & Archives (`HTML`, `XML`, `EML`, `ZIP`):** Native DOM/MIME processing and recursive `.zip` archive inspection.

---

## 🔌 REST API Integration

Germano AI is not just a Dashboard. Integrate the anonymization engine directly into your document workflows (CRM, ERP, Document Management Systems) via fast **synchronous local APIs**.

### File Anonymization Endpoint
```http
POST http://127.0.0.1:8000/api/v1/anonymize
```
Directly returns the binary stream of the "clean" file. Check the **[Official Documentation](https://germano.ai/guide.html)** on our website for usage examples.

### Text Anonymization Endpoint
```http
POST http://127.0.0.1:8000/api/v1/anonymize_text
```
Expects a JSON payload with the `{"text": "..."}` field and returns the anonymized text along with the detailed map of extracted entities.

---

## 🤖 Cross-Platform AI Integration: Local API Proxy

Data anonymization is no longer limited to files! Germano AI includes a universal **Local API Proxy** (compatible with the OpenAI format) capable of acting as a total "shield" between your IDE (Cursor, Windsurf, Claude Code, Copilot, Antigravity) and the Artificial Intelligence.

### How the Total "Privacy Shield" works
Normally, the IDE sends everything you write in the prompt (or drag into the chat) directly to online servers.
By configuring your editor to point to Germano AI, the flow changes completely:

1. **Interception**: When you ask the AI something or attach a file, the IDE sends the request to Germano AI (running offline on your PC at port 8000).
2. **On-the-Fly Censorship**: Germano intercepts the request, extracts your text prompts, passes them instantly to the local privacy filter, and replaces sensitive data with indexed labels (e.g. `[PERSONA_1]`).
3. **Traceable Mapping**: The exact map of replaced words is saved in a JSON log in the `extracted` folder, allowing you to easily link the AI labels back to real data.
4. **Secure Forwarding**: Germano forwards the "purified" request to the real LLM provider (e.g. OpenAI). When the AI responds, it will in turn use the anonymized tags (e.g. "The contract is registered to [PERSONA_1]").

The Artificial Intelligence will **never** come into contact with your original data, allowing you to use extremely specific prompts without violating the GDPR!

### How to Activate It (Manual Setup Required)

1. Start Germano AI by double-clicking on `START.bat`.
2. Open your preferred AI editor and change the AI server base address:
   - **Cursor**: Go to `Settings` -> `Models` -> Scroll to `OpenAI API Key` and insert your real key. Then, just below it, toggle on **Override OpenAI Base URL** and insert the following address: `http://127.0.0.1:8000/v1`.
   - **Windsurf / Antigravity / Other IDEs**: In the AI Provider settings (under OpenAI or Custom Provider), find the **Base URL** (or API Base URL / Custom URL) field and insert: `http://127.0.0.1:8000/v1`.
3. Make sure you enter your real OpenAI API Key in the editor. The IDE will send it to Germano AI, which will safely use it locally **exclusivamente** to forward the request to OpenAI's servers after finishing the anonymization of prompts and files!

### 🛡️ "Fail-Safe Privacy" (Hard Block Active)
Our API Proxy is designed with a zero-tolerance policy for errors (Hard Block). 
If for any reason (e.g., AI daemon stopped, unreadable format, or corrupted image file) the privacy filter fails the scan, **the Proxy will NOT send your original data to the LLM**. The request will be instantly destroyed, and you will receive an error message inside your editor. This guarantees that under no circumstances can your clear-text data leak to the internet due to a software malfunction.

---

## 📂 Working Folders Structure
- `/input`: Drag files here.
- `/output`: Anonymized files, with original format and layout intact.
- `/processed`: Original files moved at the end of the job.
- `/failed`: Corrupted, blocked, or unreadable documents.
- `/extracted`: JSON files with logs of what was replaced (for GDPR Audit).

## 📜 License and Contribution
This project is proudly distributed under the **GNU GPL v3** license. You can use it for free even for commercial purposes, as long as you keep any modifications Open Source. 
Are you a developer? Open a Pull Request! We want privacy to be a right accessible to everyone.

## 📞 Contacts
Do you need Enterprise support, custom integrations, or assistance?
- **Website**: [germano.ai](https://germano.ai)
- **Developed by**: [Yes Consulting](https://www.yesc.it/)
- **Email**: [info@germano.ai](mailto:info@germano.ai)
