"""Formati Office binari: .xls (xlrd/xlutils, stili conservati), .doc/.ppt (conversione tramite
Microsoft Office in un processo separato, oppure LibreOffice se installato).

Molti file ".doc"/".xls" prodotti dai gestionali PA sono in realta' RTF, DOCX, HTML o XML rinominati:
vengono riconosciuti dal contenuto ed elaborati senza bisogno di Office."""
import glob
import os
import shutil
import subprocess
import sys
import time
import zipfile

from .. import common
from ..analyzer import Unit, apply_replacements
from . import ProcessingError

CONVERT_TIMEOUT = 240
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _sniff(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return None
    s = head.lstrip()
    if s.startswith(b"{\\rtf"):
        return "rtf"
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
            if "word/document.xml" in names:
                return "docx"
            if "xl/workbook.xml" in names:
                return "xlsx"
            if "ppt/presentation.xml" in names:
                return "pptx"
        except zipfile.BadZipFile:
            return None
    low = s[:200].lower()
    if low.startswith(b"<?xml") or low.startswith(b"<html") or low.startswith(b"<!doctype html") or b"<html" in low:
        return "html" if b"html" in low else "xml"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "ole"
    return None


def _process_as(kind, in_path, out_path, ctx):
    if kind == "rtf":
        from .rtf import process_rtf
        return process_rtf(in_path, out_path, ctx)
    if kind in ("docx", "xlsx", "pptx"):
        from .ooxml import process_ooxml
        return process_ooxml(in_path, out_path, ctx)
    if kind == "html":
        from .markup import process_html
        return process_html(in_path, out_path, ctx)
    if kind == "xml":
        from .markup import process_xml
        return process_xml(in_path, out_path, ctx)
    raise ProcessingError("formato non riconosciuto")


# ------------------------------------------------------------------------------------------------ XLS
def process_xls(in_path, out_path, ctx):
    kind = _sniff(in_path)
    if kind and kind != "ole":
        return _process_as(kind, in_path, out_path, ctx)
    import xlrd
    from xlutils.copy import copy as xl_copy
    try:
        rb = xlrd.open_workbook(in_path, formatting_info=True)
    except NotImplementedError:
        rb = xlrd.open_workbook(in_path)
    wb = xl_copy(rb)
    units, cells = [], []
    for si in range(rb.nsheets):
        sheet = rb.sheet_by_index(si)
        for r in range(sheet.nrows):
            row_units = []
            for c in range(sheet.ncols):
                v = sheet.cell_value(r, c)
                if isinstance(v, str) and v.strip():
                    u = Unit(v, sep=" | ")
                    units.append(u)
                    row_units.append(u)
                    cells.append((si, r, c))
            if row_units:
                row_units[-1].sep = "\n"
    res = ctx.analyze(units) if units else []
    for (si, r, c), u, rep in zip(cells, units, res):
        if rep:
            _write_keep_style(wb.get_sheet(si), r, c, apply_replacements(u.text, rep))
    wb.save(out_path)
    return None


def _write_keep_style(ws, row, col, value):
    """xlwt.write() senza stile azzera la formattazione della cella: si ripristina lo stesso XF."""
    prev = None
    try:
        r = ws._Worksheet__rows.get(row)
        prev = r._Row__cells.get(col) if r else None
    except Exception:
        prev = None
    ws.write(row, col, value)
    if prev is not None:
        try:
            ws._Worksheet__rows[row]._Row__cells[col].xf_idx = prev.xf_idx
        except Exception:
            pass


# ------------------------------------------------------------------------------------------------ DOC / PPT
def _find_soffice():
    cands = []
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        cands.extend(glob.glob(os.path.join(base, "LibreOffice*", "program", "soffice.exe")))
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\LibreOffice\UNO\InstallPath") as k:
                    p = winreg.QueryValueEx(k, "")[0]
                    cands.append(os.path.join(p, "soffice.exe"))
            except OSError:
                pass
    except ImportError:
        pass
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def _office_available(progid):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID"):
            return True
    except Exception:
        return False


def _kill_automation(names, since):
    try:
        import psutil
        for p in psutil.process_iter(["name", "cmdline", "create_time"]):
            try:
                if (p.info["name"] or "").upper() in names and (p.info["create_time"] or 0) >= since - 1:
                    cmd = " ".join(p.info["cmdline"] or []).lower()
                    if "/automation" in cmd or "-embedding" in cmd:
                        p.kill()
            except Exception:
                pass
    except Exception:
        pass


def _convert_office(app, src, dst, fmt):
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "office_convert.py")
    t0 = time.time()
    try:
        proc = subprocess.run([sys.executable, script, app, src, dst, str(fmt)], capture_output=True, text=True,
                              timeout=CONVERT_TIMEOUT, creationflags=_NO_WINDOW, cwd=common.BASE_DIR)
    except subprocess.TimeoutExpired:
        _kill_automation({"WINWORD.EXE", "POWERPNT.EXE"}, t0)
        raise ProcessingError(f"conversione con {app} oltre {CONVERT_TIMEOUT}s (documento protetto o finestra di dialogo?)")
    if proc.returncode != 0 or not os.path.isfile(dst):
        _kill_automation({"WINWORD.EXE", "POWERPNT.EXE"}, t0)
        msg = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise ProcessingError(f"conversione con {app} non riuscita: {msg[-1] if msg else 'errore sconosciuto'}")


