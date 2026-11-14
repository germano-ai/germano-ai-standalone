# Changelog

 *Leggi questo documento in altre lingue: [Italiano](CHANGELOG.md)*

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Releases up to 0.50-alpha are documented in Italian only, in [CHANGELOG.md](CHANGELOG.md).

## [0.95] - 2026-11-14
Germano AI v0.95 - **MCP server and UTCP: Germano in input and output workflows**. Claude Desktop, Claude Code, Google
Antigravity, Cursor, Windsurf, Visual Studio Code, Gemini CLI, n8n, agents and scripts use Germano as a tool: **on the
way in** it anonymizes texts and documents, inspects personal data and stops leaks before anything leaves; **on the
way out** it restores the original data in the replies. The same 8 tools are offered by the MCP server (Streamable
HTTP, SSE and stdio), by the UTCP manual, by OpenAPI and by new REST APIs, with one registry and the same security
rules. Protection engine, local models and formats are those of 0.91.

### Added - MCP server (Model Context Protocol)
- **Streamable HTTP** at `http://127.0.0.1:8181/mcp`: `POST` (JSON-RPC 2.0, batches too; client notifications and
  responses → `202 Accepted`), sessions with `Mcp-Session-Id` (expired session → `404`, the client repeats
  `initialize`), `DELETE /mcp` closes the session, `GET /mcp` with `Accept: text/event-stream` → `405` (no unsolicited
  server stream), `GET /mcp` from a browser → JSON description.
- **Legacy SSE** (2024-11-05 revision, for n8n and older clients): `GET /mcp/sse` opens the stream and announces the
  endpoint, `POST /mcp/messages?session_id=...` → `202` and the response arrives on the stream.
- **stdio**: `server.py --mcp-stdio` (or `python -m germano.mcp_server` from the program folder). Only JSON-RPC
  messages on stdout. If Germano is open with the same data folder it acts as a **bridge** to `/mcp` (same engine, same
  counters); otherwise it works **in its own process**: it starts the engine on the first request and closes it with
  the MCP client. One engine per data folder (`state/daemon.lock`); the Vault is written only by the engine (SQLite in
  WAL mode) and read by the other processes. Options `--mcp-bridge` (bridge only) and `--mcp-inprocess`. The server
  writes its port to `state/server.json` for the bridge.
- **Protocol revisions:** 2025-11-25, 2025-06-18, 2025-03-26 and 2024-11-05, negotiated in `initialize` (an unknown
  revision receives 2025-11-25). Revision 2026-07-28 removes the handshake: "dual-era" clients (e.g. the official
  Python SDK `mcp` 2.3) probe `server/discover`, receive a classic error and fall back to `initialize` on their own —
  verified.
- **Methods:** `initialize`, `ping`, `tools/list`, `tools/call`, `resources/list`, `resources/read`,
  `resources/templates/list`, `prompts/list`, `prompts/get`, `logging/setLevel`.
- **8 tools** with `inputSchema` and `outputSchema` (JSON Schema), `title`, `annotations` (`readOnlyHint`,
  `destructiveHint`, `idempotentHint`, `openWorldHint`) and the result both in `structuredContent` and as JSON text
  (universal compatibility); invalid arguments → result with `isError` (not a protocol error):
  - **input:** `germano_anonymize_text` (text or `texts[]` list, `numbered`/`generic`/`blackout` masking, optional
    System 2, `restore_scope` for the output step, `mapping` only on request), `germano_anonymize_file` (PDF, Office,
    OpenDocument, RTF, EML, TXT, CSV, JSON, HTML, XML, images with OCR/faces/signatures/plates, audio, archives: from
    `file_path` or `content_base64`, to `output_path` or in base64, preview of the anonymized text),
    `germano_inspect_entities` (position, category, score and System 1/System 2 level, System 2 decisions,
    **read-only**: nothing written to the Vault), `germano_leak_check` (text or any JSON payload, with the JSONPath of
    every item found; `safe=true` only when nothing remains; values omitted by default);
  - **output:** `germano_deanonymize_text` and `germano_deanonymize_file` (only the placeholders present,
    `restored_count`, `unmatched_placeholders`; writing to `output_path` recommended for cloud assistants);
  - **verify and status:** `germano_workflow_roundtrip` (input → external or simulated reply → output, restoration
    limited to the placeholders of the cycle, check that nothing remains in the text that left) and `germano_status`
    (engine, System 1/2, Vault counts only, addresses, calls).
- **Resources:** `germano://status`, `germano://capabilities`, `germano://utcp-manual`, `germano://workflow-guide`.
  **Prompts:** `sanitize-before-send`, `restore-after-reply`, `workflow-input-output-audit`.

### Added - UTCP, OpenAPI and REST APIs for workflows
- **UTCP 1.0 manual** (`utcp_version` 1.0.1, `manual_version` 1.0.0) at `/utcp`, `/.well-known/utcp.json` and
  `/api/v1/utcp`: standard keys only (the official TypeScript client rejects extra ones), one HTTP
  `tool_call_template` per tool with the address built from the request host, `body_field: "body"` (the arguments
  become the JSON body), `tags` per phase (`input`, `output`, `workflow`, `status`...) and, when the manual is requested
  from the network, `api_key` authentication with `Authorization: Bearer ${API_TOKEN}`. Variants `?format=extended`
  (with `info`, for rs-utcp) and `?format=legacy` (0.1 format with `tool_provider`/`provider_type`).
- **OpenAPI 3.1** at `/openapi.json` (8 operations, same schemas; a UTCP client can register it too).
- **REST APIs:** `POST /api/v1/anonymize-text`, `/api/v1/anonymize-file`, `/api/v1/inspect-entities`,
  `/api/v1/leak-check`, `/api/v1/deanonymize-text`, `/api/v1/deanonymize-file`, `/api/v1/workflow-roundtrip` and
  `GET /api/v1/status` (JSON body with the arguments, also as `{"body": {...}}`). The existing local APIs
  (`/api/v1/anonymize`, `/api/v1/anonymize_text`, `/api/v1/deanonymize_text`, `/api/v1/deanonymize_file`,
  `/api/status`) are unchanged.
- **One registry** (`germano/integrations.py`) for MCP, UTCP, OpenAPI and REST: same names, schemas and handlers.

### Added - Settings › MCP & UTCP integrations
- Ready-to-use addresses (Streamable HTTP, SSE, UTCP manual, OpenAPI) and the stdio command, with **Copy MCP
  configuration** (stdio), **Copy HTTP configuration** and **Copy UTCP URL**; live status: exposed tools, calls
  (succeeded, blocked, errors), open MCP sessions, MCP/UTCP revisions and check of the UTCP manual.
- **Connect with 1 click** for the clients found on this computer: Claude Desktop, Claude Code, Google Antigravity,
  Cursor, Windsurf, Visual Studio Code and Gemini CLI. It registers Germano (stdio) changing only the "germano" entry,
  after a **backup** of the file (`.germano-backup-…`, last 5); files with comments (JSONC) are not touched. States:
  Connected, Needs update, Detected, Not detected, Configure by hand; **Disconnect** too.
- **Try the Input → Output flow** (three boxes: text that left anonymized, reply, restored text) and **Leak check**.
- **Integration token** (show, copy, new), network addresses in Server mode, the **Start the engine automatically for
  workflows** switch and the folders allowed for file paths. In Italian and English.

### Added - Germano Client
- `client mcp`: stdio MCP server on this PC that forwards to the Germano Server's MCP server, with the integration
  token (`client config --api-token <token>`) or the user session; `client utcp` shows the server's MCP/UTCP/OpenAPI
  addresses and tools (`--json` for the full manual).

### Security
- **Fail-safe:** anonymization, inspection and leak checks go through the engine; if it is not ready the request is
  **blocked** (`status: "blocked"`, HTTP `503`) and the original text is never returned as safe (the leak check never
  answers `safe=true` without the engine). With the switch on (default) an MCP/UTCP request starts the engine and waits
  for it to load (up to 120 seconds, about a minute the first time).
- **Vault:** no tool lists or downloads the Vault; the status reports only counts per type. Restoration replaces only
  the placeholders present in the text or file received (at most 5,000 different ones per text).
- **Local network** (only with the Server part on): MCP, SSE and API v1 need the **integration token**
  (`Authorization: Bearer <token>`, created by Germano and shown only in the Dashboard) or a user session (user
  management on), even with free access; the UTCP manual and OpenAPI stay public descriptions without data. From the
  network restoration requires the `restore_scope` of one's own anonymization (in memory, 24 hours) or the caller's
  `mapping`: never the whole Vault. The pre-existing local APIs stay local only.
- **File paths:** `file_path`/`output_path` only from this computer, absolute, inside Documents, Desktop, Downloads,
  the work folders or the ones added in `integration_allowed_dirs` (config.json); never Vault and reports, state,
  configuration, program, cache and models, hidden folders or files; no overwrite without `overwrite`. A file given by
  path without `output_path` goes to the `output` folder.
