# Changelog

🌍 *Leggi questo documento in altre lingue: [Italiano](CHANGELOG.md)*

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Releases up to 0.50-alpha are documented in Italian only, in [CHANGELOG.md](CHANGELOG.md).

## [0.60] - 2026-10-25
Germano becomes a **real desktop application**, distributed as **single-file installers** for Windows, macOS and
Linux that contain everything needed and **download nothing from the Internet**. One program, **`Germano`**
(`Germano.exe` on Windows, `Germano.app` on macOS, the "Germano AI" menu entry on Linux): no black console window, no
browser with an address bar or tabs, and the **red X closes everything**. The internal architecture is unchanged (same
Python + Flask engine, local daemon, offline AI models, OCR, API Proxy).

### Added - Single-file installers
- **Windows**: `germano-0.60.exe` (suite, ~2.8 GB) and `germano-client-0.60.exe` (~22 MB). The suite installer **asks
  for administrator permission right away** (UAC prompt as soon as it opens, with Germano's name and icon) and **always**
  allows access from the local network: no checkbox to tick, a single Windows Firewall rule for Germano's Python, private
  and domain networks only (the open rules of versions 0.51/0.52 are removed). The program is still installed for the
  current user into `%LOCALAPPDATA%\Programs\…` (automatic updates ask for no permission), with Desktop and Start menu
  shortcuts, an entry in Settings › Apps and working folders in `Documents\Germano AI`; at the end the window closes and
  **Germano opens by itself**, with the user's normal permissions, with no instruction pages. The **uninstaller**
  (Settings › Apps) asks for permission at start to remove the firewall rule and removes the program, shortcuts, the
  Settings › Apps entry and the technical files (optionally the working folders and the Vault too). The client asks for
  no permission and has its own shortcuts ("Germano AI Client"), so both editions can live on the same computer. The
  runtime includes the Microsoft Visual C++ DLLs: no redistributable to install.
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

### Removed
- Executables with different names (`GermanoServer.exe`, `GermanoClient.exe`, `GermanoClient.app`,
  `GermanoClient.desktop`): only `Germano` exists.
- `START.bat` and `START_SERVER.bat`: Germano is installed with the installer and started from its shortcut; Server
  mode is chosen in the app Settings.
- The separate client files (`client.py`, `client_ui.py`, …) from the full suite: the suite uses its own Client mode
  built into the Dashboard.

## [0.52-alpha] - 2026-10-24
Germano now works in four **operating modes**, chosen on first launch and changeable at any time: **Standalone**
(default, everything on this computer), **Server** (offers the engine and the proxy to the other office PCs),
**Client** (hands the model computation over to a Germano Server on the network) or **Server + Client**. Every element
of the Dashboard has a hover tooltip. Runtime and models are unchanged from 0.51; it works offline on a freshly
installed Windows 11.

### Added - Bilingual interface (Italian/English)
- The whole Dashboard and the offline Guide are **bilingual**. At startup the language is taken from the URL
  (`?lang=it|en`), then from the saved choice, finally from the browser language (Italian if it starts with `it`,
  otherwise English). The **🇮🇹 IT / 🇬🇧 EN flags** at the top switch instantly, tooltips included; the choice is
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
- The Dashboard now has a main switch **📂 Anonimizza file** (Anonymize files) / **🧠 Studio AI** (the choice is
  remembered).
- **Anonymize files**: at the top of the view, a grid of **folder cards** (pending, ready, errors, originals,
  vault/extracted) with live counters; clicking a card opens that folder in File Explorer. A **live stats** strip:
  files processed/total in the batch, redacted PII, documents per minute, CPU and RAM usage, with a progress bar.
- **AI Studio**: you write a prompt and attach files; the text and the attachments' content are **anonymized by the
  local engine before** being forwarded to an AI. If the engine is not running the request is blocked and **no data
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
