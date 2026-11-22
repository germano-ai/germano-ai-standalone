"""RTF nativo (senza Microsoft Word): si modificano solo i caratteri di testo, mai le parole di controllo,
quindi formattazione e struttura dei gruppi restano integre. Gestisce escape \\'hh, \\uN, metadati \\info,
campi (\\fldinst), la tabella revisori, i commenti (\\annotation), le proprieta' di testo delle forme (\\sp),
le immagini (\\pict) e gli oggetti incorporati (\\objdata)."""
import re

from .. import common
from ..analyzer import Segment, Unit, apply_to_segments, segments_text

_SKIP_DESTS = {
    "fonttbl", "colortbl", "stylesheet", "objdata", "themedata", "colorschememapping",
    "datastore", "latentstyles", "listtable", "listoverridetable", "rsidtbl", "generator", "xmlnstbl",
    "mmathPr", "filetbl", "pgdsctbl", "bkmkstart", "bkmkend", "panose", "falt",
    "listtext", "pntext", "xe", "tc", "blipuid", "wgrffmtfilter", "defchp",
    "defpap", "pnseclvl", "passwordhash", "protusertbl", "ftnsep", "ftnsepc", "aftnsep", "aftnsepc",
}
# Destinazioni il cui testo diretto NON e' testo del documento (dati esadecimali di un'immagine) ma che contengono
# gruppi da leggere: le proprieta' dell'immagine ({\*\picprop{\sp{\sn wzDescription}{\sv ...}}}).
_MUTE_DESTS = {"pict", "shppict", "nonshppict", "picprop"}
# Destinazioni "\*" che contengono testo da analizzare (le altre "\*" si ignorano). Fino alla 1.00 mancavano i
# commenti: il testo di {\*\annotation ...} veniva saltato e usciva in chiaro, come le sigle di {\*\atnid}.
_STARRED_KEEP = {"fldinst", "revtbl", "shpinst", "atnauthor", "userprops", "annotation", "atnid", "shppict",
                 "picprop", "docvar", "ffdeftext", "ffl", "ffstattext", "ffhelptext", "htmltag", "background"}
# testo «a parte» dentro un paragrafo: un'unita' per conto suo, cosi' non si incolla alla parola che lo precede
_SIDE_STREAMS = {"annotation", "footnote"}
_INFO_FIELDS = {"author": True, "operator": True, "manager": True, "title": False, "subject": False,
                "keywords": False, "doccomm": False, "company": False, "category": False, "comment": False,
                "hlinkbase": False}
# proprieta' delle forme e delle immagini il cui valore ({\sv ...}) e' testo scritto dall'utente
_SP_TEXT = {"wzdescription", "wzname", "gtextunicode", "pibname", "wztooltip"}
_PICT_RASTER = {"pngblip", "jpegblip"}
_PICT_KINDS = _PICT_RASTER | {"emfblip", "wmetafile", "dibitmap", "wbitmap", "macpict", "pmmetafile"}
_SPECIAL = {
    "par": "\n", "line": "\n", "sect": "\n", "page": "\n", "row": "\n", "cell": " ", "nestcell": " ",
    "tab": "\t", "emdash": "\u2014", "endash": "\u2013", "lquote": "\u2018", "rquote": "\u2019",
    "ldblquote": "\u201c", "rdblquote": "\u201d", "bullet": "\u2022", "emspace": " ", "enspace": " ",
    "qmspace": " ", "~": "\u00a0",
}
_WORD_RE = re.compile(r"\\([A-Za-z]{1,32})")
_LONE_SURROGATE_RE = re.compile("[\ud800-\udfff]")
_NOT_HEX_RE = re.compile(r"[^0-9A-Fa-f]")


class _State:
    __slots__ = ("skip", "uc", "dest", "stream", "mute", "rec", "owner", "gstart")

    def __init__(self, skip=False, uc=1, dest=None, stream=None, mute=False, rec=None, gstart=0):
        self.skip = skip
        self.uc = uc
        self.dest = dest
        self.stream = stream
        self.mute = mute            # testo diretto da ignorare (dati di un'immagine), gruppi interni da leggere
        self.rec = rec              # immagine od oggetto a cui appartiene il gruppo
        self.owner = False          # questo gruppo e' quello che ha aperto `rec`
        self.gstart = gstart        # posizione della parentesi di apertura del gruppo

    def copy(self, gstart=0):
        return _State(self.skip, self.uc, self.dest, self.stream, self.mute, self.rec, gstart)