- **Origin:** MCP (SSE too), API v1 and the panel accept only the Dashboard's own origin or no origin (MCP clients,
  n8n, curl): a web page of another site or another port gets `403`. The 1-click connection answers only this
  computer, needs a JSON body and honours `lock_settings`.
- Per-request changes can only **increase** protection (System 2 off, generic or ████ labels, inspection without
  Vault) and also apply with the PA profile.
- Restored text contains personal data: tool descriptions and MCP instructions ask assistants running in the cloud to
  write it to a file (`output_path`) instead of receiving it.

### Changed
- Engine (`daemon_api.py`): "more protective only" per-request changes and positions of the items found for inspection
  and leak checks. `common.py`: `integration_token` and `integrations_autostart_engine` settings. The server console
  also shows the MCP and UTCP addresses.

### Tests
- 158/158 end-to-end and security checks on the 0.95 sources (MCP HTTP/SSE/stdio as bridge and in-process, UTCP,
  OpenAPI, REST, DOCX and TXT files in and out, forbidden paths, simulated network with and without token, fail-safe
  with the engine stopped, 1-click connection on a test user folder, Germano Client).
- 58/58 with the **official SDKs**: `mcp` 2.3.0 (Streamable HTTP in auto mode with fallback from 2026-07-28, SSE,
  stdio) and `utcp` 1.2.0 + `utcp-http` 1.1.15 (registration from `/utcp`, `/.well-known/utcp.json` and
  `/openapi.json`, calls and tag search).
- 15/15 interface checks in headless Edge (Italian and English, 1400/860/390 px, no console errors); 72/72 tests of the
  0.91 configuration assistant.

### Known limitations
- `python-utcp` accepts `http://` only towards loopback addresses: from another computer use HTTPS (e.g. a reverse
  proxy with TLS) or MCP or the REST APIs.
- `restore_scope` lives in memory for 24 hours and is lost when Germano restarts: for long network workflows ask
  `return_mapping: true` and pass `mapping` to the restoration.
- MCP revision 2026-07-28 (without handshake) is not supported natively yet: dual-era clients fall back to the
  previous revisions on their own.
- The 1-click connection does not modify files with comments (e.g. VS Code's `mcp.json` in JSONC): copy the
  configuration by hand.

## [0.91] - 2026-11-14
Germano AI v0.91 - **AI configuration assistant**. Next to every detected AI Germano tells what is missing to use it
and does it with one click: it installs Google Antigravity CLI (`agy`) and uses it in the Chatbot & AI Agents with the
Antigravity Desktop account, adds Qwen 4 Max and GLM 5.3, links the keys already set up in other tools without copying
them and makes Ollama, LM Studio and Jan usable even when they are stopped or not installed yet. Protection engine,
local models and supported formats are those of 0.90.

### Added - AI configuration assistant
- **Contextual button** on the row of every AI in the model picker at the bottom right and next to the **Detected
  AIs** in *Settings › AI, keys & Chatbot*: «Install CLI», «Sign in», «Set up», «Start», «Install», «Get a model»,
  «Retrieve key». It opens the assistant window with the verified status (what is installed, with which account,
  which models), the possible actions, the live progress with «Cancel» and the official pages.
- New **Configuration assistant** panel in *Settings › AI, keys & Chatbot*, with the Google Antigravity, Qwen, GLM,
  Ollama, LM Studio and Jan tabs and one tab for every key found for other services.
- **Security:** the `/api/ai/assist/*` routes only answer this computer (`403` from the network), reject requests from
  external sites (anti-CSRF) and, with `lock_settings`, every action; with `GERMANO_OFFLINE=1` no downloads. Actions
  are fixed recipes, with no shell and no user text among the arguments; downloads start only after an explicit
  confirmation, only over HTTPS from allowed hosts and with the vendor's SHA-512 digest and/or Authenticode signature
  verified (if the check fails the file is discarded). No key or token ever reaches the page or the logs.
- The Remote Control and Germano Client do not show the assistant: it only configures the AIs of the computer running
  Germano.

### Added - Google Antigravity CLI (`agy`) in the Chatbot & AI Agents
- **Install CLI** downloads Google's official CLI from the official manifest (SHA-512 digest; on Windows also the
  «Google LLC» Authenticode signature) and runs the official `agy install` step (`%LOCALAPPDATA%\agy\bin` in the
  user's PATH; on macOS and Linux `~/.local/bin/agy`).
- The CLI **uses the account already signed in to Antigravity Desktop by itself**: the sign-in is shared through the
  system keychain (Windows Credential Manager, Apple Keychain, Secret Service). Germano never reads or copies the
  tokens: it only checks that the sign-in exists and shows the account masked. If it is missing: «Sign in with Google».
- **Antigravity CLI (agy)** appears in the picker with the models of your account and is used like the other AIs:
  message, history and attachments leave **already protected** through standard input (one NDJSON line with only the
  tags) and the answer comes back with the real data.
- **Protected execution:** isolated profile (`USERPROFILE`/`HOME` in `state\agy\home`: none of the user's settings,
  hooks, MCP, plugins or rules), empty working folder, restrictive session settings (`toolPermission: strict`, rules
  denying commands, files, web addresses and MCP), an instruction not to use tools and an **immediate stop** if the CLI
  announces a tool anyway; the conversation saved by the CLI is removed at the end of the answer.
- **Transparency:** with the OAuth account the CLI only talks to Google and cannot be pointed at the Germano Proxy. The
  Glass Window states it for every request: the CLI's internal instructions (about 10,000 tokens, with the path of the
  working folder) go to Google without passing through the Proxy, while your text, the history and the attachments are
  already anonymized. When the CLI is installed, while the Dashboard is open Germano checks the sign-in and the
  account's models about every 10 minutes with `agy models`: the CLI contacts Google, with no texts or document data.
- Only for whoever uses this computer: the CLI is never run for network clients (from the Remote Control, for Gemini
  models, the «Google Gemini» service remains).

### Added - Qwen 4 Max and GLM 5.3
- New services via API (also in the Proxy as `/p/<service>/v1` and in the Remote Control), with addresses and models
  verified on the official documentation on 2026-11-14:
  - `qwen-token` **Qwen Token Plan (Qwen4-Max)**: `qwen4-max-preview` (preview until 2026-11-25) and `qwen3.8-max`;
  - `qwen` **Qwen (Alibaba Cloud Model Studio)** pay-as-you-go: `qwen3.8-max`, `qwen3.7-plus`, `qwen3.8-flash`;
  - `qwen-coding` **Qwen Coding Plan**;
  - `zai` **GLM (Z.ai)** and `zai-coding` **GLM Coding Plan (Z.ai)**: `glm-5.3`.
- **Retrieve configuration** looks for keys already set for other tools (the user's environment variables, Qwen Code,
  Claude Code configured toward other providers, OpenCode, Codex, Gemini CLI), picks the right service from the
  address (plan and region) and **links it without copying it**: `state\ai_links.json` only holds the source and the
  variable name, the key is read when it is used (a key changed in the source applies right away). Regions not yet
  supported are reported and not linked; «Unlink» removes the link.
- **Install Qwen Code** (with Node.js, 22 or later recommended; on macOS also with Homebrew), to use Qwen Code with the
  Germano Proxy.

### Added - Local models (Ollama, LM Studio, Jan)
- The models already downloaded are read from disk **even when the service is stopped** (Ollama: `~/.ollama/models` or
  `OLLAMA_MODELS`; LM Studio: `~/.lmstudio/models` and the downloads folder; Jan: its data folder) and the picker row
  says so («N models already downloaded»).
- Ollama: **Install Ollama** (Windows: the official `OllamaSetup.exe` with the «Ollama Inc.» Authenticode signature
  required, silent per-user installation; macOS and Linux: official page), **Start Ollama** and **Download a
  recommended model** (`qwen3.5:4b`, `gemma4:e4b`, `llama3.2:3b`, `qwen3.5:2b`) with the progress from the local API.
- LM Studio: **Start local server** (`lms server start`, or the app); Jan: **Start Jan** (with the note on the Local
  API Server).

### Changed
- Germano Client: `client launch agy` explains that the CLI cannot be pointed at the Proxy and shows the alternatives.
- Version 0.91 in the six source trees and in the six packages; the «Version» entry of the About tab summarizes what
  is new. Offline guide, READMEs and LEGGIMI updated with the new features.

### Tests
- Assistant backend: 72/72 checks (key sources in a fake home folder, link without copy and changed key, unsupported
  regions, models on disk, `agy` profile, fake CLI attempting a tool, routes from this computer and from a simulated
  network, CSRF, `lock_settings`, Authenticode signatures), repeated with the same result on the 0.91 sources.
- Real `agy` 1.5.9 CLI in the Harness profile: correct answer and conversation removed; an attempted tool
  (`run_command`) stopped by Germano before use. Real request with synthetic data: Google only received the tags
  (`[PERSONA_1]`, `[COD.FISCALE/P.IVA_1]`, `[EMAIL_1]`, `[TELEFONO_1]`).
