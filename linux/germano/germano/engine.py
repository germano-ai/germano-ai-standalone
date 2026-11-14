"""Motore IA: caricamento modelli locali, classificazione a blocchi con cache, OCR e visione artificiale.

Concorrenza (turno 26). Il demone serve insieme la cartella input/ (lavori in coda) e le richieste interattive (Proxy,
Harness, API, motore condiviso con i client della rete). Ogni modello ha il proprio lock (i tokenizer «fast» di
HuggingFace, EasyOCR e il rilevatore di volti di OpenCV non si possono usare da piu' thread insieme), quindi modelli
diversi lavorano in parallelo: per esempio l'OCR di una scansione in coda e il Privacy Filter di una richiesta del
Proxy. I lock del Privacy Filter e dell'OCR danno la precedenza alle richieste interattive: una richiesta del Proxy
aspetta al massimo il lotto in corso, non l'intero documento in coda.
L'Italian NER in ONNX Runtime (engine_onnx, stessi risultati del modello PyTorch) rilascia il GIL e gira in un thread a
parte MENTRE il Privacy Filter elabora lo stesso lotto (misurato sul banco del turno 26: -11% sul tempo del testo,
span identici). Il Privacy Filter si carica all'avvio se attivo nelle impostazioni, altrimenti alla prima richiesta
che lo usa; all'avvio Italian NER e OCR si caricano in parallelo al Privacy Filter.
"""
import contextlib
import hashlib
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from . import common

CHUNK_CHARS = 2000
CHUNK_OVERLAP = 240
ITA_MIN_SCORE = 0.70
PF_BATCH = 8  # misurato su CPU: batch da 8 blocchi circa 1,5x piu' veloce del blocco singolo, risultati identici
# Precisione automatica. Il Privacy Filter occupa +5,3 GB in FP32 e +2,7 GB in BF16 (misurato). Sui processori senza
# BF16 nativo (AVX2: es. Intel Haswell/Broadwell, Xeon E5 v3/v4, molti host di virtualizzazione) il BF16 e' da 4 a 10
# volte piu' lento (i5-4570: 12,4 s contro 1,6 s per blocco con 4 thread), quindi lì si usa FP32 tutte le volte che la
# memoria libera lo consente; il BF16 resta per i computer con poca RAM.
FP32_TOTAL_GB = 11.5      # RAM totale oltre la quale si usa sempre FP32 (come prima)
FP32_FREE_GB = 7.0        # RAM libera sufficiente per FP32 anche sotto quella soglia (modello + altri modelli + margine)
SELF_TEST_TEXT = "Il signor Mario Rossi abita in via Roma 1 a Milano."


class CancelledError(Exception):
    def __init__(self, reason="stop"):
        super().__init__(reason)
        self.reason = reason


class CancelToken:
    """Annullamento cooperativo: arresto richiesto, timeout del file, chiusura del processo padre."""

    def __init__(self, deadline=None, stop_check=None):
        self.deadline = deadline
        self.stop_check = stop_check

    def check(self):
        if self.stop_check is not None and self.stop_check():
            raise CancelledError("stop")
        if self.deadline is not None and time.time() > self.deadline:
            raise CancelledError("timeout")


NO_CANCEL = CancelToken()


# ------------------------------------------------------------------ precedenza delle richieste interattive
_PRIORITY = threading.local()


def is_interactive():
    """True nel thread di una richiesta interattiva (API interna del demone: Proxy, Harness, motore condiviso)."""
    return bool(getattr(_PRIORITY, "high", False))


@contextlib.contextmanager
def interactive_scope(high=True):
    """Le chiamate al motore fatte in questo blocco passano davanti ai lavori della cartella input/."""
    prev = getattr(_PRIORITY, "high", False)
    _PRIORITY.high = bool(high)
    try:
        yield
    finally:
        _PRIORITY.high = prev


