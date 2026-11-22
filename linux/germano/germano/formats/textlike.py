"""TXT / codice sorgente / CSV / TSV / JSON / JSONL con preservazione di codifica e fine riga."""
import codecs
import csv
import io
import json
import os

from ..analyzer import Unit, apply_replacements

BLOCK_CHARS = 50000


def _wide_without_bom(data):
    """Codifica di un testo UTF-16/UTF-32 SENZA BOM, riconosciuta dalla posizione dei byte NUL (None se non lo e').

    Un file cosi' e' anche UTF-8 valido (NUL e' un carattere ammesso): letto come UTF-8 ha un NUL fra una lettera e
    l'altra, quindi ne' i modelli ne' le regole riconoscono piu' nulla e il file usciva identico, con i dati in chiaro.
    Si accetta solo se tutto il contenuto si decodifica senza errori (ritorno byte per byte identico)."""
    sample = data[:8192]
    n4 = len(sample) // 4
    if n4 >= 2 and len(data) % 4 == 0:
        zeros = [sample[k:n4 * 4:4].count(0) for k in range(4)]
        for enc, nul, txt in (("utf-32-le", (1, 2, 3), 0), ("utf-32-be", (0, 1, 2), 3)):
            if all(zeros[k] >= 0.9 * n4 for k in nul) and zeros[txt] <= 0.05 * n4:
                return enc
    n2 = len(sample) // 2
    if n2 >= 2 and len(data) % 2 == 0:
        even, odd = sample[0:n2 * 2:2].count(0), sample[1:n2 * 2:2].count(0)
        if odd >= 0.6 * n2 and even <= 0.05 * n2:
            return "utf-16-le"
        if even >= 0.6 * n2 and odd <= 0.05 * n2:
            return "utf-16-be"
    return None


def decode_bytes(data):
    """Restituisce (testo, codifica). Mai perdita silenziosa di caratteri (niente errors='ignore')."""
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8", errors="replace"), "utf-8-sig"
    if len(data) % 4 == 0 and (data.startswith(codecs.BOM_UTF32_LE) or data.startswith(codecs.BOM_UTF32_BE)):
        # il BOM UTF-32 LE (FF FE 00 00) inizia come quello UTF-16 LE: va provato prima
        try:
            return data.decode("utf-32"), "utf-32"
        except UnicodeDecodeError:
            pass
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16", errors="replace"), "utf-16"
    if b"\x00" in data[:8192]:
        wide = _wide_without_bom(data)
        if wide:
            try:
                return data.decode(wide), wide
            except UnicodeDecodeError:
                pass
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def encode_text(text, encoding):
    try:
        return text.encode(encoding)
    except UnicodeEncodeError:
        # Testo ripristinato con caratteri non rappresentabili nella codifica originale: UTF-8 con BOM.
        return codecs.BOM_UTF8 + text.encode("utf-8")


def read_text_file(path):
    with open(path, "rb") as f:
        return decode_bytes(f.read())


def write_text_file(path, text, encoding):
    with open(path, "wb") as f:
        f.write(encode_text(text, encoding))


