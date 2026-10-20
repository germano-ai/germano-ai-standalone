import sys
import os
import warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
import time
import shutil
import atexit
import re
import json
import concurrent.futures

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Impostazioni rigorose per esecuzione 100% Offline su Windows 11 Vanilla
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
os.environ["EASYOCR_MODULE_PATH"] = os.path.join(BASE_DIR, "models", "easyocr")

if hasattr(os, "add_dll_directory"):
    runtime_dir = os.path.dirname(sys.executable)
    if os.path.isdir(runtime_dir):
        try:
            os.add_dll_directory(runtime_dir)
        except Exception:
            pass

try:
    import pymupdf as fitz  # PyMuPDF >= 2.0
except ImportError:
    import fitz  # PyMuPDF
import docx
import openpyxl
import xlrd
from xlutils.copy import copy

INPUT_DIR = "input"
OUTPUT_DIR = "output"
PROCESSED_DIR = "processed"
FAILED_DIR = "failed"
EXTRACTED_DIR = "extracted"
VAULT_FILE = os.path.join(EXTRACTED_DIR, "deanonymize_vault.json")
STOP_FLAG = "stop.flag"
PID_FILE = "daemon.pid"
READY_FLAG = "ready.flag"
CONFIG_FILE = "config.json"

SETTINGS = {
    "ui_mode": "simple",
    "compliance_mode": "PA",
    "enable_deanonymize": True,
    "enable_model_velvet": True,
    "enable_model_italian_ner": True,
    "enable_ocr": True,
    "enable_faces": True,
    "enable_signatures": True,
    "enable_plate_vision": True,
    "enable_regex": True,
    "ai_threshold": 0.0,
    "hardware_mode": "gpu_fallback",
    "censor_person": True,
    "censor_profession": True,
    "censor_address": True,
    "censor_cadastre": True,
    "censor_email": True,
    "censor_phone": True,
    "censor_account": True,
    "censor_financial": True,
    "censor_url": True,
    "censor_date": True,
    "censor_secret": True,
    "censor_cf_iva": True,
    "censor_org": True,
    "censor_plates_docs": True,
    "censor_medical": True,
    "censor_medicine": True,
    "censor_legal": True,
    "censor_civil_status": True
}

_LAST_CONFIG_MTIME = 0.0

ALL_MODEL_AND_FEATURE_KEYS = [
    "enable_model_velvet", "enable_model_italian_ner", "enable_ocr",
    "enable_faces", "enable_signatures", "enable_plate_vision", "enable_regex",
    "censor_person", "censor_profession", "censor_address", "censor_cadastre",
    "censor_email", "censor_phone", "censor_account", "censor_financial",
    "censor_url", "censor_date", "censor_secret", "censor_cf_iva",
    "censor_org", "censor_plates_docs", "censor_medical", "censor_medicine",
    "censor_legal", "censor_civil_status"
]


def reload_settings(classifier_wrapper=None):
    global _LAST_CONFIG_MTIME
    try:
        if os.path.exists(CONFIG_FILE):
            mtime = os.path.getmtime(CONFIG_FILE)
            if mtime != _LAST_CONFIG_MTIME:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        SETTINGS.update(data)
                if SETTINGS.get("compliance_mode") == "PA":
                    SETTINGS["ai_threshold"] = 0.0
                    for k in ALL_MODEL_AND_FEATURE_KEYS:
                        SETTINGS[k] = True
                _LAST_CONFIG_MTIME = mtime
                if classifier_wrapper is not None:
                    classifier_wrapper.threshold = float(SETTINGS.get("ai_threshold", 0.0))
    except Exception:
        pass


reload_settings()


def _load_vault():
    os.makedirs(EXTRACTED_DIR, exist_ok=True)
    if os.path.exists(VAULT_FILE):
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "tag_to_word" in data:
                    return data
        except Exception:
            pass
    return {"tag_to_word": {}, "word_to_tag": {}, "counters": {}, "latest_by_base": {}}


