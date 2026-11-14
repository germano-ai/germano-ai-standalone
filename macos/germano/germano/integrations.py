"""Integrazioni di Germano nei flussi di lavoro esterni (0.95, turno 30): registro CANONICO degli strumenti.

Server MCP (germano/mcp_server.py), manuale UTCP e documento OpenAPI (germano/utcp.py) e API REST /api/v1/* (server.py)
usano questo stesso registro: un solo nome, un solo schema JSON di ingresso e di uscita e un solo gestore per ogni
strumento, cosi' MCP, UTCP, OpenAPI e REST non possono divergere.

Strumenti
- INGRESSO (prima di inviare dati a un sistema esterno): germano_anonymize_text, germano_anonymize_file,
  germano_inspect_entities (sola lettura), germano_leak_check (sola lettura);
- USCITA (dopo la risposta del sistema esterno): germano_deanonymize_text, germano_deanonymize_file;
- VERIFICA E STATO: germano_workflow_roundtrip, germano_status.

Sicurezza (fail-safe)
- Anonimizzazione, ispezione e controllo delle fughe passano dal motore di Germano (Sistema 1 + Sistema 2, corsia
  preferenziale delle richieste interattive): se il motore non e' pronto o va in errore si risponde con un errore
  strutturato «blocked» e MAI con il testo originale presentato come sicuro.
- Il ripristino sostituisce solo le etichette [TIPO_N] presenti nel testo o nel file ricevuto. Nessuno strumento elenca
  o scarica il Vault (lo stato riporta solo conteggi). Dalla rete locale il ripristino richiede l'ambito di ripristino
  (restore_scope) restituito dall'anonimizzazione fatta dalla stessa utenza, oppure la mappa (mapping) che il chiamante
  conserva: mai il Vault intero (stessa regola del Remote Control).
- Percorsi dei file (file_path, output_path): solo da questo computer, assoluti, dentro le cartelle consentite
  (Documenti, Desktop, Download dell'utente, cartelle di lavoro input/output/processed/failed e quelle aggiunte
  dall'amministratore in «integration_allowed_dirs» di config.json), mai nelle cartelle interne di Germano (Vault,
  stato, programma), mai in cartelle nascoste; un file esistente non viene sovrascritto senza overwrite=true.
- Dalla rete locale (parte Server) MCP e API v1 richiedono il token delle integrazioni (Authorization: Bearer) o una
  sessione utente valida: il controllo e' in server.py (_guard).
"""
import base64
import binascii
import hmac
import json
import os
import secrets
import shutil
import sys
import threading
import time
import uuid
from collections import Counter, OrderedDict

from . import common
from .vault import TAG_RE, normalize_tag, restore_text

SERVICE = "germano"
TITLE = "Germano AI"

TEXT_MAX_CHARS = 400_000              # come il prompt dello Studio e dell'Harness
BATCH_MAX_TEXTS = 256
BATCH_MAX_CHARS = 2_000_000           # come il motore condiviso (daemon_api.ENGINE_MAX_CHARS)
LEAK_MAX_STRINGS = 5_000
INLINE_FILE_MAX = 64 * 1024 * 1024    # file in base64 dentro JSON (ingresso e uscita)
PATH_FILE_MAX = 4 * 1024 ** 3         # file indicati per percorso (come MAX_CONTENT_LENGTH del server)
PREVIEW_DEFAULT = 2_000
PREVIEW_MAX = 200_000
MAX_RESTORE_TEXT_TAGS = 5_000         # etichette diverse in un testo da ripristinare (oltre: usare il file)
MAX_RESTORE_FILE_TAGS = 200_000
MAPPING_MAX = 20_000
FINDINGS_MAX = 1_000
ENGINE_WAIT_S = 120                   # attesa massima del motore appena avviato da una richiesta
MASKINGS = ("numbered", "generic", "blackout")


def version():
    return common.get_version()


def _L(lang, it, en):
    return en if lang == "en" else it


# ------------------------------------------------------------------------------------------------ errori e contesto
class ToolError(Exception):
    """Errore strutturato di uno strumento: codice stabile, messaggio IT/EN, stato HTTP e tipo («error» o «blocked»:
    richiesta fermata per protezione, nessun dato e' uscito)."""

    def __init__(self, code, it, en=None, status=400, kind="error", **data):
        super().__init__(en or it)
        self.code, self.it, self.en, self.status, self.kind, self.data = code, it, en or it, status, kind, data

    def payload(self, lang="it", tool=None):
        body = {"status": self.kind, "code": self.code, "message": self.en if lang == "en" else self.it}
        if tool:
            body["tool"] = tool
        body.update({k: v for k, v in self.data.items() if v is not None})
        return body


class CallContext:
    """Chi chiama e da dove: backend (motore, Vault e file di QUESTO Germano), locale o rete, identita' (per gli ambiti
    di ripristino), lingua dei messaggi, trasporto (mcp-http, mcp-sse, mcp-stdio, utcp, rest) e indirizzo di base."""

    def __init__(self, backend, local=True, principal="local", lang="it", transport="rest", base_url=None):
        self.backend = backend
        self.local = bool(local)
        self.principal = principal or ("local" if local else "remote")
        self.lang = "en" if lang == "en" else "it"
        self.transport = transport
        self.base_url = (base_url or "http://127.0.0.1:8181").rstrip("/")

    def L(self, it, en):
        return _L(self.lang, it, en)