class PriorityLock:
    """Lock rientrante di un modello: chi aspetta per una richiesta interattiva entra prima di chi aspetta per un
    lavoro in coda. Il lavoro in corso non viene interrotto: si attende al massimo un lotto (pochi secondi)."""

    def __init__(self):
        self._cv = threading.Condition(threading.Lock())
        self._owner = None
        self._count = 0
        self._waiting_high = 0

    def acquire(self, high=None):
        me = threading.get_ident()
        high = is_interactive() if high is None else bool(high)
        with self._cv:
            if self._owner == me:
                self._count += 1
                return True
            if high:
                self._waiting_high += 1
                try:
                    while self._owner is not None:
                        self._cv.wait()
                finally:
                    self._waiting_high -= 1
            else:
                while self._owner is not None or self._waiting_high:
                    self._cv.wait()
            self._owner, self._count = me, 1
            return True

    def release(self):
        with self._cv:
            if self._owner != threading.get_ident():
                raise RuntimeError("PriorityLock rilasciato da un thread che non lo possiede")
            self._count -= 1
            if not self._count:
                self._owner = None
                self._cv.notify_all()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


def make_chunks(text, size=CHUNK_CHARS, overlap=CHUNK_OVERLAP):
    """Divide il testo in blocchi sovrapposti. Restituisce (inizio, fine, keep_lo, keep_hi):
    di ogni blocco si tengono solo gli span che iniziano in [keep_lo, keep_hi), cosi' ogni zona
    viene attribuita al blocco che la vede con piu' contesto."""
    n = len(text)
    if n <= size:
        return [(0, n, 0, n)]
    bounds = []
    start = 0
    while start < n:
        end = min(n, start + size)
        if end < n:
            lo = start + int(size * 0.6)
            cut = -1
            for sep in ("\n\n", "\n", ". ", "; ", ", ", " "):
                cut = text.rfind(sep, lo, end)
                if cut != -1:
                    cut += len(sep)
                    break
            end = cut if cut > start else end
        bounds.append([start, end])
        if end >= n:
            break
        nxt = max(end - overlap, start + 1)
        sp = text.find(" ", nxt, end)
        start = sp + 1 if sp != -1 else nxt
    out = []
    for i, (a, b) in enumerate(bounds):
        keep_lo = 0 if i == 0 else (a + bounds[i - 1][1]) // 2
        keep_hi = n if i == len(bounds) - 1 else (bounds[i + 1][0] + b) // 2
        out.append((a, b, keep_lo, keep_hi))
    return out


