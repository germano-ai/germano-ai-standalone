# Germano Client v0.02

🌍 *Leggi questo documento in altre lingue: [Italiano](README.md)*

**Germano Client** is the lightweight companion to **Germano Server** (v0.52+). It contains no AI models:
anonymization, the Vault and data restoration all happen on the Server. The Client routes the AI CLIs installed on
this PC through the Server's proxy and lets you protect texts and files on the fly.

## How it works

```
  [ CLI on this PC: claude / codex / aider / qwen ]
                │  ANTHROPIC_BASE_URL / OPENAI_BASE_URL  ->  Germano Server (with /g/<token>)
                ▼
  [ GERMANO SERVER on the LAN :8181 ]         (the PC with the models)
     1. anonymizes prompts and files (Vault + local models)
     2. forwards only protected data to the AI service configured on the server
     3. puts the real data back into the response and returns it to the CLI
```

- The CLIs run on **this** PC: AIs installed only on the server cannot be launched from here.
- **The server decides the AI service.** The proxy forwards OpenAI-format requests to its «Servizio OpenAI o
  compatibile» (OpenAI or compatible service) and Anthropic-format requests to its «Servizio Anthropic» (server
  Dashboard, *Agenti AI e API* tab). A CLI meant for another provider (e.g. Qwen) only works if the server forwards to
  that provider.
- **Where the data lives.** With the Client, the Vault (tag ↔ real data mappings) is on the **server**. Between this
  PC and the server texts travel in clear text over the local network (HTTP): use the Client only on a trusted
  network. The Client stores no texts and no personal data.

## Requirements
- Windows 10/11. No installation: the Client ships a small Python runtime (`runtime` folder).
- A **Germano Server** v0.52 or later in **Server** mode (Settings › Server, or `START_SERVER.bat`) on the same local
  network. On the server, allow Python on private networks when Windows asks.

## Quick start
1. Double-click **`START_CLIENT.bat`**: the menu opens and the Client checks the connection right away.
2. **1) Cerca il server sulla rete** (search the network): the server address appears (e.g. `http://192.168.1.10:8181`).
3. **5) Imposta server e token** (set server and token): enter the address and the token shown by the server in its
   window or in Settings › *Accesso dalla rete* (the token is not displayed while you type it).
4. **2) Stato della connessione** (connection status) must answer «collegamento pronto» (connection ready).
5. **3) Avvia una CLI protetta** (launch a protected CLI, e.g. `claude-code`) or **4) Proteggi un testo o dei file**
   (protect a text or files).

## Command line
```
START_CLIENT.bat discover                          find servers on the local network
START_CLIENT.bat status                            server, engine and token: is everything ready?
START_CLIENT.bat config --server 192.168.1.10 --token ABC123
START_CLIENT.bat config --server http://192.168.1.10:8181/g/ABC123/v1     (the Dashboard Base URL works too)
START_CLIENT.bat launch claude-code                launch Claude Code protected, in a new window
START_CLIENT.bat launch codex --dry-run            show what would be set, without launching anything
START_CLIENT.bat launch codex -- --model gpt-5     everything after -- goes to the CLI
START_CLIENT.bat send "Write to Mario Rossi" letter.docx        protect text and files and show the result
```
`--server` and `--token` can go before or after the command and override `client_config.json`. An address without a
port uses 8181. `send` accepts up to 12 files; images contain no text to protect here: to redact them use file
anonymization on the server.

## Which CLIs can be protected

| CLI | How it goes through Germano | Status |
|---|---|---|
| Claude Code (`claude-code`) | `ANTHROPIC_BASE_URL` + `X-Germano-Auth` header | tested (with an API key) |
| Codex (`codex`) | `OPENAI_BASE_URL` | per its documentation: applies to the default OpenAI provider with an API key; with another provider in its `config.toml` or when signed in with a ChatGPT account, traffic may not go through Germano |
| Aider (`aider`) | `OPENAI_API_BASE`, `OPENAI_BASE_URL`, `--openai-api-base` | per its documentation: use models as `openai/<name>` |
| Qwen Code (`qwen`) | `OPENAI_BASE_URL` | per its documentation: the server must forward to DashScope (compatible mode) |
| Kimi Code CLI (`kimi`) | does not read the address from environment variables | configure it by hand in its `config.toml`, then `launch kimi --forza` |
| DeepSeek (`deepseek`) | there is no official CLI | use Claude Code, with the server's «Servizio Anthropic» set to `https://api.deepseek.com/anthropic` |
| Gemini CLI (`gemini-cli`) | uses the Gemini protocol, which the proxy does not handle | **not launched**: it would not be protected |
| Antigravity, Cursor, Windsurf, Claude Desktop | graphical applications | the Client explains what to set, when possible |

In the environment of the launched CLI the Client also:
- adds the server address to `NO_PROXY`, so requests to Germano do not go through a corporate proxy;
- for Claude Code removes `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX` and `CLAUDE_CODE_USE_FOUNDRY`, which
  would take it outside Germano;
- for Aider removes other providers' keys (e.g. `ANTHROPIC_API_KEY`), which would let it connect directly.

Your AI service key stays yours: the server only forwards it, after protecting the content.

## Fail-safe
Before sending a text or launching a CLI the Client checks, **without sending any personal data**, that a real
Germano Server answers at that address, that the token is valid and (for `send`) that the engine is ready. If
something is wrong it sends nothing and explains why. If the server's engine stops while you work, the server blocks
requests: no data leaves in clear text. The Client always connects to the server directly, never through a system
proxy.

Exit codes: `0` all good, `1` server unreachable or not valid, `2` wrong usage, `3` token missing or wrong, `4` server
engine not ready, `5` CLI not installed or not protectable.

## Manual configuration (`client_config.json`)
```json
{
  "server_url": "http://192.168.1.10:8181",
  "token": "the-token-shown-by-the-server",
  "discovery_port": 8182
}
```
Tip: after the first search, pin the address with `config --server`. Auto-discovery accepts an answer from any
computer on the network: pinning the address avoids sending the token and texts to the wrong PC.

## Common problems
- **No server found**: on the server enable Server mode and allow Python on private networks; or set the address with
  `config --server`.
- **Token ERRATO (wrong) or MANCANTE (missing)**: copy the token from the server window or from Settings › *Accesso
  dalla rete*. If someone generated a «Nuovo token» (new token) on the server, update it on every client.
- **Motore NON PRONTO (engine not ready)**: the server engine is starting or stopped; try again in a moment.

See also the **Germano Server** documentation for server-side configuration.
