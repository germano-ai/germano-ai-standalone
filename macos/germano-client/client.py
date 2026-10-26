#!/usr/bin/env python
"""Germano Client - collega questo PC a un Germano Server della rete locale.

Leggerissimo (nessun modello IA): anonimizzazione, Vault e ripristino avvengono sul Server. Il Client trova il Server
sulla LAN (broadcast UDP), verifica che sia davvero un Germano Server pronto e che l'accesso sia consentito (libero,
oppure con utente e password se sul server e' attiva la gestione utenti: «client login»), poi:
- usa le AI del server (CLI condivise e servizi via API come Meta Muse, Kimi, DeepSeek, Qwen, Mistral, Grok,
  Perplexity) con la chat protetta («client ask»), con le opzioni di elaborazione scelte qui («client options»: in
  grigio, cioe' non modificabili, se il server e' nel profilo PA);
- avvia le CLI di questo PC con le variabili d'ambiente che le fanno passare dal Proxy del Server («client launch»).
Le CLI che non si possono proteggere in modo affidabile non vengono avviate come «protette»: il Client lo dice.

Codici di uscita: 0 tutto bene, 1 server non raggiungibile o non valido, 2 uso errato dei comandi,
3 accesso richiesto o non valido, 4 motore del server non pronto, 5 CLI non installata o non proteggibile,
6 opzioni bloccate dal profilo PA del server.
"""
import argparse
import getpass
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import ai_detect          # noqa: E402  (rilevamento delle CLI installate su QUESTO computer)
import discovery          # noqa: E402  (protocollo di rilevamento UDP, identico a quello del Server)

CONFIG_FILE = os.path.join(BASE_DIR, "client_config.json")
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
DEFAULT_SERVER_PORT = 8181
MAX_ATTACHMENTS = 12          # limite dello Studio del Server per un singolo invio
OK, ERR_SERVER, ERR_USAGE, ERR_TOKEN, ERR_ENGINE, ERR_CLI, ERR_LOCKED = 0, 1, 2, 3, 4, 5, 6
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_LOOPBACK = ("127.0.0.1", "localhost", "::1")
# Verso il Germano Server della LAN ci si collega sempre direttamente: mai attraverso un proxy di sistema o aziendale,
# che vedrebbe in chiaro i testi da proteggere.
_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Come ogni CLI passa dal Proxy del Server. stato: "verificato" (collaudato dal vivo), "documentato" (secondo la
# documentazione della CLI), "manuale" (la CLI non legge le variabili d'ambiente: va configurata a mano, poi --forza),
# "non_supportato" (il Proxy non parla il suo protocollo: non si avvia).
PROFILES = {
    "claude-code": {
        "stato": "verificato",
        "nota": "collaudato con Claude Code 2.1.308 e chiave API (ANTHROPIC_API_KEY).",
        "rimuovi": ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"),
    },
    "codex": {
        "stato": "documentato",
        "nota": "vale per il fornitore OpenAI predefinito con chiave API (OPENAI_API_KEY). Se ~/.codex/config.toml "
                "usa un altro fornitore, o se accedi con l'account ChatGPT, il traffico puo' non passare da Germano.",
    },
    "aider": {
        "stato": "documentato",
        "nota": "usa i modelli come openai/<nome>: con altri nomi Aider puo' collegarsi direttamente a un altro "
                "fornitore. Per sicurezza il Client toglie dal suo ambiente le chiavi degli altri fornitori.",
        "rimuovi": ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
                    "MISTRAL_API_KEY", "GROQ_API_KEY", "XAI_API_KEY", "COHERE_API_KEY", "TOGETHERAI_API_KEY",
                    "FIREWORKS_API_KEY", "AZURE_API_KEY", "AZURE_OPENAI_API_KEY"),
    },
    "qwen": {
        "stato": "documentato",
        "nota": "Qwen Code usa il formato OpenAI: il Server inoltra queste richieste al proprio «Servizio OpenAI o "
                "compatibile», che deve essere quello di Qwen (DashScope, modalita' compatibile) per usare i modelli Qwen.",
    },
    "gemini-cli": {
        "stato": "non_supportato",
        "motivo": "Gemini CLI usa il protocollo Gemini di Google, che il Proxy di Germano Server non gestisce: le "
                  "richieste andrebbero a Google senza protezione.",
        "alternativa": "Per lavorare protetti usa Claude Code, Codex, Aider o Qwen Code, oppure proteggi il testo con:  "
                       "client send \"...\"",
    },
    "kimi": {
        "stato": "manuale",
        "motivo": "Kimi Code CLI non legge indirizzo e chiave del servizio dalle variabili d'ambiente, ma solo dal "
                  "proprio config.toml (~/.kimi/config.toml): il Client non puo' instradarlo da solo.",
        "istruzioni": "nel config.toml di Kimi, nel fornitore in uso, imposta base_url = {base}/p/moonshot/v1 (il Proxy "
                      "di Germano lo inoltra a Moonshot AI dopo aver anonimizzato i testi)",
    },
    "deepseek": {
        "stato": "manuale",
        "motivo": "DeepSeek non ha una CLI ufficiale: il comando trovato (Deep Code, Reasonix o altro) e' uno strumento "
                  "di terze parti, di cui il Client non puo' verificare il comportamento.",
        "istruzioni": "imposta nello strumento l'indirizzo compatibile OpenAI {base}/p/deepseek/v1 (oppure, per Claude "
                      "Code, il formato Anthropic {base}/p/deepseek); in alternativa usa «client ask deepseek»",
    },
    "muse-code": {
        "stato": "manuale",
        "motivo": "Muse Code (Meta) si configura con un accesso dal browser o con la chiave della Meta Model API: il "
                  "Client non sa ancora instradarlo da solo.",
        "istruzioni": "se Muse Code permette un indirizzo personalizzato compatibile OpenAI impostalo a {base}/p/meta/v1; "
                      "per Muse Wonder e Muse Spark protetti usa  client ask meta \"...\" --model muse-wonder-1.0",
    },
    "mistral-vibe": {
        "stato": "manuale",
        "motivo": "Mistral Vibe legge fornitore e chiave dal proprio ~/.vibe/config.toml.",
        "istruzioni": "nel config.toml di Vibe imposta come indirizzo del fornitore Mistral {base}/p/mistral/v1, oppure "
                      "usa  client ask mistral \"...\"",
    },
    "grok-build": {
        "stato": "manuale",
        "motivo": "Grok Build usa l'accesso a xAI configurato al suo interno.",
        "istruzioni": "se Grok Build accetta un indirizzo personalizzato impostalo a {base}/p/xai/v1, oppure usa  "
                      "client ask xai \"...\"",
    },
    "opencode": {
        "stato": "manuale",
        "motivo": "OpenCode sceglie fornitore e indirizzo nel proprio opencode.json.",
        "istruzioni": "in opencode.json aggiungi un fornitore compatibile OpenAI con baseURL {openai} (o "
                      "{base}/p/<servizio>/v1 per DeepSeek, Kimi, Qwen, Mistral, Grok...)",
    },
    "goose": {"stato": "manuale", "motivo": "Goose sceglie il fornitore nella propria configurazione.",
              "istruzioni": "configura un fornitore compatibile OpenAI con indirizzo {openai}"},
    "crush": {"stato": "manuale", "motivo": "Crush sceglie il fornitore nel proprio crush.json.",
              "istruzioni": "aggiungi un fornitore compatibile OpenAI con base_url {openai}"},
    "cline": {"stato": "manuale", "motivo": "Cline sceglie il fornitore nella propria configurazione.",
              "istruzioni": "scegli il fornitore «OpenAI Compatible» con Base URL {openai}"},
    "kilo": {"stato": "manuale", "motivo": "Kilo Code sceglie il fornitore nella propria configurazione.",
             "istruzioni": "scegli il fornitore «OpenAI Compatible» con Base URL {openai}"},
    "copilot-cli": {
        "stato": "non_supportato",
        "motivo": "GitHub Copilot CLI usa i servizi di GitHub e non permette di cambiare l'indirizzo dei modelli: le "
                  "richieste non passerebbero da Germano.",
        "alternativa": "Per lavorare protetti usa Claude Code, Codex, Aider o Qwen Code, oppure la chat protetta:  "
                       "client ask <servizio> \"...\"",
    },
    "cursor-agent": {
        "stato": "non_supportato",
        "motivo": "Cursor CLI usa i servizi di Cursor: le richieste non passerebbero da Germano.",
        "alternativa": "Usa Claude Code, Codex, Aider o Qwen Code, oppure  client ask <servizio> \"...\"",
    },
    "kiro-cli": {
        "stato": "non_supportato",
        "motivo": "Kiro CLI usa i servizi di Amazon: le richieste non passerebbero da Germano.",
        "alternativa": "Usa Claude Code, Codex, Aider o Qwen Code, oppure  client ask <servizio> \"...\"",
    },
    "amp": {"stato": "non_supportato", "motivo": "Amp usa i servizi di Sourcegraph: non passerebbe da Germano.",
            "alternativa": "Usa Claude Code, Codex, Aider o Qwen Code, oppure  client ask <servizio> \"...\""},
    "droid": {"stato": "non_supportato", "motivo": "Droid usa i servizi di Factory: non passerebbe da Germano.",
              "alternativa": "Usa Claude Code, Codex, Aider o Qwen Code, oppure  client ask <servizio> \"...\""},
    "jules": {"stato": "non_supportato", "motivo": "Jules lavora nel cloud di Google sui repository: non passa da Germano.",
              "alternativa": "Per i modelli Gemini protetti usa  client ask gemini \"...\""},
    "perplexity": {"stato": "non_supportato",
                   "motivo": "pplx interroga direttamente la ricerca di Perplexity: non passerebbe da Germano.",
                   "alternativa": "Per i modelli Sonar protetti usa  client ask perplexity \"...\" --model sonar"},
}
ALIASES = {"claude": "claude-code", "gemini": "gemini-cli", "qwen-code": "qwen", "kimi-cli": "kimi", "kimi-code": "kimi",
           "deepseek-cli": "deepseek", "deepcode": "deepseek", "reasonix": "deepseek", "openai-codex": "codex",
           "muse": "muse-code", "vibe": "mistral-vibe", "grok": "grok-build", "copilot": "copilot-cli",
           "pplx": "perplexity", "kilocode": "kilo"}
