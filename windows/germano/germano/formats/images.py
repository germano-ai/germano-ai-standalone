"""Immagini: oscuramento di volti, firme, targhe e testo personale letto via OCR.

- Risoluzione originale preservata (v0.50 riesportava a 72 dpi).
- Orientamento EXIF applicato prima del rilevamento (foto da smartphone).
- Metadati EXIF/GPS/XMP rimossi; TIFF multipagina e GIF animate elaborati frame per frame.
"""
import io
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor

from .. import common
from ..analyzer import Unit

MIN_SIDE = 48
_ALLOWED_TIFF_COMPRESSION = {"tiff_lzw", "group4", "tiff_adobe_deflate", "raw", "packbits", "jpeg"}
# Volti, firme, targhe e OCR di un'immagine sono modelli indipendenti (ognuno con il proprio lock nel motore): girano
# in parallelo (turno 26; prima uno dopo l'altro). Con il motore remoto (modalita' Client) partono insieme le quattro
# richieste al Germano Server.
PARALLEL_VISION = True
_POOL = []
_POOL_LOCK = threading.Lock()


def _pool():
    with _POOL_LOCK:
        if not _POOL:
            _POOL.append(ThreadPoolExecutor(max_workers=4, thread_name_prefix="visione"))
        return _POOL[0]


def scan_image(ctx, img_rgb, allow_plates=True, allow_ocr=True):
    """Prima fase: i modelli di visione sull'immagine, senza analisi del testo ne' voci di audit.
    Restituisce {"faces": [...], "signatures": [...], "plates": [...], "ocr": [...] | None}."""
    s = ctx.settings
    eng = ctx.engine
    tasks = []
    if s.get("enable_faces", True):
        tasks.append(("faces", eng.detect_faces, img_rgb))
    if s.get("enable_signatures", True) or (allow_plates and s.get("enable_plate_vision", True)):
        from PIL import Image
        if s.get("enable_signatures", True):
            tasks.append(("signatures", eng.detect_signatures, Image.fromarray(img_rgb)))
        if allow_plates and s.get("enable_plate_vision", True):
            tasks.append(("plates", eng.detect_plates, Image.fromarray(img_rgb)))
    if allow_ocr and s.get("enable_ocr", True) and eng.ocr_reader is not None:
        tasks.append(("ocr", eng.ocr, img_rgb))
    out = {"faces": [], "signatures": [], "plates": [], "ocr": None}
    if not PARALLEL_VISION or len(tasks) < 2:
        for kind, fn, arg in tasks:
            out[kind] = fn(arg)
        return out
    from ..engine import interactive_scope, is_interactive
    high = is_interactive()

    def run(fn, arg):
        with interactive_scope(high):            # la precedenza della richiesta vale anche nei thread della visione
            return fn(arg)
    futures = [(kind, _pool().submit(run, fn, arg)) for kind, fn, arg in tasks]
    first_error = None
    for kind, fut in futures:                    # si aspettano tutti; il primo errore (nell'ordine di prima) risale
        try:
            out[kind] = fut.result()
        except BaseException as e:               # noqa: BLE001
            if first_error is None:
                first_error = e
    if first_error is not None:
        raise first_error
    return out


def regions_from_scans(ctx, items):
    """Seconda fase per una o piu' immagini [(scansione, ocr_areas)]: voci di audit della visione (immagine per
    immagine, nell'ordine volti, firme, targhe) e UNA sola analisi del testo letto dall'OCR di tutte le immagini
    (lotto unico: piu' veloce e con la propagazione dei dati fra le pagine). Restituisce le regioni di ogni immagine."""
    out, segs_all, owners = [], [], []
    for k, (scan, areas) in enumerate(items):
        regions = []
        for kind, label, word, entity in (("faces", "[VOLTO]", "[VOLTO OSCURATO]", "BIOMETRIC_FACE"),
                                          ("signatures", "[FIRMA]", "[FIRMA AUTOGRAFA]", "SIGNATURE"),
                                          ("plates", "[TARGA]", "[TARGA VEICOLO]", "LICENSE_PLATE")):
            for x0, y0, x1, y1, sc in scan.get(kind) or []:
                regions.append((x0, y0, x1, y1, label))
                ctx.audit_add(word, label, entity, sc)
        out.append(regions)
        if scan.get("ocr") is not None:
            for seg in _ocr_segments(scan["ocr"], areas):
                segs_all.append(seg)
                owners.append(k)
    if segs_all:
        for k, regs in zip(owners, _regions_per_segment(ctx, segs_all)):
            out[k].extend(regs)
    return out