# ------------------------------------------------------------------------------------------------ statistiche
class Stats:
    """Invocazioni dall'avvio (solo conteggi: nessun testo, nessun dato)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.started = time.time()
        self.total = 0
        self.ok = 0
        self.errors = 0
        self.blocked = 0
        self.by_tool = Counter()
        self.by_transport = Counter()
        self.last = None

    def record(self, tool, transport, outcome, ms):
        with self._lock:
            self.total += 1
            if outcome == "success":
                self.ok += 1
            elif outcome == "blocked":
                self.blocked += 1
            else:
                self.errors += 1
            self.by_tool[tool] += 1
            self.by_transport[transport] += 1
            self.last = {"tool": tool, "transport": transport, "outcome": outcome, "ms": int(ms),
                         "at": time.strftime("%Y-%m-%d %H:%M:%S")}

    def snapshot(self):
        with self._lock:
            out = {"since": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.started)), "total": self.total,
                   "success": self.ok, "errors": self.errors, "blocked": self.blocked,
                   "by_tool": dict(self.by_tool), "by_transport": dict(self.by_transport)}
            if self.last:
                out["last"] = dict(self.last)
            return out


STATS = Stats()


# ------------------------------------------------------------------------------------------------ ambiti di ripristino
class ScopeStore:
    """Ambiti di ripristino: identificativo opaco -> etichette create o usate da UNA anonimizzazione di una certa
    utenza. Dalla rete il ripristino vale solo per quelle etichette (mai l'intero Vault). Solo nomi di etichette, nessun
    dato: in memoria, 24 ore, al massimo SCOPES_MAX ambiti (i piu' vecchi escono per primi)."""

    TTL = 24 * 3600
    SCOPES_MAX = 5_000
    TAGS_MAX = 50_000

    def __init__(self):
        self._lock = threading.Lock()
        self._items = OrderedDict()

    def _prune(self, now):
        for sid in [k for k, v in self._items.items() if now - v["used"] > self.TTL]:
            self._items.pop(sid, None)

    def create(self, principal, tags):
        tags = [t for t in tags if t][: self.TAGS_MAX]
        if not tags:
            return None
        sid = "gs_" + secrets.token_urlsafe(18)
        now = time.time()
        with self._lock:
            self._prune(now)
            self._items[sid] = {"principal": principal, "tags": set(tags), "created": now, "used": now}
            while len(self._items) > self.SCOPES_MAX:
                self._items.popitem(last=False)
        return sid

    def tags(self, sid, principal):
        if not isinstance(sid, str) or not sid.startswith("gs_") or len(sid) > 64:
            return None
        now = time.time()
        with self._lock:
            item = self._items.get(sid)
            if not item or now - item["used"] > self.TTL:
                self._items.pop(sid, None)
                return None
            if not hmac.compare_digest(str(item["principal"]).encode(), str(principal).encode()):
                return None
            item["used"] = now
            self._items.move_to_end(sid)
            return set(item["tags"])

    def drop_principal(self, principal):
        with self._lock:
            for sid in [k for k, v in self._items.items() if v["principal"] == principal]:
                self._items.pop(sid, None)

    def count(self):
        with self._lock:
            return len(self._items)


SCOPES = ScopeStore()


# ------------------------------------------------------------------------------------------------ token delle integrazioni
_TOKEN_LOCK = threading.Lock()


def ensure_token():
    """Token delle integrazioni (Authorization: Bearer) per MCP e API v1 dalla rete locale: creato alla prima
    necessita', conservato in config.json, mostrato solo nella Dashboard di questo computer."""
    with _TOKEN_LOCK:
        tok = str(common.load_config().get("integration_token") or "")
        if len(tok) >= 24:
            return tok
        tok = secrets.token_urlsafe(32)
        common.save_config({"integration_token": tok}, admin=True)
        return tok


def regenerate_token():
    with _TOKEN_LOCK:
        tok = secrets.token_urlsafe(32)
        common.save_config({"integration_token": tok}, admin=True)
    SCOPES.drop_principal("token")
    return tok


def token_matches(candidate):
    tok = str(common.load_config().get("integration_token") or "")
    if len(tok) < 24 or not isinstance(candidate, str) or not candidate:
        return False
    return hmac.compare_digest(candidate.encode("utf-8", "replace"), tok.encode("utf-8"))


# ------------------------------------------------------------------------------------------------ percorsi consentiti
def _known_folder(guid):
    """Cartella nota di Windows (Documenti, Desktop, Download) anche se rinominata, tradotta o reindirizzata."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
        g = GUID()
        ctypes.oledll.ole32.CLSIDFromString(guid, ctypes.byref(g))
        p = ctypes.c_wchar_p()
        ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p))
        path = p.value
        ctypes.windll.ole32.CoTaskMemFree(p)
        return path or None
    except Exception:
        return None


def _xdg_dir(name):
    try:
        import subprocess
        out = subprocess.run(["xdg-user-dir", name], capture_output=True, text=True, timeout=5).stdout.strip()
        if out and os.path.isdir(out) and os.path.abspath(out) != os.path.expanduser("~"):
            return out
    except Exception:
        pass
    return None


_FOLDERS_CACHE = []


def user_folders():
    """Documenti, Desktop e Download dell'utente (solo quelle esistenti)."""
    if _FOLDERS_CACHE:
        return list(_FOLDERS_CACHE[0])
    home = os.path.expanduser("~")
    found = []
    if os.name == "nt":
        guids = ("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}", "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
                 "{374DE290-123F-4565-9164-39C4925E467B}")
        for guid, fallback in zip(guids, ("Documents", "Desktop", "Downloads")):
            found.append(_known_folder(guid) or os.path.join(home, fallback))
    else:
        for xdg, fallback in (("DOCUMENTS", "Documents"), ("DESKTOP", "Desktop"), ("DOWNLOAD", "Downloads")):
            found.append((_xdg_dir(xdg) if sys.platform != "darwin" else None) or os.path.join(home, fallback))
    out = []
    for p in found:
        if p and os.path.isdir(p) and p not in out:
            out.append(p)
    _FOLDERS_CACHE.append(tuple(out))
    return out


def _norm(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _inside(path, root):
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:              # unita' diverse (Windows)
        return False


def allowed_roots(cfg=None):
    """Cartelle in cui gli strumenti possono leggere e scrivere file indicati per percorso."""
    cfg = cfg or common.load_config()
    roots = list(user_folders())
    roots += [common.INPUT_DIR, common.OUTPUT_DIR, common.PROCESSED_DIR, common.FAILED_DIR]
    extra = cfg.get("integration_allowed_dirs")
    if isinstance(extra, list):
        for p in extra[:50]:
            if isinstance(p, str) and p.strip() and os.path.isabs(p.strip()) and os.path.isdir(p.strip()):
                roots.append(p.strip())
    out, seen = [], set()
    for r in roots:
        n = _norm(r)
        if n not in seen and os.path.isdir(r):
            seen.add(n)
            out.append(r)
    return out


def _protected_roots():
    """Cartelle interne di Germano: mai lette o scritte dagli strumenti (Vault e report, stato, configurazione,
    programma, cache e modelli). Le cartelle di lavoro input/output/processed/failed restano consentite."""
    roots = [common.EXTRACTED_DIR, common.STATE_DIR, common.CACHE_DIR, common.BASE_DIR, common.MODELS_DIR]
    for var in ("GERMANO_TECH_DIR", "GERMANO_CACHE_DIR"):
        if os.environ.get(var):
            roots.append(os.environ[var])
    return [_norm(r) for r in roots if r]


def _work_roots():
    return [_norm(p) for p in (common.INPUT_DIR, common.OUTPUT_DIR, common.PROCESSED_DIR, common.FAILED_DIR)]


def path_policy(lang="it"):
    """Descrizione della politica dei percorsi (Dashboard, risorsa germano://capabilities)."""
    return {
        "local_only": True,
        "absolute_paths_only": True,
        "allowed_roots": allowed_roots(),
        "never": _L(lang, "Vault e report (extracted), stato e configurazione di Germano, cartella del programma, "
                          "cache e modelli, cartelle e file nascosti",
                    "Vault and reports (extracted), Germano state and configuration, program folder, cache and "
                    "models, hidden folders and files"),
        "overwrite": _L(lang, "un file esistente si sovrascrive solo con overwrite=true",
                        "an existing file is overwritten only with overwrite=true"),
        "config_key": "integration_allowed_dirs",
    }


def _hidden_parts(real, root):
    rel = os.path.relpath(real, root)
    return any(part.startswith(".") for part in rel.split(os.sep) if part not in ("", "."))


def check_path(raw, ctx, output=False, overwrite=False):
    """Percorso reale e verificato per un file indicato da chi chiama (ToolError se non consentito).
    output=True: destinazione da scrivere (la cartella deve esistere; un file esistente solo con overwrite)."""
    if not ctx.local:
        raise ToolError("path_not_allowed_remote",
                        "I percorsi dei file valgono solo da questo computer: dalla rete invia il contenuto in "
                        "content_base64 e ricevi il risultato nella risposta.",
                        "File paths are accepted only from this computer: from the network send the content in "
                        "content_base64 and receive the result in the response.", status=403)
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 1000 or "\x00" in raw:
        raise ToolError("invalid_path", "Percorso non valido.", "Invalid path.")
    raw = raw.strip()
    if not os.path.isabs(raw):
        raise ToolError("invalid_path", "Indica un percorso assoluto (es. C:\\Users\\nome\\Documents\\file.pdf).",
                        "Use an absolute path (e.g. /home/name/Documents/file.pdf).")
    real = os.path.realpath(os.path.abspath(raw))
    nreal = os.path.normcase(real)
    roots = [(r, _norm(r)) for r in allowed_roots()]
    match = next((r for r, n in roots if _inside(nreal, n)), None)
    protected = [p for p in _protected_roots() if _inside(nreal, p)]
    in_work = any(_inside(nreal, w) for w in _work_roots())
    data_dir = _norm(common.DATA_DIR)
    if (match is None or (protected and not in_work)
            or (_inside(nreal, data_dir) and not in_work)):
        raise ToolError("path_not_allowed",
                        "Percorso non consentito: usa le cartelle Documenti, Desktop o Download, le cartelle di lavoro "
                        "di Germano o quelle aggiunte dall'amministratore (integration_allowed_dirs). Le cartelle "
                        "interne di Germano (Vault, stato, programma) non sono mai accessibili.",
                        "Path not allowed: use the Documents, Desktop or Downloads folders, Germano's work folders or "
                        "the folders added by the administrator (integration_allowed_dirs). Germano's internal folders "
                        "(Vault, state, program) are never accessible.", status=403)
    if _hidden_parts(nreal, _norm(match)):
        raise ToolError("path_not_allowed", "Cartelle e file nascosti non sono consentiti.",
                        "Hidden folders and files are not allowed.", status=403)
    if output:
        if os.path.isdir(real):
            return real
        parent = os.path.dirname(real)
        if not os.path.isdir(parent):
            raise ToolError("invalid_path", "La cartella di destinazione non esiste.",
                            "The destination folder does not exist.")
        if os.path.exists(real) and not overwrite:
            raise ToolError("output_exists", "Il file di destinazione esiste gia': scegli un altro nome o usa "
                                             "overwrite=true.",
                            "The destination file already exists: choose another name or use overwrite=true.",
                            status=409)
        return real
    if not os.path.isfile(real):
        raise ToolError("file_not_found", "File non trovato.", "File not found.", status=404)
    if common.is_ignored_file(real):
        raise ToolError("path_not_allowed", "File nascosto, di sistema o temporaneo: non consentito.",
                        "Hidden, system or temporary file: not allowed.", status=403)
    if os.path.getsize(real) > PATH_FILE_MAX:
        raise ToolError("file_too_large", "File troppo grande (massimo 4 GB).", "File too large (at most 4 GB).",
                        status=413)
    return real


# ------------------------------------------------------------------------------------------------ argomenti
def _invalid(ctx, it, en):
    return ToolError("invalid_arguments", it, en, status=400)


def _opt_str(args, name, ctx, max_len=None):
    v = args.get(name)
    if v is None:
        return None
    if not isinstance(v, str):
        raise _invalid(ctx, f"«{name}» deve essere un testo.", f"«{name}» must be a string.")
    if max_len and len(v) > max_len:
        raise ToolError("too_large", f"«{name}» e' troppo lungo (massimo {max_len:,} caratteri).".replace(",", "."),
                        f"«{name}» is too long (at most {max_len:,} characters).", status=413)
    return v


def _opt_bool(args, name, default, ctx):
    v = args.get(name, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "1", "yes", "si", "on", "false", "0", "no", "off"):
        return v.strip().lower() in ("true", "1", "yes", "si", "on")
    if v is None:
        return default
    raise _invalid(ctx, f"«{name}» deve essere true o false.", f"«{name}» must be true or false.")


def _opt_int(args, name, default, lo, hi, ctx):
    v = args.get(name, default)
    if v is None:
        return default
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise _invalid(ctx, f"«{name}» deve essere un numero intero.", f"«{name}» must be an integer.") from None
    return max(lo, min(hi, n))


def _texts(args, ctx):
    """(testi, singolo) da «text» oppure «texts» (esattamente uno dei due)."""
    text, texts = args.get("text"), args.get("texts")
    if text is not None and texts is not None:
        raise _invalid(ctx, "Indica «text» oppure «texts», non entrambi.", "Send either «text» or «texts», not both.")
    if text is not None:
        if not isinstance(text, str):
            raise _invalid(ctx, "«text» deve essere un testo.", "«text» must be a string.")
        if len(text) > TEXT_MAX_CHARS:
            raise ToolError("too_large", "Testo troppo lungo (massimo 400.000 caratteri): usa germano_anonymize_file.",
                            "Text too long (at most 400,000 characters): use germano_anonymize_file.", status=413)
        return [text], True
    if texts is None:
        raise _invalid(ctx, "Manca il testo: indica «text» (oppure «texts» per un elenco).",
                       "Missing text: send «text» (or «texts» for a list).")
    if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
        raise _invalid(ctx, "«texts» deve essere un elenco di testi.", "«texts» must be a list of strings.")
    if not texts:
        raise _invalid(ctx, "«texts» e' vuoto.", "«texts» is empty.")
    if len(texts) > BATCH_MAX_TEXTS or sum(len(t) for t in texts) > BATCH_MAX_CHARS:
        raise ToolError("too_large", "Troppi testi (massimo 256 e 2.000.000 di caratteri in tutto).",
                        "Too many texts (at most 256 and 2,000,000 characters in total).", status=413)
    if any(len(t) > TEXT_MAX_CHARS for t in texts):
        raise ToolError("too_large", "Un testo supera i 400.000 caratteri.", "A text exceeds 400,000 characters.",
                        status=413)
    return list(texts), False


def _masking(args, ctx):
    m = args.get("masking")
    if m is None:
        return "numbered" if common.load_config().get("enable_deanonymize", True) else "generic"
    if m not in MASKINGS:
        raise _invalid(ctx, "«masking» deve essere numbered, generic o blackout.",
                       "«masking» must be numbered, generic or blackout.")
    return m


# ------------------------------------------------------------------------------------------------ esiti del motore
def category_of(entity):
    """Categoria leggibile (PERSONA, EMAIL, COD.FISCALE/P.IVA...) di un dato oscurato, qualunque sia il mascheramento."""
    label = entity.get("label") or ""
    nt = normalize_tag(label)
    if nt:
        return nt[1:-1].rsplit("_", 1)[0]
    if len(label) > 2 and label.startswith("[") and label.endswith("]"):
        return label[1:-1]                       # etichetta generica, es. [PERSONA]
    from .detect import categorize
    return categorize(entity.get("entity"))[1][1:-1]   # oscuramento ████: categoria dal gruppo del modello


def level_of(status):
    """Livello di decisione: system1 (Sistema 1), system2 (deciso nel contesto dal Sistema 2), system1_doubt (dubbio
    del Sistema 1 rimasto oscurato per precauzione: Sistema 2 spento, non disponibile o non abbastanza sicuro)."""
    return {"confirmed": "system1", "s2_confirmed": "system2", "doubt": "system1_doubt"}.get(status or "confirmed",
                                                                                            "system1")


def _system2_summary(results, enabled):
    decisions = [d for r in results for d in (r.get("system2") or [])]
    c = Counter(d.get("decision") for d in decisions)
    return {"enabled": bool(enabled), "decisions": len(decisions), "confirmed": c.get("confermato", 0),
            "released": c.get("rilasciato", 0), "uncertain": c.get("incerto", 0) + c.get("non_deciso", 0)}


def _placeholders(entities):
    return sorted({nt for nt in (normalize_tag(e.get("label") or "") for e in entities) if nt},
                  key=lambda t: (t.rsplit("_", 1)[0], int(t[:-1].rsplit("_", 1)[1])))


def _mapping(entities):
    out = {}
    for e in entities:
        nt = normalize_tag(e.get("label") or "")
        if nt and e.get("word"):
            out.setdefault(nt, e["word"])
    return out


def _clean(d):
    return {k: v for k, v in d.items() if v is not None}


def _ms(t0):
    return int(round((time.perf_counter() - t0) * 1000))


def require_engine(ctx):
    """Motore pronto, oppure (se consentito) avviato e atteso; altrimenti richiesta BLOCCATA (nessun dato esce)."""
    b = ctx.backend
    if b.engine_ready():
        return
    if b.autostart_allowed():
        b.ensure_engine(ENGINE_WAIT_S)
        if b.engine_ready():
            return
        raise ToolError("engine_starting",
                        "Il motore di Germano si sta avviando (caricamento dei modelli): riprova tra poco. Nessun dato "
                        "e' stato elaborato o inviato.",
                        "The Germano engine is starting (loading the models): try again shortly. No data was processed "
                        "or sent.", status=503, kind="blocked", retry_after=15)
    raise ToolError("engine_not_ready",
                    "Il motore di Germano non e' pronto: avvialo dalla Dashboard (o attiva l'avvio automatico nelle "
                    "Impostazioni > Integrazioni). Nessun dato e' stato elaborato o inviato.",
                    "The Germano engine is not ready: start it from the Dashboard (or enable automatic start in "
                    "Settings > Integrations). No data was processed or sent.", status=503, kind="blocked")


# ------------------------------------------------------------------------------------------------ file in ingresso e uscita
def _decode_b64(value, ctx):
    if not isinstance(value, str) or not value:
        raise _invalid(ctx, "«content_base64» non valido.", "Invalid «content_base64».")
    if len(value) > (INLINE_FILE_MAX * 4) // 3 + 16:
        raise ToolError("file_too_large", "File troppo grande per l'invio in base64 (massimo 64 MB): usa file_path "
                                          "da questo computer.",
                        "File too large for base64 transfer (at most 64 MB): use file_path from this computer.",
                        status=413)
    try:
        data = base64.b64decode(value.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise _invalid(ctx, "«content_base64» non e' base64 valido.", "«content_base64» is not valid base64.") from None
    if not data:
        raise _invalid(ctx, "Il file e' vuoto.", "The file is empty.")
    return data


def _input_file(args, ctx):
    """(percorso temporaneo in state/uploads, nome, byte, origine) del file da elaborare."""
    fp, b64 = args.get("file_path"), args.get("content_base64")
    if fp is not None and b64 is not None:
        raise _invalid(ctx, "Indica «file_path» oppure «content_base64», non entrambi.",
                       "Send either «file_path» or «content_base64», not both.")
    if fp is not None:
        real = check_path(fp, ctx)
        name = common.safe_filename(args.get("filename") or os.path.basename(real))
        staged = ctx.backend.stage_file(real, name)
        return staged, name, os.path.getsize(staged), real
    if b64 is None:
        raise _invalid(ctx, "Manca il file: indica «file_path» (da questo computer) oppure «content_base64» con "
                            "«filename».",
                       "Missing file: send «file_path» (from this computer) or «content_base64» with «filename».")
    fname = args.get("filename")
    if not isinstance(fname, str) or not fname.strip():
        raise _invalid(ctx, "Con «content_base64» serve «filename» (con l'estensione, es. contratto.docx).",
                       "«content_base64» requires «filename» (with the extension, e.g. contract.docx).")
    data = _decode_b64(b64, ctx)
    name = common.safe_filename(fname)
    staged = ctx.backend.stage_bytes(data, name)
    return staged, name, len(data), None


def _final_name(out_name, default_name, produced):
    """Nome del file prodotto: se l'elaborazione cambia l'estensione (es. archivio RAR -> .rar.zip, .p7m -> file
    interno) si aggiunge quella vera."""
    ext_p = os.path.splitext(produced)[1].lower()
    if ext_p and not out_name.lower().endswith(ext_p):
        return out_name + ext_p
    return out_name


def _deliver(tmp_out, produced_name, args, ctx, prefix, source=None):
    """Consegna il file prodotto: in output_path (solo da questo computer) e/o in base64 nella risposta. Un file
    indicato per percorso senza output_path finisce nella cartella output di Germano (come nella Dashboard) e la
    risposta ne riporta il percorso; un file arrivato in base64 torna in base64."""
    out = {"filename": produced_name, "bytes": os.path.getsize(tmp_out)}
    dest_raw = args.get("output_path")
    if dest_raw is None and source is not None:
        os.makedirs(common.OUTPUT_DIR, exist_ok=True)
        dest_raw = common.unique_path(os.path.join(common.OUTPUT_DIR, prefix + produced_name))
    want_b64 = _opt_bool(args, "return_content", dest_raw is None, ctx)
    if dest_raw is not None:
        overwrite = _opt_bool(args, "overwrite", False, ctx)
        dest = check_path(dest_raw, ctx, output=True, overwrite=overwrite)
        if os.path.isdir(dest):
            dest = os.path.join(dest, prefix + produced_name)
            dest = check_path(dest, ctx, output=True, overwrite=overwrite)
        else:
            dest = _final_name(dest, prefix + produced_name, produced_name)
            if dest != os.path.realpath(dest_raw.strip()):
                dest = check_path(dest, ctx, output=True, overwrite=overwrite)
        tmp_dest = dest + ".germano-part"
        try:
            shutil.copyfile(tmp_out, tmp_dest)
            os.replace(tmp_dest, dest)
        except OSError as e:
            common.remove_quietly(tmp_dest)
            raise ToolError("write_failed", f"Impossibile scrivere il file di destinazione ({e.strerror or e}).",
                            f"Cannot write the destination file ({e.strerror or e}).", status=500) from None
        out["output_path"] = dest
        out["filename"] = os.path.basename(dest)
    if want_b64:
        if out["bytes"] > INLINE_FILE_MAX:
            if dest_raw is None:
                raise ToolError("file_too_large", "Il risultato supera i 64 MB: indica output_path (da questo computer).",
                                "The result exceeds 64 MB: use output_path (from this computer).", status=413)
        else:
            with open(tmp_out, "rb") as f:
                out["content_base64"] = base64.b64encode(f.read()).decode("ascii")
    return out


def _preview(path, chars):
    if chars <= 0:
        return None
    try:
        from . import formats
        return (formats.sample_text(path, max_chars=chars) or "")[:chars]
    except Exception:
        return None


# ------------------------------------------------------------------------------------------------ ripristino limitato
def _found_tags(texts):
    found = set()
    for t in texts:
        if isinstance(t, str) and "[" in t:
            for m in TAG_RE.finditer(t):
                nt = normalize_tag(m.group(0))
                if nt:
                    found.add(nt)
    return found


def _restore_source(args, ctx, found, limit):
    """(mappa etichetta -> dato limitata alle etichette trovate, origine). Mai l'intero Vault: solo le etichette
    presenti; dalla rete solo quelle dell'ambito di ripristino o della mappa del chiamante."""
    if len(found) > limit:
        raise ToolError("too_many_placeholders",
                        f"Troppe etichette diverse da ripristinare in una richiesta ({len(found)}, massimo {limit}): "
                        "usa germano_deanonymize_file per i documenti grandi.",
                        f"Too many different placeholders to restore in one request ({len(found)}, at most {limit}): "
                        "use germano_deanonymize_file for large documents.", status=413)
    mapping, scope = args.get("mapping"), args.get("restore_scope")
    if mapping is not None:
        if not isinstance(mapping, dict) or len(mapping) > MAPPING_MAX:
            raise _invalid(ctx, "«mapping» deve essere un oggetto {\"[PERSONA_1]\": \"valore\"} (massimo 20.000 voci).",
                           "«mapping» must be an object {\"[PERSONA_1]\": \"value\"} (at most 20,000 entries).")
        source = {}
        for k, v in mapping.items():
            nk = normalize_tag(k)
            if nk and isinstance(v, str) and v:
                source[nk] = v[:2000]
        return {t: source[t] for t in found if t in source}, "mapping"
    tag_map = ctx.backend.tag_map()
    if scope is not None:
        allowed = SCOPES.tags(scope, ctx.principal)
        if allowed is None:
            raise ToolError("scope_not_found",
                            "Ambito di ripristino sconosciuto, scaduto (24 ore o riavvio di Germano) o di un'altra "
                            "utenza: ripeti l'anonimizzazione oppure usa «mapping».",
                            "Unknown or expired restore scope (24 hours or Germano restart) or owned by another "
                            "identity: repeat the anonymization or use «mapping».", status=404)
        return {t: tag_map[t] for t in found if t in allowed and t in tag_map}, "scope"
    if not ctx.local:
        raise ToolError("scope_required",
                        "Dalla rete il ripristino vale solo per i dati della tua anonimizzazione: indica "
                        "«restore_scope» (restituito da germano_anonymize_*) oppure «mapping».",
                        "From the network restoration only covers the data of your own anonymization: send "
                        "«restore_scope» (returned by germano_anonymize_*) or «mapping».", status=403)
    return {t: tag_map[t] for t in found if t in tag_map}, "vault"


def _count_restored(texts, tag_map):
    n = 0
    for t in texts:
        if isinstance(t, str) and "[" in t:
            for m in TAG_RE.finditer(t):
                if normalize_tag(m.group(0)) in tag_map:
                    n += 1
    return n


# ------------------------------------------------------------------------------------------------ strumenti: INGRESSO
def _anonymize(texts, ctx, masking, use_s2, dry_run=False, positions=False):
    require_engine(ctx)
    overrides = {"masking": masking, "system2": bool(use_s2)}
    if dry_run:
        overrides["dry_run"] = True
    return ctx.backend.anonymize_texts(texts, overrides, positions=positions)


def _effective_masking(masking):
    """Con il ripristino disattivato nelle Impostazioni (enable_deanonymize) le etichette non sono numerate."""
    if masking == "numbered" and not common.load_config().get("enable_deanonymize", True):
        return "generic"
    return masking


def _s2_enabled(use_s2):
    return bool(use_s2) and bool(common.load_config().get("enable_system2", True))


def h_anonymize_text(args, ctx):
    t0 = time.perf_counter()
    texts, single = _texts(args, ctx)
    masking = _masking(args, ctx)
    use_s2 = _opt_bool(args, "use_system2", True, ctx)
    want_map = _opt_bool(args, "return_mapping", False, ctx)
    results = _anonymize(texts, ctx, masking, use_s2)
    entities = [e for r in results for e in (r.get("extracted_data") or [])]
    placeholders = _placeholders(entities)
    effective = _effective_masking(masking)
    out = {"status": "success",
           "replacements": len(entities),
           "categories": dict(Counter(category_of(e) for e in entities)),
           "placeholders": placeholders,
           "masking": effective,
           "reversible": effective == "numbered",
           "system2": _system2_summary(results, _s2_enabled(use_s2))}
    if single:
        out["anonymized_text"] = results[0]["anonymized"]
    else:
        out["anonymized_texts"] = [r["anonymized"] for r in results]
    if placeholders:
        out["restore_scope"] = SCOPES.create(ctx.principal, placeholders)
    if want_map:
        out["mapping"] = _mapping(entities)
    ctx.backend.session_log(entities)
    out["elapsed_ms"] = _ms(t0)
    return _clean(out)


def _precheck_output(args, ctx):
    """output_path controllato PRIMA dell'elaborazione (cartella consentita, file esistente senza overwrite)."""
    if args.get("output_path") is not None:
        check_path(args.get("output_path"), ctx, output=True, overwrite=_opt_bool(args, "overwrite", False, ctx))


def h_anonymize_file(args, ctx):
    t0 = time.perf_counter()
    masking = _masking(args, ctx)
    use_s2 = _opt_bool(args, "use_system2", True, ctx)
    preview = _opt_int(args, "preview_chars", PREVIEW_DEFAULT, 0, PREVIEW_MAX, ctx)
    _precheck_output(args, ctx)
    staged, name, size, source = _input_file(args, ctx)
    try:
        require_engine(ctx)
        res = ctx.backend.process_file(staged, name, {"masking": masking, "system2": bool(use_s2)})
    finally:
        common.remove_quietly(staged)
    tmp_out = res["out_path"]
    try:
        entities = res.get("extracted_data") or []
        placeholders = _placeholders(entities)
        produced = res.get("filename") or name
        out = {"status": "success", "input": {"filename": name, "bytes": size}}
        if source:
            out["input"]["file_path"] = source
        out["output"] = _deliver(tmp_out, produced, args, ctx, "anonimizzato_", source)
        out["text_preview"] = _preview(tmp_out, preview)
        effective = _effective_masking(masking)
        out.update(replacements=len(entities), categories=dict(Counter(category_of(e) for e in entities)),
                   placeholders=placeholders, masking=effective, reversible=effective == "numbered",
                   notes=[str(n) for n in (res.get("notes") or [])][:50],
                   system2=_system2_summary([{"system2": res.get("system2") or []}], _s2_enabled(use_s2)))
        if placeholders:
            out["restore_scope"] = SCOPES.create(ctx.principal, placeholders)
        if _opt_bool(args, "return_mapping", False, ctx):
            out["mapping"] = _mapping(entities)
        ctx.backend.session_log(entities)
        ctx.backend.audit_file(name, res)
    finally:
        common.remove_quietly(tmp_out)
    out["elapsed_ms"] = _ms(t0)
    return _clean(out)


def _entities_view(results, include_values, path_of=None):
    entities, decisions = [], []
    for i, r in enumerate(results):
        where = path_of(i) if path_of else None
        for e in r.get("extracted_data") or []:
            item = {"unit": i, "start": int(e.get("start", 0)), "end": int(e.get("end", 0)),
                    "category": category_of(e), "entity": str(e.get("entity") or ""),
                    "score": float(e.get("score") or 0.0), "level": level_of(e.get("status"))}
            if where is not None:
                item["path"] = where
            if include_values:
                item["text"] = str(e.get("word") or "")
            entities.append(item)
        for d in r.get("system2") or []:
            item = {"unit": i, "start": int(d.get("start", 0)), "end": int(d.get("end", 0)),
                    "decision": {"confermato": "confirmed", "rilasciato": "released", "incerto": "uncertain",
                                 "non_deciso": "undecided"}.get(d.get("decision"), str(d.get("decision") or "")),
                    "entity": str(d.get("entity") or "")}
            if isinstance(d.get("p_personale"), (int, float)):
                item["p_personal"] = float(d["p_personale"])
            if where is not None:
                item["path"] = where
            if include_values:
                item["text"] = str(d.get("word") or "")
            decisions.append(item)
    return entities, decisions


def h_inspect_entities(args, ctx):
    t0 = time.perf_counter()
    texts, single = _texts(args, ctx)
    use_s2 = _opt_bool(args, "use_system2", True, ctx)
    include = _opt_bool(args, "include_values", True, ctx)
    results = _anonymize(texts, ctx, "generic", use_s2, dry_run=True, positions=True)
    entities, decisions = _entities_view(results, include)
    return {"status": "success", "read_only": True, "entity_count": len(entities),
            "categories": dict(Counter(e["category"] for e in entities)),
            "levels": dict(Counter(e["level"] for e in entities)),
            "entities": entities[:FINDINGS_MAX], "truncated": len(entities) > FINDINGS_MAX,
            "system2_decisions": decisions[:FINDINGS_MAX], "texts": len(texts),
            "system2": _system2_summary(results, _s2_enabled(use_s2)), "elapsed_ms": _ms(t0)}


def _walk(obj, path, out, budget):
    """Foglie testuali (e numeri lunghi, chiavi) di un JSON qualsiasi con il loro percorso JSONPath."""
    if len(out) >= LEAK_MAX_STRINGS:
        budget["truncated"] = True
        return
    if isinstance(obj, str):
        if obj.strip():
            out.append((path, obj))
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, (int, float)):
        s = str(obj)
        if len(s) >= 5:
            out.append((path, s))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            child = f"{path}.{key}" if key.replace("_", "").isalnum() else f"{path}[{json.dumps(key, ensure_ascii=False)}]"
            if key.strip() and not key.strip().isdigit():
                out.append((child + "#key", key))     # anche le chiavi: un nome o un'email possono fare da chiave
            _walk(v, child, out, budget)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _walk(v, f"{path}[{i}]", out, budget)


def h_leak_check(args, ctx):
    t0 = time.perf_counter()
    has_text, has_payload = "text" in args and args.get("text") is not None, "payload" in args
    if has_text == has_payload:
        raise _invalid(ctx, "Indica «text» oppure «payload» (JSON qualsiasi).", "Send «text» or «payload» (any JSON).")
    include = _opt_bool(args, "include_values", False, ctx)
    use_s2 = _opt_bool(args, "use_system2", True, ctx)
    budget = {}
    if has_text:
        text = _opt_str(args, "text", ctx, TEXT_MAX_CHARS)
        items = [("$", text)] if text.strip() else []
    else:
        items = []
        _walk(args.get("payload"), "$", items, budget)
    if budget.get("truncated"):
        raise ToolError("too_large", "Payload troppo grande da controllare (oltre 5.000 testi): dividilo.",
                        "Payload too large to check (over 5,000 strings): split it.", status=413)
    total = sum(len(v) for _p, v in items)
    if total > BATCH_MAX_CHARS or any(len(v) > TEXT_MAX_CHARS for _p, v in items):
        raise ToolError("too_large", "Payload troppo grande da controllare (massimo 2.000.000 di caratteri).",
                        "Payload too large to check (at most 2,000,000 characters).", status=413)
    placeholders = len(_found_tags([v for _p, v in items]))
    results = []
    for start in range(0, len(items), BATCH_MAX_TEXTS):
        chunk = items[start:start + BATCH_MAX_TEXTS]
        results += _anonymize([v for _p, v in chunk], ctx, "generic", use_s2, dry_run=True, positions=True)
    findings, _dec = _entities_view(results, include, path_of=lambda i: items[i][0])
    for f in findings:
        f["length"] = f["end"] - f["start"]
        f.pop("unit", None)
    safe = not findings
    return {"status": "success", "safe": safe, "verdict": "safe" if safe else "leak",
            "findings_count": len(findings), "categories": dict(Counter(f["category"] for f in findings)),
            "findings": findings[:FINDINGS_MAX], "truncated": len(findings) > FINDINGS_MAX,
            "strings_checked": len(items), "chars_checked": total, "placeholders_present": placeholders,
            "system2": _system2_summary(results, _s2_enabled(use_s2)), "elapsed_ms": _ms(t0)}


# ------------------------------------------------------------------------------------------------ strumenti: USCITA
def h_deanonymize_text(args, ctx):
    t0 = time.perf_counter()
    texts, single = _texts(args, ctx)
    found = _found_tags(texts)
    tag_map, source = _restore_source(args, ctx, found, MAX_RESTORE_TEXT_TAGS)
    restored = [restore_text(t, tag_map) if tag_map else t for t in texts]
    out = {"status": "success", "restored_count": _count_restored(texts, tag_map),
           "restored_placeholders": len(tag_map), "unmatched_placeholders": sorted(found - set(tag_map)),
           "source": source, "contains_personal_data": bool(tag_map)}
    dest_raw = args.get("output_path")
    if dest_raw is not None:
        if not single:
            raise _invalid(ctx, "«output_path» vale solo con «text».", "«output_path» works only with «text».")
        dest = check_path(dest_raw, ctx, output=True, overwrite=_opt_bool(args, "overwrite", False, ctx))
        if os.path.isdir(dest):
            dest = check_path(os.path.join(dest, "ripristinato.txt"), ctx, output=True,
                              overwrite=_opt_bool(args, "overwrite", False, ctx))
        with open(dest + ".germano-part", "w", encoding="utf-8", newline="") as f:
            f.write(restored[0])
        os.replace(dest + ".germano-part", dest)
        out["output_path"] = dest
        if _opt_bool(args, "return_text", False, ctx):
            out["restored_text"] = restored[0]
    elif single:
        out["restored_text"] = restored[0]
    else:
        out["restored_texts"] = restored
    out["elapsed_ms"] = _ms(t0)
    return out


def h_deanonymize_file(args, ctx):
    t0 = time.perf_counter()
    from . import formats
    preview = _opt_int(args, "preview_chars", 0, 0, PREVIEW_MAX, ctx)
    _precheck_output(args, ctx)
    staged, name, size, source = _input_file(args, ctx)
    tmp_dir = os.path.join(common.UPLOAD_DIR, "r_" + uuid.uuid4().hex[:10])
    try:
        found = _found_tags([formats.sample_text(staged)])
        tag_map, src = _restore_source(args, ctx, found, MAX_RESTORE_FILE_TAGS)
        if src == "vault" and not args.get("restore_scope") and args.get("mapping") is None:
            tag_map = ctx.backend.tag_map()           # in locale: anche le etichette fuori dal testo campionato
        elif src == "scope":
            allowed = SCOPES.tags(args.get("restore_scope"), ctx.principal) or set()
            full = ctx.backend.tag_map()
            tag_map = {t: full[t] for t in allowed if t in full}
        elif src == "mapping":
            tag_map = {}
            for k, v in (args.get("mapping") or {}).items():
                nk = normalize_tag(k)
                if nk and isinstance(v, str) and v:
                    tag_map[nk] = v[:2000]
        os.makedirs(tmp_dir, exist_ok=True)
        out_tmp = os.path.join(tmp_dir, name)
        fctx = formats.Ctx("restore", common.load_config(), tag_map=tag_map)
        try:
            real = formats.process_file(staged, out_tmp, fctx)
        except formats.UnsupportedFormat as e:
            raise ToolError("unsupported_format", str(e), str(e), status=415) from None
        except formats.ProcessingError as e:
            raise ToolError("processing_error", str(e), str(e), status=422) from None
        restored_tags = {normalize_tag(a.get("word") or "") for a in fctx.audit} - {None}
        produced = os.path.basename(real)
        out = {"status": "success", "input": _clean({"filename": name, "bytes": size, "file_path": source}),
               "output": _deliver(real, produced, args, ctx, "ripristinato_", source),
               "restored_count": len(fctx.audit), "restored_placeholders": len(restored_tags),
               "unmatched_placeholders": sorted(found - set(tag_map))[:500], "source": src,
               "contains_personal_data": bool(fctx.audit)}
        if preview:
            out["text_preview"] = _preview(real, preview)
    finally:
        common.remove_quietly(staged)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    out["elapsed_ms"] = _ms(t0)
    return _clean(out)


# ------------------------------------------------------------------------------------------------ verifica e stato
def h_workflow_roundtrip(args, ctx):
    """Ciclo controllato ingresso -> uscita: anonimizza, usa la risposta esterna indicata (o ne simula una che ripete
    il testo protetto), ripristina SOLO le etichette di questo ciclo, verifica che nulla sia rimasto in chiaro."""
    t0 = time.perf_counter()
    steps = []
    text = _opt_str(args, "text", ctx, TEXT_MAX_CHARS)
    if text is None or not text.strip():
        raise _invalid(ctx, "Manca «text».", "Missing «text».")
    reply = _opt_str(args, "external_reply", ctx, TEXT_MAX_CHARS)
    use_s2 = _opt_bool(args, "use_system2", True, ctx)
    verify = _opt_bool(args, "verify_residual", True, ctx)
    if not common.load_config().get("enable_deanonymize", True):
        raise ToolError("not_reversible", "Il ripristino dei dati e' disattivato in questo Germano: il ciclo completo "
                                          "non e' possibile.",
                        "Data restoration is disabled in this Germano: the full cycle is not possible.", status=409)
    s = time.perf_counter()
    res = _anonymize([text], ctx, "numbered", use_s2)[0]
    entities = res.get("extracted_data") or []
    anonymized = res["anonymized"]
    own = _placeholders(entities)
    steps.append({"step": "input_anonymize", "ok": True, "ms": _ms(s), "replacements": len(entities)})
    simulated = reply is None
    if simulated:
        reply = anonymized
    steps.append({"step": "external_system", "ok": True, "ms": 0, "simulated": simulated})
    s = time.perf_counter()
    found = _found_tags([reply])
    full = ctx.backend.tag_map()
    tag_map = {t: full[t] for t in found if t in set(own) and t in full}
    restored = restore_text(reply, tag_map) if tag_map else reply
    unmatched = sorted(found - set(tag_map))
    steps.append({"step": "output_restore", "ok": not unmatched, "ms": _ms(s), "restored": _count_restored([reply],
                                                                                                          tag_map)})
    residual = None
    if verify and anonymized.strip():
        s = time.perf_counter()
        chk = _anonymize([anonymized], ctx, "generic", use_s2, dry_run=True, positions=True)[0]
        residual = len(chk.get("extracted_data") or [])
        steps.append({"step": "residual_check", "ok": residual == 0, "ms": _ms(s), "entities": residual})
    out = {"status": "success", "anonymized_text": anonymized, "external_reply": reply, "reply_simulated": simulated,
           "restored_text": restored, "identical_to_input": restored == text if simulated else None,
           "roundtrip_ok": not unmatched and (residual in (None, 0)), "unmatched_placeholders": unmatched,
           "residual_entities": residual, "placeholders": own, "replacements": len(entities),
           "categories": dict(Counter(category_of(e) for e in entities)), "steps": steps}
    if own:
        out["restore_scope"] = SCOPES.create(ctx.principal, own)
    ctx.backend.session_log(entities)
    out["elapsed_ms"] = _ms(t0)
    return _clean(out)


def endpoints(base):
    base = (base or "http://127.0.0.1:8181").rstrip("/")
    return {"mcp": {"streamable_http": base + "/mcp", "sse": base + "/mcp/sse", "sse_messages": base + "/mcp/messages"},
            "utcp": {"manual": base + "/utcp", "well_known": base + "/.well-known/utcp.json",
                     "api": base + "/api/v1/utcp"},
            "openapi": base + "/openapi.json", "rest_base": base + "/api/v1"}


def stdio_command():
    """Comando per il trasporto stdio (Claude Desktop, Claude Code, Antigravity, Cursor...): lo stesso interprete e lo
    stesso server.py di questo Germano, con la stessa cartella dati. Si collega al Germano gia' aperto oppure, se
    non c'e', lavora nel proprio processo (vedi germano/mcp_server.py)."""
    exe = sys.executable or "python"
    if os.path.basename(exe).lower() == "pythonw.exe":
        cand = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(cand):
            exe = cand
    env = {k: os.environ[k] for k in ("GERMANO_DATA_DIR", "GERMANO_TECH_DIR", "GERMANO_CACHE_DIR")
           if os.environ.get(k)}
    return {"command": exe, "args": ["-B", os.path.join(common.BASE_DIR, "server.py"), "--mcp-stdio"], "env": env}


def h_status(args, ctx):
    info = ctx.backend.status_info()
    out = {"status": "success", "service": SERVICE, "name": TITLE, "version": version()}
    out.update(info)
    out["integrations"] = {"endpoints": endpoints(ctx.base_url),
                           "mcp_protocol_versions": list(_protocol_versions()),
                           "utcp_version": _utcp_version(), "tools": [t["name"] for t in TOOLS],
                           "transport": ctx.transport, "caller": "local" if ctx.local else "network",
                           "calls": STATS.snapshot(), "restore_scopes": SCOPES.count()}
    return out


def _protocol_versions():
    from .mcp_server import PROTOCOL_VERSIONS
    return PROTOCOL_VERSIONS


def _utcp_version():
    from .utcp import UTCP_VERSION
    return UTCP_VERSION


# ------------------------------------------------------------------------------------------------ schemi JSON
def _str(desc, **kw):
    return dict({"type": "string", "description": desc}, **kw)


def _bool(desc, default):
    return {"type": "boolean", "description": desc, "default": default}


_MASKING = {"type": "string", "enum": list(MASKINGS), "default": "numbered",
            "description": "numbered: reversible placeholders such as [PERSONA_1], stored in Germano's Vault "
                           "(default); generic: [PERSONA], irreversible; blackout: ████, irreversible."}
_USE_S2 = _bool("System 2 decides System 1's doubtful cases in context with a local language model (fewer false "
                "positives). false = System 1 only: every doubtful case stays masked (more conservative, faster).", True)
_TEXT = _str("Text to process (up to 400,000 characters). Send either text or texts.", maxLength=TEXT_MAX_CHARS)
_TEXTS = {"type": "array", "items": {"type": "string"}, "maxItems": BATCH_MAX_TEXTS,
          "description": "Batch of texts processed together (same placeholders for the same data). Send either text "
                         "or texts."}
_FILE_IN = {
    "file_path": _str("Absolute path of a file on THIS computer (Documents, Desktop, Downloads, Germano work folders or "
                      "folders allowed by the administrator). Not accepted from the network."),
    "content_base64": _str("File content in base64 (up to 64 MB), alternative to file_path. Requires filename."),
    "filename": _str("File name with extension (e.g. contract.docx): required with content_base64."),
    "output_path": _str("Absolute path (file or existing folder) where to save the result on THIS computer. Without "
                        "it the result is returned in content_base64."),
    "overwrite": _bool("Overwrite output_path if it already exists.", False),
    "return_content": _bool("Also return the result in base64 (default: only when output_path is missing).", False),
}
_RESTORE_IN = {
    "restore_scope": _str("Restore scope returned by germano_anonymize_* (restores only the placeholders of that "
                          "anonymization). Required from the network unless mapping is sent."),
    "mapping": {"type": "object", "additionalProperties": {"type": "string"},
                "description": "Placeholder → original value map kept by the caller (e.g. from return_mapping): used "
                               "instead of the Vault."},
}
_CATEGORIES = {"type": "object", "additionalProperties": {"type": "integer"},
               "description": "Number of masked items per category (PERSONA, EMAIL, COD.FISCALE/P.IVA...)."}
_S2_OUT = {"type": "object", "properties": {
    "enabled": {"type": "boolean"}, "decisions": {"type": "integer"}, "confirmed": {"type": "integer"},
    "released": {"type": "integer"}, "uncertain": {"type": "integer"}},
    "description": "System 2 decisions on doubtful cases (counts only)."}
_FILE_OUT = {"type": "object", "properties": {
    "filename": {"type": "string"}, "bytes": {"type": "integer"}, "output_path": {"type": "string"},
    "content_base64": {"type": "string"}}, "required": ["filename", "bytes"]}
_FILE_INFO = {"type": "object", "properties": {
    "filename": {"type": "string"}, "bytes": {"type": "integer"}, "file_path": {"type": "string"}},
    "required": ["filename", "bytes"]}
_ENTITY = {"type": "object", "properties": {
    "unit": {"type": "integer", "description": "Index of the text (0 for text)."},
    "path": {"type": "string", "description": "JSONPath of the string in the payload (leak check)."},
    "start": {"type": "integer"}, "end": {"type": "integer"}, "length": {"type": "integer"},
    "category": {"type": "string"}, "entity": {"type": "string"}, "score": {"type": "number"},
    "level": {"type": "string", "enum": ["system1", "system2", "system1_doubt"]},
    "text": {"type": "string", "description": "Detected value (only with include_values)."}},
    "required": ["start", "end", "category", "level"]}
_DECISION = {"type": "object", "properties": {
    "unit": {"type": "integer"}, "start": {"type": "integer"}, "end": {"type": "integer"},
    "decision": {"type": "string"}, "entity": {"type": "string"}, "p_personal": {"type": "number"},
    "text": {"type": "string"}}, "required": ["start", "end", "decision"]}
_PLACEHOLDERS = {"type": "array", "items": {"type": "string"},
                 "description": "Distinct numbered placeholders created or reused (no personal data)."}


def _obj(props, required=None):
    d = {"type": "object", "properties": props}
    if required:
        d["required"] = list(required)
    return d


OUT_ANON_TEXT = _obj({
    "status": {"type": "string", "enum": ["success"]},
    "anonymized_text": {"type": "string"}, "anonymized_texts": {"type": "array", "items": {"type": "string"}},
    "replacements": {"type": "integer"}, "categories": _CATEGORIES, "placeholders": _PLACEHOLDERS,
    "masking": {"type": "string", "enum": list(MASKINGS)}, "reversible": {"type": "boolean"},
    "restore_scope": {"type": "string"}, "mapping": {"type": "object", "additionalProperties": {"type": "string"}},
    "system2": _S2_OUT, "elapsed_ms": {"type": "integer"}},
    ["status", "replacements", "categories", "placeholders", "masking", "reversible", "elapsed_ms"])
OUT_ANON_FILE = _obj({
    "status": {"type": "string", "enum": ["success"]}, "input": _FILE_INFO, "output": _FILE_OUT,
    "text_preview": {"type": "string", "description": "Beginning of the ANONYMIZED text (safe to show)."},
    "replacements": {"type": "integer"}, "categories": _CATEGORIES, "placeholders": _PLACEHOLDERS,
    "masking": {"type": "string", "enum": list(MASKINGS)}, "reversible": {"type": "boolean"},
    "restore_scope": {"type": "string"}, "mapping": {"type": "object", "additionalProperties": {"type": "string"}},
    "notes": {"type": "array", "items": {"type": "string"}}, "system2": _S2_OUT, "elapsed_ms": {"type": "integer"}},
    ["status", "input", "output", "replacements", "categories", "placeholders", "masking", "reversible", "elapsed_ms"])
OUT_INSPECT = _obj({
    "status": {"type": "string", "enum": ["success"]}, "read_only": {"type": "boolean"},
    "entity_count": {"type": "integer"}, "categories": _CATEGORIES,
    "levels": {"type": "object", "additionalProperties": {"type": "integer"}},
    "entities": {"type": "array", "items": _ENTITY}, "truncated": {"type": "boolean"},
    "system2_decisions": {"type": "array", "items": _DECISION}, "texts": {"type": "integer"},
    "system2": _S2_OUT, "elapsed_ms": {"type": "integer"}},
    ["status", "read_only", "entity_count", "categories", "entities", "elapsed_ms"])
OUT_LEAK = _obj({
    "status": {"type": "string", "enum": ["success"]}, "safe": {"type": "boolean"},
    "verdict": {"type": "string", "enum": ["safe", "leak"]}, "findings_count": {"type": "integer"},
    "categories": _CATEGORIES, "findings": {"type": "array", "items": _ENTITY}, "truncated": {"type": "boolean"},
    "strings_checked": {"type": "integer"}, "chars_checked": {"type": "integer"},
    "placeholders_present": {"type": "integer", "description": "Distinct [TIPO_N] placeholders already present."},
    "system2": _S2_OUT, "elapsed_ms": {"type": "integer"}},
    ["status", "safe", "verdict", "findings_count", "findings", "elapsed_ms"])
OUT_DEANON_TEXT = _obj({
    "status": {"type": "string", "enum": ["success"]},
    "restored_text": {"type": "string", "description": "Text with the original data (PERSONAL DATA)."},
    "restored_texts": {"type": "array", "items": {"type": "string"}},
    "output_path": {"type": "string"}, "restored_count": {"type": "integer"},
    "restored_placeholders": {"type": "integer"},
    "unmatched_placeholders": {"type": "array", "items": {"type": "string"}},
    "source": {"type": "string", "enum": ["vault", "scope", "mapping"]},
    "contains_personal_data": {"type": "boolean"}, "elapsed_ms": {"type": "integer"}},
    ["status", "restored_count", "restored_placeholders", "unmatched_placeholders", "source", "elapsed_ms"])
OUT_DEANON_FILE = _obj({
    "status": {"type": "string", "enum": ["success"]}, "input": _FILE_INFO, "output": _FILE_OUT,
    "restored_count": {"type": "integer"}, "restored_placeholders": {"type": "integer"},
    "unmatched_placeholders": {"type": "array", "items": {"type": "string"}},
    "source": {"type": "string", "enum": ["vault", "scope", "mapping"]},
    "contains_personal_data": {"type": "boolean"}, "text_preview": {"type": "string"},
    "elapsed_ms": {"type": "integer"}},
    ["status", "input", "output", "restored_count", "restored_placeholders", "unmatched_placeholders", "source",
     "elapsed_ms"])
OUT_ROUNDTRIP = _obj({
    "status": {"type": "string", "enum": ["success"]}, "anonymized_text": {"type": "string"},
    "external_reply": {"type": "string"}, "reply_simulated": {"type": "boolean"},
    "restored_text": {"type": "string"}, "identical_to_input": {"type": "boolean"},
    "roundtrip_ok": {"type": "boolean"}, "unmatched_placeholders": {"type": "array", "items": {"type": "string"}},
    "residual_entities": {"type": "integer"}, "placeholders": _PLACEHOLDERS, "replacements": {"type": "integer"},
    "categories": _CATEGORIES, "restore_scope": {"type": "string"},
    "steps": {"type": "array", "items": {"type": "object", "properties": {
        "step": {"type": "string"}, "ok": {"type": "boolean"}, "ms": {"type": "integer"}}, "required": ["step", "ok"]}},
    "elapsed_ms": {"type": "integer"}},
    ["status", "anonymized_text", "restored_text", "roundtrip_ok", "steps", "elapsed_ms"])
OUT_STATUS = _obj({
    "status": {"type": "string", "enum": ["success"]}, "service": {"type": "string"}, "name": {"type": "string"},
    "version": {"type": "string"}, "mode": {"type": "string"}, "profile": {"type": "string"},
    "engine": {"type": "object", "properties": {
        "state": {"type": "string"}, "ready": {"type": "boolean"}, "running": {"type": "boolean"},
        "autostart": {"type": "boolean"}, "device": {"type": "string"},
        "system1": {"type": "object"}, "system2": {"type": "object"}}, "required": ["state", "ready"]},
    "vault": {"type": "object", "properties": {
        "entries": {"type": "integer"}, "by_type": {"type": "object", "additionalProperties": {"type": "integer"}},
        "backend": {"type": "string"}}, "required": ["entries"]},
    "integrations": {"type": "object"}},
    ["status", "service", "version", "engine", "vault", "integrations"])

# ------------------------------------------------------------------------------------------------ registro canonico
_RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
_RW = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}

TOOLS = [
    {"name": "germano_anonymize_text", "title": "Anonymize text (input)", "route": "anonymize-text", "method": "POST",
     "tags": ["input", "anonymize", "privacy"], "annotations": _RW, "average_response_size": 600,
     "handler": h_anonymize_text,
     "description": "INPUT step of a workflow: anonymize text with Germano AI before sending it to any external system "
                    "or AI. Personal data are replaced with placeholders such as [PERSONA_1] or [EMAIL_1] (System 1 "
                    "models and validated patterns, System 2 for doubtful cases), all locally. Returns the anonymized "
                    "text, counts per category, the placeholders and a restore_scope for the output step. If the "
                    "engine is not ready the call is blocked: the original text is never returned as safe.",
     "input": _obj({"text": _TEXT, "texts": _TEXTS, "masking": _MASKING, "use_system2": _USE_S2,
                    "return_mapping": _bool("Also return the placeholder → original value map of THIS request "
                                            "(contains personal data: keep it local).", False)}),
     "output": OUT_ANON_TEXT},
    {"name": "germano_anonymize_file", "title": "Anonymize file (input)", "route": "anonymize-file", "method": "POST",
     "tags": ["input", "anonymize", "privacy", "file"], "annotations": _RW, "average_response_size": 2000,
     "handler": h_anonymize_file,
     "description": "INPUT step for documents: anonymize a file keeping its format (PDF, DOCX, XLSX, PPTX, ODT, ODS, "
                    "ODP, RTF, EML, TXT, CSV, JSON, HTML, XML, images with OCR, faces and signatures, audio with "
                    "offline transcription, ZIP/7Z/TAR archives). Pass file_path (this computer only) or "
                    "content_base64 + filename; save to output_path or receive content_base64. Returns counts, "
                    "placeholders, a restore_scope and a preview of the ANONYMIZED text.",
     "input": _obj(dict(_FILE_IN, masking=_MASKING, use_system2=_USE_S2,
                        preview_chars={"type": "integer", "minimum": 0, "maximum": PREVIEW_MAX,
                                       "default": PREVIEW_DEFAULT,
                                       "description": "Characters of the anonymized text to return as preview "
                                                      "(0 = none)."},
                        return_mapping=_bool("Also return the placeholder → original value map of THIS file "
                                             "(personal data).", False))),
     "output": OUT_ANON_FILE},
    {"name": "germano_inspect_entities", "title": "Inspect personal data (read-only)", "route": "inspect-entities",
     "method": "POST", "tags": ["input", "inspect", "audit", "privacy"], "annotations": _RO,
     "average_response_size": 1500, "handler": h_inspect_entities,
     "description": "Read-only audit: detect and classify the personal data in a text (position, category, score, "
                    "System 1 / System 2 level and System 2 decisions) WITHOUT anonymizing and without writing "
                    "anything to the Vault. Useful for routing decisions in workflows. include_values=false omits the "
                    "detected values.",
     "input": _obj({"text": _TEXT, "texts": _TEXTS, "use_system2": _USE_S2,
                    "include_values": _bool("Include the detected values in the result.", True)}),
     "output": OUT_INSPECT},
    {"name": "germano_leak_check", "title": "Leak check before sending (read-only)", "route": "leak-check",
     "method": "POST", "tags": ["input", "audit", "guard", "privacy"], "annotations": _RO,
     "average_response_size": 800, "handler": h_leak_check,
     "description": "Guard for outgoing data: check whether a text or ANY structured JSON payload (e.g. tool-call "
                    "arguments or an HTTP body) still contains personal data that is not anonymized. Returns "
                    "safe=true only when nothing is found; findings carry the JSONPath, category and position. Values "
                    "are omitted unless include_values=true. Read-only: nothing is written to the Vault.",
     "input": _obj({"text": _str("Text to check.", maxLength=TEXT_MAX_CHARS),
                    "payload": {"description": "Any JSON value (object, array, string...) to check: all strings, "
                                               "long numbers and free-text keys are analyzed."},
                    "use_system2": _USE_S2,
                    "include_values": _bool("Include the detected values in the findings.", False)}),
     "output": OUT_LEAK},
    {"name": "germano_deanonymize_text", "title": "Restore original data in text (output)", "route": "deanonymize-text",
     "method": "POST", "tags": ["output", "deanonymize", "vault"], "annotations": _RW, "average_response_size": 600,
     "handler": h_deanonymize_text,
     "description": "OUTPUT step of a workflow: restore the original data in a text produced by an external system or "
                    "AI that contains Germano placeholders ([PERSONA_1]...). Only the placeholders present in the text "
                    "are restored; the Vault is never listed. The restored text CONTAINS PERSONAL DATA: an AI "
                    "assistant running in the cloud should prefer output_path (written on this computer, not returned) "
                    "or germano_deanonymize_file.",
     "input": _obj(dict({"text": _str("Text with placeholders (up to 400,000 characters). Send either text or texts.",
                                      maxLength=TEXT_MAX_CHARS), "texts": _TEXTS},
                        **_RESTORE_IN,
                        output_path=_str("Absolute path on THIS computer where to write the restored text (UTF-8) "
                                         "instead of returning it."),
                        overwrite=_bool("Overwrite output_path if it already exists.", False),
                        return_text=_bool("With output_path, also return the restored text.", False))),
     "output": OUT_DEANON_TEXT},
    {"name": "germano_deanonymize_file", "title": "Restore original data in file (output)", "route": "deanonymize-file",
     "method": "POST", "tags": ["output", "deanonymize", "vault", "file"], "annotations": _RW,
     "average_response_size": 1500, "handler": h_deanonymize_file,
     "description": "OUTPUT step for documents: restore the original data in a file produced by an external system or "
                    "AI (TXT, MD, HTML, DOCX, XLSX, PPTX, ODT, PDF text, CSV, JSON, EML...) that contains Germano "
                    "placeholders. Only placeholders present in the file are restored. Write the result to output_path "
                    "on this computer (recommended: the personal data never reach the caller) or receive "
                    "content_base64.",
     "input": _obj(dict(_FILE_IN, **_RESTORE_IN,
                        preview_chars={"type": "integer", "minimum": 0, "maximum": PREVIEW_MAX, "default": 0,
                                       "description": "Characters of the RESTORED text to return (personal data; "
                                                      "default 0)."})),
     "output": OUT_DEANON_FILE},
    {"name": "germano_workflow_roundtrip", "title": "Verify an input → output cycle", "route": "workflow-roundtrip",
     "method": "POST", "tags": ["workflow", "audit", "test"], "annotations": _RW, "average_response_size": 1500,
     "handler": h_workflow_roundtrip,
     "description": "Controlled input → output cycle to verify a workflow: anonymize text, use external_reply (or a "
                    "simulated reply that repeats the anonymized text), restore ONLY the placeholders of this cycle "
                    "and check that no personal data remain in the anonymized text. Germano stays the fail-safe "
                    "guard: if the engine is not ready the cycle is blocked.",
     "input": _obj({"text": _str("Input text containing personal data.", maxLength=TEXT_MAX_CHARS),
                    "external_reply": _str("Reply of the external system with placeholders (optional: without it a "
                                           "reply is simulated).", maxLength=TEXT_MAX_CHARS),
                    "use_system2": _USE_S2,
                    "verify_residual": _bool("Re-analyze the anonymized text to confirm that nothing personal "
                                             "remains.", True)}, ["text"]),
     "output": OUT_ROUNDTRIP},
    {"name": "germano_status", "title": "Germano status", "route": "status", "method": "GET",
     "tags": ["status"], "annotations": _RO, "average_response_size": 1200, "handler": h_status,
     "description": "Status of Germano AI: engine (System 1 and System 2 readiness), operating mode, protection "
                    "profile, aggregate Vault statistics (counts only, never values), MCP / UTCP / OpenAPI endpoints "
                    "and invocation counters.",
     "input": _obj({}), "output": OUT_STATUS},
]
BY_NAME = {t["name"]: t for t in TOOLS}
BY_ROUTE = {t["route"]: t for t in TOOLS}


def call_tool(name, args, ctx):
    """Esegue uno strumento del registro. Restituisce il risultato (dict) oppure solleva ToolError. Registra sempre
    l'esito nelle statistiche e una riga nel registro (mai testi o dati)."""
    spec = BY_NAME.get(name)
    if spec is None:
        raise ToolError("unknown_tool", f"Strumento sconosciuto: {str(name)[:60]}", f"Unknown tool: {str(name)[:60]}",
                        status=404)
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise _invalid(ctx, "Gli argomenti devono essere un oggetto JSON.", "The arguments must be a JSON object.")
    t0 = time.perf_counter()
    outcome = "error"
    try:
        result = spec["handler"](args, ctx)
        outcome = "success"
        return result
    except ToolError as e:
        outcome = e.kind
        raise
    except Exception as e:                       # errore imprevisto: mai i dati, solo il tipo
        common.log(f"Integrazioni: errore imprevisto in {name}: {type(e).__name__}: {e}")
        raise ToolError("internal_error", f"Errore interno di Germano ({type(e).__name__}): nessun dato e' stato "
                                          "inviato.",
                        f"Germano internal error ({type(e).__name__}): no data was sent.", status=500) from None
    finally:
        ms = (time.perf_counter() - t0) * 1000
        STATS.record(name, ctx.transport, outcome, ms)
        who = "locale" if ctx.local else ctx.principal
        common.log(f"Integrazioni: {name} via {ctx.transport} ({who}): {outcome}, {int(ms)} ms")


# ------------------------------------------------------------------------------------------------ risorse e prompt (MCP)
RESOURCES = [
    {"uri": "germano://status", "name": "status", "title": "Germano status",
     "description": "Engine, Vault counts (no values), endpoints and invocation counters.", "mimeType": "application/json"},
    {"uri": "germano://capabilities", "name": "capabilities", "title": "Germano capabilities",
     "description": "Tools by workflow phase, transports, protocol versions, limits and the file path policy.",
     "mimeType": "application/json"},
    {"uri": "germano://utcp-manual", "name": "utcp-manual", "title": "UTCP manual",
     "description": "The UTCP 1.0 manual of Germano's tools (same registry as MCP).", "mimeType": "application/json"},
    {"uri": "germano://workflow-guide", "name": "workflow-guide", "title": "Workflow guide (input → output)",
     "description": "How to put Germano in the input and output steps of a workflow (IT/EN).",
     "mimeType": "text/markdown"},
]


def capabilities(ctx):
    phases = {}
    for t in TOOLS:
        phase = "input" if "input" in t["tags"] else "output" if "output" in t["tags"] else \
            "workflow" if "workflow" in t["tags"] else "status"
        phases.setdefault(phase, []).append(t["name"])
    from .mcp_server import PROTOCOL_VERSIONS
    from .utcp import UTCP_VERSION
    return {"service": SERVICE, "version": version(), "tools_by_phase": phases,
            "transports": {"mcp": ["streamable-http", "sse (legacy)", "stdio"], "utcp": ["http"],
                           "openapi": "3.1.0"},
            "mcp_protocol_versions": list(PROTOCOL_VERSIONS), "utcp_version": UTCP_VERSION,
            "endpoints": endpoints(ctx.base_url), "stdio": stdio_command() if ctx.local else None,
            "limits": {"text_chars": TEXT_MAX_CHARS, "batch_texts": BATCH_MAX_TEXTS, "batch_chars": BATCH_MAX_CHARS,
                       "inline_file_bytes": INLINE_FILE_MAX, "path_file_bytes": PATH_FILE_MAX,
                       "restore_text_placeholders": MAX_RESTORE_TEXT_TAGS},
            "security": {"engine_not_ready": "blocked (fail-safe)",
                         "restore": "only placeholders present in the input; from the network only restore_scope or "
                                    "mapping; the Vault is never listed",
                         "network": "Authorization: Bearer <integration token> or user session (Server mode)",
                         "paths": path_policy(ctx.lang) if ctx.local else "local only"}}


WORKFLOW_GUIDE = """# Germano AI {v} - flussi di lavoro in ingresso e in uscita / input and output workflows

## Italiano
1. **Ingresso (prima di inviare)**: `germano_anonymize_text` o `germano_anonymize_file` sostituiscono i dati personali
   con etichette come `[PERSONA_1]`; conserva `restore_scope`. Per un controllo senza modificare nulla:
   `germano_inspect_entities`; per bloccare un invio: `germano_leak_check` (safe=true solo se non resta nulla).
2. **Sistema esterno**: invia SOLO `anonymized_text` (o il file anonimizzato) all'AI, al CRM, a n8n, a un agente.
3. **Uscita (dopo la risposta)**: `germano_deanonymize_text` / `germano_deanonymize_file` ripristinano i dati SOLO
   per le etichette presenti nella risposta. Dalla rete serve `restore_scope` (o `mapping`).
4. **Verifica**: `germano_workflow_roundtrip` esegue il ciclo completo e controlla che nulla resti in chiaro.

Regole: se il motore non e' pronto la richiesta e' bloccata (nessun dato esce); il testo ripristinato contiene dati
personali: un assistente AI nel cloud dovrebbe scriverlo su file (`output_path`) invece di riceverlo.

## English
1. **Input (before sending)**: `germano_anonymize_text` or `germano_anonymize_file` replace personal data with
   placeholders such as `[PERSONA_1]`; keep `restore_scope`. Read-only checks: `germano_inspect_entities`; to stop a
   send: `germano_leak_check` (safe=true only when nothing remains).
2. **External system**: send ONLY `anonymized_text` (or the anonymized file) to the AI, CRM, n8n flow or agent.
3. **Output (after the reply)**: `germano_deanonymize_text` / `germano_deanonymize_file` restore the data ONLY for the
   placeholders found in the reply. From the network `restore_scope` (or `mapping`) is required.
4. **Verify**: `germano_workflow_roundtrip` runs the whole cycle and checks that nothing personal remains.

Rules: if the engine is not ready the request is blocked (no data leaves); restored text contains personal data: an AI
assistant running in the cloud should write it to a file (`output_path`) instead of receiving it.

Endpoints: MCP `{base}/mcp` (Streamable HTTP), `{base}/mcp/sse` (legacy SSE), stdio `server.py --mcp-stdio`;
UTCP `{base}/utcp` and `{base}/.well-known/utcp.json`; OpenAPI `{base}/openapi.json`; REST `{base}/api/v1/...`.
"""


def read_resource(uri, ctx):
    """(mimeType, testo) di una risorsa MCP; KeyError se sconosciuta."""
    if uri == "germano://status":
        return "application/json", json.dumps(h_status({}, ctx), ensure_ascii=False, indent=2)
    if uri == "germano://capabilities":
        return "application/json", json.dumps(capabilities(ctx), ensure_ascii=False, indent=2)
    if uri == "germano://utcp-manual":
        from . import utcp
        return "application/json", json.dumps(utcp.manual(ctx.base_url, local=ctx.local), ensure_ascii=False, indent=2)
    if uri == "germano://workflow-guide":
        return "text/markdown", WORKFLOW_GUIDE.format(v=version(), base=ctx.base_url)
    raise KeyError(uri)


PROMPTS = [
    {"name": "sanitize-before-send", "title": "Sanitize before sending (input)",
     "description": "Anonymize content with Germano before it is sent to an external AI or system.",
     "arguments": [{"name": "content", "description": "Text to protect (optional: otherwise the assistant asks for it "
                                                      "or uses a file).", "required": False},
                   {"name": "destination", "description": "Where the data will be sent (e.g. ChatGPT, CRM, n8n).",
                    "required": False},
                   {"name": "language", "description": "it or en (default en).", "required": False}]},
    {"name": "restore-after-reply", "title": "Restore after the reply (output)",
     "description": "Restore the original data in a reply that contains Germano placeholders.",
     "arguments": [{"name": "reply", "description": "Reply with placeholders such as [PERSONA_1].", "required": False},
                   {"name": "output_path", "description": "File where to write the restored result (recommended).",
                    "required": False},
                   {"name": "language", "description": "it or en (default en).", "required": False}]},
    {"name": "workflow-input-output-audit", "title": "Audit a workflow (input and output)",
     "description": "Check an outgoing payload for leaks and audit the personal data of a workflow step.",
     "arguments": [{"name": "payload", "description": "Text or JSON of the step to audit.", "required": False},
                   {"name": "language", "description": "it or en (default en).", "required": False}]},
]
_PROMPT_TEXT = {
    "sanitize-before-send": {
        "en": "Before sending anything to {dest}, protect the personal data with Germano AI.\n"
              "1. Call germano_anonymize_text (or germano_anonymize_file for documents, with output_path).\n"
              "2. Use ONLY the anonymized text or file from now on; keep restore_scope for the reply.\n"
              "3. If Germano answers status \"blocked\", do not send anything and tell the user.\n{content}",
        "it": "Prima di inviare qualsiasi cosa a {dest}, proteggi i dati personali con Germano AI.\n"
              "1. Chiama germano_anonymize_text (o germano_anonymize_file per i documenti, con output_path).\n"
              "2. Da qui in poi usa SOLO il testo o il file anonimizzato; conserva restore_scope per la risposta.\n"
              "3. Se Germano risponde status \"blocked\", non inviare nulla e avvisa l'utente.\n{content}"},
    "restore-after-reply": {
        "en": "The reply contains Germano placeholders such as [PERSONA_1]. Restore the original data:\n"
              "- prefer germano_deanonymize_file or germano_deanonymize_text with output_path {out}, so the personal "
              "data are written on the user's computer and not returned into this conversation;\n"
              "- pass restore_scope from the anonymization step when you have it.\n{reply}",
        "it": "La risposta contiene etichette di Germano come [PERSONA_1]. Ripristina i dati originali:\n"
              "- preferisci germano_deanonymize_file o germano_deanonymize_text con output_path {out}, cosi' i dati "
              "personali vengono scritti sul computer dell'utente e non tornano in questa conversazione;\n"
              "- passa restore_scope del passo di anonimizzazione, se lo hai.\n{reply}"},
    "workflow-input-output-audit": {
        "en": "Audit this workflow step with Germano AI:\n1. germano_leak_check on the outgoing payload (it must be "
              "safe=true before sending).\n2. germano_inspect_entities on the incoming text to list the categories of "
              "personal data.\n3. germano_workflow_roundtrip to verify the input → output cycle.\nReport counts and "
              "categories only, never the values.\n{payload}",
        "it": "Verifica questo passo del flusso di lavoro con Germano AI:\n1. germano_leak_check sul payload in uscita "
              "(deve risultare safe=true prima dell'invio).\n2. germano_inspect_entities sul testo in ingresso per "
              "elencare le categorie di dati personali.\n3. germano_workflow_roundtrip per verificare il ciclo "
              "ingresso → uscita.\nRiporta solo conteggi e categorie, mai i valori.\n{payload}"},
}


def get_prompt(name, arguments):
    """{description, messages} di un prompt MCP; KeyError se sconosciuto."""
    spec = next((p for p in PROMPTS if p["name"] == name), None)
    if spec is None:
        raise KeyError(name)
    a = {k: str(v) for k, v in (arguments or {}).items() if isinstance(v, (str, int, float)) and str(v).strip()}
    lang = "it" if a.get("language", "en").lower().startswith("it") else "en"
    tpl = _PROMPT_TEXT[name][lang]
    text = tpl.format(
        dest=a.get("destination") or ("il sistema esterno" if lang == "it" else "the external system"),
        content=("\n---\n" + a["content"]) if a.get("content") else "",
        out=f"({a['output_path']})" if a.get("output_path") else "",
        reply=("\n---\n" + a["reply"]) if a.get("reply") else "",
        payload=("\n---\n" + a["payload"]) if a.get("payload") else "")
    return {"description": spec["description"],
            "messages": [{"role": "user", "content": {"type": "text", "text": text.rstrip()}}]}