class Engine:
    def __init__(self, log=common.log):
        self.log = log
        # un lock per modello (turno 26; prima un solo lock per tutti): modelli diversi lavorano in parallelo
        self._pf_lock = PriorityLock()          # Privacy Filter (PyTorch) e il suo tokenizer
        self._ita_pt_lock = threading.Lock()    # Italian NER in PyTorch (solo ripiego, senza ONNX Runtime)
        self._ocr_lock = PriorityLock()         # EasyOCR
        self._face_lock = threading.Lock()      # YuNet (OpenCV): setInputSize cambia lo stato del rilevatore
        self._det_locks = {"sig": threading.Lock(), "plate": threading.Lock()}   # firme, targhe (YOLOS)
        self._load_lock = threading.RLock()     # caricamento su richiesta dei modelli
        self._cache_lock = threading.Lock()     # cache dei risultati per blocco di testo
        self._ita_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="italian-ner")
        self.torch = None
        self.device = "cpu"
        self.precision = "fp32"
        self.pf = None
        self._pf_dtype = None           # precisione scelta all'avvio, per caricare il Privacy Filter piu' tardi
        self.ita = None
        self.ita_onnx = None
        self.system2 = None             # Sistema 2 (system2_resolver): si avvia solo alla prima analisi con dubbi
        self.speech = None              # trascrizione vocale (speech): processo separato, avviato al primo file audio
        self.ocr_reader = None
        self._face = None
        self._sig = None
        self._plate = None
        self._tried = set()
        self._cache = OrderedDict()
        self._cache_max = 6000
        self.info = {}

    # ------------------------------------------------------------------ caricamento
    def load(self, settings):
        import psutil
        import torch
        from transformers import pipeline

        self.torch = torch
        try:
            torch.set_grad_enabled(False)
        except Exception:
            pass

        threads, threads_source = self._cpu_threads(torch, settings)
        capability = self._cpu_capability(torch)
        bf16_native = self._bf16_native(torch)
        vm = common.virtual_machine()
        hw = settings.get("hardware_mode", "gpu_fallback")
        self.device = "cpu"
        if hw in ("gpu", "gpu_fallback"):
            try:
                if torch.cuda.is_available():
                    self.device = "cuda"
                    self.log("Hardware: GPU NVIDIA (CUDA) disponibile, accelerazione attivata.")
            except Exception:
                pass
        if self.device == "cpu":     # VM senza GPU, server, PC comuni: tutta la pipeline gira su CPU
            build = "CPU" if "+cpu" in getattr(torch, "__version__", "") else "standard"
            self.log(f"Hardware: elaborazione su processore (CPU {capability}, {common.cpus_available()} processori "
                     f"disponibili{', macchina virtuale ' + vm if vm else ''}; {threads} thread per i modelli "
                     f"({threads_source}); BF16 nativo: {'si' if bf16_native else 'no'}; PyTorch {build}).")

        mem = psutil.virtual_memory()
        total_gb, free_gb = mem.total / (1024 ** 3), mem.available / (1024 ** 3)
        dt, why = self._choose_dtype(torch, settings.get("precision", "auto"), total_gb, free_gb, bf16_native)
        self.log(f"RAM totale {total_gb:.1f} GB ({free_gb:.1f} GB liberi): Privacy Filter in "
                 f"{'BF16' if dt == torch.bfloat16 else 'FP32'} - {why}.")

        self._pf_dtype = dt
        # Italian NER (ONNX) e OCR si caricano in parallelo al Privacy Filter (turno 26: prima uno dopo l'altro)
        ita_path = os.path.join(common.MODELS_DIR, "italian-ner-xxl")
        ita_box, ocr_box = {}, {}
        side = []
        if os.path.isdir(ita_path) and os.listdir(ita_path):
            side.append(threading.Thread(target=self._load_italian_onnx, args=(ita_path, threads, ita_box),
                                         name="carica-italian-ner", daemon=True))
        side.append(threading.Thread(target=self._load_ocr, args=(ocr_box,), name="carica-ocr", daemon=True))
        for th in side:
            th.start()
        t_pf = time.time()
        if bool(settings.get("enable_model_velvet", True)):
            self._load_privacy_filter()
        else:
            self.pf = None
            self.precision = "fp32"
            self.log("Privacy Filter 1.5B disattivato nelle impostazioni: si carica alla prima richiesta che lo usa.")
        for th in side:
            th.join()
        self.log(f"Modelli del testo e OCR pronti in {time.time() - t_pf:.0f}s (caricamento in parallelo).")

        if os.path.isdir(ita_path) and os.listdir(ita_path):
            onnx_error = ita_box.get("error")
            self.ita_onnx = ita_box.get("clf")

            # Dalla 0.80 i pacchetti contengono solo il modello ONNX (stessi pesi, 210 MB in meno); il modello
            # PyTorch (model.safetensors) resta un ripiego per chi esegue dai sorgenti e lo ha nella cartella.
            if self.ita_onnx is None and os.path.isfile(os.path.join(ita_path, "model.safetensors")):
                self.log(f"Info: Italian NER in ONNX Runtime non disponibile ({onnx_error}): si usa PyTorch.")
                try:
                    t = time.time()
                    self.log("Caricamento modello specialistico Italian_NER_XXL_v2 (58 categorie, PyTorch)...")
                    self.ita = pipeline(
                        task="token-classification", model=ita_path, tokenizer=ita_path,
                        aggregation_strategy="simple", device=self.device, model_kwargs={"dtype": torch.float32},
                    )
                    self.log(f"Italian NER pronto in {time.time() - t:.0f}s.")
                except Exception as e:
                    onnx_error = e
                    self.ita = None
            if self.ita_onnx is None and self.ita is None:
                # Un modello attivo nelle impostazioni non viene mai saltato in silenzio (come il Privacy Filter):
                # senza Italian NER molti dati personali resterebbero in chiaro senza che nessuno se ne accorga.
                if bool(settings.get("enable_model_italian_ner", True)):
                    raise RuntimeError(f"il modello Italian NER non si carica ({type(onnx_error).__name__}: "
                                       f"{onnx_error}). Reinstalla Germano oppure disattiva «Italian NER» nelle "
                                       "Impostazioni (profilo PD) se vuoi proseguire senza.")
                self.log(f"Avviso: Italian_NER_XXL non caricato ({onnx_error}); e' disattivato nelle impostazioni.")

        try:
            from . import system2_resolver
            self.system2 = system2_resolver.System2Resolver(log=self.log, threads=threads)
            s2 = self.system2.info()
            if s2["available"]:
                self.log(f"Sistema 2 disponibile su richiesta ({s2['model']}, llama.cpp solo su 127.0.0.1): decide "
                         "nel contesto i casi dubbi del Sistema 1.")
            else:
                self.log("Sistema 2 non installato: i casi dubbi del Sistema 1 restano oscurati.")
        except Exception as e:
            self.log(f"Avviso: Sistema 2 non disponibile ({e}): i casi dubbi restano oscurati.")
            self.system2 = None

        try:
            from . import speech
            self.speech = speech.SpeechEngine(log=self.log, threads=threads)
            if self.speech.available:
                self.log(f"Trascrizione audio disponibile su richiesta ({self.speech.model_label()}, offline, in un "
                         "processo separato): MP3, WAV, M4A, OGG, FLAC.")
            else:
                self.log(f"Trascrizione audio non disponibile: {self.speech.unavailable_reason()}.")
        except Exception as e:
            self.log(f"Avviso: trascrizione audio non disponibile ({e}).")
            self.speech = None

        self.ocr_reader = ocr_box.get("reader")
        if self.ocr_reader is None:
            self.log(f"Avviso: OCR non disponibile ({ocr_box.get('error')}).")

        self.info = {
            "device": self.device,
            "precision": self.precision,
            "ram_gb": round(total_gb, 1),
            "threads": threads,
            "cpus": common.cpus_available(),
            "cpu": capability,
            "bf16_native": bf16_native,
            "vm": vm,
            "privacy_filter": self.pf is not None,
            "italian_ner_onnx": self.ita_onnx is not None,
            "italian_ner": self.ita is not None or self.ita_onnx is not None,
            "ocr": self.ocr_reader is not None,
            "system2": self.system2.info() if self.system2 is not None else {"available": False},
            "speech": self.speech.info() if self.speech is not None else {"available": False},
        }

    def _load_italian_onnx(self, ita_path, threads, box):
        """Thread di avvio: Italian NER in ONNX Runtime con la prova sul testo di controllo."""
        try:
            from . import engine_onnx
            t = time.time()
            self.log("Caricamento modello specialistico Italian_NER_XXL_v2 (ONNX Runtime, stessi risultati di "
                     "PyTorch)...")
            clf = engine_onnx.OnnxTokenClassifier(ita_path, threads=threads)
            # prova all'avvio: un modello che si apre ma non riconosce un nome evidente non e' utilizzabile
            found = [e for e in clf.predict([SELF_TEST_TEXT])[0] if e.get("score", 0) >= ITA_MIN_SCORE]
            if not found:
                raise RuntimeError("la prova del modello non ha riconosciuto nessun dato nel testo di controllo")
            box["clf"] = clf
            self.log(f"Italian NER pronto in {time.time() - t:.1f}s ({os.path.basename(clf.onnx_path)}, prova "
                     f"superata: {len(found)} dati nel testo di controllo).")
        except Exception as e:
            box["error"] = e

    def _load_ocr(self, box):
        """Thread di avvio: EasyOCR (rilevatore CRAFT + riconoscitore per italiano e inglese)."""
        self.log("Caricamento motore OCR (EasyOCR locale)...")
        try:
            import easyocr
            t = time.time()
            ocr_dir = os.path.join(common.MODELS_DIR, "easyocr")
            box["reader"] = easyocr.Reader(
                ["it", "en"], gpu=(self.device == "cuda"), verbose=False, download_enabled=False,
                model_storage_directory=ocr_dir, user_network_directory=ocr_dir,
            )
            self.log(f"Motore OCR caricato in {time.time() - t:.1f}s.")
        except Exception as e:
            box["error"] = e

    # ------------------------------------------------------------------ audio
    def transcribe(self, path, settings=None, cancel=None, progress=None, extend=None):
        """Trascrizione offline del parlato di un file audio, con metadati e formato (vedi speech.SpeechEngine)."""
        from . import speech
        if self.speech is None:
            raise speech.SpeechError("Trascrizione audio non disponibile su questo motore.")
        try:
            return self.speech.transcribe(path, settings, cancel, progress, extend)
        finally:
            if self.info.get("speech") is not None:
                self.info["speech"] = self.speech.info()

    # ------------------------------------------------------------------ Sistema 2
    def resolve_doubts(self, text, spans, settings, cancel=None, known=None):
        """Casi dubbi del Sistema 1 decisi nel contesto dal Sistema 2. Restituisce (span da oscurare, decisioni).
        Senza Sistema 2 (spento, non installato, errori) tutti gli span restano: i dubbi restano oscurati.
        `known`: firme di propagazione delle parole gia' oscurate nel documento (domande superflue, vedi Sistema 2)."""
        if self.system2 is None:
            return spans, []
        try:
            kept, decisions = self.system2.resolve(text, spans, settings, cancel, known=known)
        except CancelledError:
            raise
        except Exception as e:
            self.log(f"Avviso: Sistema 2 non riuscito ({type(e).__name__}: {e}): i casi dubbi restano oscurati.")
            return spans, []
        if self.info.get("system2") is not None:
            self.info["system2"] = self.system2.info()
        return kept, decisions

    def resolve_doubts_many(self, items, settings, cancel=None, known=None):
        """Come resolve_doubts per piu' testi insieme [(testo, span)]: i dubbi di tutti i testi vanno al Sistema 2 in
        un'unica coda invece che un testo alla volta (turno 26). Restituisce [(span da oscurare, decisioni)]."""
        if self.system2 is None:
            return [(spans, []) for _t, spans in items]
        try:
            out = self.system2.resolve_many(items, settings, cancel, known=known)
        except CancelledError:
            raise
        except Exception as e:
            self.log(f"Avviso: Sistema 2 non riuscito ({type(e).__name__}: {e}): i casi dubbi restano oscurati.")
            return [(spans, []) for _t, spans in items]
        if self.info.get("system2") is not None:
            self.info["system2"] = self.system2.info()
        return out

    def close(self):
        """Chiusura ordinata (fine del demone): ferma il server locale del Sistema 2 e il processo vocale."""
        for part in (self.system2, self.speech):
            if part is not None:
                try:
                    part.stop()
                except Exception:
                    pass
        self._ita_pool.shutdown(wait=False)

    def _load_privacy_filter(self):
        """Carica il Privacy Filter (all'avvio o alla prima richiesta che lo usa). Solleva un'eccezione se non riesce:
        un modello attivo nelle impostazioni non viene mai saltato in silenzio."""
        torch = self.torch
        from transformers import pipeline
        dt = self._pf_dtype or torch.float32
        pf_path = os.path.join(common.MODELS_DIR, "privacy-filter")
        if not os.path.isdir(pf_path) or not os.listdir(pf_path):
            raise FileNotFoundError(f"Modello locale non trovato in {pf_path}")
        t = time.time()
        self.log("Caricamento modello Privacy Filter 1.5B (100% offline)...")
        try:
            pf = self._load_pf(pipeline, pf_path, dt)
            if dt == torch.bfloat16:
                t2 = time.time()
                pf(SELF_TEST_TEXT)       # alcune CPU o librerie non hanno tutte le operazioni in BF16
                self.log(f"Prova del modello in BF16 riuscita ({time.time() - t2:.1f} s).")
        except Exception as e:
            if dt != torch.bfloat16:
                raise
            self.log(f"ATTENZIONE: BF16 non utilizzabile su questo processore ({type(e).__name__}: {e}): ripiego "
                     "automatico su FP32.")
            import gc
            gc.collect()
            dt = torch.float32
            pf = self._load_pf(pipeline, pf_path, dt)
        self.pf = pf
        self.precision = "bf16" if dt == torch.bfloat16 else "fp32"
        if self.info:
            self.info["privacy_filter"] = True
            self.info["precision"] = self.precision
        self.log(f"Privacy Filter pronto in {time.time() - t:.0f}s.")

    def _ensure_privacy_filter(self, settings):
        """Privacy Filter riattivato nelle impostazioni (o chiesto da un client) dopo un avvio senza: si carica ora."""
        if self.pf is not None or self.torch is None or not bool(settings.get("enable_model_velvet", True)):
            return
        with self._load_lock:
            if self.pf is None:
                self._load_privacy_filter()

    # ------------------------------------------------------------------ processore e precisione
    @staticmethod
    def _cpu_threads(torch, settings):
        """Thread di calcolo: gli stessi che il demone ha impostato prima di importare torch (OMP_NUM_THREADS)."""
        n, source = common.cpu_threads(settings)
        try:
            torch.set_num_threads(n)
        except Exception:
            pass
        try:
            torch.set_num_interop_threads(min(2, n))   # i modelli non usano il parallelismo fra operazioni
        except Exception:
            pass                                       # gia' impostato in questo processo: si lascia com'e'
        return torch.get_num_threads(), source

    @staticmethod
    def _cpu_capability(torch):
        try:
            return str(torch.backends.cpu.get_cpu_capability())
        except Exception:
            return "sconosciuta"

    @staticmethod
    def _bf16_native(torch):
        """True se oneDNN accelera il BF16 su questa CPU (AVX-512 / AMX); False su AVX2 e sulle vCPU che lo nascondono."""
        try:
            return bool(torch.ops.mkldnn._is_mkldnn_bf16_supported())
        except Exception:
            return False

    @staticmethod
    def _choose_dtype(torch, pref, total_gb, free_gb, bf16_native):
        """(dtype, motivo) del Privacy Filter."""
        if pref == "fp32":
            return torch.float32, "scelta nelle impostazioni"
        if pref == "bf16":
            return torch.bfloat16, "scelta nelle impostazioni" + (
                "" if bf16_native else " (su questo processore senza BF16 nativo e' da 4 a 10 volte piu' lento)")
        if total_gb >= FP32_TOTAL_GB:
            return torch.float32, "massima velocita'"
        if not bf16_native and free_gb >= FP32_FREE_GB:
            return torch.float32, ("processore senza BF16 nativo: con la memoria libera disponibile FP32 e' da 4 a 10 "
                                   "volte piu' veloce")
        if bf16_native:
            return torch.bfloat16, "poca RAM: meta' memoria"
        return torch.bfloat16, ("poca RAM: meta' memoria, ma da 4 a 10 volte piu' lento su questo processore senza BF16 "
                                f"nativo; per la velocita' piena servono almeno {FP32_TOTAL_GB:.0f} GB di RAM (o "
                                f"{FP32_FREE_GB:.0f} GB liberi)")

    def _load_pf(self, pipeline, pf_path, dt):
        return pipeline(
            task="token-classification", model=pf_path, tokenizer=pf_path,
            aggregation_strategy="simple", device=self.device, model_kwargs={"dtype": dt},
        )

    # ------------------------------------------------------------------ inferenza testo
    def _run_pipe(self, pipe, texts, **kw):
        """Da chiamare con il lock del modello `pipe` gia' acquisito."""
        try:
            out = pipe(texts, **kw)
        except Exception as e:
            if self.device == "cuda" or str(getattr(pipe, "device", "")).startswith("cuda"):
                # Fallback automatico su CPU (es. memoria GPU esaurita). Si sposta solo il modello di questo lock:
                # l'altro passa alla CPU da solo al primo errore (spostarlo qui, mentre un altro thread lo usa, non
                # sarebbe sicuro); i modelli caricati da ora in poi restano sulla CPU.
                self.log("ATTENZIONE: errore GPU, passaggio automatico alla CPU.")
                pipe.model = pipe.model.to("cpu")
                pipe.device = self.torch.device("cpu")
                self.device = "cpu"
            elif self.precision == "bf16" and pipe is self.pf:
                # Operazione non disponibile in BF16 su questa CPU (es. testi con forme insolite): si passa a FP32
                self.log(f"ATTENZIONE: errore del modello in BF16 ({type(e).__name__}: {e}): passaggio automatico a FP32.")
                self.pf.model = self.pf.model.to(self.torch.float32)
                self.precision = "fp32"
                self.info["precision"] = "fp32"
            else:
                raise
            out = pipe(texts, **kw)
        if len(texts) == 1 and out and isinstance(out[0], dict):
            out = [out]
        return out

    def classify_many(self, texts, settings, cancel=None):
        """Per ogni testo restituisce gli span grezzi dei modelli: [(start, end, gruppo, score)]."""
        cancel = cancel or NO_CANCEL
        results = [[] for _ in texts]
        self._ensure_privacy_filter(settings)
        use_pf = bool(settings.get("enable_model_velvet", True)) and self.pf is not None
        use_ita = bool(settings.get("enable_model_italian_ner", True)) and (self.ita_onnx is not None or self.ita is not None)
        if not (use_pf or use_ita):
            return results
        thr = float(settings.get("ai_threshold", 0.0) or 0.0)
        flags = f"{int(use_pf)}{int(use_ita)}"

        pending = []
        for ti, text in enumerate(texts):
            if not isinstance(text, str) or not text.strip():
                continue
            for a, b, klo, khi in make_chunks(text):
                chunk = text[a:b]
                if not chunk.strip():
                    continue
                key = hashlib.sha1((flags + "\x00" + chunk).encode("utf-8", "surrogatepass")).hexdigest()
                with self._cache_lock:
                    cached = self._cache.get(key)
                    if cached is not None:
                        self._cache.move_to_end(key)
                if cached is not None:
                    self._emit(results[ti], cached, a, klo, khi, thr)
                else:
                    pending.append((ti, a, klo, khi, chunk, key))

        batch = 8
        for i in range(0, len(pending), batch):
            cancel.check()
            group = pending[i:i + batch]
            chunks = [g[4] for g in group]
            ita_future = None
            if use_ita and self.ita_onnx is not None:
                # ONNX Runtime (C++, rilascia il GIL, sicuro fra thread) in parallelo al Privacy Filter sullo stesso
                # lotto: stessi blocchi e stesso modello, quindi risultati identici a prima, in meno tempo
                ita_future = self._ita_pool.submit(self.ita_onnx.predict, chunks)
            if use_pf:
                with self._pf_lock:
                    pf_out = self._run_pipe(self.pf, chunks, batch_size=PF_BATCH)
            else:
                pf_out = [[] for _ in chunks]

            if ita_future is not None:
                ita_out = ita_future.result()
            elif use_ita and self.ita is not None:
                with self._ita_pt_lock:
                    ita_out = self._run_pipe(self.ita, chunks, batch_size=len(chunks), stride=64)
            else:
                ita_out = [[] for _ in chunks]
            for (ti, a, klo, khi, chunk, key), po, io in zip(group, pf_out, ita_out):
                spans = []
                for r in po or []:
                    spans.append((int(r["start"]), int(r["end"]), str(r.get("entity_group", "PII")), float(r.get("score", 0.0)), 0))
                for r in io or []:
                    spans.append((int(r["start"]), int(r["end"]), str(r.get("entity_group", "PII")), float(r.get("score", 0.0)), 1))
                with self._cache_lock:
                    self._cache[key] = spans
                    if len(self._cache) > self._cache_max:
                        self._cache.popitem(last=False)
                self._emit(results[ti], spans, a, klo, khi, thr)
        return results

    @staticmethod
    def _emit(out, spans, offset, klo, khi, thr):
        for s, e, g, sc, src in spans:
            gs = s + offset
            if gs < klo or gs >= khi:
                continue
            if sc < (max(thr, ITA_MIN_SCORE) if src == 1 else thr):
                continue
            out.append((gs, e + offset, g, sc))

    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()

    # ------------------------------------------------------------------ OCR e visione
    def ocr(self, img_rgb):
        """[(box4punti, testo, confidenza)] su immagine numpy RGB."""
        if self.ocr_reader is None:
            return []
        with self._ocr_lock:
            return self.ocr_reader.readtext(img_rgb, detail=1, paragraph=False)

    def _face_detector(self):
        with self._load_lock:
            if self._face is None and "face" not in self._tried:
                self._tried.add("face")
                try:
                    import cv2
                    path = os.path.join(common.MODELS_DIR, "face-detection", "face_detection_yunet_2023mar.onnx")
                    if os.path.exists(path) and hasattr(cv2, "FaceDetectorYN"):
                        self._face = cv2.FaceDetectorYN.create(path, "", (320, 320), 0.6, 0.3, 5000)
                except Exception as e:
                    self.log(f"Avviso: rilevatore volti non disponibile ({e}).")
            return self._face

    def _hf_detector(self, name, folder):
        attr = "_sig" if name == "sig" else "_plate"
        with self._load_lock:
            if getattr(self, attr) is None and name not in self._tried:
                self._tried.add(name)
                try:
                    from transformers import pipeline
                    path = os.path.join(common.MODELS_DIR, folder)
                    if os.path.isdir(path) and os.listdir(path):
                        setattr(self, attr, pipeline(
                            "object-detection", model=path, device=self.device,
                            model_kwargs={"dtype": self.torch.float32},
                        ))
                except Exception as e:
                    self.log(f"Avviso: modello {folder} non disponibile ({e}).")
            return getattr(self, attr)

    def detect_faces(self, img_rgb):
        """Riquadri (x0, y0, x1, y1, score) dei volti, con margine del 15%."""
        import cv2
        with self._face_lock:
            det = self._face_detector()
            if det is None:
                return []
            h, w = img_rgb.shape[:2]
            scale = 1.0
            img = img_rgb
            if max(h, w) > 1600:
                scale = 1600.0 / max(h, w)
                img = cv2.resize(img_rgb, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
            bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            det.setInputSize((bgr.shape[1], bgr.shape[0]))
            _, faces = det.detect(bgr)
        out = []
        if faces is not None:
            for f in faces:
                x, y, fw, fh = (float(f[0]) / scale, float(f[1]) / scale, float(f[2]) / scale, float(f[3]) / scale)
                mx, my = fw * 0.15, fh * 0.15
                out.append((x - mx, y - my, x + fw + mx, y + fh + my, float(f[-1])))
        return out

    def _detect_objects(self, name, folder, pil_img, min_score):
        with self._det_locks[name]:
            det = self._hf_detector(name, folder)
            if det is None:
                return []
            preds = det(pil_img)
        out = []
        for p in preds or []:
            sc = float(p.get("score", 0.0))
            if sc >= min_score:
                b = p["box"]
                out.append((float(b["xmin"]), float(b["ymin"]), float(b["xmax"]), float(b["ymax"]), sc))
        return out

    def detect_signatures(self, pil_img):
        return self._detect_objects("sig", "signature-detection", pil_img, 0.55)

    def detect_plates(self, pil_img):
        return self._detect_objects("plate", "plate-detection", pil_img, 0.65)
