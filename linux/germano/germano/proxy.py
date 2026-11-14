"""Proxy API locale per IDE e agenti IA (OpenAI Chat Completions, OpenAI Responses, Anthropic Messages).

Uscita: tutti i testi, gli argomenti dei tool, le immagini e i documenti allegati vengono anonimizzati.
Se qualcosa non puo' essere anonimizzato la richiesta viene BLOCCATA (fail-safe), mai inoltrata in chiaro.
Ritorno: le etichette ([PERSONA_1]) vengono rimesse in chiaro, anche in streaming SSE.

Busta del protocollo e contenuto dell'utente (turno 26): le chiavi tecniche di _STRUCT_KEYS («type», «id», «name»,
«status»...) si saltano SOLO nei blocchi del protocollo. Gli argomenti dei tool (tool_use.input, function.arguments,
functionCall.args di Gemini...) sono dati dell'utente con chiavi scelte dallo strumento: li si visita in modo «libero»,
cioe' ogni stringa (e ogni chiave) viene anonimizzata, qualunque sia il suo nome. Prima del turno 26 un argomento
chiamato «name» o «id» usciva in chiaro (riprodotto nel turno 25). In piu', dopo l'anonimizzazione, un controllo
finale indipendente cerca in tutto il corpo i dati appena rilevati: se uno e' rimasto in un campo non anonimizzato,
la richiesta viene bloccata (leak_check).
"""
import base64
import codecs
import json
import re

from .vault import restore_text


class ProxyBlock(Exception):
    """Errore che impedisce l'inoltro della richiesta (blocco di sicurezza)."""

    def __init__(self, message, status=500):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------------------------
# Uscita: raccolta dei contenuti da anonimizzare
# ------------------------------------------------------------------------------------------------
# Chiavi tecniche della busta del protocollo: si saltano solo nei blocchi del protocollo, mai negli argomenti dei tool.
# «citations» non c'e' piu' (turno 26): le citazioni contengono il testo citato dei documenti («cited_text»), che il
# client rimanda nella cronologia con i dati veri ripristinati.
_STRUCT_KEYS = {
    "type", "role", "id", "model", "object", "call_id", "tool_call_id", "tool_use_id", "item_id", "name",
    "previous_response_id", "signature", "encrypted_content", "encrypted_index", "media_type", "mime_type", "detail",
    "format", "cache_control", "status", "index", "file_id", "container_id", "voice", "server_label",
}
_SKIP_BLOCK_TYPES = {"thinking", "redacted_thinking"}
# Blocchi di chiamata a uno strumento: «input» e' il contenuto dell'utente (chiavi scelte dallo strumento)
_TOOL_INPUT_TYPES = {"tool_use", "server_tool_use", "mcp_tool_use"}
# Gemini: parts[].functionCall.args e parts[].functionResponse.response sono contenuto dell'utente
_FREE_CHILD_KEYS = {"functionCall": {"args"}, "functionResponse": {"response"}, "function_call": {"args"},
                    "function_response": {"response"}}
# Nome di un partecipante (OpenAI Chat, ruoli user/assistant/system/developer): puo' essere un nome di persona
_PARTICIPANT_ROLES = {"user", "assistant", "system", "developer"}
_PARTICIPANT_NAME_RE = re.compile(r"[^A-Za-z0-9_-]")
# Campi di primo livello visitati: contenuti della conversazione e identificativi dell'utente finale
_PAYLOAD_KEYS = ("messages", "input", "instructions", "system", "prompt", "contents", "metadata", "user")
_MEDIA_EXT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
    "image/bmp": ".bmp", "image/tiff": ".tif", "application/pdf": ".pdf", "text/plain": ".txt",
    "text/csv": ".csv", "text/html": ".html", "application/json": ".json", "text/markdown": ".md",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/rtf": ".rtf", "text/xml": ".xml", "application/xml": ".xml",
}
_DATA_URL_RE = re.compile(r"^data:([\w.+\-]+/[\w.+\-]+)?((?:;[\w\-]+=[^;,]*)*)(;base64)?,(.*)$", re.S)
# Riga tecnica di attribuzione che Claude Code mette nel prompt di sistema (versione, punto d'ingresso, impronta): non
# contiene dati personali e non va alterata (il servizio la usa per riconoscere il client). Solo la forma esatta,
# valori fatti di lettere, cifre, punti e trattini: qualsiasi altro testo viene anonimizzato come sempre.
_ATTRIBUTION_RE = re.compile(r"^x-anthropic-billing-header:(?: ?[a-z_]{1,40}=[\w.\-]{0,80};?){1,12}\s*$")


