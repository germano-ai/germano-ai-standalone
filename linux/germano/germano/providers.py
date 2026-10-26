"""Servizi di AI raggiungibili attraverso Germano (Proxy e chat del Remote Control).

Ogni servizio ha l'indirizzo ufficiale delle sue API in formato OpenAI (chat/completions) e, se esiste, in formato
Anthropic (messages). Il Proxy li usa con il prefisso /p/<servizio>/ (es. http://server:8181/p/deepseek/v1) e la chat
del Remote Control li chiama con il testo GIA' anonimizzato da Germano.

Chiave API: quella che l'utente inserisce nel Remote Control o nella propria CLI (mai salvata dal server). La chiave del
server (variabile d'ambiente del servizio) si usa per gli altri solo se l'amministratore condivide le AI di questo
computer (share_ai_tools), come per le CLI condivise.
Ollama e LM Studio sono modelli locali del server: nessuna chiave, nessun dato fuori dalla rete locale.
"""
import json
import os
import re

import requests

# id -> nome, indirizzi (openai, anthropic), variabili d'ambiente della chiave sul server, porta locale, modelli noti
SERVICES = {
    "openai": {"name": "OpenAI (ChatGPT, Codex)", "openai": "https://api.openai.com/v1",
               "keys": ("OPENAI_API_KEY",)},
    "anthropic": {"name": "Anthropic (Claude)", "anthropic": "https://api.anthropic.com/v1",
                  "keys": ("ANTHROPIC_API_KEY",)},
    "meta": {"name": "Meta Muse (Muse Wonder, Muse Spark)", "openai": "https://api.meta.ai/v1",
             "keys": ("MODEL_API_KEY", "META_API_KEY"), "models": ("muse-wonder-1.0", "muse-spark-1.3", "muse-spark-1.2")},
    "moonshot": {"name": "Kimi (Moonshot AI)", "openai": "https://api.moonshot.ai/v1",
                 "anthropic": "https://api.moonshot.ai/anthropic/v1", "keys": ("MOONSHOT_API_KEY", "KIMI_API_KEY")},
    "deepseek": {"name": "DeepSeek", "openai": "https://api.deepseek.com/v1",
                 "anthropic": "https://api.deepseek.com/anthropic/v1", "keys": ("DEEPSEEK_API_KEY",),
                 "models": ("deepseek-chat", "deepseek-reasoner")},
    "qwen": {"name": "Qwen (Alibaba Cloud Model Studio)", "openai": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
             "keys": ("DASHSCOPE_API_KEY", "QWEN_API_KEY")},
    "mistral": {"name": "Mistral (Mistral Large, Codestral)", "openai": "https://api.mistral.ai/v1",
                "keys": ("MISTRAL_API_KEY",)},
    "xai": {"name": "Grok (xAI)", "openai": "https://api.x.ai/v1", "keys": ("XAI_API_KEY", "GROK_API_KEY")},
    "perplexity": {"name": "Perplexity (Sonar)", "openai": "https://api.perplexity.ai",
                   "keys": ("PERPLEXITY_API_KEY", "PPLX_API_KEY"), "models": ("sonar", "sonar-pro")},
    "gemini": {"name": "Google Gemini", "openai": "https://generativelanguage.googleapis.com/v1beta/openai",
               "keys": ("GEMINI_API_KEY", "GOOGLE_API_KEY")},
    "openrouter": {"name": "OpenRouter (molti modelli)", "openai": "https://openrouter.ai/api/v1",
                   "keys": ("OPENROUTER_API_KEY",)},
    "groq": {"name": "Groq", "openai": "https://api.groq.com/openai/v1", "keys": ("GROQ_API_KEY",)},
    "ollama": {"name": "Ollama (modelli locali del server)", "openai": "http://127.0.0.1:11434/v1", "local": True,
               "port": 11434},
    "lmstudio": {"name": "LM Studio (modelli locali del server)", "openai": "http://127.0.0.1:1234/v1", "local": True,
                 "port": 1234},
}
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]{0,127}$")
KEY_RE = re.compile(r"^[\x21-\x7e]{8,512}$")       # caratteri stampabili, senza spazi
MAX_ANSWER = 400_000
TIMEOUT = (15, 600)

_http = requests.Session()
_http_local = requests.Session()
_http_local.trust_env = False      # i modelli locali (127.0.0.1) non passano mai da un proxy aziendale


class ServiceError(RuntimeError):
    status = 502


def get(service_id):
    return SERVICES.get(str(service_id or "").strip().lower())


def server_key(service_id):
    """Chiave API presente sul server per questo servizio (variabile d'ambiente), o ''."""
    spec = get(service_id) or {}
    for var in spec.get("keys", ()):
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    return ""


