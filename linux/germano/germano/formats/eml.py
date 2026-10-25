"""Email .eml: intestazioni, corpo testo/HTML, allegati (elaborati o rimossi se non supportati),
messaggi inoltrati annidati."""
import email
import os
from email import policy

from .. import common
from ..analyzer import Unit, apply_replacements
from . import is_supported, process_bytes, transform_filename

_HEADERS = {
    "from", "to", "cc", "bcc", "reply-to", "sender", "return-path", "delivered-to", "x-original-to",
    "disposition-notification-to", "resent-from", "resent-to", "resent-cc", "x-sender", "x-receiver",
    "errors-to", "subject", "thread-topic", "comments", "keywords", "organization", "x-originating-ip",
    "received", "message-id", "in-reply-to", "references", "x-ms-exchange-organization-authas",
    "x-forwarded-to", "x-forwarded-for", "list-unsubscribe",
}
_IMAGE_SUBTYPES = {"png", "jpeg", "jpg", "gif", "bmp", "tiff", "webp"}


def _ext_for(part):
    ct = part.get_content_type()
    return {
        "application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
        "image/tiff": ".tif", "image/bmp": ".bmp", "image/webp": ".webp", "text/csv": ".csv",
        "application/zip": ".zip", "application/rtf": ".rtf", "text/rtf": ".rtf", "text/xml": ".xml",
        "application/xml": ".xml", "message/rfc822": ".eml",
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


def process_eml(in_path, out_path, ctx):
    with open(in_path, "rb") as f:
        raw = f.read()
    pol = policy.default.clone(linesep="\r\n") if b"\r\n" in raw[:65536] else policy.default
    msg = email.message_from_bytes(raw, policy=pol)

    units, appliers = [], []
    html_parts, att_parts = [], []
    person = "[PERSONA]" if ctx.settings.get("censor_person", True) else None

    for part in msg.walk():
        # intestazioni (anche dei messaggi inoltrati come allegato)
        hdrs = getattr(part, "_headers", None)
        if hdrs:
            for idx, (name, value) in enumerate(list(hdrs)):
                if name.lower() in _HEADERS:
                    sval = str(value)
                    if sval.strip():
                        units.append(Unit(sval, context=f"{name}: "))

                        def _ap(new, p=part, i=idx, nm=name):
                            p._headers[i] = p.policy.header_store_parse(nm, new)
                        appliers.append(_ap)
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

    data = msg.as_bytes(policy=pol)
    with open(out_path, "wb") as f:
        f.write(data)
    return None


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
                new_name = out_name
                maintype, subtype = "application", "octet-stream"
            if cid:
                del part["Content-ID"]
            part.set_content(new_data, maintype=maintype, subtype=subtype, disposition=disp, filename=new_name, cid=cid)
            common.log(f"Email: allegato elaborato ({base}).")
            return
        except Exception as e:
            reason = str(e)
    else:
        reason = "formato non supportato"
    if ctx.anonymize:
        note = (f"Allegato '{new_name}' rimosso da Germano AI per proteggere i dati personali ({reason}).\r\n"
                "L'originale e' conservato nella cartella 'processed'.")
        part.set_content(note, subtype="plain", charset="utf-8", disposition="attachment",
                         filename=os.path.splitext(new_name)[0] + "_RIMOSSO.txt")
        ctx.note(f"Allegato email rimosso per sicurezza ({base}: {reason}).")
