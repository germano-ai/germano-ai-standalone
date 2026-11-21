"""Servizi di AI raggiungibili attraverso Germano (Proxy e chat del Remote Control).

Ogni servizio ha l'indirizzo ufficiale delle sue API in formato OpenAI (chat/completions) e, se esiste, in formato
Anthropic (messages). Il Proxy li usa con il prefisso /p/<servizio>/ (es. http://server:8181/p/deepseek/v1) e la chat
del Remote Control li chiama con il testo GIA' anonimizzato da Germano.

Chiave API: quella che l'utente inserisce nel Remote Control o nella propria CLI (mai salvata dal server). La chiave del
server (variabile d'ambiente del servizio, oppure dal turno 28 la chiave di un altro strumento «collegata» con
l'assistente di configurazione, germano/ai_assist.py, che si legge al momento dell'uso senza copiarla) si usa per gli
altri solo se l'amministratore condivide le AI di questo computer (share_ai_tools), come per le CLI condivise.
Ollama e LM Studio sono modelli locali del server: nessuna chiave, nessun dato fuori dalla rete locale.

Modelli suggeriti verificati il 14/11/2026 sulla documentazione ufficiale: Qwen a consumo qwen3.8-max / qwen3.7-plus /
qwen3.8-flash; Qwen4-Max solo con il Token Plan (qwen4-max-preview, anteprima fino al 25/11/2026); GLM-5.3 di Z.ai
(glm-5.3) sull'API generale e sul GLM Coding Plan (chiavi diverse, indirizzi diversi).
"""
import json
import os
import re

import requests

# id -> nome, indirizzi (openai, anthropic), variabili d'ambiente della chiave sul server, porta locale, modelli noti
SERVICES = {
    "openai": {"name": "OpenAI (ChatGPT, Codex)", "openai": "https://api.openai.com/v1",
               "keys": ("OPENAI_API_KEY",),
               "models": ("gpt-5.4", "gpt-5.2", "gpt-5", "gpt-5-mini", "o3", "o4-mini", "gpt-4.1", "gpt-4o")},
    "anthropic": {"name": "Anthropic (Claude)", "anthropic": "https://api.anthropic.com/v1",
                  "keys": ("ANTHROPIC_API_KEY",),
                  "models": ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5",
                             "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5")},
    "meta": {"name": "Meta Muse (Muse Wonder, Muse Spark)", "openai": "https://api.meta.ai/v1",
             "keys": ("MODEL_API_KEY", "META_API_KEY"), "models": ("muse-wonder-1.0", "muse-spark-1.3", "muse-spark-1.2")},
    "moonshot": {"name": "Kimi (Moonshot AI)", "openai": "https://api.moonshot.ai/v1",
                 "anthropic": "https://api.moonshot.ai/anthropic/v1", "keys": ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
                 "models": ("kimi-k3.1-pro", "kimi-k3", "kimi-k2.5", "kimi-k2-thinking", "kimi-k2-turbo-preview")},
    "deepseek": {"name": "DeepSeek", "openai": "https://api.deepseek.com/v1",
                 "anthropic": "https://api.deepseek.ai/anthropic/v1", "keys": ("DEEPSEEK_API_KEY",),
                 "models": ("deepseek-reasoner", "deepseek-chat", "deepseek-v4-pro")},
    "qwen": {"name": "Qwen (Alibaba Cloud Model Studio)", "openai": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
             "anthropic": "https://dashscope-intl.aliyuncs.com/apps/anthropic/v1",
             "keys": ("DASHSCOPE_API_KEY", "QWEN_API_KEY"), "models": ("qwen3.8-max", "qwen3.7-plus", "qwen3.8-flash")},
    "qwen-token": {"name": "Qwen Token Plan (Qwen4-Max)",
                   "openai": "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
                   "anthropic": "https://token-plan.ap-southeast-1.maas.aliyuncs.com/apps/anthropic/v1",
                   "keys": ("QWEN_TOKEN_PLAN_API_KEY",), "models": ("qwen4-max-preview", "qwen3.8-max")},
    "qwen-coding": {"name": "Qwen Coding Plan", "openai": "https://coding-intl.dashscope.aliyuncs.com/v1",
                    "anthropic": "https://coding-intl.dashscope.aliyuncs.com/apps/anthropic/v1",
                    "keys": ("BAILIAN_CODING_PLAN_API_KEY",)},
    "zai": {"name": "GLM (Z.ai)", "openai": "https://api.z.ai/api/paas/v4", "anthropic": "https://api.z.ai/api/anthropic/v1",
            "keys": ("ZAI_API_KEY", "Z_AI_API_KEY", "GLM_API_KEY"), "models": ("glm-5.3",)},
    "zai-coding": {"name": "GLM Coding Plan (Z.ai)", "openai": "https://api.z.ai/api/coding/paas/v4",
                   "anthropic": "https://api.z.ai/api/anthropic/v1", "keys": ("ZAI_CODING_API_KEY",),
                   "models": ("glm-5.3",)},
    "mistral": {"name": "Mistral (Mistral Large, Codestral)", "openai": "https://api.mistral.ai/v1",
                "keys": ("MISTRAL_API_KEY",),
                "models": ("magistral-medium-latest", "magistral-small-latest", "mistral-large-latest", "codestral-latest")},
    "xai": {"name": "Grok (xAI)", "openai": "https://api.x.ai/v1", "keys": ("XAI_API_KEY", "GROK_API_KEY"),
            "models": ("grok-4.7", "grok-4.5", "grok-4", "grok-3", "grok-3-mini")},
    "perplexity": {"name": "Perplexity (Sonar)", "openai": "https://api.perplexity.ai",
                   "keys": ("PERPLEXITY_API_KEY", "PPLX_API_KEY"),
                   "models": ("sonar-pro", "sonar", "sonar-reasoning-pro", "sonar-deep-research")},
    "gemini": {"name": "Google Gemini", "openai": "https://generativelanguage.googleapis.com/v1beta/openai",
               "keys": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
               "models": ("gemini-4-neon", "gemini-4-hydrogen", "gemini-4-carbon", "gemini-3.8-flash",
                          "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash")},
    "openrouter": {"name": "OpenRouter (molti modelli)", "openai": "https://openrouter.ai/api/v1",
                   "keys": ("OPENROUTER_API_KEY",)},
    "groq": {"name": "Groq", "openai": "https://api.groq.com/openai/v1", "keys": ("GROQ_API_KEY",),
             "models": ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3-32b", "llama-3.3-70b-versatile")},
    "ollama": {"name": "Ollama (modelli locali del server)", "openai": "http://127.0.0.1:11434/v1", "local": True,
               "port": 11434},
    "lmstudio": {"name": "LM Studio (modelli locali del server)", "openai": "http://127.0.0.1:1234/v1", "local": True,
                 "port": 1234},
    "jan": {"name": "Jan (modelli locali del server)", "openai": "http://127.0.0.1:1337/v1", "local": True,
            "port": 1337},
}
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
# nomi dei modelli: anche quelli dei modelli locali (es. «qwen2.5-coder:7b-instruct-q4_K_M», «hf.co/utente/modello»)
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@\[\]+-]{0,127}$")
KEY_RE = re.compile(r"^[\x21-\x7e]{8,512}$")       # caratteri stampabili, senza spazi
MAX_ANSWER = 400_000
TIMEOUT = (15, 600)

