"""File audio (MP3, WAV, M4A, OGG, FLAC e altri): metadati incorporati e trascrizione del parlato, bonificati.

Il parlato viene trascritto in locale dal motore (germano/speech.py: Whisper, offline) in segmenti con l'istante di
inizio; i metadati incorporati (tag ID3 degli MP3, commenti Vorbis di OGG/FLAC, atomi dei file M4A, INFO dei WAV:
titolo, artista, album, commento, data, posizione...) si leggono dal contenitore. Testo trascritto e metadati
passano dallo stesso filtro di privacy dei documenti (Privacy Filter, Italian NER, regole validate, Sistema 2) e i
dati trovati finiscono nel Vault come per ogni altro formato.

In uscita NON c'e' un file audio: c'e' la trascrizione bonificata «<nome>.trascrizione.txt» (UTF-8), con
un'intestazione (durata, lingua, formato, metadati) e una riga per segmento preceduta dal tempo [hh:mm:ss].
L'audio originale resta nella cartella processed: la voce e' essa stessa un dato personale e non viene modificata.
"""
import os
import time

from .. import common
from ..analyzer import Unit, apply_replacements
from . import ProcessingError

OUT_SUFFIX = ".trascrizione.txt"
# Metadati mostrati nella trascrizione (ordine e nome italiano). Quelli che indicano una persona diventano per
# intero un'etichetta, come gli autori dei documenti; gli altri passano dal filtro come testo normale.
_TAG_LABELS = (
    ("title", "Titolo"), ("inam", "Titolo"), ("com.apple.quicktime.title", "Titolo"),
    ("artist", "Artista"), ("iart", "Artista"), ("com.apple.quicktime.artist", "Artista"),
    ("album_artist", "Artista dell'album"), ("albumartist", "Artista dell'album"),
    ("author", "Autore"), ("com.apple.quicktime.author", "Autore"), ("composer", "Compositore"),
    ("performer", "Interprete"), ("lyricist", "Autore del testo"), ("conductor", "Direttore"),
    ("owner", "Proprietario"), ("encoded_by", "Codificato da"),
    ("album", "Album"), ("show", "Programma"), ("grouping", "Gruppo"), ("episode_id", "Episodio"),
    ("subject", "Oggetto"), ("isbj", "Oggetto"), ("keywords", "Parole chiave"), ("ikey", "Parole chiave"),
    ("genre", "Genere"), ("track", "Traccia"), ("disc", "Disco"),
    ("date", "Data"), ("year", "Anno"), ("creation_time", "Data di creazione"),
    ("location", "Posizione"), ("location-eng", "Posizione"), ("com.apple.quicktime.location.iso6709", "Posizione"),
    ("comment", "Commento"), ("icmt", "Commento"), ("com.apple.quicktime.comment", "Commento"),
    ("description", "Descrizione"), ("com.apple.quicktime.description", "Descrizione"), ("synopsis", "Sinossi"),
    ("copyright", "Copyright"), ("icop", "Copyright"), ("publisher", "Editore"), ("lyrics", "Testo"),
)
_PERSON_LABELS = {"Artista", "Artista dell'album", "Autore", "Compositore", "Interprete", "Autore del testo",
                  "Direttore", "Proprietario", "Codificato da"}
_PLACE_LABELS = {"Posizione"}                       # coordinate o luogo della registrazione: sempre oscurate
_CODEC_NAMES = {"mp3": "MP3", "mp3float": "MP3", "aac": "AAC", "vorbis": "Vorbis", "opus": "Opus", "flac": "FLAC",
                "alac": "ALAC", "wmav2": "WMA", "wmav1": "WMA", "wmapro": "WMA", "amrnb": "AMR", "amrwb": "AMR-WB",
                "ac3": "AC-3"}


def _clock(seconds):
    s = max(0, int(float(seconds or 0)))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _format_line(fmt):
    codec = str(fmt.get("codec") or "")
    name = _CODEC_NAMES.get(codec) or ("PCM" if codec.startswith("pcm_") else codec.upper() or "audio")
    parts = [name]
    if fmt.get("sample_rate"):
        parts.append(f"{int(fmt['sample_rate']):,} Hz".replace(",", "."))
    ch = fmt.get("channels")
    if ch:
        parts.append("mono" if ch == 1 else ("stereo" if ch == 2 else f"{ch} canali"))
    if fmt.get("bit_rate"):
        parts.append(f"{round(int(fmt['bit_rate']) / 1000)} kb/s")
    return ", ".join(parts)


def tag_items(tags):
    """[(etichetta italiana, valore)] dei metadati da mostrare, senza doppioni."""
    out, seen = [], set()
    for key, label in _TAG_LABELS:
        value = (tags or {}).get(key)
        if not value:
            continue
        value = " ".join(str(value).split()) if label != "Testo" else str(value).strip()
        if not value or (label, value) in seen:
            continue
        seen.add((label, value))
        out.append((label, value))
    return out