APPS = {
    "cursor": "Cursor non si puo' proteggere con Germano: costruisce i prompt sui propri server e il suo «Override "
              "OpenAI Base URL» accetta solo indirizzi pubblici su Internet (127.0.0.1 e gli IP della rete locale non "
              "funzionano), quindi i testi arriverebbero in chiaro ai server di Cursor prima di Germano. Usa Claude "
              "Code, Codex, Aider o Qwen Code, oppure proteggi il testo con:  client send \"...\"",
    "windsurf": "Windsurf usa i propri servizi e non documenta un indirizzo personalizzato per i modelli: le sue "
                "richieste non passano da Germano. Al suo interno puoi usare un'estensione come Continue, "
                "configurata con l'indirizzo {openai} (formato OpenAI).",
    "antigravity": "Antigravity e' un'applicazione grafica: i modelli inclusi passano dai servizi di Google e non e' "
                   "documentato un indirizzo personalizzato, quindi le sue richieste non passano da Germano. Al suo "
                   "interno puoi usare un'estensione come Continue, configurata con l'indirizzo {openai} (formato "
                   "OpenAI) o {anthropic} (formato Anthropic).",
    "claude-desktop": "Claude Desktop si collega direttamente a claude.ai e non offre un'impostazione per cambiare "
                      "l'indirizzo del servizio: non si puo' proteggere con Germano. Usa Claude Code:  "
                      "client launch claude-code",
    "chatgpt": "L'app di ChatGPT si collega direttamente a OpenAI e non passa da Germano. Per lavorare protetti usa  "
               "client ask openai \"...\" oppure il Remote Control nel browser.",
    "kiro": "Kiro usa i servizi di Amazon e non documenta un indirizzo personalizzato per i modelli: le sue richieste "
            "non passano da Germano.",
    "trae": "Trae usa i propri servizi: le sue richieste non passano da Germano.",
    "zed": "In Zed scegli un fornitore compatibile OpenAI con l'indirizzo {openai} (impostazioni language_models).",
}
# Nome di un'AI -> servizio API del Germano Server con cui la si usa protetta («client ask <nome>»)
SERVICE_ALIASES = {"claude": "anthropic", "claude-code": "anthropic", "chatgpt": "openai", "codex": "openai",
                   "gemini": "gemini", "gemini-cli": "gemini", "muse": "meta", "muse-code": "meta", "muse-wonder": "meta",
                   "kimi": "moonshot", "kimi-cli": "moonshot", "qwen": "qwen", "qwen-code": "qwen", "deepseek": "deepseek",
                   "mistral-vibe": "mistral", "vibe": "mistral", "codestral": "mistral", "grok": "xai",
                   "grok-build": "xai", "perplexity": "perplexity", "pplx": "perplexity", "sonar": "perplexity"}
STATE_LABEL = {"verificato": "protetta (collaudata)", "documentato": "protetta (secondo la documentazione)",
               "manuale": "da configurare a mano", "non_supportato": "NON proteggibile"}


class ClientError(Exception):
    """Problema gia' descritto in modo comprensibile, con il codice di uscita da restituire."""

    def __init__(self, message, code=ERR_SERVER):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------------ utilita'
