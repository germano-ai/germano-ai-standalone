"""Rilevamento deterministico (RegEx validate a checksum matematico) e post-elaborazione degli span dei modelli IA.

In accordo con l'architettura 'Meno RegEx, Più AI', le euristiche fragili su linguaggio naturale
(indirizzi, toponimi, ruoli professionali, date colloquiali, organi catastali e societari)
sono state rimosse e delegate ai modelli neurali (Sistema 1 / Sistema 2).
Qui rimangono esclusivamente i verificatori deterministici e crittografici (IBAN MOD-97,
Codice Fiscale, Algoritmo di Luhn, Partite IVA, Secret Keys e pattern rigidi ad alta entropia).
"""
import re
from bisect import bisect_right

from .vault import ANY_TAG_RE

# --------------------------------------------------------------------------------------
# Categorie: gruppo (modello/regex) -> (etichetta base, chiave di configurazione)
# --------------------------------------------------------------------------------------
CATEGORY_MAP = {
    # privacy-filter + RegEx
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
    # Italian_NER_XXL_v2 (58 classi)
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
    "STATO_CIVILE": ("[STATO_CIVILE]", "censor_civil_status"),
    # Categorie personalizzate zero-shot (GLiNER2-PII)
    "CUSTOM_PII": ("[DATO_PERSONALIZZATO]", "censor_custom"),
}

FALLBACK_LABEL = "[DATI_SENSIBILI]"
ORG_LABEL = "[AZIENDA/ENTE]"
PERSON_LABEL = "[PERSONA]"
EMAIL_LABEL = "[EMAIL]"

_BIOES_RE = re.compile(r"^[BIESL]-")


def categorize(group):
    g = _BIOES_RE.sub("", str(group or ""))
    label, key = CATEGORY_MAP.get(g, (FALLBACK_LABEL, None))
    return g, label, key


class Span:
    __slots__ = ("start", "end", "group", "label", "key", "score", "source", "length_hint", "status")

    def __init__(self, start, end, group, label, key, score=1.0, source="model", status="confirmed"):
        self.start = start
        self.end = end
        self.group = group
        self.label = label
        self.key = key
        self.score = float(score)
        self.source = source
        self.length_hint = end - start
        self.status = status

    def __repr__(self):
        return f"Span({self.start},{self.end},{self.group},{self.label},{self.score:.2f},{self.source},{self.status})"


def _priority(sp):
    return (1 if sp.source == "regex" else 0, sp.length_hint, sp.score)


# --------------------------------------------------------------------------------------
# Validatori Matematici e Algoritmici
# --------------------------------------------------------------------------------------

def _iban_valid(s):
    s = s.upper()
    if len(s) < 15 or len(s) > 34 or not s[:2].isalpha() or not s[2:4].isdigit():
        return False
    r = s[4:] + s[:4]
    num = []
    for ch in r:
        if ch.isdigit():
            num.append(ch)
        elif "A" <= ch <= "Z":
            num.append(str(ord(ch) - 55))
        else:
            return False
    try:
        return int("".join(num)) % 97 == 1
    except ValueError:
        return False


def _luhn(digits):
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _piva_valid(d):
    if len(d) != 11 or not d.isdigit():
        return False
    s = 0
    for i in range(10):
        n = ord(d[i]) - 48
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        s += n
    return (10 - s % 10) % 10 == ord(d[10]) - 48


_IBAN_LEN = {
    "IT": 27, "SM": 27, "VA": 22, "DE": 22, "FR": 27, "ES": 24, "GB": 22, "CH": 21, "AT": 20, "BE": 16,
    "NL": 18, "PT": 25, "IE": 22, "LU": 20, "PL": 28, "GR": 27, "HR": 21, "SI": 19, "RO": 24, "BG": 22,
    "CZ": 24, "SK": 24, "HU": 28, "DK": 18, "SE": 24, "FI": 18, "NO": 15, "MT": 31, "CY": 28, "LT": 20,
    "LV": 21, "EE": 20, "LI": 21, "MC": 27, "AL": 28, "RS": 22, "TR": 26, "UA": 29,
}

_DATE_LIKE_RE = re.compile(r"^\d{1,2}[ ./\-]\d{1,2}[ ./\-]\d{2,4}$")

