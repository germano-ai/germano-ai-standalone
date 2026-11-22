"""File firmati digitalmente CAdES (.p7m), molto diffusi nella PA italiana (es. fattura.xml.p7m).

Il documento interno viene estratto (parser DER/BER senza dipendenze) ed elaborato col proprio formato.
L'output e' il documento interno anonimizzato SENZA firma: la firma conterrebbe i dati del firmatario
(nome, codice fiscale nel certificato) e non sarebbe comunque piu' valida dopo la modifica."""
import base64
import binascii
import os
import re

from . import ProcessingError, process_file

_OID_SIGNED_DATA = bytes.fromhex("2a864886f70d010702")
_MAX_BER_DEPTH = 64


def _tlv(data, pos, end, depth=0):
    """(tag, constructed, content_start, content_end, next_pos)."""
    if depth > _MAX_BER_DEPTH:
        raise ValueError("struttura ASN.1 troppo annidata")
    if pos >= end:
        raise ValueError("fine dati")
    tag = data[pos]
    pos += 1
    if tag & 0x1F == 0x1F:
        while pos < end and data[pos] & 0x80:
            pos += 1
        pos += 1
    if pos >= end:
        raise ValueError("lunghezza mancante")
    first = data[pos]
    pos += 1
    constructed = bool(tag & 0x20)
    if first == 0x80:
        if not constructed:
            raise ValueError("lunghezza indefinita su primitivo")
        # trova la fine scorrendo i figli fino all'EOC
        p = pos
        while True:
            if p + 2 > end:
                raise ValueError("EOC mancante")
            if data[p] == 0 and data[p + 1] == 0:
                return tag, constructed, pos, p, p + 2
            _, _, _, _, p = _tlv(data, p, end, depth + 1)
    if first & 0x80:
        nb = first & 0x7F
        if nb == 0 or nb > 6 or pos + nb > end:
            raise ValueError("lunghezza non valida")
        length = int.from_bytes(data[pos:pos + nb], "big")
        pos += nb
    else:
        length = first
    if pos + length > end:
        raise ValueError("dati troncati")
    return tag, constructed, pos, pos + length, pos + length


def _children(data, start, end, depth=0):
    if depth > _MAX_BER_DEPTH:
        raise ValueError("struttura ASN.1 troppo annidata")
    out = []
    p = start
    while p < end:
        if data[p] == 0 and p + 1 < end and data[p + 1] == 0:
            break
        t = _tlv(data, p, end, depth)
        out.append(t)
        p = t[4]
    return out


def _octets(data, tag, constructed, cs, ce, depth=0):
    if depth > _MAX_BER_DEPTH:
        raise ValueError("struttura ASN.1 troppo annidata")
    if not constructed:
        return data[cs:ce]
    return b"".join(_octets(data, t, c, s, e, depth + 1) for t, c, s, e, _ in _children(data, cs, ce, depth + 1))


def extract_signed_content(raw):
    data = raw
    if not data[:1] == b"\x30":
        text = data.decode("ascii", errors="ignore")
        text = re.sub(r"-----(BEGIN|END)[^-]+-----", "", text)
        try:
            data = base64.b64decode("".join(text.split()), validate=False)
        except (binascii.Error, ValueError):
            raise ProcessingError("File .p7m non riconosciuto (ne' DER ne' Base64).")
    n = len(data)
    t, c, cs, ce, _ = _tlv(data, 0, n)
    kids = _children(data, cs, ce)
    if len(kids) < 2 or data[kids[0][2]:kids[0][3]] != _OID_SIGNED_DATA:
        raise ProcessingError("Il file .p7m non contiene una busta CAdES SignedData.")
    explicit = kids[1]
    sd = _children(data, explicit[2], explicit[3])[0]
    sd_kids = _children(data, sd[2], sd[3])
    # version, digestAlgorithms, encapContentInfo, ...
    if len(sd_kids) < 3:
        raise ProcessingError("Struttura SignedData non valida.")
    eci = sd_kids[2]
    eci_kids = _children(data, eci[2], eci[3])
    if len(eci_kids) < 2:
        raise ProcessingError("Firma 'detached': il documento non e' incluso nel file .p7m.")
    ec = eci_kids[1]
    inner = _children(data, ec[2], ec[3])
    if not inner:
        raise ProcessingError("Contenuto firmato vuoto.")
    t, c, s, e, _ = inner[0]
    return _octets(data, t, c, s, e)


def _guess_ext(content):
    """Estensione del documento firmato, dal suo contenuto: «» se e' un binario che non si riconosce. Fino alla 1.00
    tutto cio' che non era PDF/RTF/XML/ZIP valeva «.txt»: una foto firmata senza estensione interna («foto.p7m») o una
    busta S/MIME («smime.p7m», un messaggio MIME con gli allegati in Base64) venivano «analizzate» come testo e
    uscivano identiche, con i dati in chiaro."""
    from . import sniff_ext
    return sniff_ext(content) or ""


# estensioni «di testo» dichiarate nel nome che non valgono se il contenuto e' riconoscibilmente un altro formato
_TEXT_DECLARED = (".txt", ".csv", ".md", ".log")


def process_p7m(in_path, out_path, ctx):
    with open(in_path, "rb") as f:
        raw = f.read()
    try:
        content = extract_signed_content(raw)
    except ProcessingError:
        raise
    except Exception as e:
        raise ProcessingError(f"File .p7m non leggibile: {e}")
    base = out_path[:-4] if out_path.lower().endswith(".p7m") else out_path
    guessed = _guess_ext(content)
    declared = os.path.splitext(os.path.basename(base))[1].lower()
    if not declared or declared in _TEXT_DECLARED:
        if not guessed:
            raise ProcessingError("Il documento firmato dentro il file .p7m non e' di un tipo riconosciuto: rinomina il "
                                  "file con l'estensione del documento (es. documento.pdf.p7m) e riprova.")
        if not declared:
            base += guessed
        elif guessed not in (".txt", ".xml", ".html", ".eml"):      # un testo dichiarato resta il testo che e'
            base = os.path.splitext(base)[0] + guessed
    with ctx.tempdir() as d:
        inner_in = os.path.join(d, os.path.basename(base))
        with open(inner_in, "wb") as f:
            f.write(content)
        result = process_file(inner_in, base, ctx.child())
    ctx.note("Firma digitale CAdES rimossa: il file in uscita e' il documento interno (la firma conteneva i dati del firmatario).")
    return result
