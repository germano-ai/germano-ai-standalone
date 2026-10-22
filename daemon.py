"""Germano AI - demone IA.

Carica i modelli locali, sorveglia la cartella input/ ed espone al server web un'API interna
(127.0.0.1, porta dinamica, protetta da token) usata dal Proxy API e dalle API REST.
Viene avviato dal server (server.py) e si chiude da solo se il server termina.
"""
import os
import sys
import threading
import time
import traceback
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from germano import common  # noqa: E402

common.setup_offline_env()
common.force_utf8_stdio()

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

from germano import formats  # noqa: E402
from germano.engine import CancelledError, CancelToken, Engine  # noqa: E402
from germano.vault import Vault, contains_tags, restore_text  # noqa: E402

VERSION = common.get_version()
log = common.log


def _pid_alive(pid, create_time=None):
    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        if create_time is not None:
            return abs(psutil.Process(pid).create_time() - create_time) < 1.0
        return True
    except Exception:
        return False


def _is_locked(path):
    """True se un altro processo sta scrivendo il file (copia in corso, salvataggio, ecc.)."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING = 0x80000000, 0x1, 3
        # Apertura in lettura negando la condivisione in scrittura: fallisce se qualcuno sta scrivendo il file.
        h = k32.CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, None, OPEN_EXISTING, 0, None)
        if h is None or h == ctypes.c_void_p(-1).value:
            return True
        k32.CloseHandle(h)
        return False
    except Exception:
        try:
            with open(path, "rb"):
                return False
        except OSError:
            return True


class Daemon:
    def __init__(self):
        common.ensure_dirs()
        self.settings = common.load_config()
        self._cfg_sig = None
        self.vault = Vault()
        self.engine = Engine()
        self.token = os.environ.get("GERMANO_TOKEN") or uuid.uuid4().hex
        self.parent_pid = int(os.environ.get("GERMANO_PARENT_PID") or 0)
        self.parent_ctime = None
        self.stop_event = threading.Event()
        self.port = None
        self.file_sig = {}
        self.stuck = {}
        self.status = {"state": "loading", "current": None, "detail": "", "queue": 0, "done": 0,
                       "failed": 0, "restored": 0}
        self._status_ts = 0.0
        self._last_cleanup = 0.0

    # ------------------------------------------------------------------ stato
    def should_stop(self):
        return self.stop_event.is_set() or os.path.exists(common.STOP_FLAG)

    def set_status(self, force=False, **kw):
        self.status.update(kw)
        now = time.time()
        if force or now - self._status_ts > 0.5:
            self._status_ts = now
            st = dict(self.status)
            st["updated"] = now
            try:
                common.atomic_write_json(common.STATUS_FILE, st)
            except Exception:
                pass

    def write_state(self, **extra):
        st = {"pid": os.getpid(), "port": self.port, "token": self.token, "version": VERSION,
              "started": time.time(), "engine": self.engine.info}
        st.update(extra)
        common.atomic_write_json(common.DAEMON_STATE_FILE, st)

    def reload_settings(self):
        try:
            st = os.stat(common.CONFIG_FILE)
            sig = (st.st_mtime_ns, st.st_size)
        except OSError:
            sig = None
        if sig != self._cfg_sig:
            self._cfg_sig = sig
            self.settings = common.load_config()

    # ------------------------------------------------------------------ avvio
    def check_single_instance(self):
        st = common.read_json(common.DAEMON_STATE_FILE, {}) or {}
        pid = st.get("pid")
        if pid and pid != os.getpid():
            try:
                import psutil
                p = psutil.Process(int(pid))
                if p.is_running() and any("daemon.py" in c for c in (p.cmdline() or [])):
                    log(f"Un altro demone Germano e' gia' in esecuzione (PID {pid}): chiusura di questa istanza.")
                    return False
            except Exception:
                pass
        return True

    def start_watchdog(self):
        if not self.parent_pid:
            return
        try:
            import psutil
            self.parent_ctime = psutil.Process(self.parent_pid).create_time()
        except Exception:
            self.parent_ctime = None

        def _watch():
            while not self.stop_event.is_set():
                if not _pid_alive(self.parent_pid, self.parent_ctime):
                    log("Il server Germano si e' chiuso: arresto automatico del demone.")
                    self.stop_event.set()
                    return
                time.sleep(2.0)
        threading.Thread(target=_watch, daemon=True, name="parent-watchdog").start()

    def cleanup_leftovers(self):
        for flag in (common.STOP_FLAG, common.READY_FLAG, common.LAST_ERROR_FILE):
            common.remove_quietly(flag)
        try:
            import shutil
            shutil.rmtree(common.WORK_TMP_DIR, ignore_errors=True)
            os.makedirs(common.WORK_TMP_DIR, exist_ok=True)
        except Exception:
            pass
        for root, _dirs, files in os.walk(common.OUTPUT_DIR):
            for f in files:
                if f.startswith(common.TMP_PREFIX):
                    common.remove_quietly(os.path.join(root, f))

    def fatal(self, message):
        log(f"ERRORE CRITICO: {message}")
        try:
            common.atomic_write_json(common.LAST_ERROR_FILE, {"message": message, "time": time.time()})
        except Exception:
            pass

    # ------------------------------------------------------------------ cartella input/
    def scan_input(self):
        now = time.time()
        found = []
        seen = set()
        for root, dirs, files in os.walk(common.INPUT_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                p = os.path.join(root, f)
                if common.is_ignored_file(p):
                    continue
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                seen.add(p)
                sig = (st.st_size, st.st_mtime_ns)
                if self.stuck.get(p) == sig:
                    continue
                prev = self.file_sig.get(p)
                self.file_sig[p] = sig
                if prev != sig:
                    continue  # nuovo o ancora in modifica: si attende il giro successivo
                if now - st.st_mtime < 1.5:
                    continue
                if _is_locked(p):
                    continue
                found.append((st.st_mtime, p))
        for p in list(self.file_sig):
            if p not in seen:
                self.file_sig.pop(p, None)
                self.stuck.pop(p, None)
        found.sort()
        return [p for _, p in found]

    def cleanup_empty_dirs(self):
        now = time.time()
        if now - self._last_cleanup < 30:
            return
        self._last_cleanup = now
        for root, dirs, files in os.walk(common.INPUT_DIR, topdown=False):
            if os.path.abspath(root) == os.path.abspath(common.INPUT_DIR):
                continue
            try:
                if not os.listdir(root) and now - os.path.getmtime(root) > 60:
                    os.rmdir(root)
            except OSError:
                pass

    def _move_away(self, src, dest_root, rel):
        """Sposta l'originale senza mai sovrascrivere un file diverso gia' presente."""
        import shutil
        dest = os.path.join(dest_root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            if common.same_file_content(src, dest):
                os.remove(dest)
            else:
                dest = common.unique_path(dest)
        last = None
        for i in range(10):
            try:
                shutil.move(src, dest)
                return dest
            except PermissionError as e:
                last = e
                time.sleep(0.3 * (i + 1))
        raise last or PermissionError("file bloccato")

    def _record_failure(self, rel, reason):
        data = common.read_json(common.FAILED_REASONS_FILE, {}) or {}
        data[rel.replace("\\", "/")] = {"reason": reason, "time": time.time()}
        if len(data) > 2000:
            for k in sorted(data, key=lambda k: data[k].get("time", 0))[: len(data) - 2000]:
                data.pop(k, None)
        common.atomic_write_json(common.FAILED_REASONS_FILE, data)

    def _record_output(self, final, rel, mode, ctx, elapsed):
        """Indice documento pronto -> esito: la Dashboard mostra quanti dati sono stati oscurati."""
        try:
            data = common.read_json(common.OUTPUTS_FILE, {}) or {}
            key = os.path.relpath(final, common.OUTPUT_DIR).replace("\\", "/")
            data[key] = {"source": rel.replace("\\", "/"), "mode": mode, "entities": len(ctx.audit),
                         "notes": len(ctx.notes), "seconds": round(elapsed, 1), "time": time.time()}
            if len(data) > 5000:
                for k in sorted(data, key=lambda k: data[k].get("time", 0))[: len(data) - 5000]:
                    data.pop(k, None)
            common.atomic_write_json(common.OUTPUTS_FILE, data)
        except Exception as e:
            log(f"Impossibile aggiornare l'elenco dei documenti pronti: {e}")

    def _output_rel(self, rel, mode, ctx):
        parts = rel.replace("\\", "/").split("/")
        if mode == "anonymize" and self.settings.get("anonymize_filenames"):
            # le cartelle non hanno estensione: il "." nei nomi di cartella non va trattato come estensione
            parts = [formats.transform_filename(p, ctx) if i == len(parts) - 1
                     else formats.transform_filename(p + ".d", ctx)[:-2] for i, p in enumerate(parts)]
        if mode == "restore":
            parts = [common.safe_filename(restore_text(p, ctx.tag_map)) for p in parts]
            base = parts[-1]
            parts[-1] = base if base.startswith("ripristinato_") else "ripristinato_" + base
        return os.path.join(*parts)

    def process_one(self, path):
        rel = os.path.relpath(path, common.INPUT_DIR)
        settings = dict(self.settings)
        try:
            sig = (os.path.getsize(path), os.stat(path).st_mtime_ns)
        except OSError:
            return
        self.vault.refresh()
        tag_map = self.vault.tag_map()
        mode = "anonymize"
        if settings.get("enable_deanonymize", True) and tag_map:
            try:
                if contains_tags(formats.sample_text(path), tag_map):
                    mode = "restore"
            except Exception:
                pass
        timeout = max(5, int(settings.get("file_timeout_minutes", 60))) * 60
        cancel = CancelToken(deadline=time.time() + timeout, stop_check=self.should_stop)
        ctx = formats.Ctx(mode, settings, engine=self.engine, vault=self.vault, tag_map=tag_map, cancel=cancel,
                          progress=lambda d: self.set_status(detail=d))
        self.set_status(state="working", current=rel.replace("\\", "/"), detail="avvio", force=True)
        if mode == "restore":
            log(f"Rilevato file di ritorno dall'AI ({rel}): ripristino automatico dei dati veri...")
        else:
            log(f"Elaborazione in corso: {rel}...")
        t0 = time.time()
        out_rel = self._output_rel(rel, mode, ctx)
        out_dir = os.path.dirname(os.path.join(common.OUTPUT_DIR, out_rel))
        os.makedirs(out_dir, exist_ok=True)
        tmp_prefix = f"{common.TMP_PREFIX}{uuid.uuid4().hex[:6]}_"
        tmp_out = os.path.join(out_dir, tmp_prefix + os.path.basename(out_rel))
        result = None
        try:
            if len(os.path.abspath(tmp_out)) >= 259:
                raise formats.ProcessingError(
                    "Percorso troppo lungo per Windows (oltre 260 caratteri): sposta Germano in una cartella piu' "
                    "corta (es. C:\\GermanoAI) oppure accorcia i nomi di cartelle e file.")
            result = formats.process_file(path, tmp_out, ctx)
            final = os.path.join(os.path.dirname(result), os.path.basename(result)[len(tmp_prefix):])
            try:
                os.replace(result, final)
            except PermissionError:
                final = common.unique_path(final)
                os.replace(result, final)
            self.vault.flush()
            if mode == "anonymize":
                self._write_audit(rel, ctx)
            try:
                self._move_away(path, common.PROCESSED_DIR, rel)
            except Exception as e:
                self.stuck[path] = sig
                log(f"ATTENZIONE: impossibile spostare {rel} in processed ({e}). Il file resta in input "
                    f"e non verra' rielaborato finche' non viene modificato.")
            elapsed = time.time() - t0
            self._record_output(final, rel, mode, ctx, elapsed)
            if mode == "restore":
                self.status["restored"] += 1
                log(f"Completato ripristino dati veri: {os.path.relpath(final, common.OUTPUT_DIR)} ({elapsed:.1f}s).")
            else:
                self.status["done"] += 1
                log(f"Completato: {rel} ({len(ctx.audit)} elementi censurati, {elapsed:.1f}s).")
        except CancelledError as e:
            self._discard(result, tmp_out, tmp_prefix)
            if e.reason == "stop":
                log(f"Elaborazione di {rel} interrotta: il file resta in input e verra' ripreso al prossimo avvio.")
            else:
                self._fail(path, rel, f"Tempo massimo superato ({timeout // 60} minuti). "
                                      f"Aumentare 'file_timeout_minutes' in config.json per documenti molto grandi.")
        except (formats.UnsupportedFormat, formats.ProcessingError, ValueError) as e:
            # errori "previsti" (formato, password, file danneggiato): messaggio chiaro senza dettagli tecnici
            self._discard(result, tmp_out, tmp_prefix)
            if isinstance(e, ValueError):
                log(f"Dettaglio errore:\n{traceback.format_exc(limit=4)}")
            self._fail(path, rel, str(e) or type(e).__name__)
        except Exception as e:
            self._discard(result, tmp_out, tmp_prefix)
            detail = traceback.format_exc(limit=6)
            log(f"Dettaglio errore:\n{detail}")
            self._fail(path, rel, f"{type(e).__name__}: {e}")
        finally:
            self.set_status(state="idle", current=None, detail="", force=True)

    @staticmethod
    def _discard(result, tmp_out, tmp_prefix):
        """Rimuove gli output parziali (anche con nome diverso, es. documento interno di un .p7m)."""
        for p in {result, tmp_out}:
            if p:
                common.remove_quietly(p)
        try:
            d = os.path.dirname(tmp_out)
            for f in os.listdir(d):
                if f.startswith(tmp_prefix):
                    common.remove_quietly(os.path.join(d, f))
        except OSError:
            pass

    def _fail(self, path, rel, reason):
        self.status["failed"] += 1
        log(f"[ERRORE] Impossibile elaborare {rel}: {reason}")
        try:
            self._move_away(path, common.FAILED_DIR, rel)
            self._record_failure(rel, reason)
        except Exception as e:
            try:
                self.stuck[path] = (os.path.getsize(path), os.stat(path).st_mtime_ns)
            except OSError:
                pass
            log(f"FATALE: impossibile spostare {rel} in failed: {e}")

    def _write_audit(self, rel, ctx):
        try:
            entries = list(ctx.audit)
            for n in ctx.notes:
                entries.append({"word": "", "label": "[NOTA]", "entity": "NOTE", "score": 1.0, "note": n})
            path = os.path.join(common.EXTRACTED_DIR, rel + ".json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            common.atomic_write_json(path, entries, indent=4)
        except Exception as e:
            log(f"Impossibile salvare il report di audit per {rel}: {e}")

    # ------------------------------------------------------------------ ciclo principale
    def run(self):
        common.ensure_dirs()
        if not self.check_single_instance():
            return 0
        self.write_state(status="loading")
        self.cleanup_leftovers()
        self.start_watchdog()
        log(f"Inizializzazione Germano AI Daemon v{VERSION}...")
        self.set_status(state="loading", force=True)
        try:
            self.engine.load(self.settings)
        except Exception as e:
            self.fatal(f"caricamento modelli IA non riuscito: {type(e).__name__}: {e}")
            log(traceback.format_exc(limit=8))
            return 1
        if self.should_stop():
            log("Avvio annullato.")
            return 0
        from germano.daemon_api import start_api
        try:
            self.port = start_api(self)
        except Exception as e:
            self.fatal(f"impossibile avviare l'API interna: {e}")
            return 1
        self.write_state(status="ready")
        with open(common.READY_FLAG, "w", encoding="utf-8") as f:
            f.write("1")
        self.set_status(state="idle", force=True)
        log("Sistema PRONTO. In ascolto continuo sulla cartella input/ e sul Proxy API.")

        last_flush = time.time()
        while not self.should_stop():
            self.reload_settings()
            if time.time() - last_flush > 3:
                self.vault.flush()
                last_flush = time.time()
            try:
                files = self.scan_input()
            except Exception as e:
                log(f"Errore lettura cartella input: {e}")
                files = []
            self.set_status(queue=len(files))
            for i, p in enumerate(files):
                if self.should_stop():
                    break
                if not os.path.exists(p):
                    continue
                self.set_status(queue=len(files) - i)
                self.reload_settings()
                try:
                    self.process_one(p)
                except Exception as e:
                    # un singolo file problematico (es. percorso troppo lungo) non deve fermare il motore
                    rel = os.path.relpath(p, common.INPUT_DIR)
                    log(f"Dettaglio errore:\n{traceback.format_exc(limit=6)}")
                    self._fail(p, rel, f"{type(e).__name__}: {e}")
                    self.set_status(state="idle", current=None, detail="", force=True)
            self.set_status(queue=0)
            self.cleanup_empty_dirs()
            if not files:
                self.stop_event.wait(1.0)
        log("Segnale di arresto ricevuto: chiusura sicura del demone.")
        self.vault.flush()
        return 0

    def shutdown(self):
        self.stop_event.set()
        for f in (common.READY_FLAG, common.STOP_FLAG, common.STATUS_FILE):
            common.remove_quietly(f)
        st = common.read_json(common.DAEMON_STATE_FILE, {}) or {}
        if st.get("pid") == os.getpid():
            common.remove_quietly(common.DAEMON_STATE_FILE)


def main():
    d = Daemon()
    code = 1
    try:
        code = d.run()
    except KeyboardInterrupt:
        code = 0
    except Exception as e:
        d.fatal(f"{type(e).__name__}: {e}")
        log(traceback.format_exc())
    finally:
        d.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
