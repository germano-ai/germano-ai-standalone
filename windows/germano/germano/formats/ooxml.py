"""Word / Excel / PowerPoint (OOXML) elaborati direttamente a livello XML.

Rispetto alla v0.50 (python-docx `paragraph.text = ...`) la formattazione dei singoli "run", le immagini,
i campi e i collegamenti restano intatti; vengono coperti anche note a pie' di pagina, caselle di testo,
commenti, revisioni, intestazioni/pie' di pagina, note del relatore, gruppi, SmartArt, grafici, metadati.
"""
import os
import re
import zipfile

from lxml import etree

from .. import common
from ..analyzer import Segment, Unit, apply_replacements, apply_to_segments, segments_text
from . import ProcessingError, is_supported, process_bytes, reraise_control

W_NS = ("http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "http://purl.oclc.org/ooxml/wordprocessingml/main")
A_NS = ("http://schemas.openxmlformats.org/drawingml/2006/main",
        "http://purl.oclc.org/ooxml/drawingml/main")
S_NS = ("http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "http://purl.oclc.org/ooxml/spreadsheetml/main")
C_NS = ("http://schemas.openxmlformats.org/drawingml/2006/chart",
        "http://purl.oclc.org/ooxml/drawingml/chart")
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _q(nss, local):
    return tuple("{%s}%s" % (ns, local) for ns in nss)


M_NS = ("http://schemas.openxmlformats.org/officeDocument/2006/math",
        "http://purl.oclc.org/ooxml/officeDocument/math")
P_NS = ("http://schemas.openxmlformats.org/presentationml/2006/main",
        "http://purl.oclc.org/ooxml/presentationml/main")
CX_NS = ("http://schemas.microsoft.com/office/drawing/2014/chartex",)

W_P, W_T, W_TAB, W_BR, W_CR = _q(W_NS, "p"), _q(W_NS, "t"), _q(W_NS, "tab"), _q(W_NS, "br"), _q(W_NS, "cr")
W_NBH, W_DELTEXT, W_INSTR = _q(W_NS, "noBreakHyphen"), _q(W_NS, "delText"), _q(W_NS, "instrText")
W_DELINSTR = _q(W_NS, "delInstrText")
W_FLDSIMPLE = _q(W_NS, "fldSimple")
M_T = _q(M_NS, "t")
A_P, A_T, A_BR = _q(A_NS, "p"), _q(A_NS, "t"), _q(A_NS, "br")
S_SI, S_T, S_R, S_RPH = _q(S_NS, "si"), _q(S_NS, "t"), _q(S_NS, "r"), _q(S_NS, "rPh")
C_V = _q(C_NS, "v")
C_STRCACHE, C_TX = _q(C_NS, "strCache"), _q(C_NS, "tx")
C_PT, C_NUMERIC = _q(C_NS, "pt"), _q(C_NS, "numCache") + _q(C_NS, "numLit")

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
_RASTER_EXTS = {".png", ".jpg", ".jpeg", ".jpe", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
_VECTOR_EXTS = {".svg", ".emf", ".wmf"}
# Immagini che il motore non sa leggere: non si possono controllare (volti, firme, testo), quindi in anonimizzazione
# non vengono ricopiate. HD Photo (.wdp) e' la copia dell'originale che Office conserva dopo un «effetto artistico».
_OPAQUE_VECTOR_EXTS = {".eps", ".pct", ".pict", ".cgm", ".wpg"}
_OPAQUE_RASTER_EXTS = {".wdp", ".jxr", ".hdp", ".heic", ".heif", ".avif", ".jp2", ".j2k", ".jpx"}
_PERSON = "[PERSONA]"
# elementi il cui attributo «name» e' il nome di una persona (autori di commenti e di modifiche)
_AUTHOR_TAGS = ("cmAuthor", "author", "chgData", "userInfo")
# attributi «val» con testo scritto dall'utente: variabili del documento e campi modulo di Word
_VAL_TEXT_TAGS = ("docVar", "listEntry", "default", "statusText", "helpText")
_NUMERIC_CELL_RE = re.compile(r"\d{8,15}")       # telefoni, partite IVA e identificativi salvati come numeri
_FORMULA_STR_RE = re.compile(r'"((?:[^"]|"")*)"')
ZIP_MAX_ENTRIES = 10_000
ZIP_MAX_MEMBER_BYTES = 128 * 1024 * 1024
ZIP_MAX_TOTAL_BYTES = 512 * 1024 * 1024
ZIP_MAX_RATIO = 100


def safe_zip_read(zin, info_or_name, budget=None, max_member=ZIP_MAX_MEMBER_BYTES):
    """Legge un membro di un archivio ZIP con limiti anti zip-bomb (dimensione, totale, rapporto)."""
    info = info_or_name if isinstance(info_or_name, zipfile.ZipInfo) else zin.getinfo(info_or_name)
    if info.file_size > max_member:
        raise ProcessingError(f"Parte interna troppo grande ({info.filename}): limite di sicurezza superato.")
    if info.compress_size > 0 and info.file_size > 1024 * 1024 and (info.file_size / info.compress_size) > ZIP_MAX_RATIO:
        raise ProcessingError(f"Rapporto di compressione anomalo ({info.filename}): file rifiutato per sicurezza.")
    chunks = []
    read = 0
    with zin.open(info, "r") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            read += len(chunk)
            if read > max_member:
                raise ProcessingError(f"Parte interna troppo grande ({info.filename}): limite di sicurezza superato.")
            if budget is not None:
                budget["total"] = budget.get("total", 0) + len(chunk)
                if budget["total"] > budget.get("max_total", ZIP_MAX_TOTAL_BYTES):
                    raise ProcessingError("Contenuto decompresso del documento troppo grande: limite di sicurezza superato.")
            chunks.append(chunk)
    if info.compress_size > 0 and read > 1024 * 1024 and (read / info.compress_size) > ZIP_MAX_RATIO:
        raise ProcessingError(f"Rapporto di compressione anomalo ({info.filename}): file rifiutato per sicurezza.")
    return b"".join(chunks)


def _blank_png_bytes():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (255, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _set_text_preserve(el, v):
    el.text = v
    el.set(XML_SPACE, "preserve")


def _set_text(el, v):
    el.text = v


class _Collector:
    def __init__(self):
        self.units = []
        self.appliers = []  # (part_name, callable(repls) -> bool)

    def segments(self, part, segs, sep=None):
        if not segs:
            return
        text = segments_text(segs)
        if text.strip():
            self.units.append(Unit(text, sep=sep))
            self.appliers.append((part, lambda r, s=segs: apply_to_segments(s, r)))

    def text(self, part, value, setter, force=None, context=""):
        if isinstance(value, str) and value.strip():
            self.units.append(Unit(value, force_label=force, context=context))

            def _ap(r, v=value, st=setter):
                if not r:
                    return False
                st(apply_replacements(v, r))
                return True
            self.appliers.append((part, _ap))

    def run(self, ctx):
        changed = set()
        if not self.units:
            return changed
        results = ctx.analyze(self.units)
        for (part, ap), r in zip(self.appliers, results):
            if r and ap(r):
                changed.add(part)
        return changed


def _paragraph_segments(root, p_tags, t_tags, sep_map, setter):
    """Raggruppa i nodi di testo per paragrafo (il paragrafo piu' vicino: le caselle di testo annidate
    formano paragrafi separati)."""
    tags = tuple(t_tags) + tuple(sep_map.keys())
    paras = {}
    order = []
    p_set = set(p_tags)
    for el in root.iter(*tags):
        p = None
        for anc in el.iterancestors():
            if anc.tag in p_set:
                p = anc
                break
        if p is None:
            continue
        key = id(p)
        if key not in paras:
            paras[key] = (p, [])
            order.append(key)
        segs = paras[key][1]
        if el.tag in sep_map:
            segs.append(Segment(sep_map[el.tag], writable=False))
        else:
            segs.append(Segment(el.text or "", setter=lambda v, e=el: setter(e, v)))
    return [paras[k][1] for k in order]


# ------------------------------------------------------------------------------------------------
def _kind(name_list):
    names = set(name_list)
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    if "ppt/presentation.xml" in names:
        return "pptx"
    return None


def _is_text_part(kind, name):
    n = name.lower()
    if not n.endswith(".xml") or n.startswith("[content_types]"):
        return False
    if "/_rels/" in n or n.endswith(".rels"):
        return False
    base = n.rsplit("/", 1)[-1]
    # word/settings.xml si legge: contiene le variabili del documento (w:docVar), dove modelli e gestionali salvano
    # i valori dei campi (nome del cliente, codice fiscale...)
    if base in ("styles.xml", "stylesweffects.xml", "fonttable.xml", "numbering.xml", "websettings.xml",
                "theme1.xml", "presprops.xml", "viewprops.xml", "tablestyles.xml", "calcchain.xml"):
        return False
    if "/theme/" in n or "/printersettings/" in n or "itemprops" in base:
        return False
    if n.startswith("docprops/"):
        return base in ("core.xml", "app.xml", "custom.xml")
    if n.startswith("customxml/"):
        return base.startswith("item")
    return True


def check_unique_names(names, family="Office"):
    """Un pacchetto Office/OpenDocument non ha mai due parti con lo stesso nome. Con un doppione si analizzerebbe una
    copia sola (l'ultima) e l'altra, mai letta, verrebbe ricopiata in uscita cosi' com'e': il file viene rifiutato."""
    seen = set()
    for n in names:
        key = n.casefold()
        if key in seen:
            raise ProcessingError(f"Documento {family} non valido: la parte interna «{n[:120]}» compare piu' volte. "
                                  "Il file non e' stato elaborato.")
        seen.add(key)


def unreadable_part(name, family="Office"):
    """Una parte che non si riesce ad analizzare non va MAI copiata in uscita: conterrebbe i dati in chiaro."""
    return ProcessingError(f"Documento {family} danneggiato: la parte interna «{name}» non e' leggibile, quindi non e' "
                           "possibile garantirne l'anonimizzazione. Il file non e' stato elaborato.")


def process_ooxml(in_path, out_path, ctx):
    if not zipfile.is_zipfile(in_path):
        raise ValueError("File Office non valido o protetto da password (non e' un pacchetto OOXML).")
    with zipfile.ZipFile(in_path, "r") as zin:
        infos = zin.infolist()
        if len(infos) > ZIP_MAX_ENTRIES:
            raise ProcessingError("Documento Office con troppi elementi interni: rifiutato per sicurezza.")
        budget = {"total": 0, "max_total": ZIP_MAX_TOTAL_BYTES}
        names = [i.filename for i in infos]
        check_unique_names(names, "Office")
        kind = _kind(names)
        if kind is None:
            raise ValueError("Pacchetto Office non riconosciuto.")
        trees = {}
        for info in infos:
            if _is_text_part(kind, info.filename):
                try:
                    trees[info.filename] = etree.fromstring(safe_zip_read(zin, info, budget), _PARSER)
                except etree.XMLSyntaxError:
                    raise unreadable_part(info.filename) from None
        rels = {}
        for info in infos:
            if info.filename.endswith(".rels"):
                try:
                    rels[info.filename] = etree.fromstring(safe_zip_read(zin, info, budget), _PARSER)
                except etree.XMLSyntaxError:
                    raise unreadable_part(info.filename) from None

        col = _Collector()
        sheet_renames = {}
        sst_map = {}
        _collect(kind, trees, col, ctx, sheet_renames, sst_map)
        _collect_rels(rels, col)
        changed = col.run(ctx)

        if kind == "xlsx":
            changed |= _finish_xlsx(trees, sheet_renames, sst_map)

        new_data = {}
        removed = set()
        for name in changed:
            if name in trees:
                new_data[name] = etree.tostring(trees[name], xml_declaration=True, encoding="UTF-8", standalone=True)
            elif name in rels:
                new_data[name] = etree.tostring(rels[name], xml_declaration=True, encoding="UTF-8", standalone=True)

        # Immagini incorporate (a finestre: un'unica analisi del testo letto dall'OCR per finestra), documenti
        # annidati, miniature
        def _image_done(name, nb, err):
            if err is not None:
                ctx.note(f"immagine incorporata non elaborata ({os.path.basename(name)}): {err}")
                if ctx.anonymize:
                    new_data[name] = _blank_png_bytes()
            elif nb is not None:
                new_data[name] = nb
        from .images import ImageBatcher
        batcher = ImageBatcher(ctx, _image_done)
        for info in infos:
            n = info.filename
            low = n.lower()
            ext = os.path.splitext(low)[1]
            if "/media/" in low and ext in _RASTER_EXTS and ctx.vision_enabled():
                ctx.check()
                batcher.add(n, safe_zip_read(zin, info, budget))
            elif "/media/" in low and ext in _VECTOR_EXTS and ctx.anonymize:
                ctx.check()
                if ext == ".svg":
                    try:
                        from .markup import transform_xml_bytes
                        new_data[n] = transform_xml_bytes(safe_zip_read(zin, info, budget), ctx)
                    except Exception as e:
                        reraise_control(e)
                        removed.add(n)
                        ctx.note(f"immagine vettoriale rimossa per sicurezza ({os.path.basename(n)}): {e}")
                else:
                    removed.add(n)
                    ctx.note(f"immagine vettoriale ({os.path.basename(n)}) rimossa per sicurezza (formato non analizzabile).")
            elif "/media/" in low and ctx.anonymize and (
                    ext in _OPAQUE_VECTOR_EXTS or (ext in _OPAQUE_RASTER_EXTS and ctx.vision_enabled())):
                removed.add(n)
                ctx.note(f"immagine ({os.path.basename(n)}) rimossa per sicurezza (formato non analizzabile).")
            elif "/embeddings/" in low:
                base = os.path.basename(n)
                if is_supported(base) and ext not in (".bin",):
                    try:
                        nb, _ = process_bytes(safe_zip_read(zin, info, budget), base, ctx.child())
                        new_data[n] = nb
                        common.log(f"Documento incorporato elaborato: {base}")
                    except Exception as e:
                        reraise_control(e)
                        if ctx.anonymize:
                            removed.add(n)
                            ctx.note(f"oggetto incorporato rimosso per sicurezza ({base}): {e}")
                        else:
                            ctx.note(f"oggetto incorporato non elaborabile ({base}): {e}")
                elif ctx.anonymize:
                    removed.add(n)
                    ctx.note(f"Oggetto OLE incorporato rimosso per sicurezza ({base}): formato binario non analizzabile.")
            elif low.startswith("docprops/thumbnail") and ctx.anonymize:
                removed.add(n)
        batcher.flush()

        if removed:
            _drop_parts(removed, new_data, zin, rels)

        write_zip(out_path, zin, infos, new_data, removed, budget=budget)
    return None


def clone_zipinfo(info):
    """Nuovo ZipInfo con i soli metadati utili (evita di ricopiare campi extra/zip64 e commenti con possibili PII)."""
    zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    zi.compress_type = info.compress_type
    zi.external_attr = info.external_attr
    zi.create_system = info.create_system
    zi.comment = b""
    return zi


def write_zip(out_path, zin, infos, new_data, removed=(), budget=None):
    """Riscrive l'archivio mantenendo ordine e metodo di compressione (es. 'mimetype' ODF non compresso)."""
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zout:
        for info in infos:
            if info.filename in removed:
                continue
            data = new_data[info.filename] if info.filename in new_data else safe_zip_read(zin, info, budget)
            zout.writestr(clone_zipinfo(info), data)


def _drop_parts(removed, new_data, zin, rels):
    for rel_name, tree in rels.items():
        if tree is None:
            continue
        base_dir = os.path.dirname(os.path.dirname(rel_name)) if "/_rels/" in rel_name else ""
        changed_rel = False
        for rel in list(tree):
            raw_t = (rel.get("Target") or "").replace("\\", "/")
            if raw_t.startswith("/"):
                cand = raw_t.lstrip("/")
            elif base_dir:
                cand = os.path.normpath(base_dir + "/" + raw_t).replace("\\", "/")
            else:
                cand = raw_t
            if cand in removed or raw_t.lstrip("/") in removed:
                tree.remove(rel)
                changed_rel = True
        if changed_rel:
            new_data[rel_name] = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)
    try:
        ct = etree.fromstring(safe_zip_read(zin, "[Content_Types].xml"), _PARSER)
        for ov in list(ct):
            if (ov.get("PartName") or "").lstrip("/") in removed:
                ct.remove(ov)
        new_data["[Content_Types].xml"] = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True)
    except Exception:
        pass


# ------------------------------------------------------------------------------------------------
def _file_name_attr(col, part, el, key, value):
    """Attributo che contiene il nome di un file («Firma Mario Rossi.png», «CV_Mario_Rossi»): si analizza con i
    separatori resi spazi (come i nomi dei file) e le sostituzioni si applicano al testo originale."""
    spaced = "".join(" " if c in "_-.+" else c for c in value)
    if not spaced.strip():
        return

    def _ap(r, e=el, kk=key, orig=value):
        if not r:
            return False
        e.set(kk, apply_replacements(orig, r))
        return True
    col.units.append(Unit(spaced))
    col.appliers.append((part, _ap))


def _collect(kind, trees, col, ctx, sheet_renames, sst_map):
    person = _PERSON if ctx.settings.get("censor_person", True) else None
    sheet_names = set()
    if kind == "xlsx":
        for root in trees.values():
            if _local(root.tag) == "workbook":
                sheet_names.update(sh.get("name") for sh in root.iter(*_q(S_NS, "sheet")) if sh.get("name"))
    for name, root in trees.items():
        low = name.lower()
        if low.startswith("docprops/"):
            _collect_docprops(name, root, col, person, sheet_names)
            continue
        # Paragrafi WordprocessingML (Word, caselle di testo, commenti, note); il testo delle formule (m:t) fa parte
        # del paragrafo che le contiene
        if kind == "docx":
            for segs in _paragraph_segments(root, W_P, W_T + M_T, {W_TAB[0]: "\t", W_TAB[1]: "\t", W_BR[0]: "\n",
                                                                   W_BR[1]: "\n", W_CR[0]: "\n", W_CR[1]: "\n",
                                                                   W_NBH[0]: "-", W_NBH[1]: "-"}, _set_text_preserve):
                col.segments(name, segs)
            for segs in _paragraph_segments(root, W_P, W_DELTEXT, {}, _set_text_preserve):
                col.segments(name, segs)
            for segs in _paragraph_segments(root, W_P, W_INSTR, {}, _set_text_preserve):
                col.segments(name, segs)
            for segs in _paragraph_segments(root, W_P, W_DELINSTR, {}, _set_text_preserve):
                col.segments(name, segs)
            for el in root.iter(*W_FLDSIMPLE):
                for k in list(el.attrib):
                    if _local(k) == "instr":
                        col.text(name, el.get(k), lambda v, e=el, kk=k: e.set(kk, v))
        # Paragrafi DrawingML (PowerPoint, forme, grafici, SmartArt, disegni Excel)
        for segs in _paragraph_segments(root, A_P, A_T, {A_BR[0]: "\n", A_BR[1]: "\n"}, _set_text):
            col.segments(name, segs)
        # Valori stringa memorizzati nei grafici: nomi delle serie (c:tx) e ogni punto che non sia in una cache
        # numerica (strCache, ma anche strLit e multiLvlStrCache: le categorie su due livelli «Reparto / Nome»)
        for el in root.iter(*C_V):
            par = el.getparent()
            gp = par.getparent() if par is not None else None
            if par is None:
                continue
            if par.tag in C_TX or (par.tag in C_PT and gp is not None and gp.tag not in C_NUMERIC):
                col.text(name, el.text, lambda v, e=el: _set_text(e, v))
        # Grafici dei tipi recenti (cascata, mappa ad albero, imbuto...): categorie e titoli
        for el in root.iter(*_q(CX_NS, "pt")):
            lvl = el.getparent()
            dim = lvl.getparent() if lvl is not None else None
            if dim is not None and _local(dim.tag) == "strDim":
                col.text(name, el.text, lambda v, e=el: _set_text(e, v))
        for el in root.iter(*_q(CX_NS, "v")):
            par = el.getparent()
            if par is not None and _local(par.tag) == "txData":
                col.text(name, el.text, lambda v, e=el: _set_text(e, v))
        # Commenti classici di PowerPoint: <p:cm><p:text>testo</p:text></p:cm> (non e' un paragrafo DrawingML)
        for el in root.iter(*_q(P_NS, "text")):
            par = el.getparent()
            if par is not None and _local(par.tag) == "cm":
                col.text(name, el.text, lambda v, e=el: _set_text(e, v))
        if kind == "xlsx":
            _collect_xlsx_part(name, root, col, person, sheet_renames, sst_map, ctx)
        # Attributi con nomi di persone / testi alternativi
        for el in root.iter():
            if not isinstance(el.tag, str):
                continue
            tag_local = _local(el.tag)
            for k, v in list(el.attrib.items()):
                lk = _local(k)
                if not v or not v.strip():
                    continue
                # «displayName» e' un nome di persona solo in <person> (commenti a thread): quello delle tabelle di
                # Excel (<table displayName="Tabella1">) e' un identificatore e NON va toccato. Prima diventava
                # «[PERSONA_n]»: nome non valido per Excel e voce fasulla nel Vault per ogni tabella.
                if lk == "author" or (lk == "name" and tag_local in _AUTHOR_TAGS) or \
                        (lk == "displayName" and tag_local == "person") or \
                        (lk == "userName" and tag_local in ("fileSharing", "header")) or \
                        (lk == "user" and tag_local == "scenario"):
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv), force=person)
                elif lk == "initials" and tag_local in ("cmAuthor", "author", "comment", "person"):
                    if ctx.anonymize:
                        el.set(k, "--")
                elif lk in ("userId", "providerId") and "@" in v:
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv))
                elif lk in ("descr", "title", "alt", "tooltip"):
                    # testo alternativo e titolo di immagini e forme (anche VML: v:shape alt, v:imagedata o:title),
                    # descrizione dei collegamenti
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv))
                elif lk == "name" and tag_local in ("cNvPr", "docPr"):
                    _file_name_attr(col, name, el, k, v)      # Word ci scrive il nome del file dell'immagine
                elif lk == "string" and tag_local == "textpath":
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv))      # testo WordArt (filigrane)
                elif lk == "val" and tag_local in _VAL_TEXT_TAGS:
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv))
                elif lk in ("displayText", "value") and tag_local == "listItem":
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv))      # voci degli elenchi a discesa
                elif lk in ("prompt", "error", "promptTitle", "errorTitle") and tag_local == "dataValidation":
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv))
                elif lk == "comment" and tag_local in ("definedName", "scenario"):
                    col.text(name, v, lambda nv, e=el, kk=k: e.set(kk, nv))
        # Parti XML personalizzate (customXml): tutti i nodi di testo
        if low.startswith("customxml/"):
            for el in root.iter():
                if isinstance(el.tag, str) and el.text and el.text.strip() and len(el) == 0:
                    col.text(name, el.text, lambda v, e=el: _set_text(e, v), context=_local(el.tag) + ": ")


