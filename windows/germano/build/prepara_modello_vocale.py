"""Prepara il modello vocale della release in modelli/whisper-small (trascrizione offline dei file audio).

1. Scarica openai/whisper-small da Hugging Face (pesi originali di OpenAI) in una cartella temporanea, fissando la
   revisione e verificando ogni file grande con l'impronta SHA-256 (LFS) pubblicata dall'API di Hugging Face.
2. Lo converte nel formato CTranslate2 con pesi INT8 (convertitore ufficiale di CTranslate2, lo stesso motore usato
   da faster-whisper): 967 MB -> circa 245 MB, stessi risultati del caricamento «int8» del modello originale.
3. Scrive il manifesto germano.json (origine, revisione, licenza, impronte) letto da germano/speech.py.

Si esegue su Windows con il python di dipendenze/windows/runtime-germano (che ha torch, transformers e ctranslate2):
    python -B prepara_modello_vocale.py [--sorgente <cartella con i file gia' scaricati>]
Nessun file scaricato viene eseguito: sono pesi (safetensors) e file JSON.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BUILD = os.path.dirname(os.path.abspath(__file__))
RELEASE = os.path.abspath(os.path.join(BUILD, "..", "..", "..", ".."))
REPO = "openai/whisper-small"
REVISION = "973afd24965f72e36ca33b3055d56a652f456b4d"
DEST = os.path.join(RELEASE, "modelli", "whisper-small")
FILES = ("config.json", "model.safetensors", "tokenizer.json", "vocab.json", "merges.txt", "normalizer.json",
         "added_tokens.json", "special_tokens_map.json", "tokenizer_config.json", "preprocessor_config.json",
         "generation_config.json")
COPY = ("tokenizer.json", "preprocessor_config.json")
UA = {"User-Agent": "python-urllib"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get(url, timeout=120):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)


def fetch(folder):
    """Scarica (o riusa, se gia' presenti e con l'impronta giusta) i file della revisione fissata."""
    os.makedirs(folder, exist_ok=True)
    tree = {i["path"]: i for i in json.load(get(f"https://huggingface.co/api/models/{REPO}/tree/{REVISION}"))}
    origin = {}
    for name in FILES:
        item = tree.get(name)
        if item is None:
            raise SystemExit(f"ERRORE: {name} non trovato in {REPO}@{REVISION[:12]}")
        lfs = item.get("lfs") or {}
        path = os.path.join(folder, name)
        expected, size = lfs.get("oid"), lfs.get("size") or item.get("size")
        if not (os.path.isfile(path) and os.path.getsize(path) == size and (not expected or sha256(path) == expected)):
            print(f"  scarico {name} ({size / 2**20:.1f} MB)...", flush=True)
            with get(f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}", timeout=600) as r, \
                    open(path + ".part", "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            if os.path.getsize(path + ".part") != size or (expected and sha256(path + ".part") != expected):
                os.remove(path + ".part")
                raise SystemExit(f"ERRORE: {name} non corrisponde a dimensione/impronta pubblicate da Hugging Face")
            os.replace(path + ".part", path)
        origin[name] = {"size": os.path.getsize(path), "sha256": sha256(path), "lfs_verified": bool(expected)}
    return origin


def main():
    source = sys.argv[sys.argv.index("--sorgente") + 1] if "--sorgente" in sys.argv else None
    with tempfile.TemporaryDirectory(prefix="germano_whisper_") as tmp:
        src = source or os.path.join(tmp, "hf")
        print(f"== {REPO}@{REVISION[:12]} -> {DEST}", flush=True)
        origin = fetch(src)
        import ctranslate2
        from ctranslate2.converters import TransformersConverter
        out = os.path.join(tmp, "ct2")
        t0 = time.time()
        TransformersConverter(src, copy_files=list(COPY)).convert(out, quantization="int8", force=True)
        print(f"  conversione CTranslate2 {ctranslate2.__version__} INT8 in {time.time() - t0:.0f} s", flush=True)
        needed = {"model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"}
        produced = set(os.listdir(out))
        if not needed <= produced or not ({"vocabulary.json", "vocabulary.txt"} & produced):
            raise SystemExit(f"ERRORE: conversione incompleta: {sorted(produced)}")
        if os.path.isdir(DEST):
            shutil.rmtree(DEST)
        os.makedirs(DEST)
        files = {}
        for name in sorted(produced):
            shutil.copyfile(os.path.join(out, name), os.path.join(DEST, name))
            files[name] = {"size": os.path.getsize(os.path.join(DEST, name)), "sha256": sha256(os.path.join(DEST, name))}
        manifest = {
            "name": "Whisper small", "quantization": "INT8", "languages": "multilingue (99 lingue, italiano compreso)",
            "runtime": f"faster-whisper (CTranslate2 {ctranslate2.__version__})",
            "source": f"https://huggingface.co/{REPO}/tree/{REVISION}", "revision": REVISION,
            "license": "MIT (OpenAI Whisper); scheda del modello su Hugging Face: Apache-2.0",
            "conversion": "ctranslate2.converters.TransformersConverter, quantization=int8 "
                          "(sorgenti/windows/germano/build/prepara_modello_vocale.py)",
            "use": "Trascrizione offline del parlato dei file audio (germano/speech.py), in un processo separato",
            "original_files": {k: origin[k] for k in ("model.safetensors", "config.json", "tokenizer.json")},
            "files": files,
        }
        with open(os.path.join(DEST, "germano.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")
    total = sum(os.path.getsize(os.path.join(DEST, n)) for n in os.listdir(DEST))
    print(f"  OK {DEST}: {len(os.listdir(DEST))} file, {total / 2**20:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