def transcribe(path, ctx):
    """Trascrizione con il motore del contesto (locale o remoto). ProcessingError con un messaggio comprensibile."""
    fn = getattr(ctx.engine, "transcribe", None)
    if fn is None:
        raise ProcessingError("La trascrizione dei file audio richiede il motore IA di Germano (non e' disponibile "
                              "senza motore).")
    from ..speech import SpeechError
    try:
        return fn(path, ctx.settings, ctx.cancel, progress=ctx.report, extend=ctx.extend_deadline)
    except SpeechError as e:
        raise ProcessingError(str(e)) from None


def plain_text(result, with_times=True):
    """Testo della trascrizione (senza filtro): per gli allegati dell'Harness, che lo proteggono subito dopo."""
    lines = [f"{label}: {value}" for label, value in tag_items(result.get("tags"))]
    if lines:
        lines.append("")
    for start, _end, text in result.get("segments") or []:
        lines.append(f"[{_clock(start)}] {text}" if with_times else text)
    return "\n".join(lines).strip()


def process_audio(in_path, out_path, ctx):
    if not ctx.anonymize:
        raise ProcessingError("Un file audio non contiene etichette del Vault: non c'e' nulla da ripristinare.")
    t0 = time.time()
    result = transcribe(in_path, ctx)
    settings = ctx.settings
    person = "[PERSONA]" if settings.get("censor_person", True) else None
    place = "[INDIRIZZO]" if settings.get("censor_address", True) else None

    units, meta = [], []
    for label, value in tag_items(result.get("tags")):
        force = person if label in _PERSON_LABELS else (place if label in _PLACE_LABELS else None)
        units.append(Unit(value, context=f"{label}: ", force_label=force))
        meta.append(label)
    segments = result.get("segments") or []
    for _start, _end, text in segments:
        units.append(Unit(text))
    res = ctx.analyze(units) if units else []
    clean = [apply_replacements(u.text, r) for u, r in zip(units, res)]

    from ..speech import LANGUAGE_NAMES
    lang = result.get("language")
    asked = settings.get("speech_language") or "auto"
    head = ["TRASCRIZIONE AUTOMATICA - Germano AI (elaborata in locale, dati personali oscurati)",
            f"Durata: {_clock(result.get('duration'))}"
            + (f" (parlato: {_clock(result['speech'])})" if result.get("speech") else "")]
    if lang:
        prob = result.get("language_probability")
        how = "indicata nelle impostazioni" if asked != "auto" else (
            f"riconosciuta, {round(float(prob) * 100)}%" if prob else "riconosciuta")
        head.append(f"Lingua: {LANGUAGE_NAMES.get(lang, lang)} ({how})")
    head.append(f"Audio: {_format_line(result.get('format') or {})}")
    head.append(f"Modello: {result.get('model') or 'Whisper'}")
    lines = head + [""]
    if meta:
        lines.append("METADATI INCORPORATI")
        for label, value in zip(meta, clean[:len(meta)]):
            lines.append(f"{label}: {value}")
        lines.append("")
    lines.append("TRASCRIZIONE")
    if segments:
        for (start, _end, _text), text in zip(segments, clean[len(meta):]):
            lines.append(f"[{_clock(start)}] {text}")
    else:
        lines.append("(nessun parlato riconosciuto nella registrazione)")
    real_out = out_path + OUT_SUFFIX
    with open(real_out, "w", encoding="utf-8", newline="\r\n" if os.name == "nt" else "\n") as f:
        f.write("\n".join(lines) + "\n")

    name = getattr(ctx, "archive_label", None) or os.path.basename(in_path)
    name = str(name).encode("utf-8", "replace").decode("utf-8")
    summary = (f"Audio {name}: {_clock(result.get('duration'))} di registrazione, {len(segments)} segmenti trascritti"
               + (f" in {LANGUAGE_NAMES.get(lang, lang)}" if lang else "")
               + f", {len(meta)} metadati, {time.time() - t0:.0f} s. In uscita la trascrizione bonificata (l'audio "
               "originale resta in processed).")
    common.log(summary)
    ctx.shared.setdefault("audio_report", []).append({
        "word": "", "label": "[AUDIO]", "entity": "AUDIO", "score": 1.0, "file": name,
        "duration": round(float(result.get("duration") or 0), 1), "speech": round(float(result.get("speech") or 0), 1),
        "language": lang, "language_probability": result.get("language_probability"), "segments": len(segments),
        "metadata": len(meta), "format": _format_line(result.get("format") or {}), "model": result.get("model"),
        "seconds": round(time.time() - t0, 1), "note": summary})
    if not segments:
        ctx.note(f"Audio {name}: nessun parlato riconosciuto; la trascrizione contiene solo i metadati.")
    return real_out
