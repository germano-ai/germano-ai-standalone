"""Germano Client v0.60 - pannello di controllo locale (si apre in una finestra app dedicata, via germano_desktop.py).

Riusa le funzioni di client.py (stessa logica della riga di comando): cerca il server, mostra stato, elenca le AI del
server, usa un'AI del server (ask) e protegge testo/file (send). Ascolta SOLO su 127.0.0.1. Nessun dato personale esce
senza che il server risponda come un vero Germano Server con token valido (verifica preliminare di client.py).
"""
import json
import os
import sys
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import client  # noqa: E402  (stesse funzioni della CLI)
from flask import Flask, Response, request, jsonify  # noqa: E402

APP_VERSION = client.get_version()
PORT = int(os.environ.get("GERMANO_PORT") or 0) or 8360
app = Flask(__name__)


def _ns(**kw):
    return argparse.Namespace(**kw)


def _resolve(server=None, token=None):
    args = _ns(server=server or None, token=token or None)
    base, origin = client.resolve_server(args)
    tok = client._token(args)
    return base, origin, tok


@app.after_request
def _local_only(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.before_request
def _guard():
    ra = request.remote_addr or ""
    if ra not in ("127.0.0.1", "::1") and not ra.startswith("127."):
        return ("Solo locale", 403)
    return None


@app.route("/favicon.ico")
def favicon():
    from flask import send_file
    return send_file(os.path.join(BASE_DIR, "favicon.ico"), mimetype="image/x-icon", max_age=86400)


@app.route("/api/status")
def status():
    # usato da germano_desktop per sapere che il pannello e' pronto
    return jsonify({"service": "germano-client-ui", "version": APP_VERSION})


@app.route("/ui/config", methods=["GET", "POST"])
def ui_config():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        cfg = client.load_config()
        try:
            if "server" in data:
                s = (data.get("server") or "").strip()
                if s:
                    base, tok = client.parse_server(s)
                    cfg["server_url"] = base
                    if tok and not data.get("token"):
                        data["token"] = tok
                else:
                    cfg["server_url"] = ""
            if "token" in data:
                t = (data.get("token") or "").strip()
                client.check_token_format(t)
                cfg["token"] = t
            cfg.setdefault("discovery_port", client.discovery.DEFAULT_PORT)
            client.save_config(cfg)
        except client.ClientError as e:
            return jsonify({"status": "error", "message": str(e)}), 400
    cfg = client.load_config()
    return jsonify({"server_url": cfg.get("server_url") or "", "token_set": bool(cfg.get("token")),
                    "discovery_port": cfg.get("discovery_port") or client.discovery.DEFAULT_PORT})


@app.route("/ui/discover")
def ui_discover():
    try:
        found = client.discover_servers(timeout=2.0)
    except Exception as e:  # noqa: BLE001
        return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"servers": [{"name": s.get("name"), "url": f"http://{s['ip']}:{s['port']}",
                                 "version": s.get("version"), "engine_ready": bool(s.get("engine_ready")),
                                 "token_required": bool(s.get("token_required"))} for s in found]})


@app.route("/ui/status")
def ui_status():
    try:
        base, origin, tok = _resolve()
        r = client.check_server(base, tok)
    except client.ClientError as e:
        return jsonify({"status": "error", "message": str(e)}), 200
    info = r["info"]
    return jsonify({"status": "ok", "base": base, "origin": origin, "name": info.get("name"),
                    "version": info.get("version"), "engine_ready": r["engine_ready"], "ms": r["ms"],
                    "token": r["token"], "token_ok": r["token_ok"]})


@app.route("/ui/models")
def ui_models():
    try:
        base, origin, tok = _resolve()
        data, note = client.server_tools(base, tok)
    except client.ClientError as e:
        return jsonify({"status": "error", "message": str(e)}), 200
    return jsonify({"status": "ok", "base": base, "note": note, "tools": data.get("tools") or [],
                    "sharing": data.get("sharing"), "proxy": data.get("proxy") or {}})