def find_regions(ctx, img_rgb, allow_plates=True, allow_ocr=True, ocr_areas=None):
    """Regioni da oscurare (x0, y0, x1, y1, etichetta) in coordinate pixel.
    `ocr_areas`: se indicato, l'OCR considera solo il testo che cade in queste aree (pixel)."""
    if ctx.engine is None or not ctx.anonymize:
        return []
    scan = scan_image(ctx, img_rgb, allow_plates, allow_ocr)
    return regions_from_scans(ctx, [(scan, ocr_areas)])[0]


def _in_areas(box, areas):
    x0, y0, x1, y1 = box
    a = max(1.0, (x1 - x0) * (y1 - y0))
    for ax0, ay0, ax1, ay1 in areas:
        ix = max(0.0, min(x1, ax1) - max(x0, ax0))
        iy = max(0.0, min(y1, ay1) - max(y0, ay0))
        if ix * iy >= 0.5 * a:
            return True
    return False


_NARROW_GLYPHS = set(" ijlI.,:;'!|ft")
_SEMI_GLYPHS = set("r-()[]/\"")
_WIDE_GLYPHS = set("mwMW")


def _glyph_weight(c):
    """Larghezza tipica di un carattere in un font proporzionale (in em, valori di Arial/Helvetica)."""
    if c in _NARROW_GLYPHS:
        return 0.28
    if c in _SEMI_GLYPHS:
        return 0.33
    if c in _WIDE_GLYPHS:
        return 0.83
    if c.isupper():
        return 0.68
    return 0.56


def _span_x(text, s, e, x0, x1):
    """Posizione orizzontale di text[s:e] dentro il riquadro OCR di tutta la riga. Si prende l'unione di due stime:
    a caratteri uguali (esatta con i font a larghezza fissa) e pesata sulla larghezza tipica dei glifi (font
    proporzionali). Con la sola prima, dopo un'etichetta stretta come 'Codice fiscale:' le maiuscole e le cifre del
    dato restavano in parte scoperte (es. le prime due lettere del codice fiscale)."""
    n = max(1, len(text))
    w = x1 - x0
    cw = w / n
    weights = [_glyph_weight(c) for c in text]
    total = sum(weights) or 1.0
    left = min(cw * s, sum(weights[:s]) / total * w) - cw * 0.8
    right = max(cw * e, sum(weights[:e]) / total * w) + cw * 0.8
    return max(x0, x0 + left), min(x1, x0 + right)


def _ocr_segments(results, areas=None):
    """Righe lette dall'OCR [(riquadro, testo)], solo quelle che cadono nelle aree indicate (se ce ne sono)."""
    segs = []
    for box, text, _conf in results or []:
        if not text or not text.strip():
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        bb = (min(xs), min(ys), max(xs), max(ys))
        if areas is not None and not _in_areas(bb, areas):
            continue
        segs.append((bb, text))
    return segs


def _regions_per_segment(ctx, segs):
    """Analizza il testo delle righe OCR (una sola chiamata) e restituisce, riga per riga, i riquadri dei dati."""
    units = [Unit(t, ocr=True) for _, t in segs]
    res = ctx.analyze(units)
    out = []
    for ((x0, y0, x1, y1), text), reps in zip(segs, res):
        regions = []
        n = max(1, len(text))
        for s, e, label in reps:
            if (e - s) >= n * 0.6:
                rx0, rx1 = x0, x1
            else:
                rx0, rx1 = _span_x(text, s, e, x0, x1)   # posizione stimata, con margine di sicurezza
            pad_y = (y1 - y0) * 0.08
            regions.append((rx0, y0 - pad_y, rx1, y1 + pad_y, label))
        out.append(regions)
    return out


def ocr_regions(ctx, img_rgb, areas=None):
    """Legge il testo con l'OCR, lo analizza e restituisce i riquadri delle sole parti personali."""
    segs = _ocr_segments(ctx.engine.ocr(img_rgb), areas)
    if not segs:
        return []
    return [r for regions in _regions_per_segment(ctx, segs) for r in regions]


