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


def _usable(ip):
    """Indirizzo raggiungibile dagli altri computer: niente loopback, niente APIPA 169.254.x.x (scheda senza DHCP,
    tipica delle schede virtuali scollegate), niente 0.0.0.0."""
    return bool(ip) and not ip.startswith(("127.", "169.254.", "0."))


def local_ipv4_addresses():
    """IPv4 di questo computer raggiungibili dalla rete, PRIMA quelle delle schede usate per uscire verso la rete
    (anche schede virtuali: VirtIO, vmxnet3, Hyper-V, bridge), poi le altre (es. switch interni dell'hypervisor)."""
    primary = []
    # L'indirizzo che il sistema sceglie per raggiungere la rete: nessun pacchetto inviato (UDP senza dati).
    for probe in ("10.255.255.255", "172.31.255.255", "192.168.255.255", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect((probe, 1))
                ip = s.getsockname()[0]
                if _usable(ip) and ip not in primary:
                    primary.append(ip)
            finally:
                s.close()
        except OSError:
            pass
    others = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _usable(ip) and ip not in primary:
                others.add(ip)
    except (socket.gaierror, OSError):
        pass
    return primary + sorted(others)


class DiscoveryResponder:
    """Thread UDP che risponde ai ping di rilevamento con le info fornite da `info_provider()` (un dict)."""

    _INFO_TTL = 3.0
    _MIN_INTERVAL = 0.25
    _MAX_IPS = 512

    def __init__(self, info_provider, port=DEFAULT_PORT):
        self.info_provider = info_provider
        self.port = port
        self._sock = None
        self._thread = None
        self._stop = threading.Event()
        self._cache_at = 0.0
        self._cache_payload = None
        self._seen = {}

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        else:
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

    def _payload(self, now):
        if self._cache_payload is None or now - self._cache_at >= self._INFO_TTL:
            info = dict(self.info_provider() or {})
            info["service"] = "germano-server"
            self._cache_payload = json.dumps(info, ensure_ascii=False).encode("utf-8")
            self._cache_at = now
        return self._cache_payload

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
            now = time.time()
            ip = addr[0]
            if now - self._seen.get(ip, 0.0) < self._MIN_INTERVAL:
                continue
            if len(self._seen) > self._MAX_IPS:
                self._seen = {k: v for k, v in self._seen.items() if now - v < 60.0}
            self._seen[ip] = now
            try:
                self._sock.sendto(self._payload(now), addr)
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
        packets = 0
        end = time.time() + timeout
        while packets < 256 and len(found) < 64:
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
            packets += 1
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
            # Chiave per (IP, porta): un host malevolo non puo' sopprimere il vero server copiandone instance_id
            key = (addr[0], info["port"])
            if key not in found:
                found[key] = info
        items = list(found.values())
        # La risposta da 127.0.0.1 e' un doppione di quella arrivata dall'IP di rete quando instance_id o (nome, porta) coincidono.
        lan_inst = {i.get("instance_id") for i in items if i.get("instance_id") and not i["ip"].startswith("127.")}
        lan_np = {(i.get("name"), i["port"]) for i in items if not i["ip"].startswith("127.")}
        return [i for i in items if not i["ip"].startswith("127.")
                or (i.get("instance_id") not in lan_inst and (i.get("name"), i["port"]) not in lan_np)]
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
