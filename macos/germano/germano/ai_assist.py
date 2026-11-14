"""Assistente di configurazione delle AI di questo computer (0.91, turno 28).

Accanto a ogni AI rilevata Germano dice che cosa manca per usarla e lo fa con un clic:
- Antigravity: installa la CLI ufficiale «agy» (manifesto di Google -> host consentito -> SHA-512 -> firma Authenticode
  «Google LLC» su Windows -> «agy install») e verifica che usi gia' l'account di Antigravity Desktop. L'accesso e'
  condiviso dal portachiavi del sistema (Gestore credenziali di Windows, Portachiavi Apple, Secret Service): Germano
  non legge e non copia mai i token, controlla solo che la voce esista e mostra l'account in forma oscurata;
- servizi via API (Qwen, GLM, Kimi, DeepSeek, OpenAI, Gemini...): «Recupera configurazione» cerca le chiavi gia'
  impostate per altri strumenti (variabili d'ambiente, Qwen Code, Claude Code, OpenCode, Codex, Gemini CLI) e COLLEGA
  la fonte: state/ai_links.json contiene solo il nome della fonte e della variabile, mai la chiave, che si legge al
  momento dell'uso, lato server (providers.server_key). Al browser arriva solo «chiave trovata in ...»;
- modelli locali (Ollama, LM Studio, Jan): modelli gia' scaricati sul disco anche a servizio spento, installazione di
  Ollama su Windows (OllamaSetup.exe ufficiale, firma «Ollama Inc.», per utente), avvio del server e download di un
  modello consigliato.

Sicurezza: le rotte /api/ai/assist/* rispondono solo a questo computer (server.py); le azioni sono ricette fisse,
senza shell e senza testo dell'utente tra gli argomenti; i download avvengono solo in HTTPS da host consentiti e con
verifica dell'impronta o della firma; il registro dei lavori viene ripulito da qualsiasi chiave nota.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

from . import common
from . import harness
from . import providers

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LINKS_FILE = os.path.join(common.STATE_DIR, "ai_links.json")
_LOCK = threading.RLock()

# ------------------------------------------------------------------------------------------------ fonti esterne
# Antigravity CLI: manifesto ufficiale (lo stesso degli script https://antigravity.google/cli/install.ps1 e install.sh)
AGY_MANIFEST = "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/{platform}.json"
AGY_HOSTS = ("storage.googleapis.com",)
AGY_PATH_PREFIX = "/antigravity-public/antigravity-cli/"
AGY_SIGNER = "O=Google LLC"
AGY_MAX_BYTES = 1024 ** 3
# Ollama per Windows: installer ufficiale (come https://ollama.com/install.ps1), firma Authenticode di Ollama Inc.
OLLAMA_SETUP = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_HOSTS = ("ollama.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
OLLAMA_SIGNER = "Ollama Inc"
OLLAMA_MAX_BYTES = 4 * 1024 ** 3
OLLAMA_PORT = 11434
# Modelli locali consigliati (catalogo Ollama verificato il 14/11/2026): piccoli, multilingua, adatti a un PC normale
OLLAMA_RECOMMENDED = (
    ("qwen3.5:4b", "Qwen 3.5 4B", "equilibrato, buono in italiano", "balanced, good in Italian"),
    ("gemma4:e4b", "Gemma 4 E4B", "Google, multimodale", "Google, multimodal"),
    ("llama3.2:3b", "Llama 3.2 3B", "Meta, leggero", "Meta, lightweight"),
    ("qwen3.5:2b", "Qwen 3.5 2B", "per PC con poca memoria", "for PCs with little memory"),
)
OLLAMA_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,80}(:[A-Za-z0-9._-]{1,60})?$")

LINKS = {   # pagine ufficiali mostrate nell'assistente (solo collegamenti: si aprono nel browser)
    "agy_docs": "https://antigravity.google/docs/cli/reference",
    "agy_install": "https://antigravity.google/docs/getting-started",
    "antigravity_download": "https://antigravity.google/download",
    "qwen_keys": "https://www.alibabacloud.com/help/en/model-studio/get-api-key",
    "qwen_models": "https://www.alibabacloud.com/help/en/model-studio/qwen4-max-preview",
    "qwen_code": "https://qwenlm.github.io/qwen-code-docs/en/users/configuration/auth/",
    "glm_docs": "https://docs.z.ai/guides/llm/glm-5.3",
    "ollama_download": "https://ollama.com/download",
    "ollama_library": "https://ollama.com/library",
    "lmstudio_download": "https://lmstudio.ai/download",
    "jan_download": "https://jan.ai/download",
    "node_download": "https://nodejs.org/en/download",
}


class AssistError(RuntimeError):
    status = 400


def _L(lang, it, en):
    return en if lang == "en" else it


def _home():
    return os.path.expanduser("~")


def _read_json(path, limit=5_000_000):
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > limit:
            return None
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _read_env_file(path, limit=200_000):
    """File .env (CHIAVE=valore, con eventuale «export» e virgolette): {nome: valore}."""
    out = {}
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > limit:
            return out
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,80}$", k):
                    out[k] = v
    except OSError:
        pass
    return out


def mask_account(value):
    """Account mostrato in forma riconoscibile ma non completa: «ma…@studio.it» (mai il nome intero)."""
    v = str(value or "").strip()
    if not v:
        return ""
    if "@" in v:
        user, _, domain = v.rpartition("@")
        return (user[:2] if len(user) > 3 else user[:1]) + "…@" + domain
    return v[:2] + "…"


def _short_path(path):
    """Percorso con la cartella personale abbreviata in «~» (per i testi mostrati nella pagina)."""
    home = _home()
    p = str(path or "")
    if home and p.lower().startswith(home.lower()):
        return "~" + p[len(home):]
    return p


# ------------------------------------------------------------------------------------------------ chiavi: fonti
_SECRET_VALUES = set()   # valori letti dalle fonti: si tolgono da qualsiasi testo dei lavori


def _remember_secret(value):
    if value and len(value) >= 8:
        _SECRET_VALUES.add(value)
        if len(_SECRET_VALUES) > 200:
            _SECRET_VALUES.pop()


def scrub(text):
    """Toglie da un testo le chiavi note e quelle riconoscibili dal formato."""
    s = str(text or "")
    for v in list(_SECRET_VALUES):
        if v in s:
            s = s.replace(v, v[:3] + "…(nascosta)")
    try:
        from .glass import redact_text
        s = redact_text(s)
    except Exception:
        pass
    return s


# Variabile d'ambiente -> servizio (oltre a quelle di providers.SERVICES[*]["keys"]); «!host» = regione non supportata
_EXTRA_VARS = {"ZHIPUAI_API_KEY": "!open.bigmodel.cn", "BAILIAN_CODING_PLAN_API_KEY": "qwen-coding"}
# Host dell'indirizzo del servizio -> servizio di Germano (per le chiavi con un base URL accanto)
_HOST_SERVICES = (
    ("token-plan.ap-southeast-1.maas.aliyuncs.com", "qwen-token"),
    ("coding-intl.dashscope.aliyuncs.com", "qwen-coding"),
    ("dashscope-intl.aliyuncs.com", "qwen"),
    ("api.z.ai/api/coding", "zai-coding"),
    ("api.z.ai/api/anthropic", "zai-coding"),   # Claude Code + Z.ai = GLM Coding Plan (documentazione di Z.ai)
    ("api.z.ai", "zai"),
    ("api.moonshot.ai", "moonshot"),
    ("api.deepseek.com", "deepseek"),
    ("openrouter.ai", "openrouter"),
    ("api.anthropic.com", "anthropic"),
    ("api.openai.com", "openai"),
    ("generativelanguage.googleapis.com", "gemini"),
    ("api.mistral.ai", "mistral"),
    ("api.x.ai", "xai"),
    ("api.groq.com", "groq"),
    ("api.perplexity.ai", "perplexity"),
)
# Regioni note ma non ancora tra i servizi di Germano: si segnalano invece di collegare la chiave al servizio sbagliato
_UNSUPPORTED_HOSTS = ("dashscope.aliyuncs.com", "dashscope-us.aliyuncs.com", "cn-hongkong.dashscope.aliyuncs.com",
                      "token-plan.cn-beijing", "coding.dashscope.aliyuncs.com", "open.bigmodel.cn",
                      "api.moonshot.cn", "maas.aliyuncs.com")
# Fornitori di OpenCode (auth.json) -> servizio
_OPENCODE = {"openai": "openai", "anthropic": "anthropic", "zai": "zai", "zai-coding-plan": "zai-coding",
             "alibaba": "qwen", "moonshotai": "moonshot", "deepseek": "deepseek", "google": "gemini",
             "openrouter": "openrouter", "groq": "groq", "xai": "xai", "mistral": "mistral", "perplexity": "perplexity",
             "zhipuai": "!open.bigmodel.cn", "zhipuai-coding-plan": "!open.bigmodel.cn",
             "alibaba-cn": "!dashscope.aliyuncs.com", "moonshotai-cn": "!api.moonshot.cn"}


def _service_for_url(url):
    u = str(url or "").lower()
    for host, sid in _HOST_SERVICES:
        if host in u:
            return sid
    for host in _UNSUPPORTED_HOSTS:
        if host in u:
            return "!" + host
    return None


def _var_services():
    out = {}
    for sid, spec in providers.SERVICES.items():
        for var in spec.get("keys", ()):
            out.setdefault(var, sid)
    for var, sid in _EXTRA_VARS.items():
        if sid:
            out.setdefault(var, sid)
    return out


def _registry_env():
    """Variabili d'ambiente salvate nel registro (utente, poi sistema): comprendono quelle impostate DOPO l'avvio di
    Germano (es. «setx DASHSCOPE_API_KEY ...»), che il processo non vede."""
    if not IS_WIN:
        return {}
    import winreg
    out = {}
    for root, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(root, sub) as k:
                i = 0
                while True:
                    try:
                        name, value, _t = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    if isinstance(value, str):
                        out[name.upper()] = value
        except OSError:
            continue
    return out


def _qwen_candidates():
    """Qwen Code: ~/.qwen/settings.json (blocco «env», «modelProviders», «security.auth») e ~/.qwen/.env."""
    base = os.path.join(_home(), ".qwen")
    settings = _read_json(os.path.join(base, "settings.json")) or {}
    env = {}
    env.update(_read_env_file(os.path.join(base, ".env")))
    if isinstance(settings.get("env"), dict):
        env.update({k: v for k, v in settings["env"].items() if isinstance(v, str)})
    urls = {}   # variabile -> base URL dichiarato accanto
    providers_cfg = settings.get("modelProviders")
    if isinstance(providers_cfg, dict):
        for entries in providers_cfg.values():
            for e in entries if isinstance(entries, list) else []:
                if isinstance(e, dict) and isinstance(e.get("envKey"), str) and isinstance(e.get("baseUrl"), str):
                    urls.setdefault(e["envKey"], e["baseUrl"])
    auth = (settings.get("security") or {}).get("auth") if isinstance(settings.get("security"), dict) else None
    if isinstance(auth, dict) and isinstance(auth.get("apiKey"), str):
        env.setdefault("__auth_apiKey", auth["apiKey"])
        if isinstance(auth.get("baseUrl"), str):
            urls["__auth_apiKey"] = auth["baseUrl"]
    if "OPENAI_BASE_URL" in env:
        urls.setdefault("OPENAI_API_KEY", env["OPENAI_BASE_URL"])
    out = []
    var_services = _var_services()
    for var, value in env.items():
        if not isinstance(value, str) or not providers.KEY_RE.match(value.strip()):
            continue
        sid = _service_for_url(urls.get(var)) if urls.get(var) else None
        if sid is None:
            sid = var_services.get(var)
            if var == "OPENAI_API_KEY" and not urls.get(var):
                sid = None      # chiave OpenAI generica senza indirizzo: non e' di Qwen
            if var == "__auth_apiKey":
                sid = None
        if sid:
            out.append({"service": sid, "var": var, "value": value.strip(), "file": os.path.join(base, "settings.json")})
    return out


def _claude_candidates():
    """Claude Code configurato verso un altro fornitore (es. GLM di Z.ai, Kimi, DeepSeek): ~/.claude/settings.json,
    blocco «env» con ANTHROPIC_BASE_URL e ANTHROPIC_AUTH_TOKEN / ANTHROPIC_API_KEY."""
    path = os.path.join(_home(), ".claude", "settings.json")
    data = _read_json(path) or {}
    env = data.get("env") if isinstance(data.get("env"), dict) else {}
    url = env.get("ANTHROPIC_BASE_URL")
    out = []
    for var in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        value = env.get(var)
        if not isinstance(value, str) or not providers.KEY_RE.match(value.strip()):
            continue
        sid = _service_for_url(url) if url else ("anthropic" if var == "ANTHROPIC_API_KEY" else None)
        if sid:
            out.append({"service": sid, "var": var, "value": value.strip(), "file": path})
    return out


def _opencode_candidates():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(_home(), ".local", "share")
    path = os.path.join(base, "opencode", "auth.json")
    data = _read_json(path) or {}
    out = []
    for prov, entry in (data.items() if isinstance(data, dict) else []):
        sid = _OPENCODE.get(str(prov))
        if sid and isinstance(entry, dict) and entry.get("type") == "api" and isinstance(entry.get("key"), str) \
                and providers.KEY_RE.match(entry["key"].strip()):
            out.append({"service": sid, "var": str(prov), "value": entry["key"].strip(), "file": path})
    return out


def _codex_candidates():
    path = os.path.join(os.environ.get("CODEX_HOME") or os.path.join(_home(), ".codex"), "auth.json")
    data = _read_json(path) or {}
    value = data.get("OPENAI_API_KEY") if isinstance(data, dict) else None
    if isinstance(value, str) and providers.KEY_RE.match(value.strip()):
        return [{"service": "openai", "var": "OPENAI_API_KEY", "value": value.strip(), "file": path}]
    return []


def _gemini_candidates():
    path = os.path.join(_home(), ".gemini", ".env")
    env = _read_env_file(path)
    out = []
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = env.get(var)
        if isinstance(value, str) and providers.KEY_RE.match(value.strip()):
            out.append({"service": "gemini", "var": var, "value": value.strip(), "file": path})
    return out


def _env_candidates(env, source):
    out = []
    var_services = _var_services()
    for var, sid in var_services.items():
        value = env.get(var) if source == "env" else env.get(var.upper())
        if isinstance(value, str) and providers.KEY_RE.match(value.strip()):
            out.append({"service": sid, "var": var, "value": value.strip(), "file": None})
    return out


# Nome breve della fonte (per le etichette dell'elenco dei modelli)
SOURCE_SHORT = {"env-user": "Windows", "qwen-code": "Qwen Code", "claude-code": "Claude Code", "opencode": "OpenCode",
                "codex": "Codex", "gemini-cli": "Gemini CLI"}
# id della fonte -> (etichetta it, etichetta en, funzione). L'ordine e' la priorita' quando un servizio ha piu' chiavi.
SOURCES = (
    ("env-user", "variabili d'ambiente di Windows (impostate dopo l'avvio di Germano)",
     "Windows environment variables (set after Germano started)", lambda: _env_candidates(_registry_env(), "registry")),
    ("qwen-code", "Qwen Code (~/.qwen)", "Qwen Code (~/.qwen)", _qwen_candidates),
    ("claude-code", "Claude Code (~/.claude/settings.json)", "Claude Code (~/.claude/settings.json)", _claude_candidates),
    ("opencode", "OpenCode (auth.json)", "OpenCode (auth.json)", _opencode_candidates),
    ("codex", "Codex CLI (~/.codex/auth.json)", "Codex CLI (~/.codex/auth.json)", _codex_candidates),
    ("gemini-cli", "Gemini CLI (~/.gemini/.env)", "Gemini CLI (~/.gemini/.env)", _gemini_candidates),
)
_SOURCE_IDS = {s[0] for s in SOURCES}
_cand_cache = {"at": 0.0, "items": []}


def _candidates(max_age=15.0):
    """Chiavi trovate nelle fonti (con il valore: SOLO in memoria, mai restituito alle pagine)."""
    with _LOCK:
        if time.time() - _cand_cache["at"] < max_age:
            return _cand_cache["items"]
        items = []
        for sid, _it, _en, fn in SOURCES:
            if sid == "env-user" and not IS_WIN:
                continue
            try:
                found = fn()
            except Exception:
                found = []
            for c in found:
                if c.get("service") and not str(c["service"]).startswith("!") and providers.get(c["service"]):
                    c["source"] = sid
                    _remember_secret(c["value"])
                    items.append(c)
                elif str(c.get("service") or "").startswith("!"):
                    c["source"] = sid
                    items.append(c)       # regione non supportata: si segnala soltanto
        _cand_cache.update(at=time.time(), items=items)
        return items


def source_label(source, lang="it"):
    for sid, it, en, _fn in SOURCES:
        if sid == source:
            return en if lang == "en" else it
    return source


def found_keys(lang="it"):
    """{servizio: [{"source", "label", "var"}]} delle chiavi trovate (senza valori)."""
    out = {}
    for c in _candidates():
        if str(c["service"]).startswith("!"):
            continue
        out.setdefault(c["service"], []).append({"source": c["source"], "label": source_label(c["source"], lang),
                                                 "var": c["var"]})
    return out


def unsupported_keys():
    return [c for c in _candidates() if str(c["service"]).startswith("!")]


# ------------------------------------------------------------------------------------------------ collegamenti
_links_cache = {"mtime": None, "data": {}}


def _load_links():
    """Collegamenti salvati (letti di nuovo solo se il file e' cambiato: si consultano a ogni elenco dei modelli)."""
    try:
        mtime = os.path.getmtime(LINKS_FILE)
    except OSError:
        mtime = None
    if mtime is not None and mtime == _links_cache["mtime"]:
        return dict(_links_cache["data"])
    data = common.read_json(LINKS_FILE, {}) or {} if mtime is not None else {}
    raw = data.get("links") if isinstance(data, dict) else None
    out = {}
    for sid, v in (raw.items() if isinstance(raw, dict) else []):
        if providers.get(sid) and isinstance(v, dict) and v.get("source") in _SOURCE_IDS and isinstance(v.get("var"), str):
            out[sid] = {"source": v["source"], "var": v["var"][:80], "at": v.get("at")}
    _links_cache.update(mtime=mtime, data=out)
    return dict(out)


def _save_links(data):
    os.makedirs(os.path.dirname(LINKS_FILE), exist_ok=True)
    common.atomic_write_json(LINKS_FILE, {"version": 1, "links": data}, indent=2)
    _links_cache.update(mtime=None, data={})


def links():
    with _LOCK:
        return _load_links()


def link(service, source, var):
    with _LOCK:
        cur = _load_links()
        cur[service] = {"source": source, "var": var, "at": int(time.time())}
        _save_links(cur)


def unlink(service):
    with _LOCK:
        cur = _load_links()
        if cur.pop(service, None) is not None:
            _save_links(cur)
            return True
        return False


def linked_key(service):
    """Chiave del servizio letta ADESSO dalla fonte collegata ('' se il collegamento non vale piu')."""
    lk = links().get(service)
    if not lk:
        return ""
    for c in _candidates():
        if c["service"] == service and c["source"] == lk["source"] and c["var"] == lk["var"]:
            return c["value"]
    return ""


def key_origin(service, lang="it"):
    """Da dove arriva la chiave del server per il servizio: «variabile X» o «collegata a ...», '' se non c'e'."""
    spec = providers.get(service) or {}
    for var in spec.get("keys", ()):
        if (os.environ.get(var) or "").strip():
            return var
    lk = links().get(service)
    if lk and linked_key(service):
        return _L(lang, "collegata: ", "linked: ") + source_label(lk["source"], lang)
    return ""


# ------------------------------------------------------------------------------------------------ Antigravity
def _agy_platform():
    import platform
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64" if machine in ("amd64", "x86_64", "x64") else None
    if arch is None:
        return None
    if IS_WIN:
        return f"windows_{arch}"
    if IS_MAC:
        return f"darwin_{arch}"
    if sys.platform.startswith("linux"):
        libc = "".join(platform.libc_ver())
        return f"linux_{arch}" + ("" if libc else "_musl")
    return None


def agy_target_path():
    """Dove l'installatore ufficiale mette la CLI: %LOCALAPPDATA%\\agy\\bin\\agy.exe oppure ~/.local/bin/agy."""
    if IS_WIN:
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(_home(), "AppData", "Local"),
                            "agy", "bin", "agy.exe")
    return os.path.join(_home(), ".local", "bin", "agy")


