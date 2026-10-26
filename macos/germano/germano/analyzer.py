"""Analisi a "unita'" di testo (paragrafi, celle, campi) e applicazione delle sostituzioni.

- Anonimizzazione: le unita' vengono concatenate in blocchi (contesto + velocita'), analizzate con modelli
  e RegEx, poi le entita' trovate vengono propagate a tutte le altre occorrenze del documento.
- Ripristino: le etichette del vault ([PERSONA_1]) vengono sostituite con i dati reali.
Le sostituzioni sono (inizio, fine, testo) relative all'unita'.
"""
from bisect import bisect_right

from . import detect
from .vault import iter_tags

GROUP_TARGET_CHARS = 60000
UNIT_SEPARATOR = "\n"


class Unit:
    """Testo da analizzare. `force_label`: l'intero testo diventa un'etichetta (es. autore -> [PERSONA]).
    `sep`: separatore usato dopo l'unita' quando viene analizzata insieme alle successive
    (" | " tra celle della stessa riga, "\\n" tra paragrafi)."""

    __slots__ = ("text", "context", "force_label", "ocr", "sep")

    def __init__(self, text, context="", force_label=None, ocr=False, sep=None):
        self.text = text if isinstance(text, str) else ("" if text is None else str(text))
        self.context = context or ""
        self.force_label = force_label
        self.ocr = ocr
        self.sep = sep


def apply_replacements(text, repls):
    if not repls:
        return text
    out = text
    for s, e, rep in sorted(repls, key=lambda r: r[0], reverse=True):
        out = out[:s] + rep + out[e:]
    return out


class Segment:
    """Frammento di testo di un nodo (es. <w:t>). I frammenti non scrivibili (tab, a capo) restano intatti."""

    __slots__ = ("text", "setter", "writable")

    def __init__(self, text, setter=None, writable=True):
        self.text = text or ""
        self.setter = setter
        self.writable = writable and setter is not None


def segments_text(segments):
    return "".join(s.text for s in segments)


def apply_to_segments(segments, repls):
    """Applica sostituzioni (sul testo concatenato) ai singoli frammenti preservandone la formattazione:
    l'etichetta va nel primo frammento coinvolto, il resto dello span viene rimosso dagli altri."""
    if not repls:
        return False
    offs = []
    pos = 0
    for seg in segments:
        offs.append(pos)
        pos += len(seg.text)
    edits = {}
    for s, e, rep in repls:
        first = True
        idx = max(0, bisect_right(offs, s) - 1)
        while idx < len(segments) and offs[idx] < e:
            seg = segments[idx]
            a = max(s, offs[idx])
            b = min(e, offs[idx] + len(seg.text))
            if b > a and seg.writable:
                edits.setdefault(idx, []).append((a - offs[idx], b - offs[idx], rep if first else ""))
                first = False
            idx += 1
    for idx, lst in edits.items():
        seg = segments[idx]
        t = seg.text
        for a, b, rep in sorted(lst, key=lambda x: x[0], reverse=True):
            t = t[:a] + rep + t[b:]
        seg.text = t
        seg.setter(t)
    return bool(edits)


