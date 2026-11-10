"""Trascrizione vocale locale (speech-to-text) per i file audio: gestione del processo separato.

Modello: OpenAI Whisper «small» (multilingue, licenza MIT) convertito in CTranslate2 con pesi INT8, eseguito da
faster-whisper su CPU, 100% offline (models/whisper-small). Il parlato viene prima isolato dal silenzio (rilevatore
vocale Silero, incluso in faster-whisper) e poi trascritto in segmenti con l'istante di inizio e di fine.

Il lavoro avviene in un processo a parte (speech_worker.py), avviato solo quando arriva un file audio:
- si avvia alla prima trascrizione; dopo 5 minuti senza richieste si chiude e libera la memoria;
- termina con il demone (Windows: job object; Linux: segnale alla morte del padre; tutti: la chiusura del suo stdin);
- un file audio malformato che manda in errore il decodificatore ferma solo quel processo, non il motore;
- annullamento (arresto del motore, tempo scaduto): il processo viene chiuso subito;
- sorveglianza: se per 15 minuti non arriva nessun segmento la trascrizione viene interrotta.
Nessun dato lascia il computer: il processo non apre connessioni (HF_HUB_OFFLINE) e riceve solo percorsi di file locali.
"""
import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time

from . import common
from .engine import NO_CANCEL

MODEL_FOLDER_PREFIX = "whisper"          # models/whisper-small (la prima cartella «whisper*» che contiene model.bin)
IDLE_STOP_S = 300                        # processo chiuso dopo 5 minuti senza richieste
START_TIMEOUT_S = 120
STALL_TIMEOUT_S = 900                    # nessun evento dal processo per 15 minuti: trascrizione interrotta
PROBE_TIMEOUT_S = 120
SPEED_MARGIN = 4.0                       # tempo concesso = durata x 4 + 10 minuti (CPU lente comprese)
SPEED_BASE_S = 600
REQUIRED = ("faster_whisper", "ctranslate2", "av")
LANGUAGE_NAMES = {"it": "italiano", "en": "inglese", "fr": "francese", "de": "tedesco", "es": "spagnolo",
                  "pt": "portoghese", "nl": "olandese", "ro": "rumeno", "pl": "polacco", "sq": "albanese",
                  "uk": "ucraino", "ru": "russo", "ar": "arabo", "zh": "cinese", "ca": "catalano", "el": "greco",
                  "tr": "turco", "hr": "croato", "sl": "sloveno", "sr": "serbo", "bg": "bulgaro", "hu": "ungherese",
                  "cs": "ceco", "sk": "slovacco", "sv": "svedese", "da": "danese", "fi": "finlandese",
                  "no": "norvegese", "ja": "giapponese", "ko": "coreano", "hi": "hindi", "la": "latino"}


class SpeechError(Exception):
    """Trascrizione non riuscita o non disponibile (messaggio gia' comprensibile per l'utente)."""


def locate_model():
    """(cartella del modello, manifesto germano.json) oppure (None, {})."""
    forced = os.environ.get("GERMANO_SPEECH_MODEL_DIR")
    candidates = [forced] if forced else []
    try:
        candidates += [os.path.join(common.MODELS_DIR, d) for d in sorted(os.listdir(common.MODELS_DIR))
                       if d.lower().startswith(MODEL_FOLDER_PREFIX)]
    except OSError:
        pass
    for folder in candidates:
        if folder and os.path.isfile(os.path.join(folder, "model.bin")) and os.path.isfile(os.path.join(folder, "config.json")):
            return folder, (common.read_json(os.path.join(folder, "germano.json"), {}) or {})
    return None, {}


def missing_packages():
    out = []
    for name in REQUIRED:
        try:
            if importlib.util.find_spec(name) is None:
                out.append(name)
        except (ImportError, ValueError):
            out.append(name)
    return out