# --------------------------------------------------------------------------------------
# Pattern Rigidi a Checksum ed Entropia Elevata
# --------------------------------------------------------------------------------------
_UPC = "A-ZÀ-ÖØ-Þ"
_WC = r"\wÀ-ÖØ-öø-ÿ"

EMAIL_RE = re.compile(
    r"(?<![\w.+\-])[A-Za-z0-9][A-Za-z0-9._%+\-]*@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,24}(?![\w\-])"
)
_CFD = "0-9LMNPQRSTUVlmnpqrstuv"
CF_RE = re.compile(
    rf"(?<![A-Za-z0-9])[A-Za-z]{{6}}[{_CFD}]{{2}}[ABCDEHLMPRSTabcdehlmprst][{_CFD}]{{2}}[A-Za-z][{_CFD}]{{3}}[A-Za-z](?![A-Za-z0-9])"
)
CF_OCR_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{6}[0-9A-Z]{2}[A-Z][0-9A-Z]{2}[A-Z][0-9A-Z]{3}[A-Z](?![A-Za-z0-9])")
PIVA_CTX_RE = re.compile(
    r"(?i)\b(?:p\.?\s?iva|partita\s+i\.?v\.?a\.?|vat(?:\s+(?:no|number|n|id))?\.?|c\.?\s?f\.?|cod(?:ice)?\.?\s+fiscale)"
    r"[ \t]*(?:[:.°n#][ \t]*)*(?:IT[ \t]?)?(\d{11})(?!\d)"
)
PIVA_IT_RE = re.compile(r"(?<![A-Za-z0-9])IT[ \t]?(\d{11})(?!\d)")
IBAN_START_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2})(\d{2})(?=[ \-]?[A-Za-z0-9])")
CARD_RE = re.compile(r"(?<![\d\-])(?:\d[ \-]?){12,18}\d(?![\d\-])")
PHONE_STRICT_RE = re.compile(r"(?<![\w+])(?:\+|00)39[ \t]?3\d{2}[ .\-]?\d{6,7}(?![\d])")
CIE_RE = re.compile(r"(?<![A-Za-z0-9])[Cc][A-Za-z]\d{5}[A-Za-z]{2}(?![A-Za-z0-9])")
PLATE_RE = re.compile(r"(?<![A-Za-z0-9])[A-HJ-NPR-TV-Z]{2}[ ]?\d{3}[ ]?[A-HJ-NPR-TV-Z]{2}(?![A-Za-z0-9])")
IPV4_RE = re.compile(
    r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?!\d|\.\d)"
)
SECRET_RES = [
    re.compile(r"(?<![\w\-])sk-(?:proj-|ant-(?:api\d{2}-|admin\d{2}-)?)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?<![\w])gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"(?<![\w])github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"(?<![\w])(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])"),
    re.compile(r"(?<![\w\-])AIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"(?<![\w\-])xox[abposr]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"(?<![\w\-])eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    re.compile(r"-----BEGIN (?:[A-Z]+ ){0,4}PRIVATE KEY-----(?:(?!-----BEGIN )[A-Za-z0-9+/=\s:,\-._]){20,16384}?-----END (?:[A-Z]+ ){0,4}PRIVATE KEY-----"),
]


_EMAIL_LOCAL = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._%+-")
_EMAIL_FIRST = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
# la parte di EMAIL_RE dopo la chiocciola (dominio)
_EMAIL_DOMAIN_RE = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,24}(?![\w\-])"
)


def email_spans(text):
    """Stessi risultati di EMAIL_RE.finditer(text) - [(inizio, fine)] - in tempo lineare.

    EMAIL_RE cerca la parte locale da ogni posizione di partenza ammessa: su un testo con «%» frequenti (dati
    URL-encoded: dopo «%» puo' iniziare un indirizzo) ogni partenza rilegge tutto il resto della sequenza prima di
    scoprire che la chiocciola non c'e'. Tempo quadratico: 1,1 s per 40.000 caratteri, minuti per un file di qualche MB.
    Qui si parte dalle chiocciole: per ciascuna si verifica il dominio e si risale alla prima partenza valida della
    sequenza che la precede (stessa regola: carattere iniziale alfanumerico, non preceduto da [\\w.+-])."""
    out = []
    last_end = 0
    a = text.find("@")
    while a != -1:
        m = _EMAIL_DOMAIN_RE.match(text, a + 1) if a > last_end else None
        if m is not None:
            r = a
            while r > last_end and text[r - 1] in _EMAIL_LOCAL:
                r -= 1
            p = r
            while p < a:
                if text[p] in _EMAIL_FIRST:
                    prev = text[p - 1] if p else ""
                    if not prev or not (prev in ".+-_" or prev.isalnum()):
                        break
                p += 1
            if p < a:
                out.append((p, m.end()))
                last_end = m.end()
                a = text.find("@", last_end)
                continue
        a = text.find("@", a + 1)
    return out