class Job:
    """Contenuti di una richiesta da anonimizzare. Un testo ripetuto (stessa stringa in piu' punti della cronologia,
    stessa chiave in molti oggetti) si analizza una sola volta: `setters[i]` lo riscrive in tutti i punti.
    `collected` = posizioni (contenitore, chiave) dei testi raccolti: servono al controllo finale (leak_check), che
    cerca i dati rilevati in tutte le ALTRE stringhe del corpo."""

    def __init__(self):
        self.texts = []
        self.setters = []
        self.media = []  # (mime, bytes, setter, filename)
        self.finalizers = []
        self.collected = set()
        self._index = {}
        self._targets = []

    def text(self, value, setter, loc=None):
        if isinstance(value, str) and value.strip():
            if loc is not None:
                self.collected.add((id(loc[0]), loc[1]))
            i = self._index.get(value)
            if i is not None:
                self._targets[i].append(setter)
                return
            targets = [setter]
            self._index[value] = len(self.texts)
            self._targets.append(targets)
            self.texts.append(value)
            self.setters.append(lambda nv, ts=targets: [t(nv) for t in ts])

    def add_media(self, mime, data, setter, filename=None):
        mime = (mime or "").lower().split(";")[0].strip()
        ext = _MEDIA_EXT.get(mime)
        if ext is None:
            raise ProxyBlock(f"Allegato di tipo '{mime or 'sconosciuto'}' non anonimizzabile: richiesta bloccata per sicurezza.", 415)
        name = filename or ("allegato" + ext)
        if not name.lower().endswith(ext):
            name += ext
        self.media.append((mime, data, setter, name))


def _data_url(job, url, setter, filename=None):
    m = _DATA_URL_RE.match(url or "")
    if not m:
        return False
    mime, b64 = m.group(1) or "text/plain", m.group(3)
    payload = m.group(4)
    try:
        data = base64.b64decode(payload) if b64 else payload.encode("utf-8")
    except Exception:
        raise ProxyBlock("Allegato base64 non valido: richiesta bloccata.", 400)

    def _set(new_bytes, mm=mime, st=setter):
        st(f"data:{mm};base64," + base64.b64encode(new_bytes).decode("ascii"))
    job.add_media(mime, data, _set, filename)
    return True


def _json_string(job, container, key, value):
    """Argomenti dei tool (stringa JSON): contenuto dell'utente, visitato in modo libero (ogni chiave e ogni valore),
    poi riserializzato."""
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        job.text(value, lambda v, c=container, k=key: c.__setitem__(k, v), (container, key))
        return
    if isinstance(parsed, str):
        job.text(value, lambda v, c=container, k=key: c.__setitem__(k, v), (container, key))
        return
    holder = [parsed]
    _walk_free(holder, job)

    def _fin(c=container, k=key, h=holder):
        c[k] = json.dumps(h[0], ensure_ascii=False)
    job.finalizers.append(_fin)
    # la stringa riserializzata NON e' segnata come raccolta: il controllo finale la rilegge per intero


def _free_string(job, container, key, value):
    """Stringa di un contenuto libero: allegato (data URL di un tipo gestito) oppure testo da anonimizzare."""
    def setter(nv, c=container, k=key):
        c[k] = nv
    if value.startswith("data:"):
        m = _DATA_URL_RE.match(value)
        if m and (m.group(1) or "").lower() in _MEDIA_EXT:
            _data_url(job, value, setter)
            job.collected.add((id(container), key))
            return
    job.text(value, setter, (container, key))