_http = requests.Session()
_http_local = requests.Session()
_http_local.trust_env = False      # i modelli locali (127.0.0.1) non passano mai da un proxy aziendale


class ServiceError(RuntimeError):
    status = 502


class ParamsError(ValueError):
    """Parametri del servizio non validi (whitelist, range): il server risponde 400."""


class Interrupted(Exception):
    """Streaming interrotto dall'utente (Glass Window): la connessione e' stata chiusa di proposito."""


# Parametri relativi al modello scelto: ogni modello ha parametri e limiti reali diversi (es. OpenAI o3/o4-mini
# rifiutano temperature/top_p e usano max_completion_tokens; gpt-4o non ha reasoning_effort; Claude 4.7+/5.x
# rifiutano temperature != 1.0 e usano output_config.effort; Claude Haiku 4.5 non ha effort; GLM-5 rifiuta
# thinking=disabled; i modelli locali di ragionamento hanno reasoning_effort, gli altri no). Con fallback
# resiliente su HTTP 400 in chat/stream_chat per modelli personalizzati o nuovi non ancora mappati.
_PARAM_RANGES = {"temperature": (0.0, 2.0), "top_p": (0.0, 1.0), "max_tokens": (1, 128000),
                 "thinking_budget": (1024, 32000)}
_LOCAL_REASONING_HINTS = ("deepseek-r1", "qwq", "qwen3", "qwen4", "gpt-oss", "cogito", "phi4-reasoning",
                          "phi-4-reasoning", "magistral", "kimi-k2-thinking", "kimi-k3", "glm-4.5", "glm-4.6",
                          "glm-4.7", "glm-5", "-thinking", "-reasoning", "r1-")
_OR_PREFIX_SERVICE = {
    "openai": "openai", "anthropic": "anthropic", "google": "gemini", "deepseek": "deepseek",
    "qwen": "qwen", "x-ai": "xai", "z-ai": "zai", "thudm": "zai", "moonshotai": "moonshot",
    "mistralai": "mistral", "meta-llama": "meta", "meta": "meta", "perplexity": "perplexity",
}


def _prof(effort=None, effort_default=None, effort_wire="reasoning_effort", thinking=None, enable_thinking=False,
          temp_max=2.0, top_p=True, sampling_show_if=None, sampling_hide_if=None, max_tokens_ui=(256, 32768),
          max_tokens_wire="max_tokens"):
    return {
        "effort": tuple(effort) if effort else None,
        "effort_default": effort_default,
        "effort_wire": effort_wire if effort else None,
        "thinking": thinking,                 # None | "anthropic" | "toggle"
        "enable_thinking": bool(enable_thinking),
        "temp_max": temp_max,                 # None = vietata/non supportata dal modello
        "top_p": bool(top_p),
        "sampling_show_if": sampling_show_if,
        "sampling_hide_if": sampling_hide_if,
        "max_tokens_ui": max_tokens_ui,
        "max_tokens_wire": max_tokens_wire,
    }