class SpeechEngine:
    def __init__(self, log=common.log, threads=None):
        self.log = log
        self.threads = max(1, int(threads or min(4, common.cpus_available())))
        self.model_dir, self.manifest = locate_model()
        self.missing = missing_packages()
        self._lock = threading.Lock()          # una trascrizione alla volta
        self._proc = None
        self._events = None
        self._job = None
        self._last_used = 0.0
        self._watcher = None
        self.last_error = None
        self.stats = {"files": 0, "audio_seconds": 0.0, "seconds": 0.0, "starts": 0}

    # ------------------------------------------------------------------ stato
    @property
    def available(self):
        return bool(self.model_dir) and not self.missing

    def unavailable_reason(self):
        if self.missing:
            return "librerie della trascrizione non installate (" + ", ".join(self.missing) + ")"
        if not self.model_dir:
            return "modello vocale non installato (models/whisper-small)"
        return ""

    def info(self):
        m = self.manifest or {}
        return {"available": self.available, "running": self._running(),
                "model": m.get("name") or (os.path.basename(self.model_dir) if self.model_dir else None),
                "quantization": m.get("quantization"), "runtime": m.get("runtime") or "faster-whisper (CTranslate2)",
                "reason": self.unavailable_reason() or None, "error": self.last_error,
                "files": self.stats["files"], "audio_seconds": round(self.stats["audio_seconds"], 1)}

    def model_label(self):
        m = self.manifest or {}
        name = m.get("name") or (os.path.basename(self.model_dir) if self.model_dir else "Whisper")
        return f"{name} ({m['quantization']})" if m.get("quantization") else name

    # ------------------------------------------------------------------ processo
    def _running(self):
        return self._proc is not None and self._proc.poll() is None

    def _start(self):
        if self._running():
            return
        if not self.available:
            raise SpeechError("Trascrizione audio non disponibile: " + self.unavailable_reason() + ".")
        worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speech_worker.py")
        os.makedirs(common.STATE_DIR, exist_ok=True)
        env = dict(os.environ)
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8", HF_HUB_OFFLINE="1",
                   OMP_NUM_THREADS=str(self.threads))
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000                   # CREATE_NO_WINDOW
        elif sys.platform.startswith("linux"):
            from .system2_resolver import _linux_parent_death
            kw["preexec_fn"] = _linux_parent_death
        logf = open(os.path.join(common.STATE_DIR, "trascrizione.log"), "ab")
        try:
            proc = subprocess.Popen([sys.executable, "-B", worker], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=logf, cwd=common.STATE_DIR, env=env, **kw)
        finally:
            logf.close()
        if os.name == "nt":
            try:
                if self._job is None:
                    from .system2_resolver import _WinJob
                    self._job = _WinJob()
                self._job.assign(proc)
            except Exception:
                pass
        events = queue.Queue()

        def pump(p=proc, q=events):
            try:
                for raw in p.stdout:
                    try:
                        q.put(json.loads(raw.decode("utf-8", "replace")))
                    except ValueError:
                        continue
            except Exception:
                pass
            q.put({"ev": "closed"})
        threading.Thread(target=pump, daemon=True, name="trascrizione-eventi").start()
        self._proc, self._events = proc, events
        t0 = time.time()
        while True:
            try:
                ev = events.get(timeout=1.0)
            except queue.Empty:
                if time.time() - t0 > START_TIMEOUT_S:
                    self._kill()
                    raise SpeechError("Il processo della trascrizione non si e' avviato in tempo.") from None
                continue
            if ev.get("ev") == "ready":
                break
            if ev.get("ev") == "closed":
                self._kill()
                raise SpeechError("Il processo della trascrizione non si e' avviato (dettagli in "
                                  "state/trascrizione.log).")
        self.stats["starts"] += 1
        self._last_used = time.time()
        if self._watcher is None or not self._watcher.is_alive():
            self._watcher = threading.Thread(target=self._idle_watch, daemon=True, name="trascrizione-riposo")
            self._watcher.start()

    def _idle_watch(self):
        while True:
            time.sleep(15)
            if not self._running():
                return
            if time.time() - self._last_used > IDLE_STOP_S and self._lock.acquire(blocking=False):
                try:
                    if self._running() and time.time() - self._last_used > IDLE_STOP_S:
                        self.log("Trascrizione: nessuna richiesta da 5 minuti, il modello vocale esce dalla memoria.")
                        self._kill(graceful=True)
                        return
                finally:
                    self._lock.release()

    def _kill(self, graceful=False):
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if graceful and proc.poll() is None:
                try:
                    proc.stdin.write(b'{"cmd": "quit"}\n')
                    proc.stdin.flush()
                    proc.wait(5)
                except Exception:
                    pass
            if proc.poll() is None:
                proc.kill()
                proc.wait(10)
        except Exception:
            pass
        for stream in (proc.stdin, proc.stdout):
            try:
                stream.close()
            except Exception:
                pass

    def stop(self):
        with self._lock:
            self._kill(graceful=True)

    def _send(self, obj):
        self._proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self._proc.stdin.flush()

    # ------------------------------------------------------------------ richieste
    def _request(self, req, cancel, on_event, total_timeout):
        """Invia un comando e legge gli eventi fino a «done». Solleva SpeechError; l'annullamento chiude il processo."""
        cancel = cancel or NO_CANCEL
        self._start()
        try:
            self._send(req)
        except (OSError, ValueError):
            self._kill()
            self._start()                      # processo chiuso nel frattempo (riposo): un nuovo tentativo
            self._send(req)
        started = last = time.time()
        while True:
            try:
                cancel.check()
            except Exception:
                self._kill()                   # arresto o tempo scaduto: il processo si ferma subito
                raise
            try:
                ev = self._events.get(timeout=0.5)
            except queue.Empty:
                now = time.time()
                if now - last > STALL_TIMEOUT_S or (total_timeout and now - started > total_timeout):
                    self._kill()
                    raise SpeechError("Trascrizione interrotta: il modello vocale non ha prodotto risultati per "
                                      "troppo tempo.") from None
                continue
            last = time.time()
            kind = ev.get("ev")
            if kind == "closed":
                self._kill()
                raise SpeechError("Il processo della trascrizione si e' chiuso in modo inatteso (file audio "
                                  "danneggiato o memoria insufficiente). Dettagli in state/trascrizione.log.")
            if kind == "error":
                raise SpeechError(self._message(ev))
            if kind == "done":
                return ev
            on_event(ev)

    @staticmethod
    def _message(ev):
        kind, detail = ev.get("kind"), str(ev.get("message") or "")
        if kind == "too_long":
            return f"too_long:{float(ev.get('duration') or 0):.0f}"
        if kind == "memory":
            return "Memoria insufficiente per trascrivere questa registrazione: dividila in parti piu' brevi."
        if kind == "decode":
            if "traccia audio" in detail:
                return "Il file non contiene una traccia audio."
            return "File audio danneggiato o in un formato non riconosciuto: non e' stato possibile leggerlo."
        return f"Trascrizione non riuscita ({detail[:200]})."

    def probe(self, path, cancel=None):
        """Formato e metadati incorporati (tag ID3, commenti Vorbis, atomi MP4...) senza trascrivere."""
        box = {}
        with self._lock:
            try:
                self._request({"cmd": "probe", "path": os.path.abspath(path)}, cancel,
                              lambda ev: box.update(ev) if ev.get("ev") == "probe" else None, PROBE_TIMEOUT_S)
            finally:
                self._last_used = time.time()
        return {"format": box.get("format") or {}, "tags": box.get("tags") or {}}

    def transcribe(self, path, settings=None, cancel=None, progress=None, extend=None):
        """Trascrive un file audio. Restituisce {segments: [(inizio, fine, testo)], language, language_probability,
        duration, speech, format, tags, model, seconds}. `extend(secondi)`: il chiamante sposta in avanti il proprio
        tempo massimo in base alla durata della registrazione."""
        settings = settings or {}
        language = settings.get("speech_language") or "auto"
        max_minutes = int(settings.get("speech_max_minutes") or common.DEFAULT_SETTINGS["speech_max_minutes"])
        out = {"segments": [], "format": {}, "tags": {}, "language": None, "language_probability": None,
               "duration": 0.0, "speech": 0.0, "model": self.model_label()}
        t0 = time.time()

        def on_event(ev):
            kind = ev.get("ev")
            if kind == "probe":
                out["format"], out["tags"] = ev.get("format") or {}, ev.get("tags") or {}
                d = out["format"].get("duration")
                if d and extend:
                    extend(d * SPEED_MARGIN + SPEED_BASE_S)
                if progress:
                    progress("audio: lettura della traccia" + (f" ({_clock(d)})" if d else ""))
            elif kind == "audio":
                out["duration"] = float(ev.get("duration") or 0)
                if extend:
                    extend(out["duration"] * SPEED_MARGIN + SPEED_BASE_S)
                if progress:
                    progress(f"audio: trascrizione di {_clock(out['duration'])} di registrazione")
            elif kind == "info":
                out["language"] = ev.get("language")
                out["language_probability"] = ev.get("language_probability")
                out["speech"] = float(ev.get("speech") or 0)
            elif kind == "segment":
                out["segments"].append((float(ev["start"]), float(ev["end"]), str(ev["text"])))
                if progress and out["duration"]:
                    progress(f"audio: trascrizione {_clock(ev['end'])} di {_clock(out['duration'])}")

        req = {"cmd": "transcribe", "path": os.path.abspath(path), "model_dir": self.model_dir,
               "threads": self.threads, "compute_type": "int8", "language": None if language == "auto" else language,
               "max_seconds": max_minutes * 60}
        with self._lock:
            try:
                self._request(req, cancel, on_event, None)
            except SpeechError as e:
                self.last_error = str(e)
                if str(e).startswith("too_long:"):
                    raise SpeechError(f"Registrazione troppo lunga ({_clock(float(str(e)[9:]))}): il massimo e' "
                                      f"{max_minutes} minuti («speech_max_minutes» in config.json). Dividila in "
                                      "parti piu' brevi.") from None
                raise
            finally:
                self._last_used = time.time()
        out["seconds"] = round(time.time() - t0, 1)
        self.last_error = None
        self.stats["files"] += 1
        self.stats["audio_seconds"] += out["duration"]
        self.stats["seconds"] += out["seconds"]
        return out


def _clock(seconds):
    s = max(0, int(round(float(seconds or 0))))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


clock = _clock
