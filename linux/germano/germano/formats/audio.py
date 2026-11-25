"""File audio (MP3, WAV, M4A, OGG, FLAC e altri): metadati incorporati e trascrizione del parlato, bonificati.

Il parlato viene trascritto in locale dal motore (germano/speech.py: ensemble NVIDIA Parakeet TDT v3 ONNX + Whisper
offline) in segmenti con l'istante di inizio; i metadati incorporati (tag ID3 degli MP3, commenti Vorbis di OGG/FLAC,
atomi dei file M4A, INFO dei WAV: titolo, artista, album, commento, data, posizione...) si leggono dal contenitore.
Testo trascritto e metadati passano dallo stesso filtro di privacy dei documenti (Privacy Filter ONNX, Italian NER,
GLiNER2-PII, regole validate, Sistema 2) e i dati trovati finiscono nel Vault come per ogni altro formato.

In modalita' Ensemble, quando entrambi i motori (Parakeet v3 e Whisper) producono un trascritto per lo stesso
segmento, Germano analizza entrambi, sceglie la trascrizione piu' accurata e applica una cross-redazione fuzzy dei
dati personali individuati dal trascritto complementare (es. cifre o nomi propri compresi meglio da uno dei due).

In uscita NON c'e' un file audio: c'e' la trascrizione bonificata «<nome>.trascrizione.txt» (UTF-8), con
un'intestazione (durata, lingua, formato, metadati) e una riga per segmento preceduta dal tempo [hh:mm:ss].
L'audio originale resta nella cartella processed: la voce e' essa stessa un dato personale e non viene modificata.
"""
import difflib
import os
import re
import time

from .. import common
from ..analyzer import Unit, apply_replacements
from ..detect import CATEGORY_MAP, regex_spans
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


_TAG_PLACEHOLDER_RE = re.compile(r"\[[A-Z0-9_/.]+(?:_\d+)?\]|█+")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9@._-]+")
_DIGIT_SEQ_RE = re.compile(r"(?:\+?\d[\d\s.\-/()]{4,}\d)")


def _digits_only(text):
    return "".join(ch for ch in str(text) if ch.isdigit())


def _group_label_enabled(group, settings):
    label, key = CATEGORY_MAP.get(str(group or ""), ("[DATO_PERSONALE]", None))
    if key and not settings.get(key, True):
        return None
    return label


def _probe_spans(text, ner_spans, settings):
    """Elenco di (start, end, group, label, strong) per valutare un candidato di trascrizione senza toccare il Vault."""
    thr = float(settings.get("ai_threshold", 0.0) or 0.0)
    out = []
    if settings.get("enable_regex", True):
        for sp in regex_spans(text, settings):
            lab = _group_label_enabled(sp.group, settings)
            if lab:
                out.append((sp.start, sp.end, sp.group, lab, True))
    for s, e, grp, sc in ner_spans or []:
        if float(sc) < thr:
            continue
        lab = _group_label_enabled(grp, settings)
        if lab and 0 <= s < e <= len(text):
            out.append((int(s), int(e), str(grp), lab, False))
    return out


def _alt_text_of(item):
    if isinstance(item, (list, tuple)):
        return str(item[2] if len(item) >= 3 else (item[-1] if item else ""))
    return str(item or "")


def _select_ensemble_segments(segments, alt_segments, ctx):
    """Sceglie per ogni segmento la trascrizione migliore fra Whisper e Parakeet v3 e restituisce
    (chosen_segments, complement_hints) dove complement_hints[i] = [(valore, group, label)] trovati solo nell'altro."""
    if not alt_segments or len(alt_segments) != len(segments):
        return segments, [[] for _ in segments]
    pairs = []
    for i, ((s, e, w_txt), alt_item) in enumerate(zip(segments, alt_segments)):
        w_t = (w_txt or "").strip()
        p_t = _alt_text_of(alt_item).strip()
        if p_t and p_t != w_t:
            pairs.append((i, s, e, w_t, p_t))
    if not pairs:
        return segments, [[] for _ in segments]

    # Una sola chiamata a classify_many: i risultati entrano nella cache del motore, quindi ctx.analyze() dopo e' a costo 0.
    probe_texts = [w for _, _, _, w, _ in pairs] + [p for _, _, _, _, p in pairs]
    ner_all = ctx.classify_many(probe_texts)
    half = len(pairs)
    chosen = list(segments)
    hints = [[] for _ in segments]
    settings = ctx.settings
    for idx, (i, s, e, w_t, p_t) in enumerate(pairs):
        w_spans = _probe_spans(w_t, ner_all[idx], settings)
        p_spans = _probe_spans(p_t, ner_all[half + idx], settings)
        w_strong = sum(1 for x in w_spans if x[4])
        p_strong = sum(1 for x in p_spans if x[4])
        w_tot = len(w_spans)
        p_tot = len(p_spans)
        # Preferiamo Parakeet v3 se trova piu' entita' regex/validate, oppure a parita' di regex trova piu' PII con
        # lunghezza coerente (>= 65%), oppure a parita' totale ha lunghezza >= 85% (minore WER su cifre e nomi).
        use_parakeet = (
            p_strong > w_strong
            or (p_strong == w_strong and p_tot > w_tot and len(p_t) >= 0.65 * max(1, len(w_t)))
            or (p_strong == w_strong and p_tot == w_tot and len(p_t) >= 0.85 * max(1, len(w_t)))
        )
        if use_parakeet:
            chosen[i] = (s, e, p_t)
            other_txt, other_spans = w_t, w_spans
        else:
            chosen[i] = (s, e, w_t)
            other_txt, other_spans = p_t, p_spans
        seg_hints = []
        seen = set()
        for a, b, grp, lab, _strong in other_spans:
            val = other_txt[a:b].strip()
            if len(val) < 4:
                continue
            key = (val.lower(), lab)
            if key not in seen:
                seen.add(key)
                seg_hints.append((val, grp, lab))
        hints[i] = seg_hints
    return chosen, hints


