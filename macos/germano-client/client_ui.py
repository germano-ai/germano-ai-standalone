"""Germano Client v0.60 - pannello locale (si apre in una finestra app dedicata, via germano_desktop.py).

E' LO STESSO Remote Control del Germano Server (remote/remote.html, remote.js, remote.css: copie identiche di quelli del
server), servito qui su 127.0.0.1: le sue richieste (/api/remote/v1/..., /api/auth/...) vengono inoltrate al Germano
Server configurato, aggiungendo la sessione dell'utente salvata in client_config.json (mai consegnata alla pagina).
Funzioni in piu' rispetto al browser: ricerca del server in rete (UDP) e indirizzo del server. Prima di inoltrare
qualsiasi dato si verifica che all'indirizzo risponda davvero un Germano Server (nessun dato verso servizi sconosciuti).
"""
import json
import os
import sys
import threading
import time
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import client  # noqa: E402  (stesse funzioni della riga di comando)
from flask import Flask, Response, jsonify, request, send_file  # noqa: E402

APP_VERSION = client.get_version()
PORT = int(os.environ.get("GERMANO_PORT") or 0) or 8360
REMOTE_DIR = os.path.join(BASE_DIR, "remote")
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024
# Intestazioni inoltrate al server (la chiave API del servizio passa solo verso il server, mai salvata qui)
_FORWARD = ("Content-Type", "X-Germano-Lang", "X-Germano-Provider-Key")
_verified = {"base": None, "at": 0.0}
_lock = threading.Lock()


@app.after_request
def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp


@app.before_request
def _guard():
    ra = request.remote_addr or ""
    if ra not in ("127.0.0.1", "::1") and not ra.startswith("127."):
        return ("Solo locale", 403)
    origin = request.headers.get("Origin")
    if request.method not in ("GET", "HEAD") and origin:   # nessuna azione avviata da siti web esterni
        host = origin.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
        if host not in ("127.0.0.1", "localhost"):
            return jsonify({"error": "Richiesta da un sito esterno bloccata."}), 403
    return None


@app.route("/favicon.ico")
def favicon():
    return send_file(os.path.join(BASE_DIR, "favicon.ico"), mimetype="image/x-icon", max_age=86400)


@app.route("/api/status")
def status():
    # usato da germano_desktop per sapere che il pannello e' pronto
    return jsonify({"service": "germano-client-ui", "version": APP_VERSION})


@app.route("/")
def index():
    with open(os.path.join(REMOTE_DIR, "remote.html"), encoding="utf-8") as f:
        page = f.read().replace("{{ version }}", APP_VERSION)
    # stessa pagina del server, in modalita' Germano Client (collegamento al server e ricerca in rete)
    page = page.replace('<script src="/static/remote.js', '<script>window.GERMANO_CLIENT = true;</script>\n'
                        '<script src="/static/remote.js', 1)
    return Response(page, mimetype="text/html")


@app.route("/static/<name>")
def static_file(name):
    if name not in ("remote.js", "remote.css"):
        return ("Non trovato", 404)
    return send_file(os.path.join(REMOTE_DIR, name), max_age=0)


# ------------------------------------------------------------------ collegamento al server
@app.route("/client/config", methods=["GET", "POST"])
def client_config():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        cfg = client.load_config()
        try:
            s = (data.get("server") or "").strip()
            if s:
                base, tok = client.parse_server(s)
                if base != (cfg.get("server_url") or ""):
                    cfg["token"], cfg["user"] = (tok or ""), ""    # sessione legata al server precedente
                cfg["server_url"] = base
            else:
                cfg["server_url"] = ""
            cfg.setdefault("discovery_port", client.discovery.DEFAULT_PORT)
            client.save_config(cfg)
        except client.ClientError as e:
            return jsonify({"status": "error", "message": str(e)}), 400
        with _lock:
            _verified["base"] = None
    cfg = client.load_config()
    return jsonify({"server_url": cfg.get("server_url") or "", "user": cfg.get("user") or "",
                    "logged_in": bool(cfg.get("token"))})


@app.route("/client/discover")
def client_discover():
    try:
        found = client.discover_servers(timeout=2.0)
    except Exception as e:  # noqa: BLE001
        return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"servers": [{"name": s.get("name"), "url": f"http://{s['ip']}:{s['port']}",
                                 "version": s.get("version"), "engine_ready": bool(s.get("engine_ready")),
                                 "auth_required": bool(s.get("auth_required", s.get("token_required")))}
                                for s in found]})


def _server():
    """(base del server verificato come Germano Server, token di sessione). Solleva ClientError."""
    base, _origin = client.resolve_server(argparse.Namespace(server=None, token=None))
    tok = client.load_config().get("token") or ""
    with _lock:
        fresh = _verified["base"] == base and time.time() - _verified["at"] < 30
    if not fresh:
        client.check_server(base, tok, timeout=6.0)        # solleva ClientError se non e' un Germano Server
        with _lock:
            _verified.update(base=base, at=time.time())
    return base, tok


def _forward(path, body=None, extra_json=None):
    try:
        base, tok = _server()
    except client.ClientError as e:
        return None, jsonify({"status": "error", "error": str(e), "message": str(e)}), 502
    headers = {k: v for k, v in request.headers.items() if k in _FORWARD}
    if tok:
        headers["X-Germano-Auth"] = tok
    data = body if body is not None else (request.get_data() if request.method != "GET" else None)
    if extra_json is not None:
        data = json.dumps(extra_json, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    url = base + path + (("?" + request.query_string.decode("latin-1")) if request.query_string else "")
    try:
        st, raw = client._request(request.method, url, data=data, headers=headers, timeout=900)
    except client.ClientError as e:
        return None, jsonify({"status": "error", "error": str(e), "message": str(e)}), 502
    return (st, raw), None, None


@app.route("/api/remote/v1/<path:sub>", methods=["GET", "POST"])
@app.route("/api/auth/status", methods=["GET"], defaults={"sub": None})
def proxy_remote(sub):
    path = request.path
    res, err, code = _forward(path)
    if err is not None:
        return err, code
    st, raw = res
    return Response(raw, status=st, content_type="application/json")


@app.route("/api/auth/login", methods=["POST"])
def proxy_login():
    data = request.get_json(silent=True) or {}
    res, err, code = _forward("/api/auth/login", extra_json={"username": data.get("username", ""),
                                                             "password": data.get("password", ""), "client": True})
    if err is not None:
        return err, code
    st, raw = res
    out = client._json(raw) or {}
    if st == 200 and out.get("token"):
        cfg = client.load_config()
        cfg["token"], cfg["user"] = out["token"], out.get("user") or ""
        client.save_config(cfg)
        return jsonify({"status": "success", "user": out.get("user")})   # il token resta nel client
    return Response(raw, status=st, content_type="application/json")


@app.route("/api/auth/logout", methods=["POST"])
def proxy_logout():
    _forward("/api/auth/logout", extra_json={})
    cfg = client.load_config()
    cfg["token"], cfg["user"] = "", ""
    client.save_config(cfg)
    return jsonify({"status": "success"})


def main():
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    from werkzeug.serving import run_simple
    run_simple("127.0.0.1", PORT, app, threaded=True, use_reloader=False, use_debugger=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
