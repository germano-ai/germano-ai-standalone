# Germano AI Client

 *Leggi questo documento in altre lingue: [Italiano](README.md)*

**Version 0.90** (November 14, 2026): panel aligned with Germano Server 0.90. What's new in the suite [CHANGELOG](https://github.com/germano-ai/germano-ai-standalone/blob/main/windows/germano/CHANGELOG.en.md).

**Germano AI Client** is the lightweight companion application (about 22 MB on Windows) built to connect any workstation (laptop, standard office PC) to a **Germano Server** running on your local network (LAN).

It requires no heavy AI models or dedicated GPUs on your local machine: all computational load, OCR and AI inference are offloaded to the central Server, while the original documents and the mappings used to restore the data remain on the client workstation.

---

## Key Capabilities

1. **Automatic LAN Server Discovery (UDP 8182 Broadcast)**:
   On startup the Client looks for active Germano Servers on the local network and connects: open access by default, or **user name and password** (`client login`) when user management is enabled on the server. The Client keeps only the session, never the password. Before sending any data it checks, **without sending personal data**, that a real Germano Server answers, that access is allowed and that the engine is ready.
2. **Server AIs and Models**:
   The Client queries the Server and lists the AIs detected on the server (Claude Code, Codex, Gemini CLI, Meta Muse Code, Kimi Code, Qwen Code, DeepSeek, Mistral Vibe, Grok Build, Perplexity, GitHub Copilot CLI, Cursor, Kiro, OpenCode, Aider, Ollama, LM Studio...) and the **AI services via API** filtered by Germano (Meta Muse Wonder and Muse Spark, Kimi, DeepSeek, Qwen, Mistral, Grok, Perplexity, Gemini, OpenAI, Anthropic and the server's local models). With the protected chat you use them directly from your seat, even if they are not installed locally.
3. **Same interface as the Remote Control**:
   The Client panel is the same Remote Control the Server offers to any browser on the network, with the **Chatbot & AI Agents**, **Manual Sanitization**, **Settings** and **Guide** tabs: Client users and browser users have the same capabilities. In Chatbot & AI Agents you choose the model **at the bottom right** among the AIs detected on the server (the others stay greyed out, not selectable, and the list refreshes by itself), answers are streamed with Markdown and highlighted code, and the **Glass Window** shows in real time everything the server sends to the model, including the System 2 decisions, with **Stop operation** to halt it. In Manual Sanitization you drag files to anonymize (audio recordings and compressed archives too) and restore the files returned by AIs. On top of that the Client discovers the server on the network and launches this PC's CLIs protected.
4. **Processing options of this PC**:
   Confidence threshold, active models, 18 personal data categories and masking (`client options`), valid only for this PC's requests. **With the server's PA profile they are locked and greyed out** (the server rejects any change: Compliance Lock).
5. **Transparent Proxy Routing for Local AI Agents**:
   For AI tools installed on your local PC, it automatically configures environment variables (`ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`) routing traffic through the Server's Privacy Proxy with transparent round-trip de-anonymization; for tools configured by hand (Kimi, Mistral Vibe, Muse Code, OpenCode...) it shows the exact address, also per service (`/p/<service>/v1`).
6. **Document & File Protection**:
   Protects text and documents on the fly before transmission: only masked tags (`[PERSONA_1]`, `[COD.FISCALE_1]`, etc.) leave towards the AI, for full GDPR compliance. Since 0.90 the server's Proxy also anonymizes the tool arguments of AI agents and blocks the request if a detected item stays in clear.
7. **Dedicated Native Window Interface**:
   Runs as a dedicated desktop window (no black terminal windows, no generic browser address bars) as well as a command-line interface (`client.py`) for automation.
8. **Silent updates, like Google Chrome**:
   On by default: only when the system reports an Internet connection, the Client checks `download.germano.ai`, downloads the new version in the background at low priority and on Windows applies it at the next start in a few seconds, with no windows (at most a discreet «Restart to update»); on macOS and Linux the package opens when you decide. Status and options in Settings › Updates.
9. **Faster with a Germano Server 0.90**:
   Client requests take the server's fast lane, ahead of the documents queued in its `input` folder; the server works in parallel (Privacy Filter and Italian NER together, one lock per model) and serves already protected history and attachments from its cache.

---

## Architecture Flow

```
  [ Client Seat: Laptop / Standard PC ]
     │  GUI (Chatbot & AI Agents + Glass Window) or CLI (Claude Code / Codex / Aider / Qwen Code)
     │  Open access, or the user's session when user management is enabled
     ▼
  [ GERMANO SERVER on LAN :8181 ]  (Workstation hosting the 8 local offline AI models)
     1. Receives requests and applies local offline privacy models (fast lane for clients)
     2. Masks prompts, documents and tool arguments (replacing personal data with tags)
     3. Keeps the mappings in the server's Vault
     4. Forwards strictly anonymized payloads to the target LLM (final check: no detected item in clear)
     5. Restores the original data of THAT request on the return trip and delivers cleartext to the Client
```

---

## Multiplatform Installation

The official Client installers are single files on **[download.germano.ai](https://download.germano.ai/)** and bundle their own Python with all libraries: installation downloads nothing from the Internet. The client creates no working folders in Documents: its settings (server address, session, options) stay in the user's technical folder.

### Windows (10 / 11 and Windows Server 2019 or later, 64-bit, also in a virtual machine)
1. **Download:** download `germano-client-0.90.exe` (about 22 MB).
2. **Installation:** double-click the installer. It installs for the current user into `%LOCALAPPDATA%\Programs\Germano AI Client` **without administrator privileges (no UAC prompt)**, with Desktop and Start menu shortcuts and the entry in Settings > Apps. The client settings are in `%LOCALAPPDATA%\Germano AI Client`.
3. **Launch:** at the end of the installation the client opens by itself; afterwards use the **Germano AI Client** shortcut on the Desktop or in the Start menu (dedicated window, no terminal; its name differs from the suite's, so both editions can live on the same computer).
4. **Uninstall:** Settings > Apps > Installed apps > Germano AI Client.

### macOS (Apple Silicon and Intel, macOS 11 or later)
1. **Download:** download `germano-client-0.90.pkg`.
2. **Installation:** double-click the package and, when choosing the destination, **Install for me only**: the app goes into `~/Applications/Germano AI Client/Germano.app` **with no administrator password** (with "Install for all users of this computer" it goes into `/Applications/Germano AI Client` and macOS asks for the password). The settings are in `~/Library/Application Support/Germano AI Client`.
3. **Launch:** open **Germano** from Launchpad or from Applications > Germano AI Client.
4. **Uninstall:** drag the `Germano AI Client` folder to the Trash.

The package is not signed by Apple yet: if macOS blocks it, go to **System Settings > Privacy & Security** and choose **Open Anyway**.

### Linux (Ubuntu / Debian 64-bit)
1. **Download:** download `germano-client-0.90.deb`, designed for **Ubuntu 26.04 LTS** and suitable for Debian-based distributions with glibc 2.34 or later.
2. **Installation:** double-click the file (App Center) or run `sudo apt install ./germano-client-0.90.deb` (administrator password, as for any system package). The program goes into `/opt/germano-client`, with the **Germano AI Client** entry in the applications menu and the `germano-ai-client` command; the settings are in `~/.local/state/germano-client`.
3. **Launch:** from the applications menu.
4. **Uninstall:** `sudo apt remove germano-ai-client`.

**Requirements:** a Germano Server in Server mode on the same local network, version 0.70 or later (0.90 recommended: with a 0.60 server only the command line can be used).

---

## Command-Line Usage (Optional)

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

## Complete Documentation
For full technical specifications on REST APIs, the Remote Control, user management and advanced networking, refer to the integrated manual:
- **[GUIDA_OFFLINE.html](GUIDA_OFFLINE.html)** (100% offline, bundled in every package)
- **[Official Online Guide](https://germano.ai/guide.html)**

---

<p align="center">
  <b>Germano AI Client</b> — Open Source software distributed under the <b>GNU GPL v3</b> license.<br>
  Proudly developed by <a href="https://www.yesc.it/">Yes Consulting</a>.
</p>


---

## Developer Guide: Running from GitHub Sources

This GitHub repository contains **exclusively clean source code and assets**. To keep the repository lightweight (< 30 MB) and fast to clone, heavy neural models and binary runtimes are **not committed to Git**. The client **uses no AI models**: Python is enough.

1. **System Dependencies & Runtimes:**
   - **Windows:** 64-bit Python 3.11+.
   - **Linux:** Python 3.11+ (`sudo apt install python3 python3-pip python3-venv`).
   - **macOS:** Python 3.11+ (Apple Silicon or Intel).

2. **Running from source:**

```bash
# 1. Clone the repository and enter the client folder of your platform
git clone https://github.com/germano-ai/germano-ai-standalone.git
cd germano-ai-standalone/windows/germano-client  # or linux/germano-client or macos/germano-client

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# 3. Install the Python dependencies and start the client (command line)
pip install -r requirements.txt
python client.py status
```

The client installers are built with the suite scripts: `windows/germano/build/costruisci_installer_windows.py client`, `costruisci_deb.py germano-client` and `costruisci_pkg.py germano-client` (see the suite README).
