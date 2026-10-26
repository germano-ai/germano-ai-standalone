"""Rilevamento delle AI e delle CLI installate su questo computer (Windows, macOS e Linux).

Solo file system e porte locali: nessun processo avviato e nessun accesso a Internet, cosi' il risultato e'
deterministico e arriva in poche decine di millisecondi. Il PATH del processo da solo non basta:
- Claude Code installato da Claude Desktop e Antigravity stanno in cartelle di AppData che non sono nel PATH;
- una CLI installata DOPO l'avvio di Germano aggiorna il PATH salvato (registro di Windows), non quello del processo;
- npm, pipx/uv, winget, scoop, bun e gli installatori ufficiali usano cartelle proprie.
Ogni voce indica il produttore e, se esiste, il servizio API equivalente (germano/providers.py) con cui la stessa AI si
usa attraverso Germano dagli altri dispositivi.
"""
import glob
import os
import re
import socket
import threading
import time

IS_WIN = os.name == "nt"
# Estensioni avviabili su Windows, in ordine di preferenza quando nella stessa cartella ci sono piu' varianti
# (es. claude.cmd e claude.ps1 creati da npm). Gli script .ps1 vengono rilevati ma non avviati.
_RUNNABLE = (".exe", ".cmd", ".bat", ".com")
_DETECT_ONLY = (".ps1",)
_EXT_RANK = {e: i for i, e in enumerate(_RUNNABLE + _DETECT_ONLY)}

# Cartelle da indicizzare oltre al PATH (anche con caratteri jolly). Si usano solo quelle che esistono.
_EXTRA_DIRS_WIN = (
    r"%APPDATA%\npm",                                   # pacchetti globali npm: codex, gemini, qwen, copilot
    r"%USERPROFILE%\.local\bin",                        # uv/pipx (kimi, vibe), installatori nativi (claude, pplx)
    r"%LOCALAPPDATA%\Microsoft\WinGet\Links",           # collegamenti di winget
    r"%LOCALAPPDATA%\Microsoft\WindowsApps",            # alias delle app dello Store
    r"%LOCALAPPDATA%\pnpm",
    r"%USERPROFILE%\.bun\bin",
    r"%USERPROFILE%\scoop\shims",
    r"%USERPROFILE%\.cargo\bin",
    r"%USERPROFILE%\go\bin",
    r"%USERPROFILE%\.deno\bin",
    r"%USERPROFILE%\.grok\bin",                         # Grok Build (installatore ufficiale)
    r"%USERPROFILE%\.muse\bin",                         # Muse Code di Meta (installatore ufficiale)
    r"%USERPROFILE%\.opencode\bin",
    r"%LOCALAPPDATA%\Programs\Python\Python3*\Scripts",
    r"%APPDATA%\Python\Python3*\Scripts",
    r"%LOCALAPPDATA%\Programs\Ollama",
    r"%PROGRAMDATA%\chocolatey\bin",
)
_EXTRA_DIRS_POSIX = (
    "~/.local/bin", "~/.npm-global/bin", "~/.bun/bin", "~/.cargo/bin", "~/go/bin", "~/.deno/bin",
    "~/.grok/bin", "~/.muse/bin", "~/.opencode/bin", "/usr/local/bin", "/opt/homebrew/bin", "/usr/bin",
)
_APP_DIRS_MAC = ("/Applications", "~/Applications")

