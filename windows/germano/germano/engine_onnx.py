"""Italian NER XXL con ONNX Runtime (Sistema 1): stesse entita' della pipeline PyTorch di HuggingFace
(token-classification, aggregation_strategy="simple", stride=64), senza il lock dei modelli PyTorch.

- Testi oltre i 512 token: finestre sovrapposte di 64 token (come la pipeline con stride=64) e, per gli span che si
  sovrappongono tra due finestre, si tiene il piu' lungo (a parita' quello con il punteggio piu' alto). Senza finestre
  la parte oltre il 512esimo token resterebbe NON analizzata (un blocco da 2.000 caratteri ne ha fino a ~950 in una
  tabella di nomi, codici e IBAN).
- Il tokenizer «fast» di HuggingFace non e' utilizzabile da piu' thread insieme (errore «Already borrowed»): la sola
  tokenizzazione e' serializzata; l'inferenza ONNX Runtime e' sicura tra thread e rilascia il GIL.
- Modello: onnx/model.onnx = lo stesso BERT di model.safetensors con i pesi FP16 (come nel file originale) convertiti
  in FP32 all'apertura da ONNX Runtime: calcolo in FP32 identico a PyTorch (verificato span per span), 212 MB. Una
  quantizzazione INT8 dinamica cambierebbe ~4% degli span (verificato): non si usa.
"""
import json
import os
import threading

import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None

try:
    from transformers import AutoTokenizer
except ImportError:
    AutoTokenizer = None

MAX_LENGTH = 512
STRIDE = 64


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