def _escape(text, uc):
    out = []
    u_cnt = min(16, max(0, int(uc or 0)))
    for ch in text:
        o = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\line ")
        elif ch == "\t":
            out.append("\\tab ")
        elif o < 128:
            out.append(ch)
        else:
            # oltre il piano di base (emoji) servono due \u, la coppia surrogata UTF-16: prima ne usciva uno solo,
            # con il codice sbagliato
            units = (o,) if o <= 0xFFFF else (0xD800 + ((o - 0x10000) >> 10), 0xDC00 + ((o - 0x10000) & 0x3FF))
            for cu in units:
                n = cu if cu < 32768 else cu - 65536
                out.append(f"\\u{n}" + "?" * u_cnt if u_cnt > 0 else f"\\u{n} ")
    return "".join(out)


class _Setter:
    """Sostituisce l'intervallo sorgente [start, end) con il nuovo testo (escape RTF)."""

    __slots__ = ("doc", "start", "end", "uc")

    def __init__(self, doc, start, end, uc):
        self.doc = doc
        self.start = start
        self.end = end
        self.uc = uc

    def __call__(self, v):
        self.doc.edits.append((self.start, self.end, _escape(v, self.uc)))


class _Doc:
    def __init__(self, data):
        self.data = data
        self.edits = []  # (start, end, replacement)
        self.streams = []  # [(kind, force_person, [segments])]
        self.body_paras = []
        self.picts = []  # immagini: {"start", "end", "kind", "hex": [(a, b)], "bin": (token, a, b) | None, "depth"}
        self.objects = []  # dati degli oggetti incorporati: {"start", "end", "data_start"}

    def make_setter(self, start, end, uc):
        return _Setter(self, start, end, uc)