def _add(spans, s, e, group, score=1.0):
    if e > s:
        spans.append((s, e, group, score))


def _iban_spans(text, spans, ocr):
    for m in IBAN_START_RE.finditer(text):
        country = m.group(1).upper()
        pos = m.end()
        chars, ends = [], []
        prev_sep = False
        i = pos
        n = len(text)
        while i < n and len(chars) < 30:
            ch = text[i]
            if ch.isascii() and ch.isalnum():
                chars.append(ch.upper())
                ends.append(i + 1)
                prev_sep = False
            elif ch in " -" and not prev_sep:
                prev_sep = True
            else:
                break
            i += 1
        if len(chars) < 11:
            continue
        head = country + m.group(2)
        want = _IBAN_LEN.get(country)
        lengths = [want] if want else range(min(34, len(chars) + 4), 14, -1)
        found = False
        for total in lengths:
            body_len = total - 4
            if body_len > len(chars) or body_len < 11:
                continue
            cand = head + "".join(chars[:body_len])
            if _iban_valid(cand) or (ocr and country == "IT" and total == 27):
                _add(spans, m.start(), ends[body_len - 1], "account_number")
                found = True
                break
        if not found and ocr and country == "IT" and len(chars) >= 23:
            _add(spans, m.start(), ends[min(len(chars), 23) - 1], "account_number", 0.9)


def regex_spans(text, ocr=False):
    """Span grezzi (start, end, gruppo, score) da sole regole deterministiche/matematiche."""
    spans = []
    if not isinstance(text, str) or not text:
        return spans
    if "@" in text:
        for s, e in email_spans(text):
            _add(spans, s, e, "private_email")
    for m in CF_RE.finditer(text):
        _add(spans, m.start(), m.end(), "cf_iva")
    if ocr:
        for m in CF_OCR_RE.finditer(text):
            w = m.group(0)
            digits = sum(1 for i in (6, 7, 9, 10, 12, 13, 14) if w[i].isdigit())
            if digits >= 2:
                _add(spans, m.start(), m.end(), "cf_iva", 0.9)
    for m in PIVA_CTX_RE.finditer(text):
        _add(spans, m.start(1), m.end(1), "cf_iva")
    for m in PIVA_IT_RE.finditer(text):
        if _piva_valid(m.group(1)) or ocr:
            _add(spans, m.start(), m.end(), "cf_iva")
    _iban_spans(text, spans, ocr)
    for m in CARD_RE.finditer(text):
        d = re.sub(r"\D", "", m.group(0))
        if 13 <= len(d) <= 19 and d[0] in "23456" and _luhn(d):
            _add(spans, m.start(), m.end(), "account_number")
    for m in PHONE_STRICT_RE.finditer(text):
        _add(spans, m.start(), m.end(), "private_phone")
    for m in CIE_RE.finditer(text):
        _add(spans, m.start(), m.end(), "plates_docs")
    for m in PLATE_RE.finditer(text):
        _add(spans, m.start(), m.end(), "plates_docs")
    for m in IPV4_RE.finditer(text):
        ip = m.group(0)
        if ip.startswith("127.") or ip == "0.0.0.0" or ip.startswith("255."):
            continue
        _add(spans, m.start(), m.end(), "private_url")
    for rx in SECRET_RES:
        for m in rx.finditer(text):
            _add(spans, m.start(), m.end(), "secret")
    return spans


