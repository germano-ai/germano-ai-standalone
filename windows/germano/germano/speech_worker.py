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

    state = {"model": None, "model_dir": None}

    def load(cfg):
        if state["model"] is not None and state["model_dir"] == cfg["model_dir"]:
            return 0.0
        t0 = time.time()
        from faster_whisper import WhisperModel
        state["model"] = WhisperModel(cfg["model_dir"], device="cpu", compute_type=cfg.get("compute_type") or "int8",
                                      cpu_threads=int(cfg.get("threads") or 0), num_workers=1, local_files_only=True)
        state["model_dir"] = cfg["model_dir"]
        log(f"modello vocale caricato in {time.time() - t0:.1f} s ({cfg['model_dir']})")
        return time.time() - t0

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

    def transcribe(req):
        from faster_whisper import decode_audio
        path = req["path"]
        fmt, tags = probe(path)
        send({"ev": "probe", "ok": True, "format": fmt, "tags": tags})
        max_seconds = float(req.get("max_seconds") or 0)
        if max_seconds and fmt.get("duration") and fmt["duration"] > max_seconds + 5:
            send({"ev": "error", "kind": "too_long", "duration": fmt["duration"],
                  "message": "registrazione troppo lunga"})
            return
        t0 = time.time()
        audio = decode_audio(path, sampling_rate=SAMPLE_RATE)
        seconds = len(audio) / float(SAMPLE_RATE)
        if max_seconds and seconds > max_seconds + 5:
            send({"ev": "error", "kind": "too_long", "duration": seconds, "message": "registrazione troppo lunga"})
            return
        send({"ev": "audio", "duration": seconds, "decode_s": round(time.time() - t0, 2)})
        if seconds < 0.2:
            send({"ev": "done", "segments": 0, "elapsed": round(time.time() - t0, 2), "duration": seconds})
            return
        load_s = load(req)
        segments, info = state["model"].transcribe(
            audio, language=req.get("language") or None, task="transcribe", beam_size=int(req.get("beam_size") or 5),
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 500}, condition_on_previous_text=True,
            word_timestamps=False)
        send({"ev": "info", "language": info.language, "language_probability": float(info.language_probability or 0),
              "duration": float(info.duration or seconds), "speech": float(getattr(info, "duration_after_vad", 0) or 0),
              "load_s": round(load_s, 2)})
        n = 0
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            n += 1
            send({"ev": "segment", "start": float(seg.start), "end": float(seg.end), "text": text})
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