def draw_regions(img, regions):
    from PIL import ImageDraw, ImageFont
    d = ImageDraw.Draw(img)
    black = (0, 0, 0, 255) if img.mode == "RGBA" else (0, 0, 0)
    white = (255, 255, 255, 255) if img.mode == "RGBA" else (255, 255, 255)
    for x0, y0, x1, y1, label in regions:
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(img.width, int(round(x1))), min(img.height, int(round(y1)))
        if x1 <= x0 or y1 <= y0:
            continue
        d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=black)
        h, w = y1 - y0, x1 - x0
        size = int(min(h * 0.6, (w / max(1, len(label))) * 1.7))
        if size >= 8:
            try:
                font = ImageFont.load_default(size=size)
                tw = d.textlength(label, font=font)
                if tw <= w:
                    d.text((x0 + (w - tw) / 2, y0 + (h - size) / 2), label, fill=white, font=font)
            except Exception:
                pass


def _has_alpha(im):
    return im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)


def _back_to_mode(img, orig_mode):
    if orig_mode == "1":
        return img.convert("L").point(lambda v: 255 if v > 127 else 0, "1")
    if orig_mode in ("L", "LA"):
        return img.convert(orig_mode)
    return img


def _prepare_frames(im, ctx, single_transpose=True):
    """Prima fase: fotogrammi da modificare e visione su ciascuno (l'analisi del testo letto avviene dopo)."""
    from PIL import ImageOps
    import numpy as np
    n = getattr(im, "n_frames", 1) or 1
    frames = []
    for i in range(n):
        ctx.check()
        if n > 1:
            im.seek(i)
            ctx.report(f"immagine, fotogramma {i + 1}/{n}")
            fr = im.copy()
        else:
            fr = ImageOps.exif_transpose(im) if single_transpose else im.copy()
        orig_mode = fr.mode
        work = fr.convert("RGBA") if _has_alpha(fr) else fr.convert("RGB")
        scan = None
        if min(work.size) >= MIN_SIDE and ctx.engine is not None and ctx.anonymize:
            scan = scan_image(ctx, np.array(work.convert("RGB")))
        frames.append({"work": work, "mode": orig_mode, "scan": scan, "regions": [],
                       "pixels": work.size[0] * work.size[1]})
    return frames


def _analyze_frames(ctx, frames):
    """Testo letto dall'OCR di tutti i fotogrammi indicati (anche di immagini diverse): un'unica analisi."""
    todo = [f for f in frames if f["scan"] is not None]
    if todo:
        for f, regions in zip(todo, regions_from_scans(ctx, [(f["scan"], None) for f in todo])):
            f["regions"] = regions


def _finish_frames(frames):
    out, total = [], 0
    for f in frames:
        if f["regions"]:
            draw_regions(f["work"], f["regions"])
            total += len(f["regions"])
        out.append(_back_to_mode(f["work"], f["mode"]))
    return out, total


def _anonymize_frames(im, ctx, single_transpose=True):
    frames = _prepare_frames(im, ctx, single_transpose)
    _analyze_frames(ctx, frames)
    return _finish_frames(frames)


def _save_frames(frames, dest, fmt, info):
    fmt = (fmt or "PNG").upper()
    if fmt == "MPO":  # JPEG multi-immagine di alcune fotocamere: si salva come JPEG standard
        fmt = "JPEG"
        frames = frames[:1]
    params = {}
    if info.get("dpi"):
        params["dpi"] = info["dpi"]
    icc = info.get("icc_profile")
    if isinstance(icc, bytes) and len(icc) > 20:
        space = icc[16:20]
        # Profilo colore mantenuto solo se compatibile (es. JPEG CMYK riesportato in RGB: profilo scartato)
        if (space == b"RGB " and frames[0].mode in ("RGB", "RGBA")) or (space == b"GRAY" and frames[0].mode == "L"):
            params["icc_profile"] = icc
    if fmt == "JPEG":
        frames = [f.convert("RGB") if f.mode not in ("RGB", "L") else f for f in frames]
        params.update(quality=95)
    elif fmt == "TIFF":
        comp = info.get("compression")
        if comp == "group4" and frames[0].mode != "1":
            comp = "tiff_lzw"
        if comp == "jpeg" and frames[0].mode not in ("RGB", "L"):
            comp = "tiff_lzw"
        params["compression"] = comp if comp in _ALLOWED_TIFF_COMPRESSION else "tiff_lzw"
    elif fmt == "WEBP":
        params.update(quality=95)
    elif fmt == "GIF":
        if "duration" in info:
            params["duration"] = info["duration"]
        params["loop"] = info.get("loop", 0)
    elif fmt == "BMP":
        frames = [f.convert("RGB") if f.mode not in ("RGB", "L", "1", "P") else f for f in frames]
    if len(frames) > 1 and fmt in ("TIFF", "GIF", "WEBP", "PNG"):
        frames[0].save(dest, format=fmt, save_all=True, append_images=frames[1:], **params)
    else:
        frames[0].save(dest, format=fmt, **params)