def _model_profile(service_id, model=None):
    """Profilo di capacita' reale per (servizio, modello): determina quali parametri mostrare nel selettore e come
    serializzarli nel payload HTTP."""
    sid = str(service_id or "").strip().lower()
    spec = get(sid) or {}
    m_raw = str(model or "").strip()
    if not m_raw and spec.get("models"):
        m_raw = spec["models"][0]
    ml = m_raw.lower()
    base = ml.split("/", 1)[-1] if "/" in ml else ml

    if sid == "openrouter":
        if "/" in ml:
            vendor, slug = ml.split("/", 1)
            mapped = _OR_PREFIX_SERVICE.get(vendor)
            if mapped:
                p = _model_profile(mapped, slug)
                # OpenRouter parla sempre formato OpenAI compatibile
                if p["effort_wire"] == "output_config":
                    p["effort_wire"] = "reasoning_effort"
                if p["thinking"] == "anthropic":
                    p["thinking"] = None
                    p["sampling_hide_if"] = None
                p["max_tokens_wire"] = "max_tokens"
                return p
        if not ml:
            return _prof(effort=("none", "low", "medium", "high", "xhigh"), effort_default="xhigh")
        if any(h in ml for h in _LOCAL_REASONING_HINTS):
            return _prof(effort=("none", "low", "medium", "high"), effort_default="high")
        return _prof(effort=None)

    if sid == "anthropic":
        if not ml or base.startswith(("claude-opus-5", "claude-sonnet-5", "claude-fable",
                                      "claude-opus-4-7", "claude-opus-4-8", "claude-opus-4.7", "claude-opus-4.8")):
            return _prof(effort=("low", "medium", "high", "xhigh", "max"), effort_default="max",
                         effort_wire="output_config", temp_max=None, top_p=False, max_tokens_ui=(256, 65536))
        if base.startswith("claude-haiku-5"):
            return _prof(effort=("low", "medium", "high"), effort_default="high",
                         effort_wire="output_config", temp_max=None, top_p=False, max_tokens_ui=(256, 65536))
        if base.startswith(("claude-opus-4-6", "claude-sonnet-4-6", "claude-opus-4.6", "claude-sonnet-4.6")):
            return _prof(effort=("low", "medium", "high", "max"), effort_default="max",
                         effort_wire="output_config", thinking="anthropic", temp_max=1.0, top_p=True,
                         sampling_hide_if={"thinking": "enabled"}, max_tokens_ui=(256, 65536))
        if base.startswith(("claude-haiku-4-5", "claude-haiku-4.5", "claude-sonnet-4-5", "claude-sonnet-4.5",
                            "claude-opus-4-5", "claude-opus-4.5", "claude-opus-4-1", "claude-opus-4-0",
                            "claude-sonnet-4-0", "claude-3-7", "claude-3.7")):
            return _prof(effort=None, thinking="anthropic", temp_max=1.0, top_p=True,
                         sampling_hide_if={"thinking": "enabled"}, max_tokens_ui=(256, 65536))
        if base.startswith("claude-3"):
            return _prof(effort=None, thinking=None, temp_max=1.0, top_p=True, max_tokens_ui=(256, 8192))
        return _prof(effort=("low", "medium", "high", "xhigh", "max"), effort_default="max",
                     effort_wire="output_config", thinking="anthropic", temp_max=1.0, top_p=True,
                     sampling_hide_if={"thinking": "enabled"}, max_tokens_ui=(256, 65536))

    if sid == "openai":
        if base.startswith(("gpt-5.2", "gpt-5.3", "gpt-5.4", "gpt-5-codex", "gpt-5.1-codex", "gpt-6")):
            return _prof(effort=("none", "low", "medium", "high", "xhigh"), effort_default="xhigh",
                         temp_max=2.0, top_p=True, sampling_show_if={"reasoning_effort": "none"},
                         max_tokens_ui=(256, 65536), max_tokens_wire="max_completion_tokens")
        if base.startswith("gpt-5.1"):
            return _prof(effort=("none", "low", "medium", "high"), effort_default="high",
                         temp_max=2.0, top_p=True, sampling_show_if={"reasoning_effort": "none"},
                         max_tokens_ui=(256, 65536), max_tokens_wire="max_completion_tokens")
        if base.startswith("gpt-5"):
            return _prof(effort=("minimal", "low", "medium", "high"), effort_default="high",
                         temp_max=None, top_p=False, max_tokens_ui=(256, 65536),
                         max_tokens_wire="max_completion_tokens")
        if re.match(r"^o[134](?:$|[-.])", base):
            return _prof(effort=("low", "medium", "high"), effort_default="high",
                         temp_max=None, top_p=False, max_tokens_ui=(256, 65536),
                         max_tokens_wire="max_completion_tokens")
        if base.startswith(("gpt-4", "gpt-3.5", "chatgpt-")):
            return _prof(effort=None, temp_max=2.0, top_p=True, max_tokens_ui=(256, 16384))
        return _prof(effort=("none", "low", "medium", "high", "xhigh"), effort_default="xhigh",
                     temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))

    if sid == "gemini":
        if any(k in base for k in ("gemini-4-neon", "gemini-4-hydrogen")):
            return _prof(effort=("low", "medium", "high", "xhigh"), effort_default="xhigh",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 65536))
        if base.startswith(("gemini-4", "gemini-3")):
            return _prof(effort=("minimal", "low", "medium", "high"), effort_default="high",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 65536))
        if base.startswith("gemini-2.5-pro"):
            return _prof(effort=("low", "medium", "high"), effort_default="high",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 65536))
        if base.startswith("gemini-2.5-flash"):
            return _prof(effort=("none", "low", "medium", "high"), effort_default="high",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 65536))
        if base.startswith(("gemini-2.0", "gemini-1.5", "gemini-1.0", "gemma")) and "thinking" not in base:
            return _prof(effort=None, temp_max=2.0, top_p=True, max_tokens_ui=(256, 8192))
        return _prof(effort=("none", "low", "medium", "high", "xhigh"), effort_default="high",
                     temp_max=2.0, top_p=True, max_tokens_ui=(256, 65536))

    if sid in ("qwen", "qwen-token", "qwen-coding"):
        if base.startswith("qwq"):
            return _prof(effort=None, enable_thinking=False, temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))
        if base.startswith(("qwen2", "qwen-turbo", "qwen-plus", "qwen-long", "qwen-coder")) or base == "qwen-max":
            return _prof(effort=None, enable_thinking=False, temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))
        return _prof(effort=("low", "medium", "high", "xhigh"), effort_default="xhigh", enable_thinking=True,
                     temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))

    if sid == "deepseek":
        if base.startswith(("deepseek-reasoner", "deepseek-r1")):
            return _prof(effort=("low", "high", "max"), effort_default="max",
                         temp_max=None, top_p=False, max_tokens_ui=(256, 65536))
        if base.startswith(("deepseek-v4", "deepseek-flash")):
            return _prof(effort=("low", "high", "max"), effort_default="max", thinking="toggle",
                         temp_max=2.0, top_p=True, sampling_show_if={"thinking": "disabled"},
                         max_tokens_ui=(256, 65536))
        if base.startswith(("deepseek-chat", "deepseek-coder", "deepseek-v3")):
            return _prof(effort=None, temp_max=2.0, top_p=True, max_tokens_ui=(256, 8192))
        return _prof(effort=("low", "high", "max"), effort_default="max", temp_max=2.0, top_p=True)

    if sid in ("zai", "zai-coding"):
        if base.startswith("glm-5"):
            return _prof(effort=("low", "high", "max"), effort_default="max", enable_thinking=False,
                         temp_max=1.0, top_p=True, max_tokens_ui=(256, 32768))
        if base.startswith(("glm-4.5", "glm-4.6", "glm-4.7", "glm-4-5", "glm-4-6", "glm-4-7")):
            return _prof(effort=("low", "medium", "high"), effort_default="high", enable_thinking=True,
                         temp_max=1.0, top_p=True, max_tokens_ui=(256, 32768))
        if base.startswith(("glm-4", "glm-3")):
            return _prof(effort=None, enable_thinking=False, temp_max=1.0, top_p=True, max_tokens_ui=(256, 8192))
        return _prof(effort=("low", "high", "max"), effort_default="max", enable_thinking=False,
                     temp_max=1.0, top_p=True, max_tokens_ui=(256, 32768))

    if sid == "moonshot":
        if base.startswith("kimi-k3"):
            return _prof(effort=("low", "high", "max"), effort_default="max",
                         temp_max=None, top_p=False, max_tokens_ui=(256, 32768))
        if base.startswith(("kimi-k2-thinking", "kimi-k2.5", "kimi-k2.6")):
            return _prof(effort=("low", "medium", "high"), effort_default="high",
                         temp_max=1.0, top_p=True, max_tokens_ui=(256, 32768))
        if base.startswith(("kimi-k2", "moonshot-")):
            return _prof(effort=None, temp_max=1.0, top_p=True, max_tokens_ui=(256, 16384))
        return _prof(effort=("low", "high", "max"), effort_default="max", temp_max=1.0, top_p=True)

    if sid == "xai":
        if base.startswith(("grok-4.5", "grok-4.6", "grok-4.7", "grok-4-5", "grok-4-6", "grok-4-7", "grok-5")):
            return _prof(effort=("low", "medium", "high", "xhigh"), effort_default="xhigh",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 65536))
        if base.startswith("grok-3-mini"):
            return _prof(effort=("low", "high"), effort_default="high",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))
        return _prof(effort=None, temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))

    if sid == "meta":
        if base.startswith(("muse-wonder", "muse-spark")):
            return _prof(effort=("low", "medium", "high", "xhigh", "max"), effort_default="max",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 65536))
        return _prof(effort=None, temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))

    if sid == "perplexity":
        if base.startswith("sonar-deep-research"):
            return _prof(effort=("low", "medium", "high"), effort_default="high",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))
        return _prof(effort=None, temp_max=2.0, top_p=True, max_tokens_ui=(256, 16384))

    if sid == "mistral":
        return _prof(effort=None, temp_max=1.5, top_p=True, max_tokens_ui=(256, 32768))

    if sid == "groq":
        if "gpt-oss" in ml:
            return _prof(effort=("low", "medium", "high"), effort_default="high",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))
        if "qwen3" in ml or "deepseek-r1" in ml:
            return _prof(effort=("none", "low", "medium", "high"), effort_default="high",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))
        return _prof(effort=None, temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))

    if sid in ("ollama", "lmstudio", "jan"):
        if "gpt-oss" in ml:
            return _prof(effort=("low", "medium", "high"), effort_default="high",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))
        if ml and any(h in ml for h in _LOCAL_REASONING_HINTS):
            return _prof(effort=("none", "low", "medium", "high"), effort_default="high",
                         temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))
        return _prof(effort=None, temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))

    return _prof(effort=None, temp_max=2.0, top_p=True, max_tokens_ui=(256, 32768))