# --------------------------------------------------------------------------------------
# Post-elaborazione
# --------------------------------------------------------------------------------------
_HONORIFIC = (
    r"sig(?:nor(?:a|ina|e|i)?|\.ra|\.na|ra|na|\.)?|dott(?:oressa|ore|or|\.ssa|ssa|\.)?|dr\.?(?:ssa)?|"
    r"avv(?:ocatessa|ocato|\.)?|ing(?:egnere|\.)?|prof(?:essoressa|essore|\.ssa|\.)?|arch(?:itetto|\.)?|"
    r"geom(?:etra|\.)?|rag(?:ioniere|\.)?|on(?:orevole|\.)|mons\.|don|suor|egr(?:egio|egia|\.)|"
    r"gent(?:ile|\.mo|\.ma|\.)|spett(?:\.le|abile)|sig\.ri"
)
_FIELD = (
    r"c\.\s?f\.|cf|cod(?:ice)?\.?\s+fiscale|p\.?\s?iva|partita\s+iva|tel(?:efono|\.)?|cell(?:ulare|\.)?|fax|"
    r"e-?mail|mail|pec|iban|bic|swift|nato\s+(?:a|il|in)|nata\s+(?:a|il|in)|residente\s+(?:a|in)|"
    r"domiciliat[oa]\s+(?:a|in)|con\s+sede\s+(?:a|in|legale\s+in)|sit[oa]\s+in"
)
_PREFIX_RE = re.compile(
    r"(?i)(?:(?:(?:il|lo|la|i|gli|le|al|alla|del|della|dal|dalla)\s+)?(?:" + _HONORIFIC + r"|" + _FIELD + r")(?![\w])[.:]?[ \t]*)+"
)
_LEAD_CHARS = set(" \t\r\n([{«“\"'.,;:-—")
_TRAIL_CHARS = set(" \t\r\n.,;:!?)]}»”\"'-—")
_SECRET_TRAIL_CHARS = set(" \t\r\n.,;:)]}»”\"'")
SECRET_LABEL = "[SEGRETO]"


def trim_span(text, s, e, label):
    while s < e and text[s] in _LEAD_CHARS:
        s += 1
    trail = _SECRET_TRAIL_CHARS if label == SECRET_LABEL else _TRAIL_CHARS
    while e > s and text[e - 1] in trail:
        c = text[e - 1]
        if c == "." and label == ORG_LABEL and "." in text[max(s, e - 6):e - 1]:
            break
        if c == ")" and "(" in text[s:e - 1]:
            break
        if c == "]" and "[" in text[s:e - 1]:
            break
        e -= 1
    m = _PREFIX_RE.match(text, s, e)
    if m and m.end() > s:
        s = m.end()
        while s < e and text[s] in _LEAD_CHARS:
            s += 1
    return s, e


def is_fragment(text, s, e):
    w = text[s:e]
    n = e - s
    if n <= 0 or not any(ch.isalnum() for ch in w):
        return True
    if n == 1:
        return True
    if n <= 3 and not w.isupper():
        if s > 0 and text[s - 1].isalpha():
            return True
        if e < len(text) and text[e].isalpha() and w.isalpha():
            return True
    if n == 2 and w.isalpha() and w.islower():
        return True
    return False


def _subtract_tags(text, s, e, tag_ranges, tag_starts):
    """Rimuove dallo span le parti che coprono etichette gia' presenti ([PERSONA_1], [VOLTO])."""
    if not tag_ranges:
        return [(s, e)]
    i = bisect_right(tag_starts, e)
    overlapping = []
    for j in range(i - 1, -1, -1):
        ts_, te_ = tag_ranges[j]
        if te_ <= s:
            break
        if ts_ < e:
            overlapping.append((ts_, te_))
    if not overlapping:
        return [(s, e)]
    parts = [(s, e)]
    for ts_, te_ in reversed(overlapping):
        new = []
        for a, b in parts:
            if te_ <= a or ts_ >= b:
                new.append((a, b))
                continue
            if a < ts_:
                new.append((a, ts_))
            if te_ < b:
                new.append((te_, b))
        parts = new
    return parts


