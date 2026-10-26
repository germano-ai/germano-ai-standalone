"""Rilevamento automatico del server sulla LAN (UDP broadcast).

Il server, quando e' in ascolto sulla rete, apre un piccolo listener UDP (porta 8182 per impostazione predefinita)
che risponde ai ping `GERMANO_DISCOVERY_PING` con le proprie informazioni (servizio, versione, porta, nome).
Nessun dato personale e nessun token viene mai diffuso: solo i metadati necessari a un client per connettersi.
Lo stesso file e' usato dal Germano Server e dal Germano Client: le due copie devono restare identiche.
"""
import json
import socket
import threading
import time

PING = b"GERMANO_DISCOVERY_PING"
DEFAULT_PORT = 8182
_MAX = 2048


def local_ipv4_addresses():
    """IPv4 non di loopback di questo computer (per mostrarle nel banner del server)."""
    addrs = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                addrs.add(ip)
    except socket.gaierror:
        pass
    # Ripiego affidabile: l'indirizzo scelto dal sistema per uscire verso la LAN (nessun pacchetto inviato).
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("192.168.255.255", 1))
            ip = s.getsockname()[0]
            if not ip.startswith("127."):
                addrs.add(ip)
        finally:
            s.close()
    except OSError:
        pass
    return sorted(addrs)


class DiscoveryResponder:
    """Thread UDP che risponde ai ping di rilevamento con le info fornite da `info_provider()` (un dict)."""

    def __init__(self, info_provider, port=DEFAULT_PORT):
        self.info_provider = info_provider
        self.port = port
        self._sock = None
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            pass
        sock.bind(("0.0.0.0", self.port))
        sock.settimeout(0.5)
        self._sock = sock
        self._thread = threading.Thread(target=self._serve, name="germano-discovery", daemon=True)
        self._thread.start()
        return self.port

    def _serve(self):
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(_MAX)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue   # Windows: notifica ICMP di una risposta precedente, non un errore del listener
            except OSError:
                break
            if not data or not data.startswith(PING):
                continue
            try:
                info = dict(self.info_provider() or {})
                info["service"] = "germano-server"
                payload = json.dumps(info, ensure_ascii=False).encode("utf-8")
                self._sock.sendto(payload, addr)
            except Exception:
                pass

    def stop(self):
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass


def discover(timeout=1.0, port=DEFAULT_PORT, broadcasts=None, exclude_instance=None):
    """Lato client: invia un ping in broadcast e raccoglie per `timeout` secondi le risposte dei server Germano.
    Restituisce una lista di dict con almeno {ip, port, version, name}. Lo stesso server risponde anche da piu'
    interfacce (es. 127.0.0.1 e l'IP di rete): si tiene una sola voce per server, preferendo l'IP di rete.
    `exclude_instance` esclude questa stessa installazione."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    targets = list(broadcasts or []) + ["255.255.255.255", "127.0.0.1"]
    try:
        sock.bind(("", 0))
        for b in dict.fromkeys(targets):
            try:
                sock.sendto(PING, (b, port))
            except OSError:
                pass
        found = {}
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                break
            sock.settimeout(left)
            try:
                data, addr = sock.recvfrom(_MAX)
            except socket.timeout:
                break
            except ConnectionResetError:
                # Windows: il ping verso un indirizzo dove non c'e' un server (di solito 127.0.0.1 su un PC client)
                # torna come "porta irraggiungibile" e fa fallire la ricezione successiva. Non e' una risposta:
                # si continua ad ascoltare, altrimenti si perderebbero i server della rete.
                continue
            except OSError:
                break
            try:
                info = json.loads(data.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            if not isinstance(info, dict) or info.get("service") != "germano-server":
                continue
            try:
                info["port"] = int(info.get("port"))
            except (TypeError, ValueError):
                continue
            if not 0 < info["port"] < 65536:
                continue
            inst = str(info.get("instance_id") or "")
            if exclude_instance and inst == exclude_instance:
                continue
            info["ip"] = addr[0]
            key = inst or (addr[0], info["port"])
            prev = found.get(key)
            if prev is None or (prev["ip"].startswith("127.") and not addr[0].startswith("127.")):
                found[key] = info
        items = list(found.values())
        # Server senza identificativo (versioni precedenti): la risposta da 127.0.0.1 e' un doppione di quella
        # arrivata dall'IP di rete quando nome e porta coincidono.
        lan = {(i.get("name"), i["port"]) for i in items if not i["ip"].startswith("127.")}
        return [i for i in items if i.get("instance_id") or not i["ip"].startswith("127.")
                or (i.get("name"), i["port"]) not in lan]
    finally:
        sock.close()


def broadcast_addresses():
    """Indirizzi di broadcast delle interfacce IPv4 locali (per coprire piu' sottoreti)."""
    out = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127."):
                continue
            parts = ip.split(".")
            if len(parts) == 4:
                out.append(".".join(parts[:3]) + ".255")   # broadcast /24 (caso piu' comune in ufficio)
    except socket.gaierror:
        pass
    return sorted(set(out))
