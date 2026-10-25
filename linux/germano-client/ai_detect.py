"""Rilevamento delle AI e delle CLI installate su questo computer (Windows).

Solo file system e porte locali: nessun processo avviato e nessun accesso a Internet, cosi' il risultato e'
deterministico e arriva in poche decine di millisecondi. Il PATH da solo non basta: Claude Code installato da
Claude Desktop e Antigravity stanno in cartelle di AppData che non sono nel PATH.
"""
import glob
import os
import re
import socket
import threading
import time

# Estensioni avviabili, in ordine di preferenza quando nella stessa cartella ci sono piu' varianti
# (es. claude.cmd e claude.ps1 creati da npm). Gli script .ps1 vengono rilevati ma non avviati.
_RUNNABLE = (".exe", ".cmd", ".bat", ".com")
_DETECT_ONLY = (".ps1",)
_EXT_RANK = {e: i for i, e in enumerate(_RUNNABLE + _DETECT_ONLY)}

# Cartelle da indicizzare oltre al PATH (anche con caratteri jolly). Si usano solo quelle che esistono.
_EXTRA_DIRS = (
    r"%APPDATA%\npm",                                   # pacchetti globali npm: codex, gemini, claude
    r"%USERPROFILE%\.local\bin",                        # installatore nativo di Claude Code, pipx
    r"%LOCALAPPDATA%\Microsoft\WinGet\Links",           # collegamenti di winget
    r"%LOCALAPPDATA%\Programs\Python\Python3*\Scripts",
    r"%APPDATA%\Python\Python3*\Scripts",
    r"%LOCALAPPDATA%\Programs\Ollama",
)

# kind: "cli" = riga di comando, "app" = applicazione desktop, "service" = servizio locale in ascolto.
# globs: percorsi di installazione (si sceglie la versione piu' alta). version_at: indice della parte del
# percorso che contiene la versione (es. -3 per ...\claude-code\2.1.308\<hash>\claude.exe).
CATALOG = (
    {"id": "claude-code", "name": "Claude Code", "kind": "cli", "bins": ("claude",),
     "globs": (r"%APPDATA%\Claude\claude-code\*\*\claude.exe",), "version_at": -3},
    {"id": "claude-desktop", "name": "Claude Desktop", "kind": "app", "bins": (),
     "globs": (r"%LOCALAPPDATA%\AnthropicClaude\app-*\claude.exe",), "version_at": -2, "version_strip": "app-"},
    {"id": "antigravity", "name": "Antigravity", "kind": "app", "bins": ("agy", "antigravity"),
     "globs": (r"%LOCALAPPDATA%\Programs\Antigravity\Antigravity.exe",)},
    {"id": "gemini-cli", "name": "Gemini CLI", "kind": "cli", "bins": ("gemini",)},
    {"id": "codex", "name": "OpenAI Codex CLI", "kind": "cli", "bins": ("codex",)},
    {"id": "aider", "name": "Aider", "kind": "cli", "bins": ("aider",)},
    {"id": "deepseek", "name": "DeepSeek", "kind": "cli", "bins": ("deepseek", "deepseek-cli")},
    {"id": "qwen", "name": "Qwen", "kind": "cli", "bins": ("qwen", "qwen-agent", "qwen-cli")},
    {"id": "kimi", "name": "Kimi (Moonshot)", "kind": "cli", "bins": ("kimi", "moonshot", "kimi-cli")},
    {"id": "cursor", "name": "Cursor", "kind": "app", "bins": ("cursor",),
     "globs": (r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe",)},
    {"id": "windsurf", "name": "Windsurf", "kind": "app", "bins": ("windsurf",),
     "globs": (r"%LOCALAPPDATA%\Programs\Windsurf\Windsurf.exe",)},
    {"id": "ollama", "name": "Ollama", "kind": "service", "bins": ("ollama",),
     "globs": (r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",), "port": 11434},
    {"id": "lm-studio", "name": "LM Studio", "kind": "service", "bins": ("lms",),
     "globs": (r"%LOCALAPPDATA%\Programs\LM Studio\LM Studio.exe",), "port": 1234},
)


def _expand(path):
    return os.path.expandvars(os.path.expanduser(path))


def _candidate_dirs():
    """PATH (nell'ordine di Windows) seguito dalle cartelle note, senza duplicati."""
    out, seen = [], set()
    raw = [d.strip().strip('"') for d in os.environ.get("PATH", "").split(os.pathsep)]
    for pattern in _EXTRA_DIRS:
        p = _expand(pattern)
        raw.extend(sorted(glob.glob(p)) if any(c in p for c in "*?[") else [p])
    for d in raw:
        if not d or "%" in d:  # variabile non espansa: cartella inesistente
            continue
        key = os.path.normcase(os.path.abspath(d))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _index_dirs(dirs):
    """nome senza estensione (minuscolo) -> percorso: vince la prima cartella, poi l'estensione preferita."""
    best = {}
    for order, d in enumerate(dirs):
        try:
            with os.scandir(d) as it:
                for e in it:
                    stem, ext = os.path.splitext(e.name)
                    rank = _EXT_RANK.get(ext.lower())
                    if rank is None:
                        continue
                    key = (order, rank)
                    cur = best.get(stem.lower())
                    if cur is None or key < cur[0]:
                        best[stem.lower()] = (key, e.path)
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
    return bool(path) and os.path.splitext(path)[1].lower() in _RUNNABLE and os.path.isfile(path)


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
            "id": spec["id"], "name": spec["name"], "kind": spec["kind"], "detected": detected,
            "path": path, "version": version, "via": via, "listening": listening if spec.get("port") else None,
        })
    return {"tools": tools, "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1), "checked_at": time.time()}


def find(tool_id, check_ports=False):
    for t in detect(check_ports=check_ports)["tools"]:
        if t["id"] == tool_id:
            return t
    return None
