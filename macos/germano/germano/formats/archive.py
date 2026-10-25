"""Archivi ZIP: ogni file interno viene elaborato col proprio formato (anche ZIP annidati).
Principio "fail-safe": in anonimizzazione i file non elaborabili NON vengono copiati in chiaro."""
import os
import zipfile

from .. import common
from . import is_supported, process_bytes, ProcessingError
from .ooxml import clone_zipinfo

MAX_ENTRIES = 20000
MAX_TOTAL_BYTES = 4 * 1024 ** 3
MAX_RATIO = 200


def process_zip(in_path, out_path, ctx):
    if not zipfile.is_zipfile(in_path):
        raise ProcessingError("Archivio ZIP non valido.")
    removed_list = []
    with zipfile.ZipFile(in_path, "r") as zin:
        infos = zin.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ProcessingError(f"Archivio con troppi file ({len(infos)}).")
        total = sum(i.file_size for i in infos)
        packed = max(1, sum(i.compress_size for i in infos))
        if total > MAX_TOTAL_BYTES or (total > 50 * 1024 ** 2 and total / packed > MAX_RATIO):
            raise ProcessingError("Archivio sospetto (dimensione decompressa eccessiva): elaborazione bloccata.")
        files = [i for i in infos if not i.is_dir()]
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zout:
            for k, info in enumerate(infos):
                if info.is_dir():
                    zout.writestr(clone_zipinfo(info), b"")
                    continue
                ctx.check()
                name = info.filename
                base = os.path.basename(name.rstrip("/")) or "file"
                ctx.report(f"archivio: file {k + 1}/{len(infos)} ({base})")
                if info.flag_bits & 0x1:
                    # File cifrato: non leggibile senza password, quindi ne' analizzabile ne' copiabile.
                    removed_list.append(f"{name} (protetto da password)")
                    continue
                if is_supported(base):
                    try:
                        data = zin.read(info)
                        new_data, out_name = process_bytes(data, base, ctx.child())
                        zi = clone_zipinfo(info)
                        if out_name != base:
                            zi.filename = name[: len(name) - len(base)] + out_name
                        zout.writestr(zi, new_data)
                        continue
                    except Exception as e:
                        reason = str(e)
                else:
                    reason = "formato non supportato"
                if ctx.anonymize:
                    removed_list.append(f"{name} ({reason})")
                else:
                    zout.writestr(clone_zipinfo(info), zin.read(info))
    if removed_list:
        shown = "; ".join(removed_list[:10]) + (" ..." if len(removed_list) > 10 else "")
        what = "non anonimizzabili" if ctx.anonymize else "non leggibili"
        ctx.note(f"Dall'archivio sono stati esclusi {len(removed_list)} file {what}: {shown}")
        common.log(f"Archivio: {len(removed_list)} file esclusi su {len(files)}.")
    return None
