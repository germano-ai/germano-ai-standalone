"""AI condivise: i computer della rete usano le AI a riga di comando installate su QUESTO Germano Server.

Il server esegue la CLI senza strumenti (nessun comando, nessun file), con il prompt sullo standard input e con il
Proxy locale di Germano come indirizzo del servizio: verso il cloud esce solo testo anonimizzato, la risposta torna
con i dati originali e, se il motore non e' attivo, il Proxy blocca la richiesta (nessun dato esce in chiaro).

Le CLI condivise usano l'account e le credenziali di questo computer: per questo la condivisione resta disattivata
finche' l'amministratore non la attiva (share_ai_tools, Impostazioni > Accesso dalla rete).
"""
import os
import re
import subprocess
import threading
import time

from . import common

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_PROMPT = 100_000          # caratteri per richiesta
MAX_ANSWER = 400_000          # caratteri di risposta restituiti al client
RUN_TIMEOUT = 300             # secondi per una richiesta
_SLOTS = threading.BoundedSemaphore(2)   # richieste contemporanee: le CLI sono processi pesanti
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\[\]-]{0,63}$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Variabili che porterebbero la CLI fuori da Germano o le farebbero credere di essere dentro un'altra sessione.
_DROP_ENV = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "CLAUDECODE",
             "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
             "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_PID")

# CLI che il server sa eseguire per conto dei client, in modo non interattivo e senza strumenti.
PROFILES = {
    "claude-code": {
        "state": "verificato",
        # Esecuzione minima e non interattiva: -p risponde e termina; --bare salta hook, plugin, LSP, auto-memory,
        # attribuzione, letture del keychain e OAuth (usa solo ANTHROPIC_API_KEY); --tools "" niente strumenti
        # (nessun comando ne' file sul server); nessun server MCP, nessun comando, nessuna sessione salvata.
        "args": ["-p", "--output-format", "text", "--bare", "--tools", "", "--strict-mcp-config",
                 "--disable-slash-commands", "--no-session-persistence"],
        "env": "ANTHROPIC_BASE_URL",
        "needs": "ANTHROPIC_API_KEY",
        "model_flag": "--model",
    },
}

# Perche' un'AI installata sul server non si puo' usare dai client.
NOT_REMOTE = {
    "antigravity": "applicazione grafica (IDE): si usa solo davanti al server e i suoi modelli passano dai servizi di "
                   "Google, non dal Proxy di Germano",
    "claude-desktop": "applicazione grafica: si collega direttamente a claude.ai e non passa da Germano; dai client "
                      "usa claude-code",
    "cursor": "applicazione grafica: costruisce i prompt sui propri server, non e' proteggibile",
    "windsurf": "applicazione grafica: usa i propri servizi, non passa dal Proxy di Germano",
    "gemini-cli": "usa il protocollo Gemini di Google, che il Proxy non gestisce: non sarebbe protetta",
    "codex": "eseguirebbe comandi sul server: per sicurezza non e' condivisa; installala sul PC client e usa "
             "«client launch codex»",
    "aider": "modificherebbe file sul server: per sicurezza non e' condivisa; installala sul PC client e usa "
             "«client launch aider»",
    "qwen": "eseguirebbe comandi sul server: per sicurezza non e' condivisa; installala sul PC client e usa "
            "«client launch qwen»",
    "kimi": "va configurata a mano nel suo config.toml: non e' condivisa",
    "deepseek": "non e' una CLI ufficiale: non e' condivisa; usa claude-code con il servizio Anthropic di DeepSeek",
}


class HarnessError(RuntimeError):
    status = 502


class HarnessBusy(HarnessError):
    status = 429


class HarnessBlocked(HarnessError):
    """Il Proxy ha bloccato la richiesta (motore non attivo): nessun dato e' uscito."""
    status = 503


