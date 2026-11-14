"""UTCP (Universal Tool Calling Protocol) e OpenAPI di Germano AI (0.95, turno 30).

Il manuale UTCP e il documento OpenAPI 3.1 sono generati dal registro canonico germano/integrations.py: stessi nomi,
stessi schemi e stessi gestori del Server MCP e delle API REST /api/v1/*.

Formato verificato sulle implementazioni ufficiali (14/11/2026):
- UTCP 1.0 (python-utcp 1.x, typescript-utcp): manuale {utcp_version, manual_version, tools}; ogni strumento ha name,
  description, inputs, outputs (JSON Schema), tags, average_response_size e tool_call_template. Il client TypeScript
  rifiuta qualsiasi altra chiave nel manuale e negli strumenti (zod .strict()): il manuale predefinito contiene SOLO
  queste. Le chiavi «tool_provider» e «provider_type» sono del formato 0.1 (deprecato): disponibili con
  ?format=legacy. Il crate Rust rs-utcp richiede anche «info»: ?format=extended.
- Chiamata HTTP (call_template_type "http"): gli argomenti che non sono intestazioni o parametri del percorso vanno
  nella query, TRANNE il campo indicato da body_field (predefinito "body") che diventa il corpo JSON. Per questo gli
  ingressi degli strumenti POST sono {"body": <schema dell'argomento>}: il client invia il corpo JSON atteso da
  /api/v1/<strumento> (che accetta anche la forma {"body": {...}}).
- Dalla rete (parte Server) le chiamate richiedono il token delle integrazioni: auth api_key nell'intestazione
  Authorization con la variabile ${API_TOKEN}, che il client risolve con il nome del manuale come prefisso (es.
  germano_API_TOKEN). Da questo computer nessuna autenticazione.
"""
import re

from . import integrations as gint

UTCP_VERSION = "1.0.1"
MANUAL_VERSION = "1.0.0"
LEGACY_VERSION = "0.1.0"
CALL_TEMPLATE_NAME = "germano"
_TOOL_KEYS = {"name", "description", "inputs", "outputs", "tags", "average_response_size", "tool_call_template"}
_MANUAL_KEYS = {"utcp_version", "manual_version", "tools"}
_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")

ERROR_SCHEMA = {"type": "object", "properties": {
    "status": {"type": "string", "enum": ["error", "blocked"],
               "description": "blocked = stopped for protection (engine not ready): no data left the computer."},
    "code": {"type": "string"}, "message": {"type": "string"}, "tool": {"type": "string"},
    "retry_after": {"type": "integer"}}, "required": ["status", "code", "message"]}


def _url(base, prefix, spec):
    return f"{base.rstrip('/')}{prefix or ''}/api/v1/{spec['route']}"


def _auth(local):
    if local:
        return None
    return {"auth_type": "api_key", "api_key": "Bearer ${API_TOKEN}", "var_name": "Authorization",
            "location": "header"}


def _call_template(spec, base, local, prefix):
    tpl = {"name": CALL_TEMPLATE_NAME, "call_template_type": "http", "http_method": spec["method"],
           "url": _url(base, prefix, spec), "content_type": "application/json"}
    if spec["method"] != "GET":
        tpl["body_field"] = "body"
    auth = _auth(local)
    if auth:
        tpl["auth"] = auth
    return tpl


def _inputs(spec):
    if spec["method"] == "GET":
        return {"type": "object", "properties": {}}
    body = dict(spec["input"])
    body["description"] = "JSON body of the request (the tool arguments)."
    return {"type": "object", "properties": {"body": body}, "required": ["body"]}


def manual(base, local=True, fmt="1.0", prefix=""):
    """Manuale UTCP. fmt: "1.0" (predefinito, solo chiavi standard), "extended" (+ info, per rs-utcp e persone),
    "legacy" (formato 0.1 con tool_provider/provider_type)."""
    tools = []
    for t in gint.TOOLS:
        tools.append({"name": t["name"], "description": t["description"], "inputs": _inputs(t),
                      "outputs": t["output"], "tags": list(t["tags"]),
                      "average_response_size": int(t["average_response_size"]),
                      "tool_call_template": _call_template(t, base, local, prefix)})
    if fmt == "legacy":
        legacy = []
        for item in tools:
            tpl = dict(item.pop("tool_call_template"))
            tpl.pop("call_template_type", None)
            provider = {"name": tpl.pop("name"), "provider_type": "http"}
            provider.update(tpl)
            legacy.append(dict(item, tool_provider=provider))
        return {"version": LEGACY_VERSION, "tools": legacy}
    out = {"utcp_version": UTCP_VERSION, "manual_version": MANUAL_VERSION, "tools": tools}
    if fmt == "extended":
        out["info"] = {"title": gint.TITLE, "version": gint.version(),
                       "description": "Germano AI: local anonymization (input) and restoration (output) of personal "
                                      "data for AI workflows. Same tools as the MCP server at /mcp."}
    return out


