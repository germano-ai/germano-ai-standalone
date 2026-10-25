"""Vault delle corrispondenze etichetta <-> dato reale (pseudonimizzazione reversibile).

Formato file (compatibile con v0.50): extracted/deanonymize_vault.json
    {"tag_to_word": {"[PERSONA_1]": "Mario Rossi"},
     "word_to_tag": {"[PERSONA]::mario rossi": "[PERSONA_1]"},
     "counters":    {"[PERSONA]": 1}}

Solo il demone crea nuove etichette; il server legge (e svuota il vault solo a demone spento).
"""
import json
import os
import re
import shutil
import threading
import time

from . import common

_L = "A-Za-zÀ-ÖØ-öø-ÿ"
# Etichetta numerata: [PERSONA_1], [PERSONA 1], [ persona_1 ], [COD.FISCALE/P.IVA_3], [DATO_SANITARIO_2]
TAG_RE = re.compile(r"\[\s*([" + _L + r"][" + _L + r"./]*(?:[ _]+[" + _L + r"./]+)*?)[ _]+(\d{1,7})\s*\]")
# Qualsiasi etichetta di Germano (anche non numerata, es. [VOLTO], [PERSONA]) da proteggere in rianalisi.
ANY_TAG_RE = re.compile(r"\[[A-Z][A-Z0-9./_ ]{1,40}\]")


def _norm(base, num):
    return "[" + re.sub(r"[ _]+", "_", base.strip()).upper() + "_" + str(int(num)) + "]"


def normalize_tag(tag):
    m = TAG_RE.fullmatch(str(tag).strip())
    if not m:
        return None
    return _norm(m.group(1), m.group(2))


def iter_tags(text, tag_map):
    """Restituisce (start, end, valore_reale) per ogni etichetta presente nel vault."""
    if not text or "[" not in text or not tag_map:
        return
    for m in TAG_RE.finditer(text):
        word = tag_map.get(_norm(m.group(1), m.group(2)))
        if word:
            yield m.start(), m.end(), word


def contains_tags(text, tag_map):
    for _ in iter_tags(text, tag_map):
        return True
    return False


def restore_text(text, tag_map, json_escape=False):
    """Rimette i dati reali al posto delle etichette numerate (passaggio unico, O(n))."""
    if not isinstance(text, str) or "[" not in text or not tag_map:
        return text

    def _rep(m):
        word = tag_map.get(_norm(m.group(1), m.group(2)))
        if not word:
            return m.group(0)
        if json_escape:
            return json.dumps(word, ensure_ascii=False)[1:-1]
        return word

    return TAG_RE.sub(_rep, text)


def _empty():
    return {"tag_to_word": {}, "word_to_tag": {}, "counters": {}}


class Vault:
    def __init__(self, path=common.VAULT_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._data = None
        self._stat_sig = None
        self._dirty = False
        self._map_cache = None

    # ------------------------------------------------------------------ disco
    def _stat(self):
        try:
            st = os.stat(self.path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _load(self):
        sig = self._stat()
        data = None
        if sig is not None:
            unreadable = True
            for i in range(10):
                try:
                    with open(self.path, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                    unreadable = False
                    break
                except FileNotFoundError:
                    data, unreadable = None, False
                    break
                except (PermissionError, json.JSONDecodeError, UnicodeDecodeError):
                    time.sleep(0.05 * (i + 1))
            if unreadable:
                # Mai sovrascrivere un vault che non si riesce a leggere: se ne conserva una copia.
                backup = f"{self.path}.illeggibile-{time.strftime('%Y%m%d-%H%M%S')}"
                try:
                    shutil.copy2(self.path, backup)
                    common.log(f"ATTENZIONE: vault illeggibile, copia di sicurezza salvata in {os.path.basename(backup)}")
                except Exception:
                    pass
        base = _empty()
        if isinstance(data, dict):
            for k in base:
                if isinstance(data.get(k), dict):
                    base[k] = data[k]
        self._data = base
        self._stat_sig = sig
        self._map_cache = None

    def _ensure(self):
        if self._data is None:
            self._load()

    def refresh(self):
        """Ricarica dal disco se il file e' stato modificato da un altro processo."""
        with self._lock:
            if self._data is None:
                self._load()
                return
            if not self._dirty and self._stat() != self._stat_sig:
                self._load()

    def flush(self):
        with self._lock:
            if not self._dirty or self._data is None:
                return
            common.atomic_write_json(self.path, self._data, indent=2)
            self._stat_sig = self._stat()
            self._dirty = False

    # ------------------------------------------------------------------ API
    def label_for(self, word, base_label):
        """Etichetta numerata stabile per (categoria, valore) - es. [PERSONA_3]."""
        w = str(word).strip()
        if not w:
            return base_label
        key = f"{base_label}::{w.lower()}"
        with self._lock:
            self._ensure()
            tag = self._data["word_to_tag"].get(key)
            if tag:
                return tag
            try:
                idx = int(self._data["counters"].get(base_label, 0)) + 1
            except (TypeError, ValueError):
                idx = 1
            stem = base_label[:-1] if base_label.endswith("]") else base_label
            tag = f"{stem}_{idx}]"
            while tag in self._data["tag_to_word"]:
                idx += 1
                tag = f"{stem}_{idx}]"
            self._data["counters"][base_label] = idx
            self._data["word_to_tag"][key] = tag
            self._data["tag_to_word"][tag] = w
            self._dirty = True
            self._map_cache = None
            return tag

    def tag_map(self):
        """Mappa etichetta normalizzata -> valore reale (oggetto condiviso: non modificarlo)."""
        with self._lock:
            self._ensure()
            if self._map_cache is None:
                m = {}
                for tag, word in self._data["tag_to_word"].items():
                    nt = normalize_tag(tag)
                    if nt and isinstance(word, str) and word:
                        m[nt] = word
                self._map_cache = m
            return self._map_cache

    def items(self):
        with self._lock:
            self._ensure()
            return list(self._data["tag_to_word"].items())

    def count(self):
        with self._lock:
            self._ensure()
            return len(self._data["tag_to_word"])

    def clear(self):
        with self._lock:
            self._data = _empty()
            self._map_cache = None
            self._dirty = True
            self.flush()


class VaultReader:
    """Accesso in sola lettura dal server web, con ricarica automatica quando il file cambia."""

    def __init__(self, path=common.VAULT_FILE):
        self._vault = Vault(path)

    def tag_map(self):
        self._vault.refresh()
        return self._vault.tag_map()

    def items(self):
        self._vault.refresh()
        return self._vault.items()

    def count(self):
        self._vault.refresh()
        return self._vault.count()