- On the real app 29/29 checks; Remote Control and Dashboard in headless Edge 9/9.

### Known limits
- With Antigravity CLI the CLI's internal instructions go to Google directly (stated in the Glass Window).
- On macOS the `agy` home folder is not isolated (the Keychain follows it); Linux and macOS verified statically only.
- Real installation of Ollama, LM Studio and Jan and real calls to Qwen and GLM not tested live (tested: the cancelled
  confirmation, a model download with a simulated Ollama and the services without a key).
- `qwen4-max-preview` is a preview until 2026-11-25: after that date the identifier must be updated.

## [0.90] - 2026-11-14
Germano AI v0.90 - **faster and parallel, with the same protection**. All measurements were taken on the real engine
(test PC Intel i5-4570, 4 cores, 16 GB of RAM, no GPU) comparing 0.80 and 0.90 on the same files: same masked data,
shorter times. The Proxy now also protects the tool arguments of AI agents, and the Linux and macOS packages are
identical again to the Windows ones.

### At a glance: 0.80 and 0.90 on the same files
| Test | 0.80 | 0.90 |
|---|---|---|
| Digital PDF, 12 pages (36,600 characters) | 234.6 s | **132.0 s** (-44%, same 735 audit entries) |
| System 2 on a document of 56 texts | 214.3 s, 75 questions to the model | **52.3 s**, 22 questions (same decisions) |
| Vault with 100,000 entries: saving a new item | 308 ms | **1.6-2.6 ms** |
| Vault with 100,000 entries: read by the server | 496 ms | **4.2 ms** |
| Transcription of 284 s of recordings | 107-126 s | **66 s** (word error rate: 13.3% → 11.6%) |
| Scanned page (faces, signatures, plates, OCR) | 29.6 s | **26.7 s** (-10%, same masked regions) |
| Engine start (disk already cached) | 26.6 s | **24.2 s** (-8%) |
| Labels in a 12-page PDF (alignment) | 1.61 s | **0.18 s** (identical positions) |
| Proxy: history already seen / image already protected | 1.15 s / 1.58 s | **0.01 s / 0.01 s** |

### Improved - Parallel engine
- **Privacy Filter and Italian NER together** on the same text batch (the NER runs in ONNX Runtime on a separate
  thread): 5 to 11% less time on text alone depending on the PC load, with identical results.
- **One lock per model** instead of a single lock: Privacy Filter, Italian NER, OCR, faces, signatures and plates serve
  different requests at the same time (for example the OCR of a queued scan and the text of a Proxy request).
- **Fast lane**: interactive requests (Chatbot & AI Agents, Proxy, REST API, Remote Control and network clients) go
  ahead of the `input` folder documents on the Privacy Filter, OCR and System 2, and wait at most for the batch in
  progress. Test: three Proxy requests served in 4.7, 5.7 and 0.3 s while a 6-page PDF was being processed.
- **Parallel loading**: Italian NER and OCR load while the Privacy Filter loads.
- **Parallel vision**: faces, signatures, plates and OCR of an image or page work together.
- **Scanned PDFs in windows of 8 pages and Office document images in batches**: the OCR text is analyzed in a single
  call, with full model batches and data propagation across pages.
- **PDF labels**: linear alignment instead of quadratic.

### Improved - System 2 without redundant questions
- When the same word stays masked elsewhere in the document, its doubtful occurrences are no longer asked to the local
  model (propagation would mask them anyway): on the test corpus 61 of 87 questions (70%) could not change the
  outcome. Coverage compared character by character with 0.80: 0 characters of difference on 56 texts. A question
  that is not asked **always** stays masked.
- The doubts of all the texts of a request share one queue, with priority to interactive requests; when the work is
  interrupted, queued doubts are cancelled.

### Improved - Vault, files and caches
- **Vault on SQLite in WAL mode** (`extracted/deanonymize_vault.db`): only new entries are written and read, more than
  100 times faster with a large Vault. `extracted/deanonymize_vault.json` stays, in the same format, as a portable copy
  (at every save up to 5,000 entries, then every 5 minutes and when the engine closes); if it is replaced by hand its
  entries are imported without losing the existing ones. Automatic migration on first start; network drives keep the
  JSON only. An error writing the JSON copy no longer stops the work.
- **Files between server and engine by path** instead of base64 inside JSON (REST API, Remote Control, Proxy,
  attachments, shared transcription): less memory and no encoding for large files; oversized bodies are rejected
  before reading on the shared engine.
- **Proxy and attachment cache**: the history that IDEs and agents resend at every turn no longer goes back to the
  engine (as already in Chatbot & AI Agents); already protected images and documents come from the cache (up to
  256 MB, emptied together with the Vault).

### Improved - Audio and Client mode
- **Batched transcription**: from 60 seconds up, Whisper transcribes the speech segments in batches of 8
  (`BatchedInferencePipeline`), with automatic fallback to the sequential mode; short recordings stay identical.
- **Parallel Client mode**: up to three `input` folder files processed together on the Germano Server (test: 9 files
  in 1.8 s).
- **Germano Server check**: when connecting and then every 10 minutes the client sends the server a control sentence
  with randomly chosen fake data; if the server does not recognize the name, it is not used and no data leaves.

### Fixed - Proxy
- Values under keys such as `name`, `id`, `status`, `detail`, `type`, `format` inside `tool_use.input`,
  `function.arguments` and `functionCall.args` (Gemini) are now anonymized: the protocol envelope stays intact, tool
  arguments are user content. Cited text of citations, `metadata`, `user` and participant names are anonymized too;
  non-streaming responses restore tool arguments.
- New **final no-exit check** (`leak_check`): if a just-detected item remains in a field that was not anonymized, the
  request is blocked (`422`) and nothing is sent. "Canary" test on 1,000 random requests in 4 formats: 20/20 checks
  passed (with 0.80 the test data left in clear in every format).
- A non-text `"type"` in tool arguments made the Proxy fail.

### Fixed - Other
- Chatbot & AI Agents: an unexpected error reaches the page as an event, saying whether anything had been sent.
- Linux and macOS sources identical again to Windows in all common files; the `.deb` and `.pkg` builders stop if a
  tree is not aligned (`build/coerenza_sorgenti.py`). Germano Client interface aligned with the server one (audio,
  archives, System 2 in the Glass Window). Complete `requirements.txt` (onnxruntime, faster-whisper, ctranslate2, av).
- Documentation: README, guide, LEGGIMI and CHANGELOG updated to 0.90 (Markdown well formatted again: the 0.80 cleanup
  had removed the spaces after bold text); `VERSION` → `0.90`.

## [0.80] - 2026-11-10
Germano AI v0.80 - **Native Audio & Offline Speech-to-Text Transcription**, **Recursive Compressed Archive Extraction & Sanitization**, **Atomic Updater Size Verification**, and refined System 1 / System 2 triage.

### Added - Native Audio & Offline Transcription
- Support for .mp3, .wav, .m4a, .ogg, .flac, .opus, .aac, .wma, .amr, .aiff files.
- Local speech-to-text transcription powered by bundled **Whisper Small INT8** (240 MB) via CTranslate2 running in an isolated worker process: 100% offline, zero cloud data leakage.
- Extraction and redaction of audio metadata and ID3/Vorbis/MP4/WAV tags (title, artist, author, comments, GPS coordinates) into Vault tokens.
- Sanitized output transcription <name>.trascrizione.txt generated with timestamped segments [hh:mm:ss]; original audio file is kept intact in processed.
- Seamless audio attachments in Chatbot & AI Agents (drag & drop or clip icon) with live transcription into prompt composer.

### Added - Compressed Archives Module (ZIP, TAR, GZ, 7Z, RAR)
- Safe recursive inspection and redaction for .zip, .tar, .tar.gz, .tgz, .gz, .bz2, .xz, .7z, .rar.
- Format detection based on binary magic bytes rather than file extension.
- Hardened sandbox extraction preventing Path Traversal (no file extracted using archive path, rejection of .. or absolute paths) and Decompression Bombs (200x max expansion ratio, 4 GB maximum size).
- Bundled **7-Zip 26.06** integration for high-performance .7z and .rar streaming extraction.
- Automatic repacking preserving the exact internal folder hierarchy; .rar archives are safely repacked as .rar.zip.

### Improved - Glass Window Instant Abort
- The 'Interrompi' (Abort) button on Glass Window stops voice transcription workers and archive unpacking in under 0.2 seconds, instantly releasing RAM and clearing temp directories.

### Fixed - Atomic Updater Byte Size Verification
- Resolved byte-size mismatch in `version.json`: exact byte sizes and SHA256 hashes are computed directly from on-disk binaries atomically via crea_version_json.py, ensuring the Google Chrome-style silent background updater validates and applies updates reliably.