def _parse(data, codepage="cp1252"):
    doc = _Doc(data)
    n = len(data)
    i = 0
    state = _State()
    stack = []
    body = []  # segmenti del testo principale
    body_paras = [body]
    pending_skip = 0
    last_u_seg = None
    group_start = False

    def new_stream(kind, force=False):
        segs = []
        doc.streams.append((kind, force, segs))
        return segs

    def target():
        return state.stream if state.stream is not None else body_paras[-1]

    def add_seg(text, start, end, writable=True):
        seg = Segment(text, setter=doc.make_setter(start, end, state.uc) if writable else None, writable=writable)
        target().append(seg)
        return seg

    def quiet():
        """Niente testo da raccogliere qui: destinazione saltata, oppure dati di un'immagine."""
        return state.skip or (state.mute and state.stream is None)

    while i < n:
        c = data[i]
        if c == "\\":
            if i + 1 >= n:
                break
            d = data[i + 1]
            if d.isalpha():
                j = i + 1
                while j < n and data[j].isalpha() and j - i <= 32:
                    j += 1
                word = data[i + 1:j]
                k = j
                param = None
                if k < n and (data[k] == "-" or data[k].isdigit()):
                    m = k + 1
                    while m < n and data[m].isdigit():
                        m += 1
                    try:
                        param = int(data[k:m])
                    except ValueError:
                        param = None
                    k = m
                if k < n and data[k] == " ":
                    k += 1
                tok_start, tok_end = i, k
                i = k
                if word == "bin" and param:
                    size = max(0, param)
                    rec = state.rec
                    if rec is not None and "hex" in rec and len(stack) == rec["depth"] and not state.skip:
                        rec["bin"] = (tok_start, i, min(n, i + size))
                    i += size
                    continue
                if group_start:
                    group_start = False
                    if word in _SKIP_DESTS:
                        state.skip = True
                        if word == "objdata":
                            state.rec = {"start": state.gstart, "end": None, "data_start": tok_end}
                            state.owner = True
                            doc.objects.append(state.rec)
                    elif word == "pict":
                        # un'immagine si legge sempre, anche dentro una destinazione saltata (sfondi, elenchi puntati)
                        state.skip = False
                        state.mute = True
                        state.stream = None
                        state.rec = {"start": state.gstart, "end": None, "kind": None, "hex": [], "bin": None,
                                     "depth": len(stack)}
                        state.owner = True
                        doc.picts.append(state.rec)
                    elif word in _MUTE_DESTS:
                        state.mute = True
                        state.stream = None
                    elif word == "info":
                        state.dest = "info"
                    elif state.dest == "info" and word in _INFO_FIELDS:
                        state.stream = new_stream("info", _INFO_FIELDS[word])
                    elif state.dest == "info":
                        state.skip = True
                    elif word == "fldinst":
                        state.stream = new_stream("field")
                    elif word == "revtbl":
                        state.dest = "revtbl"
                    elif word == "atnauthor":
                        state.stream = new_stream("info", True)      # autore di un commento: persona
                    elif word == "atnid":
                        state.stream = new_stream("initials")        # sigla dell'autore di un commento
                    elif word == "sp":
                        state.dest = "sp"
                    elif word == "sn" and state.dest == "sp":
                        state.stream = new_stream("sn")              # nome della proprieta': letto, mai modificato
                    elif word == "sv" and state.dest == "sp":
                        prop = ""
                        if doc.streams and doc.streams[-1][0] == "sn":
                            prop = segments_text(doc.streams[-1][2]).strip().lower()
                        if prop in _SP_TEXT:
                            state.stream = new_stream("shape")       # testo alternativo, nome del file, WordArt
                        else:
                            # valore tecnico: il testo si ignora, ma i gruppi interni si leggono (l'immagine di una
                            # forma e' {\sp{\sn pib}{\sv {\pict ...}}})
                            state.mute = True
                            state.stream = None
                    elif word in _SIDE_STREAMS and not state.mute:
                        state.stream = new_stream(word)
                if state.skip:
                    continue
                rec = state.rec
                if rec is not None and "hex" in rec and rec["kind"] is None and word in _PICT_KINDS:
                    rec["kind"] = word
                if word == "uc" and param is not None:
                    state.uc = param if 0 <= param <= 4 else (0 if param < 0 else 1)
                elif quiet():
                    pass
                elif word == "u" and param is not None:
                    ch = chr(param + 65536 if param < 0 else param) if -32768 <= param <= 65535 else "?"
                    tgt = target()
                    prev = last_u_seg
                    if (prev is not None and tgt and tgt[-1] is prev and prev.text and "\udc00" <= ch <= "\udfff"
                            and "\ud800" <= prev.text[-1] <= "\udbff"):
                        # seconda meta' di una coppia surrogata (emoji): un solo carattere, un solo segmento. Due
                        # surrogati isolati nel testo non si possono codificare in UTF-8 e fermano l'analisi.
                        hi, lo = ord(prev.text[-1]) - 0xD800, ord(ch) - 0xDC00
                        prev.text = prev.text[:-1] + chr(0x10000 + (hi << 10) + lo)
                        _extend(doc, prev, tok_end)
                    else:
                        last_u_seg = add_seg(ch, tok_start, tok_end)
                    pending_skip = state.uc
                elif word in _SPECIAL:
                    if state.stream is None and word in ("par", "sect", "page", "row"):
                        add_seg(_SPECIAL[word], tok_start, tok_end, writable=False)
                        body_paras.append([])
                    else:
                        add_seg(_SPECIAL[word], tok_start, tok_end, writable=False)
                elif word == "ansicpg" and param:
                    try:
                        "a".encode(f"cp{param}")
                        codepage = f"cp{param}"
                    except LookupError:
                        pass
                continue
            if d == "'":
                hx = data[i + 2:i + 4]
                tok_start, tok_end = i, i + 4
                i += 4
                group_start = False
                if quiet():
                    continue
                if pending_skip > 0:
                    pending_skip -= 1
                    if last_u_seg is not None:
                        _extend(doc, last_u_seg, tok_end)
                    continue
                try:
                    ch = bytes([int(hx, 16)]).decode(codepage, errors="replace")
                except ValueError:
                    ch = "?"
                add_seg(ch, tok_start, tok_end)
                continue
            if d in "\\{}":
                tok_start, tok_end = i, i + 2
                i += 2
                group_start = False
                if quiet():
                    continue
                if pending_skip > 0:
                    pending_skip -= 1
                    if last_u_seg is not None:
                        _extend(doc, last_u_seg, tok_end)
                    continue
                add_seg(d, tok_start, tok_end)
                continue
            if d == "*":
                i += 2
                # destinazione ignorabile: si salta, salvo quelle con testo da analizzare (campi, commenti, forme...)
                j = i
                while j < n and data[j] in " \r\n":
                    j += 1
                m = _WORD_RE.match(data, j)
                word = m.group(1) if m else ""
                if word in _STARRED_KEEP or (state.dest == "info" and word in _INFO_FIELDS):
                    continue                     # Word scrive {\*\company ...} e {\*\category ...} con l'asterisco
                state.skip = True
                continue
            if d in "\r\n":
                tok_start, tok_end = i, i + 2
                i += 2
                group_start = False
                if not quiet() and state.stream is None:
                    add_seg("\n", tok_start, tok_end, writable=False)
                    body_paras.append([])
                continue
            # altri simboli di controllo (\~ \- \_ \:)
            i += 2
            group_start = False
            if not quiet():
                if d == "~":
                    add_seg("\u00a0", i - 2, i, writable=False)
                elif d == "_":
                    add_seg("-", i - 2, i, writable=False)
            continue
        if c == "{":
            stack.append(state)
            state = state.copy(gstart=i)
            group_start = True
            i += 1
            continue
        if c == "}":
            if state.owner and state.rec is not None:
                state.rec["end"] = i             # posizione della parentesi che chiude l'immagine o l'oggetto
            state = stack.pop() if stack else _State()
            group_start = False
            pending_skip = 0
            i += 1
            continue
        if c in "\r\n":
            i += 1
            continue
        j = i
        while j < n and data[j] not in "\\{}\r\n":
            j += 1
        group_start = False
        if state.skip:
            i = j
            continue
        if state.mute and state.stream is None:
            rec = state.rec
            if rec is not None and "hex" in rec and len(stack) == rec["depth"]:
                rec["hex"].append((i, j))        # dati esadecimali dell'immagine
            i = j
            continue
        start = i
        if pending_skip > 0:
            take = min(pending_skip, j - i)
            pending_skip -= take
            if last_u_seg is not None:
                _extend(doc, last_u_seg, i + take)
            start = i + take
        if start < j:
            text = data[start:j]
            if state.dest == "revtbl" and state.stream is None:
                # tabella dei revisori: {Mario Rossi;} -> nome di persona
                stream = new_stream("revtbl", True)
                stream.append(Segment(text, setter=doc.make_setter(start, j, state.uc)))
            else:
                add_seg(text, start, j)
        i = j
    doc.body_paras = body_paras
    return doc