def _tool(tools, tid):
    for t in tools or []:
        if t.get("id") == tid:
            return t
    return {}


def agy_path(tools=None):
    t = _tool(tools, "agy")
    if t.get("detected") and t.get("path") and os.path.isfile(t["path"]):
        return t["path"]
    p = agy_target_path()
    return p if os.path.isfile(p) else None


def _win_uninstall_version(fragment):
    """Versione dichiarata da un programma nell'elenco «App installate» (registro), cercata per percorso."""
    if not IS_WIN:
        return None
    import winreg
    frag = fragment.lower()
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            base = winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
        except OSError:
            continue
        with base:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(base, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(base, name) as k:
                        vals = {}
                        for field in ("DisplayIcon", "UninstallString", "InstallLocation", "DisplayVersion"):
                            try:
                                vals[field] = str(winreg.QueryValueEx(k, field)[0])
                            except OSError:
                                vals[field] = ""
                except OSError:
                    continue
                if any(frag in vals[f].lower() for f in ("DisplayIcon", "UninstallString", "InstallLocation")):
                    if vals["DisplayVersion"]:
                        return vals["DisplayVersion"][:40]
    return None


def antigravity_desktop(tools=None):
    """Antigravity Desktop: installazione, versione e account dell'ultimo accesso (oscurato)."""
    t = _tool(tools, "antigravity")
    path = t.get("path") if t.get("detected") else None
    version = t.get("version")
    if path and IS_WIN and not version:
        version = _win_uninstall_version(os.sep + os.path.join("programs", "antigravity") + os.sep)
    if path and IS_MAC and not version:
        try:
            import plistlib
            with open(os.path.join(path, "Contents", "Info.plist"), "rb") as f:
                version = str(plistlib.load(f).get("CFBundleShortVersionString") or "")[:40] or None
        except (OSError, ValueError, Exception):
            version = None
    if IS_WIN:
        store = os.path.join(os.environ.get("APPDATA") or "", "Antigravity", "app_storage.json")
    elif IS_MAC:
        store = os.path.join(_home(), "Library", "Application Support", "Antigravity", "app_storage.json")
    else:
        store = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(_home(), ".config"), "Antigravity",
                             "app_storage.json")
    data = _read_json(store, limit=20_000_000) or {}
    user = data.get("jetski.onboarding.lastLoginUsername") if isinstance(data, dict) else None
    account = mask_account(user) if isinstance(user, str) else ""
    return {"installed": bool(path), "version": version, "account": account}