def describe(sharing, listening=None):
    """Servizi per il Remote Control: disponibilita' e provenienza della chiave (mai la chiave)."""
    listening = listening or {}
    out = []
    for sid, spec in SERVICES.items():
        item = {"id": sid, "name": spec["name"], "formats": [f for f in ("openai", "anthropic") if spec.get(f)],
                "models": list(spec.get("models", ())), "local": bool(spec.get("local"))}
        if spec.get("local"):
            up = bool(listening.get(spec.get("port")))
            item.update(available=up, key="none", reason=None if up else "non in esecuzione sul server")
        elif sharing and server_key(sid):
            item.update(available=True, key="server")
        else:
            item.update(available=True, key="user")
        out.append(item)
    return out


def _base(spec, fmt):
    return (spec.get(fmt) or "").rstrip("/")


def _clip(text):
    text = text or ""
    return text if len(text) <= MAX_ANSWER else text[:MAX_ANSWER] + "\n[... risposta troncata da Germano ...]"


def _error_text(r):
    try:
        data = r.json()
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            return str(err.get("message") or err)[:300]
        if err:
            return str(err)[:300]
        return json.dumps(data)[:300]
    except Exception:
        return (r.text or "")[:300]


def chat(service_id, model, messages, api_key="", max_tokens=4096):
    """Conversazione con il servizio (testo gia' anonimizzato). messages = [{"role": "user"|"assistant", "content"}].
    Restituisce il testo della risposta; solleva ServiceError con un messaggio comprensibile."""
    spec = get(service_id)
    if not spec:
        raise ServiceError("servizio sconosciuto")
    if not model or not MODEL_RE.match(model):
        raise ServiceError("indica il modello da usare (es. quello suggerito o uno dell'elenco del servizio)")
    if not spec.get("local") and not api_key:
        raise ServiceError("serve la chiave API del servizio")
    http = _http_local if spec.get("local") else _http
    if spec.get("openai"):
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body = {"model": model, "messages": messages, "stream": False}
        try:
            r = http.post(_base(spec, "openai") + "/chat/completions", json=body, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise ServiceError(f"{spec['name']} non raggiungibile ({e.__class__.__name__})") from None
        if r.status_code >= 400:
            raise ServiceError(f"{spec['name']} ha risposto con errore {r.status_code}: {_error_text(r)}")
        try:
            choice = r.json()["choices"][0]["message"]
            content = choice.get("content")
            if isinstance(content, list):   # alcuni servizi restituiscono parti di contenuto
                content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
            return _clip(str(content or ""))
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ServiceError(f"risposta di {spec['name']} non riconosciuta") from None
    # solo formato Anthropic
    headers = {"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"}
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [m for m in messages if m.get("role") in ("user", "assistant")]}
    if system:
        body["system"] = system
    try:
        r = http.post(_base(spec, "anthropic") + "/messages", json=body, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ServiceError(f"{spec['name']} non raggiungibile ({e.__class__.__name__})") from None
    if r.status_code >= 400:
        raise ServiceError(f"{spec['name']} ha risposto con errore {r.status_code}: {_error_text(r)}")
    try:
        return _clip("".join(p.get("text", "") for p in r.json()["content"] if p.get("type") == "text"))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ServiceError(f"risposta di {spec['name']} non riconosciuta") from None


def list_models(service_id, api_key=""):
    """Modelli offerti dal servizio (elenco /models: nessun dato personale)."""
    spec = get(service_id)
    if not spec:
        raise ServiceError("servizio sconosciuto")
    known = list(spec.get("models", ()))
    http = _http_local if spec.get("local") else _http
    fmt = "openai" if spec.get("openai") else "anthropic"
    headers = {}
    if api_key:
        headers = ({"Authorization": f"Bearer {api_key}"} if fmt == "openai"
                   else {"x-api-key": api_key, "anthropic-version": "2023-06-01"})
    elif not spec.get("local"):
        return known
    try:
        r = http.get(_base(spec, fmt) + "/models", headers=headers, timeout=(10, 30))
        if r.status_code >= 400:
            raise ServiceError(f"{spec['name']}: elenco dei modelli non disponibile (errore {r.status_code}: "
                               f"{_error_text(r)})")
        items = r.json().get("data") or []
        ids = [str(m.get("id")) for m in items if isinstance(m, dict) and m.get("id")]
    except requests.RequestException as e:
        raise ServiceError(f"{spec['name']} non raggiungibile ({e.__class__.__name__})") from None
    except (ValueError, AttributeError):
        raise ServiceError(f"elenco dei modelli di {spec['name']} non riconosciuto") from None
    return sorted(dict.fromkeys(ids + known))[:400]