def _setup_output():
    """Mai un errore di stampa: con l'uscita reindirizzata (file, pipe) i caratteri non rappresentabili diventano '?'."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def get_version():
    try:
        with open(os.path.join(BASE_DIR, "VERSION"), "r", encoding="utf-8-sig") as f:
            return f.read().strip() or "0.52-alpha"
    except OSError:
        return "0.52-alpha"


def _clean(value, limit=60):
    """Testo ricevuto dalla rete, ripulito prima di stamparlo (niente caratteri di controllo)."""
    return _CTRL_RE.sub("", str(value if value is not None else ""))[:limit]


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def _ask(prompt, secret=False):
    """Domanda nel menu: None se l'utente chiude l'ingresso (Ctrl+Z, Ctrl+C). Il testo segreto si legge senza
    mostrarlo solo da una console vera: su Windows getpass legge i tasti dalla console anche quando l'ingresso e'
    reindirizzato (pipe, file) e resterebbe in attesa per sempre."""
    try:
        if secret and sys.stdin is not None and sys.stdin.isatty():
            return getpass.getpass(prompt).strip()
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


# ------------------------------------------------------------------ configurazione
_warned = set()


def _warn(msg):
    if msg not in _warned:
        _warned.add(msg)
        print(f"Attenzione: {msg}", file=sys.stderr)


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        _warn(f"client_config.json non leggibile ({e.__class__.__name__}): uso i valori predefiniti.")
        return {}
    if not isinstance(data, dict):
        _warn("client_config.json non e' un oggetto JSON: uso i valori predefiniti.")
        return {}
    return data


def save_config(cfg):
    tmp = CONFIG_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, CONFIG_FILE)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ClientError(f"impossibile salvare client_config.json ({e.strerror or e}): la cartella del Client e' in "
                          "sola lettura? Usa le opzioni --server e --token sulla riga di comando.", ERR_USAGE) from None


def parse_server(text):
    """'192.168.1.10', '192.168.1.10:8181', 'http://pc-server:8181/' oppure un Base URL copiato dalla Dashboard
    ('.../g/<token>/v1'). Restituisce (base, token_trovato | None)."""
    raw = (text or "").strip()
    if not raw:
        raise ClientError("indirizzo del server vuoto.", ERR_USAGE)
    if "://" not in raw:
        raw = "http://" + raw
    u = urllib.parse.urlsplit(raw)
    try:
        port = u.port
    except ValueError:
        port = -1
    if u.scheme not in ("http", "https") or not u.hostname or port == -1 or " " in raw:
        raise ClientError(f"indirizzo del server non valido: «{_clean(text)}» (esempio: http://192.168.1.10:8181).",
                          ERR_USAGE)
    host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
    base = f"{u.scheme}://{host}:{port or (443 if u.scheme == 'https' else DEFAULT_SERVER_PORT)}"
    m = re.match(r"^/g/([^/]+)", u.path or "")
    return base, (m.group(1) if m else None)


def check_token_format(tok):
    if tok and not _TOKEN_RE.match(tok):
        raise ClientError("il token contiene caratteri non validi: copia esattamente quello mostrato dal server "
                          "(lettere, cifre, - e _).", ERR_USAGE)


def _token(args):
    tok = getattr(args, "token", None)
    if tok is None:
        tok = load_config().get("token") or ""
    tok = str(tok).strip()
    check_token_format(tok)
    return tok


def _discovery_port():
    try:
        port = int(load_config().get("discovery_port") or discovery.DEFAULT_PORT)
    except (TypeError, ValueError):
        return discovery.DEFAULT_PORT
    return port if 1024 <= port <= 65535 else discovery.DEFAULT_PORT


def discover_servers(timeout=1.5):
    return discovery.discover(timeout=timeout, port=_discovery_port(), broadcasts=discovery.broadcast_addresses())


def resolve_server(args):
    """(base_url, provenienza). Ordine: --server, client_config.json, rilevamento automatico sulla rete."""
    if getattr(args, "server", None):
        base, tok = parse_server(args.server)
        if tok and not getattr(args, "token", None):
            args.token = tok
        return base, "indicato con --server"
    url = load_config().get("server_url")
    if url:
        try:
            return parse_server(url)[0], "da client_config.json"
        except ClientError as e:
            raise ClientError(f"client_config.json: {e} Correggilo con:  client config --server <indirizzo>",
                              ERR_USAGE) from None
    found = discover_servers()
    if not found:
        raise ClientError("nessun Germano Server trovato sulla rete locale. Sul server attiva la modalita' Server "
                          "(nelle Impostazioni di Germano) e consenti le reti private nel firewall di Windows; "
                          "oppure indica l'indirizzo con --server.")
    if len(found) == 1:
        s = found[0]
        return f"http://{s['ip']}:{s['port']}", f"trovato in rete: «{_clean(s.get('name'))}»"
    print("Trovati piu' Germano Server sulla rete:")
    for i, s in enumerate(found, 1):
        print(f"  [{i}] {_clean(s.get('name'))}  http://{s['ip']}:{s['port']}  v{_clean(s.get('version'), 20)}")
    if sys.stdin is None or not sys.stdin.isatty():
        raise ClientError("piu' server disponibili: indica quale con --server oppure salvalo con «client config "
                          "--server <indirizzo>».", ERR_USAGE)
    choice = _ask("Scegli il server [1]: ")
    if choice is None:
        raise ClientError("nessun server scelto.", ERR_USAGE)
    choice = choice or "1"
    if not choice.isdigit() or not 1 <= int(choice) <= len(found):
        raise ClientError(f"scelta non valida: «{_clean(choice, 10)}».", ERR_USAGE)
    s = found[int(choice) - 1]
    return f"http://{s['ip']}:{s['port']}", f"scelto in rete: «{_clean(s.get('name'))}»"


# ------------------------------------------------------------------ HTTP verso il Server (solo libreria standard)
def _where(url):
    u = urllib.parse.urlsplit(url)
    return f"{u.hostname}:{u.port}" if u.port else (u.hostname or url)


def _network_problem(reason, url, timeout):
    where = _where(url)
    win = getattr(reason, "winerror", None)
    if isinstance(reason, (socket.timeout, TimeoutError)) or win == 10060:
        return (f"nessuna risposta da {where} entro {timeout:g} s: server spento o sovraccarico, firewall di Windows "
                "o indirizzo sbagliato.")
    if isinstance(reason, ConnectionRefusedError) or win == 10061:
        return (f"{where} rifiuta la connessione: Germano Server non e' avviato, non e' in modalita' Server o la porta "
                "e' sbagliata.")
    if isinstance(reason, socket.gaierror):
        return f"il nome «{urllib.parse.urlsplit(url).hostname}» non corrisponde a nessun computer raggiungibile."
    if isinstance(reason, ConnectionResetError) or win == 10054:
        return f"{where} ha interrotto la connessione."
    if win in (10051, 10065):
        return f"{where} non e' raggiungibile da questa rete."
    if isinstance(reason, str):
        return f"collegamento a {where} non riuscito ({reason})."
    return f"collegamento a {where} non riuscito ({reason.__class__.__name__}: {reason})."


def _request(method, url, data=None, headers=None, timeout=6.0):
    """(stato HTTP, corpo). Solleva ClientError se non si riesce a dialogare con il server."""
    req = urllib.request.Request(url, data=data, headers=dict(headers or {}), method=method)
    req.add_header("User-Agent", f"GermanoClient/{get_version()}")
    try:
        with _HTTP.open(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except OSError:
            return e.code, b""
    except urllib.error.URLError as e:
        raise ClientError(_network_problem(e.reason, url, timeout)) from None
    except OSError as e:   # comprende i timeout in lettura e le connessioni interrotte
        raise ClientError(_network_problem(e, url, timeout)) from None
    except http.client.HTTPException as e:
        raise ClientError(f"{_where(url)} non risponde come un server web ({e.__class__.__name__}): non e' un "
                          "Germano Server.") from None


def _json(body):
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return None


def _auth_headers(tok):
    return {"X-Germano-Auth": tok} if tok else {}


def check_server(base, token, timeout=6.0):
    """Verifica, SENZA inviare dati personali, che all'indirizzo risponda un Germano Server, lo stato del suo motore e
    l'accesso (libero, oppure sessione valida se la gestione utenti e' attiva). Solleva ClientError se il server non e'
    raggiungibile o non e' Germano."""
    t0 = time.perf_counter()
    st, body = _request("GET", base + "/api/discovery", timeout=timeout)
    ms = round((time.perf_counter() - t0) * 1000)
    info = _json(body)
    if st == 403:
        raise ClientError(f"{_where(base)} risponde ma non accetta richieste dalla rete: sul server attiva la modalita' "
                          "Server nelle Impostazioni di Germano.")
    if st != 200 or not isinstance(info, dict) or info.get("service") != "germano-server":
        raise ClientError(f"a {_where(base)} risponde un servizio che non e' un Germano Server v0.52 o successivo "
                          f"(HTTP {st}).")
    res = {"info": info, "ms": ms, "engine_ready": bool(info.get("engine_ready")), "user": None,
           "token_required": bool(info.get("auth_required", info.get("token_required", True))), "remote": "remote" in info}
    st2, body2 = _request("GET", base + "/api/auth/status", headers=_auth_headers(token), timeout=timeout)
    a = _json(body2)
    if st2 == 200 and isinstance(a, dict):            # Germano Server 0.60: gestione utenti
        if a.get("local"):
            res.update(token="non necessario (server su questo stesso computer)", token_ok=True)
        elif not a.get("enabled"):
            res.update(token="libero (il server non richiede credenziali)", token_ok=True)
        elif a.get("logged_in"):
            res.update(token=f"autenticato come «{_clean(a.get('user'), 64)}»", token_ok=True, user=a.get("user"))
        else:
            res.update(token="ACCESSO RICHIESTO" if not token else "SESSIONE SCADUTA O NON VALIDA", token_ok=False)
        return res
    host = urllib.parse.urlsplit(base).hostname or ""   # Germano Server 0.52: token condiviso
    if host in _LOOPBACK or host.startswith("127."):
        res.update(token="non necessario (server su questo stesso computer)", token_ok=True)
    elif not token:
        res.update(token="MANCANTE" if res["token_required"] else "non richiesto", token_ok=not res["token_required"])
    else:
        st3, _ = _request("GET", f"{base}/g/{token}/api/engine/v1/info", timeout=timeout)
        if st3 in (200, 409):
            res.update(token="valido", token_ok=True)
        elif st3 == 401:
            res.update(token="ERRATO", token_ok=False)
        else:
            res.update(token=f"non verificabile (HTTP {st3})", token_ok=False)
    return res


def _token_help(tok):
    if tok:
        return ("La sessione non e' piu' valida (scaduta, password cambiata o utente eliminato): accedi di nuovo con:  "
                "client login")
    return "Sul server e' attiva la gestione utenti: accedi con utente e password:  client login"


def remote_info(base, tok, timeout=8.0):
    """Informazioni del Remote Control (Germano Server 0.60): AI, servizi, opzioni, profilo. None se non disponibile."""
    st, body = _request("GET", base + "/api/remote/v1/info", headers=_auth_headers(tok), timeout=timeout)
    data = _json(body)
    return data if st == 200 and isinstance(data, dict) and data.get("service") == "germano-remote" else None


def client_options():
    """Opzioni di elaborazione scelte su questo PC (client_config.json), gia' convalidate dal server."""
    opts = load_config().get("options")
    return opts if isinstance(opts, dict) else None


def server_tools(base, tok, timeout=8.0):
    """AI installate sul SERVER: (catalogo, avviso | None). Con la gestione utenti attiva il catalogo completo (con cio'
    che si puo' usare da qui) richiede l'accesso; senza, o con un server meno recente, si ripiega sull'elenco in sola
    lettura."""
    headers = {"X-Germano-Auth": tok} if tok else {}
    st, body = _request("GET", base + "/api/harness/v1/tools", headers=headers, timeout=timeout)
    data = _json(body)
    if st == 200 and isinstance(data, dict) and isinstance(data.get("tools"), list):
        return data, None
    note = {401: "accesso richiesto (client login): elenco in sola lettura, le AI del server non si possono usare da qui",
            404: "il server non condivide ancora le sue AI (versione precedente): elenco in sola lettura"}.get(
        st, f"catalogo non disponibile (HTTP {st}): elenco in sola lettura")
    st2, body2 = _request("GET", base + "/api/ai/detect", timeout=timeout)
    d2 = _json(body2)
    if st2 != 200 or not isinstance(d2, dict):
        raise ClientError(f"il server non fornisce l'elenco delle sue AI (HTTP {st2}).")
    tools = [{"id": t.get("id"), "name": t.get("name"), "kind": t.get("kind"), "version": t.get("version"),
              "remote": {"usable": False, "reason": note}} for t in d2.get("tools") or [] if t.get("detected")]
    return {"tools": tools, "sharing": None, "proxy": {}, "server": {}}, note


def _multipart(fields, files):
    """multipart/form-data con la sola libreria standard. files = [(campo, nome_file, bytes)]."""
    boundary = "----germano" + os.urandom(12).hex()
    out = bytearray()
    for name, value in fields.items():
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
                + str(value).encode("utf-8") + b"\r\n")
    for field, filename, data in files:
        name = re.sub(r'["\\\r\n]', "_", filename) or "allegato"
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode() or "allegato"
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{ascii_name}"; '
                f"filename*=UTF-8''{urllib.parse.quote(name)}\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8") + data + b"\r\n"
    out += f"--{boundary}--\r\n".encode("utf-8")
    return bytes(out), f"multipart/form-data; boundary={boundary}"