def _collect_docprops(name, root, col, person, sheet_names=()):
    for el in root.iter():
        if not isinstance(el.tag, str) or not el.text or not el.text.strip():
            continue
        lk = _local(el.tag)
        if lk in ("creator", "lastModifiedBy", "Manager"):
            col.text(name, el.text, lambda v, e=el: _set_text(e, v), force=person)
        elif lk in ("title", "subject", "keywords", "description", "category", "contentStatus", "Company",
                    "HyperlinkBase", "lpwstr", "Template"):
            col.text(name, el.text, lambda v, e=el: _set_text(e, v))
        elif lk == "lpstr" and el.text not in sheet_names:
            # TitlesOfParts di app.xml: titoli di tutte le slide, titolo del documento Word. I nomi dei fogli di Excel
            # seguono invece la rinomina del foglio (_finish_xlsx), per restare uguali a quelli veri.
            col.text(name, el.text, lambda v, e=el: _set_text(e, v))


def _si_segments(si):
    segs = []
    for child in si:
        if child.tag in S_T:
            segs.append(Segment(child.text or "", setter=lambda v, e=child: _set_text_preserve(e, v)))
        elif child.tag in S_R:
            for t in child:
                if t.tag in S_T:
                    segs.append(Segment(t.text or "", setter=lambda v, e=t: _set_text_preserve(e, v)))
    return segs