# kind: "cli" = riga di comando, "app" = applicazione desktop, "service" = modelli locali in ascolto su una porta.
# bins: nomi del comando; globs: percorsi di installazione (si sceglie la versione piu' alta); version_at: indice della
# parte del percorso che contiene la versione; mac: nome del pacchetto .app su macOS; service: servizio API equivalente.
CATALOG = (
    # --- Anthropic
    {"id": "claude-code", "name": "Claude Code", "vendor": "Anthropic", "kind": "cli", "bins": ("claude",),
     "globs": (r"%APPDATA%\Claude\claude-code\*\*\claude.exe",), "version_at": -3, "service": "anthropic"},
    {"id": "claude-desktop", "name": "Claude Desktop", "vendor": "Anthropic", "kind": "app", "bins": (),
     "globs": (r"%LOCALAPPDATA%\AnthropicClaude\app-*\claude.exe",), "version_at": -2, "version_strip": "app-",
     "mac": "Claude.app", "service": "anthropic"},
    # --- OpenAI
    {"id": "codex", "name": "OpenAI Codex CLI", "vendor": "OpenAI", "kind": "cli", "bins": ("codex",),
     "service": "openai"},
    {"id": "chatgpt", "name": "ChatGPT (app)", "vendor": "OpenAI", "kind": "app", "bins": ("chatgpt",),
     "mac": "ChatGPT.app", "service": "openai"},
    # --- Google
    {"id": "antigravity", "name": "Antigravity", "vendor": "Google", "kind": "app", "bins": ("agy", "antigravity"),
     "globs": (r"%LOCALAPPDATA%\Programs\Antigravity\Antigravity.exe",), "mac": "Antigravity.app", "service": "gemini"},
    {"id": "gemini-cli", "name": "Gemini CLI", "vendor": "Google", "kind": "cli", "bins": ("gemini",),
     "service": "gemini"},
    {"id": "jules", "name": "Jules CLI", "vendor": "Google", "kind": "cli", "bins": ("jules",), "service": "gemini"},
    # --- Meta
    {"id": "muse-code", "name": "Muse Code (Muse Wonder, Muse Spark)", "vendor": "Meta", "kind": "cli",
     "bins": ("muse", "muse-code"), "globs": (r"%USERPROFILE%\.muse\bin\muse.exe",), "service": "meta"},
    {"id": "llama-cpp", "name": "llama.cpp (modelli Llama locali)", "vendor": "Meta / ggml", "kind": "service",
     "bins": ("llama-server", "llama-cli")},
    # --- Moonshot, Alibaba, DeepSeek, Mistral, xAI, Perplexity
    {"id": "kimi", "name": "Kimi Code CLI", "vendor": "Moonshot AI", "kind": "cli",
     "bins": ("kimi", "kimi-cli", "kimi-code", "moonshot"), "service": "moonshot"},
    {"id": "qwen", "name": "Qwen Code", "vendor": "Alibaba", "kind": "cli", "bins": ("qwen", "qwen-code", "qwen-agent",
                                                                                   "qwen-cli"), "service": "qwen"},
    {"id": "deepseek", "name": "DeepSeek (Deep Code, Reasonix)", "vendor": "DeepSeek", "kind": "cli",
     "bins": ("deepseek", "deepseek-cli", "deepcode", "reasonix"), "service": "deepseek"},
    {"id": "mistral-vibe", "name": "Mistral Vibe", "vendor": "Mistral AI", "kind": "cli", "bins": ("vibe", "mistral-vibe"),
     "service": "mistral"},
    {"id": "grok-build", "name": "Grok Build", "vendor": "xAI", "kind": "cli", "bins": ("grok",),
     "globs": (r"%USERPROFILE%\.grok\bin\grok.exe",), "service": "xai"},
    {"id": "perplexity", "name": "Perplexity (pplx)", "vendor": "Perplexity", "kind": "cli", "bins": ("pplx", "perplexity"),
     "mac": "Perplexity.app", "service": "perplexity"},
    # --- GitHub, editor e agenti
    {"id": "copilot-cli", "name": "GitHub Copilot CLI", "vendor": "GitHub", "kind": "cli", "bins": ("copilot",)},
    {"id": "cursor", "name": "Cursor", "vendor": "Anysphere", "kind": "app", "bins": ("cursor",),
     "globs": (r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe",), "mac": "Cursor.app"},
    {"id": "cursor-agent", "name": "Cursor CLI", "vendor": "Anysphere", "kind": "cli", "bins": ("cursor-agent",)},
    {"id": "windsurf", "name": "Windsurf", "vendor": "Cognition", "kind": "app", "bins": ("windsurf",),
     "globs": (r"%LOCALAPPDATA%\Programs\Windsurf\Windsurf.exe",), "mac": "Windsurf.app"},
    {"id": "kiro", "name": "Kiro", "vendor": "Amazon", "kind": "app", "bins": ("kiro",),
     "globs": (r"%LOCALAPPDATA%\Programs\Kiro\Kiro.exe",), "mac": "Kiro.app"},
    {"id": "kiro-cli", "name": "Kiro CLI (ex Amazon Q)", "vendor": "Amazon", "kind": "cli", "bins": ("kiro-cli",)},
    {"id": "trae", "name": "Trae", "vendor": "ByteDance", "kind": "app", "bins": ("trae",),
     "globs": (r"%LOCALAPPDATA%\Programs\Trae\Trae.exe",), "mac": "Trae.app"},
    {"id": "zed", "name": "Zed", "vendor": "Zed Industries", "kind": "app", "bins": (),
     "globs": (r"%LOCALAPPDATA%\Programs\Zed\Zed.exe",), "mac": "Zed.app"},
    {"id": "opencode", "name": "OpenCode", "vendor": "open source", "kind": "cli", "bins": ("opencode",),
     "globs": (r"%USERPROFILE%\.opencode\bin\opencode.exe",)},
    {"id": "aider", "name": "Aider", "vendor": "open source", "kind": "cli", "bins": ("aider",), "service": "openai"},
    {"id": "goose", "name": "Goose", "vendor": "Block", "kind": "cli", "bins": ("goose",)},
    {"id": "cline", "name": "Cline CLI", "vendor": "Cline", "kind": "cli", "bins": ("cline",)},
    {"id": "kilo", "name": "Kilo Code CLI", "vendor": "Kilo Code", "kind": "cli", "bins": ("kilo", "kilocode")},
    {"id": "amp", "name": "Amp", "vendor": "Sourcegraph", "kind": "cli", "bins": ("amp",)},
    {"id": "droid", "name": "Droid", "vendor": "Factory", "kind": "cli", "bins": ("droid",)},
    {"id": "crush", "name": "Crush", "vendor": "Charm", "kind": "cli", "bins": ("crush",)},
    # --- modelli locali
    {"id": "ollama", "name": "Ollama", "vendor": "Ollama", "kind": "service", "bins": ("ollama",),
     "globs": (r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",), "mac": "Ollama.app", "port": 11434, "service": "ollama"},
    {"id": "lm-studio", "name": "LM Studio", "vendor": "LM Studio", "kind": "service", "bins": ("lms",),
     "globs": (r"%LOCALAPPDATA%\Programs\LM Studio\LM Studio.exe",), "mac": "LM Studio.app", "port": 1234,
     "service": "lmstudio"},
    {"id": "jan", "name": "Jan", "vendor": "Menlo Research", "kind": "service", "bins": (),
     "globs": (r"%LOCALAPPDATA%\Programs\jan\Jan.exe",), "mac": "Jan.app", "port": 1337},
)


def _expand(path):
    return os.path.expandvars(os.path.expanduser(path))


def _registry_paths():
    """PATH salvato nel registro (utente e sistema): comprende le CLI installate dopo l'avvio di Germano."""
    if not IS_WIN:
        return []
    import winreg
    out = []
    for root, sub in ((winreg.HKEY_CURRENT_USER, "Environment"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
        try:
            with winreg.OpenKey(root, sub) as k:
                value, _type = winreg.QueryValueEx(k, "Path")
        except OSError:
            continue
        out.extend(_expand(p.strip().strip('"')) for p in str(value).split(os.pathsep))
    return out


def _candidate_dirs():
    """PATH del processo (nell'ordine del sistema), PATH salvato nel registro e cartelle note, senza duplicati."""
    out, seen = [], set()
    raw = [d.strip().strip('"') for d in os.environ.get("PATH", "").split(os.pathsep)]
    raw += _registry_paths()
    for pattern in (_EXTRA_DIRS_WIN if IS_WIN else _EXTRA_DIRS_POSIX):
        p = _expand(pattern)
        raw.extend(sorted(glob.glob(p)) if any(c in p for c in "*?[") else [p])
    for d in raw:
        if not d or "%" in d or (not IS_WIN and d.startswith("~")):   # variabile non espansa: cartella inesistente
            continue
        key = os.path.normcase(os.path.abspath(d))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _entry_key(entry):
    """(nome del comando, rango) di un file avviabile, oppure None."""
    if IS_WIN:
        stem, ext = os.path.splitext(entry.name)
        rank = _EXT_RANK.get(ext.lower())
        return (stem.lower(), rank) if rank is not None else None
    try:   # Linux e macOS: file eseguibile, senza estensione obbligatoria (es. claude, kimi, ollama)
        if entry.is_file() and os.access(entry.path, os.X_OK):
            return entry.name.lower(), 0
    except OSError:
        pass
    return None


def _index_dirs(dirs):
    """nome senza estensione (minuscolo) -> percorso: vince la prima cartella, poi l'estensione preferita."""
    best = {}
    for order, d in enumerate(dirs):
        try:
            with os.scandir(d) as it:
                for e in it:
                    found = _entry_key(e)
                    if found is None:
                        continue
                    name, rank = found
                    key = (order, rank)
                    cur = best.get(name)
                    if cur is None or key < cur[0]:
                        best[name] = (key, e.path)
        except OSError:
            continue
    return {k: v[1] for k, v in best.items()}


def version_key(text):
    """'2.1.308' -> (2, 1, 308): confronto numerico, cosi' 2.1.100 viene dopo 2.1.99."""
    return tuple(int(n) for n in re.findall(r"\d+", str(text or "")))


def _path_part(path, index, strip=None):
    try:
        part = os.path.normpath(path).split(os.sep)[index]
    except (IndexError, TypeError):
        return None
    if strip and part.startswith(strip):
        part = part[len(strip):]
    return part or None


def _best_install(spec):
    if IS_WIN:
        for pattern in spec.get("globs", ()):
            hits = [h for h in glob.glob(_expand(pattern)) if os.path.isfile(h)]
            if not hits:
                continue
            if "version_at" in spec:
                at, strip = spec["version_at"], spec.get("version_strip")
                hits.sort(key=lambda h: (version_key(_path_part(h, at, strip)), h))
                best = hits[-1]
                return best, _path_part(best, at, strip)
            return sorted(hits)[-1], None
    elif spec.get("mac"):
        for d in _APP_DIRS_MAC:
            app = os.path.join(_expand(d), spec["mac"])
            if os.path.isdir(app):
                return app, None
    return None, None


def _port_open(port, timeout=0.025):
    # Su Windows una porta locale chiusa non rifiuta subito la connessione (ritenta il SYN): basta un timeout
    # breve, perche' un servizio in ascolto su 127.0.0.1 risponde in meno di un millisecondo.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", int(port))) == 0
    except OSError:
        return False
    finally:
        s.close()


def _start_port_probes(ports):
    """Avvia le sonde in parallelo (mentre si scandisce il disco). Restituisce la funzione che le raccoglie."""
    results = {}
    threads = []
    for p in set(ports):
        th = threading.Thread(target=lambda p=p: results.__setitem__(p, _port_open(p)), daemon=True)
        th.start()
        threads.append(th)

    def collect():
        for th in threads:
            th.join(0.5)
        return results
    return collect


def runnable(path):
    """True se Germano puo' avviare direttamente questo file (non gli script .ps1)."""
    if not path or not os.path.isfile(path):
        return False
    if IS_WIN:
        return os.path.splitext(path)[1].lower() in _RUNNABLE
    return os.access(path, os.X_OK)


def detect(check_ports=True):
    """Elenco del catalogo con, per ciascuna voce, se e' installata, dove e (se nota) la versione."""
    t0 = time.perf_counter()
    collect_ports = _start_port_probes([s["port"] for s in CATALOG if s.get("port")]) if check_ports else dict
    index = _index_dirs(_candidate_dirs())
    found = []
    for spec in CATALOG:
        path = version = via = None
        for b in spec.get("bins", ()):
            if b in index:
                path, via = index[b], "path"
                break
        if path is None:
            path, version = _best_install(spec)
            if path:
                via = "install"
        found.append((spec, path, version, via))
    ports = collect_ports()  # le sonde hanno lavorato durante la scansione del disco
    tools = []
    for spec, path, version, via in found:
        detected = path is not None
        listening = bool(spec.get("port") and ports.get(spec["port"]))
        if not detected and listening:
            detected, via = True, "port"
        tools.append({
            "id": spec["id"], "name": spec["name"], "vendor": spec.get("vendor"), "kind": spec["kind"],
            "detected": detected, "path": path, "version": version, "via": via,
            "listening": listening if spec.get("port") else None, "service": spec.get("service"),
        })
    return {"tools": tools, "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1), "checked_at": time.time()}


def find(tool_id, check_ports=False):
    for t in detect(check_ports=check_ports)["tools"]:
        if t["id"] == tool_id:
            return t
    return None