## [0.70] - 2026-11-01
Germano AI v0.70 - New **AI Harness** architecture, real-time transparent **Glass Window**, integrated manual
sanitization and **silent updates like Google Chrome**. The interface has been reworked and simplified: it looks and
works in every respect like a modern AI harness, with the manual file sanitization tab next to it. The same interface is
in the Dashboard, the Remote Control and Germano Client. Engine, models, Proxy, formats and working folders do not
change.

### Added - AI Harness (new default tab)
- Four tabs at the top: **AI Harness** (default), **Manual Sanitization & Vault**, **Settings**, **Guide**;
  dark theme (`#0b0f19`, `#0f172a`, `#1e293b`, `#334155`, accents `#38bdf8` and `#818cf8`).
- Conversations in the sidebar (new, search, grouped by date, rename, delete; kept in the window profile, never in the
  cloud, or only for the session), instructions for the assistant, export to Markdown.
- **Streamed** answers with Markdown (headings, lists, tables, quotes), **syntax highlighting** and a **Copy code** button; restored data highlighted with the source tag, «Show tags»; indicators for total time, first token, input and
  output tokens, masked and restored data; Copy, Regenerate, Edit actions.
- A composer that grows with the text (**Enter** sends, **Shift+Enter** adds a new line), attachments with the
  paperclip or by **dragging them** (up to 12), protection and profile indicator.
- **Model picker at the bottom right**, with search: only the detected, usable AIs can be selected (turn 21 rule), the
  others stay greyed out with the reason and, when available, the protected alternative. Destinations: *Protection only*
  (copy of the protected text), local models of **Ollama, LM Studio and Jan** (one option per installed model),
  **Claude Code** run without tools, services via API (OpenAI, Anthropic, Meta Muse, Kimi, DeepSeek, Qwen, Mistral, Grok,
  Perplexity, Gemini, OpenRouter, Groq) with the computer's key or one entered in the picker. Automatic detection every
  12 seconds and when the window comes back to the foreground.
- The engine starts by itself on the first send; until it is ready the request is blocked (no data leaves).

### Added - Glass Window (Transparent Inspection)
- A **Glass Window** button (also Ctrl+Shift+G) that opens a frosted-glass side panel (`backdrop-filter: blur(16px)`)
  with the request status, a timer, the selector of the session's requests and the five phases in real time: **original
  text entered**, **Germano privacy filter and Vault mappings** (categories, highlighted text, original → tag →
  confidence table, timings and cache), **actual text sent to the model**, **raw HTTP / CLI payload** (address, headers
  with keys always masked, JSON body; for Claude Code command, variables, standard input and the HTTP payload captured by
  the Proxy) and the **real-time answer stream** before restoration (with raw SSE frames on request).
- **Stop operation**: immediately closes the connection to the AI service (socket shutdown) or terminates the CLI with
  all its processes; message «Operation stopped by the user via Glass Window: no further data was transmitted or
  received.». Closing the page or the connection also stops the execution on the server.
- **Review before sending** (optional): Germano stops after the protection and shows the exact payload; it leaves only
  with **Send now**, or **Block sending**. **Preview while typing** with the Glass Window open, without sending anything.

### Added - Manual sanitization, Remote Control and Germano Client
- The **Manual Sanitization & Vault** tab gathers the batch work of 0.60 (four `input`, `output`, `processed`,
  `failed` boxes like a file manager, documents table, requeue, CSV), manual text sanitization and the mapping archive.
- **Remote Control and Germano Client** have the same interface: AI Harness with picker and Glass Window (server AIs),
  **Manual Sanitization** with files dragged in and returned anonymized in their format and restoration of a file
  returned by an AI (only with the device's mappings), Settings (AIs and keys, processing options locked by the PA
  profile, tool connection; in the Client also server and updates), Guide. The Client relays the Harness events as a
  stream and stopping also closes the connection to the server. Clear notice when the server is an older version.

### Added - Silent updates, like Google Chrome
- **On by default**, with no banners or windows: only when the system reports an Internet connection, Germano reads
  `https://download.germano.ai/version.json`, **downloads in the background at low priority** (background-mode thread),
  checks the installer's size and structure and on Windows **prepares the new version** next to the one in use
  (`Germano AI.nuovo`, installer `--update --silent --stage` at minimum priority) while Germano stays open.
- At the **next start** the launcher applies the prepared update in a few seconds (`--apply-staged`: marker and per-file
  size check, then a quick folder swap) and Germano opens already updated; if anything goes wrong the version in use
  stays. Whoever wants it right away only finds a discreet **«Restart to update»** at the top (and a dot on the Settings
  tab).
- **Settings › Updates** like `chrome://settings/help`: «Germano AI is up to date (v0.70)» with the time of the last
  check, «Downloading the update in the background…» with the bar, «Restart Germano to apply the update», «Check now» and
  the options. On macOS and Linux the package is downloaded the same way and opened when the user decides.
- **Germano Client** updates itself the same way (`client_updater.py`, standard library only): silent download and
  update at the next start, with the server address and the session unchanged.

### Added - APIs
- `GET /api/harness/v2/targets`, `POST /api/harness/v2/run` (NDJSON stream: `start`, `original`, `phase`, `entities`,
  `sanitized`, `payload`, `gate`, `delta`, `thinking`, `usage`, `frame`, `cli`, `ping`, `done` / `aborted` / `error`),
  `POST /api/harness/v2/runs/<id>/abort`, `POST /api/harness/v2/runs/<id>/approve`, `POST /api/harness/v2/preview`,
  `GET /api/harness/v2/models`; from the network the Remote Control rules apply.
- `POST /api/remote/v1/anonymize_file` and `POST /api/remote/v1/restore_file` for file sanitization from the network
  devices (device options respected, PA lock included).

### Security
- Claude Code from the Harness: **no text among the arguments** (CLIs installed with npm are `.cmd` files run by
  `cmd.exe`, where a free argument could become a command): request and instructions go only through standard input.
  Local profile `--restricted --tools "" --strict-mcp-config --disable-slash-commands --no-session-persistence`, profile
  for the clients `--bare`; the CLI traffic goes through the Germano Proxy, which captures its payload for the Glass
  Window (from this computer only).
- Pages with CSP headers (`connect-src 'self'`, `img-src 'self'`); the Markdown renderer starts from already escaped
  text, never loads external images (an AI could use them to leak data in the address) and opens links separately.
- Keys always masked in the Glass Window; a key entered on a device travels only with its requests and the server never
  stores it.
- The tag instruction to the model uses a non-restorable example (`[CATEGORIA_N]`) and appears only when the request
  contains tags; restoration stays limited to the request's mappings.
- The anonymization cache (fingerprint of settings and text) is cleared together with the Vault. From the network each
  device or user can have at most 3 Harness requests in progress (429 beyond the limit) and only whoever started a
  request can stop or confirm it.

### Changed
- No more Simple / Advanced selector and no more AI Studio: the Harness replaces it, the detailed controls are in the
  Settings sections (Mode & network, Protection & models, AI keys & Harness, Proxy & APIs, System & log, Updates, About).
- The Proxy reads SSE streams incrementally even when the service does not use chunked encoding: fragments reach the
  editor right away (before, it waited for the end).
- Guide, README, LEGGIMI and CHANGELOG updated; `VERSION` → `0.70`.

## [0.60] - 2026-10-25
Germano becomes a **real desktop application**, distributed as **single-file installers** for Windows, macOS and
Linux that contain everything needed and **download nothing from the Internet**. One program, **`Germano`** (`Germano.exe` on Windows, `Germano.app` on macOS, the "Germano AI" menu entry on Linux): no black console window, no
browser with an address bar or tabs, and the **red X closes everything**. The internal architecture is unchanged (same
Python + Flask engine, local daemon, offline AI models, OCR, API Proxy).