def _convert_soffice(soffice, src, out_dir, target_ext):
    profile = os.path.join(common.STATE_DIR, "lo_profile")
    os.makedirs(profile, exist_ok=True)
    url = "file:///" + profile.replace("\\", "/")
    cmd = [soffice, "--headless", "--norestore", "--nolockcheck", "--nodefault", f"-env:UserInstallation={url}",
           "--convert-to", target_ext, "--outdir", out_dir, src]
    try:
        subprocess.run(cmd, capture_output=True, timeout=CONVERT_TIMEOUT, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise ProcessingError("conversione con LibreOffice oltre il tempo massimo")
    out = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + "." + target_ext)
    if not os.path.isfile(out):
        raise ProcessingError("conversione con LibreOffice non riuscita")
    return out


def _legacy_roundtrip(in_path, out_path, ctx, *, modern_ext, app, progid, to_modern_fmt, to_legacy_fmt, legacy_ext):
    from .ooxml import process_ooxml
    soffice = None if _office_available(progid) else _find_soffice()
    if not _office_available(progid) and not soffice:
        raise ProcessingError(
            f"I file {legacy_ext} richiedono Microsoft Office o LibreOffice installato. "
            f"In alternativa salva il documento come {modern_ext} e trascinalo di nuovo."
        )
    with ctx.tempdir() as d:
        src = os.path.join(d, "originale" + legacy_ext)
        shutil.copy2(in_path, src)
        modern = os.path.join(d, "convertito" + modern_ext)
        if soffice:
            conv = _convert_soffice(soffice, src, d, modern_ext.lstrip("."))
            shutil.move(conv, modern)
        else:
            _convert_office(app, src, modern, to_modern_fmt)
        processed = os.path.join(d, "elaborato" + modern_ext)
        process_ooxml(modern, processed, ctx)
        back_dir = os.path.join(d, "back")
        os.makedirs(back_dir)
        final = os.path.join(back_dir, "elaborato" + legacy_ext)
        if soffice:
            conv = _convert_soffice(soffice, processed, back_dir, legacy_ext.lstrip("."))
            if conv != final:
                shutil.move(conv, final)
        else:
            _convert_office(app, processed, final, to_legacy_fmt)
        shutil.copy2(final, out_path)
    return None


def process_doc(in_path, out_path, ctx):
    kind = _sniff(in_path)
    if kind and kind != "ole":
        return _process_as(kind, in_path, out_path, ctx)
    return _legacy_roundtrip(in_path, out_path, ctx, modern_ext=".docx", app="word", progid="Word.Application",
                             to_modern_fmt=16, to_legacy_fmt=0, legacy_ext=".doc")


def process_ppt(in_path, out_path, ctx):
    kind = _sniff(in_path)
    if kind and kind != "ole":
        return _process_as(kind, in_path, out_path, ctx)
    return _legacy_roundtrip(in_path, out_path, ctx, modern_ext=".pptx", app="powerpoint",
                             progid="PowerPoint.Application", to_modern_fmt=24, to_legacy_fmt=1, legacy_ext=".ppt")
