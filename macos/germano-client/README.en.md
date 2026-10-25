# 🛡️ Germano AI Client

👉 *Read this in other languages: [Italiano](README.md)*

**Germano AI Client** is the ultralight (~26 MB) companion application built to connect any workstation (laptop, standard office PC) to a **Germano Server** running on your local network (LAN).

It requires no heavy AI models or dedicated GPUs on your local machine: all computational load, OCR, and AI inference are offloaded to the centralized LAN Server, while all original documents and the de-anonymization Vault remain strictly and sovereignly on your local PC.

---

## ⚡ Key Capabilities

1. **Automatic LAN Server Discovery (UDP 8182 Broadcast)**:
   Upon startup, the Client automatically discovers active Germano Servers across the local subnet, establishing an instant connection secured by Bearer Token authentication.
2. **Server AI Models & Harness Exposure**:
   The Client queries the Server and displays all available AI engines and CLI agents (e.g. Claude Code, Google Antigravity, OpenAI Codex, Aider, Qwen, DeepSeek). You can execute and query them directly from the client seat, even if they are not installed locally.
3. **Transparent Proxy Routing for Local AI Agents**:
   For AI tools installed on your local PC, it automatically configures environment variables (`ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`) routing traffic through the Server's Privacy Proxy with transparent round-trip de-anonymization.
4. **Document & File Protection**:
   Protects text and documents on the fly prior to transmission: the server receives only masked tokens (`[PERSONA_1]`, `[TAX_ID_1]`, etc.), guaranteeing absolute GDPR compliance.
5. **Dedicated Native Window Interface**:
   Runs as a dedicated native desktop window (no black terminal windows, no generic browser address bars) as well as an extensible command-line interface (`client.py`) for automation.

---

## 🏗️ Architecture Flow

```
  [ Client Seat: Laptop / Standard PC ]
     │  GUI Dashboard or CLI (Claude / Antigravity / Codex / Aider)
     │  Secure Bearer Token Routing
     ▼
  [ GERMANO SERVER on LAN :8181 ]  (Workstation hosting the 6 local offline AI models)
     1. Receives requests and applies local offline privacy models
     2. Masks prompts and documents (replacing PII with deterministic tokens)
     3. Stores reverse mappings in the client's local Vault
     4. Forwards strictly anonymized payloads to the target LLM
     5. Restores original identities on the return trip and delivers cleartext to Client
```

---

## 📦 Multiplatform Installation

The official Client installers are single files on **[download.germano.ai](https://download.germano.ai/)** and bundle their own Python with all libraries: installation downloads nothing from the Internet. The client creates no working folders in Documents: its settings (server address, token) stay in the user's technical folder.

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

# List AI models exposed by the server
python client.py models

# Query a server-hosted AI directly
python client.py ask "Explain GDPR privacy by design requirements"

# Launch a local AI agent routed through the server's privacy proxy
python client.py launch claude
python client.py launch antigravity

# Anonymize a local file via the server
python client.py send document.pdf
```

---

## 📖 Complete Documentation
For full technical specifications on REST APIs, bearer tokens, and advanced networking, refer to the integrated manual:
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
   - 👉 **[Download the complete Models Bundle](https://download.germano.ai/modelli/)** and extract it into the `models/` directory of your chosen platform (e.g. `windows/germano/models/` or `linux/germano/models/`).
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
