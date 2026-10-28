"""Motore IA: caricamento modelli locali, classificazione a blocchi con cache, OCR e visione artificiale.

Tutte le chiamate ai modelli sono serializzate da un lock: i tokenizer "fast" di HuggingFace e EasyOCR
non sono thread-safe e il demone serve in parallelo la cartella input/ e il Proxy API.
"""
import hashlib
import os
import threading
import time
from collections import OrderedDict

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
        self.lock = threading.RLock()
        self.torch = None
        self.device = "cpu"
        self.precision = "fp32"
        self.pf = None
        self.ita = None
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

        pf_path = os.path.join(common.MODELS_DIR, "privacy-filter")
        if not os.path.isdir(pf_path) or not os.listdir(pf_path):
            raise FileNotFoundError(f"Modello locale non trovato in {pf_path}")
        t = time.time()
        self.log("Caricamento modello Privacy Filter 1.5B (100% offline)...")
        try:
            self.pf = self._load_pf(pipeline, pf_path, dt)
            if dt == torch.bfloat16:
                t2 = time.time()
                self.pf(SELF_TEST_TEXT)       # alcune CPU o librerie non hanno tutte le operazioni in BF16
                self.log(f"Prova del modello in BF16 riuscita ({time.time() - t2:.1f} s).")
        except Exception as e:
            if dt != torch.bfloat16:
                raise
            self.log(f"ATTENZIONE: BF16 non utilizzabile su questo processore ({type(e).__name__}: {e}): ripiego "
                     "automatico su FP32.")
            self.pf = None
            import gc
            gc.collect()
            dt = torch.float32
            self.pf = self._load_pf(pipeline, pf_path, dt)
        self.precision = "bf16" if dt == torch.bfloat16 else "fp32"
        self.log(f"Privacy Filter pronto in {time.time() - t:.0f}s.")

        ita_path = os.path.join(common.MODELS_DIR, "italian-ner-xxl")
        if os.path.isdir(ita_path) and os.listdir(ita_path):
            try:
                t = time.time()
                self.log("Caricamento modello specialistico Italian_NER_XXL_v2 (58 categorie)...")
                self.ita = pipeline(
                    task="token-classification", model=ita_path, tokenizer=ita_path,
                    aggregation_strategy="simple", device=self.device, model_kwargs={"dtype": torch.float32},
                )
                self.log(f"Italian NER pronto in {time.time() - t:.0f}s.")
            except Exception as e:
                self.log(f"Avviso: Italian_NER_XXL non caricato ({e}).")
                self.ita = None

        self.log("Caricamento motore OCR (EasyOCR locale)...")
        try:
            import easyocr
            ocr_dir = os.path.join(common.MODELS_DIR, "easyocr")
            self.ocr_reader = easyocr.Reader(
                ["it", "en"], gpu=(self.device == "cuda"), verbose=False, download_enabled=False,
                model_storage_directory=ocr_dir, user_network_directory=ocr_dir,
            )
            self.log("Motore OCR caricato.")
        except Exception as e:
            self.log(f"Avviso: OCR non disponibile ({e}).")
            self.ocr_reader = None

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
            "italian_ner": self.ita is not None,
            "ocr": self.ocr_reader is not None,
        }

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
        try:
            out = pipe(texts, **kw)
        except Exception as e:
            if self.device == "cuda":
                # Fallback automatico su CPU (es. memoria GPU esaurita)
                self.log("ATTENZIONE: errore GPU, passaggio automatico alla CPU.")
                for p in (self.pf, self.ita):
                    if p is not None:
                        p.model = p.model.to("cpu")
                        p.device = self.torch.device("cpu")
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
        use_pf = bool(settings.get("enable_model_velvet", True)) and self.pf is not None
        use_ita = bool(settings.get("enable_model_italian_ner", True)) and self.ita is not None
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
                with self.lock:
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
            with self.lock:
                pf_out = self._run_pipe(self.pf, chunks, batch_size=PF_BATCH) if use_pf else [[] for _ in chunks]
                ita_out = (
                    self._run_pipe(self.ita, chunks, batch_size=len(chunks), stride=64) if use_ita else [[] for _ in chunks]
                )
            for (ti, a, klo, khi, chunk, key), po, io in zip(group, pf_out, ita_out):
                spans = []
                for r in po or []:
                    spans.append((int(r["start"]), int(r["end"]), str(r.get("entity_group", "PII")), float(r.get("score", 0.0)), 0))
                for r in io or []:
                    spans.append((int(r["start"]), int(r["end"]), str(r.get("entity_group", "PII")), float(r.get("score", 0.0)), 1))
                with self.lock:
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
        with self.lock:
            self._cache.clear()

    # ------------------------------------------------------------------ OCR e visione
    def ocr(self, img_rgb):
        """[(box4punti, testo, confidenza)] su immagine numpy RGB."""
        if self.ocr_reader is None:
            return []
        with self.lock:
            return self.ocr_reader.readtext(img_rgb, detail=1, paragraph=False)

    def _face_detector(self):
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
        with self.lock:
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
        with self.lock:
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
