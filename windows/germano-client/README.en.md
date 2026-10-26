# 🛡️ Germano AI Client

👉 *Read this in other languages: [Italiano](README.md)*

**Germano AI Client** is the ultralight (~26 MB) companion application built to connect any workstation (laptop, standard office PC) to a **Germano Server** running on your local network (LAN).

It requires no heavy AI models or dedicated GPUs on your local machine: all computational load, OCR, and AI inference are offloaded to the centralized LAN Server, while all original documents and the de-anonymization Vault remain strictly and sovereignly on your local PC.

---

## ⚡ Key Capabilities

1. **Automatic LAN Server Discovery (UDP 8182 Broadcast)**:
   Upon startup, the Client automatically discovers active Germano Servers across the local subnet and connects: open access by default, or **user name and password** (`client login`) when user management is enabled on the server. The Client keeps only the session, never the password.
2. **Server AI Models & Harness Exposure**:
   The Client queries the Server and lists the AIs detected on the server (Claude Code, Codex, Gemini CLI, Meta Muse Code, Kimi Code, Qwen Code, DeepSeek, Mistral Vibe, Grok Build, Perplexity, GitHub Copilot CLI, Cursor, Kiro, OpenCode, Aider, Ollama, LM Studio...) and the **AI services via API** filtered by Germano (Meta Muse Wonder and Muse Spark, Kimi, DeepSeek, Qwen, Mistral, Grok, Perplexity, Gemini, OpenAI, Anthropic and the server's local models). With the protected chat you use them directly from your seat, even if they are not installed locally.
3. **Same interface as the Remote Control**:
   The Client panel is the same Remote Control the Server offers to any browser on the network (AIs, protected chat with up to 12 attachments, protect and restore, options, tool connection): Client users and browser users have the same capabilities. On top of that the Client discovers the server on the network and launches this PC's CLIs protected.
4. **Processing options of this PC**:
   Confidence threshold, active models, 18 personal data categories and masking (`client options`), valid only for this PC's requests. **With the server's PA profile they are locked and greyed out** (the server rejects any change: Compliance Lock).
5. **Transparent Proxy Routing for Local AI Agents**:
   For AI tools installed on your local PC, it automatically configures environment variables (`ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`) routing traffic through the Server's Privacy Proxy with transparent round-trip de-anonymization; for tools configured by hand (Kimi, Mistral Vibe, Muse Code, OpenCode...) it shows the exact address, also per service (`/p/<service>/v1`).
6. **Document & File Protection**:
   Protects text and documents on the fly prior to transmission: only masked tags (`[PERSONA_1]`, `[TAX_ID_1]`, etc.) leave towards the AI, guaranteeing absolute GDPR compliance.
7. **Dedicated Native Window Interface**:
   Runs as a dedicated native desktop window (no black terminal windows, no generic browser address bars) as well as an extensible command-line interface (`client.py`) for automation.

---

## 🏗️ Architecture Flow

```
  [ Client Seat: Laptop / Standard PC ]
     │  GUI (Remote Control) or CLI (Claude Code / Codex / Aider / Qwen Code)
     │  Open access, or the user's session when user management is enabled
     ▼
  [ GERMANO SERVER on LAN :8181 ]  (Workstation hosting the 6 local offline AI models)
     1. Receives requests and applies local offline privacy models
     2. Masks prompts and documents (replacing PII with deterministic tags)
     3. Keeps the mappings in the server's Vault
     4. Forwards strictly anonymized payloads to the target LLM
     5. Restores the original data of THAT request on the return trip and delivers cleartext to Client
```

---

## 📦 Multiplatform Installation

The official Client installers are single files on **[download.germano.ai](https://download.germano.ai/)** and bundle their own Python with all libraries: installation downloads nothing from the Internet. The client creates no working folders in Documents: its settings (server address, session, options) stay in the user's technical folder.

### 🪟 Windows (10 / 11 64-bit)
1. **Download:** download `germano-client-0.60.exe` (about 22 MB).
2. **Installation:** double-click the installer. It installs for the current user into `%LOCALAPPDATA%\Programs\Germano AI Client` **without administrator privileges (no UAC prompt)**, with Desktop and Start menu shortcuts and the entry in Settings > Apps. The client settings are in `%LOCALAPPDATA%\Germano AI Client`.
3. **Launch:** at the end of the installation the client opens by itself; afterwards use the **Germano AI Client** shortcut on the Desktop or in the Start menu (dedicated window, no terminal; its name differs from the suite's, so both editions can live on the same computer).
4. **Uninstall:** Settings > Apps > Installed apps > Germano AI Client.

### 🍎 macOS (Apple Silicon and Intel, macOS 11 or later)
1. **Download:** download `germano-client-0.60.pkg`.
2. **Installation:** double-click the package and, when choosing the destination, **Install for me only**: the app goes into `~/Applications/Germano AI Client/Germano.app` **with no administrator password** (with "Install for all users of this computer" it goes into `/Applications/Germano AI Client` and macOS asks for the password). The settings are in `~/Library/Application Support/Germano AI Client`.
3. **Launch:** open **Germano** from Launchpad or from Applications > Germano AI Client.
4. **Uninstall:** drag the `Germano AI Client` folder to the Trash.

The package is not signed by Apple yet: if macOS blocks it, go to **System Settings > Privacy & Security** and choose **Open Anyway**.

### 🐧 Linux (Ubuntu / Debian 64-bit)
1. **Download:** download `germano-client-0.60.deb`, designed for **Ubuntu 26.04 LTS** and suitable for Debian-based distributions with glibc 2.34 or later.
2. **Installation:** double-click the file (App Center) or run `sudo apt install ./germano-client-0.60.deb` (administrator password, as for any system package). The program goes into `/opt/germano-client`, with the **Germano AI Client** entry in the applications menu and the `germano-ai-client` command; the settings are in `~/.local/state/germano-client`.
3. **Launch:** from the applications menu.
4. **Uninstall:** `sudo apt remove germano-ai-client`.

---

## 💻 Command-Line Usage (Optional)

For automated scripts, pipelines, or power users, the Client provides a full CLI:

```bash
# Discover active Germano Servers on your local LAN
python client.py discover

# Sign in with user name and password (only if user management is enabled on the server)
python client.py login --user mario

# List the AIs and services of the server
python client.py models

# Ask a server AI: a shared CLI or a service via API (text anonymized by the server)
python client.py ask claude-code "Explain GDPR privacy by design requirements"
python client.py ask meta "Summarize this contract: ..." --model muse-wonder-1.0 --key <Meta key>
python client.py ask deepseek "..." --model deepseek-chat --key <DeepSeek key>

# Processing options of this PC (locked with the server's PA profile)
python client.py options
python client.py options --set censor_date=no --set masking=blackout

# Launch a local AI agent routed through the server's privacy proxy
python client.py launch claude-code

# Anonymize a local file via the server
python client.py send document.pdf
```

---

## 📖 Complete Documentation
For full technical specifications on REST APIs, the Remote Control, user management and advanced networking, refer to the integrated manual:
- **[GUIDA_OFFLINE.html](GUIDA_OFFLINE.html)** (100% offline, bundled in every package)
- **[Official Online Guide](https://germano.ai/guide.html)**

---

<p align="center">
  <b>Germano AI Client</b> — Open Source software distributed under the <b>GNU GPL v3</b> license.<br>
  Proudly developed by <a href="https://www.yesc.it/">Yes Consulting</a>.
</p>


---

## 🛠️ Developer Guide: Running from GitHub Sources

This GitHub repository contains **exclusively clean source code and assets**. To keep the repository lightweight (< 30 MB) and fast to clone, heavy neural models and binary runtimes are **not committed to Git**.

### 📦 What to download before running from source:

1. **AI Models (`models/`):**
   - Germano requires the 6 local AI models (privacy-filter, NER, EasyOCR, YuNet facial biometrics, license plate and signature detection).
   - 👉 All 6 AI models are bundled inside the official Germano AI installers: for development from source, copy the `models/` folder from the installed application into your chosen platform directory (e.g. `windows/germano/models/` or `linux/germano/models/`).
   - *Alternatively:* you can extract the `models/` folder directly from any official installer package on [download.germano.ai](https://download.germano.ai).

2. **System Dependencies & Runtimes:**
   - **Windows:** Requires 64-bit Python 3.11+ and the **[Microsoft Visual C++ Redistributable 64-bit](https://aka.ms/vs/17/release/vc_redist.x64.exe)** (`vc_redist.x64.exe`).
   - **Linux:** Requires Python 3.11+ (`sudo apt install python3 python3-pip python3-venv`).
   - **macOS:** Requires Python 3.11+ (Apple Silicon or Intel).

### 🚀 How to start development in 4 steps:

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
