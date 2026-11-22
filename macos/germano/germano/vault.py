"""Vault delle corrispondenze etichetta <-> dato reale (pseudonimizzazione reversibile).

Formato JSON (compatibile con v0.50): extracted/deanonymize_vault.json
    {"tag_to_word": {"[PERSONA_1]": "Mario Rossi"},
     "word_to_tag": {"[PERSONA]::mario rossi": "[PERSONA_1]"},
     "counters":    {"[PERSONA]": 1}}

Archivio (turno 26): SQLite in modalita' WAL, extracted/deanonymize_vault.db, con scritture INCREMENTALI (solo le voci
nuove) e letture incrementali dal server. Prima a ogni documento o richiesta del Proxy con un dato nuovo il motore
riscriveva tutto il JSON e il server lo rileggeva per intero (misurato nel turno 25: 0,3 s + 0,4 s con 100.000 voci).
- Il JSON resta, con lo stesso formato: copia portabile aggiornata a ogni salvataggio fino a JSON_SYNC_MAX voci, poi
  ogni JSON_EXPORT_S secondi e alla chiusura del motore. Se il JSON viene sostituito a mano (es. copiato da un'altra
  installazione, come indica la guida) il motore ne importa le voci nel database: le voci gia' presenti non vengono
  mai sovrascritte (nessuna perdita di corrispondenze).
- Migrazione automatica: al primo avvio con un JSON e senza database, il JSON viene importato per intero.
- Cartella dati su un disco di rete (SMB/NFS, condivisione UNC): SQLite in WAL richiede memoria condivisa locale,
  quindi li' resta il solo JSON come prima. GERMANO_VAULT_BACKEND=json|sqlite forza la scelta.
- Durabilita': synchronous=FULL (come la scrittura atomica con fsync del JSON). Nessuna cifratura, come prima.

Solo il demone crea nuove etichette; il server legge (e svuota il vault solo a demone spento).
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time

from . import common

_L = "A-Za-zÀ-ÖØ-öø-ÿ"
# Etichetta numerata: [PERSONA_1], [PERSONA 1], [ persona_1 ], [COD.FISCALE/P.IVA_3], [DATO_SANITARIO_2]
TAG_RE = re.compile(r"\[\s*([" + _L + r"][" + _L + r"./]*(?:[ _]+[" + _L + r"./]+)*?)[ _]+(\d{1,7})\s*\]")
# Forma canonica emessa da Germano (maiuscola, con underscore): evita falsi positivi di auto-ripristino (es. "[data 1]")
STRICT_TAG_RE = re.compile(r"\[([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ./]*(?:_[A-ZÀ-ÖØ-Þ./]+)*)_(\d{1,7})\]")
# Qualsiasi etichetta di Germano (anche non numerata, es. [VOLTO], [PERSONA]) da proteggere in rianalisi.
ANY_TAG_RE = re.compile(r"\[[A-Z][A-Z0-9./_ ]{1,40}\]")
MAX_RESTORE_FLOOR = 32 * 1024 * 1024
MAX_RESTORE_RATIO = 16
MAX_RESTORE_HARD = 250 * 1024 * 1024

JSON_SYNC_MAX = 5000        # fino a qui la copia JSON si riscrive a ogni salvataggio (pochi millisecondi)
JSON_EXPORT_S = 300         # oltre, al massimo ogni 5 minuti e alla chiusura del motore
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY AUTOINCREMENT, tag TEXT NOT NULL UNIQUE, "
    "word TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS wkeys (id INTEGER PRIMARY KEY AUTOINCREMENT, wkey TEXT NOT NULL UNIQUE, "
    "tag TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS counters (base TEXT PRIMARY KEY, n INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)",
)


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


def contains_strict_tags(text, tag_map):
    """True solo se il testo contiene almeno un'etichetta nella forma canonica esatta di Germano ([PERSONA_1]) presente
    nel Vault (evita che un testo comune come '[data 1]' attivi per errore la modalita' di ripristino)."""
    if not text or "[" not in text or not tag_map:
        return False
    for m in STRICT_TAG_RE.finditer(text):
        if _norm(m.group(1), m.group(2)) in tag_map:
            return True
    return False


def restore_text(text, tag_map, json_escape=False, max_output=None):
    """Rimette i dati reali al posto delle etichette numerate (passaggio unico, O(n)), con tetto anti-amplificazione."""
    if not isinstance(text, str) or "[" not in text or not tag_map:
        return text
    limit = max_output if max_output is not None else min(MAX_RESTORE_HARD, max(len(text) * MAX_RESTORE_RATIO, MAX_RESTORE_FLOOR))
    out = []
    out_len = 0
    pos = 0
    for m in TAG_RE.finditer(text):
        start, end = m.start(), m.end()
        if start > pos:
            chunk = text[pos:start]
            out_len += len(chunk)
            if out_len > limit:
                raise ValueError("Il testo ripristinato supera il limite di sicurezza.")
            out.append(chunk)
        word = tag_map.get(_norm(m.group(1), m.group(2)))
        if not word:
            rep = m.group(0)
        elif json_escape:
            rep = json.dumps(word, ensure_ascii=False)[1:-1]
        else:
            rep = word
        out_len += len(rep)
        if out_len > limit:
            raise ValueError("Il testo ripristinato supera il limite di sicurezza.")
        out.append(rep)
        pos = end
    if pos == 0:
        return text
    if pos < len(text):
        tail = text[pos:]
        out_len += len(tail)
        if out_len > limit:
            raise ValueError("Il testo ripristinato supera il limite di sicurezza.")
        out.append(tail)
    return "".join(out)


def _empty():
    return {"tag_to_word": {}, "word_to_tag": {}, "counters": {}}


# ------------------------------------------------------------------ dove si puo' usare SQLite
_NETWORK_FS = {"nfs", "nfs4", "cifs", "smb", "smb2", "smb3", "smbfs", "afpfs", "fuse.sshfs", "sshfs", "9p", "webdav",
               "davfs", "fuse.davfs2", "ncpfs", "glusterfs", "ceph", "fuse.rclone"}


def _on_network_drive(path):
    """True se il percorso e' su un disco di rete (unita' mappata o UNC su Windows, nfs/cifs/smbfs su Linux e macOS)."""
    p = os.path.abspath(path)
    try:
        if os.name == "nt":
            if p.startswith("\\\\"):
                return True
            import ctypes
            root = os.path.splitdrive(p)[0] + "\\"
            return ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) == 4      # DRIVE_REMOTE
        best, fstype = "", ""
        if os.path.exists("/proc/mounts"):
            with open("/proc/mounts", encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3:
                        mnt = parts[1].replace("\\040", " ")
                        if (p == mnt or p.startswith(mnt.rstrip("/") + "/")) and len(mnt) > len(best):
                            best, fstype = mnt, parts[2]
        else:
            out = subprocess.run(["/sbin/mount"], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                m = re.match(r"^.* on (.*) \(([^,)]+)", line)
                if m and (p == m.group(1) or p.startswith(m.group(1).rstrip("/") + "/")) and len(m.group(1)) > len(best):
                    best, fstype = m.group(1), m.group(2)
        return fstype.lower() in _NETWORK_FS
    except Exception:
        return False


def sqlite_backend(folder):
    forced = (os.environ.get("GERMANO_VAULT_BACKEND") or "").strip().lower()
    if forced in ("json", "sqlite"):
        return forced == "sqlite"
    return not _on_network_drive(folder)


def db_path_for(json_path):
    return os.path.splitext(json_path)[0] + ".db"


def _connect(path):
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False, isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        for stmt in _SCHEMA:
            conn.execute(stmt)
        conn.execute("SELECT count(*) FROM tags").fetchone()
    except BaseException:
        conn.close()                    # su Windows un file aperto non si puo' mettere da parte
        raise
    return conn


def _read_json_file(path):
    """(dati, firma) del JSON; dati None se il file non c'e'. Mai sovrascrivere un vault illeggibile: se ne conserva
    una copia (come prima del turno 26)."""
    try:
        st = os.stat(path)
        sig = f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return None, None
    for i in range(10):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            base = _empty()
            if isinstance(data, dict):
                for k in base:
                    if isinstance(data.get(k), dict):
                        base[k] = data[k]
            return base, sig
        except FileNotFoundError:
            return None, None
        except (PermissionError, json.JSONDecodeError, UnicodeDecodeError):
            time.sleep(0.05 * (i + 1))
    backup = f"{path}.illeggibile-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        shutil.copy2(path, backup)
        common.log(f"ATTENZIONE: vault illeggibile, copia di sicurezza salvata in {os.path.basename(backup)}")
    except Exception:
        pass
    return None, sig


class Vault:
    def __init__(self, path=common.VAULT_FILE):
        self.path = path                                   # copia JSON (unico archivio sui dischi di rete)
        self.db_path = db_path_for(path)
        self.use_sqlite = sqlite_backend(os.path.dirname(os.path.abspath(path)) or ".")
        self._lock = threading.RLock()
        self._data = None
        self._stat_sig = None
        self._dirty = False
        self._map_cache = None
        self._conn = None
        self._pending = []                                 # voci nuove da scrivere nel database
        self._json_due = False                             # la copia JSON e' indietro rispetto al database
        self._json_time = 0.0
        self._generation = None
        self._norm_tags = None
        self._active_jobs = 0
        self._jobs_cond = threading.Condition(self._lock)

    def _rollback_quietly(self, conn):
        try:
            if conn is not None and conn.in_transaction:
                conn.execute("ROLLBACK")
        except Exception:
            pass

    def begin_job(self):
        with self._lock:
            self._active_jobs += 1

    def end_job(self):
        with self._lock:
            if self._active_jobs > 0:
                self._active_jobs -= 1
            if self._active_jobs == 0:
                self._jobs_cond.notify_all()

    def generation(self):
        with self._lock:
            self._ensure()
            if self.use_sqlite:
                try:
                    self._generation = self._meta("generation", "0")
                except Exception:
                    pass
            return str(self._generation or "0")

    # ------------------------------------------------------------------ disco: JSON (dischi di rete) ---------------
    def _stat(self):
        try:
            st = os.stat(self.path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _load_json_only(self):
        data, _sig = _read_json_file(self.path)
        self._data = data or _empty()
        self._stat_sig = self._stat()
        self._map_cache = None
        self._norm_tags = None
        if self._generation is None:
            self._generation = str(self._data.get("generation", "0"))

    # ------------------------------------------------------------------ disco: SQLite ------------------------------
    def _db(self):
        if self._conn is None:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            try:
                conn = _connect(self.db_path)
            except sqlite3.DatabaseError as e:
                # database danneggiato: si mette da parte (mai cancellato) e si riparte dalla copia JSON
                backup = f"{self.db_path}.illeggibile-{time.strftime('%Y%m%d-%H%M%S')}"
                for suffix in ("", "-wal", "-shm"):
                    try:
                        os.replace(self.db_path + suffix, backup + suffix)
                    except FileNotFoundError:
                        pass
                common.log(f"ATTENZIONE: archivio del Vault illeggibile ({e}): messo da parte in "
                           f"{os.path.basename(backup)}, si ricostruisce dalla copia JSON.")
                conn = _connect(self.db_path)
            self._conn = conn
        return self._conn

    def _meta(self, key, default=None):
        row = self._db().execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return row[0] if row else default

    def _set_meta(self, conn, key, value):
        conn.execute("INSERT INTO meta(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, str(value)))

    def _merge_json(self, data, sig):
        """Voci del JSON assenti nel database (migrazione o JSON sostituito a mano). Mai sovrascritte quelle presenti."""
        conn = self._db()
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing_tags = {normalize_tag(t) or t: (t, w) for t, w in conn.execute("SELECT tag, word FROM tags")}
            added = 0
            accepted_tags = {}
            for tag, word in (data.get("tag_to_word") or {}).items():
                if not (isinstance(tag, str) and isinstance(word, str)):
                    continue
                nt = normalize_tag(tag) or tag
                if nt in existing_tags:
                    cur_tag, cur_word = existing_tags[nt]
                    if cur_word.strip().lower() == word.strip().lower():
                        accepted_tags[tag] = cur_tag
                    continue
                rc = conn.execute("INSERT OR IGNORE INTO tags(tag, word) VALUES(?, ?)", (nt, word)).rowcount
                if rc:
                    added += rc
                    existing_tags[nt] = (nt, word)
                    accepted_tags[tag] = nt
            for key, tag in (data.get("word_to_tag") or {}).items():
                if not (isinstance(key, str) and isinstance(tag, str)):
                    continue
                mapped = accepted_tags.get(tag)
                if mapped:
                    conn.execute("INSERT OR IGNORE INTO wkeys(wkey, tag) VALUES(?, ?)", (key, mapped))
            for base, n in (data.get("counters") or {}).items():
                try:
                    n = int(n)
                except (TypeError, ValueError):
                    continue
                conn.execute("INSERT INTO counters(base, n) VALUES(?, ?) ON CONFLICT(base) DO UPDATE SET "
                             "n=max(n, excluded.n)", (base, n))
            self._set_meta(conn, "json_sig", sig or "")
            self._set_meta(conn, "ready", "1")      # il server legge il database solo dopo la migrazione completa
            conn.execute("COMMIT")
        except BaseException:
            self._rollback_quietly(conn)
            raise
        return added

    def _sync_from_json(self):
        """Importa il JSON se e' diverso da quello scritto o importato l'ultima volta (copiato a mano, migrazione)."""
        try:
            st = os.stat(self.path)
            sig = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            return False
        if sig == self._meta("json_sig"):
            return False
        data, sig = _read_json_file(self.path)
        if data is None:
            if sig:
                # JSON illeggibile (copia di sicurezza gia' fatta): il database resta valido e la copia JSON verra'
                # riscritta; la firma si registra per non riprovare a ogni richiesta
                conn = self._db()
                conn.execute("BEGIN IMMEDIATE")
                try:
                    self._set_meta(conn, "json_sig", sig)
                    conn.execute("COMMIT")
                except BaseException:
                    self._rollback_quietly(conn)
                    raise
                self._json_due = True
            return False
        added = self._merge_json(data, sig)
        if added:
            common.log(f"Vault: importate {added} corrispondenze da {os.path.basename(self.path)}.")
        self._json_due = True                  # la copia JSON deve tornare a riflettere tutto il database
        return True

    def _load_sqlite(self):
        conn = self._db()
        self._sync_from_json()
        if self._meta("ready") != "1":         # nuova installazione, nessun JSON da importare
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._set_meta(conn, "ready", "1")
                conn.execute("COMMIT")
            except BaseException:
                self._rollback_quietly(conn)
                raise
        data = _empty()
        data["tag_to_word"] = {t: w for t, w in conn.execute("SELECT tag, word FROM tags ORDER BY id")}
        data["word_to_tag"] = {k: t for k, t in conn.execute("SELECT wkey, tag FROM wkeys ORDER BY id")}
        data["counters"] = {b: n for b, n in conn.execute("SELECT base, n FROM counters")}
        self._data = data
        self._generation = self._meta("generation", "0")
        self._map_cache = None
        self._norm_tags = None
        if not self._json_time:
            self._json_time = time.time()      # copia JSON di un Vault grande: la prima tra JSON_EXPORT_S secondi

    def _export_json(self):
        """Copia JSON completa (stesso formato di sempre), scritta in modo atomico; la firma si registra nel database
        per riconoscere poi una sostituzione a mano. Un errore (es. disco pieno) non ferma il lavoro: i dati sono gia'
        nel database, la copia si riprova al salvataggio successivo."""
        try:
            common.atomic_write_json(self.path, self._data, indent=2)
        except OSError as e:
            common.log(f"Avviso: copia JSON del Vault non aggiornata ({e}); i dati sono nel database, si riprova piu' "
                       "tardi.")
            self._json_due = True
            return
        conn = None
        try:
            st = os.stat(self.path)
            conn = self._db()
            conn.execute("BEGIN IMMEDIATE")
            self._set_meta(conn, "json_sig", f"{st.st_mtime_ns}:{st.st_size}")
            conn.execute("COMMIT")
        except Exception:
            self._rollback_quietly(conn)
        self._json_due = False
        self._json_time = time.time()

    # ------------------------------------------------------------------ ciclo di vita
    def _load(self):
        if self.use_sqlite:
            try:
                self._load_sqlite()
                return
            except Exception as e:
                common.log(f"ATTENZIONE: archivio SQLite del Vault non utilizzabile ({type(e).__name__}: {e}): si usa "
                           "il file JSON.")
                self.use_sqlite = False
                self._conn = None
        self._load_json_only()

    def _ensure(self):
        if self._data is None:
            self._load()

    def refresh(self):
        """Ricarica se l'archivio e' stato modificato da un altro processo (o il JSON sostituito a mano)."""
        with self._lock:
            if self._data is None:
                self._load()
                return
            if self._dirty:
                return
            if self.use_sqlite:
                if self._sync_from_json() or self._meta("generation", "0") != self._generation:
                    self._load_sqlite()
            elif self._stat() != self._stat_sig:
                self._load_json_only()

    def flush(self, final=False):
        with self._lock:
            if self._data is None:
                return
            if self.use_sqlite:
                if self._pending:
                    conn = self._db()
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        for tag, word, key, base, n in self._pending:
                            conn.execute("INSERT OR REPLACE INTO tags(tag, word) VALUES(?, ?)", (tag, word))
                            conn.execute("INSERT OR REPLACE INTO wkeys(wkey, tag) VALUES(?, ?)", (key, tag))
                            conn.execute("INSERT INTO counters(base, n) VALUES(?, ?) ON CONFLICT(base) DO UPDATE SET "
                                         "n=max(n, excluded.n)", (base, n))
                        conn.execute("COMMIT")
                    except BaseException:
                        conn.execute("ROLLBACK")
                        raise
                    self._pending = []
                    self._json_due = True
                self._dirty = False
                if self._json_due and (final or len(self._data["tag_to_word"]) <= JSON_SYNC_MAX
                                       or time.time() - self._json_time >= JSON_EXPORT_S):
                    self._export_json()
                return
            if not self._dirty:
                return
            common.atomic_write_json(self.path, self._data, indent=2)
            self._stat_sig = self._stat()
            self._dirty = False

    def close(self):
        """Fine del motore: ultime voci nel database e copia JSON allineata."""
        with self._lock:
            if self._data is not None:
                self.flush(final=True)
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    # ------------------------------------------------------------------ API
    def _norm_set(self):
        if self._norm_tags is None:
            self._norm_tags = {normalize_tag(t) or t for t in self._data["tag_to_word"]}
        return self._norm_tags

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
            used_norm = self._norm_set()
            tag = f"{stem}_{idx}]"
            while tag in self._data["tag_to_word"] or (normalize_tag(tag) or tag) in used_norm:
                idx += 1
                tag = f"{stem}_{idx}]"
            self._data["counters"][base_label] = idx
            self._data["word_to_tag"][key] = tag
            self._data["tag_to_word"][tag] = w
            used_norm.add(normalize_tag(tag) or tag)
            if self.use_sqlite:
                self._pending.append((tag, w, key, base_label, idx))
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

    def clear(self, wait_jobs=5.0):
        with self._lock:
            end = time.time() + max(0.0, float(wait_jobs or 0.0))
            while self._active_jobs > 0:
                rem = end - time.time()
                if rem <= 0:
                    raise RuntimeError("Impossibile svuotare il Vault mentre un'elaborazione e' in corso: riprova tra poco.")
                self._jobs_cond.wait(timeout=min(0.25, rem))
            gen = None
            if self.use_sqlite:
                try:
                    conn = self._db()
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        for table in ("tags", "wkeys", "counters"):
                            conn.execute(f"DELETE FROM {table}")
                        gen = int(self._meta("generation", "0") or 0) + 1
                        self._set_meta(conn, "generation", gen)
                        conn.execute("COMMIT")
                    except BaseException:
                        self._rollback_quietly(conn)
                        raise
                    self._generation = str(gen)
                except Exception as e:
                    common.log(f"ATTENZIONE: archivio SQLite del Vault non svuotato ({e}): si usa il file JSON.")
                    self.use_sqlite = False
                    if self._conn is not None:
                        try:
                            self._conn.close()
                        except Exception:
                            pass
                        self._conn = None
                    # Invalida il .db vecchio affinche' VaultReader non continui a leggere voci pre-svuotamento
                    for suffix in ("", "-wal", "-shm"):
                        try:
                            os.remove(self.db_path + suffix)
                        except OSError:
                            pass
            if gen is None:
                try:
                    gen = int(self._generation or 0) + 1
                except ValueError:
                    gen = int(time.time())
                self._generation = str(gen)
            self._data = _empty()
            self._pending = []
            self._map_cache = None
            self._norm_tags = set()
            if self.use_sqlite:
                self._dirty = False
                self._export_json()
            else:
                self._dirty = True
                self.flush()


class VaultReader:
    """Accesso in sola lettura dal server web. Con l'archivio SQLite legge solo le voci nuove (incrementale, nessuna
    rilettura dell'intero Vault); senza database (prima della migrazione, dischi di rete) rilegge il JSON quando cambia."""

    def __init__(self, path=common.VAULT_FILE):
        self.path = path
        self.db_path = db_path_for(path)
        self.use_sqlite = sqlite_backend(os.path.dirname(os.path.abspath(path)) or ".")
        self._json = Vault(path)
        self._json.use_sqlite = False
        self._lock = threading.Lock()
        self._conn = None
        self._db_ino = None
        self._gen = None
        self._last_id = 0
        self._items = {}
        self._map = {}

    def _close_conn_locked(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
            self._db_ino = None

    def _sqlite_ready(self):
        if not self.use_sqlite:
            return False
        try:
            st = os.stat(self.db_path)
            ino = (st.st_dev, st.st_ino)
        except OSError:
            self._close_conn_locked()
            return False
        if self._conn is not None and self._db_ino != ino:
            self._close_conn_locked()
            self._gen, self._last_id, self._items, self._map = None, 0, {}, {}
        if self._conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False, isolation_level=None)
            try:
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute("SELECT count(*) FROM tags").fetchone()
            except sqlite3.DatabaseError:
                conn.close()                    # il motore deve poter mettere da parte un database danneggiato
                return False
            self._conn = conn
            self._db_ino = ino
        row = self._conn.execute("SELECT v FROM meta WHERE k='ready'").fetchone()
        return bool(row and row[0] == "1")      # migrazione dal JSON non ancora conclusa: si legge il JSON

    def _update(self):
        """Voci aggiunte dall'ultima lettura; tutto da capo solo se il Vault e' stato svuotato o reimportato.
        Generazione e voci nuove si leggono nella STESSA transazione (un'unica istantanea del database): con due
        SELECT separate, uno svuotamento del motore seguito da nuove voci proprio fra l'una e l'altra lasciava per
        una lettura le voci di prima insieme alle nuove (etichette ripartite da 1, dati del Vault precedente)."""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            row = conn.execute("SELECT v FROM meta WHERE k='generation'").fetchone()
            gen = row[0] if row else "0"
            last_id = self._last_id if gen == self._gen else 0
            rows = conn.execute("SELECT id, tag, word FROM tags WHERE id > ? ORDER BY id", (last_id,)).fetchall()
        finally:
            try:
                conn.execute("COMMIT")
            except sqlite3.Error:
                pass
        if gen != self._gen:
            self._gen, self._last_id, self._items, self._map = gen, 0, {}, {}
        if rows:
            new_items = dict(self._items)
            new_map = dict(self._map)                 # chi ha gia' una mappa la usa intatta (oggetto non modificato)
            for rid, tag, word in rows:
                new_items[tag] = word
                nt = normalize_tag(tag)
                if nt and word:
                    new_map[nt] = word
                self._last_id = rid
            self._items = new_items
            self._map = new_map

    def _sqlite(self):
        with self._lock:
            try:
                if not self._sqlite_ready():
                    return False
                self._update()
                return True
            except sqlite3.DatabaseError:
                self._close_conn_locked()
                return False

    def generation(self):
        if self._sqlite():
            return str(self._gen or "0")
        self._json.refresh()
        return self._json.generation()

    def tag_map(self):
        if self._sqlite():
            return self._map
        self._json.refresh()
        return self._json.tag_map()

    def items(self):
        if self._sqlite():
            with self._lock:
                return list(self._items.items())
        self._json.refresh()
        return self._json.items()

    def count(self):
        if self._sqlite():
            with self._lock:
                return len(self._items)
        self._json.refresh()
        return self._json.count()
