"""PDF: censura a livello di carattere, OCR su scansioni (anche miste con timbro digitale),
volti/firme/targhe, campi modulo, commenti, segnalibri, metadati e file incorporati."""
from array import array

from .. import common
from ..analyzer import Unit, apply_replacements
from . import is_supported, process_bytes, ProcessingError

ZOOM = 2.0
_SEP = -1.0e9
_DENSITY_OCR = 12.0  # caratteri digitali ogni 10.000 pt^2 di immagine sotto i quali la pagina si considera scansione


def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover
        import fitz
    return fitz


def extract_chars(page, fitz):
    """Testo della pagina + riquadro di ogni carattere (array compatto: 4 float per carattere)."""
    flags = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP
    rd = page.get_text("rawdict", flags=flags)
    parts = []
    boxes = array("f")
    sizes = array("f")
    for block in rd.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                size = float(span.get("size", 10.0) or 10.0)
                for ch in span.get("chars", []):
                    c = ch.get("c", "")
                    bb = ch.get("bbox") or (0, 0, 0, 0)
                    for cc in c:
                        parts.append(cc)
                        boxes.extend((bb[0], bb[1], bb[2], bb[3]))
                        sizes.append(size)
            parts.append("\n")
            boxes.extend((_SEP, 0, 0, 0))
            sizes.append(0.0)
        parts.append("\n")
        boxes.extend((_SEP, 0, 0, 0))
        sizes.append(0.0)
    return "".join(parts), boxes, sizes


def span_rects(boxes, s, e, fitz):
    """Riquadri (uno per riga) che coprono i caratteri [s, e)."""
    rects = []
    cur = None
    for i in range(s, e):
        x0 = boxes[4 * i]
        if x0 <= _SEP / 2:
            if cur:
                rects.append(cur)
                cur = None
            continue
        r = (x0, boxes[4 * i + 1], boxes[4 * i + 2], boxes[4 * i + 3])
        if r[2] - r[0] <= 0 and r[3] - r[1] <= 0:
            continue
        if cur is None:
            cur = list(r)
        elif r[1] < cur[3] and r[3] > cur[1] and r[0] >= cur[0] - 2:
            cur = [min(cur[0], r[0]), min(cur[1], r[1]), max(cur[2], r[2]), max(cur[3], r[3])]
        else:
            rects.append(cur)
            cur = list(r)
    if cur:
        rects.append(cur)
    return [fitz.Rect(*r) for r in rects]


MIN_LABEL_FS = 4.0  # PyMuPDF non inserisce testo di sostituzione sotto i 4 pt


def _text_width(fitz, text, fs):
    try:
        return fitz.get_text_length(text, fontname="helv", fontsize=fs)
    except Exception:
        return len(text) * 0.55 * fs


def _fit_fontsize(fitz, label, rect, size_hint):
    w1 = _text_width(fitz, label, 1)
    if w1 <= 0:
        return 0
    # margine del 10%: insert_textbox richiede un po' di spazio oltre la larghezza teorica del testo
    return min(size_hint or 10.0, rect.width * 0.90 / w1, rect.height / 1.25)


def _max_size(sizes, s, e):
    m = 0.0
    for i in range(s, min(e, len(sizes))):
        if sizes[i] > m:
            m = sizes[i]
    return m or 10.0


def _needs_ocr(page, text, boxes, big_imgs):
    if not text.strip():
        return True
    if not big_imgs:
        return False
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    big_area = min(page_area, sum(abs(r.get_area()) for r in big_imgs))
    inside = 0
    n = len(boxes) // 4
    for i in range(n):
        x0 = boxes[4 * i]
        if x0 <= _SEP / 2 or text[i].isspace():
            continue
        cx = (x0 + boxes[4 * i + 2]) / 2
        cy = (boxes[4 * i + 1] + boxes[4 * i + 3]) / 2
        for r in big_imgs:
            if r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1:
                inside += 1
                break
    density = inside / max(1.0, big_area / 10000.0)
    return density < _DENSITY_OCR


