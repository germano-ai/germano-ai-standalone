"""Email .eml: intestazioni, corpo testo/HTML, allegati (elaborati o rimossi se non supportati),
messaggi inoltrati annidati."""
import base64
import email
import html as _html
import os
import quopri
import re
from email import policy
from email.headerregistry import HeaderRegistry, UnstructuredHeader

from .. import common
from ..analyzer import Unit, apply_replacements
from . import ProcessingError, is_supported, process_bytes, reraise_control, transform_filename

# Intestazioni che NON si analizzano: struttura MIME, date e marcatori tecnici senza dati personali. TUTTE le altre
# si' (elenco aperto). Fino alla 1.00 valeva un elenco chiuso di intestazioni note: quelle fuori elenco, come
# Envelope-To (Exim), X-Apparently-To, ARC-Authentication-Results («smtp.mailfrom=...» delle email scaricate da
# Gmail), Diagnostic-Code e X-Postfix-Sender delle notifiche di mancata consegna, uscivano in chiaro.
_STRUCTURAL = {
    "mime-version", "content-type", "content-transfer-encoding", "content-disposition", "content-id",
    "content-length", "content-md5", "content-language", "accept-language", "date", "resent-date", "delivery-date",
    "expires", "x-priority", "x-msmail-priority", "importance", "priority", "precedence", "sensitivity", "x-mailer",
    "user-agent", "x-mimeole", "thread-index", "auto-submitted", "x-auto-response-suppress", "x-ms-has-attach",
    "x-ms-tnef-correlator", "x-spam-flag", "x-spam-level", "x-spam-score",
}
_UNFOLD_RE = re.compile(r"\r?\n[ \t]+")
_IMAGE_SUBTYPES = {"png", "jpeg", "jpg", "gif", "bmp", "tiff", "webp"}
_ENCODED_CTE = ("base64", "quoted-printable")
# intestazioni lette e scritte come testo semplice, qualunque sia il loro nome (vedi _header_text e _store_header)
_PLAIN = HeaderRegistry(default_class=UnstructuredHeader, use_default_map=False)


def _ext_for(part):
    ct = part.get_content_type()
    return {
        "application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
        "image/tiff": ".tif", "image/bmp": ".bmp", "image/webp": ".webp", "text/csv": ".csv",
        "application/zip": ".zip", "application/rtf": ".rtf", "text/rtf": ".rtf", "text/xml": ".xml",
        "application/xml": ".xml", "message/rfc822": ".eml",
        "application/x-7z-compressed": ".7z", "application/vnd.rar": ".rar", "application/x-rar-compressed": ".rar",
        "application/gzip": ".gz", "application/x-gzip": ".gz", "application/x-tar": ".tar",
        "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a", "audio/ogg": ".ogg", "audio/flac": ".flac", "audio/x-flac": ".flac",
        "audio/opus": ".opus", "audio/aac": ".aac", "audio/amr": ".amr",
    }.get(ct, ".bin")


def _get_text(part):
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        cs = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(cs, errors="replace")
        except LookupError:
            return payload.decode("utf-8", errors="replace")


def _header_text(part, name, value):
    """Valore DECODIFICATO di un'intestazione, su una riga sola. `_headers` conserva il testo grezzo del file: le
    parole codificate RFC 2047 («=?UTF-8?B?TWFyaW8gUm9zc2k=?=», normali appena c'e' una lettera accentata) vanno
    decodificate PRIMA dell'analisi, altrimenti il nome o l'indirizzo che contengono non viene riconosciuto e resta
    nel file (chi lo riceve lo decodifica); in ripristino le etichette dentro una parola codificata non si
    troverebbero. Si decodifica come testo semplice, qualunque sia l'intestazione: il parser «strutturato» di Python
    per gli indirizzi rilegge «[PERSONA_1] <[EMAIL_2]>» come «<>» e in ripristino le etichette sparirebbero."""
    raw = _UNFOLD_RE.sub(" ", str(value)).replace("\r", " ").replace("\n", " ")
    try:
        return str(_PLAIN(name, raw))
    except Exception:
        return raw


def _store_header(part, name, text):
    """Intestazione riscritta, pronta per `_headers`. Se contiene un'etichetta («[PERSONA_1] <[EMAIL_2]>»,
    «<[EMAIL_4]>») va scritta come testo semplice: il parser degli indirizzi la interpreterebbe a modo suo e quello dei
    Message-ID va in errore (IndexError). Cio' che non e' ASCII viene ricodificato in entrambi i casi."""
    if "[" not in text:
        try:
            return part.policy.header_store_parse(name, text)
        except Exception:
            pass
    return (name, _PLAIN(name, text))


