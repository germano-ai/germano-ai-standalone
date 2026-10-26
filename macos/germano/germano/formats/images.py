"""Immagini: oscuramento di volti, firme, targhe e testo personale letto via OCR.

- Risoluzione originale preservata (v0.50 riesportava a 72 dpi).
- Orientamento EXIF applicato prima del rilevamento (foto da smartphone).
- Metadati EXIF/GPS/XMP rimossi; TIFF multipagina e GIF animate elaborati frame per frame.
"""
import io
import shutil

from .. import common
from ..analyzer import Unit

MIN_SIDE = 48
_ALLOWED_TIFF_COMPRESSION = {"tiff_lzw", "group4", "tiff_adobe_deflate", "raw", "packbits", "jpeg"}


def find_regions(ctx, img_rgb, allow_plates=True, allow_ocr=True, ocr_areas=None):
    """Regioni da oscurare (x0, y0, x1, y1, etichetta) in coordinate pixel.
    `ocr_areas`: se indicato, l'OCR considera solo il testo che cade in queste aree (pixel)."""
    s = ctx.settings
    eng = ctx.engine
    regions = []
    if eng is None or not ctx.anonymize:
        return regions
    if s.get("enable_faces", True):
        for x0, y0, x1, y1, sc in eng.detect_faces(img_rgb):
            regions.append((x0, y0, x1, y1, "[VOLTO]"))
            ctx.audit_add("[VOLTO OSCURATO]", "[VOLTO]", "BIOMETRIC_FACE", sc)
    pil = None
    if s.get("enable_signatures", True):
        from PIL import Image
        pil = Image.fromarray(img_rgb)
        for x0, y0, x1, y1, sc in eng.detect_signatures(pil):
            regions.append((x0, y0, x1, y1, "[FIRMA]"))
            ctx.audit_add("[FIRMA AUTOGRAFA]", "[FIRMA]", "SIGNATURE", sc)
    if allow_plates and s.get("enable_plate_vision", True):
        if pil is None:
            from PIL import Image
            pil = Image.fromarray(img_rgb)
        for x0, y0, x1, y1, sc in eng.detect_plates(pil):
            regions.append((x0, y0, x1, y1, "[TARGA]"))
            ctx.audit_add("[TARGA VEICOLO]", "[TARGA]", "LICENSE_PLATE", sc)
    if allow_ocr and s.get("enable_ocr", True) and eng.ocr_reader is not None:
        regions.extend(ocr_regions(ctx, img_rgb, ocr_areas))
    return regions


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


def ocr_regions(ctx, img_rgb, areas=None):
    """Legge il testo con l'OCR, lo analizza e restituisce i riquadri delle sole parti personali."""
    results = ctx.engine.ocr(img_rgb)
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
    if not segs:
        return []
    units = [Unit(t, ocr=True) for _, t in segs]
    res = ctx.analyze(units)
    regions = []
    for ((x0, y0, x1, y1), text), reps in zip(segs, res):
        n = max(1, len(text))
        for s, e, label in reps:
            if (e - s) >= n * 0.6:
                rx0, rx1 = x0, x1
            else:
                rx0, rx1 = _span_x(text, s, e, x0, x1)   # posizione stimata, con margine di sicurezza
            pad_y = (y1 - y0) * 0.08
            regions.append((rx0, y0 - pad_y, rx1, y1 + pad_y, label))
    return regions


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


def _anonymize_frames(im, ctx, single_transpose=True):
    from PIL import ImageOps
    import numpy as np
    n = getattr(im, "n_frames", 1) or 1
    frames, total = [], 0
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
        regions = []
        if min(work.size) >= MIN_SIDE:
            regions = find_regions(ctx, np.array(work.convert("RGB")))
        if regions:
            draw_regions(work, regions)
            total += len(regions)
        frames.append(_back_to_mode(work, orig_mode))
    return frames, total


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


def anonymize_image_bytes(data, ctx):
    """Per le immagini incorporate nei documenti: nuovi bytes oppure None se nulla da cambiare."""
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
        fmt = im.format
        info = dict(im.info)
        frames, total = _anonymize_frames(im, ctx)
        if not total and not has_meta:
            return None
        buf = io.BytesIO()
        _save_frames(frames, buf, fmt, info)
        return buf.getvalue()
    finally:
        im.close()