@app.route("/ui/ask", methods=["POST"])
def ui_ask():
    data = request.get_json(silent=True) or {}
    tool = (data.get("tool") or "").strip()
    prompt = (data.get("prompt") or "").strip()
    model = (data.get("model") or "").strip()
    if not tool or not prompt:
        return jsonify({"status": "error", "message": "Scegli un'AI e scrivi un prompt."}), 400
    try:
        base, origin, tok = _resolve()
        code, r = client._preflight(base, tok, "richiesta annullata")
        if code:
            return jsonify({"status": "error", "message": f"Verifica non superata (codice {code}): nessun dato inviato."}), 200
        if not r["engine_ready"]:
            return jsonify({"status": "error", "message": "Il motore del server non e' pronto: nessun dato inviato."}), 200
        payload = json.dumps({"tool": tool, "prompt": prompt, "model": model}, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if tok:
            headers["X-Germano-Auth"] = tok
        st, raw = client._request("POST", base + "/api/harness/v1/run", data=payload, headers=headers, timeout=330)
        out = client._json(raw) or {}
    except client.ClientError as e:
        return jsonify({"status": "error", "message": str(e)}), 200
    if st == 200 and out.get("status") == "success":
        return jsonify({"status": "ok", "answer": out.get("answer", ""), "seconds": out.get("seconds"),
                        "tool_name": out.get("tool_name") or tool})
    return jsonify({"status": "error", "message": out.get("message") or out.get("error") or f"Errore (HTTP {st})."}), 200


@app.route("/ui/protect", methods=["POST"])
def ui_protect():
    prompt = (request.form.get("prompt") or "").strip()
    files = []
    for f in request.files.getlist("files"):
        if f and f.filename:
            files.append(("files", os.path.basename(f.filename), f.read()))
            if len(files) >= client.MAX_ATTACHMENTS:
                break
    if not prompt and not files:
        return jsonify({"status": "error", "message": "Scrivi un testo o allega dei file."}), 400
    try:
        base, origin, tok = _resolve()
        code, r = client._preflight(base, tok, "invio annullato")
        if code:
            return jsonify({"status": "error", "message": f"Verifica non superata (codice {code}): nessun dato inviato."}), 200
        if not r["engine_ready"]:
            return jsonify({"status": "error", "message": "Il motore del server non e' pronto: nessun dato inviato."}), 200
        body, ctype = client._multipart({"prompt": prompt, "target": "germano-client"}, files)
        headers = {"Content-Type": ctype}
        if tok:
            headers["X-Germano-Auth"] = tok
        st, raw = client._request("POST", base + "/api/studio/send", data=body, headers=headers, timeout=1800)
        out = client._json(raw) or {}
    except client.ClientError as e:
        return jsonify({"status": "error", "message": str(e)}), 200
    if st == 200 and out.get("status") == "success":
        return jsonify({"status": "ok", "composed": out.get("composed", ""), "labels": out.get("labels") or [],
                        "entity_count": out.get("entity_count", 0)})
    return jsonify({"status": "error", "message": out.get("message") or out.get("error") or f"Errore (HTTP {st})."}), 200


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")


PAGE = r"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Germano AI — Client</title><link rel="icon" href="/favicon.ico" sizes="any"><style>
:root{--bg:#0f172a;--panel:#1e293b;--panel2:#273449;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--accent:#2563eb;--ok:#16a34a;--warn:#d97706;--err:#dc2626}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 "Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--text)}
header{display:flex;align-items:center;gap:12px;padding:14px 20px;background:var(--panel);border-bottom:1px solid var(--border)}
header h1{font-size:18px;margin:0;font-weight:700}header .sub{color:var(--muted);font-size:12px}
main{max-width:980px;margin:0 auto;padding:20px;display:grid;gap:16px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px}
.card h2{font-size:15px;margin:0 0 12px;font-weight:700}
label{display:block;font-size:12px;color:var(--muted);margin:8px 0 4px}
input,textarea,select{width:100%;background:var(--panel2);border:1px solid var(--border);border-radius:8px;color:var(--text);padding:8px 10px;font:inherit}
textarea{min-height:90px;resize:vertical}
.row{display:flex;gap:10px;flex-wrap:wrap}.row>*{flex:1;min-width:180px}
button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:9px 16px;font:600 14px/1 inherit;cursor:pointer}
button.sec{background:var(--panel2);border:1px solid var(--border)}
button:disabled{opacity:.5;cursor:default}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
.pill.ok{background:rgba(22,163,74,.2);color:#4ade80}.pill.err{background:rgba(220,38,38,.2);color:#f87171}.pill.warn{background:rgba(217,119,6,.2);color:#fbbf24}
.muted{color:var(--muted)}.mono{font-family:Consolas,monospace;white-space:pre-wrap;word-break:break-word}
.tool{border:1px solid var(--border);border-radius:8px;padding:10px;margin:6px 0;background:var(--panel2)}
.tool.use{border-color:#2563eb55}.out{background:#0b1220;border:1px solid var(--border);border-radius:8px;padding:12px;margin-top:10px;max-height:340px;overflow:auto}
small{color:var(--muted)}
</style></head><body>
<header><h1>🛡️ Germano AI · Client</h1><span class="sub">Collega le AI alla rete protetta di Germano · solo locale</span><span id="ver" class="sub" style="margin-left:auto"></span></header>
<main>
  <div class="card">
    <h2>1 · Server Germano</h2>
    <div class="row">
      <div style="flex:2"><label>Indirizzo del server (vuoto = ricerca automatica in rete)</label><input id="server" placeholder="es. 192.168.1.10:8181"></div>
      <div><label>Token</label><input id="token" type="password" placeholder="token del server"></div>
    </div>
    <div class="row" style="margin-top:10px">
      <button class="sec" onclick="discover()">🔎 Cerca in rete</button>
      <button class="sec" onclick="saveCfg()">💾 Salva</button>
      <button onclick="refreshStatus()">↻ Verifica collegamento</button>
    </div>
    <div id="servers"></div>
    <div id="status" style="margin-top:10px"></div>
  </div>

  <div class="card">
    <h2>2 · AI del server</h2>
    <button class="sec" onclick="loadModels()">📋 Elenca le AI del server</button>
    <div id="models" style="margin-top:10px"></div>
  </div>

  <div class="card">
    <h2>3 · Chiedi a un'AI del server</h2>
    <div class="row"><div><label>AI</label><select id="askTool"></select></div>
      <div><label>Modello (facoltativo)</label><input id="askModel" placeholder="es. sonnet"></div></div>
    <label>Prompt (verra' anonimizzato dal server prima di uscire)</label><textarea id="askPrompt" placeholder="Scrivi la richiesta..."></textarea>
    <div style="margin-top:10px"><button onclick="ask()" id="askBtn">▶ Invia (protetto)</button></div>
    <div id="askOut"></div>
  </div>

  <div class="card">
    <h2>4 · Proteggi un testo o dei file</h2>
    <label>Testo</label><textarea id="protText" placeholder="Incolla qui il testo da proteggere..."></textarea>
    <label>File (max 12)</label><input id="protFiles" type="file" multiple>
    <div style="margin-top:10px"><button onclick="protect()" id="protBtn">🛡️ Proteggi</button></div>
    <div id="protOut"></div>
  </div>
</main>
<script>
const $=id=>document.getElementById(id);
async function jget(u){const r=await fetch(u);return r.json()}
async function jpost(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.json()}
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
async function loadCfg(){const c=await jget('/ui/config');$('server').value=c.server_url||'';if(c.token_set)$('token').placeholder='•••••••• (impostato)';}
async function saveCfg(){const r=await jpost('/ui/config',{server:$('server').value,token:$('token').value});if(r.status==='error'){alert(r.message)}else{$('token').value='';$('token').placeholder='•••••••• (impostato)';refreshStatus()}}
async function discover(){$('servers').innerHTML='<span class="muted">ricerca in corso…</span>';const r=await jget('/ui/discover');if(r.status==='error'){$('servers').innerHTML='<span class="pill err">'+esc(r.message)+'</span>';return}
 if(!r.servers.length){$('servers').innerHTML='<p class="muted">Nessun server trovato. Attiva la modalità Server sul PC server, oppure scrivi l\'indirizzo qui sopra.</p>';return}
 $('servers').innerHTML=r.servers.map(s=>`<div class="tool"><b>${esc(s.name||s.url)}</b> <small>${esc(s.url)} · v${esc(s.version||'?')} · ${s.engine_ready?'motore pronto':'motore non pronto'}</small> <button class="sec" onclick="pick('${esc(s.url)}')">usa</button></div>`).join('')}
function pick(u){$('server').value=u;saveCfg()}
async function refreshStatus(){$('status').innerHTML='<span class="muted">verifica…</span>';const r=await jget('/ui/status');
 if(r.status!=='ok'){$('status').innerHTML='<span class="pill err">non raggiungibile</span> <span class="muted">'+esc(r.message)+'</span>';return}
 const tok=r.token_ok?'<span class="pill ok">token '+esc(r.token)+'</span>':'<span class="pill err">token '+esc(r.token)+'</span>';
 const eng=r.engine_ready?'<span class="pill ok">motore pronto</span>':'<span class="pill warn">motore non pronto</span>';
 $('status').innerHTML=`<span class="pill ok">collegato</span> <b>${esc(r.name)}</b> <small>v${esc(r.version)} · ${r.ms} ms</small> ${eng} ${tok}`}
async function loadModels(){$('models').innerHTML='<span class="muted">caricamento…</span>';const r=await jget('/ui/models');
 if(r.status!=='ok'){$('models').innerHTML='<span class="pill err">'+esc(r.message)+'</span>';return}
 const sel=$('askTool');sel.innerHTML='';let html='';
 (r.tools||[]).forEach(t=>{const rm=t.remote||{};const usable=rm.usable;
   if(usable){const o=document.createElement('option');o.value=t.id;o.textContent=t.name+' ('+t.id+')';sel.appendChild(o)}
   html+=`<div class="tool ${usable?'use':''}"><b>${esc(t.name)}</b> <small>${esc(t.id)}${t.version?' · v'+esc(t.version):''}</small> `+
     (usable?'<span class="pill ok">usabile da qui</span>':'<span class="pill warn">non da remoto</span>')+
     (rm.reason?`<div class="muted" style="margin-top:4px">${esc(rm.reason)}</div>`:'')+`</div>`});
 if(!sel.options.length){const o=document.createElement('option');o.value='';o.textContent='(nessuna AI utilizzabile da qui)';sel.appendChild(o)}
 if(r.note)html='<p class="muted">'+esc(r.note)+'</p>'+html;
 $('models').innerHTML=html||'<p class="muted">Nessuna AI rilevata sul server.</p>'}
async function ask(){const t=$('askTool').value,p=$('askPrompt').value.trim();if(!t||!p){alert('Scegli un\'AI e scrivi un prompt.');return}
 $('askBtn').disabled=true;$('askOut').innerHTML='<div class="out muted">il server anonimizza ed esegue l\'AI… attendere…</div>';
 const r=await jpost('/ui/ask',{tool:t,prompt:p,model:$('askModel').value});
 $('askBtn').disabled=false;
 if(r.status!=='ok'){$('askOut').innerHTML='<div class="out"><span class="pill err">errore</span> '+esc(r.message)+'</div>';return}
 $('askOut').innerHTML='<div class="out"><div class="muted">risposta di '+esc(r.tool_name)+' ('+(r.seconds||'?')+'s · dati ripristinati da Germano)</div><div class="mono">'+esc(r.answer)+'</div></div>'}
async function protect(){const fd=new FormData();fd.append('prompt',$('protText').value);for(const f of $('protFiles').files)fd.append('files',f);
 $('protBtn').disabled=true;$('protOut').innerHTML='<div class="out muted">protezione in corso…</div>';
 const r=await (await fetch('/ui/protect',{method:'POST',body:fd})).json();
 $('protBtn').disabled=false;
 if(r.status!=='ok'){$('protOut').innerHTML='<div class="out"><span class="pill err">errore</span> '+esc(r.message)+'</div>';return}
 $('protOut').innerHTML='<div class="out"><div class="muted">🛡️ '+(r.entity_count||0)+' dati oscurati · etichette: '+esc((r.labels||[]).join(', ')||'nessuna')+'</div><div class="mono">'+esc(r.composed)+'</div></div>'}
loadCfg();fetch('/api/status').then(r=>r.json()).then(d=>$('ver').textContent='v'+d.version);refreshStatus();
</script></body></html>"""


def main():
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    from werkzeug.serving import run_simple
    run_simple("127.0.0.1", PORT, app, threaded=True, use_reloader=False, use_debugger=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
