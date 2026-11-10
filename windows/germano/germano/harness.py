"""CLI di AI eseguite da Germano: Harness AI di questo computer e AI condivise con i computer della rete.

Il server esegue la CLI senza strumenti (nessun comando, nessun file), con il prompt sullo standard input e con il
Proxy locale di Germano come indirizzo del servizio: verso il cloud esce solo testo anonimizzato, la risposta torna
con i dati originali e, se il motore non e' attivo, il Proxy blocca la richiesta (nessun dato esce in chiaro).

Due profili per Claude Code:
- condiviso (PROFILES, client della rete): --bare, solo con la chiave ANTHROPIC_API_KEY del server; le CLI condivise
  usano l'account e le credenziali di questo computer, per questo la condivisione resta disattivata finche'
  l'amministratore non la attiva (share_ai_tools, Impostazioni > Accesso dalla rete);
- locale (LOCAL_PROFILES, Harness AI di chi usa questo computer): --restricted, con l'accesso gia' configurato
  dall'utente (abbonamento o chiave), senza strumenti, senza server MCP e senza le impostazioni utente (hook).
Dalla 0.70 l'esecuzione e' in streaming (--output-format stream-json): la risposta compare man mano nell'Harness e
nella Glass Window, e l'interruzione termina subito l'albero dei processi della CLI.
"""
import json
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
        # streaming per l'Harness AI (Remote Control, Germano Client): stessi limiti, uscita evento per evento
        "stream_args": ["-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--bare",
                        "--tools", "", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"],
    },
}
# Nessun testo libero tra gli argomenti: le CLI installate con npm sono file .cmd e cmd.exe interpreterebbe i caratteri
# speciali (iniezione di comandi). Prompt e istruzioni passano SOLO dallo standard input; il modello e' validato
# (_MODEL_RE: lettere, cifre e . _ : [ ] -).

# CLI per l'Harness AI di chi usa QUESTO computer: il suo accesso (abbonamento o chiave), mai strumenti.
# --restricted ignora le impostazioni dell'utente (hook, plugin) e toglie gli strumenti che eseguono codice;
# --tools "" toglie anche tutti gli altri; --strict-mcp-config esclude i server MCP. Le richieste passano comunque dal
# Proxy di Germano (ANTHROPIC_BASE_URL), che anonimizza tutto cio' che esce (anche il prompt di sistema della CLI).
LOCAL_PROFILES = {
    "claude-code": {
        "state": "verificato",
        "stream_args": ["-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
                        "--restricted", "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
                        "--no-session-persistence"],
        "env": "ANTHROPIC_BASE_URL",
        "needs": None,
        "model_flag": "--model",
    },
}

# Perche' un'AI installata sul server non si puo' eseguire per i client (e con che cosa la si usa comunque protetta).
_AGENT = ("agente che eseguirebbe comandi o modificherebbe file sul server: per sicurezza il server non lo esegue per "
          "i client")
