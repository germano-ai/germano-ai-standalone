"""Processo separato della trascrizione vocale di Germano (Whisper con faster-whisper / CTranslate2, 100% offline).

Viene avviato dal motore (germano/speech.py) solo quando arriva un file audio e si chiude da solo quando il motore lo
ferma o termina. E' un processo a parte perche':
- il decodificatore audio (FFmpeg, tramite PyAV) legge file non fidati: un file malformato che lo manda in errore non
  ferma il motore di Germano;
- CTranslate2 e PyTorch portano ciascuno la propria libreria OpenMP: nello stesso processo possono andare in conflitto;
- alla chiusura tutta la memoria del modello vocale viene restituita al sistema.

Protocollo: una riga JSON per comando su stdin, una riga JSON per evento su stdout (UTF-8). Tutto quello che le
librerie scrivono su stdout viene deviato su stderr (registro state/trascrizione.log), cosi' il canale resta pulito.
  {"cmd": "probe", "path": ...}                -> {"ev": "probe", "ok": true, "format": {...}, "tags": {...}}
  {"cmd": "transcribe", "path": ..., "language": null | "it", "max_seconds": 14400}
        -> {"ev": "audio", ...}  {"ev": "info", ...}  {"ev": "segment", "start": s, "end": s, "text": "..."} ...
           {"ev": "done", "segments": n, "elapsed": s}
  errore di un comando                           -> {"ev": "error", "message": "...", "kind": "..."}
Questo file non importa nulla di Germano: usa solo la libreria standard, faster-whisper, PyAV e NumPy.
"""
import json
import os
import sys
import time

SAMPLE_RATE = 16000
# Registrazioni lunghe (turno 26): BatchedInferencePipeline di faster-whisper trascrive i segmenti del rilevatore di voce
# a lotti. Misurato sulle registrazioni sintetiche del turno 24 (284 s, i5-4570, 3 thread): 66 s invece di 107 s e
# errore di parola 11,6% invece di 13,3% (il modo in serie, condizionato sul testo precedente, perdeva anche una cifra
# di un numero di telefono). Sotto il minuto i due modi danno lo stesso testo: resta il modo in serie.
BATCH_MIN_SECONDS = 60
BATCH_SIZE = 8
PARAKEET_MAX_CHUNK_S = 24.0
PARAKEET_LANGS = frozenset({
    "it", "en", "fr", "de", "es", "pt", "nl", "ro", "pl", "uk", "ru", "hr",
    "sl", "bg", "hu", "cs", "sk", "sv", "da", "fi", "el", "et", "lt", "lv", "mt",
})
# etichette dei metadati utili (le altre sono tecniche: codificatore, marche del contenitore...)
TAG_KEYS = ("title", "artist", "album", "album_artist", "albumartist", "composer", "author", "performer", "lyricist",
            "conductor", "comment", "description", "synopsis", "date", "year", "creation_time", "genre", "track",
            "disc", "copyright", "publisher", "lyrics", "location", "location-eng", "encoded_by", "owner",
            "com.apple.quicktime.location.iso6709", "com.apple.quicktime.author", "com.apple.quicktime.artist",
            "com.apple.quicktime.description", "com.apple.quicktime.title", "com.apple.quicktime.comment",
            "icmt", "inam", "iart", "isbj", "ikey", "icop", "subject", "keywords", "show", "episode_id", "grouping")