def _annotation_rects(page, fitz):
    """Aree di campi modulo e annotazioni con testo visibile: il loro testo compare in get_text() ma appartiene
    all'annotazione, che viene anonimizzata direttamente (altrimenti il testo comparirebbe due volte)."""
    rects = []
    try:
        for w in page.widgets():
            rects.append(fitz.Rect(w.rect))
    except Exception:
        pass
    try:
        for a in page.annots():
            if a.type[0] in (fitz.PDF_ANNOT_FREE_TEXT, fitz.PDF_ANNOT_WIDGET):
                rects.append(fitz.Rect(a.rect))
    except Exception:
        pass
    return rects


def _inside_any(rect, rects):
    """True se il riquadro e' per la maggior parte dentro un'annotazione (il riquadro dei caratteri include
    ascendenti/discendenti e puo' sbordare in verticale dal campo modulo)."""
    a = abs(rect.get_area())
    if a <= 0:
        return False
    for r in rects:
        inter = rect & r
        if not inter.is_empty and abs(inter.get_area()) >= 0.5 * a:
            return True
    return False


_VISION_LABELS = {"[VOLTO]", "[FIRMA]", "[TARGA]"}


def _overlaps_any(rect, rects, ratio=0.3):
    a = abs(rect.get_area()) or 1.0
    for r in rects:
        inter = rect & r
        if not inter.is_empty and abs(inter.get_area()) >= ratio * min(a, abs(r.get_area()) or 1.0):
            return True
    return False


def _overlaps_image(rect, img_rects):
    a = abs(rect.get_area()) or 1.0
    for ir in img_rects:
        inter = rect & ir
        if not inter.is_empty and abs(inter.get_area()) > 0.3 * a:
            return True
    return False


def _render_rgb(page, fitz):
    import numpy as np
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 1:
        img = np.repeat(img, 3, axis=2)
    elif pix.n > 3:
        img = img[:, :, :3]
    return np.ascontiguousarray(img)


def _pix_to_page(page, fitz, x0, y0, x1, y1):
    r = fitz.Rect(x0 / ZOOM, y0 / ZOOM, x1 / ZOOM, y1 / ZOOM) * page.derotation_matrix
    r.normalize()
    return r


# ------------------------------------------------------------------------------------------------
def process_pdf(in_path, out_path, ctx):
    fitz = _fitz()
    doc = fitz.open(in_path)
    try:
        if doc.needs_pass:
            raise ProcessingError("PDF protetto da password: impossibile elaborarlo senza la password.")
        if not doc.is_pdf:
            data = doc.convert_to_pdf()
            doc.close()
            doc = fitz.open("pdf", data)
        _process_doc(doc, ctx, fitz)
        doc.save(out_path, garbage=4, deflate=True, clean=True, encryption=fitz.PDF_ENCRYPT_NONE)
    finally:
        doc.close()
    return None