NOT_REMOTE = {
    "antigravity": "applicazione grafica (IDE): si usa solo davanti al server e i suoi modelli passano dai servizi di "
                   "Google, non dal Proxy di Germano. Per i modelli Gemini usa il servizio «Google Gemini» della chat",
    "claude-desktop": "applicazione grafica: si collega direttamente a claude.ai e non passa da Germano; usa claude-code "
                      "o il servizio «Anthropic» della chat",
    "chatgpt": "applicazione grafica: si collega direttamente a OpenAI e non passa da Germano; usa il servizio «OpenAI» "
               "della chat",
    "cursor": "applicazione grafica: costruisce i prompt sui propri server, non e' proteggibile",
    "windsurf": "applicazione grafica: usa i propri servizi, non passa dal Proxy di Germano",
    "kiro": "applicazione grafica: usa i servizi di Amazon, non passa dal Proxy di Germano",
    "trae": "applicazione grafica: usa i propri servizi, non passa dal Proxy di Germano",
    "zed": "editor: i suoi modelli si collegano al Proxy solo se configurati sul PC che lo usa (Base URL di Germano)",
    "gemini-cli": _AGENT + "; per i modelli Gemini usa il servizio «Google Gemini» della chat",
    "jules": "agente di Google che lavora sui repository nel cloud: non passa da Germano",
    "codex": _AGENT + "; installala sul PC client e usa «client launch codex», oppure il servizio «OpenAI» della chat",
    "aider": _AGENT + "; installala sul PC client e usa «client launch aider»",
    "qwen": _AGENT + "; per i modelli Qwen usa il servizio «Qwen» della chat, oppure installala sul PC client "
                     "(«client launch qwen»)",
    "kimi": _AGENT + "; per i modelli Kimi usa il servizio «Kimi (Moonshot AI)» della chat, oppure collega la CLI del tuo "
                     "PC al Proxy (base_url .../p/moonshot/v1 nel suo config.toml)",
    "deepseek": _AGENT + "; per i modelli DeepSeek usa il servizio «DeepSeek» della chat (o .../p/deepseek/v1 dal tuo PC)",
    "muse-code": _AGENT + "; per Muse Wonder e Muse Spark usa il servizio «Meta Muse» della chat (o .../p/meta/v1 dal "
                          "tuo PC)",
    "mistral-vibe": _AGENT + "; per i modelli Mistral usa il servizio «Mistral» della chat (o .../p/mistral/v1 dal tuo PC)",
    "grok-build": _AGENT + "; per i modelli Grok usa il servizio «Grok (xAI)» della chat (o .../p/xai/v1 dal tuo PC)",
    "perplexity": "pplx interroga la ricerca web di Perplexity (nessuna versione ufficiale per Windows): per i modelli "
                  "Sonar usa il servizio «Perplexity» della chat",
    "copilot-cli": _AGENT + " e usa i servizi di GitHub, che non passano dal Proxy di Germano",
    "cursor-agent": _AGENT + " e usa i servizi di Cursor, che non passano dal Proxy di Germano",
    "kiro-cli": _AGENT + " e usa i servizi di Amazon, che non passano dal Proxy di Germano",
    "opencode": _AGENT + "; dal tuo PC si collega al Proxy come fornitore compatibile OpenAI (Base URL .../v1)",
    "goose": _AGENT + "; dal tuo PC si collega al Proxy come fornitore compatibile OpenAI (Base URL .../v1)",
    "cline": _AGENT,
    "kilo": _AGENT,
    "amp": _AGENT + " e usa i servizi di Sourcegraph",
    "droid": _AGENT + " e usa i servizi di Factory",
    "crush": _AGENT + "; dal tuo PC si collega al Proxy come fornitore compatibile OpenAI (Base URL .../v1)",
}
# Servizi di modelli locali del server utilizzabili dalla chat del Remote Control (germano/providers.py)
_LOCAL_SERVICES = {"ollama": "ollama", "lm-studio": "lmstudio"}


class HarnessError(RuntimeError):
    status = 502


class HarnessBusy(HarnessError):
    status = 429


class HarnessBlocked(HarnessError):
    """Il Proxy ha bloccato la richiesta (motore non attivo): nessun dato e' uscito."""
    status = 503


class HarnessInterrupted(Exception):
    """Esecuzione interrotta dall'utente (Glass Window): l'albero dei processi della CLI e' stato terminato."""


def catalog(tools, sharing):
    """AI rilevate su questo computer, con la possibilita' (o il motivo per cui no) di usarle dai client."""
    out = []
    for t in tools or []:
        if not t.get("detected"):
            continue
        item = {k: t.get(k) for k in ("id", "name", "vendor", "kind", "version", "service")}
        prof = PROFILES.get(t.get("id")) if t.get("kind") == "cli" else None
        if prof and sharing:
            item["remote"] = {"usable": True, "state": prof["state"], "how": f'client ask {t["id"]} "..."'}
        elif prof:
            item["remote"] = {"usable": False, "reason": "condivisione delle AI disattivata sul server "
                                                         "(Impostazioni > Accesso dalla rete)"}
        elif t.get("id") in _LOCAL_SERVICES:
            item["remote"] = {"usable": False, "service": _LOCAL_SERVICES[t["id"]],
                              "reason": "modelli locali del server: si usano dalla chat del Remote Control (servizio "
                                        f"«{t.get('name')}», nessun dato esce dalla rete locale)"
                                        + ("" if t.get("listening") else "; ora non e' in esecuzione sul server")}
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