def _save_vault(vault):
    try:
        os.makedirs(EXTRACTED_DIR, exist_ok=True)
        with open(VAULT_FILE, "w", encoding="utf-8") as f:
            json.dump(vault, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_or_create_indexed_label(word, base_label):
    word_clean = str(word).strip()
    if not word_clean:
        return base_label
    vault = _load_vault()
    lookup_key = f"{base_label}::{word_clean.lower()}"
    if lookup_key in vault["word_to_tag"]:
        indexed_label = vault["word_to_tag"][lookup_key]
        vault["tag_to_word"][indexed_label] = word_clean
        vault.setdefault("latest_by_base", {})[base_label] = word_clean
        _save_vault(vault)
        return indexed_label

    idx = int(vault["counters"].get(base_label, 0)) + 1
    vault["counters"][base_label] = idx
    indexed_label = base_label.replace("]", f"_{idx}]")
    vault["word_to_tag"][lookup_key] = indexed_label
    vault["tag_to_word"][indexed_label] = word_clean
    vault.setdefault("latest_by_base", {})[base_label] = word_clean
    _save_vault(vault)
    return indexed_label


def load_vault_tag_map():
    vault = _load_vault()
    tag_map = dict(vault.get("tag_to_word", {}))
    for base_label, word_val in vault.get("latest_by_base", {}).items():
        if base_label not in tag_map:
            tag_map[base_label] = word_val
    return tag_map


def clear_vault():
    _save_vault({"tag_to_word": {}, "word_to_tag": {}, "counters": {}, "latest_by_base": {}})


def deanonymize_string(text, tag_map=None):
    if not isinstance(text, str) or not text:
        return text
    if tag_map is None:
        tag_map = load_vault_tag_map()
    if not tag_map:
        return text

    result = text
    # Sort tags by length descending so [PERSONA_10] is replaced before [PERSONA_1] and before [PERSONA]
    sorted_tags = sorted(tag_map.keys(), key=lambda k: len(k), reverse=True)
    for tag in sorted_tags:
        original_word = tag_map[tag]
        if not original_word:
            continue
        # Match both [TAG_1] and [TAG 1] case-insensitively
        escaped = re.escape(tag).replace(r"\_", r"[\_\s]")
        result = re.sub(escaped, lambda _: original_word, result, flags=re.IGNORECASE)
    return result


def text_contains_vault_tags(text, tag_map=None):
    if not isinstance(text, str) or "[" not in text:
        return False
    if tag_map is None:
        tag_map = load_vault_tag_map()
    if not tag_map:
        return False
    for tag in tag_map.keys():
        if "_" not in tag:
            continue
        escaped = re.escape(tag).replace(r"\_", r"[\_\s]")
        if re.search(escaped, text, flags=re.IGNORECASE):
            return True
    return False


def file_contains_vault_tags(filepath, tag_map=None):
    if not os.path.exists(filepath):
        return False
    if tag_map is None:
        tag_map = load_vault_tag_map()
    if not tag_map:
        return False
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext in ['.txt', '.csv', '.xml', '.html', '.htm', '.eml', '.rtf']:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return text_contains_vault_tags(f.read(500000), tag_map)
        elif ext in ['.docx', '.docm']:
            doc = docx.Document(filepath)
            chunks = [p.text for p in doc.paragraphs]
            for tbl in doc.tables:
                for row in tbl.rows:
                    for cell in row.cells:
                        chunks.append(cell.text)
            return text_contains_vault_tags("\n".join(chunks), tag_map)
        elif ext in ['.xlsx', '.xlsm']:
            wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            chunks = []
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                for row in ws.iter_rows(values_only=True):
                    for val in row:
                        if isinstance(val, str):
                            chunks.append(val)
            wb.close()
            return text_contains_vault_tags("\n".join(chunks), tag_map)
        elif ext == '.pptx':
            import pptx
            prs = pptx.Presentation(filepath)
            chunks = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        chunks.append(shape.text_frame.text)
            return text_contains_vault_tags("\n".join(chunks), tag_map)
        elif ext in ['.odt', '.ods', '.odp']:
            import zipfile
            with zipfile.ZipFile(filepath, 'r') as zin:
                if 'content.xml' in zin.namelist():
                    raw = zin.read('content.xml').decode('utf-8', errors='ignore')
                    return text_contains_vault_tags(raw, tag_map)
        elif ext == '.pdf':
            doc = fitz.open(filepath)
            try:
                for page in doc:
                    if text_contains_vault_tags(page.get_text(), tag_map):
                        return True
            finally:
                doc.close()
    except Exception:
        pass
    return False


def cleanup_flags():
    for flag in [PID_FILE, READY_FLAG]:
        if os.path.exists(flag):
            try:
                os.remove(flag)
            except Exception:
                pass


atexit.register(cleanup_flags)


def get_regex_spans(text):
    if not SETTINGS.get("enable_regex", True):
        return []
    patterns = [
        # Indirizzi generici italiani
        (r'(?i)\b(?:Via|Viale|Piazza|Corso|Largo|Vicolo|P\.zza|C\.so)\s+[A-Za-z0-9\s\'\.,]+\d{1,5}\b', 'private_address'),
        # CAP + Città
        (r'\b\d{5}\s+[A-Za-zÀ-ÿ\'\s]{2,25}\b', 'private_address'),
        # Codice Fiscale
        (r'(?i)\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b', 'cf_iva'),
        # Partita IVA / IBAN Italiano
        (r'\bIT\d{2}[A-Z]\d{10}[0-9A-Z]{12}\b', 'account_number'),
        (r'\bIT\d{11}\b', 'cf_iva'),
        # Email
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b', 'private_email'),
        # Telefoni italiani
        (r'(?:\+39|0039)?\s?\b(?:3\d{2}[\s\-\.]?\d{6,7}|0\d{1,3}[\s\-\.]?\d{5,8})\b', 'private_phone'),
        # Ragioni Sociali / Aziende / Enti
        (r'\b[A-ZÀ-Ÿ][A-Za-zÀ-ÿ0-9&\'\.\-]*(?:\s+[A-ZÀ-Ÿ][A-Za-zÀ-ÿ0-9&\'\.\-]*){0,3}\s+(?:S\.?r\.?l\.?s?\.?|S\.?p\.?A\.?|S\.?n\.?c\.?|S\.?a\.?s\.?|S\.?c\.?a\.?r\.?l\.?)', 'private_org'),
        # Carta d'Identità Elettronica (CIE) e Targhe automobilistiche
        (r'\bC[A-Z]\d{5}[A-Z]{2}\b', 'plates_docs'),
        (r'(?i)\b(?:targa\s+)([A-Z]{2}\s?\d{3}\s?[A-Z]{2})\b', 'plates_docs'),
        # Riferimenti catastali espliciti (Foglio / Particella / Subalterno)
        (r'(?i)\b(?:foglio|particella|mappale|subalterno|sub\.)\s*(?:n\.?\s*)?\d+\b', 'cadastre')
    ]
    spans = []
    if not isinstance(text, str):
        return spans

    for pattern, entity_group in patterns:
        try:
            for match in re.finditer(pattern, text):
                spans.append({
                    "word": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "score": 1.0,
                    "entity": entity_group,
                    "entity_group": entity_group
                })
        except Exception:
            pass
    return spans


CATEGORY_MAP = {
    # Categorie modello privacy-filter & RegEx
    "private_person": ("[PERSONA]", "censor_person"),
    "private_address": ("[INDIRIZZO]", "censor_address"),
    "cadastre": ("[CATASTO]", "censor_cadastre"),
    "private_email": ("[EMAIL]", "censor_email"),
    "private_phone": ("[TELEFONO]", "censor_phone"),
    "cf_iva": ("[COD.FISCALE/P.IVA]", "censor_cf_iva"),
    "account_number": ("[CONTO/CARTA]", "censor_account"),
    "secret": ("[SEGRETO]", "censor_secret"),
    "private_url": ("[URL]", "censor_url"),
    "private_date": ("[DATA]", "censor_date"),
    "private_org": ("[AZIENDA/ENTE]", "censor_org"),
    "plates_docs": ("[TARGA/DOCUMENTO]", "censor_plates_docs"),
    "medical": ("[DATO_SANITARIO]", "censor_medical"),
    "medicine": ("[FARMACO/TERAPIA]", "censor_medicine"),
    "legal": ("[DATO_GIUDIZIARIO]", "censor_legal"),

    # Categorie modello specialistico DeepMount00/Italian_NER_XXL_v2 (58 classi italiane)
    "NOME": ("[PERSONA]", "censor_person"),
    "COGNOME": ("[PERSONA]", "censor_person"),
    "AVV_NOTAIO": ("[PROFESSIONE/TITOLO]", "censor_profession"),
    "PROFESSIONE": ("[PROFESSIONE/TITOLO]", "censor_profession"),
    "INDIRIZZO": ("[INDIRIZZO]", "censor_address"),
    "LUOGO": ("[INDIRIZZO]", "censor_address"),
    "STATO": ("[INDIRIZZO]", "censor_address"),
    "CODICE_POSTALE": ("[INDIRIZZO]", "censor_address"),
    "FOGLIO": ("[CATASTO]", "censor_cadastre"),
    "PARTICELLA": ("[CATASTO]", "censor_cadastre"),
    "SUBALTERNO": ("[CATASTO]", "censor_cadastre"),
    "MAPPALE": ("[CATASTO]", "censor_cadastre"),
    "CODICE_FISCALE": ("[COD.FISCALE/P.IVA]", "censor_cf_iva"),
    "P_IVA": ("[COD.FISCALE/P.IVA]", "censor_cf_iva"),
    "EMAIL": ("[EMAIL]", "censor_email"),
    "NUMERO_TELEFONO": ("[TELEFONO]", "censor_phone"),
    "IMEI": ("[TELEFONO]", "censor_phone"),
    "IBAN": ("[CONTO/CARTA]", "censor_account"),
    "NUMERO_CARTA": ("[CONTO/CARTA]", "censor_account"),
    "NUMERO_CONTO": ("[CONTO/CARTA]", "censor_account"),
    "BIC": ("[CONTO/CARTA]", "censor_account"),
    "CVV": ("[CONTO/CARTA]", "censor_account"),
    "NUM_ASSEGNO_BANCARIO": ("[CONTO/CARTA]", "censor_account"),
    "BANCA": ("[CONTO/CARTA]", "censor_account"),
    "IMPORTO": ("[IMPORTO/FINANZA]", "censor_financial"),
    "TASSO_MUTUO": ("[IMPORTO/FINANZA]", "censor_financial"),
    "VALUTA": ("[IMPORTO/FINANZA]", "censor_financial"),
    "DATA": ("[DATA]", "censor_date"),
    "DATA_NASCITA": ("[DATA]", "censor_date"),
    "DATA_MORTE": ("[DATA]", "censor_date"),
    "ETA": ("[DATA]", "censor_date"),
    "ORARIO": ("[DATA]", "censor_date"),
    "RAGIONE_SOCIALE": ("[AZIENDA/ENTE]", "censor_org"),
    "BRAND": ("[AZIENDA/ENTE]", "censor_org"),
    "TARGA_VEICOLO": ("[TARGA/DOCUMENTO]", "censor_plates_docs"),
    "NUMERO_DOCUMENTO": ("[TARGA/DOCUMENTO]", "censor_plates_docs"),
    "N_LICENZA": ("[TARGA/DOCUMENTO]", "censor_plates_docs"),
    "PASSWORD": ("[SEGRETO]", "censor_secret"),
    "PIN": ("[SEGRETO]", "censor_secret"),
    "URL": ("[URL]", "censor_url"),
    "IP": ("[URL]", "censor_url"),
    "IPV6_1": ("[URL]", "censor_url"),
    "MAC": ("[URL]", "censor_url"),
    "USER_AGENT": ("[URL]", "censor_url"),
    "MALATTIA": ("[DATO_SANITARIO]", "censor_medical"),
    "CARTELLA_CLINICA": ("[DATO_SANITARIO]", "censor_medical"),
    "STORIA_CLINICA": ("[DATO_SANITARIO]", "censor_medical"),
    "MEDICINA": ("[FARMACO/TERAPIA]", "censor_medicine"),
    "DOSAGGIO": ("[FARMACO/TERAPIA]", "censor_medicine"),
    "FORM": ("[FARMACO/TERAPIA]", "censor_medicine"),
    "FREQUENZA": ("[FARMACO/TERAPIA]", "censor_medicine"),
    "DURATION": ("[FARMACO/TERAPIA]", "censor_medicine"),
    "STRENGTH": ("[FARMACO/TERAPIA]", "censor_medicine"),
    "N_SENTENZA": ("[DATO_GIUDIZIARIO]", "censor_legal"),
    "TRIBUNALE": ("[DATO_GIUDIZIARIO]", "censor_legal"),
    "LEGGE": ("[DATO_GIUDIZIARIO]", "censor_legal"),
    "REGIME_PATRIMONIALE": ("[STATO_CIVILE]", "censor_civil_status"),
    "STATO_CIVILE": ("[STATO_CIVILE]", "censor_civil_status")
}


def filter_and_format_spans(spans, text=None):
    filtered = []
    for span in spans:
        s_copy = span.copy()
        if isinstance(text, str) and 'start' in s_copy and 'end' in s_copy:
            st, en = int(s_copy['start']), int(s_copy['end'])
            # Trim leading/trailing spaces included by BPE tokenizer
            while st < en and text[st].isspace():
                st += 1
            while en > st and text[en - 1].isspace():
                en -= 1
            if st >= en:
                continue

            # Trim common Italian honorifics or field prefixes if captured inside the span
            m_pref = re.match(
                r'(?i)^(?:(?:il|lo|la|i|gli|le)\s+)?(?:signor(?:a|ina|e|i)?|sig\.?(?:ra)?|dott\.?(?:ssa)?|avv\.?|ing\.?|prof\.?|cf|c\.f\.|p\.iva|tel\.?|telefono|cell\.?|email|pec|iban)\b\.?\s*:?\s*',
                text[st:en]
            )
            if m_pref:
                st += m_pref.end()
                while st < en and text[st].isspace():
                    st += 1
            if st >= en:
                continue

            # Filter out tiny isolated mid-word subword false positives (e.g. 'ita' inside 'abita')
            if (en - st) <= 3 and st > 0 and text[st - 1].isalpha() and not text[st:en].isupper():
                continue
            s_copy['start'] = st
            s_copy['end'] = en
            s_copy['word'] = text[st:en]

        group = s_copy.get("entity_group", s_copy.get("entity", "PII"))
        clean_group = re.sub(r'^[BIES]-', '', str(group))
        if clean_group in CATEGORY_MAP:
            label, config_key = CATEGORY_MAP[clean_group]
            if not SETTINGS.get(config_key, True):
                continue
            s_copy["replacement_label"] = label
            s_copy["entity_group"] = clean_group
        else:
            s_copy["replacement_label"] = "[DATI_SENSIBILI]"
        filtered.append(s_copy)
    return filtered


def merge_and_sort_spans(spans, text):
    if not spans:
        return []
    spans.sort(key=lambda x: (x['start'], -x['end']))
    merged = [spans[0].copy()]
    for current in spans[1:]:
        prev = merged[-1]
        same_label = current.get('replacement_label') == prev.get('replacement_label')
        gap_text = text[prev['end']:current['start']] if (isinstance(text, str) and current['start'] >= prev['end']) else None
        # Merge overlapping spans, adjacent spans, or consecutive tokens of the same entity separated by a single space
        if current['start'] <= prev['end'] or (same_label and gap_text in ("", " ")):
            prev['end'] = max(prev['end'], current['end'])
            prev['score'] = max(float(prev.get('score', 0.0)), float(current.get('score', 0.0)))
            if isinstance(text, str):
                prev['word'] = text[prev['start']:prev['end']]
        else:
            merged.append(current.copy())
    cleaned = []
    for sp in merged:
        if isinstance(text, str) and 'start' in sp and 'end' in sp:
            st, en = int(sp['start']), int(sp['end'])
            m_field = re.match(
                r'(?i)^(?:cf|c\.f\.|p\.iva|tel\.?|telefono|cell\.?|email|pec|iban|bic|swift)\b\.?\s*:?\s*',
                text[st:en]
            )
            if m_field:
                st += m_field.end()
                while st < en and text[st].isspace():
                    st += 1
            if st >= en:
                continue
            sp['start'] = st
            sp['end'] = en
            sp['word'] = text[st:en]
        cleaned.append(sp)
    cleaned.sort(key=lambda x: x['start'], reverse=True)
    return cleaned


def anonymize_string(text, classifier, extracted_data):
    if not isinstance(text, str) or not text.strip():
        return text
    spans = classifier(text) + get_regex_spans(text)
    if not spans:
        return text
    spans = merge_and_sort_spans(filter_and_format_spans(spans, text), text)
    if not spans:
        return text
    use_indexed = bool(SETTINGS.get("enable_deanonymize", True))
    # First register in forward order so numbering is natural (1, 2, 3...)
    for span in sorted(spans, key=lambda x: x['start']):
        base_label = span.get('replacement_label', '[DATI_SENSIBILI]')
        indexed_label = get_or_create_indexed_label(span["word"], base_label)
        span["indexed_label"] = indexed_label

    anonymized_text = text
    for span in spans:
        base_label = span.get('replacement_label', '[DATI_SENSIBILI]')
        indexed_label = span.get("indexed_label") or get_or_create_indexed_label(span["word"], base_label)
        replacement = indexed_label if use_indexed else base_label
        extracted_data.append({
            "word": span["word"],
            "label": replacement,
            "entity": span.get("entity_group", span.get("entity", "PII")),
            "score": float(span["score"])
        })
        anonymized_text = anonymized_text[:span['start']] + replacement + anonymized_text[span['end']:]
    return anonymized_text


def process_embedded_files(file_path, classifier, extracted_data, ocr_reader=None):
    import zipfile
    import tempfile
    if not zipfile.is_zipfile(file_path):
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_zip = os.path.join(tmpdir, "new_arch.zip")
        has_modified = False
        with zipfile.ZipFile(file_path, 'r') as zin:
            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if 'embeddings/' in item.filename and (item.filename.lower().endswith('.pdf') or item.filename.lower().endswith('.bin')):
                        ext_file = os.path.join(tmpdir, "embed_" + os.path.basename(item.filename))
                        with open(ext_file, 'wb') as f:
                            f.write(data)
                        out_ext_file = ext_file + ".out.pdf"
                        try:
                            process_pdf(ext_file, out_ext_file, classifier, extracted_data, ocr_reader=ocr_reader)
                            with open(out_ext_file, 'rb') as f:
                                new_data = f.read()
                            zout.writestr(item, new_data)
                            has_modified = True
                        except Exception:
                            zout.writestr(item, data)
                    else:
                        zout.writestr(item, data)
        if has_modified:
            shutil.copy2(temp_zip, file_path)


def process_txt(input_file, output_file, classifier, extracted_data):
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    anonymized_text = anonymize_string(text, classifier, extracted_data)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(anonymized_text)


_FACE_DETECTOR = None
_SIGNATURE_DETECTOR = None
_PLATE_DETECTOR = None


def get_face_detector():
    global _FACE_DETECTOR
    if _FACE_DETECTOR is not None:
        return _FACE_DETECTOR
    try:
        import cv2  # type: ignore
        model_path = os.path.join(BASE_DIR, "models", "face-detection", "face_detection_yunet_2023mar.onnx")
        if os.path.exists(model_path) and hasattr(cv2, "FaceDetectorYN"):
            _FACE_DETECTOR = cv2.FaceDetectorYN.create(model_path, "", (320, 320), 0.6, 0.3, 5000)
    except Exception:
        pass
    return _FACE_DETECTOR


def get_signature_detector():
    global _SIGNATURE_DETECTOR
    if _SIGNATURE_DETECTOR is not None:
        return _SIGNATURE_DETECTOR
    try:
        import torch
        from transformers import pipeline
        sig_path = os.path.join(BASE_DIR, "models", "signature-detection")
        if os.path.exists(sig_path) and os.listdir(sig_path):
            _SIGNATURE_DETECTOR = pipeline("object-detection", model=sig_path, model_kwargs={"dtype": torch.float32})
    except Exception:
        pass
    return _SIGNATURE_DETECTOR


def get_plate_detector():
    global _PLATE_DETECTOR
    if _PLATE_DETECTOR is not None:
        return _PLATE_DETECTOR
    try:
        import torch
        from transformers import pipeline
        pl_path = os.path.join(BASE_DIR, "models", "plate-detection")
        if os.path.exists(pl_path) and os.listdir(pl_path):
            _PLATE_DETECTOR = pipeline("object-detection", model=pl_path, model_kwargs={"dtype": torch.float32})
    except Exception:
        pass
    return _PLATE_DETECTOR


def process_pdf(input_file, output_file, classifier, extracted_data, ocr_reader=None):
    doc = None
    try:
        doc = fitz.open(input_file)
        was_image = not doc.is_pdf
        if was_image:
            pdf_bytes = doc.convert_to_pdf()
            doc.close()
            doc = fitz.open("pdf", pdf_bytes)

        for page in doc:
            text = page.get_text()
            has_visual_content = was_image or (not text.strip()) or (len(page.get_images()) > 0)

            # --- 1. BLOCCO VISIONE ARTIFICIALE (VOLTI YuNet, FIRME YOLOS, TARGHE YOLOS) ---
            if has_visual_content and (
                SETTINGS.get("enable_faces", True)
                or SETTINGS.get("enable_signatures", True)
                or SETTINGS.get("enable_plate_vision", True)
            ):
                try:
                    import cv2  # type: ignore
                    import numpy as np  # type: ignore
                    from PIL import Image
                    pix = page.get_pixmap()
                    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

                    if pix.n >= 4:
                        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
                    elif pix.n == 1:
                        img_bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                    else:
                        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                        img_rgb = img

                    redacted_visual = False

                    # 1a. Volti (YuNet DNN)
                    if SETTINGS.get("enable_faces", True):
                        faces_list = []
                        detector = get_face_detector()
                        if detector is not None:
                            h_img, w_img = img_bgr.shape[:2]
                            detector.setInputSize((w_img, h_img))
                            _, detected = detector.detect(img_bgr)
                            if detected is not None:
                                for f in detected:
                                    faces_list.append((int(f[0]), int(f[1]), int(f[2]), int(f[3])))
                        if len(faces_list) > 0:
                            print(f"[{time.strftime('%H:%M:%S')}] Rilevati {len(faces_list)} volti nella pagina. Applicazione censura biometrica...", flush=True)
                            for (x, y, w, h) in faces_list:
                                margin_x = int(w * 0.15)
                                margin_y = int(h * 0.15)
                                rect = fitz.Rect(x - margin_x, y - margin_y, x + w + margin_x, y + h + margin_y)
                                annot = page.add_redact_annot(rect, fill=(0, 0, 0), text="[VOLTO]", text_color=(1, 1, 1))
                                annot.set_colors(stroke=None, fill=(0, 0, 0))
                                annot.update()
                                extracted_data.append({"word": "[VOLTO OSCURATO]", "label": "[VOLTO]", "entity": "BIOMETRIC_FACE", "score": 1.0})
                                redacted_visual = True

                    pil_page = Image.fromarray(img_rgb)

                    # 1b. Firme Autografe (YOLOS-Tiny)
                    if SETTINGS.get("enable_signatures", True):
                        sig_det = get_signature_detector()
                        if sig_det is not None:
                            sig_preds = sig_det(pil_page)
                            sig_boxes = [p for p in sig_preds if float(p.get("score", 0.0)) >= 0.55]
                            if sig_boxes:
                                print(f"[{time.strftime('%H:%M:%S')}] Rilevate {len(sig_boxes)} firme autografe nella pagina. Oscuramento...", flush=True)
                                for p in sig_boxes:
                                    b = p["box"]
                                    rect = fitz.Rect(b["xmin"], b["ymin"], b["xmax"], b["ymax"])
                                    annot = page.add_redact_annot(rect, fill=(0, 0, 0), text="[FIRMA]", text_color=(1, 1, 1))
                                    annot.set_colors(stroke=None, fill=(0, 0, 0))
                                    annot.update()
                                    extracted_data.append({"word": "[FIRMA AUTOGRAFA]", "label": "[FIRMA]", "entity": "SIGNATURE", "score": round(float(p["score"]), 4)})
                                    redacted_visual = True

                    # 1c. Targhe Veicoli nelle Immagini (YOLOS-Small)
                    if SETTINGS.get("enable_plate_vision", True) and (was_image or not text.strip()):
                        pl_det = get_plate_detector()
                        if pl_det is not None:
                            pl_preds = pl_det(pil_page)
                            pl_boxes = [p for p in pl_preds if float(p.get("score", 0.0)) >= 0.65]
                            if pl_boxes:
                                print(f"[{time.strftime('%H:%M:%S')}] Rilevate {len(pl_boxes)} targhe automobilistiche nell'immagine. Oscuramento...", flush=True)
                                for p in pl_boxes:
                                    b = p["box"]
                                    rect = fitz.Rect(b["xmin"], b["ymin"], b["xmax"], b["ymax"])
                                    annot = page.add_redact_annot(rect, fill=(0, 0, 0), text="[TARGA]", text_color=(1, 1, 1))
                                    annot.set_colors(stroke=None, fill=(0, 0, 0))
                                    annot.update()
                                    extracted_data.append({"word": "[TARGA VEICOLO]", "label": "[TARGA]", "entity": "LICENSE_PLATE", "score": round(float(p["score"]), 4)})
                                    redacted_visual = True

                    if redacted_visual:
                        page.apply_redactions(images=2, graphics=0)
                except Exception as e:
                    print(f"Errore nel rilevamento visivo IA: {e}", flush=True)

            # --- 2. BLOCCO OCR (SE LA PAGINA E' UNA SCANSIONE O IMMAGINE) ---
            if not text.strip():
                if not SETTINGS.get("enable_ocr", True) or ocr_reader is None:
                    continue

                print(f"[{time.strftime('%H:%M:%S')}] Rilevata scansione visiva/immagine. Attivazione OCR sulla pagina...", flush=True)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")

                results = ocr_reader.readtext(img_bytes)
                if not results:
                    continue

                ocr_text = " \n ".join([res[1] for res in results])
                raw_spans = classifier(ocr_text) + get_regex_spans(ocr_text)
                spans_classification = merge_and_sort_spans(filter_and_format_spans(raw_spans, ocr_text), ocr_text)
                processed_words = set()

                use_indexed = bool(SETTINGS.get("enable_deanonymize", True))
                for span in sorted(spans_classification, key=lambda x: x['start']):
                    word = span['word'].strip()
                    if not word or word in processed_words:
                        continue
                    processed_words.add(word)

                    base_label = span.get("replacement_label", "[DATI_SENSIBILI]")
                    indexed_label = get_or_create_indexed_label(word, base_label)
                    replacement = indexed_label if use_indexed else base_label

                    extracted_data.append({
                        "word": span["word"],
                        "label": replacement,
                        "entity": span.get("entity_group", span.get("entity", "PII")),
                        "score": float(span["score"])
                    })
                    word_lower = word.lower()

                    for res in results:
                        bbox, text_seg, conf = res
                        if word_lower in text_seg.lower() or text_seg.lower() in word_lower:
                            x0 = min(bbox[0][0], bbox[3][0]) / 2.0
                            y0 = min(bbox[0][1], bbox[1][1]) / 2.0
                            x1 = max(bbox[1][0], bbox[2][0]) / 2.0
                            y1 = max(bbox[2][1], bbox[3][1]) / 2.0

                            rect = fitz.Rect(x0, y0, x1, y1)

                            annot = page.add_redact_annot(rect, text=replacement, text_color=(1, 1, 1), fill=(0, 0, 0), cross_out=False)
                            annot.set_colors(stroke=None, fill=(0, 0, 0))
                            annot.update()

                page.apply_redactions(images=2, graphics=0)
                continue

            # --- 3. BLOCCO TESTO DIGITALE ---
            raw_spans = classifier(text) + get_regex_spans(text)
            spans_classification = merge_and_sort_spans(filter_and_format_spans(raw_spans, text), text)

            page_dict = page.get_text("dict")
            all_spans = []
            for block in page_dict.get("blocks", []):
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    for s in line["spans"]:
                        all_spans.append((fitz.Rect(s["bbox"]), s["size"]))

            spans_classification.sort(key=lambda x: x['start'])
            use_indexed = bool(SETTINGS.get("enable_deanonymize", True))

            from collections import defaultdict
            word_spans = defaultdict(list)
            for span in spans_classification:
                base_label = span.get("replacement_label", "[DATI_SENSIBILI]")
                indexed_label = get_or_create_indexed_label(span['word'].strip(), base_label)
                span["final_label"] = indexed_label if use_indexed else base_label
                word_spans[span['word'].strip()].append(span)

            for word, spans_for_word in word_spans.items():
                if not word:
                    continue

                for span in spans_for_word:
                    extracted_data.append({
                        "word": span["word"],
                        "label": span.get("final_label", span.get("replacement_label", "[DATI_SENSIBILI]")),
                        "entity": span.get("entity_group", span.get("entity", "PII")),
                        "score": float(span["score"])
                    })

                rects = page.search_for(word)
                matches = list(re.finditer(re.escape(word), text, flags=re.IGNORECASE))

                for span in spans_for_word:
                    occurrence_idx = -1
                    for i, match in enumerate(matches):
                        if abs(match.start() - span['start']) <= 2 or match.start() == span['start']:
                            occurrence_idx = i
                            break

                    if occurrence_idx == -1 and len(rects) == 1:
                        occurrence_idx = 0

                    if occurrence_idx != -1 and occurrence_idx < len(rects):
                        rect = rects[occurrence_idx]
                        replacement = span.get("final_label", span.get("replacement_label", "[DATI_SENSIBILI]"))

                        fontsize = rect.height * 0.75
                        for span_rect, size in all_spans:
                            if span_rect.intersects(rect):
                                fontsize = size
                                break

                        annot = page.add_redact_annot(
                            rect,
                            text=replacement,
                            text_color=(0, 0, 0),
                            fontsize=fontsize,
                            fill=False,
                            cross_out=False
                        )
                        annot.set_colors(stroke=None, fill=None)
                        annot.update()

            page.apply_redactions(images=0, graphics=0)

        out_ext = os.path.splitext(output_file)[1].lower()
        if out_ext == '.pdf':
            try:
                emb_count = doc.embfile_count()
                if emb_count > 0:
                    print(f"[{time.strftime('%H:%M:%S')}] Rilevati {emb_count} PDF incapsulati in {os.path.basename(input_file)}. Elaborazione...", flush=True)
                    import tempfile
                    with tempfile.TemporaryDirectory() as tmpdir:
                        for i in range(emb_count):
                            emb_name = doc.embfile_names()[i]
                            emb_data = doc.embfile_get(emb_name)
                            if emb_name.lower().endswith('.pdf') or emb_name.lower().endswith('.bin'):
                                tmp_in = os.path.join(tmpdir, "in_" + emb_name)
                                tmp_out = os.path.join(tmpdir, "out_" + emb_name)
                                with open(tmp_in, 'wb') as f:
                                    f.write(emb_data)
                                process_pdf(tmp_in, tmp_out, classifier, extracted_data, ocr_reader=ocr_reader)
                                with open(tmp_out, 'rb') as f:
                                    new_emb_data = f.read()
                                doc.embfile_upd(emb_name, new_emb_data)
            except Exception as e:
                print(f"Errore incapsulamento PDF in {input_file}: {e}", flush=True)

            doc.save(output_file, garbage=4, deflate=True, clean=True)
        else:
            # Salvataggio diretto come immagine (PNG, JPG, WEBP, BMP, TIFF)
            from PIL import Image
            page0 = doc[0]
            pix = page0.get_pixmap()
            mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            if out_ext in ['.jpg', '.jpeg', '.bmp'] and mode == "RGBA":
                img = img.convert("RGB")
            img.save(output_file)
    finally:
        if doc:
            doc.close()


def process_docx(input_file, output_file, classifier, extracted_data, ocr_reader=None):
    doc = docx.Document(input_file)

    def process_paragraphs(paragraphs):
        for para in paragraphs:
            if not para.text.strip():
                continue
            para.text = anonymize_string(para.text, classifier, extracted_data)

    def process_tables(tables):
        for table in tables:
            for row in table.rows:
                for cell in row.cells:
                    process_paragraphs(cell.paragraphs)

    process_paragraphs(doc.paragraphs)
    process_tables(doc.tables)

    for section in doc.sections:
        headers_footers = [
            section.header, section.first_page_header, section.even_page_header,
            section.footer, section.first_page_footer, section.even_page_footer
        ]
        for hf in headers_footers:
            if hf is not None and not hf.is_linked_to_previous:
                process_paragraphs(hf.paragraphs)
                process_tables(hf.tables)

    doc.save(output_file)
    process_embedded_files(output_file, classifier, extracted_data, ocr_reader=ocr_reader)


def process_xlsx(input_file, output_file, classifier, extracted_data, ocr_reader=None):
    from openpyxl.comments import Comment

    ext = os.path.splitext(input_file)[1].lower()
    wb = None
    try:
        wb = openpyxl.load_workbook(input_file, keep_vba=(ext == '.xlsm'))

        for sheet in wb.worksheets:
            new_title = anonymize_string(sheet.title, classifier, extracted_data)
            if new_title and new_title != sheet.title:
                sheet.title = new_title[:31]

            for row in sheet.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.value = anonymize_string(cell.value, classifier, extracted_data)

                    if cell.comment and cell.comment.text:
                        new_comment_text = anonymize_string(cell.comment.text, classifier, extracted_data)
                        if new_comment_text != cell.comment.text:
                            author = anonymize_string(cell.comment.author, classifier, extracted_data) if cell.comment.author else "Author"
                            cell.comment = Comment(new_comment_text, author)

        wb.save(output_file)
    finally:
        if wb and hasattr(wb, 'close'):
            wb.close()

    process_embedded_files(output_file, classifier, extracted_data, ocr_reader=ocr_reader)


def process_xls(input_file, output_file, classifier, extracted_data):
    try:
        rb = xlrd.open_workbook(input_file, formatting_info=True)
    except NotImplementedError:
        rb = xlrd.open_workbook(input_file)

    wb = copy(rb)
    for s in range(rb.nsheets):
        sheet = rb.sheet_by_index(s)
        w_sheet = wb.get_sheet(s)

        for rowx in range(sheet.nrows):
            for colx in range(sheet.ncols):
                val = sheet.cell_value(rowx, colx)
                if isinstance(val, str) and val.strip():
                    anonymized_text = anonymize_string(val, classifier, extracted_data)
                    w_sheet.write(rowx, colx, anonymized_text)

    wb.save(output_file)


def process_doc(input_file, output_file, classifier, extracted_data, ocr_reader=None):
    try:
        import win32com.client
    except ImportError:
        raise Exception("Manca pywin32 o Office non installato. File .doc ignorato.")
    import tempfile
    abs_in = os.path.abspath(input_file)
    with tempfile.TemporaryDirectory() as tmpdir:
        abs_out_docx = os.path.join(tmpdir, "converted.docx")
        try:
            word = win32com.client.Dispatch("Word.Application")
            word.DisplayAlerts = False
            doc = word.Documents.Open(abs_in, ConfirmConversions=False, ReadOnly=True)
            doc.SaveAs(abs_out_docx, 16)
            doc.Close()
            word.Quit()
        except Exception as e:
            try:
                word.Quit()
            except Exception:
                pass
            raise Exception(f"Conversione win32com fallita per vecchi .doc: {e}")

        process_docx(abs_out_docx, abs_out_docx, classifier, extracted_data, ocr_reader=ocr_reader)

        try:
            word = win32com.client.Dispatch("Word.Application")
            word.DisplayAlerts = False
            doc2 = word.Documents.Open(abs_out_docx, ConfirmConversions=False, ReadOnly=True)
            doc2.SaveAs(os.path.abspath(output_file), 0)
            doc2.Close()
            word.Quit()
        except Exception as e:
            try:
                word.Quit()
            except Exception:
                pass
            raise Exception(f"Salvataggio win32com fallito per vecchi .doc: {e}")


def process_csv(input_file, output_file, classifier, extracted_data):
    import csv
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as fin, open(output_file, 'w', encoding='utf-8', newline='') as fout:
        sample = fin.read(1024)
        fin.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except Exception:
            dialect = csv.excel

        reader = csv.reader(fin, dialect)
        writer = csv.writer(fout, dialect)

        for row in reader:
            new_row = [anonymize_string(cell, classifier, extracted_data) for cell in row]
            writer.writerow(new_row)


def process_xml(input_file, output_file, classifier, extracted_data):
    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(input_file)
        root = tree.getroot()

        def recurse_node(node):
            if node.text and node.text.strip():
                node.text = anonymize_string(node.text, classifier, extracted_data)
            if node.tail and node.tail.strip():
                node.tail = anonymize_string(node.tail, classifier, extracted_data)
            for child in node:
                recurse_node(child)

        recurse_node(root)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
    except Exception:
        process_txt(input_file, output_file, classifier, extracted_data)


def process_html(input_file, output_file, classifier, extracted_data):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise Exception("Manca beautifulsoup4. File HTML ignorato.")

    with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    for text_node in soup.find_all(string=True):
        if text_node.parent and text_node.parent.name not in ['script', 'style']:
            new_text = anonymize_string(str(text_node), classifier, extracted_data)
            if new_text != str(text_node):
                text_node.replace_with(new_text)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(str(soup))


def process_eml(input_file, output_file, classifier, extracted_data):
    import email
    from email import policy
    with open(input_file, 'rb') as f:
        msg = email.message_from_binary_file(f, policy=policy.default)

    for header in ['Subject', 'From', 'To', 'Cc']:
        if msg[header]:
            new_val = anonymize_string(str(msg[header]), classifier, extracted_data)
            try:
                msg.replace_header(header, new_val)
            except Exception:
                pass

    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get_filename():
            continue

        content_type = part.get_content_type()
        try:
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            text = payload.decode(part.get_content_charset('utf-8') or 'utf-8', errors='ignore')

            if content_type == 'text/plain':
                new_text = anonymize_string(text, classifier, extracted_data)
                part.set_payload(new_text.encode('utf-8'))
                part.set_charset('utf-8')
            elif content_type == 'text/html':
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(text, 'html.parser')
                    for text_node in soup.find_all(string=True):
                        if text_node.parent and text_node.parent.name not in ['script', 'style']:
                            new_t = anonymize_string(str(text_node), classifier, extracted_data)
                            if new_t != str(text_node):
                                text_node.replace_with(new_t)
                    part.set_payload(str(soup).encode('utf-8'))
                    part.set_charset('utf-8')
                except ImportError:
                    pass
        except Exception:
            pass

    with open(output_file, 'wb') as f:
        f.write(msg.as_bytes())


def process_opendocument(input_file, output_file, classifier, extracted_data):
    import zipfile
    import tempfile
    if not zipfile.is_zipfile(input_file):
        raise Exception("Invalid OpenDocument")
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_zip = os.path.join(tmpdir, "new_arch.zip")
        with zipfile.ZipFile(input_file, 'r') as zin:
            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == 'content.xml':
                        ext_file = os.path.join(tmpdir, "content.xml")
                        with open(ext_file, 'wb') as f:
                            f.write(data)
                        process_xml(ext_file, ext_file, classifier, extracted_data)
                        with open(ext_file, 'rb') as f:
                            new_data = f.read()
                        zout.writestr(item, new_data)
                    else:
                        zout.writestr(item, data)
        shutil.copy2(temp_zip, output_file)


def process_rtf(input_file, output_file, classifier, extracted_data, ocr_reader=None):
    try:
        import win32com.client
        import tempfile
        abs_in = os.path.abspath(input_file)
        with tempfile.TemporaryDirectory() as tmpdir:
            abs_out_docx = os.path.join(tmpdir, "converted.docx")
            word = win32com.client.Dispatch("Word.Application")
            word.DisplayAlerts = False
            doc = word.Documents.Open(abs_in, ConfirmConversions=False, ReadOnly=True)
            doc.SaveAs(abs_out_docx, 16)
            doc.Close()
            word.Quit()

            process_docx(abs_out_docx, abs_out_docx, classifier, extracted_data, ocr_reader=ocr_reader)

            word = win32com.client.Dispatch("Word.Application")
            word.DisplayAlerts = False
            doc2 = word.Documents.Open(abs_out_docx, ConfirmConversions=False, ReadOnly=True)
            doc2.SaveAs(os.path.abspath(output_file), 6)
            doc2.Close()
            word.Quit()
            return
    except Exception:
        with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        anonymized_text = anonymize_string(text, classifier, extracted_data)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(anonymized_text)


def process_pptx(input_file, output_file, classifier, extracted_data, ocr_reader=None):
    try:
        import pptx
    except ImportError:
        raise Exception("Manca python-pptx. File ignorato.")

    prs = pptx.Presentation(input_file)
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        text = run.text
                        if not text.strip():
                            continue
                        run.text = anonymize_string(text, classifier, extracted_data)

            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for paragraph in cell.text_frame.paragraphs:
                            for run in paragraph.runs:
                                text = run.text
                                if not text.strip():
                                    continue
                                run.text = anonymize_string(text, classifier, extracted_data)

    prs.save(output_file)
    process_embedded_files(output_file, classifier, extracted_data, ocr_reader=ocr_reader)


def process_ppt(input_file, output_file, classifier, extracted_data, ocr_reader=None):
    try:
        import win32com.client
    except ImportError:
        raise Exception("Manca pywin32 o Office non installato. File .ppt ignorato.")

    import tempfile
    abs_in = os.path.abspath(input_file)
    with tempfile.TemporaryDirectory() as tmpdir:
        abs_out_pptx = os.path.join(tmpdir, "converted.pptx")
        try:
            powerpoint = win32com.client.Dispatch("PowerPoint.Application")
            presentation = powerpoint.Presentations.Open(abs_in, WithWindow=False)
            presentation.SaveAs(abs_out_pptx, 24)
            presentation.Close()
            powerpoint.Quit()
        except Exception as e:
            try:
                powerpoint.Quit()
            except Exception:
                pass
            raise Exception(f"Conversione win32com fallita per vecchi .ppt: {e}")

        process_pptx(abs_out_pptx, output_file, classifier, extracted_data, ocr_reader=ocr_reader)


def process_zip(input_file, output_file, classifier, extracted_data, ocr_reader=None):
    import zipfile
    import tempfile
    if not zipfile.is_zipfile(input_file):
        raise Exception("Invalid ZIP")
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_zip = os.path.join(tmpdir, "new_arch.zip")
        with zipfile.ZipFile(input_file, 'r') as zin:
            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename.endswith('/'):
                        zout.writestr(item, data)
                        continue

                    inner_ext = os.path.splitext(item.filename)[1].lower()
                    ext_file = os.path.join(tmpdir, "inner_" + os.path.basename(item.filename))
                    with open(ext_file, 'wb') as f:
                        f.write(data)
                    out_ext_file = ext_file + ".out" + inner_ext
                    try:
                        if inner_ext == '.txt':
                            process_txt(ext_file, out_ext_file, classifier, extracted_data)
                        elif inner_ext in ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp']:
                            process_pdf(ext_file, out_ext_file, classifier, extracted_data, ocr_reader=ocr_reader)
                        elif inner_ext in ['.docx', '.docm']:
                            process_docx(ext_file, out_ext_file, classifier, extracted_data, ocr_reader=ocr_reader)
                        elif inner_ext in ['.xlsx', '.xlsm']:
                            process_xlsx(ext_file, out_ext_file, classifier, extracted_data, ocr_reader=ocr_reader)
                        elif inner_ext == '.xls':
                            process_xls(ext_file, out_ext_file, classifier, extracted_data)
                        elif inner_ext == '.rtf':
                            process_rtf(ext_file, out_ext_file, classifier, extracted_data, ocr_reader=ocr_reader)
                        elif inner_ext == '.pptx':
                            process_pptx(ext_file, out_ext_file, classifier, extracted_data, ocr_reader=ocr_reader)
                        elif inner_ext == '.ppt':
                            process_ppt(ext_file, out_ext_file, classifier, extracted_data, ocr_reader=ocr_reader)
                        elif inner_ext == '.doc':
                            process_doc(ext_file, out_ext_file, classifier, extracted_data, ocr_reader=ocr_reader)
                        elif inner_ext == '.csv':
                            process_csv(ext_file, out_ext_file, classifier, extracted_data)
                        elif inner_ext == '.xml':
                            process_xml(ext_file, out_ext_file, classifier, extracted_data)
                        elif inner_ext in ['.html', '.htm']:
                            process_html(ext_file, out_ext_file, classifier, extracted_data)
                        elif inner_ext == '.eml':
                            process_eml(ext_file, out_ext_file, classifier, extracted_data)
                        elif inner_ext in ['.odt', '.ods', '.odp']:
                            process_opendocument(ext_file, out_ext_file, classifier, extracted_data)
                        else:
                            zout.writestr(item, data)
                            continue

                        with open(out_ext_file, 'rb') as f:
                            new_data = f.read()
                        zout.writestr(item.filename, new_data)
                    except Exception:
                        zout.writestr(item, data)

        shutil.copy2(temp_zip, output_file)


def deanonymize_file(input_file, output_file, tag_map=None):
    """Ripristina i dati reali originali all'interno di un documento contenente tag [PERSONA_1], ecc."""
    if tag_map is None:
        tag_map = load_vault_tag_map()
    ext = os.path.splitext(input_file)[1].lower()
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

    if ext == '.txt' or ext == '.rtf':
        with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        restored = deanonymize_string(text, tag_map)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(restored)

    elif ext in ['.docx', '.docm']:
        doc = docx.Document(input_file)
        for p in doc.paragraphs:
            if p.text:
                p.text = deanonymize_string(p.text, tag_map)
        for t in doc.tables:
            for row in t.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        if p.text:
                            p.text = deanonymize_string(p.text, tag_map)
        for section in doc.sections:
            for hf in [section.header, section.first_page_header, section.even_page_header, section.footer, section.first_page_footer, section.even_page_footer]:
                if hf is not None and not hf.is_linked_to_previous:
                    for p in hf.paragraphs:
                        if p.text:
                            p.text = deanonymize_string(p.text, tag_map)
                    for t in hf.tables:
                        for row in t.rows:
                            for cell in row.cells:
                                for p in cell.paragraphs:
                                    if p.text:
                                        p.text = deanonymize_string(p.text, tag_map)
        doc.save(output_file)

    elif ext in ['.xlsx', '.xlsm']:
        from openpyxl.comments import Comment
        wb = openpyxl.load_workbook(input_file, keep_vba=(ext == '.xlsm'))
        for sheet in wb.worksheets:
            sheet.title = deanonymize_string(sheet.title, tag_map)[:31]
            for row in sheet.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.value = deanonymize_string(cell.value, tag_map)
                    if cell.comment and cell.comment.text:
                        cell.comment = Comment(deanonymize_string(cell.comment.text, tag_map), cell.comment.author or "Author")
        wb.save(output_file)
        wb.close()

    elif ext == '.csv':
        import csv
        with open(input_file, 'r', encoding='utf-8', errors='ignore') as fin, open(output_file, 'w', encoding='utf-8', newline='') as fout:
            sample = fin.read(1024)
            fin.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.reader(fin, dialect)
            writer = csv.writer(fout, dialect)
            for row in reader:
                writer.writerow([deanonymize_string(c, tag_map) for c in row])

    elif ext == '.xml':
        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(input_file)
            root = tree.getroot()
            def _rec(n):
                if n.text:
                    n.text = deanonymize_string(n.text, tag_map)
                if n.tail:
                    n.tail = deanonymize_string(n.tail, tag_map)
                for ch in n:
                    _rec(ch)
            _rec(root)
            tree.write(output_file, encoding='utf-8', xml_declaration=True)
        except Exception:
            with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
                t = f.read()
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(deanonymize_string(t, tag_map))

    elif ext in ['.html', '.htm']:
        from bs4 import BeautifulSoup
        with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        for tn in soup.find_all(string=True):
            if tn.parent and tn.parent.name not in ['script', 'style']:
                nt = deanonymize_string(str(tn), tag_map)
                if nt != str(tn):
                    tn.replace_with(nt)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(str(soup))

    elif ext == '.eml':
        import email
        from email import policy
        with open(input_file, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        for h in ['Subject', 'From', 'To', 'Cc']:
            if msg[h]:
                try:
                    msg.replace_header(h, deanonymize_string(str(msg[h]), tag_map))
                except Exception:
                    pass
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart' or part.get_filename():
                continue
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True)
            if payload and ctype in ['text/plain', 'text/html']:
                txt = payload.decode(part.get_content_charset('utf-8') or 'utf-8', errors='ignore')
                part.set_payload(deanonymize_string(txt, tag_map).encode('utf-8'))
                part.set_charset('utf-8')
        with open(output_file, 'wb') as f:
            f.write(msg.as_bytes())

    elif ext in ['.odt', '.ods', '.odp']:
        import zipfile
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_zip = os.path.join(tmpdir, "out.zip")
            with zipfile.ZipFile(input_file, 'r') as zin, zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == 'content.xml':
                        txt = data.decode('utf-8', errors='ignore')
                        data = deanonymize_string(txt, tag_map).encode('utf-8')
                    zout.writestr(item, data)
            shutil.copy2(temp_zip, output_file)

    elif ext == '.pptx':
        import pptx
        prs = pptx.Presentation(input_file)
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.has_text_frame:
                    for p in shape.text_frame.paragraphs:
                        for r in p.runs:
                            if r.text:
                                r.text = deanonymize_string(r.text, tag_map)
                if shape.has_table:
                    for row in shape.table.rows:
                        for cell in row.cells:
                            for p in cell.text_frame.paragraphs:
                                for r in p.runs:
                                    if r.text:
                                        r.text = deanonymize_string(r.text, tag_map)
        prs.save(output_file)

    elif ext == '.pdf':
        doc = fitz.open(input_file)
        try:
            sorted_tags = sorted(tag_map.keys(), key=lambda k: len(k), reverse=True)
            for page in doc:
                modified = False
                for tag in sorted_tags:
                    orig_word = tag_map[tag]
                    if not orig_word:
                        continue
                    variants = [tag, tag.replace("_", " ")]
                    for var in variants:
                        rects = page.search_for(var)
                        for rect in rects:
                            fontsize = max(8.0, rect.height * 0.72)
                            annot = page.add_redact_annot(
                                rect,
                                text=orig_word,
                                text_color=(0, 0, 0),
                                fontsize=fontsize,
                                fill=(1, 1, 1),
                                cross_out=False
                            )
                            annot.update()
                            modified = True
                if modified:
                    page.apply_redactions(images=0, graphics=0)
            doc.save(output_file, garbage=4, deflate=True, clean=True)
        finally:
            doc.close()

    else:
        shutil.copy2(input_file, output_file)


def main():
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    if os.path.exists(STOP_FLAG):
        try:
            os.remove(STOP_FLAG)
        except Exception:
            pass

    if os.path.exists(READY_FLAG):
        try:
            os.remove(READY_FLAG)
        except Exception:
            pass

    print(f"[{time.strftime('%H:%M:%S')}] Inizializzazione Germano AI Daemon v0.50-alpha...", flush=True)
    for d in [INPUT_DIR, OUTPUT_DIR, PROCESSED_DIR, FAILED_DIR, EXTRACTED_DIR]:
        os.makedirs(d, exist_ok=True)

    import torch
    from transformers import pipeline

    reload_settings()
    hardware_mode = SETTINGS.get("hardware_mode", "gpu_fallback")
    device = "cpu"

    if hardware_mode in ["gpu", "gpu_fallback"]:
        if torch.cuda.is_available():
            device = "cuda"
            print(f"[{time.strftime('%H:%M:%S')}] Hardware Rilevato: NVIDIA GPU (CUDA disponibile). Accelerazione attivata.", flush=True)
        else:
            try:
                import torch_directml  # type: ignore
                if torch_directml.is_available():
                    device = torch_directml.device()
                    print(f"[{time.strftime('%H:%M:%S')}] Hardware Rilevato: AMD/Intel GPU (DirectML disponibile). Accelerazione attivata.", flush=True)
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Nessuna GPU compatibile rilevata. Avvio su CPU.", flush=True)
            except Exception:
                print(f"[{time.strftime('%H:%M:%S')}] Elaborazione impostata su Processore Centrale (CPU).", flush=True)
    else:
        print(f"[{time.strftime('%H:%M:%S')}] Modalita' CPU selezionata.", flush=True)

    print(f"[{time.strftime('%H:%M:%S')}] Caricamento Modello NLP Privacy Filter in memoria (100% Offline)...", flush=True)
    try:
        model_path = os.path.join(BASE_DIR, "models", "privacy-filter")
        if not os.path.exists(model_path) or not os.listdir(model_path):
            raise FileNotFoundError(f"Modello locale non trovato in {model_path}")

        raw_classifier = pipeline(
            task="token-classification",
            model=model_path,
            tokenizer=model_path,
            aggregation_strategy="simple",
            device=device,
            model_kwargs={"dtype": torch.float32}
        )

        ita_ner_pipe = None
        ita_ner_path = os.path.join(BASE_DIR, "models", "italian-ner-xxl")
        if os.path.exists(ita_ner_path) and os.listdir(ita_ner_path):
            try:
                print(f"[{time.strftime('%H:%M:%S')}] Caricamento Modello Specialistico Italiano (Italian_NER_XXL_v2 - 58 categorie)...", flush=True)
                ita_ner_pipe = pipeline(
                    task="token-classification",
                    model=ita_ner_path,
                    tokenizer=ita_ner_path,
                    aggregation_strategy="simple",
                    device=device,
                    model_kwargs={"dtype": torch.float32}
                )
            except Exception as e_ita:
                print(f"[{time.strftime('%H:%M:%S')}] Avviso caricamento Italian_NER_XXL: {e_ita}", flush=True)

        class SafeClassifier:
            def __init__(self, pipe, ita_pipe=None, threshold=0.0):
                self.pipe = pipe
                self.ita_pipe = ita_pipe
                self.fallback_done = False
                self.threshold = threshold

            def __call__(self, text):
                if not isinstance(text, str) or not text.strip():
                    return []
                res = []
                try:
                    if SETTINGS.get("enable_model_velvet", True) and self.pipe is not None:
                        res.extend(list(self.pipe(text)))
                    if SETTINGS.get("enable_model_italian_ner", True) and self.ita_pipe is not None:
                        ita_min_score = max(self.threshold, 0.70)
                        for s in self.ita_pipe(text):
                            if float(s.get("score", 0.0)) >= ita_min_score:
                                res.append(s)
                except Exception as e:
                    if SETTINGS.get("hardware_mode", "gpu_fallback") == "gpu_fallback" and not self.fallback_done:
                        print(f"[{time.strftime('%H:%M:%S')}] ATTENZIONE: Fallback su CPU attivato ('{str(e)[:60]}').", flush=True)
                        if self.pipe is not None:
                            self.pipe.model = self.pipe.model.to("cpu")
                            self.pipe.device = torch.device("cpu")
                        if self.ita_pipe is not None:
                            self.ita_pipe.model = self.ita_pipe.model.to("cpu")
                            self.ita_pipe.device = torch.device("cpu")
                        self.fallback_done = True
                        if SETTINGS.get("enable_model_velvet", True) and self.pipe is not None:
                            res = list(self.pipe(text))
                    else:
                        raise e
                return [s for s in res if float(s.get("score", 0.0)) >= self.threshold]

        classifier = SafeClassifier(raw_classifier, ita_pipe=ita_ner_pipe, threshold=float(SETTINGS.get("ai_threshold", 0.0)))
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ERRORE CRITICO caricamento modello NLP: {str(e)}", flush=True)
        cleanup_flags()
        sys.exit(1)

    print(f"[{time.strftime('%H:%M:%S')}] Caricamento Motore OCR (EasyOCR Locale)...", flush=True)
    try:
        import easyocr  # type: ignore
        easyocr_dir = os.path.join(BASE_DIR, "models", "easyocr")
        os.makedirs(easyocr_dir, exist_ok=True)
        use_gpu = True if torch.cuda.is_available() and device == "cuda" else False
        ocr_reader = easyocr.Reader(
            ['it', 'en'],
            gpu=use_gpu,
            verbose=False,
            download_enabled=False,
            model_storage_directory=easyocr_dir,
            user_network_directory=easyocr_dir
        )
        print(f"[{time.strftime('%H:%M:%S')}] Motore OCR EasyOCR caricato con successo.", flush=True)
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Avviso caricamento OCR: {str(e)}", flush=True)
        ocr_reader = None

    print(f"[{time.strftime('%H:%M:%S')}] Avvio Server Proxy Interno sulla porta 8001...", flush=True)

    import threading
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

    class ReusableThreadingHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True

    class InternalProxyAPI(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/internal/health':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == '/internal/anonymize_text':
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode('utf-8')
                try:
                    reload_settings(classifier)
                    data = json.loads(body)
                    text = data.get("text", "")
                    force_anon = bool(data.get("force_anonymize", False))
                    ext_data = []

                    # Se lo switch di de-anonimizzazione è attivo e il testo è una risposta dell'AI che contiene
                    # già etichette del Vault (es. [PERSONA_1]), rimette automaticamente a posto i dati veri!
                    if not force_anon and SETTINGS.get("enable_deanonymize", True) and text_contains_vault_tags(text):
                        restored = deanonymize_string(text)
                        response = {
                            "anonymized": restored,
                            "restored": restored,
                            "auto_restored": True,
                            "extracted_data": []
                        }
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps(response).encode('utf-8'))
                        return

                    spans = classifier(text) + get_regex_spans(text)
                    if spans:
                        spans = merge_and_sort_spans(filter_and_format_spans(spans, text), text)

                        word_to_label = {}
                        spans_forward = sorted(spans, key=lambda x: x['start'])
                        for span in spans_forward:
                            word = span["word"]
                            if word not in word_to_label:
                                base_label = span.get('replacement_label', '[DATI_SENSIBILI]')
                                indexed_label = get_or_create_indexed_label(word, base_label)
                                word_to_label[word] = indexed_label

                        anonymized = text
                        for span in spans:
                            word = span["word"]
                            indexed_label = word_to_label[word]
                            ext_data.append({
                                "word": word,
                                "label": indexed_label,
                                "entity": span.get("entity_group", span.get("entity", "PII")),
                                "score": round(float(span.get("score", 1.0)), 4)
                            })
                            anonymized = anonymized[:span['start']] + indexed_label + anonymized[span['end']:]
                    else:
                        anonymized = text

                    response = {"anonymized": anonymized, "extracted_data": ext_data}

                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(str(e).encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    def start_internal_server():
        try:
            server = ReusableThreadingHTTPServer(('127.0.0.1', 8001), InternalProxyAPI)
            server.serve_forever()
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Internal proxy server error: {e}", flush=True)

    threading.Thread(target=start_internal_server, daemon=True).start()

    with open(READY_FLAG, "w", encoding="utf-8") as f:
        f.write("1")

    print(f"[{time.strftime('%H:%M:%S')}] Sistema PRONTO. In ascolto continuo su cartella input/ e API Proxy...", flush=True)

    while True:
        if os.path.exists(STOP_FLAG):
            print(f"[{time.strftime('%H:%M:%S')}] Segnale di arresto ricevuto. Chiusura sicura del demone...", flush=True)
            try:
                os.remove(STOP_FLAG)
            except Exception:
                pass
            cleanup_flags()
            break

        reload_settings(classifier)

        found_files = []
        for root, dirs, files in os.walk(INPUT_DIR):
            for file in files:
                found_files.append(os.path.join(root, file))

        if not found_files:
            time.sleep(1.0)
            continue

        for input_file in found_files:
            if os.path.exists(STOP_FLAG):
                break
            if not os.path.exists(input_file):
                continue

            reload_settings(classifier)

            rel_path = os.path.relpath(input_file, INPUT_DIR)
            output_file = os.path.join(OUTPUT_DIR, rel_path)
            processed_file = os.path.join(PROCESSED_DIR, rel_path)

            try:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                os.makedirs(os.path.dirname(processed_file), exist_ok=True)

                # RILEVAMENTO AUTOMATICO RITORNO DALL'AI:
                # Se lo switch 'enable_deanonymize' è attivo e il file contiene già tag del Vault (es. [PERSONA_1]),
                # Germano capisce da solo che è un documento di ritorno dall'AI e rimette automaticamente i dati veri!
                if SETTINGS.get("enable_deanonymize", True) and file_contains_vault_tags(input_file):
                    print(f"[{time.strftime('%H:%M:%S')}] Rilevato file di ritorno dall'AI ({rel_path}). Ripristino automatico dati veri in corso...", flush=True)
                    deanonymize_file(input_file, output_file)
                    if os.path.exists(processed_file):
                        os.remove(processed_file)
                    if os.path.exists(input_file):
                        shutil.move(input_file, processed_file)
                    print(f"[{time.strftime('%H:%M:%S')}] Completato ripristino automatico dati veri in output/: {rel_path}", flush=True)
                    continue

                print(f"[{time.strftime('%H:%M:%S')}] Elaborazione in corso: {rel_path}...", flush=True)

                ext = os.path.splitext(input_file)[1].lower()
                success = False
                is_failed = False
                extracted_data = []

                def run_task():
                    if ext == '.txt':
                        process_txt(input_file, output_file, classifier, extracted_data)
                    elif ext in ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp']:
                        process_pdf(input_file, output_file, classifier, extracted_data, ocr_reader=ocr_reader)
                    elif ext in ['.docx', '.docm']:
                        process_docx(input_file, output_file, classifier, extracted_data, ocr_reader=ocr_reader)
                    elif ext in ['.xlsx', '.xlsm']:
                        process_xlsx(input_file, output_file, classifier, extracted_data, ocr_reader=ocr_reader)
                    elif ext == '.xls':
                        process_xls(input_file, output_file, classifier, extracted_data)
                    elif ext == '.rtf':
                        process_rtf(input_file, output_file, classifier, extracted_data, ocr_reader=ocr_reader)
                    elif ext == '.pptx':
                        process_pptx(input_file, output_file, classifier, extracted_data, ocr_reader=ocr_reader)
                    elif ext == '.ppt':
                        process_ppt(input_file, output_file, classifier, extracted_data, ocr_reader=ocr_reader)
                    elif ext == '.doc':
                        process_doc(input_file, output_file, classifier, extracted_data, ocr_reader=ocr_reader)
                    elif ext == '.csv':
                        process_csv(input_file, output_file, classifier, extracted_data)
                    elif ext == '.xml':
                        process_xml(input_file, output_file, classifier, extracted_data)
                    elif ext in ['.html', '.htm']:
                        process_html(input_file, output_file, classifier, extracted_data)
                    elif ext == '.eml':
                        process_eml(input_file, output_file, classifier, extracted_data)
                    elif ext in ['.odt', '.ods', '.odp']:
                        process_opendocument(ext_file=input_file, output_file=output_file, classifier=classifier, extracted_data=extracted_data) if False else process_opendocument(input_file, output_file, classifier, extracted_data)
                    elif ext == '.zip':
                        process_zip(input_file, output_file, classifier, extracted_data, ocr_reader=ocr_reader)
                    else:
                        return "unsupported"
                    return "success"

                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = executor.submit(run_task)
                try:
                    result = future.result(timeout=300)
                    if result == "unsupported":
                        raise Exception(f"Formato file non supportato: {ext}")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] Completato: {rel_path} ({len(extracted_data)} elementi censurati).", flush=True)
                        success = True
                except concurrent.futures.TimeoutError:
                    print(f"[{time.strftime('%H:%M:%S')}] [TIMEOUT] Elaborazione oltre 5 minuti su {rel_path}. Spostamento in failed.", flush=True)
                    is_failed = True
                finally:
                    executor.shutdown(wait=False)

                if success:
                    try:
                        extracted_file = os.path.join(EXTRACTED_DIR, rel_path + ".json")
                        os.makedirs(os.path.dirname(extracted_file), exist_ok=True)
                        with open(extracted_file, "w", encoding="utf-8") as f:
                            json.dump(extracted_data, f, indent=4, ensure_ascii=False)
                    except Exception as e:
                        print(f"Impossibile salvare report audit per {rel_path}: {str(e)}", flush=True)

                    try:
                        if os.path.exists(processed_file):
                            os.remove(processed_file)
                        if os.path.exists(input_file):
                            shutil.move(input_file, processed_file)
                    except Exception as e:
                        print(f"Impossibile spostare {rel_path} in processed: {str(e)}", flush=True)
                elif is_failed:
                    raise Exception("Process failed or timed out.")

            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] [ERRORE] Impossibile processare {rel_path}: {str(e)}", flush=True)
                try:
                    failed_file = os.path.join(FAILED_DIR, rel_path)
                    try:
                        os.makedirs(os.path.dirname(failed_file), exist_ok=True)
                    except Exception:
                        import hashlib
                        short_hash = hashlib.md5(rel_path.encode('utf-8')).hexdigest()
                        ext = os.path.splitext(input_file)[1]
                        failed_file = os.path.join(FAILED_DIR, f"error_{short_hash[:8]}{ext}")

                    if os.path.exists(failed_file):
                        os.remove(failed_file)
                    if os.path.exists(input_file):
                        shutil.move(input_file, failed_file)
                except Exception as fatal_e:
                    print(f"FATALE: Impossibile spostare in failed: {str(fatal_e)}", flush=True)

            try:
                input_sub_dir = os.path.dirname(input_file)
                if input_sub_dir != INPUT_DIR and os.path.exists(input_sub_dir) and not os.listdir(input_sub_dir):
                    os.rmdir(input_sub_dir)
            except Exception:
                pass


if __name__ == "__main__":
    main()