def _apply_complement_redaction(clean_text, hints, ctx):
    """Cross-redazione fuzzy: oscura eventuali PII riconosciuti solo dal motore complementare (es. cifre/nomi)."""
    if not hints or not clean_text:
        return clean_text
    # Evita di toccare i segnaposto gia' inseriti ([PERSONA_1], [TELEFONO_2], ████)
    masked_ranges = [(m.start(), m.end()) for m in _TAG_PLACEHOLDER_RE.finditer(clean_text)]

    def _overlaps_masked(a, b, extra):
        for x, y in masked_ranges:
            if a < y and b > x:
                return True
        for x, y, _v, _g, _l in extra:
            if a < y and b > x:
                return True
        return False

    extra_repl = []
    words = [(m.start(), m.end(), m.group(0)) for m in _WORD_RE.finditer(clean_text)]
    digit_matches = [(m.start(), m.end(), m.group(0), _digits_only(m.group(0))) for m in _DIGIT_SEQ_RE.finditer(clean_text)]

    for val, grp, lab in hints:
        val_digits = _digits_only(val)
        matched = False
        # 1) Match su sequenze numeriche lunghe (telefoni, P.IVA, conti, codici): tollera spazi/trattini o 1 cifra errata
        if len(val_digits) >= 6:
            for a, b, orig, cand_digits in digit_matches:
                if len(cand_digits) < 6 or _overlaps_masked(a, b, extra_repl):
                    continue
                ratio = difflib.SequenceMatcher(None, val_digits, cand_digits).ratio()
                if ratio >= 0.78:
                    extra_repl.append((a, b, orig, grp, lab))
                    matched = True
                    break
        if matched:
            continue
        # 2) Match testuale fuzzy su nomi/enti/luoghi (>= 5 caratteri alfabetici)
        alpha = "".join(ch for ch in val if ch.isalpha())
        if len(alpha) < 5:
            continue
        n_toks = max(1, min(4, len(_WORD_RE.findall(val))))
        min_ratio = 0.72 if len(alpha) >= 8 else 0.80
        best = None
        for idx in range(len(words)):
            end_idx = idx + n_toks
            if end_idx > len(words):
                break
            a, b = words[idx][0], words[end_idx - 1][1]
            if _overlaps_masked(a, b, extra_repl):
                continue
            cand = clean_text[a:b]
            ratio = difflib.SequenceMatcher(None, val.lower(), cand.lower()).ratio()
            if ratio >= min_ratio and (best is None or ratio > best[0]):
                best = (ratio, a, b, cand)
        if best is not None:
            _r, a, b, cand = best
            extra_repl.append((a, b, cand, grp, lab))

    if not extra_repl:
        return clean_text
    extra_repl.sort(key=lambda x: x[0])
    deanon = bool(ctx.settings.get("enable_deanonymize", True))
    override = getattr(ctx, "label_override", None)
    out_parts = []
    pos = 0
    for a, b, orig, grp, lab in extra_repl:
        out_parts.append(clean_text[pos:a])
        if override:
            rep = override
        elif deanon and ctx.vault is not None:
            rep = ctx.vault.label_for(orig, lab)
        else:
            rep = lab
        ctx.audit.append({"word": orig, "label": rep, "entity": grp, "score": 0.90, "source": "audio_ensemble"})
        out_parts.append(rep)
        pos = b
    out_parts.append(clean_text[pos:])
    return "".join(out_parts)


def plain_text(result, with_times=True):
    """Testo della trascrizione (senza filtro): per gli allegati dell'Harness, che lo proteggono subito dopo."""
    lines = [f"{label}: {value}" for label, value in tag_items(result.get("tags"))]
    if lines:
        lines.append("")
    segs = result.get("segments") or []
    alt_segs = result.get("alt_segments") or []
    if alt_segs and len(alt_segs) == len(segs):
        chosen = []
        for (s, e, w_t), alt_item in zip(segs, alt_segs):
            wt, pt = (w_t or "").strip(), _alt_text_of(alt_item).strip()
            if pt and (len(_digits_only(pt)) > len(_digits_only(wt)) or len(pt) >= 0.85 * max(1, len(wt))):
                chosen.append((s, e, pt))
            else:
                chosen.append((s, e, wt))
        segs = chosen
    for start, _end, text in segs:
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
    raw_segments = result.get("segments") or []
    alt_segments = result.get("alt_segments") or []
    segments, hints = _select_ensemble_segments(raw_segments, alt_segments, ctx)
    for _start, _end, text in segments:
        units.append(Unit(text))
    res = ctx.analyze(units) if units else []
    clean = [apply_replacements(u.text, r) for u, r in zip(units, res)]
    if any(hints):
        for i, seg_hints in enumerate(hints):
            if seg_hints:
                clean[len(meta) + i] = _apply_complement_redaction(clean[len(meta) + i], seg_hints, ctx)

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