### Added - Single-file installers
- **Windows**: `germano-0.60.exe` (suite, ~2.8 GB) and `germano-client-0.60.exe` (~22 MB). The suite installer **asks
  for administrator permission right away** (UAC prompt as soon as it opens, with Germano's name and icon) and **always** allows access from the local network: no checkbox to tick, a single Windows Firewall rule for Germano's Python, private
  and domain networks only (the open rules of versions 0.51/0.52 are removed). The program is still installed for the
  current user into `%LOCALAPPDATA%\Programs\…` (automatic updates ask for no permission), with Desktop and Start menu
  shortcuts, an entry in Settings › Apps and working folders in `Documents\Germano AI`; at the end the window closes and
  **Germano opens by itself**, with the user's normal permissions, with no instruction pages. The **uninstaller** (Settings › Apps) asks for permission at start to remove the firewall rule and removes the program, shortcuts, the
  Settings › Apps entry and the technical files (optionally the working folders and the Vault too). The client asks for
  no permission and has its own shortcuts ("Germano AI Client"), so both editions can live on the same computer. The
  runtime includes the Microsoft Visual C++ DLLs: no redistributable to install.
- **Windows, immediate startup screen**: as soon as the installer opens, a "Germano AI" window with an animated bar
  appears right away; it stays during the UAC prompt and the extraction, and closes by itself when the setup window
  appears. The **UAC prompt also arrives within moments**: permission is requested for a small launcher (the same
  program without the data, a few KB) instead of the ~3 GB file, which Windows used to check in full without showing
  anything (27 seconds measured on a test PC). The confirmation page no longer shows the note about the firewall
  rule: the rule is still created, silently, with the administrator permission (the outcome stays in the setup log).
- **macOS**: `germano-0.60.pkg` (Apple Silicon, macOS 14 or later) and `germano-client-0.60.pkg` (Apple Silicon and
  Intel, macOS 11 or later): macOS Installer packages with a self-contained `Germano.app`; with "Install for me only"
  no administrator password; at the end Germano opens by itself (not for command-line installs).
- **Linux**: `germano-0.60.deb` and `germano-client-0.60.deb` for Ubuntu 26.04 LTS and 64-bit Debian/Ubuntu
  distributions: program in `/opt`, menu entry and `germano-ai` / `germano-ai-client` command, no dependency on other
  packages.
- The macOS and Linux packages contain Python 3.11 with the same library versions tested on Windows.

### Added - Desktop application
- **`Germano.exe`**, the only executable on Windows: a GUI launcher (no console) that starts the bundled runtime
  (`runtime\pythonw.exe`) on the window manager `germano_desktop.py`.
- One name for both editions: in the **full suite** it opens the **unified Dashboard** (offline Standalone, LAN Server,
  Client mode); in the **light client** it opens the client panel (`client_ui.py`: find server, status, server AIs,
  «ask a server AI», «protect text/files»).
- **Dedicated app window**: Microsoft Edge in app mode on Windows, the system WebKit on macOS, Qt WebEngine (bundled)
  on Linux; isolated profile, no tabs and no address bar.
- **Full shutdown with the red X**: the manager cleanly stops **only** Germano's processes (Flask server + AI daemon),
  with no orphan processes and without touching other system processes.

### Added - Remote Control: Germano from any browser on the network, with nothing to install
- With Server mode on, any PC, tablet or smartphone on the local network opens `http://<server-IP>:8181/` (the
  `/remote` page, mobile-friendly and bilingual) and finds: the **server's AIs**, discovered automatically, the
  **protected chat** (prompt and up to 12 attachments anonymized by the server before leaving, answer with the data
  restored and the exact text received by the AI), **Protect and restore** for any AI (restoration on the device), the
  **processing options** and the Proxy addresses for the device's tools.
- **AI services via API** through Germano: Meta Muse (Muse Wonder, Muse Spark), Kimi (Moonshot AI), DeepSeek, Qwen,
  Mistral, Grok (xAI), Perplexity (Sonar), Google Gemini, OpenAI, Anthropic, OpenRouter, Groq and the server's local
  models (Ollama, LM Studio). The user's API key (used only for that request, never stored by the server) or the
  server's key, if the administrator shares this computer's AIs. The server runs its CLIs for the clients only when
  verified and without tools (Claude Code): agents that would run commands or modify files on the server are never run,
  and the Remote Control shows the protected alternative.
- The **Proxy** also forwards to the service named in the path: `http://<server>:8181/p/<service>/v1` (e.g.
  `/p/deepseek/v1`, `/p/moonshot/v1`, `/p/meta/v1`), so Kimi Code, Mistral Vibe, Qwen Code, OpenCode and the SDKs go
  through Germano.
- **Germano Client** uses the same interface (served by the client, which forwards to the server): the same
  capabilities as the browser, plus finding the server on the network and launching the PC's CLIs protected. New
  commands: `client login`, `client logout`, `client options`; `client ask` also with the services (`--model`, `--key`).

### Added - User management for network access
- By default network access needs **no credentials**. In the server's Dashboard (Settings › Network access › User
  management) the administrator creates the users and enables sign-in with **user name and password**, for the browser
  (sign-in screen, `HttpOnly` and `SameSite=Strict` session cookie) and for Germano Client (`client login`).
- Passwords stored only as a **PBKDF2-SHA256** hash (600,000 iterations, random salt) in `config.json`; random 256-bit
  sessions kept on the server only as a SHA-256 hash, valid 30 days from the last use, closed when the password changes
  or the user is deleted; 5 wrong attempts in 10 minutes block the address for 10 minutes; the same response time for
  existing and non-existing users. Without credentials, network requests get `401`. From the server computer
  (127.0.0.1) administration never needs credentials.
- The Dashboard's Client mode signs in to a server with user management enabled using user name and password (only the
  session is kept). If the server refuses access (missing or expired session) the engine stops right away with the
  reason, with no repeated attempts, and no data is processed; with the local fallback enabled this computer's models
  are used.

### Added - Client processing options and PA profile lock
- From the Remote Control and Germano Client you choose the confidence threshold, the active models, the 18 categories
  of personal data and the masking (restorable numbered tags, generic tags or the new `████` blackout): they apply only
  to that client's requests, the server configuration does not change.
- **PA profile or `lock_settings`**: the options are disabled and greyed out in the clients, with the notice «Locked by
  the Server's PA compliance profile» (or the administrator's lock); the server rejects every change with
  `403 Forbidden` (Compliance Lock) and the engine also ignores the clients' options.
- The engine re-reads the settings at every request: a profile change (PA/PD) applies immediately, also to the
  clients' options.

### Added - Extended and automatic AI detection
- Also recognized: Meta Muse Code (Muse Wonder, Muse Spark), Kimi Code CLI, Qwen Code, DeepSeek (Deep Code, Reasonix),
  Mistral Vibe, Grok Build (xAI), Perplexity (pplx), GitHub Copilot CLI, ChatGPT, Jules, Cursor CLI, Kiro and Kiro CLI,
  Trae, Zed, OpenCode, Goose, Cline, Kilo Code, Amp, Droid, Crush, llama.cpp and Jan, besides the ones already known.
- Detection also reads the PATH saved in the registry (CLIs installed after Germano started) and also works on macOS
  and Linux (executables without extension, apps in `/Applications`).