def _cond_visible(field, values):
    """True se il campo e' attivo con i valori correnti (rispetta show_if e hide_if)."""
    si = field.get("show_if")
    if si and any((values.get(k) not in v if isinstance(v, (list, tuple)) else values.get(k) != v) for k, v in si.items()):
        return False
    hi = field.get("hide_if")
    if hi and any((values.get(k) in v if isinstance(v, (list, tuple)) else values.get(k) == v) for k, v in hi.items()):
        return False
    return True


def param_schema_for(service_id, model=None):
    """Schema dei parametri per il selettore dell'Harness, specifico per il modello scelto: campi con etichette e
    note IT/EN, valori ammessi, condizioni di visibilita' (show_if/hide_if) e predefiniti effettivi."""
    sid = str(service_id or "").strip().lower()
    spec = get(sid)
    if not spec:
        return {"service": sid, "model": model or None, "fields": []}
    prof = _model_profile(sid, model)
    fields = []
    if prof["effort"]:
        levels = ", ".join(prof["effort"])
        edef = prof["effort_default"]
        if prof["effort_wire"] == "output_config":
            note_it = f"output_config.effort ({levels}; predefinito: {edef}; «auto · modello» = nessun override)."
            note_en = f"output_config.effort ({levels}; default: {edef}; «auto · model» = no override)."
        else:
            note_it = f"reasoning_effort ({levels}; predefinito: {edef}; «auto · modello» = nessun override)."
            note_en = f"reasoning_effort ({levels}; default: {edef}; «auto · model» = no override)."
        fields.append({"key": "reasoning_effort", "type": "enum", "values": ["default"] + list(prof["effort"]),
                       "default": edef, "it": "Sforzo di ragionamento", "en": "Reasoning effort",
                       "note_it": note_it, "note_en": note_en})
    if prof["enable_thinking"]:
        fields.append({"key": "enable_thinking", "type": "enum", "values": ["default", "on", "off"],
                       "default": "default", "it": "Ragionamento", "en": "Thinking",
                       "note_it": "enable_thinking per questo modello (on = attivo, off = disattivo).",
                       "note_en": "enable_thinking for this model (on = enabled, off = disabled)."})
    if prof["thinking"] == "anthropic":
        fields.append({"key": "thinking", "type": "enum", "values": ["default", "enabled", "disabled"],
                       "default": "default", "it": "Ragionamento esteso", "en": "Extended thinking",
                       "note_it": "thinking: «enabled» invia budget_tokens e disattiva temperature/top_p (specifica Anthropic).",
                       "note_en": "thinking: «enabled» sends budget_tokens and disables temperature/top_p (Anthropic spec)."})
        fields.append({"key": "thinking_budget", "type": "int", "min": 1024, "max": 32000, "step": 1,
                       "default": None, "show_if": {"thinking": "enabled"},
                       "it": "Budget di ragionamento", "en": "Thinking budget",
                       "note_it": "budget_tokens (1024–32000): max_tokens sara' almeno budget + 1.",
                       "note_en": "budget_tokens (1024–32000): max_tokens will be at least budget + 1."})
    elif prof["thinking"] == "toggle":
        fields.append({"key": "thinking", "type": "enum", "values": ["default", "enabled", "disabled"],
                       "default": "default", "it": "Modalita' ragionamento", "en": "Thinking mode",
                       "note_it": "thinking.type per questo modello (enabled/disabled).",
                       "note_en": "thinking.type for this model (enabled/disabled)."})
    if prof["temp_max"] is not None:
        tmax = prof["temp_max"]
        tf = {"key": "temperature", "type": "number", "min": 0.0, "max": tmax, "step": 0.1, "default": None,
              "it": "Temperatura", "en": "Temperature",
              "note_it": f"Vuoto = predefinito del modello (0.0–{tmax:.1f}).",
              "note_en": f"Empty = model default (0.0–{tmax:.1f})."}
        if prof["sampling_show_if"]:
            tf["show_if"] = dict(prof["sampling_show_if"])
        if prof["sampling_hide_if"]:
            tf["hide_if"] = dict(prof["sampling_hide_if"])
        fields.append(tf)
    mt_lo, mt_hi = prof["max_tokens_ui"]
    fields.append({"key": "max_tokens", "type": "int", "min": mt_lo, "max": mt_hi, "step": 1, "default": None,
                   "it": "Token massimi", "en": "Max tokens",
                   "note_it": f"Vuoto = predefinito del modello ({mt_lo}–{mt_hi}).",
                   "note_en": f"Empty = model default ({mt_lo}–{mt_hi})."})
    if prof["top_p"]:
        pf = {"key": "top_p", "type": "number", "min": 0.0, "max": 1.0, "step": 0.05, "default": None,
              "it": "Top-p", "en": "Top-p",
              "note_it": "Vuoto = predefinito del modello (0.0–1.0).", "note_en": "Empty = model default (0.0–1.0)."}
        if prof["sampling_show_if"]:
            pf["show_if"] = dict(prof["sampling_show_if"])
        if prof["sampling_hide_if"]:
            pf["hide_if"] = dict(prof["sampling_hide_if"])
        fields.append(pf)
    return {"service": sid, "model": model or None, "fields": fields}