def _extend(doc, seg, new_end):
    """Estende il segmento \\uN ai caratteri di fallback che lo seguono (vanno rimossi insieme)."""
    st = seg.setter
    if isinstance(st, _Setter):
        st.end = max(st.end, new_end)


def _apply_edits(data, edits):
    if not edits:
        return data
    edits.sort(key=lambda x: x[0])
    out = []
    pos = 0
    for s, e, rep in edits:
        if s < pos:
            continue
        out.append(data[pos:s])
        out.append(rep)
        pos = e
    out.append(data[pos:])
    return "".join(out)


def _process_pictures(doc, ctx):
    """Immagini e oggetti incorporati (solo in anonimizzazione). Fino alla 1.00 i dati di {\\pict ...} e di
    {\\*\\objdata ...} venivano ricopiati cosi' com'erano: una firma scansionata, la foto di un documento o un foglio
    Excel incorporato in una lettera RTF uscivano identici. Ora, come per i documenti Word:
    - PNG e JPEG passano dall'analisi delle immagini (volti, firme, targhe, testo letto dall'OCR, metadati);
    - le immagini che non si possono analizzare (WMF, EMF, bitmap) e quelle illeggibili vengono tolte;
    - i dati degli oggetti incorporati (OLE) vengono tolti."""
    if not ctx.anonymize:
        return
    from . import reraise_control
    data = doc.data
    removed = kept = 0
    for rec in doc.picts:
        if rec["end"] is None or (not rec["hex"] and not rec["bin"]):
            continue
        ctx.check()
        if rec["kind"] in _PICT_RASTER:
            if not ctx.vision_enabled():
                continue                         # visione spenta nelle impostazioni: come per le immagini dei DOCX
            try:
                if rec["bin"]:
                    raw = data[rec["bin"][1]:rec["bin"][2]].encode("latin-1")
                else:
                    raw = bytes.fromhex(_NOT_HEX_RE.sub("", "".join(data[a:b] for a, b in rec["hex"])))
                from .images import anonymize_image_bytes
                new = anonymize_image_bytes(raw, ctx)
            except Exception as e:
                reraise_control(e)
                ctx.note(f"immagine incorporata non elaborata, rimossa per sicurezza: {type(e).__name__}")
                doc.edits.append((rec["start"], rec["end"] + 1, ""))
                removed += 1
                continue
            kept += 1
            if new is None:
                continue
            hexed = new.hex()
            # l'a capo iniziale separa i dati dalla parola di controllo che li precede: senza, «\pngblip» seguito
            # da «8950...» verrebbe letto come «\pngblip8950» (parola con parametro numerico) e l'immagine si romperebbe
            lines = "\n" + "\n".join(hexed[k:k + 128] for k in range(0, len(hexed), 128))
            ranges = list(rec["hex"])
            if rec["bin"]:
                ranges.append((rec["bin"][0], rec["bin"][2]))          # «\binN» + dati binari -> esadecimale
            ranges.sort()
            doc.edits.append((ranges[0][0], ranges[0][1], lines))
            for a, b in ranges[1:]:
                doc.edits.append((a, b, ""))
        else:
            doc.edits.append((rec["start"], rec["end"] + 1, ""))
            removed += 1
    if removed:
        ctx.note(f"{removed} immagini del documento RTF rimosse per sicurezza (formato non analizzabile: WMF, EMF, "
                 "bitmap).")
    objs = [rec for rec in doc.objects if rec["end"] is not None and rec["end"] > rec["data_start"]]
    for rec in objs:
        doc.edits.append((rec["data_start"], rec["end"], ""))
    if objs:
        ctx.note(f"{len(objs)} oggetti incorporati (OLE) del documento RTF rimossi per sicurezza: formato binario non "
                 "analizzabile.")