def _cli_env(prof, port, scope):
    """Ambiente della CLI: quello di Germano senza le variabili che la porterebbero fuori dal Proxy, con il Proxy
    locale come indirizzo del servizio. Il Proxy anonimizza, blocca se serve e ripristina SOLO i dati di quella
    richiesta (/s/<ambito>: mai il resto del Vault, anche se il prompt chiedesse di ripetere etichette di altri
    documenti)."""
    env = dict(os.environ)
    for k in _DROP_ENV:
        env.pop(k, None)
    env[prof["env"]] = f"http://127.0.0.1:{port}/s/{scope}"
    for var in ("NO_PROXY", "no_proxy"):
        items = [x for x in (env.get(var) or "").split(",") if x.strip()]
        env[var] = ",".join(items + [h for h in ("127.0.0.1", "localhost") if h not in items])
    return env


def germano_env(prof, port, scope):
    """Le SOLE variabili che Germano imposta per la CLI (per la Glass Window: mai l'ambiente completo, che potrebbe
    contenere chiavi)."""
    return {prof["env"]: f"http://127.0.0.1:{port}/s/{scope}", "NO_PROXY": "+127.0.0.1,localhost"}


def _workdir():
    workdir = os.path.join(common.STATE_DIR, "harness")   # cartella vuota: la CLI non trova progetti ne' file
    os.makedirs(workdir, exist_ok=True)
    return workdir


def profile(tool_id, local=False):
    return (LOCAL_PROFILES if local else PROFILES).get(tool_id)


def command_line(tool_id, exe, model=None, local=False):
    """(profilo, argomenti) dell'esecuzione in streaming; profilo None se la CLI non e' eseguibile. Solo argomenti
    fissi e il modello validato: il testo passa dallo standard input."""
    prof = profile(tool_id, local)
    if not prof or not prof.get("stream_args") or not valid_model(model):
        return None, []
    return prof, [exe] + prof["stream_args"] + ([prof["model_flag"], model] if model else [])