def _process_doc(doc, ctx, fitz):
    n_pages = len(doc)
    units, appliers = [], []

    def add(text, applier, force=None):
        if isinstance(text, str) and text.strip():
            units.append(Unit(text, force_label=force))
            appliers.append(applier)

    person = "[PERSONA]" if ctx.settings.get("censor_person", True) else None

    # --- Passo 1: testo digitale delle pagine ---------------------------------------------------
    page_data = []
    for pno in range(n_pages):
        ctx.check()
        ctx.report(f"lettura pagina {pno + 1}/{n_pages}")
        page = doc[pno]
        text, boxes, sizes = extract_chars(page, fitz)
        page_data.append((text, boxes, sizes))
        units.append(Unit(text))
        appliers.append(("page", pno))

    # --- Campi modulo, commenti, segnalibri, metadati (analizzati insieme al testo) -------------
    widget_updates, annot_updates = {}, {}
    sign_widgets = []
    for pno in range(n_pages):
        page = doc[pno]
        try:
            for w in page.widgets():
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    sign_widgets.append((pno, w.xref))
                    continue
                if w.field_type in (fitz.PDF_WIDGET_TYPE_TEXT, fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
                    v = w.field_value
                    if isinstance(v, str) and v.strip():
                        add(v, lambda nv, k=(pno, w.xref): widget_updates.__setitem__(k, nv))
        except Exception:
            pass
        try:
            for a in page.annots():
                if a.type[0] in (fitz.PDF_ANNOT_REDACT, fitz.PDF_ANNOT_WIDGET, fitz.PDF_ANNOT_POPUP):
                    continue
                info = a.info or {}
                for field in ("content", "subject", "title"):
                    v = info.get(field)
                    if isinstance(v, str) and v.strip():
                        add(v, lambda nv, k=(pno, a.xref), f=field: annot_updates.setdefault(k, {}).__setitem__(f, nv),
                            force=person if field == "title" else None)
        except Exception:
            pass

    toc = []
    try:
        toc = doc.get_toc(simple=False)
    except Exception:
        toc = []
    toc_changed = [False]
    for item in toc:
        def _set_toc(nv, it=item):
            it[1] = nv
            toc_changed[0] = True
        add(item[1], _set_toc)

    meta = dict(doc.metadata or {})
    new_meta = {}
    for field in ("title", "author", "subject", "keywords", "creator", "producer"):
        v = meta.get(field)
        if isinstance(v, str) and v.strip():
            add(v, lambda nv, f=field: new_meta.__setitem__(f, nv), force=person if field == "author" else None)

    results = ctx.analyze(units)

    page_repls = {}
    for u, ap, r in zip(units, appliers, results):
        if isinstance(ap, tuple) and ap[0] == "page":
            page_repls[ap[1]] = r
        elif r:
            ap(apply_replacements(u.text, r))

    # --- Passo 2: censura pagina per pagina -------------------------------------------------------
    total_regions = 0
    for pno in range(n_pages):
        ctx.check()
        ctx.report(f"pagina {pno + 1}/{n_pages}")
        page = doc[pno]
        text, boxes, sizes = page_data[pno]
        repls = page_repls.get(pno) or []
        if ctx.anonymize:
            total_regions += _anonymize_page(page, fitz, ctx, text, boxes, sizes, repls)
        else:
            _restore_page(page, fitz, text, boxes, sizes, repls)
        page_data[pno] = None

    # --- Passo 3: campi modulo, commenti, link, segnalibri, metadati -----------------------------
    for pno in range(n_pages):
        page = doc[pno]
        if widget_updates:
            try:
                for w in page.widgets():
                    nv = widget_updates.get((pno, w.xref))
                    if nv is not None:
                        w.field_value = nv
                        w.update()
            except Exception as e:
                ctx.note(f"campo modulo non aggiornabile a pagina {pno + 1}: {e}")
        if annot_updates:
            try:
                for a in page.annots():
                    upd = annot_updates.get((pno, a.xref))
                    if upd:
                        a.set_info(**upd)
                        a.update()
            except Exception as e:
                ctx.note(f"commento non aggiornabile a pagina {pno + 1}: {e}")
        if ctx.anonymize:
            try:
                for link in page.get_links():
                    uri = (link.get("uri") or "").lower()
                    if uri.startswith(("mailto:", "tel:", "sms:", "callto:")):
                        page.delete_link(link)
            except Exception:
                pass
    if ctx.anonymize and sign_widgets:
        for pno, xref in sign_widgets:
            try:
                page = doc[pno]
                for w in page.widgets():
                    if w.xref == xref:
                        page.delete_widget(w)
                        break
            except Exception:
                pass
        ctx.note("Firma digitale rimossa dal PDF (conteneva i dati del firmatario; dopo la modifica non sarebbe piu' valida).")
    if toc_changed[0]:
        try:
            doc.set_toc(toc)
        except Exception as e:
            ctx.note(f"segnalibri non aggiornati: {e}")
    if new_meta:
        md = {k: meta.get(k) or "" for k in ("title", "author", "subject", "keywords", "creator", "producer",
                                           "creationDate", "modDate", "trapped")}
        md.update(new_meta)
        try:
            doc.set_metadata(md)
        except Exception:
            pass
    if ctx.anonymize:
        try:
            doc.del_xml_metadata()
        except Exception:
            pass

    _process_attachments(doc, ctx, fitz)
    if total_regions:
        common.log(f"PDF: oscurate {total_regions} aree visive (scansioni, volti, firme, targhe).")


def _anonymize_page(page, fitz, ctx, text, boxes, sizes, repls):
    img_rects = []
    try:
        for info in page.get_image_info():
            r = fitz.Rect(info["bbox"])
            if not r.is_empty and r.is_valid:
                img_rects.append(r)
    except Exception:
        pass
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    big_imgs = [r for r in img_rects if abs(r.get_area()) >= 0.12 * page_area]
    annot_rects = _annotation_rects(page, fitz)

    redact_rects = []
    removed = []
    labels_later = []
    for s, e, label in repls:
        rects = [r for r in span_rects(boxes, s, e, fitz) if not _inside_any(r, annot_rects)]
        if not rects:
            continue
        removed.append((s, e))
        size_hint = _max_size(sizes, s, e)
        for k, r in enumerate(rects):
            r = fitz.Rect(r.x0 - 0.3, r.y0, r.x1 + 0.3, r.y1)
            on_img = _overlaps_image(r, img_rects)
            txt = None
            fs = 11
            if k == 0:
                if on_img:
                    # testo (anche invisibile) sopra una scansione: riquadro nero con etichetta, subito
                    fs = _fit_fontsize(fitz, label, r, size_hint)
                    txt = label if fs >= MIN_LABEL_FS else None
                    fs = fs if fs >= MIN_LABEL_FS else 11
                else:
                    labels_later.append((s, e, r, label, size_hint))
            page.add_redact_annot(
                r, text=txt, fontname="helv", fontsize=fs,
                fill=(0, 0, 0) if on_img else False,
                text_color=(1, 1, 1) if on_img else (0, 0, 0), cross_out=False,
            )
            redact_rects.append(r)

    has_text = bool(text.strip())
    vision = bool(img_rects) or not has_text
    need_ocr = bool(ctx.settings.get("enable_ocr", True)) and _needs_ocr(page, text, boxes, big_imgs)
    n_regions = 0
    if ctx.vision_enabled() and (vision or need_ocr):
        from .images import find_regions
        if need_ocr and has_text:
            common.log("Pagina con scansione e testo digitale parziale: OCR attivato anche sull'immagine.")
        elif need_ocr:
            common.log("Pagina scansionata: OCR attivato.")
        img = _render_rgb(page, fitz)
        ocr_areas = None
        if need_ocr and has_text:
            # Pagina mista: l'OCR serve solo sulle immagini scansionate; il testo digitale (es. timbro di
            # protocollo) e' gia' stato analizzato con precisione dal livello testo.
            m = page.rotation_matrix * fitz.Matrix(ZOOM, ZOOM)
            ocr_areas = []
            for br in big_imgs:
                pr = fitz.Rect(br) * m
                pr.normalize()
                ocr_areas.append((pr.x0, pr.y0, pr.x1, pr.y1))
        regions = find_regions(ctx, img, allow_plates=bool(img_rects) or not has_text, allow_ocr=need_ocr,
                               ocr_areas=ocr_areas)
        text_rects = list(redact_rects)
        for x0, y0, x1, y1, label in regions:
            r = _pix_to_page(page, fitz, x0, y0, x1, y1)
            if r.is_empty or not r.is_valid:
                continue
            fs = _fit_fontsize(fitz, label, r, max(6.0, r.height * 0.6))
            show = fs >= MIN_LABEL_FS
            if show and label not in _VISION_LABELS and _overlaps_any(r, text_rects):
                # gia' censurato dal livello testo (es. scansione ricercabile): si mantiene la doppia copertura
                # (protegge da livelli OCR disallineati) ma senza ripetere l'etichetta
                show = False
            page.add_redact_annot(
                r, text=label if show else None, fontname="helv", fontsize=fs if show else 11,
                fill=(0, 0, 0), text_color=(1, 1, 1), cross_out=False,
            )
            redact_rects.append(r)
            n_regions += 1

    if redact_rects:
        # Firme/annotazioni a mano libera o timbri sopra le aree censurate vengono eliminati
        try:
            for a in list(page.annots()):
                if a.type[0] in (fitz.PDF_ANNOT_INK, fitz.PDF_ANNOT_STAMP):
                    if any(not (a.rect & r).is_empty for r in redact_rects):
                        page.delete_annot(a)
        except Exception:
            pass
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_PIXELS,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )
    if labels_later:
        _place_labels(page, fitz, text, boxes, removed, labels_later)
    return n_regions