def split_blocks(text, size=BLOCK_CHARS):
    """Blocchi la cui concatenazione e' esattamente il testo originale (tagli su fine riga)."""
    if len(text) <= size:
        return [text]
    out = []
    pos = 0
    n = len(text)
    while pos < n:
        end = min(n, pos + size)
        if end < n:
            nl = text.rfind("\n", pos + size // 2, end)
            if nl != -1:
                end = nl + 1
        out.append(text[pos:end])
        pos = end
    return out


def transform_text(text, ctx):
    blocks = split_blocks(text)
    res = ctx.analyze([Unit(b) for b in blocks])
    return "".join(apply_replacements(b, r) for b, r in zip(blocks, res))


def process_text(in_path, out_path, ctx):
    text, enc = read_text_file(in_path)
    write_text_file(out_path, transform_text(text, ctx), enc)


def process_csv(in_path, out_path, ctx):
    text, enc = read_text_file(in_path)
    is_tsv = in_path.lower().endswith(".tsv")
    try:
        sample = text[:65536]
        if is_tsv:
            dialect = csv.excel_tab
        else:
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
        if not getattr(dialect, "doublequote", True) and not getattr(dialect, "escapechar", None):
            # Sniffer mette doublequote=False ogni volta che nel campione non vede apici raddoppiati (quasi sempre):
            # in scrittura una cella con un apice (es. «Monitor 19" LG») dava csv.Error «need to escape, but no
            # escapechar set» e il file finiva tra i non riusciti; in lettura "a ""b""" oltre il campione veniva
            # letto male. Lo standard dei CSV (RFC 4180, Excel, LibreOffice) e' l'apice raddoppiato.
            dialect = type("dialect", (dialect,), {"doublequote": True})
        rows = list(csv.reader(io.StringIO(text, newline=""), dialect))
    except csv.Error:
        return process_text(in_path, out_path, ctx)
    units = []
    index = []
    for ri, row in enumerate(rows):
        row_units = []
        for ci, cell in enumerate(row):
            if cell and cell.strip():
                index.append((ri, ci))
                u = Unit(cell, sep=" | ")
                units.append(u)
                row_units.append(u)
        if row_units:
            row_units[-1].sep = "\n"
    # Contesto di riga: le celle della stessa riga vengono analizzate insieme, separate da " | ".
    res = ctx.analyze(units) if units else []
    for (ri, ci), u, r in zip(index, units, res):
        if r:
            rows[ri][ci] = apply_replacements(u.text, r)
    newline = "\r\n" if "\r\n" in text[:65536] else "\n"
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, dialect, lineterminator=newline)
    writer.writerows(rows)
    write_text_file(out_path, buf.getvalue(), enc)


def _embedded(value, ctx, key):
    """File incorporato in un valore JSON (URI «data:...» o blocco Base64): elaborato col suo formato e rimesso al suo
    posto (o tolto, in anonimizzazione, se non e' elaborabile). None se il valore e' un testo normale."""
    if ctx is None or len(value) < 32:
        return None
    from . import embedded_text
    return embedded_text(value, ctx, "", f"contenuto incorporato in «{str(key)[:40]}»")


def _collect_json(obj, units, setters, key="", ctx=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                if v.strip():
                    nv = _embedded(v, ctx, k)
                    if nv is not None:
                        obj[k] = nv
                        continue
                    units.append(Unit(v, context=f"{k}: "))
                    setters.append((obj, k))
            else:
                _collect_json(v, units, setters, k, ctx)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                if v.strip():
                    nv = _embedded(v, ctx, key)
                    if nv is not None:
                        obj[i] = nv
                        continue
                    units.append(Unit(v, context=f"{key}: " if key else ""))
                    setters.append((obj, i))
            else:
                _collect_json(v, units, setters, key, ctx)


def _json_indent(text):
    for line in text.splitlines()[1:6]:
        stripped = line.lstrip(" ")
        if stripped and len(line) != len(stripped):
            return len(line) - len(stripped)
        if line.startswith("\t"):
            return "\t"
    return None


def process_json(in_path, out_path, ctx):
    text, enc = read_text_file(in_path)
    ext = os.path.splitext(in_path)[1].lower()
    try:
        if ext in (".jsonl", ".ndjson"):
            lines = text.splitlines(keepends=True)
            objs = []
            for line in lines:
                s = line.strip()
                objs.append(json.loads(s) if s else None)
        else:
            objs = [json.loads(text)]
    except (ValueError, RecursionError):
        return process_text(in_path, out_path, ctx)

    units, setters = [], []
    holder = [objs]
    _collect_json(holder, units, setters, ctx=ctx)
    res = ctx.analyze(units) if units else []
    for (container, k), u, r in zip(setters, units, res):
        if r:
            container[k] = apply_replacements(u.text, r)
    objs = holder[0]
    ascii_only = all(ord(c) < 128 for c in text[:200000])
    if ext in (".jsonl", ".ndjson"):
        out_lines = []
        for line, obj in zip(text.splitlines(keepends=True), objs):
            if obj is None:
                out_lines.append(line)
            else:
                nl = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
                out_lines.append(json.dumps(obj, ensure_ascii=ascii_only) + nl)
        write_text_file(out_path, "".join(out_lines), enc)
    else:
        out = json.dumps(objs[0], ensure_ascii=ascii_only, indent=_json_indent(text))
        if text.endswith("\n"):
            out += "\r\n" if text.endswith("\r\n") else "\n"
        write_text_file(out_path, out, enc)
    return None


def anonymize_plain_string(text, ctx):
    """Utility per moduli che devono trattare un testo semplice (es. corpo email)."""
    if not text or not text.strip():
        return text
    return transform_text(text, ctx)