def shared_login():
    """True se nel portachiavi del sistema c'e' l'accesso condiviso di Antigravity (voce «gemini:antigravity»), False
    se manca, None se non si puo' sapere. Si legge SOLO il nome della voce, mai il suo contenuto."""
    if IS_WIN:
        try:
            import ctypes
            from ctypes import wintypes

            class CREDENTIAL(ctypes.Structure):
                _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                            ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                            ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.c_void_p),
                            ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                            ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                            ("UserName", wintypes.LPWSTR)]
            advapi = ctypes.WinDLL("advapi32", use_last_error=True)
            advapi.CredEnumerateW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                              ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(CREDENTIAL)))]
            advapi.CredEnumerateW.restype = wintypes.BOOL
            advapi.CredFree.argtypes = [ctypes.c_void_p]
            count = wintypes.DWORD()
            creds = ctypes.POINTER(ctypes.POINTER(CREDENTIAL))()
            if not advapi.CredEnumerateW("gemini:antigravity*", 0, ctypes.byref(count), ctypes.byref(creds)):
                return False
            try:
                names = [str(creds[i].contents.TargetName or "") for i in range(count.value)]
            finally:
                advapi.CredFree(creds)
            return any(n.lower().startswith("gemini:antigravity") for n in names)
        except Exception:
            return None
    if IS_MAC:
        try:   # senza -w/-g «security» mostra solo gli attributi della voce, non la password
            r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", "gemini", "-a", "antigravity"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=8)
            return r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return None
    return None


_agy_state = {"key": None, "at": 0.0, "models": None, "error": None, "busy": False, "version": None}
AGY_MODELS_TTL = 600.0


def _run_agy(path, args, timeout=60, isolated=True):
    env = harness.cli_env_for("agy", isolated=isolated)
    r = subprocess.run([path] + args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       cwd=harness.agy_workdir(), env=env, timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def _parse_models(text):
    out = []
    for line in text.splitlines():
        parts = line.strip().split("\t")
        mid = parts[0].strip() if parts else ""
        if mid and harness.valid_model(mid) and " " not in mid:
            out.append({"id": mid, "name": (parts[1].strip() if len(parts) > 1 else mid)[:80]})
    return out[:120]


def agy_refresh(path, wait=False):
    """Aggiorna in background versione e modelli della CLI (agy models = verifica che l'accesso funzioni)."""
    def work():
        try:
            rc, out, err = _run_agy(path, ["--version"], timeout=20)
            version = out.strip().splitlines()[0][:40] if rc == 0 and out.strip() else None
            rc, out, err = _run_agy(path, ["models"], timeout=60)
            models = _parse_models(out) if rc == 0 else None
            error = None if rc == 0 and models else scrub((err or out).strip()[-400:]) or f"codice {rc}"
        except subprocess.TimeoutExpired:
            version, models, error = None, None, "timeout"
        except OSError as e:
            version, models, error = None, None, str(e)
        with _LOCK:
            _agy_state.update(key=_agy_key(path), at=time.time(), models=models, error=error, busy=False,
                              version=version or _agy_state.get("version"))
    with _LOCK:
        if _agy_state["busy"]:
            th = None
        else:
            _agy_state["busy"] = True
            th = threading.Thread(target=work, name="germano-agy-models", daemon=True)
            th.start()
    if wait and th is not None:
        th.join(90)


def _agy_key(path):
    try:
        st = os.stat(path)
        return (os.path.normcase(path), int(st.st_mtime), st.st_size)
    except OSError:
        return None


def agy_status(path, refresh_if_stale=True):
    """{"models": [...] | None, "error": str | None, "checked": bool, "version"} dalla cache; se vecchia la aggiorna
    in background (le pagine chiedono le destinazioni ogni 12 s: mai attese qui)."""
    if not path:
        return {"models": None, "error": None, "checked": False, "version": None}
    with _LOCK:
        st = dict(_agy_state)
    stale = st["key"] != _agy_key(path) or time.time() - st["at"] > AGY_MODELS_TTL
    if stale and refresh_if_stale:
        agy_refresh(path)
    fresh = st["key"] == _agy_key(path)
    return {"models": st["models"] if fresh else None, "error": st["error"] if fresh else None,
            "checked": fresh and st["at"] > 0, "version": st.get("version") if fresh else None, "busy": st["busy"]}


# ------------------------------------------------------------------------------------------------ modelli sul disco
def ollama_disk_models():
    """Modelli gia' scaricati da Ollama (anche a servizio spento): manifesti in ~/.ollama/models (o OLLAMA_MODELS)."""
    root = os.environ.get("OLLAMA_MODELS") or os.path.join(_home(), ".ollama", "models")
    base = os.path.join(root, "manifests")
    out = []
    if not os.path.isdir(base):
        return out
    for dirpath, _dirs, files in os.walk(base):
        rel = os.path.relpath(dirpath, base).replace("\\", "/").split("/")
        if len(rel) < 3:
            continue
        registry, namespace, model = rel[0], "/".join(rel[1:-1]), rel[-1]
        for tag in files:
            if tag.startswith("."):
                continue
            if registry == "registry.ollama.ai":
                name = (f"{model}:{tag}" if namespace == "library" else f"{namespace}/{model}:{tag}")
            else:
                name = f"{registry}/{namespace}/{model}:{tag}"
            if providers.MODEL_RE.match(name):
                out.append(name)
            if len(out) >= 200:
                return sorted(out)
    return sorted(out)


def lmstudio_dirs():
    roots = [os.path.join(_home(), ".lmstudio", "models"), os.path.join(_home(), ".cache", "lm-studio", "models")]
    settings = _read_json(os.path.join(_home(), ".lmstudio", "settings.json")) or {}
    custom = settings.get("downloadsFolder") if isinstance(settings, dict) else None
    if isinstance(custom, str) and custom.strip():
        roots.insert(0, custom.strip())
    return [r for r in dict.fromkeys(roots) if os.path.isdir(r)]


def lmstudio_disk_models():
    """Modelli scaricati da LM Studio: cartelle <editore>/<modello> con file .gguf o .safetensors."""
    out = []
    for root in lmstudio_dirs():
        try:
            for pub in sorted(os.listdir(root)):
                pdir = os.path.join(root, pub)
                if not os.path.isdir(pdir) or pub.startswith("."):
                    continue
                for repo in sorted(os.listdir(pdir)):
                    rdir = os.path.join(pdir, repo)
                    if not os.path.isdir(rdir):
                        continue
                    try:
                        has = any(f.lower().endswith((".gguf", ".safetensors")) for f in os.listdir(rdir))
                    except OSError:
                        has = False
                    if has:
                        out.append(f"{pub}/{repo}")
                    if len(out) >= 200:
                        return out
        except OSError:
            continue
    return out


def jan_data_dir():
    if IS_WIN:
        base = os.path.join(os.environ.get("APPDATA") or "", "Jan", "data")
    elif IS_MAC:
        base = os.path.join(_home(), "Library", "Application Support", "Jan", "data")
    else:
        base = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(_home(), ".config"), "Jan", "data")
    return base if os.path.isdir(base) else None


def jan_disk_models():
    base = jan_data_dir()
    out = []
    if not base:
        return out
    for sub in (os.path.join("llamacpp", "models"), "models"):
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            continue
        for dirpath, _dirs, files in os.walk(d):
            if any(f.lower() in ("model.yml", "model.json") or f.lower().endswith(".gguf") for f in files):
                name = os.path.relpath(dirpath, d).replace("\\", "/")
                if name != "." and name not in out:
                    out.append(name[:128])
            if len(out) >= 200:
                return out
    return out


_disk_cache = {}


def disk_models(kind, max_age=30.0):
    fn = {"ollama": ollama_disk_models, "lm-studio": lmstudio_disk_models, "jan": jan_disk_models}[kind]
    hit = _disk_cache.get(kind)
    if hit and time.time() - hit[0] < max_age:
        return hit[1]
    try:
        val = fn()
    except Exception:
        val = []
    _disk_cache[kind] = (time.time(), val)
    return val


def _lms_path(tools):
    t = _tool(tools, "lm-studio")
    p = t.get("path") if t.get("via") == "path" else None
    if p and os.path.basename(p).lower().startswith("lms"):
        return p
    cand = os.path.join(_home(), ".lmstudio", "bin", "lms.exe" if IS_WIN else "lms")
    return cand if os.path.isfile(cand) else None


def _node_tools():
    """(npm, versione di node) se Node.js e' installato."""
    import shutil as _sh
    npm = _sh.which("npm.cmd" if IS_WIN else "npm")
    if not npm and IS_WIN:
        cand = os.path.join(os.environ.get("ProgramFiles") or r"C:\Program Files", "nodejs", "npm.cmd")
        npm = cand if os.path.isfile(cand) else None
    node = _sh.which("node.exe" if IS_WIN else "node")
    if not node and npm:
        cand = os.path.join(os.path.dirname(npm), "node.exe" if IS_WIN else "node")
        node = cand if os.path.isfile(cand) else None
    version = None
    if node:
        try:
            r = subprocess.run([node, "--version"], stdin=subprocess.DEVNULL, capture_output=True, timeout=10,
                               creationflags=NO_WINDOW)
            version = r.stdout.decode("utf-8", "replace").strip().lstrip("v")[:20] or None
        except (OSError, subprocess.TimeoutExpired):
            version = None
    return npm, version


# ------------------------------------------------------------------------------------------------ lavori
# Righe di registro delle CLI scritte in Go (es. «agy install»): «ERROR: logging before google.Init: I1114 11:34:51.11
# 1 installer.go:22] testo» sono messaggi informativi, non errori: si mostra solo il testo.
_GLOG_RE = re.compile(r"^(?:ERROR: logging before google\.Init: )?[IWEF]\d{4} \d{2}:\d{2}:\d{2}\.\d+\s+\d+ "
                      r"[\w./-]+:\d+\] ")