def _default_params(service_id, model=None):
    """Parametri effettivi predefiniti per il modello scelto."""
    out = {}
    for f in param_schema_for(service_id, model)["fields"]:
        d = f.get("default")
        if d is None or d == "" or d == "default":
            continue
        out[f["key"]] = d
    return out


def validate_params(service_id, raw, model=None):
    """Parametri validati con whitelist esatta di chiavi, valori e range relativi al modello scelto, partendo dai
    predefiniti dello schema del modello. Idempotente: conserva l'override esplicito «default» sui campi con
    predefinito attivo e scarta i campi condizionali non attivi (es. temperature con thinking=enabled)."""
    sid = str(service_id or "").strip().lower()
    if not get(sid):
        raise ParamsError("servizio sconosciuto")
    fields = param_schema_for(sid, model)["fields"]
    out = _default_params(sid, model)
    if raw is None or raw == {}:
        return out
    if not isinstance(raw, dict):
        raise ParamsError("I parametri devono essere un oggetto JSON.")
    schema = {f["key"]: f for f in fields}
    known_optional = {"reasoning_effort", "enable_thinking", "thinking", "thinking_budget", "temperature", "top_p"}
    for key, value in raw.items():
        f = schema.get(key)
        if f is None:
            if key in known_optional and value in (None, "", "default"):
                continue
            raise ParamsError(f"Parametro non supportato per {sid}"
                              + (f" ({model})" if model else "") + f": «{str(key)[:40]}».")
        if value is None or value == "":
            out.pop(key, None)
            continue
        typ = f["type"]
        if typ == "enum":
            if not isinstance(value, str) or value not in f["values"]:
                raise ParamsError(f"Valore non valido per «{key}»: «{str(value)[:40]}» "
                                  f"(ammessi: {', '.join(f['values'])}).")
            if value == "default":
                if f.get("default") not in (None, "", "default"):
                    out[key] = "default"
                else:
                    out.pop(key, None)
                continue
        elif typ == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ParamsError(f"«{key}» deve essere un intero.")
            lo, hi = _PARAM_RANGES[key]
            if not (lo <= value <= hi):
                raise ParamsError(f"«{key}» deve essere tra {lo} e {hi}.")
        elif typ == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ParamsError(f"«{key}» deve essere un numero.")
            lo, hi = f.get("min", _PARAM_RANGES[key][0]), f.get("max", _PARAM_RANGES[key][1])
            if not (lo <= value <= hi):
                raise ParamsError(f"«{key}» deve essere tra {lo} e {hi}.")
            value = float(value)
        out[key] = value
    # Rimuove eventuali campi condizionali non attivi con le scelte correnti (es. thinking_budget o temperature)
    for f in fields:
        if f["key"] in out and not _cond_visible(f, out):
            del out[f["key"]]
    return out