def main():
    proto = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", newline="\n")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())          # le librerie non devono sporcare il protocollo
    sys.stdout = sys.stderr
    stdin = os.fdopen(sys.stdin.fileno(), "r", encoding="utf-8", newline="\n", closefd=False)

    def send(obj):
        proto.write(json.dumps(obj, ensure_ascii=False) + "\n")
        proto.flush()

    def log(msg):
        print(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg, file=sys.stderr, flush=True)

    state = {"model": None, "model_dir": None, "parakeet": None, "parakeet_dir": None}

    def load(cfg):
        if not cfg.get("model_dir"):
            return 0.0
        if state["model"] is not None and state["model_dir"] == cfg["model_dir"]:
            return 0.0
        t0 = time.time()
        from faster_whisper import WhisperModel
        state["model"] = WhisperModel(cfg["model_dir"], device="cpu", compute_type=cfg.get("compute_type") or "int8",
                                      cpu_threads=int(cfg.get("threads") or 0), num_workers=1, local_files_only=True)
        state["model_dir"] = cfg["model_dir"]
        log(f"modello vocale Whisper caricato in {time.time() - t0:.1f} s ({cfg['model_dir']})")
        return time.time() - t0

    def load_parakeet(cfg):
        pdir = cfg.get("parakeet_dir")
        if not pdir:
            return 0.0
        if state["parakeet"] is not None and state["parakeet_dir"] == pdir:
            return 0.0
        t0 = time.time()
        import onnx_asr
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, int(cfg.get("threads") or 2))
        opts.inter_op_num_threads = 1
        try:
            m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", path=pdir, quantization="int8",
                                    sess_options=opts, providers=["CPUExecutionProvider"])
        except TypeError:
            m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", path=pdir, quantization="int8")
        state["parakeet"] = m.with_timestamps()
        state["parakeet_dir"] = pdir
        log(f"modello vocale Parakeet v3 ONNX caricato in {time.time() - t0:.1f} s ({pdir})")
        return time.time() - t0

    def _parakeet_chunk_text(pcm_slice):
        """Trascrive un segmento audio con Parakeet v3 ONNX (spezzando in blocchi <=24 s se lungo)."""
        import numpy as np
        n = len(pcm_slice)
        if n < int(0.15 * SAMPLE_RATE):
            return ""
        max_n = int(PARAKEET_MAX_CHUNK_S * SAMPLE_RATE)
        parts = []
        pos = 0
        while pos < n:
            end = min(n, pos + max_n)
            if end < n:
                # Cerca il punto di minima energia negli ultimi 4 secondi del blocco per non tagliare parole
                win_start = max(pos + int(16 * SAMPLE_RATE), end - int(4 * SAMPLE_RATE))
                win = pcm_slice[win_start:end]
                step = int(0.05 * SAMPLE_RATE)
                if len(win) > step * 2:
                    frames = win[:len(win) - (len(win) % step)].reshape(-1, step)
                    energy = np.mean(frames * frames, axis=1)
                    end = win_start + int(np.argmin(energy)) * step + step // 2
            res = state["parakeet"].recognize(pcm_slice[pos:end], sample_rate=SAMPLE_RATE)
            txt = (res.text if hasattr(res, "text") else str(res)).strip()
            if txt:
                parts.append(txt)
            pos = max(end, pos + int(1.0 * SAMPLE_RATE))
        return " ".join(parts).strip()

    def _parakeet_segments(audio):
        """Modalita' solo Parakeet: trascrive in blocchi <=24 s e raggruppa per frasi/pause usando i timestamp."""
        import numpy as np
        n = len(audio)
        max_n = int(PARAKEET_MAX_CHUNK_S * SAMPLE_RATE)
        segs = []
        pos = 0
        while pos < n:
            end = min(n, pos + max_n)
            if end < n:
                win_start = max(pos + int(16 * SAMPLE_RATE), end - int(4 * SAMPLE_RATE))
                win = audio[win_start:end]
                step = int(0.05 * SAMPLE_RATE)
                if len(win) > step * 2:
                    frames = win[:len(win) - (len(win) % step)].reshape(-1, step)
                    energy = np.mean(frames * frames, axis=1)
                    end = win_start + int(np.argmin(energy)) * step + step // 2
            base_s = pos / float(SAMPLE_RATE)
            res = state["parakeet"].recognize(audio[pos:end], sample_rate=SAMPLE_RATE)
            toks = getattr(res, "tokens", None) or []
            ts = getattr(res, "timestamps", None) or []
            if toks and ts and len(toks) == len(ts):
                cur_txt, cur_start, cur_end = [], None, base_s
                for tok, t_rel in zip(toks, ts):
                    t_abs = base_s + float(t_rel)
                    if cur_start is None:
                        cur_start = t_abs
                    if cur_txt and (t_abs - cur_end >= 0.85 or (cur_txt[-1].rstrip().endswith((".", "!", "?")) and len("".join(cur_txt)) >= 60)):
                        joined = "".join(cur_txt).strip()
                        if joined:
                            segs.append((cur_start, max(cur_end, cur_start + 0.1), joined))
                        cur_txt, cur_start = [], t_abs
                    cur_txt.append(str(tok))
                    cur_end = t_abs
                if cur_txt:
                    joined = "".join(cur_txt).strip()
                    if joined:
                        segs.append((cur_start or base_s, end / float(SAMPLE_RATE), joined))
            else:
                txt = (res.text if hasattr(res, "text") else str(res)).strip()
                if txt:
                    segs.append((base_s, end / float(SAMPLE_RATE), txt))
            pos = max(end, pos + int(1.0 * SAMPLE_RATE))
        return segs

    def probe(path):
        import av
        with av.open(path, mode="r", metadata_errors="replace") as c:
            audio = next((s for s in c.streams if s.type == "audio"), None)
            if audio is None:
                raise ValueError("il file non contiene una traccia audio")
            duration = None
            if c.duration:
                duration = float(c.duration) / float(av.time_base)
            elif audio.duration and audio.time_base:
                duration = float(audio.duration * audio.time_base)
            cc = audio.codec_context
            fmt = {"container": c.format.name, "codec": cc.name, "sample_rate": cc.sample_rate,
                   "channels": getattr(cc, "channels", None) or len(getattr(cc.layout, "channels", ()) or ()),
                   "bit_rate": int(c.bit_rate or cc.bit_rate or 0) or None, "duration": duration,
                   "cover": any(s.type == "video" for s in c.streams)}
            tags = {}
            for source in (c.metadata, audio.metadata):
                for k, v in (source or {}).items():
                    key = str(k).strip().lower()
                    val = str(v).strip() if v is not None else ""
                    if val and key in TAG_KEYS and key not in tags:
                        tags[key] = val[:20000]
        return fmt, tags

    def _decode_bounded(path, max_seconds):
        import av
        import numpy as np
        max_samples = int((max_seconds + 6) * SAMPLE_RATE) if max_seconds else 0
        chunks = []
        total = 0
        resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        with av.open(path, metadata_errors="ignore") as container:
            audio_streams = [s for s in container.streams if s.type == "audio"]
            if not audio_streams:
                raise ValueError("il file non contiene una traccia audio")
            for frame in container.decode(audio_streams[0]):
                for rf in resampler.resample(frame):
                    arr = rf.to_ndarray().reshape(-1)
                    if arr.size:
                        chunks.append(arr.copy())
                        total += arr.size
                        if max_samples and total > max_samples:
                            return None, total / float(SAMPLE_RATE)
            for rf in resampler.resample(None):
                arr = rf.to_ndarray().reshape(-1)
                if arr.size:
                    chunks.append(arr.copy())
                    total += arr.size
                    if max_samples and total > max_samples:
                        return None, total / float(SAMPLE_RATE)
        if not chunks:
            return np.zeros(0, dtype=np.float32), 0.0
        # Conversione a float32 senza copie intermedie: «np.concatenate(chunks).astype(np.float32) / 32768.0» teneva
        # in memoria insieme i blocchi, la loro unione, la copia float32 e il risultato della divisione (12 byte per
        # campione: circa 2,7 GB per quattro ore di registrazione). Ora al massimo 6 byte per campione, che scendono
        # a 4 man mano che i blocchi vengono liberati; il risultato e' identico (32768 e' una potenza di due).
        pcm = np.empty(total, dtype=np.float32)
        pos = 0
        for k in range(len(chunks)):
            part = chunks[k]
            chunks[k] = None
            pcm[pos:pos + part.size] = part
            pos += part.size
        pcm *= np.float32(1.0 / 32768.0)
        return pcm, len(pcm) / float(SAMPLE_RATE)

    def transcribe(req):
        path = req["path"]
        fmt, tags = probe(path)
        max_seconds = float(req.get("max_seconds") or 0)
        if max_seconds and fmt.get("duration") and fmt["duration"] > max_seconds + 5:
            send({"ev": "error", "kind": "too_long", "duration": fmt["duration"],
                  "message": "registrazione troppo lunga"})
            return
        send({"ev": "probe", "ok": True, "format": fmt, "tags": tags})
        t0 = time.time()
        audio, seconds = _decode_bounded(path, max_seconds)
        if audio is None or (max_seconds and seconds > max_seconds + 5):
            send({"ev": "error", "kind": "too_long", "duration": seconds, "message": "registrazione troppo lunga"})
            return
        send({"ev": "audio", "duration": seconds, "decode_s": round(time.time() - t0, 2)})
        if seconds < 0.2:
            send({"ev": "done", "segments": 0, "elapsed": round(time.time() - t0, 2), "duration": seconds})
            return
        language = req.get("language") or None
        engine_pref = str(req.get("speech_engine") or "ensemble").lower()
        has_w = bool(req.get("model_dir"))
        has_p = bool(req.get("parakeet_dir"))
        lang_ok_p = (language is None) or (language in PARAKEET_LANGS)

        # Modalita' solo Parakeet (5x piu' veloce sulle 25 lingue europee)
        if engine_pref == "parakeet" and has_p and lang_ok_p:
            load_s = load_parakeet(req)
            send({"ev": "info", "language": language or "eu", "language_probability": 0.0,
                  "duration": seconds, "speech": seconds, "load_s": round(load_s, 2),
                  "mode": "parakeet", "model_label": "NVIDIA Parakeet TDT 0.6B v3 (INT8)"})
            n = 0
            for s0, e0, txt in _parakeet_segments(audio):
                n += 1
                send({"ev": "segment", "start": float(s0), "end": float(e0), "text": txt})
            send({"ev": "done", "segments": n, "elapsed": round(time.time() - t0, 2), "duration": seconds})
            return

        if not has_w and has_p:
            load_s = load_parakeet(req)
            send({"ev": "info", "language": language or "eu", "language_probability": 0.0,
                  "duration": seconds, "speech": seconds, "load_s": round(load_s, 2),
                  "mode": "parakeet", "model_label": "NVIDIA Parakeet TDT 0.6B v3 (INT8)"})
            n = 0
            for s0, e0, txt in _parakeet_segments(audio):
                n += 1
                send({"ev": "segment", "start": float(s0), "end": float(e0), "text": txt})
            send({"ev": "done", "segments": n, "elapsed": round(time.time() - t0, 2), "duration": seconds})
            return

        load_s = load(req)
        beam = int(req.get("beam_size") or 5)
        segments = info = None
        mode = "serie"
        if seconds >= BATCH_MIN_SECONDS and not req.get("no_batch"):
            try:
                from faster_whisper import BatchedInferencePipeline
                if state.get("batched_for") is not state["model"]:
                    state["batched"] = BatchedInferencePipeline(model=state["model"])
                    state["batched_for"] = state["model"]
                segments, info = state["batched"].transcribe(
                    audio, language=language, task="transcribe", beam_size=beam, batch_size=BATCH_SIZE,
                    vad_filter=True, vad_parameters={"min_silence_duration_ms": 500}, word_timestamps=False)
                mode = "a lotti"
            except Exception as e:                  # libreria senza il modo a lotti o errore all'avvio: in serie
                log(f"trascrizione a lotti non disponibile ({type(e).__name__}: {e}): si usa il modo in serie")
                segments = info = None
        if segments is None:
            segments, info = state["model"].transcribe(
                audio, language=language, task="transcribe", beam_size=beam, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500}, condition_on_previous_text=True,
                word_timestamps=False)
        det_lang = getattr(info, "language", None) or language
        use_ensemble = (engine_pref == "ensemble" and has_p and (det_lang in PARAKEET_LANGS))
        if use_ensemble:
            try:
                load_s += load_parakeet(req)
            except Exception as e:
                log(f"Avviso: Parakeet v3 non caricabile per ensemble ({type(e).__name__}: {e}): uso solo Whisper")
                use_ensemble = False
        model_lbl = ("Ensemble NVIDIA Parakeet TDT 0.6B v3 + Whisper small (INT8)"
                     if use_ensemble else "Whisper small (INT8)")
        send({"ev": "info", "language": det_lang, "language_probability": float(info.language_probability or 0),
              "duration": float(info.duration or seconds), "speech": float(getattr(info, "duration_after_vad", 0) or 0),
              "load_s": round(load_s, 2), "mode": ("ensemble+" + mode) if use_ensemble else mode,
              "model_label": model_lbl})
        n = 0
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            s0, e0 = float(seg.start), float(seg.end)
            alt_text = ""
            if use_ensemble:
                try:
                    a0 = max(0, int((s0 - 0.15) * SAMPLE_RATE))
                    a1 = min(len(audio), int((e0 + 0.15) * SAMPLE_RATE))
                    alt_text = _parakeet_chunk_text(audio[a0:a1])
                except Exception as e:
                    log(f"Avviso: segmento Parakeet non riuscito ({e})")
                    alt_text = ""
            n += 1
            ev = {"ev": "segment", "start": s0, "end": e0, "text": text}
            if alt_text:
                ev["alt_text"] = alt_text
            send(ev)
        send({"ev": "done", "segments": n, "elapsed": round(time.time() - t0, 2), "duration": seconds})

    log("processo vocale avviato (pid %d)" % os.getpid())
    send({"ev": "ready", "pid": os.getpid()})
    while True:
        line = stdin.readline()
        if not line:                       # il motore si e' chiuso: fine
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            send({"ev": "error", "message": "comando non valido", "kind": "protocol"})
            continue
        cmd = req.get("cmd")
        try:
            if cmd == "quit":
                break
            if cmd == "load":
                send({"ev": "loaded", "seconds": round(load(req), 2)})
            elif cmd == "probe":
                fmt, tags = probe(req["path"])
                send({"ev": "probe", "ok": True, "format": fmt, "tags": tags})
                send({"ev": "done", "segments": 0, "elapsed": 0})
            elif cmd == "transcribe":
                transcribe(req)
            else:
                send({"ev": "error", "message": "comando sconosciuto", "kind": "protocol"})
        except MemoryError:
            send({"ev": "error", "kind": "memory", "message": "memoria insufficiente per questa registrazione"})
        except Exception as e:             # file non leggibile, formato non riconosciuto, modello mancante...
            kind = "decode" if type(e).__module__.startswith("av") or isinstance(e, (ValueError, OSError)) else "engine"
            log(f"errore ({cmd}): {type(e).__name__}: {e}")
            send({"ev": "error", "kind": kind, "message": f"{type(e).__name__}: {e}"[:500]})
    log("processo vocale terminato")


if __name__ == "__main__":
    main()
