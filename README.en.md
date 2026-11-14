# Germano AI - Document Privacy, in the Era of Artificial Intelligence.

 *Leggi questo documento in altre lingue: [Italiano](README.md)*

**Version 0.95** (November 14, 2026): MCP server and UTCP — Germano in input workflows (anonymization, inspection, leak checks) and output workflows (data restoration), for Claude, Antigravity, Cursor, n8n and agents. See [What's new in 0.95](#whats-new-in-095-mcp-server-and-utcp-germano-in-workflows) and the [CHANGELOG](CHANGELOG.en.md).

*<span style="color: #007bff; font-weight: bold;">Use Case 1</span>: You simply have a large number of documents to anonymize on your computer or server or NAS. Germano works in standalone mode and returns the anonymized documents; it supports many formats and is highly configurable. You simply copy the folder containing the files into input and receive the anonymized files in the output folder. Germano maintains the original directory and subfolder structure. Germano anonymizes text, prompts and faces and is compatible with the GDPR; Germano is a local and offline Windows application (does not require internet access to work).*

*<span style="color: #007bff; font-weight: bold;">Use Case 2</span>: Want to use the power of an online LLM (chatgpt, gemini, claude, copilot, deepseek..) but your documents or the text you write in the prompt contain personal data that you do not want or cannot send to the AI (as per current regulations for the Public Administration)? Germano anonymizes this data for you: with **Chatbot & AI Agents** you talk directly to the AI you prefer (and with the **Glass Window** you see in real time what reaches it), or it integrates as a Local API Proxy with the tools you already use that let you change the service address: Claude Code, Codex, OpenCode, Aider and the others. If you write "Mario Rossi" on the prompt, it notices and replaces it with [PERSONA_1] before it is sent to the online LLM. In this way, the online AI will only receive as input the anonymized documents and texts.*

Germano AI is a powerful open-source suite designed for **intelligent and massive document and text anonymization**. Based on local Artificial Intelligence engines, it guarantees total data privacy by processing files **100% offline** (without sending data to the cloud) and works out-of-the-box on a fresh **Vanilla Windows 11** installation without requiring internet access or pre-installed system runtimes.

> Proudly developed in Italy by **[Yes Consulting](https://www.yesc.it/)**

---

## Quickstart (How it works)

Germano opens on the **Chatbot & AI Agents** tab, where you talk to the AI you prefer and Germano masks personal data before it leaves. Next to it, the **Manual Sanitization & Vault** tab keeps all the batch work on files. The interface is fully bilingual (IT / EN).

1. Open **Germano AI** from the Desktop shortcut or the Start menu (Windows), from Launchpad or the Applications folder (macOS), or from the applications menu (Linux): it opens directly in a dedicated window (no black terminal windows, no external browser with navigation bars or tabs; the **red X** in the top right cleanly closes the entire application and all inference processes in the background). On first launch choose the operating mode (if in doubt keep **Standalone**: everything stays on your computer).
2. **Talk to an AI, protected:** choose the model **at the bottom right** (only the detected AIs can be selected: Claude Code, Antigravity CLI, the local models of Ollama, LM Studio and Jan, the services via API with a key; the others stay greyed out with the reason and, next to them, the **configuration assistant** button that installs or sets them up), type (**Enter** sends, **Shift+Enter** adds a new line) and attach files with the paperclip or by dragging them. The AI only receives the tags (e.g. `[PERSONA_1]`); the answer is streamed, with Markdown and highlighted code, already with your real data.
3. **Check with the Glass Window:** the **Glass Window** button at the top right opens a transparent panel that shows in real time everything sent to the model (original text, data intercepted by the privacy filter and the Vault, text actually sent, raw HTTP/CLI payload, answer stream) and lets you **stop the operation** at any moment.
4. **Anonymize files in bulk:** in the **Manual Sanitization & Vault** tab drag documents or whole folders onto the **input** box (or copy them into the **`input`** folder): Germano anonymizes them and saves the clean documents in **`output`**, with the same subfolder structure; originals go to **`processed`**, files that cannot be processed go to **`failed`** with the reason and a **Requeue** button. The four boxes are a live preview of the real folders, like a file manager.

 **Productivity Tip:** the protection engine starts by itself on the first send or when you add documents; while it is off no data leaves. You can add files *while the software is already working*: they are queued without restarting anything. **Export list** saves the list of ready or failed documents as CSV (for Excel), and the **«Manual text sanitization»** box anonymizes a text on the fly to paste into any AI (and restores the answer).

 **[DOWNLOAD GERMANO AI STANDALONE](https://download.germano.ai)**

---

## What's new in 0.95: MCP server and UTCP, Germano in workflows

Germano becomes a **tool** for other systems: Claude Desktop, Claude Code, Google Antigravity, Cursor, Windsurf, Visual Studio Code, Gemini CLI, n8n, agents and scripts use it **on the way in** (anonymize texts and documents, inspect personal data, stop leaks before anything leaves) and **on the way out** (restore the original data in the replies). Protection engine, local models and formats are those of 0.91.

- **MCP server** (Model Context Protocol) at `http://127.0.0.1:8181/mcp` (Streamable HTTP), `/mcp/sse` (SSE for n8n and older clients) and over **stdio** (`server.py --mcp-stdio`: it connects to the open Germano or works on its own). Revisions 2025-11-25, 2025-06-18, 2025-03-26 and 2024-11-05; 8 tools with input and output schemas, 4 resources and 3 prompts.
- **8 tools** — input: `germano_anonymize_text`, `germano_anonymize_file`, `germano_inspect_entities` (read-only), `germano_leak_check` (JSON payloads too); output: `germano_deanonymize_text`, `germano_deanonymize_file`; verify and status: `germano_workflow_roundtrip`, `germano_status`.
- **UTCP 1.0** at `/utcp` and `/.well-known/utcp.json`, **OpenAPI 3.1** at `/openapi.json` and new **REST APIs** `/api/v1/anonymize-text`, `/api/v1/leak-check`, `/api/v1/deanonymize-text`... sharing the same registry as the MCP tools.
- **Settings › MCP & UTCP integrations:** addresses and configurations to copy, **Connect with 1 click** to the clients found on the PC (with a backup of their file), Input → Output flow test, token for the network.
- **Security:** if the engine is not ready the request is blocked (never clear data presented as safe), the Vault is never listed and restoration covers only the placeholders present; from the network the integration token or a user session is needed and restoration covers only the data of one's own anonymization; file paths are limited to the allowed folders.

Details, tests (also with the official MCP and UTCP SDKs) and known limitations in the [CHANGELOG](CHANGELOG.en.md); full manual in the Guide, chapter 11.

---

## What's new in 0.91: AI configuration assistant

Next to every AI, in the model picker at the bottom right and among the **Detected AIs** in the Settings, a button tells what is missing to use it and does it with one click (**Install CLI**, **Sign in**, **Set up**, **Start**, **Install**, **Get a model**, **Retrieve key**); *Settings › AI, keys & Chatbot* also has the **Configuration assistant** panel. Protection engine, local models and formats are those of 0.90.

- **Google Antigravity CLI (`agy`) in the Chatbot & AI Agents:** *Install CLI* downloads Google's official CLI (SHA-512 digest and, on Windows, the «Google LLC» signature) and the CLI uses by itself the **account already signed in to Antigravity Desktop**, shared through the system keychain: Germano does not read or copy the tokens. The text leaves already protected, the CLI runs in an isolated profile without tools (if it announces one it is stopped) and the Glass Window states that the CLI's internal instructions go to Google without passing through the Proxy. With the CLI installed, while the Dashboard is open, Germano checks the sign-in and the account's models about every 10 minutes (`agy models`, toward Google, with no texts). Only for whoever uses this computer, never for network clients.
- **Qwen 4 Max and GLM 5.3:** new services **Qwen Token Plan (Qwen4-Max)** with `qwen4-max-preview`, **Qwen Coding Plan**, **GLM (Z.ai)** and **GLM Coding Plan** with `glm-5.3` (also in the Proxy and in the Remote Control). **Retrieve configuration** links **without copying them** the keys already set for Qwen Code, Claude Code, OpenCode, Codex, Gemini CLI or in the environment variables: the key is read when it is used.
- **Local models even when stopped:** Ollama, LM Studio and Jan show the models already downloaded on disk even when the service is stopped, with **Install Ollama**, **Start** and **Download a recommended model** (`qwen3.5:4b`, `gemma4:e4b`, `llama3.2:3b`, `qwen3.5:2b`).
- **Security:** the assistant only answers this computer (never from the network or the Remote Control), with anti-CSRF and the settings lock (`lock_settings`); downloads start only after your confirmation, over HTTPS and with a verified digest or signature; no key or token reaches the page.

Details, tests and known limits in the [CHANGELOG](CHANGELOG.en.md).

---

## What's new in 0.90: faster and parallel

0.90 works in parallel where it used to wait, without changing what is protected. Measured on the same PC (Intel i5-4570, 4 cores, 16 GB of RAM, no GPU) with the same files: the masked data match those of 0.80.

| Test | 0.80 | 0.90 |
|---|---|---|
| Digital PDF, 12 pages | 234.6 s | **132.0 s** (-44%) |
| System 2 on a document of 56 texts | 214.3 s (75 questions to the model) | **52.3 s** (22 questions) |
| Vault with 100,000 entries: save / read | 308 ms / 496 ms | **2 ms / 4 ms** |
| Transcription of 284 s of recordings | 107-126 s | **66 s** |
| Scanned page (faces, signatures, plates, OCR) | 29.6 s | **26.7 s** |

- **Parallel engine:** the Privacy Filter and the Italian NER analyze the same text together; each model has its own lock, so OCR, faces, signatures and plates serve different requests at the same time; the Italian NER and OCR load while the Privacy Filter loads.
- **Fast lane:** interactive requests (Chatbot & AI Agents, Proxy, REST API, Remote Control, network clients) go ahead of the documents queued in the `input` folder.
- **System 2 without redundant questions:** doubts about words already masked elsewhere in the document are no longer asked to the local model (70% of the questions on the test corpus); a question that is not asked always stays masked.
- **Documents in batches:** scanned PDFs in windows of 8 pages and Office document images in batches, analyzed in a single call.
- **Vault on SQLite (WAL):** `extracted/deanonymize_vault.db` with incremental writes and reads, plus the portable copy `deanonymize_vault.json` in the usual format.
- **Files by path and caches:** between server and engine files travel by path (no base64); history and attachments already protected come from the Proxy cache.
- **Batched audio:** recordings of 60 seconds or longer are transcribed by Whisper in batches of 8 segments.
- **Parallel, verified Client:** up to three files together on the Germano Server, which is tested with fake data when connecting and every 10 minutes.
- **Hardened Proxy:** tool arguments of AI agents are anonymized too (`tool_use.input`, `function.arguments`, `functionCall.args`), with a final check that blocks the request if a detected item stayed in clear.
- **Linux and macOS aligned:** sources and `.deb` / `.pkg` packages are identical again to the Windows ones in all common files.

Full details and measurements in the [CHANGELOG](CHANGELOG.en.md).

---

## Multiplatform Installation

All official installers are single ready-to-use files on **[download.germano.ai](https://download.germano.ai/)** and contain everything needed: the program, its own Python with all libraries and (in the full suite) the 8 AI models. Installation downloads nothing from the Internet and works on a freshly installed system.

| System | Full suite | Lightweight client |
|---|---|---|
| Windows 10/11 and Windows Server 2019/2022/2025 64-bit (also in a virtual machine) | `germano-0.95.exe` | `germano-client-0.95.exe` |
| macOS | `germano-0.95.pkg` (Apple Silicon, macOS 14 or later) | `germano-client-0.95.pkg` (Apple Silicon and Intel, macOS 11 or later) |
| Linux Ubuntu/Debian 64-bit | `germano-0.95.deb` | `germano-client-0.95.deb` |

### Windows (10 / 11 64-bit)
1. **Download:** download `germano-0.95.exe`.
2. **Installation:** double-click the installer. **As soon as it opens it asks for administrator permission** (Windows UAC prompt: choose **Yes**): it is needed to allow access from the local network, always enabled, with a Windows Firewall rule that only applies to Germano's Python and only to private and domain networks (Server LAN mode). The program installs for the current user into `%LOCALAPPDATA%\Programs\Germano AI`, with the Desktop and Start menu shortcuts, the entry in Settings > Apps and the working folders in `Documents\Germano AI`; at the end the installer window closes and **Germano AI opens by itself**, with the user's normal permissions. The Microsoft Visual C++ libraries are already included: nothing else to install.
3. **Launch:** **Germano AI** shortcut on the Desktop or in the Start menu (dedicated window, no black terminal windows).
4. **Uninstall:** Settings > Apps > Installed apps > Germano AI (it asks for administrator permission to remove the firewall rule); you can choose whether to keep the working folders and the Vault.

### Windows Server and virtual machines
- **Windows Server 2019, 2022 and 2025** (Standard and Datacenter) and **VMware, Hyper-V, Proxmox VE (KVM), VirtualBox** and cloud (AWS, Azure, Google Cloud) virtual machines: no GPU and no redistributable to install (the Visual C++ DLLs are included). 12 GB of RAM and 4 vCPUs recommended: threads adapt to the vCPUs and precision to the processor (FP32, or BF16 with little RAM).
- **Without a window** (servers, Server Core, scheduled tasks): `Germano.exe --no-browser --mode=server` starts server and engine with no windows and writes the local and network addresses to the log and the console; `Germano.exe --stop` stops it. On Windows Server 2019, which has no Microsoft Edge, Germano offers by itself to stay active this way (Internet Explorer is not used).
- **Network**: the firewall rule applies to private and domain networks; if an adapter is classified as «Public» (common in VMs), if the rule is missing or if Group Policy ignores local rules, the server Dashboard reports it with the command to fix it. In VMs with NAT networking you need TCP port 8181 forwarding or a bridged adapter.

The full suite installer is about 3.8 GB (it contains all the AI models): on the first double-click Microsoft Defender scans it, so the window may take a few seconds to appear. The installer is not digitally signed yet: if "Windows protected your PC" appears, choose **More info > Run anyway**.

### macOS
1. **Download:** download `germano-0.95.pkg`. The full suite requires a Mac with **Apple Silicon** (M1 or later) and **macOS 14 Sonoma** or later, because PyTorch is no longer published for Intel Macs; on Intel Macs use the lightweight client `germano-client-0.95.pkg`.
2. **Installation:** double-click the package. When choosing the destination select **Install for me only**: `Germano.app` goes into `~/Applications` **with no administrator password**. With "Install for all users of this computer" it goes into `/Applications` and macOS asks for the password. At the end Germano opens by itself.
3. **Launch:** open **Germano** (`Germano.app`) from Launchpad or the Applications folder. On first launch it creates the working folders in `~/Documents/Germano AI` (in `~/Germano AI` if Documents is synced with iCloud).
4. **Uninstall:** drag `Germano.app` to the Trash; the working folders stay where they are.

The package is not signed by Apple yet: if macOS blocks it, go to **System Settings > Privacy & Security** and choose **Open Anyway**.

### Linux (Ubuntu / Debian 64-bit)
1. **Download:** download `germano-0.95.deb`, designed for **Ubuntu 26.04 LTS** and suitable for Debian-based distributions with glibc 2.34 or later (Ubuntu 22.04 or later, Debian 12 or later).
2. **Installation:** double-click the file (App Center) or run `sudo apt install ./germano-0.95.deb` in a terminal. As with any system package, the administrator password is required. The program goes into `/opt/germano`, with the **Germano AI** entry in the applications menu and the `germano-ai` command; no other packages are needed.
3. **Launch:** from the applications menu. On first launch it creates the working folders in `Documents/Germano AI` (the Documents folder in the system language).
4. **Uninstall:** `sudo apt remove germano-ai`; the working folders stay where they are.

---

## Compliance Profiles (PA vs PD)

Germano AI is designed to adapt to both highly regulated environments and private professionals through two specific profiles selectable in real time from the Dashboard:

### Germano PA (Public Administration)
- **GDPR** & **CAD** compliant.
- No possibility for the operator to disable crucial security filters like OCR, facial biometrics, or personal data categories.
- Absolute "by design" security for handling hypersensitive citizen data.

### Germano PD (Public Domain)
- Completely unlocked and customizable in real time (Hot-Reload without restarting the daemon).
- Allows you to balance the AI filter threshold and individually toggle the 18 data categories and the 6 AI models (e.g. turn off image scanning) to optimize processing times.

---

## Architecture & Operating Modes (Tri-Mode & Dual Mode)

Germano AI implements a modular hybrid architecture, selectable on initial launch and configurable at any time in Settings (taking effect immediately, zero restarts required):

### Three Native Operating Modes:
*   **Standalone (Default & 100% Offline):** everything runs locally on this computer in complete isolation. Zero open ports to the external network and zero client discovery. The local AI models load into local memory, the de-anonymization Vault remains on local disk, and zero packets leave the workstation.
*   **LAN Server (Shared Inference Engine):** Germano listens on the local network (default port **8181**) and responds to UDP broadcast auto-discovery (port **8182**). It exposes the local inference engine, the AI Proxy and the **Remote Control** (from any browser on the network, nothing to install) to the workstations and devices of the office or studio: open access by default, or **user name and password** when the administrator enables user management. Launches directly via `Germano.exe`.
*   **Client (Lightweight Germano Client ~28 MB):** an agile, portable executable designed for laptops or workstations with limited resources. On launch, it automatically discovers the LAN Germano Server and offloads heavy model inference. **Original documents, anonymized files, and the de-anonymization vault strictly reside on the client workstation**: if the server is unreachable, zero data leaves the client and documents remain queued.
*   **Server + Client together:** the host workstation shares inference across the LAN while concurrently processing its own local queue.

### Interface: Chatbot & AI Agents, plus manual sanitization
*   **Four tabs at the top:** **Chatbot & AI Agents** (default), **Manual Sanitization & Vault**, **Settings**, **Guide**. The same interface is in the **Remote Control** (browsers of the network devices) and in **Germano Client**. Dark theme (`#0b0f19`, `#0f172a`, `#1e293b`, accents `#38bdf8` and `#818cf8`).
*   **Chatbot & AI Agents:** conversations in the sidebar (search, rename, delete, export to Markdown), instructions for the assistant, streamed answers with Markdown, syntax highlighting and **Copy code**, indicators for time, tokens, masked and restored data, a composer that grows with the text (Enter / Shift+Enter), attachments with paperclip or drag & drop, protection indicator and the **model picker at the bottom right**: automatic detection every 12 seconds of the installed AIs (Claude Code, Antigravity CLI, Ollama, LM Studio and Jan with every installed model and, when the service is stopped, with the models already downloaded on disk, services via API such as OpenAI, Anthropic, Meta Muse, Kimi, DeepSeek, Qwen and Qwen 4 Max, GLM 5.3 by Z.ai, Mistral, Grok, Perplexity, Gemini, OpenRouter and Groq); only the usable ones can be chosen, the others (Cursor, Antigravity Desktop, Windsurf, agents that would run commands…) stay greyed out with the reason and, when possible, with the **configuration assistant** button (Install CLI, Set up, Start, Get a model, Retrieve key).
*   **Glass Window (Transparent Inspection):** a frosted-glass panel that shows in real time the five phases of every request (original text, privacy filter and Vault mappings, text actually sent, raw HTTP/CLI payload with keys masked, answer stream before restoration), with **Stop operation** (it closes the connection to the service or terminates the CLI: «Operation stopped by the user via Glass Window: no further data was transmitted or received.»), optional review before sending (**Send now**/ **Block sending**) and protection preview while typing.
*   **Manual Sanitization & Vault:** massive batch processing with the four `input`, `output`, `processed`, `failed` boxes like a file manager, real-time metrics (files/min, redacted PII, CPU/RAM), failure reasons with **Requeue**, CSV export, manual text sanitization and the mapping archive (Vault).
*   **100% Bilingual Interface & Contextual Tooltips (Italian / English):** automatic language detection (`it` -> Italian, otherwise English), IT / EN toggle in the top bar and hover tooltips, which can be turned off in Settings.

---

## Remote Control: Germano from any device on the network, nothing to install

With **Server** mode on, from a Windows, Mac or Linux PC, a tablet or a smartphone on the same local network just open the browser at **`http://<server-IP>:8181/`** (the Remote Control opens, also at `/remote`; the exact addresses are in the server Settings). Like Google Antigravity's Remote Control, the work stays on the server: the device is a secure window, with **the same interface as the Dashboard** (Chatbot & AI Agents, Manual Sanitization, Settings, Guide). Germano Client shows the same page on the network PCs.

- **Chatbot & AI Agents with the Glass Window:** at the bottom right you choose one of the **server's AIs, detected automatically** — the shared CLIs (run by the server without tools: agents that would run commands or edit files on the server are never run for clients, and Antigravity CLI, which uses the Google account of whoever sits at the server, stays for that person only), the **AI services via API** filtered by Germano (Meta Muse with Muse Wonder and Muse Spark, Kimi, DeepSeek, Qwen also with Qwen 4 Max, GLM 5.3 by Z.ai, Mistral, Grok, Perplexity, Google Gemini, OpenAI, Anthropic, OpenRouter, Groq) and the **server's local models** (Ollama, LM Studio, Jan: no data leaves the local network). The prompt and up to **12 attachments** are anonymized by the server engine before leaving; the answer is streamed back with the original data **of that request only**, and the Glass Window shows every step from here too, with **Stop operation**. API key: the user's own (it stays on the device, the server does not save it) or the server's, if the administrator shares this computer's AIs.
- **Manual Sanitization:** files dragged in and returned anonymized in their format, restoration of a file returned by an AI, protected text to copy into any AI and restoration of the answer, always with the mappings kept only on the device.
- **Client processing options** (in Settings): confidence threshold, active models, the 18 personal data categories, masking (numbered tags `[PERSONA_1]`, restorable; generic tags `[PERSONA]` or blackout `████`, irreversible). They apply only to that device's requests, never to the server configuration. **With the PA profile (or `lock_settings`) they are disabled and greyed out**, and the server rejects any change with `403 Forbidden` (Compliance Lock).
- **Connect the device's tools:** the Proxy addresses to use as Base URL: `/v1` (OpenAI format), the root (Anthropic format) and `/p/<service>/v1` for Meta, Kimi, DeepSeek, Qwen, GLM (Z.ai), Mistral, Grok, Perplexity, Gemini, etc.

**User management (optional).** By default network access needs no credentials. In the server Dashboard, Settings › Mode & network › Network access, the administrator can create one or more users and enable sign-in with **user name and password**: it applies to the Remote Control in the browser (sign-in screen, `HttpOnly` session cookie) and to Germano Client (`client login`). Passwords are stored only as a **PBKDF2-SHA256** hash (600,000 iterations, random salt); sessions last 30 days from last use and are closed when the password changes or the user is deleted; after 5 wrong attempts the address is blocked for 10 minutes. From the server computer (127.0.0.1) administration never needs credentials.

**Security.** From the network, data restoration only covers the tags of the request itself: no device can get back the data of other Vault documents (not even by asking an AI to "repeat [PERSONA_1]"). The full Dashboard, settings, Vault and files stay accessible only from the server. On the local network the connection is plain HTTP, not encrypted: use Germano on trusted networks.

---

## Main Features

*   **100% Offline & ready on a freshly installed system:** every installer bundles its own Python 3.11 with all libraries (on Windows also the 64-bit Microsoft Visual C++ libraries, next to the interpreter: no redistributable to install), an offline Web UI free of external CDNs, and **8 pre-installed local AI models**.
*   **All settings in one place:** **Mode & network** (Standalone, Server, Client, network access, user management), **Protection & models** (compliance profiles, sensitivity, **18 categories and 7 analysis engines**: Names, Professions/Titles, Addresses, Cadastral, Tax Codes/VAT, Email/PEC, Phone Numbers, IBAN/Bank accounts, Amounts/Finance, Dates, Companies/Entities, License Plates/IDs, Health Data (GDPR Art. 9), Medications/Therapies, Judicial Data (GDPR Art. 10), Marital Status, Passwords/Secrets, and URLs/IPs), **AI, keys & Chatbot** (detected AIs, keys and, since 0.91, the Configuration assistant), **Proxy & APIs** (Proxy URLs, per-tool setup, target services, REST examples), **MCP & UTCP integrations** (since 0.95: MCP, UTCP and OpenAPI addresses, 1-click connection to the clients, Input → Output flow test, network token), **System & log**, **Updates** (like Google Chrome's «About» page) and **About Germano**.
*   **Complete Offline Guide & Technical Documentation:** *"Guide"* tab integrated into the Dashboard (available at `/guide` and as standalone file `GUIDA_OFFLINE.html`), fully bilingual (Italian and English), featuring step-by-step guides, 5-folder workflow breakdown, REST API specifications, and setup instructions for Google Antigravity (also Antigravity CLI with the same account), OpenAI Codex, Cursor, and Claude Code.
*   **Automatic De-Anonymization via API Proxy and Internal Folders:** When *"Ripristino automatico dei dati originali"* (Automatic data restoration) is active (default), Germano logs entity mappings in the local Vault (`extracted/deanonymize_vault.db`, with the portable copy `deanonymize_vault.json`). In API Proxy integrations (`/v1/chat/completions`, `/v1/responses`, `/v1/messages` for **Claude Code, Codex, OpenCode, Aider** and the other tools that accept a service address) and in the local `input/` folder, AI responses and returned documents are **automatically de-anonymized** with their true original values.
*   **8 Integrated 100% Offline AI Models (`models/`):**
    1. **Velvet Privacy Filter (1.5B, BF16 weights):** Multilingual contextual Transformer model for PII (based on OpenAI Privacy Filter, Apache-2.0 license).
    2. **Italian NER XXL v2 (58 classes):** Specialized NER model for legal, medical, banking, cadastral, and administrative Italian documents.
    3. **EasyOCR (CRAFT + Latin G2):** Local Optical Character Recognition on scanned PDFs and photos.
    4. **YuNet Face Detector (OpenCV 5 DNN):** Biometric face detection and redaction (`[VOLTO]`).
    5. **YOLOS-Tiny Signature Detector:** Visual detection and redaction of handwritten signatures (`[FIRMA]`).
    6. **YOLOS-Small License Plate Detector:** Visual detection and redaction of vehicle license plates (`[TARGA]`).
    7. **Whisper Small INT8 (CTranslate2, 240 MB):** offline transcription of audio recordings, in batches for long ones.
    8. **Qwen3.5-0.8B (GGUF Q8_0, 812 MB, run by llama.cpp) - System 2:** decides doubtful recognition cases in context: it leaves a doubtful item in clear only when it is sure it is not personal data, otherwise it stays masked.
*   **Advanced Multi-Format Management with Layout Preservation:**
    *   **PDF & PDF Portfolios:** Character-level redaction, OCR and *visual redaction* on scans (including stamped scans), form fields, comments, bookmarks, metadata, and recursive redaction of embedded attachments. PAdES digital signatures cleanly stripped to prevent visual validation conflicts.
    *    **Images (`PNG`, `JPG`, `JPEG`, `BMP`, `TIFF`, `WEBP`, `GIF`):** Local OCR and visual redaction of faces, signatures, and license plates retaining original dimensions and resolution; EXIF/GPS metadata removed.
    *    **Word (`DOCX`, `DOCM`, `DOC`, `RTF`) & OpenDocument (`ODT`, `ODS`, `ODP`):** Anonymizes and de-anonymizes body text, tables, headers, footers, footnotes, text frames, comments, speaker notes, and embedded objects without altering document layout, fonts, bolding, or images. `DOC`/`PPT` require Microsoft Office or LibreOffice (unless renamed RTF/DOCX/HTML).
    *    **Spreadsheets & Presentations (`XLSX`, `XLSM`, `XLS`, `CSV`, `TSV`, `PPTX`, `PPT`):** Redacts and restores cell data, sheet names, charts, slides, presenter notes, and comments, preserving underlying formulas and VBA Macros.
    *   **Audio & Offline Speech Transcription (`MP3`, `WAV`, `M4A`, `OGG`, `FLAC`, `OPUS`, `AAC`, `WMA`, `AMR`, `AIFF`):** 100% offline speech-to-text transcription powered by bundled **Whisper Small INT8** (240 MB), ID3/Vorbis/MP4 metadata sanitization, and generation of redacted `<name>.trascrizione.txt` transcripts with `[hh:mm:ss]` timestamps.
    *   **Web, Data, Email & Compressed Archives (`HTML`, `XML`/FatturaPA, `JSON`, `EML`, `P7M`, `ZIP`, `7Z`, `RAR`, `TAR`, `GZ`, `BZ2`, `XZ`):** Native DOM/MIME handling, email attachment recursion, PKCS#7 signed file parsing (`.p7m`), and hardened recursive archive extraction (with bundled **7-Zip** and Path-Traversal / Zip-Bomb protection up to 4 GB) preserving the original folder hierarchy.
*   **Reliability & Concurrency:** parallel engine with one lock per model and a fast lane for interactive requests, Vault on SQLite in WAL mode protected from concurrent access, file processing only after copy completion, and clean graceful shutdown.

**Requirements:** 64-bit Windows 10/11 or Windows Server 2019 or later (also in a virtual machine), macOS 14 or later on Apple Silicon, or 64-bit Ubuntu/Debian Linux; 8 GB RAM (16 GB recommended), at least 4 processors or vCPUs and about 6 GB of free disk space (plus the space for your documents); no GPU needed. On Windows the suite installer asks for administrator permission as soon as it opens (firewall rule for local network access; the client does not ask for it); on macOS ("Install for me only") it is not needed; on Linux, as for any .deb package, the administrator password is required.

## REST API Integration

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

### MCP server, UTCP and workflow APIs (since 0.95)
```http
POST http://127.0.0.1:8181/mcp                     # MCP server (Streamable HTTP; SSE at /mcp/sse; stdio: server.py --mcp-stdio)
GET  http://127.0.0.1:8181/utcp                    # UTCP 1.0 manual (also /.well-known/utcp.json)
GET  http://127.0.0.1:8181/openapi.json            # OpenAPI 3.1
POST http://127.0.0.1:8181/api/v1/anonymize-text   # and anonymize-file, inspect-entities, leak-check,
                                                   # deanonymize-text, deanonymize-file, workflow-roundtrip
```
The same 8 tools in MCP, UTCP, OpenAPI and REST: on the way in they anonymize, inspect and check for leaks, on the way out they restore the original data only for the placeholders present. From this computer no key is needed; from the network (Server mode) `Authorization: Bearer <token>` is required with the token of *Settings › MCP & UTCP integrations*. JSON-RPC, curl, n8n and Python examples in the Guide, chapter 11.

---

## Cross-Platform AI Integration: Local API Proxy

Data anonymization is no longer limited to files! Germano AI includes a universal **Local API Proxy** (compatible with the OpenAI format) capable of acting as a total "shield" between the tools that let you change the service address (Claude Code, Codex, Aider, Qwen Code, OpenCode, Continue, the SDKs) and the Artificial Intelligence.

### How the Total "Privacy Shield" works
Normally, the IDE sends everything you write in the prompt (or drag into the chat) directly to online servers.
By configuring your editor to point to Germano AI, the flow changes completely:

1. **Interception**: When you ask the AI something or attach a file, the IDE sends the request to Germano AI (running offline on your PC at port 8181).
2. **On-the-Fly Censorship**: Germano intercepts the request, extracts your text prompts, passes them instantly to the local privacy filter, and replaces sensitive data with indexed labels (e.g. `[PERSONA_1]`).
3. **Traceable Mapping**: The exact map of replaced words is saved in a daily log (`extracted/proxy_sessions/YYYY-MM-DD.jsonl`), allowing you to easily link the AI labels back to real data.
4. **Secure Forwarding**: Germano forwards the "purified" request to the real LLM provider (e.g. OpenAI). When the AI responds, it will in turn use the anonymized tags (e.g. "The contract is registered to [PERSONA_1]").

The Artificial Intelligence will **never** come into contact with your original data, allowing you to use extremely specific prompts without violating the GDPR!

### How to Activate It (Manual Setup Required)

In **Settings › Proxy & APIs** the Dashboard shows the addresses to copy and, tool by tool, where to set them (or why a tool cannot be protected).

1. Start Germano AI (Desktop shortcut or Start menu on Windows, Launchpad on macOS, applications menu on Linux).
2. Configure the tool so that it uses Germano as the service base address:
   - **Claude Code**: before starting it, set `ANTHROPIC_BASE_URL=http://127.0.0.1:8181` (in PowerShell: `$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8181"`).
   - **OpenAI Codex CLI**: set `OPENAI_BASE_URL=http://127.0.0.1:8181/v1`.
   - **Aider, Qwen Code, OpenCode, Continue, OpenAI and Anthropic SDKs**: set the Base URL to `http://127.0.0.1:8181/v1` (OpenAI format) or `http://127.0.0.1:8181` (Anthropic format).
   - **Cursor, Google Antigravity, Windsurf, Claude Desktop**: **cannot be protected** with the Proxy (they build prompts on their own servers or do not accept a local address): to work protected use Germano's **Chatbot & AI Agents**. For Antigravity, since 0.91 the configuration assistant installs **Antigravity CLI**, which in the Chatbot & AI Agents uses the same account as Antigravity Desktop. Since 0.95 these tools can use Germano as an **MCP server** (see *MCP server, UTCP and workflow APIs*): their chat does not become protected, but the agent can anonymize documents before reading them, check what it sends and write restored results to files.
3. Make sure you enter your real API Key (OpenAI or Anthropic) in the tool. The tool will send it to Germano AI, which will use it locally **exclusively** to forward the request to the service after finishing the anonymization of prompts and files.

### "Fail-Safe Privacy" (Hard Block Active)
Our API Proxy is designed with a zero-tolerance policy for errors (Hard Block). 
If for any reason (e.g., AI daemon stopped, unreadable format, or corrupted image file) the privacy filter fails the scan, **the Proxy will NOT send your original data to the LLM**. The request will be instantly destroyed, and you will receive an error message inside your editor. This guarantees that under no circumstances can your clear-text data leak to the internet due to a software malfunction. Since 0.90 the tool arguments of AI agents are anonymized too (`tool_use.input`, `function.arguments`, `functionCall.args`) and a final check blocks the request (error `422`, nothing is sent) if a detected item stayed in a field that Germano cannot anonymize.

---

## Silent updates, like Google Chrome

By default Germano updates itself **silently**, with no windows or notices interrupting your work and without giving up offline operation:

1. **Only when the system reports that the PC is connected to the Internet** (about 20 seconds after startup and then every 6 hours), Germano checks `https://download.germano.ai/version.json` (the only update source). On a disconnected PC no connection attempt is made.
2. If a newer version exists, the official installer (`germano-<version>.exe`) is downloaded **in the background at low priority** into the user's technical folder (`%LOCALAPPDATA%\Germano AI\update`), checking its size and structure (files on `download.germano.ai` are considered trustworthy: no manual verification).
3. On Windows the installer prepares the new version right away, silently and at low priority, in a folder next to the program's one (`Germano AI.nuovo`), while Germano stays open and the version in use is not touched.
4. At the **next start** the new version replaces the old one in a few seconds and Germano opens already updated. Whoever wants to apply it right away only finds a discreet **«Restart to update»** at the top. Working folders in `Documents\Germano AI`, the Vault (`extracted\deanonymize_vault.db` and the copy `deanonymize_vault.json`) and the preferences `config.json` stay intact; if anything goes wrong, the version in use stays.

**Settings › Updates**, like Chrome's «About» page, shows the status: «Germano AI is up to date (v0.95)» with the time of the last check, «Downloading the update in the background…» with the progress bar, «Restart Germano to apply the update». On macOS and Linux the `.pkg` / `.deb` package is downloaded the same way and opened with the system installer when you decide. Germano Client updates itself the same way.

Options (in Settings or in `config.json`): `"auto_update": false` only reports the new version, `"check_updates": false` disables the check. No document or text data is sent during the check.

---

## Working Folders Structure

To guarantee maximum security, avoid administrator permission conflicts (UAC), and prevent unintended cloud synchronization of unencrypted data, Germano's working folders reside in the user's personal directory (`Documents\Germano AI` on Windows, `~/Documents/Germano AI` on macOS and Linux):

- `Documents\Germano AI\input`: Drag files here to process.
- `Documents\Germano AI\output`: Anonymized files, with original format and layout intact.
- `Documents\Germano AI\processed`: Original files archived at the end of the job.
- `Documents\Germano AI\failed`: Corrupted, blocked, or unreadable documents (listed in the *Non riusciti* tab with the reason).
- `Documents\Germano AI\extracted`: JSON audit log files (for GDPR compliance) and the **Vault**, the table that maps the tags (`[PERSONA_1]`...) to the original data and allows restoring it: since 0.90 it is an SQLite database (`deanonymize_vault.db`) with the portable copy `deanonymize_vault.json` in the usual format. The Vault is local and **is not encrypted**: protect it like the original documents (it stays on this computer and is never sent to any service).


---

## Developer Guide: Running from GitHub Sources

This GitHub repository contains **exclusively clean source code and assets**. To keep the repository lightweight (< 30 MB) and fast to clone, heavy neural models and binary runtimes are **not committed to Git**.

### What to download before running from source:

1. **AI Models (`models/`):**
   - Germano requires the 8 local AI models (privacy-filter, NER, EasyOCR, YuNet facial biometrics, license plate and signature detection, Whisper for audio and Qwen3.5 for System 2).
   - All 8 AI models are bundled inside the official Germano AI installers: for development from source, copy the `models/` folder from the installed application into your chosen platform directory (e.g. `windows/germano/models/` or `linux/germano/models/`).
   - *Alternatively:* you can extract the `models/` folder directly from any official installer package on [download.germano.ai](https://download.germano.ai).

2. **System Dependencies & Runtimes:**
   - **Windows:** Requires 64-bit Python 3.11+ and the **[Microsoft Visual C++ Redistributable 64-bit](https://aka.ms/vs/17/release/vc_redist.x64.exe)** (`vc_redist.x64.exe`).
   - **Linux:** Requires Python 3.11+ (`sudo apt install python3 python3-pip python3-venv`).
   - **macOS:** Requires Python 3.11+ (Apple Silicon or Intel).

### How to start development in 4 steps:

```bash
# 1. Clone the repository and navigate to your target platform
git clone https://github.com/germano-ai/germano-ai-standalone.git
cd germano-ai-standalone/windows/germano  # or linux/germano or macos/germano

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Place the downloaded 'models/' folder into the current directory and start:
python server.py
```
To run the lightweight client instead:
```bash
cd germano-ai-standalone/windows/germano-client
pip install -r requirements.txt
python client.py
```

### Building the installers

Every release has the same structure: `sorgenti/{windows,linux,macos}/{germano,germano-client}` (the content of this repository), `modelli/` (the 8 models), `dipendenze/{windows,linux,macos}` (Python and libraries for each system, llama.cpp, 7-Zip) and `releases/`. The scripts in `windows/germano/build/` run on Windows with the runtime's Python, with `-B` (no cache in the sources), and produce the six self-contained packages:

```bash
python -B build/coerenza_sorgenti.py                    # Linux and macOS sources identical to the Windows ones in common files
python -B build/costruisci_installer_windows.py tutti   # releases/windows/germano-0.95.exe and germano-client-0.95.exe
python -B build/costruisci_deb.py tutti                 # releases/linux/germano-0.95.deb and germano-client-0.95.deb
python -B build/costruisci_pkg.py tutti                 # releases/macos/germano-0.95.pkg and germano-client-0.95.pkg
python -B build/crea_version_json.py                    # releases/version.json: sizes and SHA-256 read from the files
```

The `.deb` and `.pkg` builders stop if the Linux or macOS trees are not aligned with the Windows sources (the reference); the Windows suite installer must stay below 4 GB, the limit of Windows executables, and the builder checks it. `version.json` is published on download.germano.ai last, after the six packages.

## License and Contribution
This project is proudly distributed under the **GNU GPL v3** license. You can use it for free even for commercial purposes, as long as you keep any modifications Open Source. 
Are you a developer? Open a Pull Request! We want privacy to be a right accessible to everyone.

## Contacts
Do you need Enterprise support, custom integrations, or assistance?
- **Website**: [germano.ai](https://germano.ai)
- **Developed by**: [Yes Consulting](https://www.yesc.it/)
- **Email**: [info@germano.ai](mailto:info@germano.ai)