def _formula_strings(col, part, el):
    """Stringhe scritte dentro una formula o in un elenco di convalida: =SE(B1="Mario Rossi";...), "Rossi,Bianchi".
    Si analizza solo il contenuto fra virgolette (il resto e' sintassi: riferimenti, nomi dei fogli, funzioni) e le
    sostituzioni si riportano sul testo della formula."""
    text = el.text
    if not text or '"' not in text:
        return
    state = {"orig": text, "repls": []}
    for m in _FORMULA_STR_RE.finditer(text):
        a, b = m.start(1), m.end(1)
        if b - a < 3 or not text[a:b].strip():
            continue

        def _ap(r, off=a, e=el, st=state):
            if not r:
                return False
            st["repls"].extend((off + s, off + t, rep.replace('"', '""')) for s, t, rep in r)
            e.text = apply_replacements(st["orig"], st["repls"])
            return True
        col.units.append(Unit(text[a:b]))
        col.appliers.append((part, _ap))


def _numeric_cell_to_text(cell, value_el, text):
    """Una cella numerica il cui valore e' un dato personale (telefono, partita IVA scritti come numeri) diventa una
    cella di testo con l'etichetta: il numero non puo' restare ne' nel valore ne' nella formula."""
    ns = cell.tag[:cell.tag.index("}") + 1] if cell.tag.startswith("{") else ""
    for child in list(cell):
        if _local(child.tag) in ("v", "f", "is"):
            cell.remove(child)
    cell.set("t", "inlineStr")
    is_ = etree.SubElement(cell, ns + "is")
    t = etree.SubElement(is_, ns + "t")
    _set_text_preserve(t, text)
    ext = next((ch for ch in cell if _local(ch.tag) == "extLst"), None)
    if ext is not None:                      # ordine dello schema: is prima di extLst
        cell.remove(ext)
        cell.append(ext)


