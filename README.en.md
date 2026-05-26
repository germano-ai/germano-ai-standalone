# 🛡️ Germano AI - Document Privacy, in the Era of Artificial Intelligence.

🌍 *Leggi questo documento in altre lingue: [Italiano](README.md)*

**💡 Example of Use:** *Want to use the power of an online LLM (chatgpt, gemini, claude, copilot, deepseek..) but your documents or the text you write in the prompt contain personal data that you do not want or cannot send to the AI (as per current regulations for the Public Administration)? Germano anonymizes this data for you. Germano is a local and offline Windows application (does not require internet access to work). germano.ai anonymizes text, prompts and faces and is compatible with the GDPR; it integrates perfectly by acting as a Local API Proxy with the tools you already use: Claude Code, Google Antigravity, OpenCode, Cursor, and all the others. In this way, the online AI will only receive as input the anonymized documents and texts.
<span style="color: #007bff; font-weight: bold;">Use Case 2</span>: you simply have a large number of documents to anonymize on your computer or server or NAS. Germano works in standalone mode and returns the anonymized documents; it supports many formats and is highly configurable. You simply copy the folder containing the files into input and receive the anonymized files in the output folder. Germano maintains the original directory and subfolder structure.*

Germano AI is a powerful open-source suite designed for **intelligent and massive document and text anonymization**. Based on local Artificial Intelligence engines, it guarantees total data privacy by processing files offline (without sending data to the cloud).

