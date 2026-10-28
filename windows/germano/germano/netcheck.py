"""Controlli di rete della parte Server su Windows (sola lettura, senza permessi di amministratore).

Spiegano all'amministratore perche' i client della rete non raggiungono Germano, anche su Windows Server e sulle
macchine virtuali: rete classificata come «Pubblica» (la regola di Germano vale solo per le reti private e di
dominio: tipico delle VM e dei server in gruppo di lavoro), regola del firewall mancante, disattivata o per un altro
programma, criteri di gruppo che ignorano le regole locali del firewall. Una sola interrogazione di PowerShell
(circa 2 secondi) in un thread separato, ripetuta al massimo ogni 2 minuti.
"""
import json
import os
import subprocess
import sys
import threading
import time

RULE = "Germano AI (Server LAN)"
TTL = 120.0
_PS = (r"[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ErrorActionPreference='SilentlyContinue'; "
       r"$p=@(Get-NetConnectionProfile|Select-Object InterfaceAlias,NetworkCategory); "
       r"$f=@(Get-NetFirewallProfile -PolicyStore ActiveStore|Select-Object Name,Enabled,AllowLocalFirewallRules); "
       r"$r=@(Get-NetFirewallRule -DisplayName '" + RULE + r"'|ForEach-Object{[pscustomobject]@{Enabled=[string]$_.Enabled;"
       r"Action=[string]$_.Action;Profile=[string]$_.Profile;Program=($_|Get-NetFirewallApplicationFilter).Program}}); "
       r"@{profiles=$p;firewall=$f;rules=$r}|ConvertTo-Json -Depth 4 -Compress")
_lock = threading.Lock()
_state = {"time": 0.0, "running": False, "warnings": None}


def query():
    """Stato di reti e firewall da PowerShell (dict), o None se non disponibile."""
    exe = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "WindowsPowerShell", "v1.0",
                       "powershell.exe")
    r = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _PS],
                       capture_output=True, timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    text = (r.stdout or b"").decode("utf-8", errors="replace").strip()
    return json.loads(text) if text.startswith("{") else None


def _same_program(a, b):
    def norm(p):
        return os.path.normcase(os.path.abspath(os.path.expandvars(str(p or "").strip().strip('"'))))
    return bool(a and b) and norm(a) == norm(b)


def analyze(data, program, installed, port, discovery_port):
    """Avvisi [{code, it, en, command}] dai dati di query()."""
    out = []
    for p in (data or {}).get("profiles") or []:
        if p.get("NetworkCategory") == 0:
            alias = p.get("InterfaceAlias") or "?"
            out.append({
                "code": "public_network",
                "it": f"La rete «{alias}» è classificata come Pubblica: Windows blocca i computer della rete (la regola "
                      "di Germano vale per le reti private e di dominio, come scelto per la sicurezza). Se è la rete "
                      "dell'ufficio impostala come Privata, da PowerShell come amministratore:",
                "en": f"The «{alias}» network is classified as Public: Windows blocks the network computers (Germano's "
                      "rule applies to private and domain networks, by design). If it is the office network set it to "
                      "Private, from PowerShell as administrator:",
                "command": f'Set-NetConnectionProfile -InterfaceAlias "{alias}" -NetworkCategory Private'})
    rules = (data or {}).get("rules") or []
    good = [r for r in rules if r.get("Enabled") == "True" and r.get("Action") == "Allow"
            and _same_program(r.get("Program"), program)]
    if installed and not good:
        why_it = "manca" if not rules else "è disattivata o riguarda un altro programma"
        why_en = "is missing" if not rules else "is disabled or refers to another program"
        cmd = (f'netsh advfirewall firewall add rule name="{RULE}" dir=in action=allow program="{program}" '
               'enable=yes profile=private,domain')
        out.append({
            "code": "firewall_rule",
            "it": f"La regola del firewall «{RULE}» {why_it}: i computer della rete non raggiungono Germano. Reinstalla "
                  "Germano accettando la richiesta dei permessi, oppure da un prompt dei comandi come amministratore:",
            "en": f"The «{RULE}» firewall rule {why_en}: the network computers cannot reach Germano. Reinstall Germano "
                  "accepting the permission prompt, or from a command prompt as administrator:",
            "command": cmd})
    for fw in (data or {}).get("firewall") or []:
        if fw.get("Enabled") == 1 and fw.get("AllowLocalFirewallRules") == 0 and fw.get("Name") in ("Domain", "Private"):
            name = {"Domain": ("Dominio", "Domain"), "Private": ("Privata", "Private")}[fw["Name"]]
            out.append({
                "code": "gpo_local_rules",
                "it": f"I criteri di gruppo ignorano le regole locali del firewall (profilo {name[0]}): l'amministratore "
                      f"di dominio deve consentire {program} (TCP {port} e UDP {discovery_port}) con un criterio.",
                "en": f"Group Policy ignores local firewall rules ({name[1]} profile): the domain administrator must "
                      f"allow {program} (TCP {port} and UDP {discovery_port}) with a policy.",
                "command": ""})
    return out


def warnings(program=None, installed=False, port=8181, discovery_port=8182, wait=False):
    """Ultimi avvisi noti (lista) o None se il primo controllo e' ancora in corso. Su Windows avvia un controllo in
    background quando i dati hanno piu' di TTL secondi; altrove restituisce sempre []."""
    if os.name != "nt":
        return []
    program = program or sys.executable
    with _lock:
        stale = time.time() - _state["time"] > TTL
        start = stale and not _state["running"]
        if start:
            _state["running"] = True
    if start:
        def run():
            try:
                data = query()
                res = analyze(data, program, installed, port, discovery_port) if data is not None else []
            except Exception:
                res = []
            with _lock:
                _state.update(time=time.time(), running=False, warnings=res)
        t = threading.Thread(target=run, name="germano-netcheck", daemon=True)
        t.start()
        if wait:
            t.join(60)
    with _lock:
        return _state["warnings"]