def process_image(in_path, out_path, ctx):
    if not ctx.anonymize:
        shutil.copy2(in_path, out_path)
        ctx.note("Immagine copiata senza modifiche: il ripristino dei dati non si applica alle immagini.")
        return None
    from PIL import Image
    with Image.open(in_path) as im:
        fmt = im.format
        info = dict(im.info)
        frames, total = _anonymize_frames(im, ctx)
    _save_frames(frames, out_path, fmt, info)
    if total:
        common.log(f"Oscurate {total} aree sensibili nell'immagine.")
    return None


def _prepare_bytes(data, ctx):
    """Immagine incorporata: stato della prima fase, oppure None se non c'e' nulla da fare (illeggibile, troppo
    piccola). Gli errori della visione risalgono a chi chiama."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return None
    try:
        if min(im.size) < MIN_SIDE:
            return None
        try:
            has_meta = bool(im.info.get("exif")) or bool(im.getexif()) or bool(im.info.get("xmp"))
        except Exception:
            has_meta = False
        return {"fmt": im.format, "info": dict(im.info), "has_meta": has_meta,
                "frames": _prepare_frames(im, ctx)}
    finally:
        im.close()


def _encode_prepared(st):
    frames, total = _finish_frames(st["frames"])
    if not total and not st["has_meta"]:
        return None
    buf = io.BytesIO()
    _save_frames(frames, buf, st["fmt"], st["info"])
    return buf.getvalue()


def anonymize_image_bytes(data, ctx):
    """Per le immagini incorporate nei documenti: nuovi bytes oppure None se nulla da cambiare."""
    st = _prepare_bytes(data, ctx)
    if st is None:
        return None
    _analyze_frames(ctx, st["frames"])
    return _encode_prepared(st)


class ImageBatcher:
    """Immagini incorporate di un documento (DOCX/XLSX/PPTX, ODF) elaborate a finestre (turno 26): visione immagine
    per immagine, poi UN'UNICA analisi del testo letto dall'OCR di tutta la finestra (prima: una per immagine), infine
    le immagini modificate. Memoria limitata: al massimo `window` immagini o `max_pixels` pixel alla volta.
    `on_result(chiave, bytes_nuovi | None, errore | None)` viene chiamato per ogni immagine, nell'ordine di arrivo."""

    def __init__(self, ctx, on_result, window=8, max_pixels=40_000_000):
        self.ctx, self.on_result = ctx, on_result
        self.window, self.max_pixels = window, max_pixels
        self._pending, self._pixels = [], 0

    def add(self, key, data):
        from . import reraise_control
        try:
            st = _prepare_bytes(data, self.ctx)
        except Exception as e:
            reraise_control(e)
            self.on_result(key, None, e)
            return
        if st is None:
            self.on_result(key, None, None)
            return
        self._pending.append((key, st))
        self._pixels += sum(f["pixels"] for f in st["frames"])
        if len(self._pending) >= self.window or self._pixels >= self.max_pixels:
            self.flush()

    def flush(self):
        from . import reraise_control
        pending, self._pending, self._pixels = self._pending, [], 0
        if not pending:
            return
        try:
            _analyze_frames(self.ctx, [f for _k, st in pending for f in st["frames"]])
        except Exception as e:
            reraise_control(e)
            for key, _st in pending:
                self.on_result(key, None, e)
            return
        for key, st in pending:
            try:
                nb = _encode_prepared(st)
            except Exception as e:
                reraise_control(e)
                self.on_result(key, None, e)
                continue
            self.on_result(key, nb, None)