def _encoded_message(part):
    """Parte message/* con Content-Transfer-Encoding base64 o quoted-printable: RFC 2046 lo vieta ma alcuni
    programmi la producono (messaggi inoltrati come allegato). Il parser di Python non la decodifica: ne leggerebbe
    il contenuto codificato come un testo qualunque, senza trovarci nulla."""
    if part.get_content_maintype() != "message":
        return False
    return str(part.get("Content-Transfer-Encoding") or "").strip().lower() in _ENCODED_CTE


def _walk(msg):
    """Come Message.walk(), ma senza entrare nel contenuto (non decodificato) delle parti di _encoded_message."""
    yield msg
    if msg.is_multipart() and not _encoded_message(msg):
        for sub in msg.get_payload():
            yield from _walk(sub)


def _encoded_message_bytes(part, pol):
    """Il messaggio annidato di una parte _encoded_message, decodificato."""
    cte = str(part.get("Content-Transfer-Encoding") or "").strip().lower()
    payload = part.get_payload()
    inner = payload[0] if isinstance(payload, list) and payload else payload
    if isinstance(inner, (bytes, bytearray)):
        raw = bytes(inner)
    elif isinstance(inner, str):
        raw = inner.encode("ascii", "surrogateescape")
    else:
        raw = inner.as_bytes(policy=pol)
        if not getattr(inner, "_headers", None):
            raw = raw.lstrip(b"\r\n")           # nessuna intestazione letta: la riga vuota iniziale e' del generatore
    if cte == "base64":
        return base64.b64decode(raw, validate=False)
    return quopri.decodestring(raw)


def process_eml(in_path, out_path, ctx):
    with open(in_path, "rb") as f:
        raw = f.read()
    pol = policy.default.clone(linesep="\r\n") if b"\r\n" in raw[:65536] else policy.default
    msg = email.message_from_bytes(raw, policy=pol)

    units, appliers = [], []
    html_parts, att_parts, encoded_parts = [], [], []
    person = "[PERSONA]" if ctx.settings.get("censor_person", True) else None

    for part in _walk(msg):
        # intestazioni (anche dei messaggi inoltrati come allegato e delle notifiche di consegna)
        hdrs = getattr(part, "_headers", None)
        if hdrs:
            for idx, (name, value) in enumerate(list(hdrs)):
                if name.lower() in _STRUCTURAL:
                    continue
                sval = _header_text(part, name, value)
                if sval.strip():
                    units.append(Unit(sval, context=f"{name}: "))

                    def _ap(new, p=part, i=idx, nm=name):
                        clean = _UNFOLD_RE.sub(" ", str(new)).replace("\r", " ").replace("\n", " ")
                        clean = "".join(" " if c in "\x0b\x0c\x1c\x1d\x1e\x85  " else c for c in clean)
                        p._headers[i] = _store_header(p, nm, clean)
                    appliers.append(_ap)
        if _encoded_message(part):
            encoded_parts.append(part)
            continue
        if part.is_multipart() or part.get_content_maintype() == "message":
            continue
        disp = part.get_content_disposition()
        fname = part.get_filename()
        ctype = part.get_content_type()
        if fname or disp == "attachment":
            att_parts.append(part)
        elif ctype == "text/plain":
            text = _get_text(part)
            if text and text.strip():
                units.append(Unit(text))

                def _ap_text(new, p=part):
                    p.set_content(new, subtype="plain", charset="utf-8")
                appliers.append(_ap_text)
        elif ctype == "text/html":
            html_parts.append(part)
        elif part.get_content_maintype() == "text":
            text = _get_text(part)
            sub = part.get_content_subtype() or "plain"
            if text and text.strip():
                units.append(Unit(text))

                def _ap_other_text(new, p=part, st=sub):
                    p.set_content(new, subtype=st, charset="utf-8")
                appliers.append(_ap_other_text)
        elif part.get_content_maintype() == "image":
            att_parts.append(part)
        elif ctx.anonymize and part.get_content_maintype() not in ("text", "multipart"):
            att_parts.append(part)

    res = ctx.analyze(units) if units else []
    for u, ap, r in zip(units, appliers, res):
        if r:
            try:
                ap(apply_replacements(u.text, r))
            except Exception as e:
                if ctx.anonymize:
                    # mai proseguire con il testo originale: l'email uscirebbe con il dato in chiaro e una semplice nota
                    raise ProcessingError(f"Email non anonimizzabile: un'intestazione o un testo non si puo' "
                                          f"aggiornare ({type(e).__name__}: {e}).") from None
                ctx.note(f"intestazione/testo email non aggiornabile: {e}")

    if html_parts:
        from .markup import transform_html_string
        for part in html_parts:
            ctx.check()
            html = _get_text(part)
            new_html = transform_html_string(html, ctx)
            if new_html != html:
                part.set_content(new_html, subtype="html", charset="utf-8")

    for part in att_parts:
        ctx.check()
        _process_attachment(part, ctx, person)

    for part in encoded_parts:
        ctx.check()
        _process_encoded_message(part, ctx, pol)

    data = msg.as_bytes(policy=pol)
    with open(out_path, "wb") as f:
        f.write(data)
    return None