class Job:
    def __init__(self, action, param, assist, title):
        self.id = uuid.uuid4().hex[:12]
        self.action, self.param, self.assist, self.title = action, param, assist, title
        self.state = "running"
        self.progress = None
        self.lines = []
        self.result = {}
        self.message = ""
        self.started = time.time()
        self.ended = None
        self.cancel = threading.Event()
        self.proc = None

    def log(self, text):
        line = _GLOG_RE.sub("", scrub(str(text or "")).rstrip())[:600]
        if line:
            with _LOCK:
                self.lines.append({"t": round(time.time() - self.started, 1), "text": line})
                del self.lines[:-400]

    def check(self):
        if self.cancel.is_set():
            raise _Cancelled()

    def view(self, since=0):
        with _LOCK:
            return {"id": self.id, "action": self.action, "assist": self.assist, "title": self.title,
                    "state": self.state, "progress": self.progress, "message": self.message,
                    "lines": self.lines[since:], "next": len(self.lines), "result": self.result,
                    "seconds": round((self.ended or time.time()) - self.started, 1)}


class _Cancelled(Exception):
    pass


JOBS = {}
_refresh_hook = None


def set_refresh_hook(fn):
    """Funzione chiamata a fine lavoro (server.py svuota la cache del rilevamento: l'AI compare subito)."""
    global _refresh_hook
    _refresh_hook = fn


def job(jid):
    with _LOCK:
        return JOBS.get(str(jid or ""))


def running_jobs():
    with _LOCK:
        return [j for j in JOBS.values() if j.state == "running"]


def cancel_job(jid):
    j = job(jid)
    if not j:
        return None
    j.cancel.set()
    p = j.proc
    if p is not None:
        harness._kill_tree(p)
    return j


def _spawn(j, fn, lang):
    def work():
        try:
            fn(j, lang)
            if j.state == "running":
                j.state = "done"
        except _Cancelled:
            j.state = "cancelled"
            j.message = _L(lang, "Operazione annullata.", "Operation cancelled.")
        except AssistError as e:
            j.state = "error"
            j.message = scrub(str(e))
        except Exception as e:
            j.state = "error"
            j.message = scrub(_L(lang, f"Errore imprevisto: {e}", f"Unexpected error: {e}"))
        finally:
            j.ended = time.time()
            j.proc = None          # il messaggio finale si mostra a parte (j.message), non si ripete nel registro
            common.log(f"Assistente AI: {j.action} -> {j.state}")
            if _refresh_hook:
                try:
                    _refresh_hook()
                except Exception:
                    pass
    threading.Thread(target=work, name=f"germano-assist-{j.action}", daemon=True).start()


def _run_process(j, args, timeout, env=None, cwd=None):
    """Processo con argomenti fissi, senza shell; l'uscita va nel registro del lavoro (ripulita dalle chiavi)."""
    j.check()
    try:
        p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=env, cwd=cwd, creationflags=NO_WINDOW)
    except OSError as e:
        raise AssistError(f"{os.path.basename(args[0])}: {e}") from None
    j.proc = p
    timer = threading.Timer(timeout, lambda: harness._kill_tree(p))
    timer.daemon = True
    timer.start()
    try:
        for raw in p.stdout:
            j.log(raw.decode("utf-8", "replace"))
            if j.cancel.is_set():
                harness._kill_tree(p)
                break
        p.wait(timeout=30)
    finally:
        timer.cancel()
        j.proc = None
    j.check()
    return p.returncode


def _http():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = f"GermanoAI/{common.get_version()}"
    return s


def _check_url(url, hosts, prefix=None):
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if u.scheme != "https" or (u.hostname or "").lower() not in hosts:
        return False
    return not prefix or u.path.startswith(prefix)


def _download(j, url, dest, hosts, max_bytes, lang, sha512=None, prefix=None):
    """Scarica in `dest` (accanto alla destinazione finale) mostrando l'avanzamento; host e redirect controllati."""
    import requests
    if not _check_url(url, hosts, prefix):
        raise AssistError(_L(lang, f"Indirizzo di download non consentito: {url[:120]}",
                             f"Download address not allowed: {url[:120]}"))
    h = hashlib.sha512()
    total = 0
    try:
        with _http().get(url, stream=True, timeout=(20, 120), allow_redirects=True) as r:
            final = r.url
            if not _check_url(final, hosts):
                raise AssistError(_L(lang, f"Il download e' stato reindirizzato a un host non consentito: "
                                           f"{urllib.parse.urlsplit(final).hostname}",
                                     f"The download was redirected to a host that is not allowed: "
                                     f"{urllib.parse.urlsplit(final).hostname}"))
            if r.status_code != 200:
                raise AssistError(_L(lang, f"Download non riuscito (HTTP {r.status_code}).",
                                     f"Download failed (HTTP {r.status_code})."))
            size = int(r.headers.get("Content-Length") or 0) or None
            if size and size > max_bytes:
                raise AssistError(_L(lang, "File troppo grande.", "File too large."))
            j.log(_L(lang, f"Download da {urllib.parse.urlsplit(final).hostname}"
                           + (f" ({size / 1048576:.0f} MB)" if size else ""),
                     f"Downloading from {urllib.parse.urlsplit(final).hostname}"
                     + (f" ({size / 1048576:.0f} MB)" if size else "")))
            last = 0.0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if j.cancel.is_set():
                        raise _Cancelled()
                    if not chunk:
                        continue
                    f.write(chunk)
                    h.update(chunk)
                    total += len(chunk)
                    if total > max_bytes:
                        raise AssistError(_L(lang, "File troppo grande.", "File too large."))
                    if size and time.time() - last > 0.4:
                        last = time.time()
                        j.progress = round(min(0.99, total / size), 3)
    except requests.RequestException as e:
        raise AssistError(_L(lang, f"Download non riuscito ({e.__class__.__name__}): controlla la connessione a "
                                   "Internet.", f"Download failed ({e.__class__.__name__}): check the Internet "
                                                "connection.")) from None
    except BaseException:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise
    if sha512 and h.hexdigest().lower() != sha512.lower():
        try:
            os.remove(dest)
        except OSError:
            pass
        raise AssistError(_L(lang, "Impronta SHA-512 diversa da quella pubblicata: file scartato (download corrotto o "
                                   "manomesso).", "SHA-512 digest differs from the published one: file discarded "
                                                  "(corrupted or tampered download)."))
    j.log(_L(lang, f"Scaricati {total / 1048576:.1f} MB" + (", impronta SHA-512 verificata" if sha512 else ""),
             f"Downloaded {total / 1048576:.1f} MB" + (", SHA-512 digest verified" if sha512 else "")))
    return total


def authenticode(path):
    """(stato, soggetto del certificato) della firma digitale di un eseguibile Windows; (None, None) se non
    verificabile. Il percorso passa da una variabile d'ambiente, non dal testo del comando."""
    if not IS_WIN:
        return None, None
    ps = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "WindowsPowerShell", "v1.0",
                      "powershell.exe")
    if not os.path.isfile(ps):
        return None, None
    cmd = ("$s = Get-AuthenticodeSignature -LiteralPath $env:GERMANO_SIGNED_FILE; "
           "@{status=[string]$s.Status; subject=[string]$s.SignerCertificate.Subject} | ConvertTo-Json -Compress")
    env = dict(os.environ, GERMANO_SIGNED_FILE=path)
    try:
        r = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", cmd], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=180, env=env, creationflags=NO_WINDOW)
        data = json.loads(r.stdout.decode("utf-8", "replace").strip() or "{}")
        return data.get("status"), data.get("subject")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None, None


def _require_signature(j, path, signer, lang):
    status, subject = authenticode(path)
    if status is None:
        j.log(_L(lang, "Firma digitale non verificabile su questo sistema: resta valida la verifica dell'impronta.",
                 "Digital signature not verifiable on this system: the digest check still applies."))
        return
    if status != "Valid" or signer.lower() not in str(subject or "").lower():
        try:
            os.remove(path)
        except OSError:
            pass
        raise AssistError(_L(lang, f"Firma digitale non valida o di un altro editore ({status}): file scartato.",
                             f"Invalid digital signature or another publisher ({status}): file discarded."))
    j.log(_L(lang, f"Firma digitale verificata: {signer.replace('O=', '')}",
             f"Digital signature verified: {signer.replace('O=', '')}"))


def _offline(lang):
    if os.environ.get("GERMANO_OFFLINE") == "1":
        raise AssistError(_L(lang, "Germano e' in modalita' offline (GERMANO_OFFLINE=1): nessun download.",
                             "Germano is in offline mode (GERMANO_OFFLINE=1): no downloads."))


def _detach_flags():
    if not IS_WIN:
        return 0
    return 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def _launch_detached(args, cwd=None):
    """Avvia un programma dell'utente che deve restare aperto anche dopo Germano (Ollama, LM Studio, Jan)."""
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "cwd": cwd,
              "close_fds": True}
    if IS_WIN:
        for flags in (_detach_flags() | 0x01000000, _detach_flags()):   # prima fuori dal Job object del lanciatore
            try:
                return subprocess.Popen(args, creationflags=flags, **kwargs)
            except OSError:
                continue
        raise AssistError(f"impossibile avviare {os.path.basename(args[0])}")
    return subprocess.Popen(args, start_new_session=True, **kwargs)


def _wait_port(j, port, seconds):
    from . import ai_detect
    end = time.time() + seconds
    while time.time() < end:
        j.check()
        if ai_detect._port_open(port, timeout=0.3):
            return True
        time.sleep(0.5)
    return False


