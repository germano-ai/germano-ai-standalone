"""Crea version.json per https://download.germano.ai/ dagli installer in germano.ai-0.60/releases/: versione, note e,
per ogni piattaforma, nome del file e dimensione esatta (l'updater controlla che il download sia completo; nessuna
impronta SHA, come richiesto). Le chiavi «windows», «macos», «linux» sono quelle lette dall'updater della suite; le
voci «-client» descrivono i client leggeri.
Il file non viene pubblicato da qui: si scrive dove indicato e si carica a mano accanto agli installer.

Uso: python crea_version_json.py <file di uscita> ["note della versione"]
"""
import json
import os
import sys

sys.dont_write_bytecode = True
BUILD = os.path.dirname(os.path.abspath(__file__))
RELEASE = os.path.abspath(os.path.join(BUILD, "..", "..", "..", ".."))
VERSION = open(os.path.join(BUILD, "..", "VERSION"), encoding="utf-8-sig").read().strip()
FILES = {"windows": "windows/germano-{v}.exe", "macos": "macos/germano-{v}.pkg", "linux": "linux/germano-{v}.deb",
         "windows-client": "windows/germano-client-{v}.exe", "macos-client": "macos/germano-client-{v}.pkg",
         "linux-client": "linux/germano-client-{v}.deb"}


def main():
    out = sys.argv[1]
    notes = sys.argv[2] if len(sys.argv) > 2 else f"Germano AI {VERSION}"
    files = {}
    for key, rel in FILES.items():
        path = os.path.join(RELEASE, "releases", rel.format(v=VERSION))
        if not os.path.isfile(path):
            raise SystemExit(f"ERRORE: manca {path}")
        files[key] = {"file": os.path.basename(path), "size": os.path.getsize(path)}
    data = {"version": VERSION, "notes": notes, "files": files}
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