# ------------------------------------------------------------------ comandi
def cmd_discover(args):
    timeout = min(max(float(getattr(args, "timeout", 1.5) or 1.5), 0.2), 30.0)
    t0 = time.perf_counter()
    found = discover_servers(timeout=timeout)
    if not found:
        print(f"Nessun Germano Server trovato sulla rete locale (ricerca di {timeout:g} s).")
        print("Verifica che sul server sia attiva la modalita' Server (nelle Impostazioni di Germano) e che il "
              "firewall di Windows consenta le reti private.")
        return ERR_SERVER
    print(f"{'Trovato' if len(found) == 1 else 'Trovati'} {len(found)} server in "
          f"{round((time.perf_counter() - t0) * 1000)} ms:")
    for s in found:
        tok = " (richiede token)" if s.get("token_required") else ""
        rdy = "motore pronto" if s.get("engine_ready") else "motore non ancora pronto"
        print(f"  - {_clean(s.get('name'))}  http://{s['ip']}:{s['port']}  v{_clean(s.get('version'), 20)}{tok}  [{rdy}]")
    if len(found) == 1 and not load_config().get("server_url"):
        print(f"Per collegarti sempre a questo server:  client config --server http://{found[0]['ip']}:{found[0]['port']}")
    return OK


def cmd_status(args):
    base, origin = resolve_server(args)
    tok = _token(args)
    print(f"Server: {base}  ({origin})")
    try:
        r = check_server(base, tok)
    except ClientError as e:
        print(f"  NON RAGGIUNGIBILE: {e}")
        return e.code
    info = r["info"]
    print(f"  servizio : Germano Server v{_clean(info.get('version'), 20)} «{_clean(info.get('name'))}» "
          f"(risposta in {r['ms']} ms)")
    print("  motore IA: " + ("pronto" if r["engine_ready"] else
                             "NON PRONTO: il server blocca le richieste finche' il motore non e' attivo (nessun dato esce)"))
    print(f"  accesso  : {r['token']}")
    prof = info.get("profile")
    if prof:
        print(f"  profilo  : {prof}" + (" (opzioni di elaborazione imposte dal server, non modificabili da qui)"
                                       if info.get("options_locked") else " (opzioni di elaborazione personalizzabili: "
                                                                          "client options)"))
    if r.get("remote"):
        print(f"  browser  : {base}/remote  (Remote Control, anche da tablet e smartphone)")
    if not r["token_ok"]:
        print("  " + _token_help(tok))
        return ERR_TOKEN
    if not r["engine_ready"]:
        return ERR_ENGINE
    print("Esito: collegamento pronto.")
    if origin.startswith(("trovato", "scelto")):
        print(f"Per collegarti sempre a questo server:  client config --server {base}")
    return OK


def _preflight(base, tok, what):
    """Controlli prima di inviare dati o di avviare una CLI. Restituisce (codice, esito di check_server)."""
    try:
        r = check_server(base, tok)
    except ClientError as e:
        print(f"Server {base}: {e}")
        print(f"{what}: nessun dato e' stato inviato.")
        return e.code, None
    if not r["token_ok"]:
        print(f"Accesso {r['token']}: {what}, nessun dato e' stato inviato.")
        print(_token_help(tok))
        return ERR_TOKEN, r
    return OK, r


def _options_field(r):
    """Opzioni da inviare con la richiesta: solo con un server 0.60 che non le blocca (profilo PA o lock_settings)."""
    opts = client_options()
    if not opts or not r.get("remote") or r["info"].get("options_locked"):
        return None
    return json.dumps(opts, ensure_ascii=False)


def cmd_send(args):
    prompt = (args.prompt or "").strip()
    files = list(args.files or [])
    if prompt and not files and os.path.isfile(prompt):
        files, prompt = [prompt], ""
        print(f"«{_clean(files[0], 80)}» e' un file: lo allego.")
    if not prompt and not files:
        print('Scrivi un testo da proteggere e/o indica dei file.  Esempio:  client send "Scrivi a Mario Rossi" lettera.docx')
        return ERR_USAGE
    if len(files) > MAX_ATTACHMENTS:
        print(f"Al massimo {MAX_ATTACHMENTS} file per invio ({len(files)} indicati). Nessun dato e' stato inviato.")
        return ERR_USAGE
    parts = []
    for p in files:
        try:
            with open(p, "rb") as f:
                parts.append(("files", os.path.basename(p), f.read()))
        except OSError as e:
            print(f"File non leggibile: {_clean(p, 120)} ({e.strerror or e}). Invio annullato: nessun dato e' stato inviato.")
            return ERR_USAGE
    base, _origin = resolve_server(args)
    tok = _token(args)
    code, r = _preflight(base, tok, "invio annullato")
    if code:
        return code
    if not r["engine_ready"]:
        print("Il motore del server non e' pronto: invio annullato, nessun dato e' stato inviato. Riprova tra poco.")
        return ERR_ENGINE
    fields = {"prompt": prompt, "target": "germano-client"}
    opts = _options_field(r)
    if opts:
        fields["options"] = opts
    body, ctype = _multipart(fields, parts)
    headers = {"Content-Type": ctype, **_auth_headers(tok)}
    path = "/api/remote/v1/protect" if r.get("remote") else "/api/studio/send"
    try:
        st, raw = _request("POST", base + path, data=body, headers=headers, timeout=1800)
    except ClientError as e:
        print(f"Invio non riuscito: {e}")
        return e.code
    data = _json(raw) or {}
    if st == 200 and data.get("status") == "success":
        n = data.get("entity_count", 0)
        labels = data.get("labels") or []
        print(f"Protetto dal server: {_plural(n, 'dato oscurato', 'dati oscurati')}"
              f" ({', '.join(_clean(x, 40) for x in labels) or 'nessuna etichetta'}).")
        skipped = [_clean(a.get("name"), 80) for a in data.get("attachments") or [] if not a.get("textual")]
        if skipped:
            print(f"Attenzione: allegati senza testo non inclusi ({', '.join(skipped)}): per oscurare immagini e "
                  "scansioni usa l'anonimizzazione dei file sul server.")
        print("--- testo protetto, pronto da inviare all'AI ---")
        print(data.get("protected", data.get("composed", "")))
        return OK
    msg = _clean(data.get("message") or data.get("error") or f"risposta inattesa (HTTP {st})", 400)
    print(f"[{st}] {msg}")
    if st in (401, 403, 503):
        print("Nessun dato e' uscito verso servizi di AI.")
    if st == 403 and data.get("code") == "compliance_lock":
        print("Le opzioni di questo PC non valgono con il profilo PA del server: rimuovile con  client options --reset")
        return ERR_LOCKED
    return ERR_TOKEN if st == 401 else ERR_ENGINE if st == 503 else ERR_SERVER


KIND_LABEL = {"cli": "CLI", "app": "applicazione", "service": "modelli locali"}


def cmd_models(args):
    """Elenca le AI e i modelli disponibili sul Germano Server e come usarli da questo PC."""
    base, origin = resolve_server(args)
    tok = _token(args)
    try:
        r = check_server(base, tok)
    except ClientError as e:
        print(f"Server {base}: {e}")
        return e.code
    info = r["info"]
    data, note = server_tools(base, tok)
    tools = data.get("tools") or []
    rinfo = remote_info(base, tok) if r.get("remote") and r["token_ok"] else None
    print(f"AI del Germano Server «{_clean(info.get('name'))}» ({base}, v{_clean(info.get('version'), 20)}; {origin}):")
    if note:
        print(f"  nota: {note}.")
    services = (rinfo or {}).get("services") or []
    if services:
        print("  Servizi di AI attraverso Germano (testo anonimizzato dal server prima di uscire):")
        for s in services:
            if s.get("local"):
                how = "modelli locali del server" if s.get("available") else "modelli locali: ora non in esecuzione"
            else:
                how = "chiave del server condivisa" if s.get("key") == "server" else "con la tua chiave (--key)"
            models = f"; modelli: {', '.join(_clean(m, 40) for m in s.get('models') or [])}" if s.get("models") else ""
            print(f"    - {s.get('id'):<11} {_clean(s.get('name'))} ({how}{models})")
        print('        client ask <servizio> "il tuo prompt" --model <modello> [--key <chiave API>]')
    usable = [t for t in tools if (t.get("remote") or {}).get("usable")]
    others = [t for t in tools if not (t.get("remote") or {}).get("usable")]
    if usable:
        print("  Utilizzabili da questo PC (eseguite sul server; verso l'AI esce solo testo anonimizzato):")
        for t in usable:
            ver = f" {_clean(t.get('version'), 20)}" if t.get("version") else ""
            state = " [collaudata]" if (t.get("remote") or {}).get("state") == "verificato" else ""
            print(f"    - {t.get('id'):<15} {_clean(t.get('name'))}{ver}{state}")
            print(f"        client ask {t.get('id')} \"il tuo prompt\"")
    if others:
        print("  Installate sul server ma non utilizzabili da qui:")
        for t in others:
            ver = f" {_clean(t.get('version'), 20)}" if t.get("version") else ""
            kind = KIND_LABEL.get(t.get("kind"), t.get("kind") or "")
            reason = _clean((t.get("remote") or {}).get("reason"), 220)
            print(f"    - {t.get('id'):<15} {_clean(t.get('name'))}{ver} ({kind}): {reason}")
    if not tools:
        print("  Nessuna AI rilevata sul server.")
    if data.get("sharing") is False and any(t.get("kind") == "cli" for t in tools):
        print("  Condivisione delle AI disattivata sul server: l'amministratore la attiva in Impostazioni > Accesso dalla "
              "rete («Condividi con i client le AI di questo computer»).")
    proxy = data.get("proxy") or {}
    if proxy:
        print("  Proxy del server, per le CLI installate su QUESTO PC (client launch ...):")
        print(f"    formato Anthropic -> {_clean(proxy.get('anthropic')) or '?'}   (claude-code)")
        print(f"    formato OpenAI    -> {_clean(proxy.get('openai')) or '?'}   (codex, aider, qwen)")
    here = _local_tools()
    print("AI installate su questo PC: " + (", ".join(f"{i} ({lbl})" for i, lbl in here) or "nessuna") + ".")
    if not r["token_ok"]:
        print(_token_help(tok))
        return ERR_TOKEN
    return OK


