# Changelog

🌍 *Leggi questo documento in altre lingue: [Italiano](CHANGELOG.md)*

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Releases up to 0.50-alpha are documented in Italian only, in [CHANGELOG.md](CHANGELOG.md).

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

### Added - Automatic updates
- **Only when Windows reports that the PC is connected to the Internet** (Network List Manager: the check sends no
  packets), 20 seconds after startup and then every 6 hours, Germano reads `update.json` with the latest version from
  GitHub. On a disconnected PC no connection attempt is made.
- When a newer version exists the package is downloaded from Google Drive (also past the confirmation page of large
  files), accepted only over HTTPS from Google domains, verified for size and SHA-256 fingerprint, extracted and
  checked in the `update/` folder.
- Installation at the next `START.bat` start or right away with *Installa ora e riavvia* (install now and restart): a
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
- `START.bat`: `%errorlevel%` checked inside a block (always evaluated beforehand), network folders not supported.

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
- Running `START.bat` while Germano is already open opens the existing Dashboard instead of a "port in use" error.
- `START.bat` warnings for Smart App Control, overly long paths and incomplete packages.
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
