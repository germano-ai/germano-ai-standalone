"""Modelli locali del Sistema 1 in ONNX Runtime (Italian NER XXL, Privacy Filter Q4, GLiNER2-PII):
esecuzione in C++ senza GIL (parallela fra thread) e con memoria ridotta rispetto a PyTorch.

- OnnxTokenClassifier (Italian_NER_XXL_v2): stesse entita' di PyTorch (aggregation_strategy="simple", stride=64).
- OnnxPrivacyFilter (openai/privacy-filter onnx/model_q4.onnx): classificazione BIOES (B-/I-/E-/S-) in Q4 (~917 MB su
  disco, ~645 MB di RAM contro ~5,3 GB in PyTorch FP32, piu' veloce su CPU).
- OnnxGLiNER2 (yethdev/gliner2-pii-onnx): GLiNER2-PII multilingua (205M, 7 lingue, 31+ categorie PII + categorie
  personalizzate zero-shot definite dall'utente a runtime) su solo ONNX Runtime + tokenizers (zero dipendenze extra).
"""
import json
import os
import re
import sys
import threading
import unicodedata

import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None

try:
    from transformers import AutoTokenizer
except ImportError:
    AutoTokenizer = None

try:
    from tokenizers import Tokenizer as _HfTokenizer
except ImportError:
    _HfTokenizer = None

MAX_LENGTH = 512
STRIDE = 64

# Categorie predefinite ad alta precisione di GLiNER2-PII mappate su detect.CATEGORY_MAP (esclusa 'organization'
# generica che sui testi normativi italiani tocca riferimenti a leggi/enti pubblici).
GLINER2_DEFAULT_LABELS = (
    "person", "full_name", "date_of_birth", "sensitive_date",
    "email", "phone_number", "address", "street_address", "city", "postal_code",
    "government_id", "national_id_number", "passport_number", "drivers_license_number",
    "license_number", "tax_id", "tax_number",
    "iban", "bank_account", "account_number", "payment_card", "card_number", "card_cvv",
    "ip_address", "password", "secret", "api_key", "access_token",
    "medical_condition", "medication", "license_plate",
)

GLINER2_TO_GERMANO = {
    "person": "private_person", "full_name": "private_person",
    "date_of_birth": "DATA_NASCITA", "sensitive_date": "private_date",
    "email": "private_email", "phone_number": "private_phone",
    "address": "private_address", "street_address": "private_address",
    "city": "LUOGO", "postal_code": "CODICE_POSTALE",
    "government_id": "plates_docs", "national_id_number": "cf_iva",
    "passport_number": "plates_docs", "drivers_license_number": "plates_docs", "license_number": "plates_docs",
    "tax_id": "cf_iva", "tax_number": "cf_iva",
    "iban": "account_number", "bank_account": "account_number", "account_number": "account_number",
    "payment_card": "account_number", "card_number": "account_number", "card_cvv": "account_number",
    "ip_address": "IP", "password": "secret", "secret": "secret", "api_key": "secret", "access_token": "secret",
    "medical_condition": "medical", "medication": "medicine", "license_plate": "plates_docs",
}

_COMBINING_MARKS = "".join(
    chr(c) for c in range(sys.maxunicode + 1) if unicodedata.category(chr(c)).startswith("M")
)
_GL2_WORD_RE = re.compile(
    rf"(?:https?://[^\s]+|www\.[^\s]+)|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{{2,}}|@[a-z0-9_]+|"
    rf"[\w{_COMBINING_MARKS}\u200c\u200d]+(?:[-_][\w{_COMBINING_MARKS}\u200c\u200d]+)*|\S",
    re.IGNORECASE,
)