def _apply_params(body, fmt, params, max_tokens, profile=None):
    """Applica i parametri gia' validati al corpo JSON della richiesta in base al formato e al profilo del modello."""
    prof = profile or {}
    mt = params.get("max_tokens", max_tokens)
    mt_wire = prof.get("max_tokens_wire") or "max_tokens"
    eff = params.get("reasoning_effort")
    if eff in (None, "", "default"):
        eff = None
    if fmt == "anthropic":
        if eff:
            body["output_config"] = {"effort": eff}
        thinking = params.get("thinking")
        if thinking == "enabled":
            budget = params.get("thinking_budget", 1024)
            body["thinking"] = {"type": "enabled", "budget_tokens": budget}
            mt = max(mt, budget + 1)
        elif thinking == "disabled":
            body["thinking"] = {"type": "disabled"}
        if thinking != "enabled":
            for k in ("temperature", "top_p"):
                if k in params:
                    body[k] = params[k]
        body["max_tokens"] = mt
    else:
        if "max_tokens" in params:
            body[mt_wire] = params["max_tokens"]
        for k in ("temperature", "top_p"):
            if k in params:
                body[k] = params[k]
        if eff and (params.get("enable_thinking") != "off" or eff == "none"):
            body["reasoning_effort"] = eff
        if "enable_thinking" in params:
            body["enable_thinking"] = params["enable_thinking"] == "on"
        if params.get("thinking") in ("enabled", "disabled"):
            body["thinking"] = {"type": params["thinking"]}
    return body


def _step_down_effort(cur, detail_low):
    """Se il servizio rifiuta un livello di effort alto ma l'errore cita un livello inferiore ammesso, scala al
    livello inferiore invece di togliere subito l'effort (es. max -> xhigh su qwen4-max, xhigh -> high su altri)."""
    if cur == "max":
        if "xhigh" in detail_low:
            return "xhigh"
        if "high" in detail_low:
            return "high"
    elif cur == "xhigh":
        if "high" in detail_low:
            return "high"
    elif cur == "minimal":
        if "low" in detail_low:
            return "low"
    return None


def _adapt_400_body(body, fmt, detail):
    """Fallback resiliente su HTTP 400: rinomina max_tokens -> max_completion_tokens (OpenAI), scala un livello
    di reasoning_effort / output_config.effort non ammesso al livello inferiore supportato, oppure toglie i campi
    opzionali citati nell'errore. Restituisce il nuovo payload o None se non c'e' nulla da adattare."""
    d_low = (detail or "").lower()
    if fmt == "openai" and "max_tokens" in body and "max_tokens" in d_low and "max_completion_tokens" not in body:
        nxt = dict(body, max_completion_tokens=body["max_tokens"])
        del nxt["max_tokens"]
        return nxt
    eff_hint = "reasoning_effort" in d_low or "effort" in d_low or ("low" in d_low and "high" in d_low)
    if fmt == "openai" and "reasoning_effort" in body and eff_hint:
        nxt_eff = _step_down_effort(body["reasoning_effort"], d_low)
        if nxt_eff and nxt_eff != body["reasoning_effort"]:
            return dict(body, reasoning_effort=nxt_eff)
        return {k: v for k, v in body.items() if k != "reasoning_effort"}
    if fmt == "anthropic" and "output_config" in body and ("output_config" in d_low or eff_hint):
        cur = (body.get("output_config") or {}).get("effort")
        nxt_eff = _step_down_effort(cur, d_low)
        if nxt_eff and nxt_eff != cur:
            return dict(body, output_config={"effort": nxt_eff})
        return {k: v for k, v in body.items() if k != "output_config"}
    drop = [k for k in ("stream_options", "enable_thinking", "thinking", "top_p", "temperature")
            if k in body and k in d_low]
    if drop:
        return {k: v for k, v in body.items() if k not in drop}
    return None


def get(service_id):
    return SERVICES.get(str(service_id or "").strip().lower())


_key_resolver = None


def set_key_resolver(fn):
    """fn(servizio) -> chiave collegata ('' se nessuna): impostata da server.py con ai_assist.linked_key."""
    global _key_resolver
    _key_resolver = fn


def server_key(service_id):
    """Chiave API presente sul server per questo servizio: variabile d'ambiente, poi chiave collegata con
    l'assistente di configurazione (letta adesso dalla sua fonte), o ''."""
    spec = get(service_id) or {}
    for var in spec.get("keys", ()):
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    if _key_resolver is not None and spec and not spec.get("local"):
        try:
            value = (_key_resolver(str(service_id).strip().lower()) or "").strip()
        except Exception:
            value = ""
        if value and KEY_RE.match(value):
            return value
    return ""


