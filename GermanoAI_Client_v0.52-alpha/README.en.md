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
     3. Stores reverse mappings in the client's local protected Vault
     4. Forwards strictly anonymized payloads to the target LLM
     5. Restores original identities on the return trip and delivers cleartext to Client
```

---

## 📦 Multiplatform Installation

All official Client installers are available directly from **[download.germano.ai](https://download.germano.ai/)**:

### 🪟 Windows (10 / 11 64-bit)
1. **Download:** Download `germano-client-0.60.exe` (or `Installa_Germano.exe`).
2. **Installation:** Double-click the installer. It deploys into user-space `%LOCALAPPDATA%\Programs\Germano AI` **with zero administrator privileges required (zero UAC)** and sets up `Documents\Germano AI` and a Desktop shortcut.
3. **Launch:** Double-click the **Germano** desktop icon to launch the dedicated GUI panel.

### 🍎 macOS (Apple Silicon & Intel)
1. **Download:** Download `germano-client-0.60.command`.
2. **Installation:** Double-click to run the native guided wizard: installs `Germano.app` to `~/Applications` and configures `~/Documents/Germano AI` without requiring root or sudo access.
3. **Launch:** Open **Germano.app** from Launchpad or your Applications folder.

### 🐧 Linux (Ubuntu, Debian, Fedora, Arch)
1. **Download:** Download `germano-client-0.60.sh`.
2. **Installation:** Run via double-click or terminal via `bash germano-client-0.60.sh`. It adheres strictly to XDG standards by installing to `~/.local/share/germano`, integrates launchers into the Applications Menu and Desktop, and creates `~/Documents/Germano AI`.
3. **Launch:** Launch Germano directly from your application menu or desktop shortcut.

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