> Proudly developed in Italy by **[Yes Consulting](https://www.yesc.it/)**

---

## ⚡ Quickstart (How it works)

Germano AI works completely autonomously by "listening" to its folders. The basic operation is extremely simple:
1. Place the documents (and any subfolders) you want to anonymize inside the **`input`** folder.
2. Double-click the **`START.bat`** file to start the AI engine and open the Dashboard in your browser.
3. From the Dashboard, click on "START DAEMON". The software will take the files from `input`, redact them, and save the clean documents in the **`output`** folder, preserving your internal folder and subfolder structure intact.
4. The original files will be parked in **`processed`**, while any unsupported files will go to **`failed`**. 

💡 **Productivity Tip:** You can safely drag new files or entire folders into `input` *while the software is already working*! They will be queued and processed in real time without having to restart anything. Additionally, from the Dashboard, you can anonymize portions of text "on the fly" by pasting them into the dedicated text box.

👉 **[DOWNLOAD GERMANO AI STANDALONE (~4 GB)](https://drive.google.com/drive/folders/1uyRyW-zgqkEy5QmMmylQZ6k7-wzuEleD)**

---

## 🏛️ Compliance Profiles (PA vs PD)

Germano AI is designed to adapt to both highly regulated environments and private professionals through two specific profiles selectable from the Dashboard:

### 🔴 Germano PA (Public Administration)
- **GDPR** compliant.
- No possibility for the operator to disable crucial security filters like OCR or facial biometrics.
- Absolute "by design" security for handling hypersensitive citizen data.

### 🟢 Germano PD (Public Domain)
- Completely unlocked.
- Allows you to balance the power of AI filters and disable image censorship to optimize processing times on less powerful PCs.

---

## 🚀 Main Features

*   **100% Offline & Local:** Your data never leaves your office.
*   **Advanced Multi-Format Management:**
    *   📄 **PDF:** Textual censorship and *visual censorship* (draws obscuring black masks preserving the layout).
    *   📝 **DOCX / DOCM:** Anonymizes texts, tables, headers, and footers.
    *   📊 **XLSX / XLSM / XLS:** Obscures data in cells and even in comments, preserving any VBA Macros.
*   **Smart Censorship & RegEx:** Combines NLP Transformer (`openai/privacy-filter`) with local Regular Expressions (RegEx) (Email, Fiscal Codes, VAT, etc.).
*   **OCR and Integrated Biometrics:** Integrates `EasyOCR` to extract and censor texts in scans and `OpenCV` to automatically recognize and blur faces on ID photos.
*   **Hardware Acceleration:** Supports CPU, NVIDIA GPUs (CUDA), and AMD/Intel GPUs (via `torch_directml`).

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
Expects a JSON payload with the `{"text": "..."}` field and returns the anonymized text.

---

## 🤖 Cross-Platform AI Integration: Local API Proxy

Data anonymization is no longer limited to files! Germano AI includes a universal **Local API Proxy** (compatible with the OpenAI format) capable of acting as a total "shield" between your IDE (Cursor, Windsurf, Claude Code, Copilot, Antigravity) and the Artificial Intelligence.

### How the Total "Privacy Shield" works
Normally, the IDE sends everything you write in the prompt (or drag into the chat) directly to online servers.
By configuring your editor to point to Germano AI, the flow changes completely:

1. **Interception**: When you ask the AI something or attach a file, the IDE sends the request to Germano AI (running offline on your PC at port 8000).
2. **On-the-Fly Censorship**: Germano intercepts the request, extracts your text prompts, passes them instantly to the local privacy filter, and replaces sensitive data with labels (e.g. `[PERSON_1]`).
3. **Traceable Mapping**: The exact map of replaced words is saved in a JSON log in the `extracted` folder, allowing you to easily link the AI labels back to real data.
4. **Secure Forwarding**: Germano forwards the "purified" request to the real LLM provider (e.g. OpenAI). When the AI responds, it will in turn use the anonymized tags (e.g. "The contract is registered to [PERSON_1]").

The Artificial Intelligence will **never** come into contact with your original data, allowing you to use extremely specific prompts without violating the GDPR!

### How to Activate It (Manual Setup Required)

Because modern IDEs encrypt and secure their API keys and proxy configurations within internal databases, the integration cannot be automated via scripts for security reasons. It **must be done manually by the user within the software's graphical interface**. This is a safe, one-time operation that takes just a few seconds:

1. Start Germano AI by double-clicking on `START.bat`.
2. Open your preferred AI editor and change the AI server base address:
   - **Cursor**: Go to `Settings` -> `Models` -> Scroll to `OpenAI API Key` and insert your real key. Then, just below it, toggle on **Override OpenAI Base URL** and insert the following address: `http://127.0.0.1:8000/v1`.
   - **Windsurf / Antigravity / Other IDEs**: In the AI Provider settings (under OpenAI or Custom Provider), find the **Base URL** (or API Base URL / Custom URL) field and insert: `http://127.0.0.1:8000/v1`.
3. Make sure you enter your real OpenAI API Key in the editor. The IDE will send it to Germano AI, which will safely use it locally **exclusively** to forward the request to OpenAI's servers after finishing the anonymization of prompts and files!

### 🛡️ "Fail-Safe Privacy" (Hard Block Active)
Our API Proxy is designed with a zero-tolerance policy for errors (Hard Block). 
If for any reason (e.g., AI daemon crash, unreadable format, or corrupted image file) the privacy filter fails the scan, **the Proxy will NOT send your original data to the LLM**. The request will be instantly destroyed, and you will receive a red error message inside your editor. This guarantees that under no circumstances can your clear-text data leak to the internet due to a software malfunction.

---

## 📂 Working Folders Structure
- `/input`: Drag files here.
- `/output`: Anonymized files, with original format and layout intact.
- `/processed`: Original files moved at the end of the job.
- `/failed`: Corrupted, blocked, or unreadable documents.
- `/extracted`: JSON files with logs of what was replaced (for Audit).

## 📜 License and Contribution
This project is proudly distributed under the **GNU GPL v3** license. You can use it for free even for commercial purposes, as long as you keep any modifications Open Source. 
Are you a developer? Open a Pull Request! We want privacy to be a right accessible to everyone.

## 📞 Contacts
Do you need Enterprise support, custom integrations, or assistance?
- **Website**: [germano.ai](https://germano.ai)
- **Developed by**: [Yes Consulting](https://www.yesc.it/)
- **Email**: [info@germano.ai](mailto:info@germano.ai)