def _collect_xlsx_part(name, root, col, person, sheet_renames, sst_map, ctx=None):
    tag = _local(root.tag)
    if tag == "sst":
        for si in root:
            if si.tag in S_SI:
                segs = _si_segments(si)
                if not segs:
                    continue
                old = segments_text(segs)

                def _ap(r, s=segs, o=old, item=si):
                    if not r:
                        return False
                    apply_to_segments(s, r)
                    sst_map[o] = segments_text(s)
                    for child in list(item):          # lettura fonetica (furigana) del testo appena sostituito
                        if child.tag in S_RPH or _local(child.tag) == "phoneticPr":
                            item.remove(child)
                    return True
                if old.strip():
                    col.units.append(Unit(old))
                    col.appliers.append((name, _ap))
    elif tag == "worksheet":
        for c in root.iter(*_q(S_NS, "c")):
            t = c.get("t")
            if t == "inlineStr":
                for is_ in c:
                    if _local(is_.tag) == "is":
                        col.segments(name, _si_segments(is_))
            elif t == "str":
                for v in c:
                    if _local(v.tag) == "v" and v.text:
                        col.text(name, v.text, lambda nv, e=v: _set_text(e, nv))
            elif t in (None, "n"):
                # Numeri lunghi (8-15 cifre): un telefono o una partita IVA digitati in Excel diventano numeri e
                # prima non venivano mai analizzati. Se risultano un dato personale la cella diventa testo.
                for v in c:
                    if _local(v.tag) == "v" and v.text and _NUMERIC_CELL_RE.fullmatch(v.text.strip()):
                        col.text(name, v.text.strip(), lambda nv, cell=c, e=v: _numeric_cell_to_text(cell, e, nv))
        for el in root.iter():
            if isinstance(el.tag, str) and _local(el.tag) in ("f", "formula1", "formula2", "formula"):
                _formula_strings(col, name, el)
        for hf in root.iter(*_q(S_NS, "headerFooter")):
            for el in hf:
                if el.text and el.text.strip():
                    col.text(name, el.text, lambda v, e=el: _set_text(e, v))
    elif tag == "comments":
        for el in root.iter():
            lk = _local(el.tag)
            if lk == "author" and el.text:
                col.text(name, el.text, lambda v, e=el: _set_text(e, v), force=person)
            elif lk == "text":
                col.segments(name, _si_segments(el))
    elif tag == "ThreadedComments":
        for el in root.iter():
            if _local(el.tag) == "text" and el.text:
                col.text(name, el.text, lambda v, e=el: _set_text(e, v))
    elif tag == "workbook":
        for sh in root.iter(*_q(S_NS, "sheet")):
            old = sh.get("name")
            if not old:
                continue
            if ctx is not None and not ctx.anonymize:
                new = restore_sheet_name(old, ctx)
                if new != old:
                    sheet_renames[old] = (sh, new)
            else:
                col.text(name, old, lambda nv, e=sh, o=old: sheet_renames.__setitem__(o, (e, nv)))
        for el in root.iter(*_q(S_NS, "definedName")):
            _formula_strings(col, name, el)
    elif tag in ("pivotCacheDefinition", "pivotCacheRecords"):
        # la cache di una tabella pivot e' una copia dei dati di origine: valori condivisi (definition) e, per i
        # campi senza elenco condiviso, valori riga per riga (records)
        for el in root.iter():
            if isinstance(el.tag, str) and _local(el.tag) == "s" and el.get("v"):
                col.text(name, el.get("v"), lambda nv, e=el: e.set("v", nv))