def parse_custom_labels(raw):
    """Converte una stringa utente («numero pratica, codice cliente») in lista pulita di etichette (max 16)."""
    if not raw:
        return []
    parts = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"[,;\n]+", str(raw))]
    out, seen = [], set()
    for p in parts:
        if not p or len(p) < 2:
            continue
        p = p[:60]
        k = p.casefold()
        if k not in seen:
            seen.add(k)
            out.append(p)
        if len(out) >= 16:
            break
    return out


class OnnxTokenClassifier:
    """Classificatore di token per le entita' personali, raggruppamento B/I come la strategia «simple»."""

    def __init__(self, model_dir, onnx_filename=None, threads=4):
        if ort is None:
            raise RuntimeError("onnxruntime non installato.")
        if AutoTokenizer is None:
            raise RuntimeError("transformers.AutoTokenizer non disponibile.")
        self.model_dir = model_dir
        names = [onnx_filename] if onnx_filename else ["model.onnx", "model_fp32.onnx"]
        self.onnx_path = None
        for name in names:
            for cand in (os.path.join(model_dir, "onnx", name), os.path.join(model_dir, name)):
                if os.path.isfile(cand):
                    self.onnx_path = cand
                    break
            if self.onnx_path:
                break
        if not self.onnx_path:
            raise FileNotFoundError(f"Nessun modello ONNX valido trovato in {model_dir}")

        self.id2label = {}
        config_path = os.path.join(model_dir, "config.json")
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.id2label = {int(k): v for k, v in cfg.get("id2label", {}).items()}

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, int(threads))
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(self.onnx_path, opts, providers=["CPUExecutionProvider"])
        self.input_names = {inp.name for inp in self.session.get_inputs()}
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self._tok_lock = threading.Lock()

    def predict(self, texts):
        """Per ogni testo: lista di dict {entity_group, score, word, start, end} (offset nel testo originale)."""
        if not texts:
            return []
        with self._tok_lock:
            enc = self.tokenizer(
                list(texts), truncation=True, max_length=MAX_LENGTH, stride=STRIDE, return_overflowing_tokens=True,
                return_offsets_mapping=True, padding=True, return_tensors="np",
            )
        owners = enc["overflow_to_sample_mapping"] if "overflow_to_sample_mapping" in enc else np.arange(len(texts))
        lengths = enc["attention_mask"].sum(axis=1)
        per_text = [[] for _ in texts]
        # Una finestra alla volta con la sua lunghezza reale: su CPU il riempimento fino a 512 token costa piu' di
        # quanto renda raggruppare le finestre (misurato: gruppi da 8 piu' lenti delle finestre singole).
        for w in range(len(enc["input_ids"])):
            n = int(lengths[w])
            feed = {name: enc[name][w:w + 1, :n].astype(np.int64)
                    for name in ("input_ids", "attention_mask", "token_type_ids")
                    if name in self.input_names and name in enc}
            logits = self.session.run(None, feed)[0][0]
            shifted = np.exp(logits - np.max(logits, axis=-1, keepdims=True))   # softmax stabile
            probs = shifted / np.sum(shifted, axis=-1, keepdims=True)
            ti = int(owners[w])
            per_text[ti].append(self._window_entities(texts[ti], enc["offset_mapping"][w][:n],
                                                      np.argmax(probs, axis=-1), np.max(probs, axis=-1)))
        return [self._merge_windows(wins) for wins in per_text]

    def _window_entities(self, text, offsets, ids, scores):
        entities = []
        cur = None
        for i in range(len(ids)):
            start_char, end_char = int(offsets[i][0]), int(offsets[i][1])
            if start_char == end_char:                  # token speciali e riempimento
                if cur:
                    entities.append(cur)
                    cur = None
                continue
            label = self.id2label.get(int(ids[i]), "O")
            if label == "O":
                if cur:
                    entities.append(cur)
                    cur = None
                continue
            prefix, _, group = label.partition("-")
            if not group:
                group, prefix = prefix, "I"             # etichette senza B-/I-: continuazione (come HuggingFace)
            score = float(scores[i])
            if cur and prefix != "B" and cur["entity_group"] == group:
                cur["end"] = end_char
                cur["scores"].append(score)
                continue
            if cur:
                entities.append(cur)
            cur = {"entity_group": group, "start": start_char, "end": end_char, "scores": [score]}
        if cur:
            entities.append(cur)
        return [{"entity_group": e["entity_group"], "score": float(np.mean(e["scores"])),
                 "word": text[e["start"]:e["end"]], "start": e["start"], "end": e["end"]} for e in entities]

    @staticmethod
    def _merge_windows(windows):
        """Unione delle finestre sovrapposte (come aggregate_overlapping_entities di HuggingFace)."""
        if len(windows) == 1:
            return windows[0]
        ents = sorted((e for w in windows for e in w), key=lambda e: e["start"])
        if not ents:
            return []
        out = []
        prev = ents[0]
        for e in ents[1:]:
            if prev["start"] <= e["start"] < prev["end"]:
                le, lp = e["end"] - e["start"], prev["end"] - prev["start"]
                if le > lp or (le == lp and e["score"] > prev["score"]):
                    prev = e
            else:
                out.append(prev)
                prev = e
        out.append(prev)
        return out