def _rename_keys(node, renames):
    """Chiavi anonimizzate di un oggetto libero, nello stesso ordine (stessa istanza di dict)."""
    if not any(renames.get(k, k) != k for k in node):
        return
    items = list(node.items())
    node.clear()
    for k, v in items:
        nk = renames.get(k, k)
        while nk in node:                           # due chiavi diverse con la stessa etichetta: nessuna si perde
            nk += " "
        node[nk] = v


def _walk_free(node, job):
    """Contenuto dell'utente (argomenti e risultati strutturati degli strumenti): nessuna chiave e' tecnica, ogni
    stringa - chiavi comprese - passa dall'anonimizzazione. Nessun salto per tipo di blocco."""
    if isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                _free_string(job, node, i, v)
            elif isinstance(v, (dict, list)):
                _walk_free(v, job)
        return
    if not isinstance(node, dict):
        return
    renames = {}
    for k, v in list(node.items()):
        if isinstance(v, str):
            _free_string(job, node, k, v)
        elif isinstance(v, (dict, list)):
            _walk_free(v, job)
        if isinstance(k, str) and k.strip():
            job.text(k, lambda nk, kk=k, r=renames: r.__setitem__(kk, nk))
    job.finalizers.append(lambda n=node, r=renames: _rename_keys(n, r))


def _participant_name(job, node):
    """OpenAI Chat: «name» di un partecipante (user/assistant/system/developer) e' facoltativo e puo' essere il nome di
    una persona; il servizio accetta solo [A-Za-z0-9_-]{1,64}: se contiene un dato, diventa p.es. «PERSONA_1»."""
    original = node.get("name")
    spaced = "".join(" " if c in "_-." else c for c in original)

    def setter(nv, d=node, orig=original, sp=spaced):
        if nv != sp:
            d["name"] = (_PARTICIPANT_NAME_RE.sub("", nv.replace(" ", "_")) or "partecipante")[:64]
    job.text(spaced, setter, (node, "name"))


def _walk(node, job, free_keys=()):
    if isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                job.text(v, lambda nv, c=node, k=i: c.__setitem__(k, nv), (node, i))
            else:
                _walk(v, job)
        return
    if not isinstance(node, dict):
        return
    t = node.get("type")
    if not isinstance(t, str):
        t = None              # «type» con un valore non testuale (es. una lista): prima mandava in errore il Proxy
    if t in _SKIP_BLOCK_TYPES:
        return  # testo generato dal modello (gia' con etichette) e firmato: non va modificato
    if t == "text" and isinstance(node.get("text"), str) and len(node["text"]) < 600 \
            and _ATTRIBUTION_RE.match(node["text"]):
        return  # riga di attribuzione di Claude Code (nessun dato personale)
    if t in ("input_audio", "audio"):
        raise ProxyBlock("Contenuti audio non anonimizzabili (voce = dato biometrico): richiesta bloccata.", 415)
    free = {"input"} if t in _TOOL_INPUT_TYPES else set(free_keys)
    if node.get("role") in _PARTICIPANT_ROLES and isinstance(node.get("name"), str) and node["name"].strip():
        _participant_name(job, node)
    handled = set()
    # OpenAI Chat: {"type":"image_url","image_url":{"url":"data:..."}}
    iu = node.get("image_url")
    if isinstance(iu, dict) and isinstance(iu.get("url"), str):
        _data_url(job, iu["url"], lambda v, d=iu: d.__setitem__("url", v))
        handled.add("image_url")
    elif isinstance(iu, str):  # Responses: {"type":"input_image","image_url":"data:..."}
        _data_url(job, iu, lambda v, d=node: d.__setitem__("image_url", v))
        handled.add("image_url")
    # OpenAI file: {"type":"file","file":{"file_data":"data:...","filename":...}}
    fobj = node.get("file")
    if isinstance(fobj, dict) and isinstance(fobj.get("file_data"), str):
        if not _data_url(job, fobj["file_data"], lambda v, d=fobj: d.__setitem__("file_data", v), fobj.get("filename")):
            raw = fobj["file_data"]

            def _set_raw(v, d=fobj):
                d["file_data"] = v.split(",", 1)[1] if v.startswith("data:") else v
            _data_url(job, "data:application/pdf;base64," + raw, _set_raw, fobj.get("filename"))
        handled.add("file")
    if isinstance(node.get("file_data"), str):  # Responses input_file
        fd = node["file_data"]
        if not _data_url(job, fd, lambda v, d=node: d.__setitem__("file_data", v), node.get("filename")):
            _data_url(job, "data:application/pdf;base64," + fd,
                      lambda v, d=node: d.__setitem__("file_data", v.split(",", 1)[1]), node.get("filename"))
        handled.add("file_data")
    # Anthropic: {"type":"image"|"document","source":{"type":"base64","media_type":...,"data":...}}
    src = node.get("source")
    if isinstance(src, dict):
        st = src.get("type")
        if st == "base64" and isinstance(src.get("data"), str):
            try:
                data = base64.b64decode(src["data"])
            except Exception:
                raise ProxyBlock("Allegato base64 non valido: richiesta bloccata.", 400)
            job.add_media(src.get("media_type"), data,
                          lambda b, d=src: d.__setitem__("data", base64.b64encode(b).decode("ascii")))
        elif st == "text" and isinstance(src.get("data"), str):
            job.text(src["data"], lambda v, d=src: d.__setitem__("data", v), (src, "data"))
        elif st == "content":
            _walk(src.get("content"), job)
        handled.add("source")
    for k, v in list(node.items()):
        if k in handled:
            continue
        if k in free:                              # contenuto dell'utente: visita libera, anche sotto «name»/«id»
            if isinstance(v, str):
                _free_string(job, node, k, v)
            else:
                _walk_free(v, job)
            continue
        if k in _STRUCT_KEYS:
            continue
        if k in ("arguments", "partial_json"):
            if isinstance(v, str):
                _json_string(job, node, k, v)
            else:
                _walk_free(v, job)                 # argomenti gia' come oggetto (alcuni servizi compatibili)
        elif isinstance(v, str):
            job.text(v, lambda nv, c=node, kk=k: c.__setitem__(kk, nv), (node, k))
        elif k in _FREE_CHILD_KEYS and isinstance(v, dict):
            _walk(v, job, _FREE_CHILD_KEYS[k])
        else:
            _walk(v, job)