def _collect_rels(rels, col):
    for name, root in rels.items():
        for rel in root:
            if rel.get("TargetMode") != "External":
                continue
            target = rel.get("Target") or ""
            if target.lower().startswith(("mailto:", "tel:", "file:", "callto:", "sms:")) or re.match(r"^[A-Za-z]:\\", target):
                col.text(name, target, lambda v, e=rel: e.set("Target", v))


# ------------------------------------------------------------------------------------------------
_SHEET_BAD = re.compile(r"[\[\]:*?/\\]")
_BARE_TAG_RE = re.compile(r"(?<![A-Za-z0-9_])[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ.]*(?:_[A-ZÀ-ÖØ-Þ.]+)*_\d{1,7}(?!\d)")


def restore_sheet_name(name, ctx):
    """Ripristino del nome di un foglio (Excel, Calc). Excel e LibreOffice vietano [ ] : * ? / \\ nei nomi dei fogli,
    quindi l'etichetta vi e' scritta senza quei caratteri («PERSONA_1» per [PERSONA_1], «COD.FISCALEP.IVA_3» per
    [COD.FISCALE/P.IVA_3]): il ripristino normale, che cerca le parentesi quadre, non la trovava e il foglio restava
    con l'etichetta al posto del nome."""
    tag_map = getattr(ctx, "tag_map", None)
    if not tag_map or "_" not in name:
        return name
    bare = ctx.shared.get("sheet_tags")
    if bare is None:
        bare = ctx.shared["sheet_tags"] = {_SHEET_BAD.sub("", tag): word for tag, word in tag_map.items()}
    return _BARE_TAG_RE.sub(lambda m: bare.get(m.group(0), m.group(0)), name)