class OnnxPrivacyFilter:
    """OpenAI Privacy Filter 1.5B in ONNX Runtime (onnx/model_q4.onnx): BIOES (B-/I-/E-/S-), ~645 MB RAM, senza GIL."""

    def __init__(self, model_dir, onnx_filename=None, threads=4):
        if ort is None:
            raise RuntimeError("onnxruntime non installato.")
        if AutoTokenizer is None:
            raise RuntimeError("transformers.AutoTokenizer non disponibile.")
        self.model_dir = model_dir
        names = [onnx_filename] if onnx_filename else [
            "model_q4.onnx", "model_quantized.onnx", "model_q4f16.onnx", "model.onnx",
        ]
        self.onnx_path = None
        for name in names:
            for cand in (os.path.join(model_dir, "onnx", name), os.path.join(model_dir, name)):
                if os.path.isfile(cand):
                    self.onnx_path = cand
                    break
            if self.onnx_path:
                break
        if not self.onnx_path:
            raise FileNotFoundError(f"Nessun modello ONNX Privacy Filter trovato in {model_dir}")

        with open(os.path.join(model_dir, "config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.id2label = {int(k): v for k, v in cfg.get("id2label", {}).items()}
        self.quant_label = "onnx-q4" if "q4" in os.path.basename(self.onnx_path).lower() else "onnx-int8"

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, int(threads))
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(self.onnx_path, opts, providers=["CPUExecutionProvider"])
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self._tok_lock = threading.Lock()

    def predict(self, texts):
        """Per ogni testo: lista di dict {entity_group, score, word, start, end} (BIOES simple)."""
        if not texts:
            return []
        out = []
        for text in texts:
            if not text or not text.strip():
                out.append([])
                continue
            with self._tok_lock:
                enc = self.tokenizer(
                    text, return_offsets_mapping=True, return_tensors="np", add_special_tokens=False,
                )
            ids = enc["input_ids"].astype(np.int64)
            mask = enc["attention_mask"].astype(np.int64)
            if ids.shape[1] == 0:
                out.append([])
                continue
            logits = self.session.run(None, {"input_ids": ids, "attention_mask": mask})[0][0]
            shifted = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
            probs = shifted / np.sum(shifted, axis=-1, keepdims=True)
            pred_ids = np.argmax(probs, axis=-1)
            pred_sc = np.max(probs, axis=-1)
            offsets = enc["offset_mapping"][0]
            ents = []
            cur = None
            for i in range(len(pred_ids)):
                sc0, ec0 = int(offsets[i][0]), int(offsets[i][1])
                if sc0 == ec0:
                    if cur:
                        ents.append(cur)
                        cur = None
                    continue
                lbl = self.id2label.get(int(pred_ids[i]), "O")
                if lbl == "O":
                    if cur:
                        ents.append(cur)
                        cur = None
                    continue
                pref, _, grp = lbl.partition("-")
                if not grp:
                    grp, pref = pref, "I"
                sc = float(pred_sc[i])
                if pref == "S":
                    if cur:
                        ents.append(cur)
                        cur = None
                    ents.append({"entity_group": grp, "start": sc0, "end": ec0, "scores": [sc]})
                elif pref == "B" or cur is None or cur["entity_group"] != grp:
                    if cur:
                        ents.append(cur)
                    cur = {"entity_group": grp, "start": sc0, "end": ec0, "scores": [sc]}
                else:
                    cur["end"] = ec0
                    cur["scores"].append(sc)
                    if pref == "E":
                        ents.append(cur)
                        cur = None
            if cur:
                ents.append(cur)
            out.append([{
                "entity_group": e["entity_group"],
                "score": float(np.mean(e["scores"])),
                "word": text[e["start"]:e["end"]],
                "start": e["start"],
                "end": e["end"],
            } for e in ents])
        return out


class OnnxGLiNER2:
    """GLiNER2-PII multilingua (205M, Apache 2.0) in puro ONNX Runtime + tokenizers (zero dipendenze extra).
    Supporta sia le 31 categorie PII ad alta precisione sia categorie personalizzate zero-shot a runtime."""

    def __init__(self, model_dir, onnx_filename=None, threads=4):
        if ort is None:
            raise RuntimeError("onnxruntime non installato.")
        if _HfTokenizer is None:
            raise RuntimeError("libreria tokenizers non disponibile.")
        self.model_dir = model_dir
        names = [onnx_filename] if onnx_filename else ["model.quantized.onnx", "model.onnx"]
        self.onnx_path = None
        for name in names:
            for cand in (os.path.join(model_dir, name), os.path.join(model_dir, "onnx", name)):
                if os.path.isfile(cand):
                    self.onnx_path = cand
                    break
            if self.onnx_path:
                break
        if not self.onnx_path:
            raise FileNotFoundError(f"Nessun modello ONNX GLiNER2 trovato in {model_dir}")
        tok_path = os.path.join(model_dir, "tokenizer.json")
        if not os.path.isfile(tok_path):
            raise FileNotFoundError(f"tokenizer.json mancante in {model_dir}")

        self.tok = _HfTokenizer.from_file(tok_path)
        self._tok_lock = threading.Lock()
        self._word_cache = {}
        self._schema_cache = {}
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, int(threads))
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(self.onnx_path, opts, providers=["CPUExecutionProvider"])

    def _tok_ids(self, word):
        v = self._word_cache.get(word)
        if v is None:
            v = self.tok.encode(word, add_special_tokens=False).ids
            if len(self._word_cache) < 50000:
                self._word_cache[word] = v
        return v

    def _schema_prefix(self, labels_tuple):
        hit = self._schema_cache.get(labels_tuple)
        if hit is not None:
            return hit
        schema_toks = ["(", "[P]", "entities", "("]
        marker_slots = {1}
        for lbl in labels_tuple:
            marker_slots.add(len(schema_toks))
            schema_toks.append("[E]")
            schema_toks.append(lbl)
        schema_toks.extend([")", ")"])
        prefix_ids, schema_pos = [], []
        for idx, t in enumerate(schema_toks):
            if idx in marker_slots:
                schema_pos.append(len(prefix_ids))
            prefix_ids.extend(self._tok_ids(t))
        prefix_ids.extend(self._tok_ids("[SEP_TEXT]"))
        res = (prefix_ids, np.asarray(schema_pos, dtype=np.int64))
        if len(self._schema_cache) > 64:
            self._schema_cache.clear()
        self._schema_cache[labels_tuple] = res
        return res

    def predict(self, texts, custom_labels=None, threshold=0.55, custom_threshold=0.45):
        """Per ogni testo: lista di dict {entity_group, score, word, start, end}."""
        if not texts:
            return []
        custom = parse_custom_labels(custom_labels) if isinstance(custom_labels, str) else list(custom_labels or [])
        labels = list(GLINER2_DEFAULT_LABELS)
        custom_set = set()
        seen_l = {l.casefold() for l in labels}
        for c in custom:
            if c.casefold() not in seen_l:
                labels.append(c)
                seen_l.add(c.casefold())
            custom_set.add(c.casefold())
        labels_tuple = tuple(labels)
        with self._tok_lock:
            prefix_ids, schema_arr = self._schema_prefix(labels_tuple)
        min_thr = min(float(threshold), float(custom_threshold)) if custom_set else float(threshold)
        out = []
        for text in texts:
            out.append(self._predict_one(text, labels, custom_set, prefix_ids, schema_arr,
                                         float(threshold), float(custom_threshold), min_thr))
        return out

    def _predict_one(self, text, labels, custom_set, prefix_ids, schema_arr, thr, custom_thr, min_thr):
        if not text or not text.strip():
            return []
        norm_text = text if text.endswith((".", "!", "?")) else text + "."
        words = [(m.group().lower(), m.start(), min(m.end(), len(text))) for m in _GL2_WORD_RE.finditer(norm_text)]
        if not words:
            return []
        with self._tok_lock:
            word_subs = [self._tok_ids(w) for w, _, _ in words]
        max_sub = 510
        budget = max(32, max_sub - len(prefix_ids))
        best = {}
        pos = 0
        n_total = len(words)
        while pos < n_total:
            ids = list(prefix_ids)
            word_pos, starts, ends = [], [], []
            used = 0
            j = pos
            while j < n_total:
                sub = word_subs[j]
                if word_pos and used + len(sub) > budget:
                    break
                if len(sub) > budget:
                    sub = sub[:budget]
                word_pos.append(len(ids))
                ids.extend(sub)
                starts.append(words[j][1])
                ends.append(words[j][2])
                used += len(sub)
                j += 1
            if not word_pos:
                break
            n_words = len(word_pos)
            input_ids = np.asarray([ids], dtype=np.int64)
            attn = np.ones_like(input_ids, dtype=np.int64)
            twi = np.asarray(word_pos, dtype=np.int64)
            span_probs = self.session.run(None, {
                "input_ids": input_ids, "attention_mask": attn,
                "text_word_indices": twi, "schema_special_indices": schema_arr,
            })[0]
            hit_w, hit_k, hit_l = np.where(span_probs >= min_thr)
            for wi, ki, li in zip(hit_w.tolist(), hit_k.tolist(), hit_l.tolist()):
                end_wi = wi + ki
                if end_wi >= n_words or li >= len(labels):
                    continue
                lbl = labels[li]
                is_cust = lbl.casefold() in custom_set
                sc = float(span_probs[wi, ki, li])
                if sc < (custom_thr if is_cust else thr):
                    continue
                cs, ce = starts[wi], ends[end_wi]
                if ce <= cs:
                    continue
                grp = "CUSTOM_PII" if is_cust else GLINER2_TO_GERMANO.get(lbl, "CUSTOM_PII")
                # Le categorie personalizzate chieste esplicitamente dall'utente restano confermate se prob >= 0.70
                if is_cust and sc >= 0.70:
                    sc = max(sc, 0.88)
                key = (cs, ce, grp)
                if key not in best or sc > best[key]:
                    best[key] = sc
            if j >= n_total:
                break
            step = max(1, (j - pos) - 30)   # sovrapposizione di 30 parole fra finestre
            pos += step
        return [{
            "entity_group": grp, "score": sc, "word": text[cs:ce], "start": cs, "end": ce,
        } for (cs, ce, grp), sc in sorted(best.items())]