def describe(sharing, listening=None, local_models=None):
    """Servizi per il Remote Control: disponibilita' e provenienza della chiave (mai la chiave). Per i modelli locali
    (Ollama, LM Studio) local_models = {porta: [modelli installati] | None} dal rilevamento automatico: un servizio in
    ascolto ma senza modelli installati non e' disponibile; None = il servizio non li elenca (si scrive il modello)."""
    listening = listening or {}
    local_models = local_models or {}
    out = []
    for sid, spec in SERVICES.items():
        item = {"id": sid, "name": spec["name"], "formats": [f for f in ("openai", "anthropic") if spec.get(f)],
                "models": list(spec.get("models", ())), "local": bool(spec.get("local"))}
        if spec.get("local"):
            up = bool(listening.get(spec.get("port")))
            installed = local_models.get(spec.get("port")) if up else None
            if installed is not None:
                installed = [m for m in installed if MODEL_RE.match(m)]   # solo i nomi che il servizio accetta da qui
                item["models"] = installed
                item["models_detected"] = True
            if not up:
                item.update(available=False, key="none", reason="non in esecuzione sul server")
            elif installed == []:
                item.update(available=False, key="none", reason="nessun modello installato")
            else:
                item.update(available=True, key="none", reason=None)
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


def chat(service_id, model, messages, api_key="", max_tokens=4096, params=None):
    """Conversazione con il servizio (testo gia' anonimizzato). messages = [{"role": "user"|"assistant", "content"}].
    params: parametri validati (validate_params). Restituisce il testo della risposta; solleva ServiceError con un
    messaggio comprensibile."""
    spec = get(service_id)
    if not spec:
        raise ServiceError("servizio sconosciuto")
    if not model or not MODEL_RE.match(model):
        raise ServiceError("indica il modello da usare (es. quello suggerito o uno dell'elenco del servizio)")
    if not spec.get("local") and not api_key:
        raise ServiceError("serve la chiave API del servizio")
    params = validate_params(service_id, params, model=model)
    prof = _model_profile(service_id, model)
    http = _http_local if spec.get("local") else _http
    def _post_sync(url, payload, headers, fmt):
        cur = payload
        for _ in range(4):
            try:
                resp = http.post(url, json=cur, headers=headers, timeout=TIMEOUT)
            except requests.RequestException as e:
                raise ServiceError(f"{spec['name']} non raggiungibile ({e.__class__.__name__})") from None
            if resp.status_code == 400:
                nxt = _adapt_400_body(cur, fmt, (resp.text or "")[:2000])
                if nxt is not None:
                    cur = nxt
                    continue
            return resp
        return resp

    if spec.get("openai"):
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body = _apply_params({"model": model, "messages": messages, "stream": False}, "openai", params, max_tokens, prof)
        r = _post_sync(_base(spec, "openai") + "/chat/completions", body, headers, "openai")
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
    _apply_params(body, "anthropic", params, max_tokens, prof)
    r = _post_sync(_base(spec, "anthropic") + "/messages", body, headers, "anthropic")
    if r.status_code >= 400:
        raise ServiceError(f"{spec['name']} ha risposto con errore {r.status_code}: {_error_text(r)}")
    try:
        return _clip("".join(p.get("text", "") for p in r.json()["content"] if p.get("type") == "text"))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ServiceError(f"risposta di {spec['name']} non riconosciuta") from None


def build_request(service_id, model, messages, api_key="", max_tokens=4096, stream=True, params=None):
    """Richiesta HTTP verso il servizio, con il testo GIA' anonimizzato: (url, intestazioni, corpo, formato).
    params: parametri validati (validate_params), applicati al corpo JSON. E' la stessa che l'Harness mostra nella
    Glass Window prima dell'invio (con la chiave oscurata)."""
    spec = get(service_id)
    if not spec:
        raise ServiceError("servizio sconosciuto")
    params = validate_params(service_id, params, model=model)
    prof = _model_profile(service_id, model)
    if spec.get("openai"):
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body = {"model": model, "messages": messages, "stream": bool(stream)}
        if stream:
            body["stream_options"] = {"include_usage": True}    # consumo di token alla fine dello streaming
        _apply_params(body, "openai", params, max_tokens, prof)
        return _base(spec, "openai") + "/chat/completions", headers, body, "openai"
    headers = {"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"}
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [m for m in messages if m.get("role") in ("user", "assistant")], "stream": bool(stream)}
    if system:
        body["system"] = system
    _apply_params(body, "anthropic", params, max_tokens, prof)
    return _base(spec, "anthropic") + "/messages", headers, body, "anthropic"


def iter_stream(r, size=65536):
    """Byte di una risposta in streaming appena arrivano. iter_content(chunk_size=None) consegna a pezzi solo con il
    trasferimento «chunked»: con uno stream delimitato dalla chiusura della connessione (alcuni server compatibili)
    aspetterebbe la fine della risposta. read1() di urllib3 2.x restituisce subito cio' che e' disponibile, in
    entrambi i casi (e decomprime gzip/deflate)."""
    raw = getattr(r, "raw", None)
    if raw is not None and hasattr(raw, "read1"):
        while True:
            chunk = raw.read1(size, decode_content=True)
            if not chunk:
                return
            yield chunk
    else:
        yield from r.iter_content(chunk_size=None)


def _sse(r, frame):
    """Eventi Server-Sent Events di una risposta in streaming: (nome, dati). frame(testo) riceve i byte grezzi."""
    from .proxy import SSEParser
    parser = SSEParser()
    for chunk in iter_stream(r):
        if not chunk:
            continue
        if frame is not None:
            frame(chunk.decode("utf-8", "replace"))
        for name, data, _other in parser.feed(chunk):
            yield name, data
    for name, data, _other in parser.close():
        yield name, data


def _text_of(content):
    if isinstance(content, list):   # alcuni servizi restituiscono parti di contenuto
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content if isinstance(content, str) else ""


