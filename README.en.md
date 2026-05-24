# 🛡️ Germano AI - Document Privacy, in the Era of Artificial Intelligence.

🌍 *Leggi questo documento in altre lingue: [Italiano](README.md)*

Germano AI is a powerful open-source suite designed for **intelligent and massive document anonymization**. Based on local Artificial Intelligence engines, it guarantees total data privacy by processing files offline (without sending data to the cloud).

> Proudly developed in Italy by **[Yes Consulting](https://www.yesc.it/)**

---

## ⚡ Quickstart (How it works)

Germano AI works completely autonomously by "listening" to its folders. The basic operation is extremely simple:
1. Place the documents (and any subfolders) you want to anonymize inside the **`input`** folder.
2. Double-click the **`START.bat`** file to start the AI engine and open the Dashboard in your browser.
3. From the Dashboard, click on "START DAEMON". The software will take the files from `input`, redact them, and save the clean documents in the **`output`** folder, preserving your internal folder and subfolder structure intact.
4. The original files will be parked in **`processed`**, while any unsupported files will go to **`failed`**. 

💡 **Productivity Tip:** You can safely drag new files or entire folders into `input` *while the software is already working*! They will be queued and processed in real time without having to restart anything.

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

### Anonymization Endpoint
```http
POST http://127.0.0.1:8000/api/v1/anonymize
```
Directly returns the binary stream of the "clean" file. Check the **[Official Documentation](https://germano.ai/guide.html)** on our website for usage examples (cURL, Postman).

---

## 🤖 Cross-Platform AI Integration (Cursor, Windsurf, Claude Code, Copilot, Antigravity)

Document anonymization is no longer limited to the web Dashboard. Germano AI now includes an official integration suite designed to connect our local privacy engine directly with the most popular and powerful **AI Programming Assistants**. 

Leveraging the **Model Context Protocol (MCP)** standard (created by Anthropic and adopted industry-wide), we developed a universal Python plugin capable of acting as a "shield" between your files and Artificial Intelligence.

### How the "Privacy Shield" works
Normally, when you ask an AI like Claude, Antigravity or Cursor to "Read this document and summarize it", the AI uses its standard tools to read the entire original file in plain text and send it to its cloud servers.

By installing this plugin:
1. When the editor starts, the plugin connects in the background to Germano AI (starting the local `START.bat` daemon if it is not already active).
2. It provides the AI with a new tool called `read_anonymized_file`.
3. It dynamically teaches the AI a fundamental rule: **"Whenever the user asks you to read a file, you are forced to use read_anonymized_file instead of your standard reader"**.
4. When the AI invokes this tool, our local script takes charge of the original file, passes it to the local privacy filter, saves the redacted version locally and returns to the AI **only the anonymized data**.

The Artificial Intelligence will **never** come into contact with the original data!

### Super Easy Installation
You don't have to go crazy configuring JSON files manually. 
Double-click on the **`INSTALL_AI_PLUGINS.bat`** file (or run `python ai_plugins/install_ai_plugins.py` from the terminal).

An interactive program will open that will scan your computer looking for compatible editors (Cursor, Windsurf, VS Code, etc.) and will guide you step-by-step providing the exact configuration ready for copy-pasting, or in the case of Claude Code, it will install everything automatically with a single click. If it doesn't find compatible editors in the system, it will notify you with a clear message, still allowing you to force the configurations manually.

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