def _resolve_target(name, rinfo):
    """Nome scritto dall'utente -> ('tool:<id>' | 'service:<id>', nome leggibile) tra le AI utilizzabili del server."""
    raw = (name or "").strip().lower()
    tool_id = ALIASES.get(raw, raw)
    for t in rinfo.get("tools") or []:
        if t.get("id") == tool_id and (t.get("remote") or {}).get("usable"):
            return "tool:" + tool_id, t.get("name") or tool_id
    services = {s.get("id"): s for s in rinfo.get("services") or [] if s.get("available")}
    for sid in (raw, tool_id, SERVICE_ALIASES.get(raw), SERVICE_ALIASES.get(tool_id)):
        if sid and sid in services:
            return "service:" + sid, services[sid].get("name") or sid
    return None, None


def cmd_ask(args):
    """Usa da questo PC un'AI del SERVER: una CLI condivisa (es. Claude Code) o un servizio via API (es. Meta Muse,
    Kimi, DeepSeek, Qwen, Mistral, Grok, Perplexity), sempre con i testi anonimizzati dal server."""
    tool_id = ALIASES.get((args.tool or "").lower(), (args.tool or "").lower())
    prompt = (args.prompt or "").strip()
    if not prompt:
        print('Scrivi il prompt.  Esempio:  client ask claude-code "Riassumi questo testo: ..."')
        return ERR_USAGE
    if len(prompt) > 100_000:
        print("Prompt troppo lungo (massimo 100.000 caratteri): per i documenti usa  client send. Nessun dato inviato.")
        return ERR_USAGE
    base, origin = resolve_server(args)
    tok = _token(args)
    code, r = _preflight(base, tok, "richiesta annullata")
    if code:
        return code
    if not r["engine_ready"]:
        print("Il motore del server non e' pronto: richiesta annullata, nessun dato e' stato inviato. Riprova tra poco.")
        return ERR_ENGINE
    rinfo = remote_info(base, tok) if r.get("remote") else None
    if rinfo is None:          # Germano Server 0.52: solo le CLI condivise
        return _ask_harness(base, origin, tok, tool_id, prompt, getattr(args, "model", None) or "")
    target, target_name = _resolve_target(args.tool, rinfo)
    if not target:
        usable = [t.get("id") for t in rinfo.get("tools") or [] if (t.get("remote") or {}).get("usable")]
        usable += [s.get("id") for s in rinfo.get("services") or [] if s.get("available")]
        print(f"«{_clean(args.tool, 30)}» non e' utilizzabile su questo server. Disponibili: {', '.join(usable) or 'nessuna'}. "
              "Dettagli:  client models")
        return ERR_CLI
    fields = {"target": target, "model": getattr(args, "model", None) or "", "prompt": prompt}
    opts = _options_field(r)
    if opts:
        fields["options"] = opts
    body, ctype = _multipart(fields, [])
    headers = {"Content-Type": ctype, **_auth_headers(tok)}
    key = (getattr(args, "key", None) or "").strip()
    if key:
        headers["X-Germano-Provider-Key"] = key
    print(f"{target_name} tramite il Germano Server {base} ({origin}): il server anonimizza il prompt prima di inoltrarlo...")
    try:
        st, raw = _request("POST", base + "/api/remote/v1/ask", data=body, headers=headers, timeout=660)
    except ClientError as e:
        print(f"Richiesta non riuscita: {e}")
        return e.code
    data = _json(raw) or {}
    if st == 200 and data.get("status") == "success":
        model = f" · {_clean(data.get('model'), 60)}" if data.get("model") else ""
        print(f"--- risposta di {_clean(data.get('target_name') or target_name)}{model} ({data.get('seconds')} s; "
              f"{_plural(data.get('entity_count', 0), 'dato oscurato', 'dati oscurati')}, ripristinati da Germano) ---")
        print(data.get("answer", ""))
        return OK
    msg = _clean(data.get("message") or data.get("error") or f"risposta inattesa (HTTP {st})", 800)
    print(f"[{st}] {msg}")
    if st in (401, 403, 404, 503):
        print("Nessun dato e' uscito verso servizi di AI.")
    if st == 403 and data.get("code") == "compliance_lock":
        print("Le opzioni di questo PC non valgono con il profilo PA del server: rimuovile con  client options --reset")
        return ERR_LOCKED
    if data.get("code") == "key_needed":
        print("Indica la tua chiave API con  --key <chiave>  (non viene salvata da nessuna parte).")
    return ERR_TOKEN if st == 401 else ERR_ENGINE if st == 503 else ERR_CLI if st in (400, 403, 404, 429) else ERR_SERVER