def process_rtf(in_path, out_path, ctx):
    with open(in_path, "rb") as f:
        raw = f.read()
    if not raw.lstrip().startswith(b"{\\rtf"):
        from .textlike import process_text
        return process_text(in_path, out_path, ctx)
    data = raw.decode("latin-1")
    doc = _parse(data)
    units, seg_lists = [], []

    def unit(text, force=None):
        # un surrogato rimasto isolato (file malformato) non e' codificabile: per l'analisi vale U+FFFD (stessa
        # lunghezza, le posizioni delle sostituzioni non cambiano)
        return Unit(_LONE_SURROGATE_RE.sub("\ufffd", text), force_label=force)

    for segs in doc.body_paras:
        t = segments_text(segs)
        if t.strip():
            units.append(unit(t))
            seg_lists.append(segs)
    person = "[PERSONA]" if ctx.settings.get("censor_person", True) else None
    for kind, force, segs in doc.streams:
        t = segments_text(segs)
        if not t.strip() or kind == "sn":
            continue
        if kind == "initials":
            if ctx.anonymize:
                apply_to_segments(segs, [(0, len(t), "--")])        # come le sigle nei commenti dei DOCX
            continue
        if kind == "revtbl":
            # "Mario Rossi;" -> l'intero nome come persona (senza il punto e virgola)
            stripped = t.rstrip("; ")
            units.append(unit(stripped, person))
            seg_lists.append(segs)
        else:
            units.append(unit(t, person if force else None))
            seg_lists.append(segs)
    res = ctx.analyze(units) if units else []
    for segs, r in zip(seg_lists, res):
        if r:
            apply_to_segments(segs, r)
    _process_pictures(doc, ctx)
    new_data = _apply_edits(data, doc.edits)
    with open(out_path, "wb") as f:
        f.write(new_data.encode("latin-1"))
    if doc.edits:
        common.log(f"RTF: {len(doc.edits)} porzioni di testo aggiornate.")
    return None


def rtf_plain_text(raw_bytes):
    """Testo visibile (per riconoscere i file di ritorno dall'AI)."""
    try:
        doc = _parse(raw_bytes.decode("latin-1"))
    except Exception:
        return ""
    return "\n".join(segments_text(s) for s in doc.body_paras)