def postprocess(raw, text, settings):
    """Da span grezzi (start, end, gruppo, score, [source]) a Span definitivi con calibrazione tri-stato."""
    if not raw or not isinstance(text, str):
        return []
    items = []
    n = len(text)
    for r in raw:
        s, e, group, score = int(r[0]), int(r[1]), r[2], float(r[3])
        source = r[4] if len(r) > 4 else "model"
        # Calibrazione tri-stato Kahneman (Sistema 1)
        if source == "regex" or score >= 0.85:
            status = "confirmed"
        elif score >= 0.15:
            status = "doubt"
        else:
            continue  # Escluso (< 0.15)

        s = max(0, min(s, n))
        e = max(0, min(e, n))
        g, label, key = categorize(group)
        if key and not settings.get(key, True):
            continue
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e <= s:
            continue
        items.append(Span(s, e, g, label, key, score, source, status))
    if not items:
        return []
    items.sort(key=lambda x: (x.start, -x.end))

    merged = []
    for sp in items:
        if merged:
            prev = merged[-1]
            if sp.start < prev.end:
                # Etichetta dello span "migliore" (prima le regole validate, poi il piu' lungo); lo stato invece non
                # scende mai: basta una parte confermata perche' tutto lo span fuso resti confermato.
                if _priority(sp) > _priority(prev):
                    prev.group, prev.label, prev.key = sp.group, sp.label, sp.key
                    prev.source = sp.source
                    prev.length_hint = sp.end - sp.start
                prev.end = max(prev.end, sp.end)
                prev.score = max(prev.score, sp.score)
                if sp.status == "confirmed":
                    prev.status = "confirmed"
                continue
            if sp.label == prev.label:
                gap = text[prev.end:sp.start]
                if len(gap) <= 2 and all(c in " \t" for c in gap):
                    prev.end = max(prev.end, sp.end)
                    prev.score = max(prev.score, sp.score)
                    if sp.status == "confirmed":
                        prev.status = "confirmed"
                    continue
        merged.append(sp)

    extended = False
    for sp in merged:
        if sp.source == "regex":
            continue
        s, e = sp.start, sp.end
        w = text[s:e]
        cut = (s > 0 and text[s - 1].isalnum() and text[s].isalnum()) or (e < n and text[e].isalnum() and text[e - 1].isalnum())
        if not cut:
            continue
        if len(w) <= 3 and w.isalpha() and not w.isupper():
            continue
        k = 0
        while s > 0 and text[s - 1].isalnum() and text[s].isalnum() and k < 25:
            s -= 1
            k += 1
        k = 0
        while e < n and text[e].isalnum() and text[e - 1].isalnum() and k < 25:
            e += 1
            k += 1
        sp.start, sp.end = s, e
        extended = True
    if extended:
        merged.sort(key=lambda x: (x.start, -x.end))
        again = []
        for sp in merged:
            if again and sp.start < again[-1].end:
                prev = again[-1]
                if _priority(sp) > _priority(prev):
                    prev.group, prev.label, prev.key, prev.source = sp.group, sp.label, sp.key, sp.source
                prev.end = max(prev.end, sp.end)
                if sp.status == "confirmed":
                    prev.status = "confirmed"
                continue
            again.append(sp)
        merged = again

    tag_ranges = [(m.start(), m.end()) for m in ANY_TAG_RE.finditer(text)]
    tag_starts = [a for a, _ in tag_ranges]
    out = []
    for sp in merged:
        for a, b in _subtract_tags(text, sp.start, sp.end, tag_ranges, tag_starts):
            a, b = trim_span(text, a, b, sp.label)
            if b <= a:
                continue
            if sp.source == "regex":
                if not any(ch.isalnum() for ch in text[a:b]):
                    continue
            elif is_fragment(text, a, b):
                continue
            out.append(Span(a, b, sp.group, sp.label, sp.key, sp.score, sp.source, sp.status))
    out.sort(key=lambda x: x.start)
    return out


def detect(text, model_raw, settings, ocr=False):
    """Combina span dei modelli e RegEx in Span definitivi."""
    raw = [tuple(r) + ("model",) for r in (model_raw or [])]
    if settings.get("enable_regex", True):
        raw.extend(r + ("regex",) for r in regex_spans(text, ocr=ocr))
    return postprocess(raw, text, settings)