def _is_sep(boxes, i):
    return boxes[4 * i] <= _SEP / 2


def _place_labels(page, fitz, text, boxes, removed, items):
    """Secondo passaggio: inserisce le etichette nello spazio realmente rimasto libero.

    MuPDF 1.28, rimuovendo glifi da una stringa di testo, sposta a sinistra il resto della riga della larghezza
    del primo glifo rimosso. Invece di usare le coordinate originali, si rilegge la pagina e si misura il vuoto
    tra il carattere precedente e quello successivo; l'etichetta viene poi inserita senza rimuovere altro testo."""
    from bisect import bisect_right
    from difflib import SequenceMatcher

    removed = sorted(removed)
    starts = [a for a, _ in removed]

    def in_removed(i):
        k = bisect_right(starts, i) - 1
        return k >= 0 and removed[k][0] <= i < removed[k][1]

    new_text, new_boxes, _sizes = extract_chars(page, fitz)
    orig_idx = [i for i in range(len(text)) if not _is_sep(boxes, i) and not in_removed(i)]
    new_idx = [j for j in range(len(new_text)) if not _is_sep(new_boxes, j)]
    mapping = {}
    sm = SequenceMatcher(None, "".join(text[i] for i in orig_idx), "".join(new_text[j] for j in new_idx), autojunk=False)
    for blk in sm.get_matching_blocks():
        for t in range(blk.size):
            mapping[orig_idx[blk.a + t]] = new_idx[blk.b + t]

    n = len(text)
    placed = 0
    for s, e, r, label, size_hint in items:
        prev = None
        i = s - 1
        while i >= 0 and not _is_sep(boxes, i):
            if not in_removed(i):
                prev = i
                break
            i -= 1
        j = s
        while j < e and not _is_sep(boxes, j):
            j += 1
        nxt = None
        if j == e:
            k = e
            while k < n and not _is_sep(boxes, k):
                if not in_removed(k):
                    nxt = k
                    break
                k += 1
        x0 = new_boxes[4 * mapping[prev] + 2] if prev in mapping else r.x0
        x1 = new_boxes[4 * mapping[nxt]] if nxt in mapping else r.x1
        if prev is not None and prev not in mapping:
            x0 = r.x0
        if nxt is not None and nxt not in mapping:
            x1 = r.x1
        gap = fitz.Rect(x0 + 0.25, r.y0, x1 - 0.25, r.y1)
        if gap.width < 2 or gap.is_empty:
            continue
        fs = _fit_fontsize(fitz, label, gap, size_hint)
        if fs < MIN_LABEL_FS:
            # spazio stretto: corpo minimo leggibile, area allargata simmetricamente (massimo 12 pt in tutto;
            # in questo passaggio non si rimuove testo, al piu' l'etichetta sfiora i caratteri vicini)
            need = _text_width(fitz, label, MIN_LABEL_FS) / 0.90 + 0.5
            extra = need - gap.width
            if extra > 12 or gap.height < MIN_LABEL_FS * 1.25:
                continue
            gap = fitz.Rect(gap.x0 - extra / 2, gap.y0, gap.x1 + extra / 2, gap.y1)
            fs = MIN_LABEL_FS
        page.add_redact_annot(gap, text=label, fontname="helv", fontsize=fs, fill=False,
                              text_color=(0, 0, 0), cross_out=False)
        placed += 1
    if placed:
        # nessuna rimozione: le aree sono gia' vuote, si inserisce solo il testo delle etichette
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_NONE)