def stream_chat(service_id, model, messages, api_key, emit, cancel=None, max_tokens=4096, raw_frames=False,
                request=None, params=None):
    """Conversazione in streaming con il servizio (testo gia' anonimizzato).
    emit(tipo, dato): "delta" (testo della risposta, ancora con le etichette), "thinking" (ragionamento esposto dal
    modello), "usage" ({"input_tokens", "output_tokens"}), "frame" (byte SSE grezzi, solo con raw_frames).
    cancel: oggetto con is_set() e bind_response(r) (glass.Run): l'interruzione chiude subito la connessione.
    request: la richiesta gia' costruita con build_request (quella mostrata nella Glass Window).
    params: parametri validati (validate_params), usati solo quando la richiesta non e' gia' costruita.
    Restituisce {"answer", "usage"}; solleva ServiceError o Interrupted."""
    spec = get(service_id)
    if not spec:
        raise ServiceError("servizio sconosciuto")
    if not model or not MODEL_RE.match(model):
        raise ServiceError("indica il modello da usare (es. quello suggerito o uno dell'elenco del servizio)")
    if not spec.get("local") and not api_key:
        raise ServiceError("serve la chiave API del servizio")
    url, headers, body, fmt = request or build_request(service_id, model, messages, api_key, max_tokens,
                                                       params=params)
    http = _http_local if spec.get("local") else _http

    def stopped():
        return cancel is not None and cancel.is_set()

    def post(payload):
        if stopped():
            raise Interrupted()
        try:
            return http.post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers,
                             timeout=TIMEOUT, stream=True)
        except requests.RequestException as e:
            if stopped():
                raise Interrupted() from None
            raise ServiceError(f"{spec['name']} non raggiungibile ({e.__class__.__name__})") from None

    r = post(body)
    # Fallback resiliente: rinomina max_tokens -> max_completion_tokens (OpenAI), scala reasoning_effort /
    # output_config.effort al livello inferiore ammesso oppure toglie i campi opzionali citati nell'errore 400.
    retries = 0
    while r.status_code == 400 and retries < 3:
        detail = (r.text or "")[:2000]
        r.close()
        if stopped():
            raise Interrupted()
        nxt = _adapt_400_body(body, fmt, detail)
        if nxt is not None:
            body = nxt
        else:
            raise ServiceError(f"{spec['name']} ha risposto con errore 400: {detail[:300]}")
        retries += 1
        r = post(body)
    if cancel is not None:
        cancel.bind_response(r)
    if r.status_code >= 400:
        msg = _error_text(r)
        r.close()
        if stopped():
            raise Interrupted()
        raise ServiceError(f"{spec['name']} ha risposto con errore {r.status_code}: {msg}")
    answer, usage = [], {}

    def put_usage(inp=None, out=None):
        if inp is not None:
            usage["input_tokens"] = inp
        if out is not None:
            usage["output_tokens"] = out
        emit("usage", dict(usage))

    try:
        if "event-stream" not in (r.headers.get("Content-Type") or ""):
            data = r.json()          # il servizio ha ignorato «stream»: risposta in un solo blocco
            if fmt == "openai":
                text = _text_of((data.get("choices") or [{}])[0].get("message", {}).get("content"))
                u = data.get("usage") or {}
                if u:
                    put_usage(u.get("prompt_tokens"), u.get("completion_tokens"))
            else:
                text = "".join(p.get("text", "") for p in data.get("content") or [] if p.get("type") == "text")
                u = data.get("usage") or {}
                if u:
                    put_usage(u.get("input_tokens"), u.get("output_tokens"))
            if text:
                answer.append(text)
                emit("delta", text)
        else:
            frame = (lambda s: emit("frame", s)) if raw_frames else None
            for _name, data in _sse(r, frame):
                if stopped():
                    raise Interrupted()
                if data is None:
                    continue
                if data.strip() == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                if not isinstance(obj, dict):
                    continue
                err = obj.get("error")
                if err and fmt == "openai":
                    raise ServiceError(f"{spec['name']}: {str(err.get('message') if isinstance(err, dict) else err)[:300]}")
                if fmt == "openai":
                    u = obj.get("usage")
                    if isinstance(u, dict) and u:
                        put_usage(u.get("prompt_tokens"), u.get("completion_tokens"))
                    for ch in obj.get("choices") or []:
                        if not isinstance(ch, dict):
                            continue
                        d = ch.get("delta") or ch.get("message") or {}
                        text = _text_of(d.get("content"))
                        if text:
                            answer.append(text)
                            emit("delta", text)
                        reasoning = d.get("reasoning_content") or d.get("reasoning")
                        if isinstance(reasoning, str) and reasoning:
                            emit("thinking", reasoning)
                else:
                    t = obj.get("type")
                    if t == "content_block_delta":
                        d = obj.get("delta") or {}
                        if d.get("type") == "text_delta" and d.get("text"):
                            answer.append(d["text"])
                            emit("delta", d["text"])
                        elif d.get("type") == "thinking_delta" and d.get("thinking"):
                            emit("thinking", d["thinking"])
                    elif t == "message_start":
                        u = (obj.get("message") or {}).get("usage") or {}
                        if u:
                            put_usage(u.get("input_tokens"), u.get("output_tokens"))
                    elif t == "message_delta":
                        u = obj.get("usage") or {}
                        if u:
                            put_usage(None, u.get("output_tokens"))
                    elif t == "error":
                        e = obj.get("error") or {}
                        raise ServiceError(f"{spec['name']}: {str(e.get('message') or e)[:300]}")
    except (Interrupted, ServiceError):
        raise
    except Exception as e:
        if stopped():
            raise Interrupted() from None
        raise ServiceError(f"lo streaming di {spec['name']} si e' interrotto ({e.__class__.__name__})") from None
    finally:
        try:
            r.close()
        except Exception:
            pass
    if stopped():
        raise Interrupted()
    return {"answer": _clip("".join(answer)), "usage": usage}


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