def _ask_harness(base, origin, tok, tool_id, prompt, model):
    """Germano Server 0.52: esecuzione di una CLI condivisa (/api/harness/v1/run)."""
    payload = json.dumps({"tool": tool_id, "prompt": prompt, "model": model}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8", **_auth_headers(tok)}
    print(f"{tool_id} sul Germano Server {base} ({origin}): il server anonimizza il prompt prima di inoltrarlo all'AI...")
    try:
        st, raw = _request("POST", base + "/api/harness/v1/run", data=payload, headers=headers, timeout=330)
    except ClientError as e:
        print(f"Richiesta non riuscita: {e}")
        return e.code
    data = _json(raw) or {}
    if st == 200 and data.get("status") == "success":
        ver = f" {_clean(data.get('version'), 20)}" if data.get("version") else ""
        print(f"--- risposta di {_clean(data.get('tool_name') or tool_id)}{ver} (sul server, {data.get('seconds')} s; "
              "dati originali ripristinati da Germano) ---")
        print(data.get("answer", ""))
        return OK
    msg = _clean(data.get("message") or data.get("error") or f"risposta inattesa (HTTP {st})", 800)
    print(f"[{st}] {msg}")
    if st in (401, 403, 404, 503):
        print("Nessun dato e' uscito verso servizi di AI.")
    if st in (403, 404):
        print("Per vedere le AI del server e come usarle da qui:  client models")
    return ERR_TOKEN if st == 401 else ERR_ENGINE if st == 503 else ERR_CLI if st in (403, 404, 429) else ERR_SERVER


# ------------------------------------------------------------------ accesso e opzioni (Germano Server 0.60)
def _login(base, user, password):
    """Accede al server e restituisce il token di sessione ('' se il server non richiede credenziali)."""
    body = json.dumps({"username": user, "password": password, "client": True}, ensure_ascii=False).encode("utf-8")
    st, raw = _request("POST", base + "/api/auth/login", data=body,
                       headers={"Content-Type": "application/json; charset=utf-8"}, timeout=20)
    data = _json(raw) or {}
    if st == 200 and data.get("token"):
        return data["token"]
    if st == 400 and data.get("code") == "auth_disabled":
        return ""
    if st == 404:
        raise ClientError("questo server non ha la gestione utenti (versione precedente alla 0.60): usa il suo token "
                          "con  client config --token <TOKEN>", ERR_TOKEN)
    raise ClientError(_clean(data.get("error") or data.get("message") or f"accesso non riuscito (HTTP {st})", 300),
                      ERR_TOKEN)


def cmd_login(args):
    base, origin = resolve_server(args)
    user = (getattr(args, "user", None) or "").strip()
    password = getattr(args, "password", None)
    if not user:
        user = _ask("Utente: ")
        if not user:
            print("Accesso annullato.")
            return ERR_USAGE
    if password is None:
        password = _ask("Password (non viene mostrata): ", secret=True)
        if not password:
            print("Accesso annullato.")
            return ERR_USAGE
    token = _login(base, user, password)
    cfg = load_config()
    if not cfg.get("server_url") and not getattr(args, "server", None):
        cfg["server_url"] = base          # la sessione vale per questo server: lo si ricorda
    elif getattr(args, "server", None):
        cfg["server_url"] = base
    cfg["token"] = token
    cfg["user"] = user if token else ""
    save_config(cfg)
    if token:
        print(f"Accesso riuscito su {base} come «{_clean(user, 64)}»: sessione salvata in client_config.json "
              "(valida 30 giorni dall'ultimo uso; la password non viene salvata).")
    else:
        print(f"{base} non richiede credenziali: l'accesso dalla rete e' libero.")
    return OK


def cmd_logout(args):
    cfg = load_config()
    tok = cfg.get("token") or ""
    if tok and cfg.get("server_url"):
        try:
            _request("POST", parse_server(cfg["server_url"])[0] + "/api/auth/logout", data=b"{}",
                     headers={"Content-Type": "application/json", **_auth_headers(tok)}, timeout=8)
        except ClientError:
            pass
    cfg["token"] = ""
    cfg["user"] = ""
    save_config(cfg)
    print("Uscito: la sessione e' stata chiusa e rimossa da questo PC.")
    return OK


OPTION_NAMES = {
    "ai_threshold": "soglia di confidenza dell'IA (0 = protezione massima, fino a 0.95)",
    "enable_model_velvet": "modello Velvet Privacy Filter", "enable_model_italian_ner": "modello Italian NER XXL",
    "enable_regex": "regole validate (RegEx)", "censor_person": "nomi", "censor_profession": "professioni e titoli",
    "censor_address": "indirizzi", "censor_cadastre": "dati catastali", "censor_cf_iva": "codici fiscali e P.IVA",
    "censor_email": "email e PEC", "censor_phone": "telefoni", "censor_account": "IBAN, conti e carte",
    "censor_financial": "importi e dati finanziari", "censor_date": "date", "censor_org": "aziende ed enti",
    "censor_plates_docs": "targhe e documenti", "censor_medical": "dati sanitari", "censor_medicine": "farmaci e terapie",
    "censor_legal": "dati giudiziari", "censor_civil_status": "stato civile", "censor_secret": "password e segreti",
    "censor_url": "URL e indirizzi IP",
    "masking": "mascheramento: numbered ([PERSONA_1], ripristinabile), generic ([PERSONA]) o blackout (████)",
}


def cmd_options(args):
    """Mostra o imposta le opzioni di elaborazione di questo PC (valgono solo per le sue richieste)."""
    base, origin = resolve_server(args)
    tok = _token(args)
    code, r = _preflight(base, tok, "opzioni non lette")
    if code:
        return code
    rinfo = remote_info(base, tok)
    if rinfo is None:
        print("Questo server non supporta le opzioni dei client (versione precedente alla 0.60).")
        return ERR_SERVER
    locked = bool(rinfo.get("locked"))
    cfg = load_config()
    if getattr(args, "reset", False):
        cfg.pop("options", None)
        save_config(cfg)
        print("Opzioni di questo PC rimosse: valgono quelle del server.")
    sets = getattr(args, "set", None) or []
    if sets:
        if locked:
            print("🔒 Opzioni bloccate dal " + ("profilo di conformità PA del Server: le regole di protezione e i filtri "
                                                "di privacy sono imposti centralmente e non possono essere alterati dal "
                                                "client." if rinfo.get("lock_reason") == "pa"
                                                else "l'amministratore del Server (lock_settings)."))
            return ERR_LOCKED
        new = dict(client_options() or rinfo.get("options") or {})
        for item in sets:
            key, sep, value = item.partition("=")
            key = key.strip()
            if not sep or key not in OPTION_NAMES:
                print(f"Opzione non valida: «{_clean(item, 60)}». Usa nome=valore; nomi: {', '.join(OPTION_NAMES)}.")
                return ERR_USAGE
            v = value.strip()
            if key == "masking":
                new[key] = v.lower()
            elif key == "ai_threshold":
                try:
                    new[key] = float(v.replace(",", "."))
                except ValueError:
                    print(f"Valore non valido per ai_threshold: «{_clean(v, 20)}» (un numero da 0 a 0.95).")
                    return ERR_USAGE
            else:
                new[key] = v.lower() in ("1", "true", "si", "sì", "yes", "on")
        body = json.dumps({"options": new}, ensure_ascii=False).encode("utf-8")
        st, raw = _request("POST", base + "/api/remote/v1/options", data=body,
                           headers={"Content-Type": "application/json; charset=utf-8", **_auth_headers(tok)}, timeout=10)
        data = _json(raw) or {}
        if st == 403:
            print(_clean(data.get("error") or "Opzioni bloccate dal server.", 300))
            return ERR_LOCKED
        if st != 200:
            print(f"[{st}] {_clean(data.get('message') or data.get('error') or 'opzioni non salvate', 300)}")
            return ERR_SERVER
        cfg = load_config()
        cfg["options"] = data["options"]
        save_config(cfg)
        print("Opzioni salvate in client_config.json: valgono per le prossime richieste di questo PC.")
    mine = client_options()
    current = dict(rinfo.get("options") or {}, **(mine if mine and not locked else {}))
    print(f"Profilo del server: {rinfo.get('profile')}" + (" — 🔒 opzioni bloccate (in grigio nel Remote Control)" if locked
                                                           else " — opzioni personalizzabili da questo PC"))
    print("Opzioni in uso per le richieste di questo PC" + (" (personalizzate)" if mine and not locked else " (del server)") + ":")
    for key, label in OPTION_NAMES.items():
        value = current.get(key)
        shown = value if not isinstance(value, bool) else ("sì" if value else "no")
        print(f"  {key:<26} {str(shown):<10} {label}")
    if not locked:
        print("Per cambiarle:  client options --set censor_date=no --set ai_threshold=0.5 --set masking=blackout   "
              "(--reset per tornare a quelle del server)")
    return OK


def _launch_options(rest):
    """Separa le opzioni del Client ('--dry-run', '--forza', '--server', '--token', ovunque prima di un eventuale
    '--') dagli argomenti da passare alla CLI (tutto cio' che segue '--' arriva alla CLI cosi' com'e')."""
    rest = list(rest or [])
    head, tail = (rest[:rest.index("--")], rest[rest.index("--") + 1:]) if "--" in rest else (rest, [])
    opts = {"dry_run": False, "force": False, "server": None, "token": None}
    cli_args = []
    i = 0
    while i < len(head):
        a = head[i]
        key = a.split("=", 1)[0]
        if a in ("--dry-run", "--prova"):
            opts["dry_run"] = True
        elif a in ("--forza", "--force"):
            opts["force"] = True
        elif key in ("--server", "--token"):
            if "=" in a:
                opts[key[2:]] = a.split("=", 1)[1]
            elif i + 1 < len(head):
                opts[key[2:]] = head[i + 1]
                i += 1
            else:
                raise ClientError(f"manca il valore di {key}.", ERR_USAGE)
        else:
            cli_args.append(a)
        i += 1
    return opts, cli_args + tail


def _with_line(value, line):
    lines = [x for x in (value or "").splitlines() if x.strip()]
    if line not in lines:
        lines.append(line)
    return "\n".join(lines)


def _with_item(value, item):
    items = [x.strip() for x in (value or "").split(",") if x.strip()]
    if item not in items:
        items.append(item)
    return ",".join(items)


def build_env(tool_id, base, tok, base_env=None):
    """Ambiente della CLI. Restituisce (env, modifiche, argomenti_extra); modifiche = [(azione, nome, valore)]."""
    env = dict(os.environ if base_env is None else base_env)
    profile = PROFILES.get(tool_id, {})
    anth = f"{base}/g/{tok}" if tok else base   # Claude Code aggiunge /v1/messages
    openai = anth + "/v1"                         # Codex, Aider, Qwen Code e gli SDK OpenAI usano .../v1
    changes, extra = [], []

    def put(name, value):
        env[name] = value
        changes.append(("imposta", name, value))

    if tool_id == "claude-code":
        put("ANTHROPIC_BASE_URL", anth)
        if tok:   # utile se una richiesta non passa dal prefisso /g/<token>
            put("ANTHROPIC_CUSTOM_HEADERS", _with_line(env.get("ANTHROPIC_CUSTOM_HEADERS"), f"X-Germano-Auth: {tok}"))
    elif tool_id in ("codex", "qwen"):
        put("OPENAI_BASE_URL", openai)
    elif tool_id == "aider":
        put("OPENAI_API_BASE", openai)
        put("OPENAI_BASE_URL", openai)
        extra = ["--openai-api-base", openai]
    else:   # profili «manuale» avviati con --forza e CLI non classificate: entrambe le vie
        put("ANTHROPIC_BASE_URL", anth)
        put("OPENAI_BASE_URL", openai)
    put("GERMANO_SERVER", base)
    host = urllib.parse.urlsplit(base).hostname or ""
    for name in ("NO_PROXY", "no_proxy"):   # le richieste verso Germano non devono passare da un proxy aziendale
        put(name, _with_item(env.get(name), host))
    for name in profile.get("rimuovi", ()):
        if name in env:
            del env[name]
            changes.append(("rimuove", name, ""))
    return env, changes, extra


def _mask(text, tok):
    return text.replace(tok, tok[:4] + "…") if tok and len(tok) > 4 else text


def _local_tools():
    out = []
    for t in ai_detect.detect()["tools"]:
        if not t["detected"]:
            continue
        if t["kind"] == "cli":
            label = STATE_LABEL.get(PROFILES.get(t["id"], {}).get("stato"), "da verificare")
        elif t["kind"] == "app":
            label = "applicazione: configurazione manuale"
        else:
            label = "modelli locali: i dati non escono"
        out.append((t["id"], label))
    return out


def _addresses(args):
    """Indirizzi da mostrare nelle istruzioni (segnaposto se il server non e' noto): (openai, anthropic/base, token)."""
    try:
        base, _ = resolve_server(args)
        tok = _token(args)
    except ClientError:
        return "http://<server>:8181/v1", "http://<server>:8181", None
    anth = f"{base}/g/{tok}" if tok else base
    return anth + "/v1", anth, tok


def cmd_launch(args):
    opts, cli_args = _launch_options(args.args)
    dry = bool(getattr(args, "dry_run", False) or opts["dry_run"])
    force = bool(getattr(args, "forza", False) or opts["force"])
    for key in ("server", "token"):   # scritti dopo il nome della CLI: valgono per il Client, non per la CLI
        if opts[key] is not None:
            setattr(args, key, opts[key])
    tool_id = ALIASES.get(args.tool.lower(), args.tool.lower())
    tool = ai_detect.find(tool_id)
    if tool is None:
        print(f"«{_clean(args.tool, 30)}» non e' tra le AI che il Client conosce: "
              f"{', '.join(t['id'] for t in ai_detect.detect(check_ports=False)['tools'])}.")
        return ERR_USAGE
    name = tool["name"]
    if not tool.get("detected"):
        print(f"{name} non risulta installato su questo computer.")
        here = _local_tools()
        print("AI installate qui: " + (", ".join(f"{i} ({lbl})" for i, lbl in here) or "nessuna") + ".")
        try:   # se e' installata sul server la si puo' usare da qui: la esegue il server, protetta dal suo Proxy
            base, _origin = resolve_server(args)
            data, _note = server_tools(base, _token(args), timeout=5.0)
            remote = next((t for t in data.get("tools") or [] if t.get("id") == tool_id), None)
        except ClientError:
            remote = None
        if remote and (remote.get("remote") or {}).get("usable"):
            print(f"{name} e' installata sul Germano Server e si puo' usare da questo PC:  "
                  f"client ask {tool_id} \"il tuo prompt\"")
        elif remote:
            print(f"{name} e' installata sul server, ma da qui non si puo' usare: "
                  f"{_clean((remote.get('remote') or {}).get('reason'), 220)}.")
        else:
            print("Per vedere le AI del server e come usarle da qui:  client models")
        return ERR_CLI
    if tool["kind"] == "service":
        print(f"{name} e' un servizio di modelli locali su questo PC: i dati non escono dal computer e Germano non serve.")
        return ERR_CLI
    if tool["kind"] == "app":
        openai, anth, tok = _addresses(args)
        hint = APPS.get(tool_id, "{name} e' un'applicazione grafica: il Client non puo' configurarla. Se permette un "
                                 "servizio OpenAI personalizzato, imposta l'indirizzo {openai}.")
        print(_mask(hint.format(openai=openai, anthropic=anth, base=anth, name=name), tok))
        return ERR_CLI
    profile = PROFILES.get(tool_id, {"stato": "manuale", "motivo": "CLI non classificata dal Client.",
                                     "istruzioni": "configurala perche' usi l'indirizzo {openai} (formato OpenAI)"})
    if profile["stato"] == "non_supportato":
        print(f"{name}: NON avviato. {profile['motivo']}")
        print(profile.get("alternativa", ""))
        return ERR_CLI
    if profile["stato"] == "manuale" and not force:
        openai, anth, tok = _addresses(args)
        print(f"{name}: NON avviato come «protetto». {profile['motivo']}")
        print(_mask("Per proteggerlo: " + profile["istruzioni"].format(openai=openai, anthropic=anth, base=anth) + ".", tok))
        print(f"Dopo averlo configurato cosi', avvialo con:  client launch {tool_id} --forza")
        return ERR_CLI
    exe = tool["path"]
    base, origin = resolve_server(args)
    tok = _token(args)
    code, r = _preflight(base, tok, f"{name} non avviato")
    if code:
        return code
    env, changes, extra = build_env(tool_id, base, tok)
    print(f"{name} -> Germano Server {base} ({origin})")
    if profile["stato"] == "verificato":
        print(f"  profilo    : collaudato ({profile['nota']})")
    elif profile["stato"] == "documentato":
        print(f"  profilo    : secondo la documentazione della CLI: {profile['nota']}")
    else:
        print(f"  ATTENZIONE : protezione NON garantita dal Client ({profile['motivo']}) Avvio forzato: verifica tu "
              "che la CLI usi l'indirizzo del server.")
    if not r["engine_ready"]:
        print("  nota       : il motore del server non e' ancora pronto: le richieste resteranno bloccate (nessun dato "
              "esce) finche' non lo sara'.")
    print(f"  eseguibile : {exe}")
    if extra or cli_args:
        print(f"  argomenti  : {_mask(' '.join(extra + cli_args), tok)}")
    for action, var, value in changes:
        if action == "imposta":
            print(f"  {var:24} = {_mask(value, tok).replace(chr(10), ' | ')}")
        else:
            print(f"  {var:24}   rimossa (porterebbe la CLI fuori da Germano)")
    if not ai_detect.runnable(exe):
        print(f"{name} e' installato come script PowerShell: il Client non lo avvia. Aprilo tu in una finestra in cui "
              "hai impostato le variabili qui sopra.")
        return ERR_CLI
    if dry:
        print("(prova a vuoto: la CLI non e' stata avviata)")
        return OK
    try:
        subprocess.Popen([exe] + extra + cli_args, env=env, cwd=os.getcwd(), creationflags=CREATE_NEW_CONSOLE)
    except OSError as e:
        print(f"Avvio non riuscito: {e}")
        return ERR_CLI
    print(f"{name} avviato in una nuova finestra.")
    return OK


def cmd_config(args):
    cfg = load_config()
    changed = False
    server = getattr(args, "server", None)
    token = getattr(args, "token", None)
    if server is not None:
        if not server.strip():
            cfg["server_url"] = ""
            print("Indirizzo del server rimosso: si torna alla ricerca automatica in rete.")
        else:
            base, tok_in_url = parse_server(server)
            cfg["server_url"] = base
            if tok_in_url and token is None:
                token = tok_in_url
                print("Token preso dall'indirizzo indicato.")
        changed = True
    if token is not None:
        token = token.strip()
        check_token_format(token)
        cfg["token"] = token
        changed = True
    user = (getattr(args, "user", None) or "").strip()
    password = getattr(args, "password", None)
    if user and password:                     # accesso con utente e password: si conserva solo la sessione
        if not cfg.get("server_url"):
            raise ClientError("per accedere indica anche l'indirizzo del server con --server.", ERR_USAGE)
        cfg["token"] = _login(parse_server(cfg["server_url"])[0], user, password)
        cfg["user"] = user if cfg["token"] else ""
        changed = True
    cfg.setdefault("server_url", "")
    cfg.setdefault("token", "")
    cfg.setdefault("discovery_port", discovery.DEFAULT_PORT)
    if changed:
        save_config(cfg)
        print("Configurazione salvata in client_config.json.")
    print(f"  server_url     : {cfg.get('server_url') or '(automatico: ricerca in rete)'}")
    print(f"  accesso        : " + (f"sessione di «{_clean(cfg.get('user'), 64)}»" if cfg.get("token") and cfg.get("user")
                                    else "token impostato" if cfg.get("token") else "nessuna sessione (accesso libero o "
                                                                                     "«client login»)"))
    print(f"  opzioni        : {'personalizzate (client options)' if client_options() else 'quelle del server'}")
    print(f"  discovery_port : {cfg.get('discovery_port')}")
    if changed and cfg.get("server_url"):
        try:
            r = check_server(cfg["server_url"], cfg.get("token") or "", timeout=4.0)
            print(f"Verifica: server raggiungibile, motore {'pronto' if r['engine_ready'] else 'non ancora pronto'}, "
                  f"accesso {r['token']}.")
        except ClientError as e:
            print(f"Verifica: {e}")
    return OK


# ------------------------------------------------------------------ menu interattivo (doppio clic su START_CLIENT.bat)
def _safe(fn, ns):
    """Esegue un comando del menu: un errore non deve mai chiudere la finestra."""
    try:
        return fn(ns)
    except KeyboardInterrupt:
        print("\nOperazione annullata.")
    except ClientError as e:
        print(f"Errore: {e}")
    except Exception as e:   # noqa: BLE001
        print(f"Errore imprevisto ({e.__class__.__name__}: {e}).")
    return ERR_SERVER


def _menu_send():
    text = _ask("Testo da proteggere (invio = nessuno): ")
    if text is None:
        return
    files = []
    print("File da allegare, uno per riga (si possono trascinare nella finestra); invio vuoto per terminare:")
    while len(files) < MAX_ATTACHMENTS:
        p = _ask("  file: ")
        if not p:
            break
        files.append(p.strip().strip('"'))
    _safe(cmd_send, argparse.Namespace(server=None, token=None, prompt=text, files=files))


def _menu_config():
    srv = _ask("Indirizzo del server (es. 192.168.1.10:8181; invio = invariato, «-» = ricerca automatica): ")
    if srv is None:
        return
    server = None if not srv else ("" if srv == "-" else srv)
    if server is None:
        _safe(cmd_config, argparse.Namespace())
    else:
        _safe(cmd_config, argparse.Namespace(server=server, token=None))


def _menu_ask():
    usable = []
    try:
        base, _origin = resolve_server(argparse.Namespace(server=None, token=None))
        tok = _token(argparse.Namespace(token=None))
        rinfo = remote_info(base, tok, timeout=5.0)
        if rinfo:
            usable = [t.get("id") for t in rinfo.get("tools") or [] if (t.get("remote") or {}).get("usable")]
            usable += [s.get("id") for s in rinfo.get("services") or [] if s.get("available")]
        else:
            data, _note = server_tools(base, tok, timeout=5.0)
            usable = [t.get("id") for t in data.get("tools") or [] if (t.get("remote") or {}).get("usable")]
    except ClientError as e:
        print(f"Errore: {e}")
        return
    if not usable:
        print("Il server non offre AI utilizzabili da qui: vedi la voce «AI e modelli del server».")
        return
    tool = _ask(f"  Quale AI del server ({', '.join(usable)}; invio = {usable[0]}): ")
    if tool is None:
        return
    model = _ask("  Modello (obbligatorio per i servizi via API, es. deepseek-chat; invio = predefinito): ")
    key = _ask("  La tua chiave API (solo se il servizio la richiede; non viene salvata): ", secret=True)
    prompt = _ask("  Prompt: ")
    if prompt:
        _safe(cmd_ask, argparse.Namespace(server=None, token=None, tool=tool or usable[0], prompt=prompt,
                                          model=model or None, key=key or None))


def interactive():
    print("=" * 64)
    print(f"  GERMANO CLIENT v{get_version()}  -  harness LAN per le AI")
    print("=" * 64)
    _safe(cmd_status, argparse.Namespace(server=None, token=None))
    here = _local_tools()
    print("AI su questo PC: " + (", ".join(f"{i} ({lbl})" for i, lbl in here) or "nessuna"))
    actions = {
        "1": ("Cerca il server sulla rete", lambda: _safe(cmd_discover, argparse.Namespace(timeout=1.5))),
        "2": ("Stato della connessione", lambda: _safe(cmd_status, argparse.Namespace(server=None, token=None))),
        "3": ("AI e modelli del server", lambda: _safe(cmd_models, argparse.Namespace(server=None, token=None))),
        "4": ("Chiedi a un'AI del server (anche Meta Muse, Kimi, DeepSeek, Qwen, Mistral, Grok...)", _menu_ask),
        "5": ("Avvia una CLI protetta (installata su questo PC)", None),
        "6": ("Proteggi un testo o dei file", _menu_send),
        "7": ("Imposta il server", _menu_config),
        "8": ("Accedi al server (utente e password)", lambda: _safe(cmd_login, argparse.Namespace(server=None, user=None,
                                                                                                   password=None))),
        "9": ("Opzioni di elaborazione di questo PC", lambda: _safe(cmd_options, argparse.Namespace(server=None, token=None,
                                                                                                    set=None, reset=False))),
        "0": ("Esci", None),
    }
    while True:
        print("\nComandi:")
        for k, (label, _) in actions.items():
            print(f"  {k}) {label}")
        c = _ask("> ")
        if c is None or c.lower() in ("0", "q", "esci", "exit", "quit"):
            return OK
        if c == "5":
            clis = [i for i, lbl in _local_tools() if lbl.startswith(("protetta", "da configurare", "NON"))]
            tool = _ask(f"  Quale CLI ({', '.join(clis) or 'nessuna installata qui'}): ")
            if tool:
                _safe(cmd_launch, argparse.Namespace(server=None, token=None, tool=tool, args=[], dry_run=False,
                                                     forza=False))
        elif c in actions and actions[c][1]:
            actions[c][1]()
        elif c:
            print("  Comando non riconosciuto: scegli un numero da 0 a 9.")


def main(argv=None):
    _setup_output()
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--server", default=argparse.SUPPRESS,
                        help="indirizzo del Germano Server (es. http://192.168.1.10:8181)")
    common.add_argument("--token", default=argparse.SUPPRESS, help="token di sessione (di solito lo salva «login»)")
    p = argparse.ArgumentParser(prog="client", description="Germano Client - collega questo PC a un Germano Server.",
                                epilog="Codici di uscita: 0 ok, 1 server non raggiungibile o non valido, 2 uso errato, "
                                       "3 accesso richiesto o non valido, 4 motore del server non pronto, "
                                       "5 CLI non installata o non proteggibile, 6 opzioni bloccate dal profilo PA.")
    p.add_argument("--server", default=None, help="indirizzo del Germano Server (es. http://192.168.1.10:8181)")
    p.add_argument("--token", default=None, help="token di sessione (di solito lo salva «login»)")
    p.add_argument("--version", action="version", version=f"Germano Client {get_version()}")
    sub = p.add_subparsers(dest="cmd")
    sp = sub.add_parser("discover", parents=[common], help="cerca i Germano Server sulla rete locale")
    sp.add_argument("--timeout", type=float, default=1.5, help="durata della ricerca in secondi (predefinita 1,5)")
    sub.add_parser("status", parents=[common], help="stato del collegamento: server, motore, accesso, profilo")
    sub.add_parser("models", parents=[common], help="AI e servizi del server e come usarli da qui")
    sa = sub.add_parser("ask", parents=[common], help="usa un'AI del server (CLI condivisa o servizio via API)",
                        epilog='Esempi: ask claude-code "Riassumi: ..." | ask deepseek "..." --model deepseek-chat '
                               '--key sk-... | ask meta "..." --model muse-wonder-1.0 | ask ollama "..." --model llama3')
    sa.add_argument("tool", help="AI o servizio del server (vedi: models)")
    sa.add_argument("prompt", help="testo della richiesta (anonimizzato dal server prima di uscire)")
    sa.add_argument("--model", default=None, help="modello da usare (obbligatorio per i servizi via API)")
    sa.add_argument("--key", default=None, help="la tua chiave API del servizio (non viene salvata)")
    sg = sub.add_parser("login", parents=[common], help="accede al server con utente e password (gestione utenti)")
    sg.add_argument("--user", default=None, help="nome utente (se manca viene chiesto)")
    sg.add_argument("--password", default=None, help="password (se manca viene chiesta senza mostrarla)")
    sub.add_parser("logout", parents=[common], help="chiude la sessione sul server e la toglie da questo PC")
    so = sub.add_parser("options", parents=[common], help="opzioni di elaborazione di questo PC (soglia, modelli, "
                                                          "categorie, mascheramento)")
    so.add_argument("--set", action="append", metavar="NOME=VALORE", help="imposta un'opzione (ripetibile)")
    so.add_argument("--reset", action="store_true", help="torna alle opzioni del server")
    sl = sub.add_parser("launch", parents=[common], help="avvia una CLI di questo PC protetta dal server",
                        epilog="Esempi: launch claude-code --dry-run | launch codex -- --model gpt-5")
    sl.add_argument("--dry-run", action="store_true", help="mostra cosa verrebbe impostato senza avviare la CLI")
    sl.add_argument("--forza", action="store_true", help="avvia anche le CLI da configurare a mano")
    sl.add_argument("tool", help="claude-code, codex, aider, qwen, kimi, deepseek, muse-code, mistral-vibe, grok-build, "
                                 "opencode, gemini-cli...")
    sl.add_argument("args", nargs=argparse.REMAINDER, help="argomenti per la CLI (dopo --)")
    ss = sub.add_parser("send", parents=[common], help="protegge un testo e dei file e mostra il testo protetto")
    ss.add_argument("prompt", nargs="?", default="")
    ss.add_argument("files", nargs="*")
    sc = sub.add_parser("config", parents=[common], help="mostra o salva il server (e l'accesso) in client_config.json")
    sc.add_argument("--user", default=None, help="accede con questo utente (con --password)")
    sc.add_argument("--password", default=None, help="password dell'utente (non viene salvata)")
    args = p.parse_args(argv)
    handlers = {"discover": cmd_discover, "status": cmd_status, "models": cmd_models, "ask": cmd_ask,
                "launch": cmd_launch, "send": cmd_send, "config": cmd_config, "login": cmd_login,
                "logout": cmd_logout, "options": cmd_options}
    try:
        if not args.cmd:
            return interactive()
        return handlers[args.cmd](args)
    except ClientError as e:
        print(f"Errore: {e}")
        return e.code
    except KeyboardInterrupt:
        print("\nOperazione annullata.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
