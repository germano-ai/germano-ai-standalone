"""Crea version.json per https://download.germano.ai/ dagli installer in germano.ai-0.90/releases/.

Per ogni piattaforma: nome del file, dimensione esatta e impronta SHA-256, calcolate DIRETTAMENTE dal file su disco
in una sola lettura. Le chiavi «windows», «macos», «linux» sono quelle lette dall'updater della suite; le voci
«-client» descrivono i client leggeri. I campi «file» e «size» sono quelli letti anche dalle versioni 0.60 e 0.70;
«sha256» e' verificata dalla 0.80 in poi.

Perche' e' fatto cosi' (difetto della 0.70): i pacchetti erano stati ricostruiti DOPO aver scritto version.json, che
quindi dichiarava dimensioni di una costruzione precedente (es. 1.964 byte in piu' per germano-0.70.exe): l'updater
scaricava l'installer, vedeva una dimensione diversa da quella dichiarata e lo scartava, a ogni controllo. Ora:
- dimensione e impronta vengono dalla stessa lettura del file (mai da numeri calcolati altrove o ricopiati a mano);
- durante la lettura il file non deve cambiare (dimensione e data controllate prima e dopo) e deve essere un
  pacchetto completo (struttura dell'installer Windows, archivio xar, archivio ar);
- version.json si scrive in un file temporaneo, si rilegge, si riconfronta con i file su disco e solo allora prende
  il posto del precedente (sostituzione atomica): non esiste mai un version.json scritto a meta' o non verificato;
- i costruttori dei pacchetti cancellano il version.json esistente quando ricostruiscono un pacchetto che vi e'
  elencato (scarta_se_superato): un indice superato non puo' piu' restare accanto ai pacchetti nuovi.

Il file non viene pubblicato da qui: si carica a mano accanto agli installer, PER ULTIMO.

Uso:
  python crea_version_json.py [<file di uscita>] ["note della versione"]     crea (predefinito: releases/version.json)
  python crea_version_json.py --verifica [<version.json>]                    ricalcola tutto e confronta, senza scrivere
  python crea_version_json.py --online [<version.json>] [<indirizzo base>]   confronta anche con i file pubblicati
"""
import hashlib
import json
import os
import struct
import sys
import time

sys.dont_write_bytecode = True
BUILD = os.path.dirname(os.path.abspath(__file__))
RELEASE = os.path.abspath(os.path.join(BUILD, "..", "..", "..", ".."))
RELEASES = os.path.join(RELEASE, "releases")
DEFAULT_OUT = os.path.join(RELEASES, "version.json")
DOWNLOAD_BASE = "https://download.germano.ai/"
FILES = {"windows": "windows/germano-{v}.exe", "macos": "macos/germano-{v}.pkg", "linux": "linux/germano-{v}.deb",
         "windows-client": "windows/germano-client-{v}.exe", "macos-client": "macos/germano-client-{v}.pkg",
         "linux-client": "linux/germano-client-{v}.deb"}
NOTES = ("Germano AI v{v} - Motore parallelo (Privacy Filter + Italian NER) con corsia preferenziale per le richieste "
         "interattive, Sistema 2 senza domande superflue, Vault su SQLite WAL, Proxy che protegge anche gli argomenti "
         "degli strumenti, trascrizione audio a lotti, Client in parallelo con verifica del server")
SFX_MAGIC = b"GERMANO.SFX.0001"
SFX_TRAILER = struct.Struct("<16sQQQQ")
WINDOWS_EXE_MAX = 4 * 1024 ** 3 - 1          # Windows non avvia eseguibili da 4 GB in su


def version():
    with open(os.path.join(BUILD, "..", "VERSION"), encoding="utf-8-sig") as f:
        return f.read().strip()


def measure(path):
    """(dimensione, sha256) in UNA lettura, con il controllo che il file non cambi mentre viene letto."""
    before = os.stat(path)
    h, n = hashlib.sha256(), 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
            n += len(chunk)
    after = os.stat(path)
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or n != after.st_size:
        raise SystemExit(f"ERRORE: {path} e' cambiato durante la lettura (costruzione in corso?): riprovare a fine "
                         "costruzione.")
    return n, h.hexdigest(), after.st_mtime_ns