class Anonymizer:
    def __init__(self, ctx):
        self.ctx = ctx

    def run(self, units, batch_context=True):
        ctx = self.ctx
        settings = ctx.settings
        n = len(units)
        spans_per_unit = [[] for _ in range(n)]
        todo = [i for i, u in enumerate(units) if u.force_label is None and u.text and u.text.strip()]

        if batch_context:
            groups, cur, size = [], [], 0
            for i in todo:
                L = len(units[i].text) + len(units[i].context) + 1
                if cur and size + L > GROUP_TARGET_CHARS:
                    groups.append(cur)
                    cur, size = [], 0
                cur.append(i)
                size += L
            if cur:
                groups.append(cur)
            for gi, grp in enumerate(groups):
                ctx.check()
                if len(groups) > 3:
                    ctx.report(f"analisi testo {gi + 1}/{len(groups)}")
                self._analyze_group(units, grp, spans_per_unit)
        else:
            for grp_start in range(0, len(todo), 64):
                ctx.check()
                grp = todo[grp_start:grp_start + 64]
                texts = [units[i].text for i in grp]
                raws = ctx.classify_many(texts)
                for i, raw in zip(grp, raws):
                    spans_per_unit[i] = detect.detect(units[i].text, raw, settings, ocr=units[i].ocr)

        # Propagazione delle entita' a tutte le occorrenze del documento (indice condiviso tra le chiamate
        # dello stesso documento: es. un nome letto nel testo digitale viene oscurato anche nelle scansioni).
        prop = getattr(ctx, "propagator", None) or detect.Propagator()
        for i in todo:
            t = units[i].text
            for sp in spans_per_unit[i]:
                prop.add(t[sp.start:sp.end], sp.label, sp.group, sp.key)
        if prop:
            for i in todo:
                t = units[i].text
                existing = spans_per_unit[i]
                extra = []
                for a, b, label, group, key in prop.find(t):
                    if any(not (b <= sp.start or a >= sp.end) for sp in existing):
                        continue
                    extra.append(detect.Span(a, b, group, label, key, 1.0, "propagation"))
                if extra:
                    spans_per_unit[i] = sorted(existing + extra, key=lambda x: x.start)

        use_indexed = bool(settings.get("enable_deanonymize", True))
        # Oscuramento ████ scelto da un client per i propri testi: irreversibile, nessuna voce nel Vault
        override = getattr(ctx, "label_override", None)
        vault = ctx.vault
        results = [[] for _ in range(n)]
        for i in range(n):
            u = units[i]
            if u.force_label is not None:
                word = u.text.strip()
                if not word or detect.ANY_TAG_RE.fullmatch(word):
                    continue
                label = override or (vault.label_for(word, u.force_label) if use_indexed else u.force_label)
                ctx.audit_add(word, label, "METADATA", 1.0)
                results[i] = [(0, len(u.text), label)]
                continue
            for sp in spans_per_unit[i]:
                word = u.text[sp.start:sp.end]
                label = override or (vault.label_for(word, sp.label) if use_indexed else sp.label)
                ctx.audit_add(word, label, sp.group, sp.score)
                results[i].append((sp.start, sp.end, label))
        return results

    def _analyze_group(self, units, grp, spans_per_unit):
        ctx = self.ctx
        parts = []
        starts, ends = [], []
        pos = 0
        for i in grp:
            u = units[i]
            if u.context:
                parts.append(u.context)
                pos += len(u.context)
            starts.append(pos)
            parts.append(u.text)
            pos += len(u.text)
            ends.append(pos)
            sep = u.sep or UNIT_SEPARATOR
            parts.append(sep)
            pos += len(sep)
        combined = "".join(parts)
        raw = ctx.classify_many([combined])[0]
        ocr = any(units[i].ocr for i in grp)
        spans = detect.detect(combined, raw, ctx.settings, ocr=ocr)
        for sp in spans:
            k = max(0, bisect_right(starts, sp.start) - 1)
            while k < len(grp) and starts[k] < sp.end:
                a = max(sp.start, starts[k])
                b = min(sp.end, ends[k])
                if b > a:
                    text = units[grp[k]].text
                    la, lb = detect.trim_span(text, a - starts[k], b - starts[k], sp.label)
                    if lb > la and (sp.source == "regex" or not detect.is_fragment(text, la, lb)):
                        spans_per_unit[grp[k]].append(detect.Span(la, lb, sp.group, sp.label, sp.key, sp.score, sp.source))
                k += 1
        for i in grp:
            spans_per_unit[i].sort(key=lambda x: x.start)


class Restorer:
    def __init__(self, ctx):
        self.ctx = ctx

    def run(self, units, batch_context=True):
        tag_map = self.ctx.tag_map
        results = []
        for u in units:
            reps = []
            for s, e, word in iter_tags(u.text, tag_map):
                reps.append((s, e, word))
                self.ctx.audit_add(u.text[s:e], "[RIPRISTINATO]", "RESTORED", 1.0)
            results.append(reps)
        return results