def catalog(tools, sharing):
    """AI rilevate su questo computer, con la possibilita' (o il motivo per cui no) di usarle dai client."""
    out = []
    for t in tools or []:
        if not t.get("detected"):
            continue
        item = {k: t.get(k) for k in ("id", "name", "kind", "version")}
        prof = PROFILES.get(t.get("id")) if t.get("kind") == "cli" else None
        if prof and sharing:
            item["remote"] = {"usable": True, "state": prof["state"], "how": f'client ask {t["id"]} "..."'}
        elif prof:
            item["remote"] = {"usable": False, "reason": "condivisione delle AI disattivata sul server "
                                                         "(Impostazioni > Accesso dalla rete)"}
        elif t.get("kind") == "service":
            item["remote"] = {"usable": False, "reason": "modelli locali del server: si usano tramite il Proxy se il "
                                                         "«Servizio OpenAI o compatibile» del server punta a questo "
                                                         "servizio"}
        else:
            item["remote"] = {"usable": False, "reason": NOT_REMOTE.get(t.get("id"), "non utilizzabile da remoto")}
        out.append(item)
    return out


def valid_model(model):
    return not model or bool(_MODEL_RE.match(model))


def _clean(text, limit):
    text = _CTRL_RE.sub("", text or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n[... risposta troncata da Germano ...]"


def _kill_tree(proc):
    try:
        import psutil
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        parent.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run(tool_id, exe, prompt, port, model=None, timeout=RUN_TIMEOUT):
    """Esegue la CLI del server per un client. Restituisce {"answer", "seconds"}; solleva HarnessError."""
    prof = PROFILES.get(tool_id)
    if not prof:
        raise HarnessError(f"{tool_id} non e' tra le AI che il server sa eseguire per i client.")
    needs = prof.get("needs")
    if needs and not os.environ.get(needs):
        raise HarnessError(f"Per condividere {tool_id} il server deve avere la variabile {needs} (la chiave API del "
                           f"servizio). Impostala e riavvia Germano sul server.")
    if not _SLOTS.acquire(blocking=False):
        raise HarnessBusy("Il server sta gia' eseguendo altre richieste per i client: riprova tra poco.")
    try:
        args = [exe] + prof["args"] + ([prof["model_flag"], model] if model else [])
        env = dict(os.environ)
        for k in _DROP_ENV:
            env.pop(k, None)
        env[prof["env"]] = f"http://127.0.0.1:{port}"   # il Proxy locale: anonimizza, ripristina, blocca se serve
        for var in ("NO_PROXY", "no_proxy"):
            items = [x for x in (env.get(var) or "").split(",") if x.strip()]
            env[var] = ",".join(items + [h for h in ("127.0.0.1", "localhost") if h not in items])
        workdir = os.path.join(common.STATE_DIR, "harness")   # cartella vuota: la CLI non trova progetti ne' file
        os.makedirs(workdir, exist_ok=True)
        t0 = time.time()
        try:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    cwd=workdir, env=env, creationflags=NO_WINDOW)
        except OSError as e:
            raise HarnessError(f"Impossibile avviare {tool_id} sul server: {e}") from None
        try:
            out, err = proc.communicate(prompt.encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
            raise HarnessError(f"{tool_id} non ha risposto entro {timeout} s: richiesta interrotta.") from None
        seconds = round(time.time() - t0, 1)
        text = out.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            detail = _clean((text + "\n" + err.decode("utf-8", errors="replace")).strip(), 600)
            if "Motore IA di Germano" in detail or "germano_privacy_block" in detail:
                raise HarnessBlocked("Il Proxy di Germano ha bloccato la richiesta (motore non attivo o non "
                                     f"disponibile): nessun dato e' uscito. Dettaglio: {detail}")
            raise HarnessError(f"{tool_id} sul server ha terminato con errore (codice {proc.returncode}): {detail}")
        return {"answer": _clean(text, MAX_ANSWER), "seconds": seconds}
    finally:
        _SLOTS.release()