# --------------------------------------------------------------------------------------
# Propagazione: le entita' rilevate in un punto del documento vengono censurate ovunque
# --------------------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+(?:[.'’@\-][\wÀ-ÖØ-öø-ÿ]+)*|[^\s\w]")
_PROP_STOP = {
    "via", "viale", "piazza", "corso", "largo", "signor", "signora", "sig", "dott", "dottor", "avv", "ing", "prof",
    "il", "la", "lo", "le", "gli", "di", "da", "in", "con", "per", "tra", "fra", "ed", "al", "del", "della",
    "nato", "nata", "residente", "comune", "provincia", "regione", "italia", "euro", "anni", "data", "the",
}


class Propagator:
    """Indice delle entita' gia' rilevate, per trovarne altre occorrenze (match per token, O(n)).

    L'indice e' un albero di token (trie): `index[token] = [figli | None, (etichetta, gruppo, chiave) | None]`. Fino
    alla 1.00 era un elenco per primo token, riordinato a ogni inserimento e scorso per intero a ogni occorrenza di quel
    token: con migliaia di entita' che iniziano con la stessa parola (gli indirizzi «via ...» di un'anagrafe, i «sig.»)
    la ricerca era quadratica - 27,7 s per 8.000 indirizzi, ore per 80.000 (file oltre il tempo massimo). Il risultato
    e' lo stesso di prima: a ogni posizione vince la sequenza piu' lunga che corrisponde; a parita' di sequenza,
    l'etichetta inserita per prima."""

    def __init__(self):
        self.index = {}
        self.seen = set()

    def add(self, word, label, group, key):
        w = " ".join(str(word).split())
        if len(w) < 3:
            return
        alnum = sum(c.isalnum() for c in w)
        if alnum < 3:
            return
        if w.replace(" ", "").replace(".", "").replace("/", "").replace("-", "").isdigit() and alnum < 5:
            return
        toks = [t.casefold() for t in _TOKEN_RE.findall(w)]
        if not toks:
            return
        if len(toks) == 1 and toks[0] in _PROP_STOP:
            return
        sig = (tuple(toks), label)
        if sig in self.seen:
            return
        self.seen.add(sig)
        node = self.index.get(toks[0])
        if node is None:
            node = self.index[toks[0]] = [None, None]
        for t in toks[1:]:
            if node[0] is None:
                node[0] = {}
            nxt = node[0].get(t)
            if nxt is None:
                nxt = node[0][t] = [None, None]
            node = nxt
        if node[1] is None:
            node[1] = (label, group, key)

    def __bool__(self):
        return bool(self.index)

    def find(self, text):
        out = []
        if not self.index or not text:
            return out
        tag_ranges = [(m.start(), m.end()) for m in ANY_TAG_RE.finditer(text)] if "[" in text else []
        tag_starts = [a for a, _ in tag_ranges]

        def _overlaps_tag(a, b):
            if not tag_ranges:
                return False
            idx = bisect_right(tag_starts, b)
            for j in range(idx - 1, -1, -1):
                ts_, te_ = tag_ranges[j]
                if te_ <= a:
                    return False
                if ts_ < b:
                    return True
            return False

        toks = [(m.start(), m.end(), m.group(0).casefold()) for m in _TOKEN_RE.finditer(text)]
        index = self.index
        i = 0
        nt = len(toks)
        while i < nt:
            node = index.get(toks[i][2])
            matched = False
            if node is not None:
                # si scende nell'albero finche' i token coincidono e non c'e' un a capo, un «|» o piu' di 3 caratteri
                # fra un token e il successivo; `found`: le sequenze complete incontrate, dalla piu' corta
                found = [(1, node[1])] if node[1] is not None else []
                j = i + 1
                while node[0] and j < nt:
                    nxt = node[0].get(toks[j][2])
                    if nxt is None:
                        break
                    gap = text[toks[j - 1][1]:toks[j][0]]
                    if "\n" in gap or "|" in gap or len(gap) > 3:
                        break
                    node = nxt
                    j += 1
                    if node[1] is not None:
                        found.append((j - i, node[1]))
                for L, (label, group, key) in reversed(found):
                    a, b = toks[i][0], toks[i + L - 1][1]
                    if _overlaps_tag(a, b):
                        continue
                    out.append((a, b, label, group, key))
                    i += L
                    matched = True
                    break
            if not matched:
                i += 1
        return out