def collect_payload(payload):
    """Raccoglie dal corpo della richiesta tutti i contenuti da anonimizzare."""
    job = Job()
    for key in _PAYLOAD_KEYS:
        if key not in payload:
            continue
        v = payload[key]
        if isinstance(v, str):
            job.text(v, lambda nv, k=key: payload.__setitem__(k, nv), (payload, key))
        elif key == "metadata":
            _walk_free(v, job)                     # es. metadata.user_id: valori liberi dell'applicazione
        else:
            _walk(v, job)
    return job


# ------------------------------------------------------------------------------------------------
# Controllo finale di non-uscita (turno 26)
# ------------------------------------------------------------------------------------------------
_BINARY_KEYS = {"data", "file_data", "image_url", "url"}
# Valori che per protocollo non contengono dati dell'utente (tipi, ruoli, stati, nomi degli strumenti, firme): un falso
# positivo del rilevamento su una parola come «Read» o «Bash» non deve bloccare ogni richiesta della conversazione.
_CHECK_SKIP_KEYS = {"type", "role", "status", "object", "media_type", "mime_type", "detail", "format", "voice", "model",
                    "name", "signature", "encrypted_content", "encrypted_index", "cache_control"}


def leak_check(payload, job, words):
    """Dopo l'anonimizzazione: cerca i dati appena rilevati (`words`: [(dato, etichetta)]) in tutte le stringhe del
    corpo che NON sono passate dall'anonimizzazione (campi nuovi o sconosciuti, identificativi, strutture che la visita
    non conosce). Restituisce [(percorso, etichetta)] dei punti in cui un dato e' rimasto: il chiamante blocca la
    richiesta. Indipendente da _walk: guarda ogni stringa, tranne i blocchi di ragionamento firmati, i contenuti binari
    (base64, data URL) e i valori tecnici del protocollo (_CHECK_SKIP_KEYS)."""
    from .detect import Propagator
    prop = Propagator()
    for word, label in words:
        prop.add(word, label, "LEAK", None)
    if not prop:
        return []
    found = []

    def scan(value, path):
        for _a, _b, label, _g, _k in prop.find(value):
            found.append((path, label))
            return

    def walk(node, path, free=False):
        # free=True: dentro gli argomenti di uno strumento nessuna chiave e' tecnica (si controlla tutto)
        if isinstance(node, dict):
            typ = node.get("type") if isinstance(node.get("type"), str) else None
            if not free and typ in _SKIP_BLOCK_TYPES:
                return
            for k, v in node.items():
                p = f"{path}.{k}"
                child_free = free or (k == "input" and typ in _TOOL_INPUT_TYPES) or \
                    k in ("args", "response") or k in ("arguments", "partial_json")
                if isinstance(v, str):
                    if (id(node), k) in job.collected or v.startswith("data:"):
                        continue
                    if not child_free and k in _CHECK_SKIP_KEYS:
                        continue
                    if k in _BINARY_KEYS and len(v) > 256:
                        continue
                    if typ == "text" and k == "text" and _ATTRIBUTION_RE.match(v):
                        continue
                    scan(v, p)
                else:
                    walk(v, p, child_free)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                p = f"{path}[{i}]"
                if isinstance(v, str):
                    if (id(node), i) not in job.collected and not v.startswith("data:"):
                        scan(v, p)
                else:
                    walk(v, p, free)

    for key in _PAYLOAD_KEYS:
        v = payload.get(key)
        if isinstance(v, str):
            if (id(payload), key) not in job.collected:
                scan(v, key)
        elif v is not None:
            walk(v, key, key == "metadata")
    return found


