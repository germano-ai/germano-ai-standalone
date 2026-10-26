"""RTF nativo (senza Microsoft Word): si modificano solo i caratteri di testo, mai le parole di controllo,
quindi formattazione e struttura dei gruppi restano integre. Gestisce escape \\'hh, \\uN, metadati \\info,
campi (\\fldinst) e la tabella revisori."""
from .. import common
from ..analyzer import Segment, Unit, apply_to_segments, segments_text

_SKIP_DESTS = {
    "fonttbl", "colortbl", "stylesheet", "pict", "object", "objdata", "themedata", "colorschememapping",
    "datastore", "latentstyles", "listtable", "listoverridetable", "rsidtbl", "generator", "xmlnstbl",
    "mmathPr", "filetbl", "pgdsctbl", "bkmkstart", "bkmkend", "panose", "falt", "sp",
    "listtext", "pntext", "xe", "tc", "shppict", "nonshppict", "blipuid", "wgrffmtfilter", "defchp",
    "defpap", "pnseclvl", "passwordhash", "protusertbl", "ftnsep", "ftnsepc", "aftnsep", "aftnsepc",
}
# Destinazioni "\*" che contengono testo da analizzare (le altre "\*" si ignorano)
_STARRED_KEEP = ("\\fldinst", "\\revtbl", "\\shpinst")
_INFO_FIELDS = {"author": True, "operator": True, "manager": True, "title": False, "subject": False,
                "keywords": False, "doccomm": False, "company": False, "category": False, "comment": False,
                "hlinkbase": False}
_SPECIAL = {
    "par": "\n", "line": "\n", "sect": "\n", "page": "\n", "row": "\n", "cell": " ", "nestcell": " ",
    "tab": "\t", "emdash": "\u2014", "endash": "\u2013", "lquote": "\u2018", "rquote": "\u2019",
    "ldblquote": "\u201c", "rdblquote": "\u201d", "bullet": "\u2022", "emspace": " ", "enspace": " ",
    "qmspace": " ", "~": "\u00a0",
}


class _State:
    __slots__ = ("skip", "uc", "dest", "stream")

    def __init__(self, skip=False, uc=1, dest=None, stream=None):
        self.skip = skip
        self.uc = uc
        self.dest = dest
        self.stream = stream

    def copy(self):
        return _State(self.skip, self.uc, self.dest, self.stream)


def _escape(text, uc):
    out = []
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
            n = o if o < 32768 else o - 65536
            out.append(f"\\u{n}" + "?" * uc if uc > 0 else f"\\u{n} ")
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

    def add_seg(text, start, end, writable=True):
        tgt = state.stream if state.stream is not None else body_paras[-1]
        seg = Segment(text, setter=doc.make_setter(start, end, state.uc) if writable else None, writable=writable)
        tgt.append(seg)
        return seg

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
                    i += max(0, param)
                    continue
                if group_start:
                    group_start = False
                    if word in _SKIP_DESTS:
                        state.skip = True
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
                if state.skip:
                    continue
                if word == "uc" and param is not None:
                    state.uc = max(0, param)
                elif word == "u" and param is not None:
                    ch = chr(param + 65536 if param < 0 else param) if -32768 <= param <= 65535 else "?"
                    seg = add_seg(ch, tok_start, tok_end)
                    last_u_seg = seg
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
                if state.skip:
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
                if state.skip:
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
                # destinazione ignorabile: si salta, salvo i campi (fldinst) gestiti come flusso separato
                j = i
                while j < n and data[j] in " \r\n":
                    j += 1
                if data.startswith(_STARRED_KEEP, j):
                    continue
                state.skip = True
                continue
            if d in "\r\n":
                tok_start, tok_end = i, i + 2
                i += 2
                group_start = False
                if not state.skip and state.stream is None:
                    add_seg("\n", tok_start, tok_end, writable=False)
                    body_paras.append([])
                continue
            # altri simboli di controllo (\~ \- \_ \:)
            i += 2
            group_start = False
            if not state.skip:
                if d == "~":
                    add_seg("\u00a0", i - 2, i, writable=False)
                elif d == "_":
                    add_seg("-", i - 2, i, writable=False)
            continue
        if c == "{":
            stack.append(state)
            state = state.copy()
            group_start = True
            i += 1
            continue
        if c == "}":
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


def process_rtf(in_path, out_path, ctx):
    with open(in_path, "rb") as f:
        raw = f.read()
    if not raw.lstrip().startswith(b"{\\rtf"):
        from .textlike import process_text
        return process_text(in_path, out_path, ctx)
    data = raw.decode("latin-1")
    doc = _parse(data)
    units, seg_lists = [], []
    for segs in doc.body_paras:
        t = segments_text(segs)
        if t.strip():
            units.append(Unit(t))
            seg_lists.append(segs)
    person = "[PERSONA]" if ctx.settings.get("censor_person", True) else None
    for kind, force, segs in doc.streams:
        t = segments_text(segs)
        if not t.strip():
            continue
        if kind == "revtbl":
            # "Mario Rossi;" -> l'intero nome come persona (senza il punto e virgola)
            stripped = t.rstrip("; ")
            units.append(Unit(stripped, force_label=person))
            seg_lists.append(segs)
        else:
            units.append(Unit(t, force_label=person if force else None))
            seg_lists.append(segs)
    res = ctx.analyze(units) if units else []
    for segs, r in zip(seg_lists, res):
        if r:
            apply_to_segments(segs, r)
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