# ------------------------------------------------------------------------------------------------ azioni
def _act_agy_install(j, lang):
    _offline(lang)
    platform_id = _agy_platform()
    if not platform_id:
        raise AssistError(_L(lang, "Sistema o processore non supportato dalla CLI di Antigravity.",
                             "System or processor not supported by the Antigravity CLI."))
    target = agy_target_path()
    if os.path.isfile(target):
        j.log(_L(lang, f"La CLI e' gia' installata in {_short_path(target)}: verifico l'accesso.",
                 f"The CLI is already installed in {_short_path(target)}: checking the sign-in."))
    else:
        j.log(_L(lang, f"Manifesto ufficiale di Google ({platform_id})…", f"Google's official manifest ({platform_id})…"))
        try:
            r = _http().get(AGY_MANIFEST.format(platform=platform_id), timeout=(15, 30))
            man = r.json() if r.status_code == 200 else None
        except Exception:
            man = None
        if not isinstance(man, dict):
            raise AssistError(_L(lang, "Manifesto della CLI non raggiungibile: controlla la connessione a Internet.",
                                 "CLI manifest not reachable: check the Internet connection."))
        version, url, sha = str(man.get("version") or ""), str(man.get("url") or ""), str(man.get("sha512") or "")
        if not re.match(r"^\d+(\.\d+){1,3}$", version) or not re.match(r"^[0-9a-fA-F]{128}$", sha):
            raise AssistError(_L(lang, "Manifesto della CLI non valido.", "Invalid CLI manifest."))
        j.log(_L(lang, f"Versione {version}", f"Version {version}"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        part = target + ".germano-download"
        _download(j, url, part, AGY_HOSTS, AGY_MAX_BYTES, lang, sha512=sha, prefix=AGY_PATH_PREFIX)
        if IS_WIN:
            _require_signature(j, part, AGY_SIGNER, lang)
        else:
            os.chmod(part, 0o755)
        j.check()
        os.replace(part, target)
        j.progress = None
        j.log(_L(lang, f"Installata in {_short_path(target)}", f"Installed in {_short_path(target)}"))
        # configurazione nativa come negli script ufficiali (PATH e impostazioni della shell dell'utente)
        rc = _run_process(j, [target, "install"], timeout=180, env=harness.cli_env_for("agy", isolated=False))
        if rc != 0:
            j.log(_L(lang, f"«agy install» ha restituito il codice {rc} (non bloccante: la CLI e' gia' utilizzabile).",
                     f"«agy install» returned code {rc} (not blocking: the CLI is already usable)."))
    j.log(_L(lang, "Verifica dell'accesso con l'account di Antigravity (agy models)…",
             "Checking the sign-in with the Antigravity account (agy models)…"))
    agy_refresh(target, wait=True)
    st = agy_status(target, refresh_if_stale=False)
    if st["models"]:
        acc = antigravity_desktop().get("account")
        j.result = {"models": len(st["models"]), "account": acc}
        j.message = _L(lang, f"Pronta: {len(st['models'])} modelli disponibili"
                             + (f" con l'account {acc}" if acc else "") + ". La trovi nell'elenco dei modelli.",
                       f"Ready: {len(st['models'])} models available" + (f" with the account {acc}" if acc else "")
                       + ". You find it in the model list.")
    else:
        j.result = {"login_needed": True}
        j.message = _L(lang, "CLI installata, ma serve l'accesso a Google: usa «Accedi con Google» (si apre una "
                             "finestra della CLI e poi il browser).",
                       "CLI installed, but Google sign-in is needed: use «Sign in with Google» (a CLI window opens, "
                       "then the browser).")


def _act_agy_check(j, lang):
    path = agy_path(_tools())
    if not path:
        raise AssistError(_L(lang, "Antigravity CLI non e' installata.", "Antigravity CLI is not installed."))
    j.log(_L(lang, "agy models…", "agy models…"))
    agy_refresh(path, wait=True)
    st = agy_status(path, refresh_if_stale=False)
    if st["models"]:
        j.result = {"models": len(st["models"])}
        j.message = _L(lang, f"Accesso valido: {len(st['models'])} modelli disponibili.",
                       f"Sign-in valid: {len(st['models'])} models available.")
    else:
        raise AssistError(_L(lang, f"La CLI non riesce a usare l'account: {st['error'] or 'nessun modello'}. Usa "
                                   "«Accedi con Google».", f"The CLI cannot use the account: {st['error'] or 'no model'}"
                                                           ". Use «Sign in with Google»."))


def _act_agy_login(j, lang):
    path = agy_path(_tools())
    if not path:
        raise AssistError(_L(lang, "Antigravity CLI non e' installata.", "Antigravity CLI is not installed."))
    env = harness.cli_env_for("agy", isolated=False)
    if IS_WIN:
        subprocess.Popen([path], creationflags=0x00000010, env=env, cwd=harness.agy_workdir(),   # nuova console
                         close_fds=True)
    elif IS_MAC:
        subprocess.Popen(["/usr/bin/open", "-a", "Terminal", path], close_fds=True)
    else:
        term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal") or shutil.which("konsole")
        if not term:
            raise AssistError(_L(lang, "Apri un terminale e scrivi «agy» per accedere.",
                                 "Open a terminal and type «agy» to sign in."))
        subprocess.Popen([term, "-e", path], start_new_session=True, close_fds=True)
    j.message = _L(lang, "Si e' aperta la finestra della CLI: segui le istruzioni (accesso con Google nel browser), poi "
                         "chiudila e premi «Verifica accesso».",
                   "The CLI window opened: follow the instructions (Google sign-in in the browser), then close it and "
                   "press «Check sign-in».")


def _act_agy_update(j, lang):
    _offline(lang)
    path = agy_path(_tools())
    if not path:
        raise AssistError(_L(lang, "Antigravity CLI non e' installata.", "Antigravity CLI is not installed."))
    rc = _run_process(j, [path, "update"], timeout=600, env=harness.cli_env_for("agy", isolated=False))
    if rc != 0:
        raise AssistError(_L(lang, f"Aggiornamento non riuscito (codice {rc}).", f"Update failed (code {rc})."))
    agy_refresh(path, wait=True)
    j.message = _L(lang, "Antigravity CLI aggiornata.", "Antigravity CLI updated.")


def _act_antigravity_open(j, lang):
    t = _tool(_tools(), "antigravity")
    if not t.get("detected") or not t.get("path"):
        raise AssistError(_L(lang, "Antigravity Desktop non e' installata.", "Antigravity Desktop is not installed."))
    if IS_MAC:
        _launch_detached(["/usr/bin/open", t["path"]])
    else:
        _launch_detached([t["path"]], cwd=os.path.dirname(t["path"]))
    j.message = _L(lang, "Antigravity Desktop aperta: accedi con il tuo account Google, poi torna qui.",
                   "Antigravity Desktop opened: sign in with your Google account, then come back here.")


ASSIST_SERVICES = {   # servizi di ciascuna voce dell'assistente (per «Recupera configurazione»)
    "qwen": ("qwen", "qwen-token", "qwen-coding"),
    "glm": ("zai", "zai-coding"),
}


def _services_for(param):
    if param in ASSIST_SERVICES:
        return ASSIST_SERVICES[param]
    if param.startswith("key:") and providers.get(param[4:]) and not providers.get(param[4:]).get("local"):
        return (param[4:],)
    raise AssistError("servizio non valido")


def _act_keys_link(j, lang):
    services = _services_for(j.param)
    with _LOCK:
        _cand_cache["at"] = 0.0
    found = [c for c in _candidates() if c["service"] in services]
    done = []
    for sid in services:
        if providers.server_key(sid) and not links().get(sid):
            j.log(_L(lang, f"{providers.SERVICES[sid]['name']}: chiave gia' impostata (variabile d'ambiente).",
                     f"{providers.SERVICES[sid]['name']}: key already set (environment variable)."))
            continue
        cands = [c for c in found if c["service"] == sid]
        if not cands:
            continue
        c = cands[0]
        link(sid, c["source"], c["var"])
        done.append(sid)
        j.log(_L(lang, f"{providers.SERVICES[sid]['name']}: chiave collegata da {source_label(c['source'], lang)} "
                       f"({c['var']}).", f"{providers.SERVICES[sid]['name']}: key linked from "
                                         f"{source_label(c['source'], lang)} ({c['var']})."))
    for c in unsupported_keys():
        j.log(_L(lang, f"Trovata una chiave per {c['service'][1:]} ({source_label(c['source'], lang)}): regione non "
                       "ancora supportata da Germano, non collegata.",
                 f"Found a key for {c['service'][1:]} ({source_label(c['source'], lang)}): region not supported by "
                 "Germano yet, not linked."))
    j.result = {"linked": done}
    if done:
        j.message = _L(lang, "Configurazione recuperata: " + ", ".join(providers.SERVICES[s]["name"] for s in done)
                       + " ora si puo' scegliere nell'elenco dei modelli. La chiave resta dov'era: Germano la legge "
                         "solo al momento dell'uso.",
                       "Configuration retrieved: " + ", ".join(providers.SERVICES[s]["name"] for s in done)
                       + " can now be chosen in the model list. The key stays where it was: Germano reads it only "
                         "when it is used.")
    else:
        j.message = _L(lang, "Nessuna nuova chiave da collegare su questo computer.",
                       "No new key to link on this computer.")


def _act_key_unlink(j, lang):
    sid = j.param
    if not providers.get(sid):
        raise AssistError("servizio non valido")
    unlink(sid)
    j.message = _L(lang, f"Collegamento tolto: {providers.SERVICES[sid]['name']} non usa piu' la chiave trovata.",
                   f"Link removed: {providers.SERVICES[sid]['name']} no longer uses the found key.")


def _act_qwen_install(j, lang):
    _offline(lang)
    npm, node_version = _node_tools()
    if npm:
        m = re.match(r"(\d+)", node_version or "")
        major = int(m.group(1)) if m else 0
        if major and major < 20:
            raise AssistError(_L(lang, f"Qwen Code richiede Node.js 22 o successivo (trovato {node_version}): "
                                       "aggiorna Node.js e riprova.",
                                 f"Qwen Code needs Node.js 22 or later (found {node_version}): update Node.js and "
                                 "retry."))
        j.log(f"npm install -g @qwen-code/qwen-code@latest (Node.js {node_version or '?'})")
        rc = _run_process(j, [npm, "install", "-g", "@qwen-code/qwen-code@latest"], timeout=900)
        if rc != 0:
            raise AssistError(_L(lang, f"Installazione non riuscita (npm, codice {rc}).",
                                 f"Installation failed (npm, code {rc})."))
    elif IS_MAC and shutil.which("brew"):
        rc = _run_process(j, [shutil.which("brew"), "install", "qwen-code"], timeout=1200)
        if rc != 0:
            raise AssistError(_L(lang, f"Installazione non riuscita (Homebrew, codice {rc}).",
                                 f"Installation failed (Homebrew, code {rc})."))
    else:
        raise AssistError(_L(lang, "Per installare Qwen Code serve Node.js 22 o successivo (nodejs.org): installalo e "
                                   "riprova.", "Installing Qwen Code needs Node.js 22 or later (nodejs.org): install "
                                               "it and retry."))
    j.message = _L(lang, "Qwen Code installata: avviala una volta con «qwen» per scegliere l'accesso, poi usa "
                         "«Recupera configurazione».",
                   "Qwen Code installed: start it once with «qwen» to choose the sign-in, then use «Retrieve "
                   "configuration».")


def _act_ollama_install(j, lang):
    _offline(lang)
    if not IS_WIN:
        raise AssistError(_L(lang, "Su questo sistema installa Ollama dalla pagina ufficiale (ollama.com/download).",
                             "On this system install Ollama from the official page (ollama.com/download)."))
    if _tool(_tools(), "ollama").get("detected"):
        j.message = _L(lang, "Ollama e' gia' installato.", "Ollama is already installed.")
        return
    work = os.path.join(common.STATE_DIR, "tmp")
    os.makedirs(work, exist_ok=True)
    setup = os.path.join(work, "OllamaSetup.germano.exe")
    _download(j, OLLAMA_SETUP, setup, OLLAMA_HOSTS, OLLAMA_MAX_BYTES, lang)
    try:
        _require_signature(j, setup, OLLAMA_SIGNER, lang)
        j.progress = None
        marker_dir = os.path.join(os.environ.get("LOCALAPPDATA") or "", "Ollama")
        try:   # come lo script ufficiale: l'app si avvia nascosta dopo l'installazione
            os.makedirs(marker_dir, exist_ok=True)
            open(os.path.join(marker_dir, "upgraded"), "a").close()
        except OSError:
            pass
        j.log(_L(lang, "Installazione silenziosa per questo utente…", "Silent installation for this user…"))
        rc = _run_process(j, [setup, "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"], timeout=1800)
        if rc != 0:
            raise AssistError(_L(lang, f"L'installatore di Ollama ha restituito il codice {rc}.",
                                 f"The Ollama installer returned code {rc}."))
    finally:
        try:
            os.remove(setup)
        except OSError:
            pass
    if _wait_port(j, OLLAMA_PORT, 60):
        j.message = _L(lang, "Ollama installato e in esecuzione: scarica un modello consigliato.",
                       "Ollama installed and running: download a recommended model.")
    else:
        j.message = _L(lang, "Ollama installato: avvialo con «Avvia Ollama».", "Ollama installed: start it with «Start "
                                                                               "Ollama».")


def _act_ollama_start(j, lang):
    from . import ai_detect
    if ai_detect._port_open(OLLAMA_PORT, timeout=0.3):
        j.message = _L(lang, "Ollama e' gia' in esecuzione.", "Ollama is already running.")
        return
    t = _tool(_tools(), "ollama")
    path = t.get("path") if t.get("detected") else None
    if not path:
        raise AssistError(_L(lang, "Ollama non e' installato.", "Ollama is not installed."))
    if IS_MAC and path.endswith(".app"):
        _launch_detached(["/usr/bin/open", "-a", path])
    elif IS_WIN and os.path.isfile(os.path.join(os.path.dirname(path), "ollama app.exe")):
        app = os.path.join(os.path.dirname(path), "ollama app.exe")
        _launch_detached([app], cwd=os.path.dirname(app))
    else:
        exe = path if os.path.isfile(path) else shutil.which("ollama")
        if not exe:
            raise AssistError(_L(lang, "Eseguibile di Ollama non trovato.", "Ollama executable not found."))
        _launch_detached([exe, "serve"], cwd=os.path.dirname(exe))
    j.log(_L(lang, "Avvio di Ollama…", "Starting Ollama…"))
    if not _wait_port(j, OLLAMA_PORT, 45):
        raise AssistError(_L(lang, "Ollama non risponde sulla porta 11434 dopo 45 secondi.",
                             "Ollama does not answer on port 11434 after 45 seconds."))
    j.message = _L(lang, "Ollama in esecuzione: i suoi modelli compaiono nell'elenco.",
                   "Ollama running: its models appear in the list.")


def _act_ollama_pull(j, lang):
    import requests
    _offline(lang)
    name = j.param
    if not OLLAMA_NAME_RE.match(name or "") or ".." in name:
        raise AssistError(_L(lang, "Nome del modello non valido.", "Invalid model name."))
    from . import ai_detect
    if not ai_detect._port_open(OLLAMA_PORT, timeout=0.3):
        _act_ollama_start(j, lang)
        j.message = ""
    s = requests.Session()
    s.trust_env = False
    j.log(_L(lang, f"Download di {name} da registry.ollama.ai (tramite Ollama)…",
             f"Downloading {name} from registry.ollama.ai (through Ollama)…"))
    try:
        with s.post(f"http://127.0.0.1:{OLLAMA_PORT}/api/pull", json={"model": name, "stream": True},
                    stream=True, timeout=(10, 600)) as r:
            if r.status_code != 200:
                raise AssistError(_L(lang, f"Ollama ha risposto {r.status_code}.", f"Ollama answered {r.status_code}."))
            last_status = None
            for line in r.iter_lines():
                if j.cancel.is_set():
                    raise _Cancelled()
                if not line:
                    continue
                try:
                    ev = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if ev.get("error"):
                    raise AssistError(_L(lang, f"Ollama: {str(ev['error'])[:300]}", f"Ollama: {str(ev['error'])[:300]}"))
                st = str(ev.get("status") or "")
                if ev.get("total") and ev.get("completed") is not None:
                    j.progress = round(min(0.99, float(ev["completed"]) / float(ev["total"])), 3)
                if st and st != last_status:
                    j.log(st[:200])
                last_status = st
                if st == "success":
                    break
    except requests.RequestException as e:
        raise AssistError(_L(lang, f"Ollama non raggiungibile ({e.__class__.__name__}).",
                             f"Ollama not reachable ({e.__class__.__name__}).")) from None
    j.progress = None
    j.result = {"model": name}
    j.message = _L(lang, f"Modello {name} pronto: lo trovi nell'elenco dei modelli locali.",
                   f"Model {name} ready: you find it in the list of local models.")


def _act_lmstudio_start(j, lang):
    tools = _tools()
    lms = _lms_path(tools)
    if lms:
        rc = _run_process(j, [lms, "server", "start"], timeout=120)
        if rc != 0:
            raise AssistError(_L(lang, f"«lms server start» ha restituito il codice {rc}.",
                                 f"«lms server start» returned code {rc}."))
    else:
        t = _tool(tools, "lm-studio")
        if not t.get("detected") or not t.get("path"):
            raise AssistError(_L(lang, "LM Studio non e' installato.", "LM Studio is not installed."))
        if IS_MAC:
            _launch_detached(["/usr/bin/open", t["path"]])
        else:
            _launch_detached([t["path"]], cwd=os.path.dirname(t["path"]))
        j.log(_L(lang, "LM Studio aperto: attiva «Start server» nella scheda Developer.",
                 "LM Studio opened: turn on «Start server» in the Developer tab."))
    if _wait_port(j, 1234, 40):
        j.message = _L(lang, "Server di LM Studio in esecuzione: i modelli scaricati compaiono nell'elenco.",
                       "LM Studio server running: the downloaded models appear in the list.")
    else:
        j.message = _L(lang, "LM Studio non risponde ancora sulla porta 1234: attiva il server nell'app.",
                       "LM Studio does not answer on port 1234 yet: turn on the server in the app.")


def _act_jan_start(j, lang):
    t = _tool(_tools(), "jan")
    if not t.get("detected") or not t.get("path") or t.get("via") == "port":
        raise AssistError(_L(lang, "Jan non e' installato.", "Jan is not installed."))
    if IS_MAC:
        _launch_detached(["/usr/bin/open", t["path"]])
    else:
        _launch_detached([t["path"]], cwd=os.path.dirname(t["path"]))
    if _wait_port(j, 1337, 30):
        j.message = _L(lang, "Jan in esecuzione: i suoi modelli compaiono nell'elenco.",
                       "Jan running: its models appear in the list.")
    else:
        j.message = _L(lang, "Jan aperto: attiva «Local API Server» nelle impostazioni di Jan (porta 1337).",
                       "Jan opened: turn on «Local API Server» in Jan's settings (port 1337).")


# azione -> (voce dell'assistente, funzione, controllo del parametro, titolo it, titolo en)
ACTIONS = {
    "agy-install": ("antigravity", _act_agy_install, None, "Installazione di Antigravity CLI", "Installing Antigravity CLI"),
    "agy-check": ("antigravity", _act_agy_check, None, "Verifica dell'accesso", "Sign-in check"),
    "agy-login": ("antigravity", _act_agy_login, None, "Accesso con Google", "Google sign-in"),
    "agy-update": ("antigravity", _act_agy_update, None, "Aggiornamento di Antigravity CLI", "Updating Antigravity CLI"),
    "antigravity-open": ("antigravity", _act_antigravity_open, None, "Apertura di Antigravity", "Opening Antigravity"),
    "keys-link": (None, _act_keys_link, re.compile(r"^(qwen|glm|key:[a-z][a-z0-9-]{1,31})$"),
                  "Recupero della configurazione", "Retrieving the configuration"),
    "key-unlink": (None, _act_key_unlink, re.compile(r"^[a-z][a-z0-9-]{1,31}$"), "Scollegamento della chiave",
                   "Unlinking the key"),
    "qwen-install": ("qwen", _act_qwen_install, None, "Installazione di Qwen Code", "Installing Qwen Code"),
    "ollama-install": ("ollama", _act_ollama_install, None, "Installazione di Ollama", "Installing Ollama"),
    "ollama-start": ("ollama", _act_ollama_start, None, "Avvio di Ollama", "Starting Ollama"),
    "ollama-pull": ("ollama", _act_ollama_pull, OLLAMA_NAME_RE, "Download del modello", "Downloading the model"),
    "lmstudio-start": ("lm-studio", _act_lmstudio_start, None, "Avvio di LM Studio", "Starting LM Studio"),
    "jan-start": ("jan", _act_jan_start, None, "Avvio di Jan", "Starting Jan"),
}


def start(action, param, lang="it"):
    """Avvia un'azione in background: restituisce il lavoro (uno solo alla volta per la stessa azione)."""
    spec = ACTIONS.get(str(action or ""))
    if not spec:
        raise AssistError("azione sconosciuta")
    assist_id, fn, check, it, en = spec
    param = str(param or "").strip()[:100]
    if check is not None and not check.match(param):
        raise AssistError(_L(lang, "Parametro non valido.", "Invalid parameter."))
    if check is None:
        param = ""
    if action == "keys-link":
        assist_id = param                         # «qwen», «glm» oppure «key:<servizio>»
    elif action == "key-unlink":
        assist_id = next((a for a, svcs in ASSIST_SERVICES.items() if param in svcs), "key:" + param)
    with _LOCK:
        for j in JOBS.values():
            if j.state == "running" and j.action == action:
                return j
        if len([j for j in JOBS.values() if j.state == "running"]) >= 3:
            raise AssistError(_L(lang, "Ci sono gia' altre operazioni in corso: attendi che finiscano.",
                                 "Other operations are already running: wait for them to finish."))
        j = Job(action, param, assist_id, _L(lang, it, en))
        JOBS[j.id] = j
        old = sorted((x for x in JOBS.values() if x.state != "running"), key=lambda x: x.started)
        for x in old[:-20]:
            JOBS.pop(x.id, None)
    common.log(f"Assistente AI: avvio {action}")
    _spawn(j, fn, lang)
    return j


# ------------------------------------------------------------------------------------------------ stato per le pagine
_tools_cache = {"at": 0.0, "tools": []}


def _tools():
    """Rilevamento fresco (le azioni lo chiedono dopo installazioni e avvii)."""
    from . import ai_detect
    with _LOCK:
        if time.time() - _tools_cache["at"] < 2.0:
            return _tools_cache["tools"]
    tools = ai_detect.detect()["tools"]
    with _LOCK:
        _tools_cache.update(at=time.time(), tools=tools)
    return tools


def _fact(ok, text):
    return {"ok": ok, "text": text}


def _action(aid, label, primary=False, confirm=None, note=None, param=None, choices=None):
    out = {"id": aid, "label": label, "primary": bool(primary)}
    if confirm:
        out["confirm"] = confirm
    if note:
        out["note"] = note
    if param is not None:
        out["param"] = param
    if choices:
        out["choices"] = choices
    return out


def _job_for(assist_id):
    with _LOCK:
        cands = [j for j in JOBS.values() if j.assist == assist_id]
    if not cands:
        return None
    j = max(cands, key=lambda x: x.started)
    return j.view() if (j.state == "running" or time.time() - (j.ended or 0) < 600) else None


def _service_facts(services, lang, facts, actions, assist_id):
    """Fatti sulle chiavi dei servizi della voce; restituisce quanti servizi hanno gia' una chiave attiva."""
    keys = found_keys(lang)
    lk = links()
    linkable = False
    active = 0
    for sid in services:
        spec = providers.SERVICES[sid]
        origin = key_origin(sid, lang)
        if origin:
            active += 1
            facts.append(_fact(True, _L(lang, f"{spec['name']}: chiave attiva ({origin})",
                                        f"{spec['name']}: key active ({origin})")))
            if sid in lk:
                actions.append(_action("key-unlink", _L(lang, f"Scollega {spec['name']}", f"Unlink {spec['name']}"),
                                       param=sid))
        elif keys.get(sid):
            k = keys[sid][0]
            facts.append(_fact(None, _L(lang, f"{spec['name']}: chiave trovata in {k['label']} ({k['var']})",
                                        f"{spec['name']}: key found in {k['label']} ({k['var']})")))
            linkable = True
        else:
            facts.append(_fact(False, _L(lang, f"{spec['name']}: nessuna chiave su questo computer",
                                         f"{spec['name']}: no key on this computer")))
    for c in unsupported_keys():
        facts.append(_fact(None, _L(lang, f"Chiave per {c['service'][1:]} in {source_label(c['source'], lang)}: regione "
                                          "non ancora supportata", f"Key for {c['service'][1:]} in "
                                                                   f"{source_label(c['source'], lang)}: region not "
                                                                   "supported yet")))
    if linkable:
        actions.insert(0, _action("keys-link", _L(lang, "Recupera configurazione", "Retrieve configuration"),
                                  primary=True, param=assist_id,
                                  note=_L(lang, "Germano collega la chiave gia' configurata (senza copiarla) e la usa "
                                                "solo da questo computer.",
                                          "Germano links the key already configured (without copying it) and uses it "
                                          "only from this computer.")))
    return active


def describe(assist_id, lang="it"):
    """Scheda dell'assistente per una voce: fatti, azioni, collegamenti utili e lavoro in corso."""
    tools = _tools()
    facts, actions, links_out = [], [], []
    item = {"id": assist_id}
    if assist_id == "antigravity":
        desk = antigravity_desktop(tools)
        ide = _tool(tools, "antigravity-ide")
        path = agy_path(tools)
        login = shared_login()
        st = agy_status(path) if path else {"models": None, "error": None, "checked": False, "version": None}
        item.update(name="Google Antigravity", vendor="Google")
        if desk["installed"]:
            facts.append(_fact(True, "Antigravity Desktop" + (f" {desk['version']}" if desk["version"] else "")
                               + _L(lang, " installata", " installed")))
        else:
            facts.append(_fact(False, _L(lang, "Antigravity Desktop non installata", "Antigravity Desktop not installed")))
        if ide.get("detected"):
            facts.append(_fact(True, "Antigravity IDE" + _L(lang, " installato", " installed")))
        if desk["account"]:
            facts.append(_fact(True, _L(lang, f"Account dell'ultimo accesso: {desk['account']}",
                                        f"Account of the last sign-in: {desk['account']}")))
        if login is True:
            facts.append(_fact(True, _L(lang, "Accesso condiviso nel portachiavi del sistema (la CLI lo usa da sola, "
                                              "Germano non legge i token)",
                                        "Shared sign-in in the system keychain (the CLI uses it by itself, Germano "
                                        "does not read the tokens)")))
        elif login is False:
            facts.append(_fact(False, _L(lang, "Nessun accesso condiviso: accedi in Antigravity Desktop o con la CLI",
                                         "No shared sign-in: sign in in Antigravity Desktop or with the CLI")))
        if path:
            facts.append(_fact(True, _L(lang, "Antigravity CLI (agy)", "Antigravity CLI (agy)")
                               + (f" {st['version']}" if st.get("version") else "") + f" · {_short_path(path)}"))
            if st["models"]:
                facts.append(_fact(True, _L(lang, f"Accesso valido: {len(st['models'])} modelli (es. "
                                                  f"{', '.join(m['id'] for m in st['models'][:3])})",
                                            f"Sign-in valid: {len(st['models'])} models (e.g. "
                                            f"{', '.join(m['id'] for m in st['models'][:3])})")))
                item["status"] = "ready"
                item["summary"] = _L(lang, "Pronta nell'elenco dei modelli come «Antigravity CLI (agy)».",
                                     "Ready in the model list as «Antigravity CLI (agy)».")
                actions.append(_action("agy-check", _L(lang, "Verifica accesso", "Check sign-in")))
                actions.append(_action("agy-update", _L(lang, "Aggiorna la CLI", "Update the CLI")))
            elif st.get("busy") or not st["checked"]:
                facts.append(_fact(None, _L(lang, "Verifica dell'accesso in corso…", "Checking the sign-in…")))
                item["status"] = "action"
                item["summary"] = _L(lang, "Verifica dell'accesso in corso.", "Checking the sign-in.")
                actions.append(_action("agy-check", _L(lang, "Verifica accesso", "Check sign-in"), primary=True))
            else:
                facts.append(_fact(False, _L(lang, f"La CLI non riesce ad accedere: {st['error'] or '?'}",
                                             f"The CLI cannot sign in: {st['error'] or '?'}")))
                item["status"] = "action"
                item["summary"] = _L(lang, "Serve l'accesso con Google.", "Google sign-in needed.")
                actions.append(_action("agy-login", _L(lang, "Accedi con Google", "Sign in with Google"), primary=True,
                                       note=_L(lang, "Si apre la finestra della CLI: l'accesso avviene nel browser, "
                                                     "con l'account che scegli.",
                                               "The CLI window opens: sign-in happens in the browser, with the account "
                                               "you choose.")))
                actions.append(_action("agy-check", _L(lang, "Verifica accesso", "Check sign-in")))
        else:
            facts.append(_fact(False, _L(lang, "Antigravity CLI (agy) non installata", "Antigravity CLI (agy) not installed")))
            item["status"] = "action"
            item["summary"] = _L(lang, "Installa la CLI per usare Antigravity nell'Harness con lo stesso account.",
                                 "Install the CLI to use Antigravity in the Harness with the same account.")
            actions.append(_action(
                "agy-install", _L(lang, "Installa e configura Antigravity CLI", "Install and set up Antigravity CLI"),
                primary=True,
                confirm=_L(lang, "Germano scarica la CLI ufficiale di Google (circa 230 MB) dal manifesto di "
                                 "antigravity.google, ne verifica impronta SHA-512 e firma digitale e la installa per "
                                 f"questo utente in {_short_path(agy_target_path())}. Procedere?",
                           "Germano downloads Google's official CLI (about 230 MB) from the antigravity.google manifest, "
                           "verifies its SHA-512 digest and digital signature and installs it for this user in "
                           f"{_short_path(agy_target_path())}. Proceed?"),
                note=_L(lang, "Se Antigravity Desktop ha gia' un accesso, la CLI usa lo stesso account senza chiedere "
                              "nulla." if login else "Dopo l'installazione potrai accedere con Google.",
                        "If Antigravity Desktop is already signed in, the CLI uses the same account without asking "
                        "anything." if login else "After the installation you can sign in with Google.")))
        if desk["installed"] and not desk["account"] and login is False:
            actions.append(_action("antigravity-open", _L(lang, "Apri Antigravity Desktop", "Open Antigravity Desktop")))
        facts.append(_fact(None, _L(lang, "Nell'Harness la CLI riceve solo il testo gia' protetto da Germano, senza "
                                          "strumenti, file o comandi; le sue istruzioni interne vanno a Google "
                                          "direttamente (non passano dal Proxy).",
                                    "In the Harness the CLI receives only the text already protected by Germano, with no "
                                    "tools, files or commands; its internal instructions go to Google directly (not "
                                    "through the Proxy).")))
        links_out += [{"label": _L(lang, "Guida della CLI", "CLI guide"), "url": LINKS["agy_docs"]},
                      {"label": _L(lang, "Installazione e accesso", "Installation and sign-in"),
                       "url": LINKS["agy_install"]}]
    elif assist_id == "qwen":
        item.update(name="Qwen (Alibaba Cloud)", vendor="Alibaba")
        cli = _tool(tools, "qwen")
        settings = _read_json(os.path.join(_home(), ".qwen", "settings.json")) or {}
        auth = ((settings.get("security") or {}).get("auth") or {}).get("selectedType") \
            if isinstance(settings.get("security"), dict) else None
        if cli.get("detected"):
            facts.append(_fact(True, _L(lang, "Qwen Code installata", "Qwen Code installed")
                               + (f" · {_L(lang, 'accesso', 'sign-in')}: {auth}" if auth else "")))
        else:
            facts.append(_fact(False, _L(lang, "Qwen Code (CLI) non installata", "Qwen Code (CLI) not installed")))
        active = _service_facts(ASSIST_SERVICES["qwen"], lang, facts, actions, "qwen")
        facts.append(_fact(None, _L(lang, "Qwen4-Max (qwen4-max-preview) e' in anteprima fino al 25/11/2026 e solo con "
                                          "il Token Plan; a consumo il modello Max e' qwen3.8-max.",
                                    "Qwen4-Max (qwen4-max-preview) is in preview until 25/11/2026 and only with the "
                                    "Token Plan; pay-as-you-go the Max model is qwen3.8-max.")))
        if auth == "qwen-oauth":
            facts.append(_fact(None, _L(lang, "L'accesso Qwen OAuth di Qwen Code vale solo per la CLI: per Germano "
                                              "serve una chiave di Model Studio.",
                                        "Qwen Code's Qwen OAuth sign-in works only for the CLI: Germano needs a Model "
                                        "Studio key.")))
        if not cli.get("detected"):
            npm, node_version = _node_tools()
            actions.append(_action("qwen-install", _L(lang, "Installa Qwen Code", "Install Qwen Code"),
                                   confirm=_L(lang, "Germano esegue «npm install -g @qwen-code/qwen-code@latest» "
                                                    "(pacchetto ufficiale). Procedere?",
                                              "Germano runs «npm install -g @qwen-code/qwen-code@latest» (official "
                                              "package). Proceed?"),
                                   note=(f"Node.js {node_version}" if npm else
                                         _L(lang, "Serve Node.js 22 o successivo.", "Node.js 22 or later is needed."))))
        item["status"] = "ready" if active else "action"
        item["summary"] = _L(lang, "Chiavi di Model Studio (a consumo, Token Plan, Coding Plan) e Qwen Code.",
                             "Model Studio keys (pay-as-you-go, Token Plan, Coding Plan) and Qwen Code.")
        links_out += [{"label": _L(lang, "Chiave API di Model Studio", "Model Studio API key"), "url": LINKS["qwen_keys"]},
                      {"label": "Qwen4-Max-Preview", "url": LINKS["qwen_models"]},
                      {"label": "Qwen Code", "url": LINKS["qwen_code"]}]
        if not cli.get("detected") and not _node_tools()[0]:
            links_out.append({"label": "Node.js", "url": LINKS["node_download"]})
    elif assist_id == "glm":
        item.update(name="GLM (Z.ai)", vendor="Zhipu AI / Z.ai")
        active = _service_facts(ASSIST_SERVICES["glm"], lang, facts, actions, "glm")
        facts.append(_fact(None, _L(lang, "Modello GLM-5.3: «glm-5.3». Le chiavi del Coding Plan valgono solo con il "
                                          "servizio «GLM Coding Plan».",
                                    "GLM-5.3 model: «glm-5.3». Coding Plan keys work only with the «GLM Coding Plan» "
                                    "service.")))
        item["status"] = "ready" if active else "action"
        item["summary"] = _L(lang, "Chiavi di Z.ai (API generale e GLM Coding Plan).",
                             "Z.ai keys (general API and GLM Coding Plan).")
        links_out.append({"label": "GLM-5.3 (docs.z.ai)", "url": LINKS["glm_docs"]})
    elif assist_id.startswith("key:"):
        sid = assist_id[4:]
        spec = providers.get(sid)
        if not spec or spec.get("local"):
            raise AssistError("servizio non valido")
        item.update(name=spec["name"], vendor=spec["name"])
        _service_facts((sid,), lang, facts, actions, assist_id)
        item["status"] = "ready" if key_origin(sid, lang) else "action"
        item["summary"] = _L(lang, "Chiave del servizio trovata su questo computer.",
                             "Service key found on this computer.")
    elif assist_id == "ollama":
        from . import ai_detect
        item.update(name="Ollama", vendor="Ollama")
        t = _tool(tools, "ollama")
        up = ai_detect._port_open(OLLAMA_PORT, timeout=0.3)
        disk = disk_models("ollama", max_age=5)
        served = [m for m in (t.get("models") or []) if isinstance(m, str)] if up else []
        have = served if up else disk   # acceso: i modelli che offre il server; spento: quelli gia' sul disco
        installed = bool(t.get("detected") and t.get("via") != "port")
        facts.append(_fact(installed or up, _L(lang, "Ollama installato", "Ollama installed") if installed or up else
                           _L(lang, "Ollama non installato", "Ollama not installed")))
        facts.append(_fact(up, _L(lang, "In esecuzione (porta 11434)", "Running (port 11434)") if up else
                           _L(lang, "Non in esecuzione", "Not running")))
        facts.append(_fact(bool(have), (_L(lang, f"Modelli disponibili: {len(have)}", f"Models available: {len(have)}")
                                        if up else _L(lang, f"Modelli gia' scaricati: {len(have)}",
                                                      f"Models already downloaded: {len(have)}"))
                           + (f" ({', '.join(have[:4])}{'…' if len(have) > 4 else ''})" if have else "")))
        disk = sorted(set(disk) | set(served))
        if not installed and not up:
            if IS_WIN:
                actions.append(_action("ollama-install", _L(lang, "Installa Ollama", "Install Ollama"), primary=True,
                                       confirm=_L(lang, "Germano scarica l'installer ufficiale da ollama.com (oltre 1 GB), "
                                                        "ne verifica la firma digitale «Ollama Inc.» e lo installa per "
                                                        "questo utente, senza finestre. Procedere?",
                                                  "Germano downloads the official installer from ollama.com (over 1 GB), "
                                                  "verifies its «Ollama Inc.» digital signature and installs it for this "
                                                  "user, without windows. Proceed?")))
            links_out.append({"label": _L(lang, "Scarica Ollama", "Download Ollama"), "url": LINKS["ollama_download"]})
        elif not up:
            actions.append(_action("ollama-start", _L(lang, "Avvia Ollama", "Start Ollama"), primary=True))
        choices = [{"value": m, "label": f"{label} · {_L(lang, it, en)}"} for m, label, it, en in OLLAMA_RECOMMENDED
                   if m not in disk]
        if (installed or up) and choices:
            actions.append(_action("ollama-pull", _L(lang, "Scarica modello consigliato", "Download a recommended model"),
                                   primary=up and not disk, choices=choices,
                                   note=_L(lang, "Il modello resta su questo computer: nessun dato esce in rete quando lo "
                                                 "usi.", "The model stays on this computer: no data leaves the network "
                                                         "when you use it.")))
        item["status"] = "ready" if up and disk else "action"
        item["summary"] = _L(lang, "Modelli locali: nessun dato esce da questo computer.",
                             "Local models: no data leaves this computer.")
        links_out.append({"label": _L(lang, "Catalogo dei modelli", "Model library"), "url": LINKS["ollama_library"]})
    elif assist_id == "lm-studio":
        from . import ai_detect
        item.update(name="LM Studio", vendor="LM Studio")
        t = _tool(tools, "lm-studio")
        up = ai_detect._port_open(1234, timeout=0.3)
        disk = disk_models("lm-studio", max_age=5)
        installed = bool(t.get("detected") and t.get("via") != "port") or bool(_lms_path(tools))
        facts.append(_fact(installed or up, _L(lang, "LM Studio installato", "LM Studio installed") if installed or up
                           else _L(lang, "LM Studio non installato", "LM Studio not installed")))
        facts.append(_fact(up, _L(lang, "Server in esecuzione (porta 1234)", "Server running (port 1234)") if up else
                           _L(lang, "Server non in esecuzione", "Server not running")))
        facts.append(_fact(bool(disk), _L(lang, f"Modelli scaricati: {len(disk)}", f"Downloaded models: {len(disk)}")
                           + (f" ({', '.join(disk[:3])}{'…' if len(disk) > 3 else ''})" if disk else "")))
        if installed and not up:
            actions.append(_action("lmstudio-start", _L(lang, "Avvia server locale", "Start local server"), primary=True,
                                   note=None if _lms_path(tools) else _L(lang, "Si apre LM Studio: attiva il server "
                                                                               "nella scheda Developer.",
                                                                         "LM Studio opens: turn on the server in the "
                                                                         "Developer tab.")))
        if not installed and not up:
            links_out.append({"label": _L(lang, "Scarica LM Studio", "Download LM Studio"),
                              "url": LINKS["lmstudio_download"]})
        item["status"] = "ready" if up else "action"
        item["summary"] = _L(lang, "Modelli locali di LM Studio (compatibili OpenAI).",
                             "LM Studio local models (OpenAI compatible).")
    elif assist_id == "jan":
        from . import ai_detect
        item.update(name="Jan", vendor="Menlo Research")
        t = _tool(tools, "jan")
        up = ai_detect._port_open(1337, timeout=0.3)
        disk = disk_models("jan", max_age=5)
        installed = bool(t.get("detected") and t.get("via") != "port")
        facts.append(_fact(installed or up, _L(lang, "Jan installato", "Jan installed") if installed or up else
                           _L(lang, "Jan non installato", "Jan not installed")))
        facts.append(_fact(up, _L(lang, "Local API Server attivo (porta 1337)", "Local API Server running (port 1337)")
                           if up else _L(lang, "Local API Server spento", "Local API Server off")))
        facts.append(_fact(bool(disk), _L(lang, f"Modelli scaricati: {len(disk)}", f"Downloaded models: {len(disk)}")))
        if installed and not up:
            actions.append(_action("jan-start", _L(lang, "Avvia Jan", "Start Jan"), primary=True,
                                   note=_L(lang, "Poi attiva «Local API Server» nelle impostazioni di Jan.",
                                           "Then turn on «Local API Server» in Jan's settings.")))
        if not installed and not up:
            links_out.append({"label": _L(lang, "Scarica Jan", "Download Jan"), "url": LINKS["jan_download"]})
        item["status"] = "ready" if up else "action"
        item["summary"] = _L(lang, "Modelli locali di Jan.", "Jan local models.")
    else:
        raise AssistError("voce sconosciuta")
    item.update(facts=facts, actions=actions, links=links_out, job=_job_for(assist_id))
    item.setdefault("status", "action")
    item.setdefault("summary", "")
    return item


ASSIST_IDS = ("antigravity", "qwen", "glm", "ollama", "lm-studio", "jan")


def overview(lang="it"):
    """Tutte le voci dell'assistente (Impostazioni > AI): le voci delle chiavi si aggiungono se c'e' qualcosa da
    collegare."""
    out = []
    for aid in ASSIST_IDS:
        try:
            out.append(describe(aid, lang))
        except Exception as e:
            out.append({"id": aid, "name": aid, "status": "action", "summary": scrub(str(e)), "facts": [],
                        "actions": [], "links": []})
    covered = {s for v in ASSIST_SERVICES.values() for s in v}
    for sid in sorted(found_keys(lang)):
        if sid not in covered:
            try:
                out.append(describe("key:" + sid, lang))
            except Exception:
                pass
    return out


def annotate(targets, tools, lang="it"):
    """Aggiunge alle destinazioni dell'Harness (solo per questo computer) il pulsante contestuale dell'assistente:
    assist = voce da aprire, assist_label = testo del pulsante, e i modelli gia' scaricati sul disco."""
    L = (lambda it, en: en if lang == "en" else it)
    keys = found_keys(lang)
    agy = agy_path(tools)
    agy_st = agy_status(agy) if agy else None
    by_tool = {t.get("id"): t for t in tools or []}
    for t in targets:
        tid, kind = t.get("id", ""), t.get("kind")
        if tid in ("other:antigravity", "other:antigravity-ide", "cli:agy"):
            t["assist"] = "antigravity"
            if not agy:
                t["assist_label"] = L("Installa CLI", "Install CLI")
                if tid == "cli:agy":
                    t["reason"] = L("non installata: usa «Installa CLI»", "not installed: use «Install CLI»")
            elif agy_st and agy_st["checked"] and not agy_st["models"]:
                t["assist_label"] = L("Accedi", "Sign in")
            else:
                t["assist_label"] = L("Configura", "Set up")
            if tid == "cli:agy" and agy_st and agy_st["models"]:
                t["models"] = [m["id"] for m in agy_st["models"]]
            if tid == "other:antigravity":
                t["reason"] = (L("app desktop: nell'Harness usa «Antigravity CLI (agy)», stesso account",
                                 "desktop app: in the Harness use «Antigravity CLI (agy)», same account") if agy else
                               L("app desktop: con «Installa CLI» la usi qui con lo stesso account",
                                 "desktop app: with «Install CLI» you use it here with the same account"))
        elif kind == "cloud":
            sid = t.get("service")
            family = next((a for a, svcs in ASSIST_SERVICES.items() if sid in svcs), None)
            usable_server = t.get("key") == "server"
            if keys.get(sid) and not usable_server:
                t["assist"] = family or "key:" + sid
                t["assist_label"] = L("Recupera chiave", "Retrieve key")
                short = SOURCE_SHORT.get(keys[sid][0]["source"], keys[sid][0]["label"])
                t["assist_hint"] = L(f"chiave trovata ({short})", f"key found ({short})")
            elif family and not usable_server:
                t["assist"] = family
                t["assist_label"] = L("Configura", "Set up")
            elif usable_server and links().get(sid):
                t["key_vars"] = [key_origin(sid, lang)]
        elif kind == "other" and tid == "other:qwen":
            t["assist"] = "qwen"
            t["assist_label"] = L("Configura", "Set up")
        elif kind == "local":
            svc = t.get("service")
            aid = {"ollama": "ollama", "lmstudio": "lm-studio", "jan": "jan"}.get(svc)
            if not aid:
                continue
            spec_tool = by_tool.get(aid) or {}
            installed = bool(spec_tool.get("detected") and spec_tool.get("via") != "port")
            if not t.get("enabled"):
                disk = disk_models(aid)
                t["assist"] = aid
                if t.get("reason") and disk:
                    t["reason"] = t["reason"] + L(f" · {len(disk)} modelli gia' scaricati",
                                                  f" · {len(disk)} models already downloaded")
                if aid == "ollama" and installed and str(t.get("reason") or "").startswith(L("nessun", "no")):
                    t["assist_label"] = L("Scarica modello", "Get a model")
                elif installed:
                    t["assist_label"] = L("Avvia", "Start")
                else:
                    t["assist_label"] = L("Installa", "Install")
    return targets