def _restore_page(page, fitz, text, boxes, sizes, repls):
    if not repls:
        return
    removed, items = [], []
    for s, e, word in repls:
        rects = span_rects(boxes, s, e, fitz)
        if not rects:
            continue
        removed.append((s, e))
        items.append((s, e, rects[0], word, _max_size(sizes, s, e)))
        for r in rects:
            page.add_redact_annot(r, fill=False, cross_out=False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)
    _place_labels(page, fitz, text, boxes, removed, items)


def _replace_embedded(doc, name, data, info):
    try:
        doc.embfile_upd(name, buffer_=data)
        return
    except Exception:
        pass
    # PyMuPDF 2.0: embfile_upd puo' fallire con bytes -> si rimuove e si riaggiunge il file
    doc.embfile_del(name)
    # la descrizione (testo libero, possibile dato personale) non viene ricopiata
    doc.embfile_add(name, data, filename=info.get("filename") or name, ufilename=info.get("ufilename") or name, desc="")


def _process_attachments(doc, ctx, fitz):
    # File incorporati (portfolio / allegati del documento)
    try:
        names = list(doc.embfile_names())
    except Exception:
        names = []
    for name in names:
        ctx.check()
        try:
            info = doc.embfile_info(name) or {}
            fname = info.get("filename") or info.get("ufilename") or name
            data = doc.embfile_get(name)
        except Exception:
            continue
        base = str(fname).replace("\\", "/").split("/")[-1] or "allegato.bin"
        if is_supported(base):
            try:
                new_data, _ = process_bytes(data, base, ctx.child())
                _replace_embedded(doc, name, new_data, info)
                common.log(f"PDF: allegato incorporato elaborato ({base}).")
                continue
            except Exception as e:
                reason = str(e)
        else:
            reason = "formato non supportato"
        if ctx.anonymize:
            try:
                doc.embfile_del(name)
                ctx.note(f"Allegato incorporato rimosso per sicurezza ({base}: {reason}).")
            except Exception:
                pass
    # Annotazioni "file allegato"
    for pno in range(len(doc)):
        page = doc[pno]
        try:
            atts = [a for a in page.annots() if a.type[0] == fitz.PDF_ANNOT_FILE_ATTACHMENT]
        except Exception:
            atts = []
        for a in atts:
            try:
                fi = a.file_info or {}
                base = str(fi.get("filename") or "allegato.bin").replace("\\", "/").split("/")[-1]
                data = a.get_file()
                if is_supported(base):
                    new_data, _ = process_bytes(data, base, ctx.child())
                    a.update_file(buffer_=new_data)
                    continue
                if ctx.anonymize:
                    page.delete_annot(a)
                    ctx.note(f"Allegato in annotazione rimosso per sicurezza ({base}: formato non supportato).")
            except Exception as e:
                if ctx.anonymize:
                    try:
                        page.delete_annot(a)
                        ctx.note(f"Allegato in annotazione rimosso per sicurezza ({e}).")
                    except Exception:
                        pass