def stream_run(tool_id, exe, prompt, port, emit, model=None, scope="harness", local=False, cancel=None,
               timeout=RUN_TIMEOUT):
    """Esegue la CLI in streaming (stream-json) per l'Harness AI. emit(tipo, dato) per ogni evento: "delta" (testo
    della risposta, con le etichette), "thinking", "usage", "cli" (righe della CLI non riconosciute, troncate).
    cancel: oggetto con is_set() e bind_process(proc) (glass.Run). Restituisce {"answer", "seconds", "usage"};
    solleva HarnessError (o HarnessInterrupted se l'utente interrompe)."""
    if cancel is not None and cancel.is_set():
        raise HarnessInterrupted()
    prof, args = command_line(tool_id, exe, model, local)
    if not prof:
        raise HarnessError(f"{tool_id} non e' tra le CLI che Germano sa eseguire nell'Harness.")
    needs = prof.get("needs")
    if needs and not os.environ.get(needs):
        raise HarnessError(f"Per condividere {tool_id} il server deve avere la variabile {needs} (la chiave API del "
                           f"servizio). Impostala e riavvia Germano sul server.")
    if not _SLOTS.acquire(blocking=False):
        raise HarnessBusy("Germano sta gia' eseguendo altre richieste con le CLI: riprova tra poco.")
    try:
        env = _cli_env(prof, port, scope)
        t0 = time.time()
        try:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    cwd=_workdir(), env=env, creationflags=NO_WINDOW)
        except OSError as e:
            raise HarnessError(f"Impossibile avviare {tool_id}: {e}") from None
        if cancel is not None:
            cancel.bind_process(proc)

        def feed():
            try:
                proc.stdin.write(prompt.encode("utf-8"))
                proc.stdin.close()
            except OSError:
                pass

        err_lines = []

        def read_err():
            try:
                for line in proc.stderr:
                    err_lines.append(line)
                    del err_lines[:-80]
            except (OSError, ValueError):
                pass

        expired = []

        def on_timeout():
            expired.append(True)
            _kill_tree(proc)

        threading.Thread(target=feed, daemon=True).start()
        err_thread = threading.Thread(target=read_err, daemon=True)
        err_thread.start()
        timer = threading.Timer(timeout, on_timeout)
        timer.daemon = True
        timer.start()
        parts, usage, final, is_error, streamed = [], {}, None, False, False
        try:
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    emit("cli", line[:2000])
                    continue
                if not isinstance(obj, dict):
                    continue
                typ = obj.get("type")
                if typ == "stream_event":
                    ev = obj.get("event") or {}
                    et = ev.get("type")
                    if et == "content_block_delta":
                        d = ev.get("delta") or {}
                        if d.get("type") == "text_delta" and d.get("text"):
                            streamed = True
                            parts.append(d["text"])
                            emit("delta", d["text"])
                        elif d.get("type") == "thinking_delta" and d.get("thinking"):
                            emit("thinking", d["thinking"])
                    elif et == "message_start":
                        u = (ev.get("message") or {}).get("usage") or {}
                        if u.get("input_tokens") is not None:
                            usage["input_tokens"] = u["input_tokens"]
                            emit("usage", dict(usage))
                    elif et == "message_delta":
                        u = ev.get("usage") or {}
                        if u.get("output_tokens") is not None:
                            usage["output_tokens"] = u["output_tokens"]
                            emit("usage", dict(usage))
                elif typ == "assistant" and not streamed:
                    content = (obj.get("message") or {}).get("content") or []
                    text = "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
                    if text:
                        parts.append(text)
                        emit("delta", text)
                elif typ == "result":
                    final = obj.get("result") if isinstance(obj.get("result"), str) else None
                    is_error = bool(obj.get("is_error")) or obj.get("subtype") not in (None, "success")
                    u = obj.get("usage") or {}
                    for k in ("input_tokens", "output_tokens"):
                        if u.get(k) is not None:
                            usage[k] = u[k]
                    if u:
                        emit("usage", dict(usage))
                elif typ == "system":
                    info = {k: obj.get(k) for k in ("subtype", "model", "apiKeySource", "permissionMode", "tools")
                            if k in obj}
                    emit("cli", json.dumps({"system": info}, ensure_ascii=False)[:2000])
        finally:
            timer.cancel()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
        err_thread.join(2)
        if cancel is not None and cancel.is_set():
            raise HarnessInterrupted()
        if expired:
            raise HarnessError(f"{tool_id} non ha risposto entro {timeout} s: richiesta interrotta.")
        seconds = round(time.time() - t0, 1)
        text = "".join(parts)
        stderr = b"".join(err_lines).decode("utf-8", errors="replace")
        if proc.returncode != 0 or is_error:
            detail = _clean(((final or text) + "\n" + stderr).strip(), 600)
            if "Motore IA di Germano" in detail or "germano_privacy_block" in detail:
                raise HarnessBlocked("Il Proxy di Germano ha bloccato la richiesta (motore non attivo o non "
                                     f"disponibile): nessun dato e' uscito. Dettaglio: {detail}")
            if re.search(r"unknown option|--include-partial-messages|--restricted|stream-json", detail, re.I):
                raise HarnessError(f"La versione di {tool_id} installata non supporta l'esecuzione in streaming "
                                   f"richiesta da Germano 0.80: aggiornala (es. «claude update»). Dettaglio: {detail}")
            raise HarnessError(f"{tool_id} ha terminato con errore (codice {proc.returncode}): {detail}")
        return {"answer": _clean(final if final is not None else text, MAX_ANSWER), "seconds": seconds,
                "usage": usage}
    finally:
        _SLOTS.release()


def run(tool_id, exe, prompt, port, model=None, timeout=RUN_TIMEOUT):
    """Esegue la CLI del server per un client (senza streaming: «client ask» e /api/harness/v1/run).
    Restituisce {"answer", "seconds"}; solleva HarnessError."""
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
        env = _cli_env(prof, port, "harness")
        workdir = _workdir()
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