def _replace_sheet_refs(text, renames):
    if not text:
        return text
    out = text
    for old, new in renames.items():
        q_new = "'" + new.replace("'", "''") + "'!"
        out = out.replace("'" + old.replace("'", "''") + "'!", q_new)
        if re.fullmatch(r"[A-Za-z_À-ɏ][\w.À-ɏ]*", old):
            out = re.sub(r"(?<![\w.'!])" + re.escape(old) + r"!", lambda m: q_new, out)
    return out


def _finish_xlsx(trees, sheet_renames, sst_map):
    changed = set()
    renames = {}
    used = set()
    wb_name = None
    for name, root in trees.items():
        if _local(root.tag) == "workbook":
            wb_name = name
            for sh in root.iter(*_q(S_NS, "sheet")):
                used.add((sh.get("name") or "").lower())
    for old, (el, new_raw) in sheet_renames.items():
        new = _SHEET_BAD.sub("", new_raw).strip().strip("'")[:31] or "Foglio"
        if new == old:
            continue
        used.discard(old.lower())
        base, k = new, 2
        while new.lower() in used:
            suffix = f" ({k})"
            new = base[:31 - len(suffix)] + suffix
            k += 1
        used.add(new.lower())
        el.set("name", new)
        renames[old] = new
    if renames and wb_name:
        changed.add(wb_name)
        for name, root in trees.items():
            touched = False
            for el in root.iter():
                lk = _local(el.tag) if isinstance(el.tag, str) else ""
                if lk in ("f", "definedName", "formula1", "formula2", "formula") and el.text:
                    # anche convalida dati e formattazione condizionale: prima il vecchio nome del foglio vi restava
                    nt = _replace_sheet_refs(el.text, renames)
                    if nt != el.text:
                        el.text = nt
                        touched = True
                elif lk == "hyperlink" and el.get("location"):
                    nt = _replace_sheet_refs(el.get("location"), renames)
                    if nt != el.get("location"):
                        el.set("location", nt)
                        touched = True
                elif lk == "worksheetSource" and el.get("sheet") in renames:
                    el.set("sheet", renames[el.get("sheet")])
                    touched = True
                elif lk == "lpstr" and el.text in renames:
                    el.text = renames[el.text]
                    touched = True
            if touched:
                changed.add(name)
    if sst_map:
        # Le intestazioni delle tabelle Excel devono coincidere con il testo delle celle
        for name, root in trees.items():
            if _local(root.tag) != "table":
                continue
            touched = False
            for tc in root.iter(*_q(S_NS, "tableColumn")):
                nm = tc.get("name")
                if nm in sst_map and sst_map[nm] != nm:
                    tc.set("name", sst_map[nm])
                    touched = True
            if touched:
                changed.add(name)
    return changed