- **"Send to" only towards the detected AIs** (AI Studio, Remote Control and Germano Client): only the installed CLIs and
  apps, the installed models of a running Ollama or LM Studio (one option per model) and, in the Remote Control, the
  services via API with a key (the server's, or entered on the device with " Enter the key") can be chosen; the other
  entries stay visible **greyed out and not selectable**, with the reason ("not detected", "not running", "no model
  installed", "API key needed"). Default destination: the first detected AI, otherwise copying the protected text.
- **Automatic detection of the installed models**: Germano reads the model list of Ollama (`/api/tags`) and of
  LM Studio / Jan (`/v1/models`), on `127.0.0.1` only; the pages refresh by themselves every 12 seconds, when they come
  back to the foreground and when the Studio or the chat opens, without reloading or restarting Germano (5-second server
  cache). If the chosen destination disappears, the first available one is used, with a notice. The server refuses an
  undetected local model anyway (409); `client ask` with a local model and no `--model` uses the first installed one.

### Added - Windows Server and virtual machines
- **Windows Server 2019, 2022 and 2025** (Standard and Datacenter) and **virtual machines** (VMware, Hyper-V, Proxmox
  VE / KVM, VirtualBox, AWS, Azure, Google Cloud). The installer checks the real Windows version and reports: «Germano
  AI requires 64-bit Windows 10, Windows 11 or Windows Server 2019 or higher».
- **Without Microsoft Edge or Chrome** (Windows Server 2019, Server Core) Germano does not open Internet Explorer, which
  cannot show the Dashboard: a notice shows the addresses to open and with OK Germano stays active as a server without a
  window (with Cancel it closes). The same happens if the window does not open (e.g. corporate policies), instead of
  closing. Edge installed for the user is recognized too.
- **Windowless mode** for servers, VMs and scheduled tasks: `Germano.exe --no-browser` (or `--headless`,
  `GERMANO_HEADLESS=1`), `--mode=server` for a single start, `Germano.exe --stop` to stop it; the local and network
  addresses (Remote Control, Proxy) and the network warnings go to the log and the console, no dialogs. Reopened from
  the shortcut while it runs without a window, Germano only opens a window on the same Dashboard (no second server).
  `GERMANO_TECH_DIR` picks the technical folder.
- **Threads sized to the vCPUs**: all the processors granted to the program up to 2, then one left free for the web
  server and the system (on 4 cores it costs 2%), at most 16; OpenMP, MKL and OpenBLAS set before PyTorch loads;
  `"cpu_threads"` in `config.json` or `GERMANO_CPU_THREADS` to choose them, the administrator's `OMP_NUM_THREADS`
  honored.
- **Precision according to the processor**: on CPUs without native BF16 (AVX2, e.g. Xeon E5 v3/v4) BF16 is 4 to 10
  times slower (measured), so FP32 is used even with less than 12 GB of RAM when at least 7 are free; if BF16 does not
  work Germano switches to FP32 by itself, at startup or during processing.
- Virtual machine, processors, threads and native BF16 shown in the engine log and in the engine status.
- **Network and firewall**: in the server Dashboard, the console and the log, warnings with the command to fix a network
  classified as «Public», a firewall rule that is missing, disabled or for another program, and Group Policy ignoring
  local rules. The Remote Control addresses list first the adapter that reaches the network (virtual adapters too) and
  leave out the automatic 169.254.x.x addresses.
- **Shared data folder** (SMB/NFS, virtual disks): an operating-system lock on the data folder, a second engine (even
  from another computer) is refused with a clear message: the Vault never has two writers.
- Self-contained runtime verified: Visual C++ 2015-2022 DLLs included (`vcruntime140`, `vcruntime140_1`, `msvcp140`,
  `msvcp140_1`, `msvcp140_2`, `vcomp140`, `concrt140` and the others) and the dependencies of all 408 runtime binaries
  checked: the rest are standard Windows components.

### Security
- From the network (Proxy, Remote Control, shared AIs) restoration uses **only the tags of the request itself**: a
  device can no longer get back the data of other documents in the Vault (e.g. by asking an AI to «repeat
  [PERSONA_1]»). Requests made from the server computer keep using the whole Vault.
- Removed the **shared token** for the network clients (`lan_token`, «New token»): replaced by open access or user
  management. The `/g/<token>/` Base URL prefix stays, with the session's personal token.

### Changed - Dashboard: work folders preview
- The "Elaborazione dei documenti" (document processing) section (drop area and pending / ready / failed counters) is
  replaced by a **file-manager-style preview**: four boxes `input`, `output`, `processed` and `failed` with the folder's
  **full path** above each one and the files they contain, updated in real time (newly arrived files highlighted, the
  file being processed at the top of `input`, the reason for failed files with "Queue again").
- Documents are dragged straight onto the **input** box ("Drag files here into the input folder"); a click on a box or
  on its path opens the folder in File Explorer (Finder on macOS, the file manager on Linux). Texts in Italian and
  English.

### Changed - Updates
- Only source: **https://download.germano.ai/** (`version.json`, or else the file listing). No more Google Drive and no
  SHA-256 digest: files on the official server are considered trustworthy, only the completeness of the download is
  checked.
- Windows: the new version's installer is downloaded into the user's technical folder and, with "Install now" or at
  the next start, updates Germano keeping working folders, Vault and settings, then reopens it; a failed update is not
  retried at every start.
- macOS and Linux: the Dashboard points to the new `.pkg` / `.deb` to download and open with a double click.

### Changed
- `VERSION` → `0.60`; `config.json` reset to clean defaults; Dashboard, Guide and README texts updated (installation,
  working folders, Vault in `extracted/deanonymize_vault.json`).
- Release layout: `sorgenti/` (only the code publishable on GitHub, for Windows, macOS and Linux), `dipendenze/`
  (runtimes and libraries for offline use, per operating system), `modelli/` (the 6 AI models) and `releases/` (the
  installers only).

### Fixed
- A second engine started by mistake on the same data folder deleted, while closing, the status files of the first
  one (`ready.flag`, `status.json`): a refused instance now leaves them alone.

### Removed
- Executables with different names (`GermanoServer.exe`, `GermanoClient.exe`, `GermanoClient.app`,
  `GermanoClient.desktop`): only `Germano` exists.
- `START.bat` and `START_SERVER.bat`: Germano is installed with the installer and started from its shortcut; Server
  mode is chosen in the app Settings.
- The separate client files (`client.py`, `client_ui.py`, …) from the full suite: the suite uses its own Client mode
  built into the Dashboard.

## [0.52-alpha] - 2026-10-24
Germano now works in four **operating modes**, chosen on first launch and changeable at any time: **Standalone** (default, everything on this computer), **Server** (offers the engine and the proxy to the other office PCs),
**Client** (hands the model computation over to a Germano Server on the network) or **Server + Client**. Every element
of the Dashboard has a hover tooltip. Runtime and models are unchanged from 0.51; it works offline on a freshly
installed Windows 11.

### Added - Bilingual interface (Italian/English)
- The whole Dashboard and the offline Guide are **bilingual**. At startup the language is taken from the URL
  (`?lang=it|en`), then from the saved choice, finally from the browser language (Italian if it starts with `it`,
  otherwise English). The **IT /  EN flags** at the top switch instantly, tooltips included; the choice is
  remembered and shared between Dashboard and Guide. The tags used in documents (`[PERSONA]`, …) and the *Activity
  log* messages stay in Italian. Server messages shown in the interface follow the `X-Germano-Lang` header.

### Added - Server AIs shared with the clients
- The Germano Server can **run its own AI CLIs for the clients** (e.g. Claude Code): new endpoints
  `GET /api/harness/v1/tools` (list of the server's AIs and which can be used remotely) and
  `POST /api/harness/v1/run` (non-interactive execution, always through the Proxy: only anonymized text leaves towards
  the AI, the answer comes back with the real data). A client without that CLI locally uses it with `client ask`;
  `client models` shows the catalog. Sharing is **off by default** and is enabled in *Settings › Network access*
  (`share_ai_tools`), because it uses the server's account and credentials. Graphical tools (Antigravity, Cursor,
  Claude Desktop, Windsurf) are listed as not usable remotely, with the reason. Client mode and the remote engine also
  accept the server address in short form (`192.168.1.10`) or as a Base URL with token copied from the Dashboard, with
  understandable network messages.

### Added - Operating mode at startup
- **Welcome dialog** on the first Dashboard launch: three checkboxes — **[x] Standalone** (default), **[ ] Server**,
  **[ ] Client** — each one explained; Server and Client can be selected together. The dialog states that the mode
  *can always be changed at any time in the Settings* («Questa modalità è sempre modificabile in qualsiasi momento
  nelle Impostazioni»). Closing it without choosing confirms Standalone and it is not shown again.
- New **Impostazioni** (Settings) button and mode indicator in the top bar (green = Server, blue = Client, orange =
  attention, e.g. server unreachable); in Advanced mode the **Sistema › Rete e modalità operativa** panel summarizes
  network listening, the connection to the server and the token.
- The mode **applies immediately, without restarting Germano**: the Dashboard always and only listens on
  `127.0.0.1`; the Server part adds and removes, live, a second network listener (`0.0.0.0`, or the `bind_host` IP)
  and the UDP discovery. In **Standalone** and **Client** no Germano port is open to the network. Server and Client
  start the engine by themselves; changing the Client part restarts the engine with the right type (local or remote).
- With the Server part active, the Settings show the IP addresses, the client token (with **Nuovo token** — new
  token — which immediately invalidates the previous one) and the auto-discovery status.
- **`Germano.exe`** now sets `GERMANO_MODE=server`: it forces Server mode for that run only, without changing
  the saved choice (the Dashboard says so). `GERMANO_HOST=0.0.0.0` remains supported.
- Changing the mode, the token and searching for servers are reserved to the computer itself (`/api/mode`,
  `/api/mode/token`, `/api/remote/servers`, never from the network) and honor `lock_settings`: with settings locked by
  the administrator the mode cannot be changed, the interface preferences can.

### Added - Client mode (remote engine)
- New `germano/remote_engine.py`: in Client mode the daemon **does not load the models** (a few MB of memory instead
  of several GB) and sends the Germano Server only the texts and images to analyze; it receives positions,
  categories and scores. **Vault, tags, files and restoration stay on this computer**: the server keeps nothing from
  the clients and does not log their file names. The server applies the client's settings (models and threshold), so
  the result matches the local engine's.
- The server is found automatically through UDP discovery (a GPU server is preferred) or its address is entered in
  the Settings, with a **Cerca server in rete** (search the network) button. The server token is mandatory.
- **Fail-safe**: if the server does not answer Germano sends nothing, the proxy and the Studio block the request with
  a clear message (HTTP 503) and documents stay in the `input` folder (not among the failed ones) until the server is
  back; processing then resumes by itself. Optional: fall back to the local engine if no server answers at startup
  (`client_fallback_local`).
- Server shared engine: `GET /api/engine/v1/info`, `POST /api/engine/v1/classify` and
  `/api/engine/v1/{ocr,faces,signatures,plates}`, always with the token. A server that delegates its own computation
  does not share its engine (no chains) and no installation discovers itself (`instance_id`).

### Added - Tooltips
- An explanation on hover (and with the Tab key) for every element of the Dashboard: buttons, folder cards, live
  statistics (CPU, RAM, throughput), engine and mode status, the Anonimizza file / Studio AI and Semplice / Avanzata
  selectors, API address fields, models, data categories and threshold. On by default, they can be turned off in the
  Settings (`enable_tooltips`).

### Added - LAN Server mode
- **LAN auto-discovery** (`germano/discovery.py`): a lightweight UDP responder on port **8182** answers
  `GERMANO_DISCOVERY_PING` pings with the server's info (service, version, port, name, shared engine status) — never
  the token, never personal data. `GET /api/discovery` returns the same over HTTP. The default Dashboard port is now
  **8181**.
- **Tiered security for network access** (nothing changes for `127.0.0.1`-only use):
  - from the network, read-only and without a token: Dashboard, `/api/status`, `/api/ai/detect`, `/api/discovery`;
  - from the network, with a **shared token**: the proxy to the AIs (`/v1/messages`, `/v1/chat/completions`, …),
    `POST /api/studio/send` and the shared engine (`/api/engine/v1/…`). The token travels in the `X-Germano-Auth`
    header **or** as a `/g/<token>` Base URL prefix (so it works with any CLI, unmodified). Without a valid token
    access is always denied;
  - **server computer only**: engine control, settings, mode, files, the mapping archive and de-anonymization
    (`/api/v1/deanonymize_*`). Real data is never exposed to the network.
  - Extended anti DNS-rebinding: only loopback hosts, IP literals and the computer name are accepted.
- The shared token is generated randomly when the Server part is first enabled and saved in `config.json`;
  `/api/settings` no longer returns any token.
- New settings in `config.json`: `operating_mode`, `first_run_done`, `remote_server`, `remote_token`,
  `client_fallback_local`, `enable_tooltips`, `bind_host`, `discovery_enabled`, `discovery_port`, `lan_token`,
  `server_name`, `instance_id`, `instance_host`.
- `GERMANO_DATA_DIR` variable: moves configuration, working folders, Vault and log to another folder (models and
  runtime stay with the program); allows several independent instances of the same installation.
- When opened from another computer, the Dashboard shows the proxy addresses with the server's real IP.
- **Kimi, DeepSeek and Qwen Integration**: added to the local detection catalog (`ai_detect.py`) on both server and client. In AI Studio they are available directly as forwarding targets; in the *AI Agents and API* tab, 1-click preset buttons allow instantly setting the OpenAI target to: OpenAI, DeepSeek (`api.deepseek.com`), Kimi (`api.moonshot.cn`), Qwen (`dashscope.aliyuncs.com`), and Ollama.

### Fixed - from the client/server test campaign of 24/10
- **Privacy: damaged Office and OpenDocument files are no longer marked «ready» with personal data in clear.** If an
  internal text part (e.g. `word/document.xml`, `styles.xml`) cannot be read, the file goes to *Non riusciti*
  (failed) with the reason, instead of being copied to the output without anonymization.
- A damaged or truncated PDF stayed stuck forever in the `input` folder (with a copy in `failed` and no reason): it
  now goes to the failed documents with a clear message.
- Images and scans: when the data covers only part of the line read by the OCR, the black box could leave the first
  or last character uncovered (e.g. the first two letters of the tax code after «Codice fiscale:», the initial of a
  name). The position now accounts for the different widths of the characters.
- Understandable messages for damaged PDFs, images and archives (previously: technical errors with the full path).
- `Thumbs.db`, `desktop.ini` and hidden files no longer count as pending documents: previously the batch never
  showed as completed and the Dashboard stayed on «Documenti in arrivo».
- `GET /api/ai/detect` requested from the network returns the names and versions of the AIs but not their
  installation paths (they revealed the server's Windows user name).
- **Network auto-discovery** (Client mode and Germano Client): on a PC without a local server the search stopped
  right away, at the first «port unreachable» notice Windows returns for the ping to 127.0.0.1, and often missed the
  LAN servers. It now listens for answers for the whole expected time; answers with an invalid port are discarded.
- `Germano.exe` uses Windows line endings (CRLF), like `Germano.exe`.

### Added - Germano Client v0.01 (separate product)
- New **`germano_client`** application (separate folder), very lightweight: it **contains no models** (28 MB of
  runtime). It finds the server on the LAN by itself (UDP broadcast), falling back to `client_config.json` or a
  command-line parameter, and routes local CLIs (Claude Code, Codex, Aider, Gemini CLI) to the server's proxy by
  setting `ANTHROPIC_BASE_URL`/`OPENAI_BASE_URL` with the `/g/<token>` prefix.
- **`START_CLIENT.bat`** launcher with an interactive menu and `discover`, `status`, `launch <cli>`, `send`,
  `config` commands. Documentation in `README.md` and `README.en.md`.

## [0.51-alpha] - 2026-10-22
Consolidation release: full audit of the 0.50 code (bugs verified with reproducible tests), modular rewrite of the
engine (`germano/`), a completely redesigned Dashboard and automatic updates. Runtime, libraries and models are
unchanged: it works offline on a freshly installed Windows 11.

### Added - New Dashboard
- Redesigned interface, light and sober, with the official logo. **Semplice / Avanzata** (Simple / Advanced)
  selector; in Advanced Mode four tabs: *Elaborazione* (Processing), *Agenti AI e API* (AI agents and API),
  *Filtri e modelli* (Filters and models), *Sistema e registro* (System and log). The Dashboard labels are in Italian.
- **Batch work**: add files or whole folders (drag & drop or *Seleziona file* / *Seleziona cartella*), **Apri cartella
  input** and **Apri cartella output** buttons (File Explorer), *In attesa* / *Pronti* / *Non riusciti* (pending /
  ready / failed) counters, batch progress and final summary, a notice with *Avvia elaborazione* (start processing)
  when documents are waiting and the engine is paused.
- **Documenti** table with *Pronti*, *In attesa*, *Non riusciti* and *Originali* (Advanced) tabs, a filter by name,
  folder or reason, and *Apri* (open), *Mostra nella cartella* (show in folder) and *Scarica* (download) actions.
  Failed documents show the reason and can be queued again one by one or all together (**Rimetti in coda**);
  **Esporta elenco** saves the table as CSV for Excel (`;` separator, protected against formula injection).
- For every processed document the mode, the number of redacted items and the time are recorded
  (`state/outputs.json`) and shown in the table.
- **Agenti AI e API** tab: Proxy addresses to copy (OpenAI `/v1` and Anthropic formats), a table showing where to set
  them in Claude Code, Codex CLI, Cursor, Antigravity, Windsurf, OpenCode, Continue, Aider and the OpenAI and
  Anthropic SDKs, target services and REST API examples with `curl.exe`.
- *Sistema e registro* tab: working folder paths with *Apri* (open) and *Copia percorso* (copy path) buttons, update
  settings, mapping archive and live log.
- New local APIs: `GET /api/folders`, `POST /api/file_action` (shows/opens a file; only documents are opened, never
  executables or scripts), `POST /api/retry_failed`, `GET /api/update/status`, `POST /api/update/check|download|install`.

### Added - Dual mode and AI Studio
- The Dashboard now has a main switch **Anonimizza file** (Anonymize files) / **Studio AI** (the choice is
  remembered).
- **Anonymize files**: at the top of the view, a grid of **folder cards** (pending, ready, errors, originals,
  vault/extracted) with live counters; clicking a card opens that folder in File Explorer. A **live stats** strip:
  files processed/total in the batch, redacted PII, documents per minute, CPU and RAM usage, with a progress bar.
- **AI Studio**: you write a prompt and attach files; the text and the attachments' content are **anonymized by the
  local engine before** being forwarded to an AI. If the engine is not running the request is blocked and ** no data
  leaves the computer**. The conversation always shows *what* is sent (already with the labels) and the list of
  redacted items; a button copies the protected text.
- **Rileva AI** (Detect AI): a button that finds the AIs and CLIs installed on the computer (Claude Code, Claude
  Desktop, Antigravity, Gemini CLI, Codex, Aider, Cursor, Windsurf, Ollama, LM Studio) by reading the file system and
  local ports (no process started, no network): a chip with a green check for the ready ones and a target selector.
  Detection is not limited to `PATH` (Claude Code and Antigravity install outside `PATH`).
- **Configurazione Granulare** (Granular configuration): a button in the Studio that opens a drawer with the *protection
  profile*, *analysis models* (sensitivity included) and *data categories* panels, to tune what gets redacted on the fly.
- New local APIs: `GET /api/ai/detect` (list of installed AIs, cached for 30 s, `?refresh=1` to rescan) and
  `POST /api/studio/send` (protects prompt and attachments and returns the text ready to send, with the redacted items).

### Added - Automatic updates
- **Only when Windows reports that the PC is connected to the Internet** (Network List Manager: the check sends no
  packets), 20 seconds after startup and then every 6 hours, Germano opens `https://download.germano.ai`, the single
  reference for new versions, which points to the public Google Drive folder holding the packages, and looks there for
  the most recent `GermanoAI_Release_v<version>.zip`. On a disconnected PC no connection attempt is made.
- When it is newer than the installed version the package is downloaded (also past Google Drive's confirmation page
  for large files), accepted only over HTTPS from download.germano.ai and Google domains, checked (complete download,
  SHA-256 fingerprint when the folder also holds `<ZIP name>.sha256`, CRC of every file in the ZIP, VERSION matching
  the file name), extracted and prepared in the `update/` folder.
- Installation at the next `Germano.exe` start or right away with *Installa ora e riavvia* (install now and restart): a
  separate installer replaces the program components, keeps `input`, `output`, `processed`, `failed`, `extracted`,
  `state` and `config.json`, puts the previous version back if anything fails and restarts Germano.
- `check_updates` and `auto_update` options (also in the Dashboard, *Sistema e registro → Aggiornamenti*) and a
  *Controlla ora* (check now) button.

### Fixed - Data loss and privacy
- **DOCX files destroyed by anonymization**: 0.50 rewrote every paragraph with `paragraph.text = ...`, wiping bold
  text, fonts, hyperlinks and **the pictures** of the document; the author stayed in the metadata. Word, Excel and
  PowerPoint files are now edited directly in their XML: only personal text changes, everything else stays identical.
- **Document parts never analyzed**: footnotes, text boxes, nested tables, comments (and their authors), tracked
  changes, content controls, grouped shapes and PowerPoint SmartArt, speaker notes, charts, ODT headers/footers
  (`styles.xml`), metadata (author, last modified by, title), preview thumbnails.
- **Italian NER model blind beyond ~512 tokens**: on long texts it detected nothing after the first lines (test: 0
  entities on 5,500 characters, 7 after the fix). The text is now split into overlapping chunks.
- **Scanned PDFs with a digital stamp** (typical in public administrations: a protocol number printed on a scan): no
  OCR, so the content stayed readable. OCR now runs whenever the page images carry little digital text.
- **"Searchable" scans**: only the invisible text layer was removed while the image stayed visible. The pixels
  underneath are now blanked as well.
- **Rotated PDF pages**: faces, signatures and OCR text were blacked out in the wrong place (coordinates were not
  de-rotated).
- **PDF**: form fields, comments and their author, bookmarks, metadata/XMP, `mailto:` links, embedded files (also in
  subfolders, which used to cause an error) and PAdES digital signatures (carrying the signer's name and tax code) are
  now anonymized or removed. A missed occurrence is no longer confused with another one (character-level redaction
  instead of `search_for`).
- **Attachments sent in clear text**: emails skipped their attachments; ZIP archives copied unsupported or failed files
  unchanged; the Proxy forwarded images and PDFs untouched in the Anthropic and OpenAI Responses formats. Everything is
  now anonymized, or excluded/blocked (fail-safe principle).
- **Vault that could be wiped**: concurrent writes without locking, and a failed read treated as an empty vault that
  was then saved over the good one. Now: locking, atomic writes, backup copy when the file is unreadable.
- **Restore with wrong data**: non-numbered tags (`[PERSONA]`) were replaced with the last name seen. Only numbered
  tags are restored now; with the switch off, the vault no longer stores real data.
- **ANSI texts**: TXT/CSV files encoded as Windows-1252 lost their accented letters (`errors="ignore"`).
- **HTML comments** turned into visible text after anonymization.
- Images were re-exported at 72 dpi (loss of resolution), only the first page of multi-page TIFFs was kept, EXIF
  rotation of photos was not applied and GPS metadata was preserved.
- Originals in `processed/` could be overwritten by a file with the same name.

### Fixed - API Proxy (Claude Code, Codex, Cursor, Antigravity)
- **Broken streaming for Anthropic and OpenAI Responses**: the `event:` line was split from the `data:` line, so every
  event arrived empty and the SDKs failed on the first event. New spec-compliant SSE parser.
- Text held back to reassemble a split tag was lost at the end of a block; a single buffer was shared between text and
  tool arguments (corrupted JSON). Now there is one buffer per block, flushed when the block ends.
- Values restored inside tool JSON arguments were not escaped (quotes/newlines broke the JSON).
- Claude's signed `thinking` blocks were modified (signature no longer valid).
- AI service errors (e.g. 401) returned as a malformed 200 stream; `anthropic-beta` headers and `?beta=true` parameters
  not forwarded; `/v1/messages/count_tokens` missing.
- Performance: one HTTP call to the engine for every message and no caching; now a single batched call with a cache
  of already analyzed blocks.

### Fixed - Stability
- The engine kept running (about 6 GB of RAM) after the Germano window was closed: it now stops on its own.
- When importing `daemon.py`, the server deleted on exit the PID of the still running engine (possible double engine).
- `.doc`/`.ppt`/`.rtf` through Word always failed in the worker thread (missing CoInitialize) and risked closing the
  Word instance already opened by the user; `.ppt` files were saved in PPTX format with a `.ppt` extension.
- Excel sheet names containing personal data: the XLSX ended up in `failed` (character `[` not allowed).
- `.xls`: anonymized cells lost their style.
- Files processed while still being copied; Office temporary files (`~$`) and `Thumbs.db` ended up in `failed`; locked
  files reprocessed forever; partial outputs left behind on shutdown.
- Fixed 5-minute timeout: long documents always failed (now 60 configurable minutes, cooperative cancellation instead
  of threads left running).
- Concurrent access to the models from several threads (random "Already borrowed" errors): now serialized.
- Log read in full every second and never rotated; full folder scan on every status request.
- `Germano.exe`: `%errorlevel%` checked inside a block (always evaluated beforehand), network folders not supported.

### Security
- Anti DNS-rebinding (local hosts only) and anti CSRF protection (no actions from external websites) on the local API,
  which exposes the vault with real data; `/api/start` and `/api/stop` are POST only.
- The engine's internal API now runs on a dynamic port protected by a token (it used to be fixed port 8001, without
  authentication).
- HTML escaping in the Dashboard (file names and vault values).
- No document data is ever sent over the network. The only automatic connection is the update check (see above),
  only when Windows reports Internet access, and it can be turned off (`"check_updates": false`).
- Office conversions run in a separate process, with macros disabled and a timeout.

### Added
- **Native RTF** without Microsoft Word (Windows 11 24H2 no longer even ships WordPad).
- **Signed `.p7m` files (CAdES)**: the inner document is extracted and anonymized (e.g. `fattura.xml.p7m`).
- `.doc`/`.ppt`/`.xls` files that are actually renamed RTF, DOCX, HTML or XML are recognized without Office;
  conversion through LibreOffice when Microsoft Office is not installed.
- New formats: `.json`, `.jsonl`, `.tsv`, `.md`, `.log`, source code, `.gif`, Office templates (`.dotx`, `.potx`...).
- Validated RegEx: IBANs with spaces and from all over Europe (checksum), Italian tax codes with omocodia and an
  OCR-tolerant variant, VAT numbers, payment cards (Luhn), real-world phone formats (`333 123 4567`, `+39`, `02/...`),
  dates, license plates, Italian electronic ID cards (CIE), cadastre references, upper-case company names
  (`ROSSI SRL`), API keys and passwords.
- **Propagation**: a name detected in one place is redacted in every other occurrence in the document.
- FatturaPA fields (Nome, Cognome, CodiceFiscale, Indirizzo...) recognized by their structure.
- Automatic precision of the main model: FP32 with at least 12 GB of RAM, BF16 (half the memory) below that.
- Dashboard: real-time progress (file and page), reason of each failed document, banners for engine errors and for an
  unreachable server, drag & drop of whole folders, visible PA/PD profile, new options (precision, timeout,
  anonymized file names, separate Anthropic service).
- Administrative settings lock (`"lock_settings": true` in `config.json`) for the PA profile.
- Option to anonymize file and folder names too (`anonymize_filenames`).
- Running `Germano.exe` while Germano is already open opens the existing Dashboard instead of a "port in use" error.
- `Germano.exe` warnings for Smart App Control, overly long paths and incomplete packages.
- Proxy: Windows certificate store (corporate networks with TLS inspection), daily session logs in JSONL.

### Changed
- `check_updates` is now on by default (it used to be off), with the safeguards described above; new `auto_update`.
- Dashboard labels: *Avvia motore* / *Arresta motore* (start / stop engine) instead of *ATTIVA GERMANO* /
  *FERMA GERMANO*; the *Ripristino automatico dei dati originali* (automatic restore) switch now sits below the box
  for adding documents.

### Documentation
- Updated bilingual offline guide, with the Dashboard's light theme: "What's new in v0.51" section, step-by-step batch
  work, the four Advanced Mode tabs, automatic updates, instructions to move from 0.50 to 0.51 keeping the Vault and
  settings, `/api/v1/deanonymize_file` endpoint, local API security, OpenAI and Anthropic service fields in the Claude
  Code, Codex, Cursor and Antigravity setup.
- README and changelog available in English as well (`README.en.md`, `CHANGELOG.en.md`).

## [0.50-alpha] - 2026-10-20
Standalone architecture for vanilla Windows 11 (100% offline), 6 bundled local AI models, Simple/Advanced Dashboard,
automatic de-anonymization and API Proxy. Details (in Italian) in [CHANGELOG.md](CHANGELOG.md).