def validate_manual(m, strict=True):
    """Controllo strutturale di un manuale UTCP 1.0 (le regole dei client ufficiali). {valid, errors, tools}."""
    errors = []
    if not isinstance(m, dict):
        return {"valid": False, "errors": ["manual is not an object"], "tools": 0}
    if strict:
        extra = set(m) - _MANUAL_KEYS
        if extra:
            errors.append(f"unknown manual keys: {sorted(extra)}")
    for key in ("utcp_version", "manual_version"):
        if not isinstance(m.get(key), str) or not re.match(r"^\d+\.\d+(\.\d+)?", m.get(key) or ""):
            errors.append(f"{key} must be a version string")
    tools = m.get("tools")
    if not isinstance(tools, list) or not tools:
        errors.append("tools must be a non-empty list")
        tools = []
    names = set()
    for i, t in enumerate(tools):
        where = f"tools[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{where} is not an object")
            continue
        if strict and set(t) - _TOOL_KEYS:
            errors.append(f"{where}: unknown keys {sorted(set(t) - _TOOL_KEYS)}")
        name = t.get("name")
        if not isinstance(name, str) or not re.match(r"^[A-Za-z0-9_.-]{1,128}$", name or ""):
            errors.append(f"{where}: invalid name")
        elif name in names:
            errors.append(f"{where}: duplicate name {name}")
        names.add(name)
        if not isinstance(t.get("description", ""), str):
            errors.append(f"{where}: description must be a string")
        for key in ("inputs", "outputs"):
            sch = t.get(key)
            if not isinstance(sch, dict) or sch.get("type") != "object":
                errors.append(f"{where}: {key} must be a JSON Schema of type object")
        if not isinstance(t.get("tags", []), list) or not all(isinstance(x, str) for x in t.get("tags", [])):
            errors.append(f"{where}: tags must be a list of strings")
        if "average_response_size" in t and not isinstance(t["average_response_size"], int):
            errors.append(f"{where}: average_response_size must be an integer")
        tpl = t.get("tool_call_template")
        if not isinstance(tpl, dict):
            errors.append(f"{where}: tool_call_template missing")
            continue
        if tpl.get("call_template_type") != "http":
            errors.append(f"{where}: call_template_type must be http")
        if tpl.get("http_method") not in _METHODS:
            errors.append(f"{where}: invalid http_method")
        if not isinstance(tpl.get("url"), str) or not re.match(r"^https?://", tpl.get("url") or ""):
            errors.append(f"{where}: invalid url")
        if not isinstance(tpl.get("content_type", "application/json"), str):
            errors.append(f"{where}: invalid content_type")
        body_field = tpl.get("body_field")
        if tpl.get("http_method") != "GET":
            props = (t.get("inputs") or {}).get("properties") or {}
            if not body_field or body_field not in props:
                errors.append(f"{where}: body_field must name an input property")
        auth = tpl.get("auth")
        if auth is not None:
            if not isinstance(auth, dict) or auth.get("auth_type") != "api_key" or not auth.get("api_key") \
                    or auth.get("location") not in ("header", "query", "cookie") or not auth.get("var_name"):
                errors.append(f"{where}: invalid auth")
    return {"valid": not errors, "errors": errors, "tools": len(tools)}


def openapi(base, local=True, prefix=""):
    """Documento OpenAPI 3.1 delle API /api/v1/* (stessi schemi del registro). Anche un client UTCP puo' registrarlo:
    lo converte da solo in strumenti."""
    paths = {}
    err = {"description": "Error (status error) or protection block (status blocked).",
           "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}}
    for t in gint.TOOLS:
        op = {"operationId": t["name"], "summary": t["title"], "description": t["description"], "tags": [t["tags"][0]],
              "responses": {"200": {"description": "Success",
                                    "content": {"application/json": {"schema": t["output"]}}},
                            "400": err, "401": err, "403": err, "404": err, "409": err, "413": err, "415": err,
                            "422": err, "500": err, "503": err}}
        if t["method"] != "GET":
            op["requestBody"] = {"required": True, "content": {"application/json": {"schema": t["input"]}}}
        paths[f"/api/v1/{t['route']}"] = {t["method"].lower(): op}
    doc = {
        "openapi": "3.1.0",
        "info": {"title": gint.TITLE, "version": gint.version(),
                 "description": "Local anonymization (input) and restoration (output) of personal data for AI "
                                "workflows. The same tools are available through MCP (/mcp) and UTCP (/utcp).",
                 "license": {"name": "GNU General Public License v3.0"}},
        "servers": [{"url": f"{base.rstrip('/')}{prefix or ''}"}],
        "paths": paths,
        "components": {"schemas": {"Error": ERROR_SCHEMA},
                       "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer",
                                                          "description": "Integration token (Settings > Integrations); "
                                                                         "required only from the network."}}},
        "tags": [{"name": "input"}, {"name": "output"}, {"name": "workflow"}, {"name": "status"}],
    }
    if not local:
        doc["security"] = [{"bearerAuth": []}]
    return doc
