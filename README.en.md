# 🛡️ Germano AI - Document Privacy, in the Era of Artificial Intelligence.

🌍 *Leggi questo documento in altre lingue: [Italiano](README.md)*

**💡 Example of Use:** *Do you want to use the power of an online LLM (chatgpt, gemini, claude, copilot, deepseek..) but your documents contain personal data that you do not want or cannot send to the AI (as per current regulations for the Public Administration)? Germano anonymizes this data for you. Germano is a local and offline Windows application (does not require internet access to work) that anonymizes your documents. germano.ai anonymizes text and faces and is compatible with the GDPR as well as being adaptable to specific privacy requirements; it integrates perfectly via plugins with the tools you already use: Claude Code, Google Antigravity, OpenCode, and all the others via plugins and MCP servers. In this way, the online AI will only receive as input the anonymized documents.

This is just one use case, germano.ai can be used in any situation where there is a large number of documents to anonymize, it supports many formats, returns the anonymized documents in the output folder, and is highly configurable.*

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

## 🤖 Cross-Platform AI Integration: Local API Proxy (New!)

Data anonymization is no longer limited to files! Germano AI now includes a universal **Local API Proxy** (compatible with the OpenAI format) capable of acting as a total "shield" between your IDE (Cursor, Windsurf, Claude Code, Copilot, Antigravity) and the Artificial Intelligence.

### How the Total "Privacy Shield" works
Normally, the IDE sends everything you write (or drag into the chat) directly to online servers.
By configuring your editor to point to Germano AI, the flow changes completely:

1. **Interception**: When you ask the AI something or attach a file, the IDE sends the request to Germano AI (running offline on your PC at port 8000).
2. **On-the-Fly Censorship**: Germano intercepts the JSON, extracts your text prompts and images, passes them instantly to the local privacy filter, and replaces sensitive data with labels (e.g. `[PERSON_1]`).
3. **Secure Forwarding**: Germano forwards the "purified" request to the real LLM provider (e.g. OpenAI).
4. **Real-Time De-Anonymization**: When the LLM responds (even in word-by-word *streaming* mode), Germano intercepts the response, swaps `[PERSON_1]` back with the original name on the fly, and returns it to the IDE.

The Artificial Intelligence will **never** come into contact with your original data, and you won't even notice the difference!

### How to Enable It
1. Start Germano AI by double-clicking on `START.bat`.
2. Open the settings of your preferred IDE or AI tool.
3. Set the **API Base URL** (or Custom URL) to: `http://127.0.0.1:8000/v1`
4. Enter your real OpenAI API Key normally (or Anthropic, if your client natively supports it on the OpenAI proxy). Germano will use it securely only to forward the request to the real servers.

*(Note: The old integration via MCP Plugin using the `INSTALL_AI_PLUGINS.bat` script is still available, but the API Proxy offers superior protection by intercepting the entire conversation).*

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