def _process_encoded_message(part, ctx, pol):
    """Messaggio annidato codificato (base64/quoted-printable): decodificato, elaborato come una email a se' e rimesso
    al suo posto senza codifica. Se non si riesce, in anonimizzazione la parte viene sostituita da una nota."""
    try:
        data = _encoded_message_bytes(part, pol)
        new_data, _name = process_bytes(data, "messaggio.eml", ctx.child())
        inner = email.message_from_bytes(new_data, policy=pol)
        del part["Content-Transfer-Encoding"]
        part.set_payload([inner])
        common.log("Email: messaggio inoltrato (codificato) elaborato.")
        return
    except Exception as e:
        reraise_control(e)
        reason = str(e) or type(e).__name__
    if ctx.anonymize:
        note = (f"Messaggio inoltrato rimosso da Germano AI per proteggere i dati personali ({reason}).\r\n"
                "L'originale e' conservato nella cartella 'processed'.")
        part.clear_content()
        part.set_content(note, subtype="plain", charset="utf-8", disposition="attachment",
                         filename="messaggio_RIMOSSO.txt")
        ctx.note(f"Messaggio inoltrato rimosso per sicurezza ({reason}).")


def _process_attachment(part, ctx, person):
    fname = part.get_filename() or ("allegato" + _ext_for(part))
    base = common.safe_filename(os.path.basename(fname.replace("\\", "/")))
    data = part.get_payload(decode=True)
    if data is None:
        return
    maintype, subtype = part.get_content_maintype(), part.get_content_subtype()
    disp = part.get_content_disposition() or ("inline" if maintype == "image" else "attachment")
    cid = part.get("Content-ID")
    new_name = transform_filename(base, ctx)
    if is_supported(base):
        try:
            new_data, out_name = process_bytes(data, base, ctx.child())
            if out_name != base:  # es. documento.pdf.p7m -> documento.pdf
                new_name = transform_filename(out_name, ctx)
                maintype, subtype = "application", "octet-stream"
            if cid:
                del part["Content-ID"]
            part.set_content(new_data, maintype=maintype, subtype=subtype, disposition=disp, filename=new_name, cid=cid)
            common.log(f"Email: allegato elaborato ({base}).")
            return
        except Exception as e:
            reraise_control(e)      # arresto, tempo scaduto o motore remoto assente: non e' un difetto dell'allegato
            reason = str(e)
    else:
        reason = "formato non supportato"
    if ctx.anonymize:
        note = (f"Allegato '{new_name}' rimosso da Germano AI per proteggere i dati personali ({reason}).\r\n"
                "L'originale e' conservato nella cartella 'processed'.")
        part.set_content(note, subtype="plain", charset="utf-8", disposition="attachment",
                         filename=os.path.splitext(new_name)[0] + "_RIMOSSO.txt")
        ctx.note(f"Allegato email rimosso per sicurezza ({base}: {reason}).")


def plain_text(raw, max_chars=3_000_000, depth=0):
    """Testo leggibile di un messaggio: intestazioni decodificate, corpi di testo decodificati, nomi degli allegati,
    messaggi inoltrati. Serve a riconoscere i file di ritorno dall'AI e agli allegati dell'Harness e di Studio AI, che
    lo anonimizzano prima di inviarlo. Il sorgente grezzo non basta: un corpo in Base64 o un nome scritto come
    «=?UTF-8?B?...?=» non vengono riconosciuti dai modelli, ma chi li riceve li decodifica senza fatica."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    out, size = [], 0

    def add(text):
        nonlocal size
        if text:
            out.append(text)
            size += len(text) + 1

    for part in _walk(msg):
        if size > max_chars:
            break
        for name, value in list(getattr(part, "_headers", None) or []):
            if name.lower() not in _STRUCTURAL:
                add(f"{name}: {_header_text(part, name, value)}")
        if _encoded_message(part):
            if depth < 3:
                try:
                    add("\n" + plain_text(_encoded_message_bytes(part, policy.default), max_chars, depth + 1))
                except Exception:
                    pass
            continue
        if part.is_multipart() or part.get_content_maintype() == "message":
            add("")
            continue
        fname = part.get_filename()
        if fname or part.get_content_disposition() == "attachment":
            add(f"[allegato: {fname or 'senza nome'}]")
        elif part.get_content_maintype() == "text":
            text = _get_text(part)
            if isinstance(text, str) and text.strip():
                add("\n" + (_html.unescape(text) if part.get_content_subtype() == "html" else text))
    return "\n".join(out)[:max_chars]
