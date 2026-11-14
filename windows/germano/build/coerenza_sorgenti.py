# -*- coding: utf-8 -*-
"""Cancello di coerenza dei sorgenti (turno 26).

I sorgenti Windows (sorgenti/windows/<edizione>) sono il riferimento. Gli alberi Linux e macOS devono avere gli STESSI
file comuni, byte per byte; differiscono solo i file propri di ciascun sistema (script di avvio, icone, Info.plist,
finestra dell'applicazione, requirements.txt, costruttori e installer di Windows). Nella 0.80 i pacchetti Linux e
macOS sono stati costruiti da alberi rimasti a meta' fra 0.70 e 0.80 (turno 25): costruisci_deb.py e
costruisci_pkg.py ora si fermano se l'albero non e' allineato, e file inutili/sincronizza_sorgenti_linux_mac.py usa
lo stesso elenco per copiare.

Uso da riga di comando: python -B coerenza_sorgenti.py [cartella della release]  (controlla tutti gli alberi)."""
import hashlib
import os
import sys

EDITIONS = ("germano", "germano-client")
SYSTEMS = ("windows", "linux", "macos")
# File propri di un sistema (non confrontati): nomi esatti e cartelle (prefissi)
PLATFORM_FILES = {
    "windows": {"germano_install.py", "requirements.txt"},
    "linux": {"Germano.desktop", "README_Linux.md", "germano.sh", "germano_window.py", "requirements.txt"},
    "macos": {"LEGGIMI_macOS.md", "germano_window.py", "requirements.txt"},
}
PLATFORM_DIRS = {"windows": ("build/",), "linux": ("icons/",), "macos": ("Germano.app/",)}
IGNORED_DIRS = {"__pycache__", ".git", "cache"}


def _files(base):
    out = {}
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                continue
            p = os.path.join(root, f)
            out[os.path.relpath(p, base).replace("\\", "/")] = p
    return out


def platform_specific(rel, system):
    return rel in PLATFORM_FILES[system] or rel.startswith(PLATFORM_DIRS[system])


def common_files(release, edition):
    """{percorso relativo: percorso assoluto} dei file comuni, presi dal riferimento Windows."""
    ref = _files(os.path.join(release, "sorgenti", "windows", edition))
    return {rel: p for rel, p in ref.items() if not platform_specific(rel, "windows")}


def _digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def compare(release, edition, system):
    """(mancanti, diversi, in_piu') dell'albero `system` rispetto al riferimento Windows (file comuni)."""
    ref = common_files(release, edition)
    tgt = _files(os.path.join(release, "sorgenti", system, edition))
    missing = sorted(rel for rel in ref if rel not in tgt)
    different = sorted(rel for rel in ref if rel in tgt and _digest(ref[rel]) != _digest(tgt[rel]))
    extra = sorted(rel for rel in tgt if rel not in ref and not platform_specific(rel, system))
    return missing, different, extra


def verify(release, edition, system):
    """Da chiamare prima di costruire un pacchetto: solleva SystemExit con l'elenco se l'albero non e' allineato."""
    missing, different, extra = compare(release, edition, system)
    if missing or different or extra:
        lines = [f"Sorgenti {system}/{edition} NON allineati a windows/{edition} (riferimento):"]
        for title, items in (("mancanti", missing), ("diversi", different), ("in piu'", extra)):
            if items:
                lines.append(f"  {title} ({len(items)}): " + ", ".join(items[:30]) + (" ..." if len(items) > 30 else ""))
        lines.append("Esegui file inutili/sincronizza_sorgenti_linux_mac.py e ripeti la costruzione.")
        raise SystemExit("\n".join(lines))
    return len(common_files(release, edition))


def main():
    release = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else
                              os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
    ok = True
    for edition in EDITIONS:
        for system in ("linux", "macos"):
            missing, different, extra = compare(release, edition, system)
            n = len(common_files(release, edition))
            status = "allineato" if not (missing or different or extra) else "NON allineato"
            print(f"{system}/{edition}: {status} ({n} file comuni; mancanti {len(missing)}, diversi {len(different)}, "
                  f"in piu' {len(extra)})")
            for title, items in (("mancanti", missing), ("diversi", different), ("in piu'", extra)):
                if items:
                    print(f"   {title}: {', '.join(items)}")
            ok = ok and not (missing or different or extra)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
