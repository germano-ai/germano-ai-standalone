"""Installazione di un aggiornamento di Germano AI (eseguita a programma chiuso).

Viene avviata da germano/updater.py con un interprete Python minimo copiato in update/installer, perché la
cartella runtime viene sostituita. Usa solo la libreria standard.

Passi: attende la chiusura dei processi di Germano, sposta ogni componente della versione installata in
update/old e mette al suo posto quello nuovo (spostamenti sullo stesso disco: istantanei). Cartelle di lavoro,
Vault, config.json e update/ non vengono toccati. Se un passo non riesce, ripristina la versione precedente.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback

# Elementi della cartella del programma che appartengono all'utente e non vengono mai sostituiti
KEEP = {"input", "output", "processed", "failed", "extracted", "state", "cache", "update", "config.json"}


def log(app, msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(msg, flush=True)
    try:
        with open(os.path.join(app, "update", "update.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def write_result(app, data):
    path = os.path.join(app, "update", "install_result.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def wait_and_stop(pids, timeout):
    """Attende la chiusura dei processi di Germano indicati; alla scadenza termina quelli ancora attivi.
    Gli handle vengono aperti subito: si agisce sempre sul processo originale, mai su un PID riassegnato."""
    import _winapi
    SYNCHRONIZE, PROCESS_TERMINATE = 0x00100000, 0x0001
    handles = []
    for pid in pids:
        try:
            handles.append((pid, _winapi.OpenProcess(SYNCHRONIZE | PROCESS_TERMINATE, False, pid)))
        except OSError:
            pass  # processo già terminato
    deadline = time.time() + timeout
    killed = []
    for pid, handle in handles:
        try:
            if _winapi.WaitForSingleObject(handle, max(0, int((deadline - time.time()) * 1000))) != 0:
                _winapi.TerminateProcess(handle, 1)
                _winapi.WaitForSingleObject(handle, 15000)
                killed.append(pid)
        except OSError:
            pass
        finally:
            _winapi.CloseHandle(handle)
    return killed


def move(src, dst, attempts=40):
    """Spostamento con nuovi tentativi (antivirus o indicizzazione possono bloccare un file per un attimo)."""
    for i in range(attempts):
        try:
            os.rename(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.25 * min(i + 1, 8))


def install(app, source, old_dir, dry_run=False):
    names = [n for n in sorted(os.listdir(source)) if n.lower() not in KEEP and not n.lower().startswith("daemon.log")]
    if dry_run:
        for n in names:
            log(app, f"  (prova) sostituirei: {n}")
        return names
    os.makedirs(old_dir, exist_ok=True)
    done = []  # (nome, c'era una versione precedente)
    try:
        for n in names:
            dst, bak, src = os.path.join(app, n), os.path.join(old_dir, n), os.path.join(source, n)
            had_old = os.path.lexists(dst)
            if had_old:
                if os.path.lexists(bak):
                    raise RuntimeError(f"update/old contiene già {n}: installazione precedente non conclusa.")
                move(dst, bak)
            try:
                move(src, dst)
            except Exception:
                if had_old:
                    move(bak, dst)
                raise
            done.append((n, had_old))
            log(app, f"  sostituito: {n}")
    except Exception:
        log(app, "ERRORE durante la sostituzione: ripristino della versione precedente...")
        for n, had_old in reversed(done):
            try:
                move(os.path.join(app, n), os.path.join(source, n))
                if had_old:
                    move(os.path.join(old_dir, n), os.path.join(app, n))
            except Exception as e:
                log(app, f"  ATTENZIONE: impossibile ripristinare {n}: {e}")
        raise
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--from-version", default="")
    ap.add_argument("--wait", default="")
    ap.add_argument("--restart", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    app = os.path.abspath(a.app)
    source = os.path.abspath(a.source)
    old_dir = os.path.join(app, "update", "old")
    try:
        os.system("title Germano AI - aggiornamento")
    except Exception:
        pass
    log(app, f"Aggiornamento di Germano AI dalla versione {a.from_version} alla {a.version}.")
    log(app, "Non chiudere questa finestra: al termine Germano si riavvia da solo.")

    pids = [int(p) for p in a.wait.split(",") if p.strip().isdigit()]
    for pid in wait_and_stop(pids, 90):
        log(app, f"Il processo {pid} non si è chiuso entro 90 secondi ed è stato terminato.")
    time.sleep(1.0)

    status, error = "ok", None
    try:
        if not os.path.isfile(os.path.join(source, "START.bat")):
            raise RuntimeError("cartella dell'aggiornamento non valida")
        install(app, source, old_dir, dry_run=a.dry_run)
        if not a.dry_run:
            for f in ("ready.json",):
                try:
                    os.remove(os.path.join(app, "update", f))
                except OSError:
                    pass
        log(app, "Aggiornamento completato." if not a.dry_run else "Prova completata: nessun file modificato.")
    except Exception as e:
        status, error = "error", f"{type(e).__name__}: {e}"
        log(app, f"Aggiornamento NON riuscito: {error}")
        log(app, traceback.format_exc())
        log(app, "La versione precedente è stata mantenuta.")
    if not a.dry_run:
        write_result(app, {"status": status, "from": a.from_version, "to": a.version if status == "ok" else a.from_version,
                           "target": a.version, "error": error, "time": time.time()})
    if a.restart and not a.dry_run:
        log(app, "Riavvio di Germano AI...")
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(["cmd.exe", "/c", os.path.join(app, "START.bat")], cwd=app, creationflags=flags, close_fds=True)
        time.sleep(2)
    elif status != "ok":
        input("Premi Invio per chiudere...")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