# ------------------------------------------------------------------------------------------------
# Ritorno: ripristino dei dati reali
# ------------------------------------------------------------------------------------------------
_SKIP_RESTORE_KEYS = {
    "id", "object", "created", "model", "role", "type", "index", "finish_reason", "stop_reason", "signature",
    "encrypted_content", "item_id", "call_id", "tool_call_id", "tool_use_id", "sequence_number", "status",
    "name", "logprobs", "system_fingerprint", "usage", "service_tier",
}
_JSON_STRING_KEYS = {"arguments", "partial_json"}
_SKIP_RESTORE_TYPES = {"thinking", "redacted_thinking", "thinking_delta", "signature_delta"}


def _restore_free(obj, tag_map):
    """Argomenti degli strumenti nelle risposte: ogni stringa e ogni chiave (come all'andata, nessuna chiave tecnica)."""
    if isinstance(obj, str):
        return restore_text(obj, tag_map)
    if isinstance(obj, list):
        return [_restore_free(x, tag_map) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            nk = restore_text(k, tag_map) if isinstance(k, str) else k
            out[nk if nk not in out else k] = _restore_free(v, tag_map)
        return out
    return obj


def restore_obj(obj, tag_map, free_keys=()):
    if isinstance(obj, str):
        return restore_text(obj, tag_map)
    if isinstance(obj, list):
        return [restore_obj(x, tag_map) for x in obj]
    if isinstance(obj, dict):
        typ = obj.get("type") if isinstance(obj.get("type"), str) else None
        if typ in _SKIP_RESTORE_TYPES:
            return obj
        free = {"input"} if typ in _TOOL_INPUT_TYPES else set(free_keys)
        out = {}
        for k, v in obj.items():
            if k in free:
                # risposta non in streaming: tool_use.input con {"name": "[PERSONA_1]"} torna con il dato vero
                # anche sotto le chiavi tecniche (prima del turno 26 restava l'etichetta, diversamente dallo streaming)
                out[k] = _restore_free(v, tag_map)
            elif k in _JSON_STRING_KEYS and isinstance(v, str):
                out[k] = restore_text(v, tag_map, json_escape=True)
            elif k in _JSON_STRING_KEYS and isinstance(v, (dict, list)):
                out[k] = _restore_free(v, tag_map)
            elif k in _SKIP_RESTORE_KEYS:
                out[k] = v
            elif k in _FREE_CHILD_KEYS and isinstance(v, dict):
                out[k] = restore_obj(v, tag_map, _FREE_CHILD_KEYS[k])
            else:
                out[k] = restore_obj(v, tag_map)
        return out
    return obj


class HoldBuffer:
    """Trattiene in streaming un possibile frammento di etichetta ("[PERS") finche' non si chiude."""

    MAXTAG = 48

    def __init__(self, fn):
        self.fn = fn
        self.buf = ""

    def feed(self, chunk):
        if not chunk:
            return chunk
        self.buf += chunk
        i = self.buf.rfind("[")
        tail = self.buf[i:] if i != -1 else ""
        if i == -1 or "]" in tail or len(tail) > self.MAXTAG or "\n" in tail:
            out, self.buf = self.buf, ""
            return self.fn(out)
        out, self.buf = self.buf[:i], self.buf[i:]
        return self.fn(out) if out else ""

    def flush(self):
        out, self.buf = self.buf, ""
        return self.fn(out) if out else ""


class SSEParser:
    """Parser Server-Sent Events conforme: gestisce \\r\\n, \\n, \\r e chunk spezzati in qualunque punto."""

    _NL = re.compile(r"\r\n|\n|\r")

    def __init__(self):
        self.dec = codecs.getincrementaldecoder("utf-8")("replace")
        self.buf = ""
        self._reset()

    def _reset(self):
        self.event = None
        self.data = []
        self.other = []

    def feed(self, chunk):
        self.buf += self.dec.decode(chunk)
        out = []
        while True:
            m = self._NL.search(self.buf)
            if not m:
                break
            if m.group() == "\r" and m.end() == len(self.buf):
                break  # potrebbe essere \r\n spezzato tra due chunk
            line = self.buf[:m.start()]
            self.buf = self.buf[m.end():]
            ev = self._line(line)
            if ev is not None:
                out.append(ev)
        return out

    def close(self):
        out = []
        self.buf += self.dec.decode(b"", final=True)
        if self.buf:
            ev = self._line(self.buf)
            self.buf = ""
            if ev is not None:
                out.append(ev)
        ev = self._line("")
        if ev is not None:
            out.append(ev)
        return out

    def _line(self, line):
        if line == "":
            if self.event is None and not self.data and not self.other:
                return None
            ev = (self.event, "\n".join(self.data) if self.data else None, list(self.other))
            self._reset()
            return ev
        if line.startswith(":"):
            self.other.append(line)
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            self.event = value
        elif field == "data":
            self.data.append(value)
        else:
            self.other.append(line)
        return None


def serialize_event(name, data, other=()):
    lines = list(other)
    if name is not None:
        lines.append("event: " + name)
    if data is not None:
        lines.extend("data: " + ln for ln in data.split("\n"))
    return "\n".join(lines) + "\n\n"


class StreamRewriter:
    """Ripristina i dati reali negli eventi SSE di OpenAI Chat, OpenAI Responses e Anthropic Messages."""

    def __init__(self, tag_map):
        self.tm = tag_map
        self.bufs = {}

    def _buf(self, key, json_mode):
        b = self.bufs.get(key)
        if b is None:
            tm = self.tm
            b = HoldBuffer((lambda s: restore_text(s, tm, json_escape=True)) if json_mode else (lambda s: restore_text(s, tm)))
            self.bufs[key] = b
        return b

    def process(self, name, data):
        """Restituisce la lista di (nome_evento, dati) da inviare al client."""
        if data is None:
            return [(name, None)]
        if data.strip() == "[DONE]":
            return [(name, data)]
        try:
            obj = json.loads(data)
        except ValueError:
            return [(name, restore_text(data, self.tm))]
        if not isinstance(obj, dict):
            return [(name, json.dumps(restore_obj(obj, self.tm), ensure_ascii=False))]
        before = []
        typ = obj.get("type")
        if isinstance(obj.get("choices"), list):
            self._chat(obj)
        elif typ == "content_block_delta":
            self._anthropic_delta(obj)
        elif typ == "content_block_stop":
            idx = obj.get("index", 0)
            for key in [k for k in self.bufs if k[0] == "anth" and k[1] == idx]:
                rem = self.bufs.pop(key).flush()
                if rem:
                    delta = {"type": "input_json_delta", "partial_json": rem} if key[2] == "json" else {"type": "text_delta", "text": rem}
                    synth = {"type": "content_block_delta", "index": idx, "delta": delta}
                    before.append(("content_block_delta" if name else None, json.dumps(synth, ensure_ascii=False)))
        elif isinstance(typ, str) and typ.startswith("response."):
            obj, synth = self._responses(obj, typ, name)
            if synth:
                before.append(synth)
        else:
            obj = restore_obj(obj, self.tm)
        return before + [(name, json.dumps(obj, ensure_ascii=False))]

    def _chat(self, obj):
        for ch in obj["choices"]:
            if not isinstance(ch, dict):
                continue
            ci = ch.get("index", 0)
            delta = ch.get("delta")
            if isinstance(delta, dict):
                for field in ("content", "reasoning_content", "reasoning", "refusal"):
                    if isinstance(delta.get(field), str):
                        delta[field] = self._buf(("chat", ci, field), False).feed(delta[field])
                tcs = delta.get("tool_calls")
                if isinstance(tcs, list):
                    for tc in tcs:
                        fn = tc.get("function") if isinstance(tc, dict) else None
                        if isinstance(fn, dict) and isinstance(fn.get("arguments"), str):
                            fn["arguments"] = self._buf(("chat", ci, "tool", tc.get("index", 0)), True).feed(fn["arguments"])
            if isinstance(ch.get("message"), dict):
                ch["message"] = restore_obj(ch["message"], self.tm)
            if ch.get("finish_reason"):
                if not isinstance(delta, dict):
                    delta = {}
                    ch["delta"] = delta
                for key in [k for k in self.bufs if k[0] == "chat" and k[1] == ci]:
                    rem = self.bufs.pop(key).flush()
                    if not rem:
                        continue
                    if key[2] == "tool":
                        tcs = delta.setdefault("tool_calls", [])
                        entry = next((t for t in tcs if isinstance(t, dict) and t.get("index", 0) == key[3]), None)
                        if entry is None:
                            entry = {"index": key[3], "function": {"arguments": ""}}
                            tcs.append(entry)
                        fnd = entry.setdefault("function", {})
                        fnd["arguments"] = (fnd.get("arguments") or "") + rem
                    else:
                        delta[key[2]] = (delta.get(key[2]) or "") + rem

    def _anthropic_delta(self, obj):
        idx = obj.get("index", 0)
        d = obj.get("delta")
        if not isinstance(d, dict):
            return
        dt = d.get("type")
        if dt == "text_delta" and isinstance(d.get("text"), str):
            d["text"] = self._buf(("anth", idx, "text"), False).feed(d["text"])
        elif dt == "input_json_delta" and isinstance(d.get("partial_json"), str):
            d["partial_json"] = self._buf(("anth", idx, "json"), True).feed(d["partial_json"])
        elif isinstance(dt, str) and dt in _SKIP_RESTORE_TYPES:
            pass
        else:
            obj["delta"] = restore_obj(d, self.tm)

    def _responses(self, obj, typ, name):
        def key_for(base):
            return ("resp", base, obj.get("item_id"), obj.get("output_index"), obj.get("content_index"), obj.get("summary_index"))
        if typ.endswith(".delta") and isinstance(obj.get("delta"), str):
            base = typ[:-6]
            json_mode = base.endswith("_arguments")
            obj["delta"] = self._buf(key_for(base), json_mode).feed(obj["delta"])
            return obj, None
        synth = None
        if typ.endswith(".done"):
            base = typ[:-5]
            b = self.bufs.pop(key_for(base), None)
            if b is not None:
                rem = b.flush()
                if rem:
                    s = {"type": base + ".delta", "delta": rem}
                    for k in ("item_id", "output_index", "content_index", "summary_index", "sequence_number"):
                        if k in obj:
                            s[k] = obj[k]
                    synth = (base + ".delta" if name else None, json.dumps(s, ensure_ascii=False))
        return restore_obj(obj, self.tm), synth