def check_package(path):
    """Il pacchetto deve essere completo: installer Windows in un solo file, pacchetto macOS (xar) o Debian (ar)."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(8)
        if path.endswith(".exe"):
            if head[:2] != b"MZ" or size < SFX_TRAILER.size + 1024:
                return "non e' un eseguibile Windows"
            if size > WINDOWS_EXE_MAX:
                return f"supera i 4 GB ({size:,} byte): Windows non lo avvierebbe"
            f.seek(size - SFX_TRAILER.size)
            magic, ko, kl, po, pl = SFX_TRAILER.unpack(f.read(SFX_TRAILER.size))
            if not (magic == SFX_MAGIC and 0 < ko and ko + kl <= po and po + pl == size - SFX_TRAILER.size):
                return "coda dell'installer non valida (file incompleto)"
        elif path.endswith(".pkg"):
            if head[:4] != b"xar!":
                return "non e' un pacchetto macOS (xar)"
        elif path.endswith(".deb"):
            if head != b"!<arch>\n":
                return "non e' un pacchetto Debian (ar)"
    return None


def collect(v):
    """{chiave: {"file", "size", "sha256"}} e le date dei file misurati."""
    files, stamps = {}, {}
    for key, rel in FILES.items():
        path = os.path.join(RELEASES, rel.format(v=v).replace("/", os.sep))
        if not os.path.isfile(path):
            raise SystemExit(f"ERRORE: manca {path}")
        problem = check_package(path)
        if problem:
            raise SystemExit(f"ERRORE: {path}: {problem}")
        size, digest, mtime = measure(path)
        files[key] = {"file": os.path.basename(path), "size": size, "sha256": digest}
        stamps[key] = (path, size, mtime)
        print(f"  {key:15} {os.path.basename(path):28} {size:>14,} byte  sha256 {digest}", flush=True)
    return files, stamps


def write_atomic(out, data, stamps):
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    try:
        with open(tmp, encoding="utf-8") as f:
            back = json.load(f)
        for key, (path, size, mtime) in stamps.items():
            st = os.stat(path)
            if (st.st_size, st.st_mtime_ns) != (size, mtime) or back["files"][key]["size"] != st.st_size:
                raise SystemExit(f"ERRORE: {path} e' cambiato mentre si creava version.json: nulla e' stato scritto.")
        os.replace(tmp, out)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def create(out, notes):
    v = version()
    print(f"== version.json per Germano AI {v} (dai file in {RELEASES})", flush=True)
    files, stamps = collect(v)
    data = {"version": v, "notes": notes or NOTES.format(v=v),
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": files}
    write_atomic(out, data, stamps)
    print(f"  scritto {out} ({os.path.getsize(out)} byte), verificato sui file")
    return data


def verify(index_path):
    """Ricalcola dimensione e impronta di ogni pacchetto e le confronta con un version.json esistente."""
    with open(index_path, encoding="utf-8-sig") as f:
        data = json.load(f)
    v = str(data.get("version") or "")
    print(f"== verifica di {index_path} (versione {v})", flush=True)
    bad = 0
    if v != version():
        print(f"  DIVERSO: version.json dichiara {v}, i sorgenti sono alla {version()}")
        bad += 1
    entries = data.get("files") if isinstance(data.get("files"), dict) else {}
    for key, rel in FILES.items():
        entry = entries.get(key) or {}
        path = os.path.join(RELEASES, rel.format(v=v).replace("/", os.sep))
        if not os.path.isfile(path):
            print(f"  MANCA   {key}: {path}")
            bad += 1
            continue
        size, digest, _ = measure(path)
        problems = []
        if entry.get("file") != os.path.basename(path):
            problems.append(f"nome {entry.get('file')!r}")
        if entry.get("size") != size:
            problems.append(f"dimensione dichiarata {entry.get('size')} reale {size} (differenza "
                            f"{size - int(entry.get('size') or 0):+d})")
        if entry.get("sha256") and str(entry["sha256"]).lower() != digest:
            problems.append("sha256 diversa")
        if not entry.get("sha256"):
            problems.append("sha256 assente")
        problem = check_package(path)
        if problem:
            problems.append(problem)
        bad += bool(problems)
        print(f"  {'DIVERSO' if problems else 'OK     '} {key:15} {os.path.basename(path):28} {size:>14,} byte"
              + (": " + "; ".join(problems) if problems else ""), flush=True)
    print("  version.json coerente con i pacchetti su disco" if not bad else f"  {bad} PROBLEMI: rigenerare version.json")
    return bad == 0, data


def online(index_path, base):
    """Confronta version.json e le dimensioni dei pacchetti locali con quelli pubblicati (solo richieste HEAD/GET di
    lettura). Da eseguire dopo il caricamento: l'indice pubblicato deve essere identico a quello locale."""
    import urllib.error
    import urllib.request
    ok, data = verify(index_path)
    headers = {"User-Agent": "GermanoAI-Updater/" + version()}
    base = base if base.endswith("/") else base + "/"
    print(f"== confronto con {base}", flush=True)
    try:
        with urllib.request.urlopen(urllib.request.Request(base + "version.json", headers=headers), timeout=30) as r:
            remote = json.loads(r.read().decode("utf-8-sig"))
    except Exception as e:
        print(f"  version.json pubblicato non leggibile: {e}")
        return False
    same = remote == data
    print("  version.json pubblicato " + ("identico a quello locale" if same else "DIVERSO da quello locale"))
    ok = ok and same
    for key, entry in (data.get("files") or {}).items():
        req = urllib.request.Request(base + entry["file"], headers=headers, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                length = int(r.headers.get("Content-Length") or 0)
        except Exception as e:
            print(f"  NON LEGGIBILE {key}: {entry['file']}: {e}")
            ok = False
            continue
        good = length == entry["size"]
        ok = ok and good
        print(f"  {'OK     ' if good else 'DIVERSO'} {key:15} {entry['file']:28} pubblicato {length:>14,} byte"
              + ("" if good else f" (locale {entry['size']:,}, differenza {length - entry['size']:+d})"))
    print("  pubblicazione coerente" if ok else "  PUBBLICAZIONE NON COERENTE: gli aggiornamenti verrebbero rifiutati")
    return ok


def scarta_se_superato(package_path):
    """Chiamata dai costruttori dopo aver (ri)creato un pacchetto: se releases/version.json lo elenca con una
    dimensione diversa, quell'indice descrive una costruzione precedente e viene cancellato (va rigenerato a fine
    costruzione con questo script). Restituisce True se l'indice e' stato cancellato."""
    try:
        with open(DEFAULT_OUT, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    name, size = os.path.basename(package_path), os.path.getsize(package_path)
    for entry in (data.get("files") or {}).values():
        if isinstance(entry, dict) and entry.get("file") == name and entry.get("size") != size:
            os.remove(DEFAULT_OUT)
            print(f"  ATTENZIONE: releases/version.json descriveva un {name} diverso ed e' stato cancellato: "
                  "rigenerarlo con crea_version_json.py quando tutti i pacchetti sono pronti.", flush=True)
            return True
    return False


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = sys.argv[1:]
    if args and args[0] == "--verifica":
        sys.exit(0 if verify(args[1] if len(args) > 1 else DEFAULT_OUT)[0] else 1)
    if args and args[0] == "--online":
        rest = args[1:]
        index = rest[0] if rest and not rest[0].lower().startswith("http") else DEFAULT_OUT
        base = next((a for a in rest if a.lower().startswith("http")), DOWNLOAD_BASE)
        sys.exit(0 if online(index, base) else 1)
    out = args[0] if args else DEFAULT_OUT
    create(out, args[1] if len(args) > 1 else None)
    if not verify(out)[0]:
        raise SystemExit("ERRORE: il version.json appena scritto non supera la verifica")


if __name__ == "__main__":
    main()
