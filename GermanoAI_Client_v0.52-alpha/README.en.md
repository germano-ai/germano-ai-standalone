# Germano Client v0.52-alpha

👉 *Leggi questo documento in altre lingue: [Italiano](README.md)*

**Germano Client** is the lightweight companion executable (~28 MB) to **Germano Server**. It requires no heavy local AI models: inference workloads are offloaded entirely to the central Germano Server across your local network (LAN).

The Client provides three primary capabilities:
1. **Server Model Exposure**: discovers and lists all AI models and CLIs installed on and exposed by the Germano Server (e.g., Claude Code, Google Antigravity, OpenAI Codex, Aider, Qwen, DeepSeek). Allows querying and running them directly from the client workstation even if they are not installed locally.
2. **Transparent Local CLI Routing**: for AI tools installed locally on this workstation, configures environment variables (`ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`) to securely tunnel requests through the Server's Privacy Proxy with Bearer Token authentication.
3. **On-the-Fly Text & Document Anonymization**: sanitizes text and files before transmission, ensuring complete privacy.

## How it works

```
  [ Client Workstation: Claude / Antigravity / Codex / Aider / Qwen ]
                │  ANTHROPIC_BASE_URL / OPENAI_BASE_URL (with Bearer Token)
                ▼
  [ GERMANO SERVER on the LAN :8181 ]  (machine hosting the 6 local models)
     1. Receives requests and applies local privacy models
     2. Anonymizes prompts and documents (replacing PII with tokens like [PERSONA_1])
     3. Records reversible mappings in the protected Vault
     4. Forwards only sanitized prompts to the configured upstream LLM
     5. Re-identifies true data in the response and returns plaintext to the Client
```

- **Two Primary Operating Modes:**
  - `launch`: starts a locally installed AI CLI or agent on **this** workstation, routing its traffic through the server proxy.
  - `ask`: directly queries an AI or model hosted on the **server** (executed on the server and protected by its proxy), ideal when the client PC lacks heavy dependencies.
  - `models`: queries the Germano Server and displays all available server-side AI engines, models, and CLIs.

## Requirements
- 64-bit Windows 10/11. Zero administrative privileges or complex installation needed: includes an isolated embedded Python runtime.
- A running instance of **Germano Server** on the same local network (LAN) launched via `START.bat`.

## Quickstart
1. Double-click **`START.bat`**: performs pre-flight verification and displays the interactive menu.
2. **1) Discover server on network**: automatically detects the Germano Server via UDP broadcast (port 8182).
3. **5) Set server and token**: specify the server URL (e.g. `http://192.168.1.10:8181`) and the bearer authorization token shown on the Server console.
4. **2) Connection status**: confirms the server is reachable and the engine is ready.
5. **3) Server AI models**: lists all server-hosted models ready for queries.
6. **4) Ask server AI**: sends prompts and tasks to server-side AI tools.
7. **5) Launch protected CLI**: starts local developer tools (Claude, Codex, Aider) routed through Germano.
8. **6) Protect text or files**: submits documents for immediate local anonymization.

## Command-Line Usage
```bash
START.bat discover                          # Scan LAN for active Germano servers (UDP 8182)
START.bat status                            # Check connectivity, token, and engine state
START.bat config --server 192.168.1.10 --token ABC123   # Set server host and token
START.bat models                            # List AI models and engines available on SERVER
START.bat ask claude-code "Summarize: ..."  # Run prompt using an AI tool hosted on SERVER
START.bat launch claude-code                # Launch local Claude Code tunneled through Server
START.bat launch antigravity                # Launch Google Antigravity tunneled through Server
START.bat launch codex --dry-run            # Inspect environment variables without executing
START.bat send "Letter for John Doe" doc.docx  # Anonymize text and documents
```

## CLI & AI Agent Compatibility

| Tool | Routing Method | Status |
|---|---|---|
| **Claude Code** (`claude-code`) | `ANTHROPIC_BASE_URL` + Header `X-Germano-Auth` | Fully verified |
| **Google Antigravity** | `OPENAI_BASE_URL` on local proxy endpoint | Fully verified |
| **OpenAI Codex** (`codex`) | `OPENAI_BASE_URL` | Natively supported |
| **Aider** (`aider`) | `OPENAI_API_BASE` / `OPENAI_BASE_URL` | Natively supported |
| **Qwen Code** (`qwen`) | `OPENAI_BASE_URL` with upstream forwarding | Supported |
| **Kimi Code CLI** (`kimi`) | Environment variables and CLI parameters | Supported |
| **DeepSeek** (`deepseek`) | OpenAI / Anthropic proxy compatibility | Supported |

## Security & Pre-flight Checks
Before sending any document or prompt, the Client validates:
- Genuine connectivity to Germano Server and bearer token authentication.
- Readiness of the local anonymization engine.
- If the server is unreachable or offline, **zero data is transmitted** and documents remain safely buffered on the client.

## Manual Configuration (`client_config.json`)
```json
{
  "server_url": "http://192.168.1.10:8181",
  "token": "your-server-token",
  "discovery_port": 8182
}
```

## Troubleshooting
- **No server found**: verify Germano Server is running via `START.bat` on the same subnet and Windows Firewall permits traffic on port 8181 (TCP) and 8182 (UDP).
- **Invalid or missing token**: copy the active token from the server console or Settings (*Network access*).
- **Engine not ready**: the server is loading local AI weights into memory; wait a moment and re-test with `START.bat status`.
