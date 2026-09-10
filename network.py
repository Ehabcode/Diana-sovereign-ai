from __future__ import annotations

try:
    import psutil
except ImportError:
    psutil = None


def local_network_inventory() -> dict:
    """Return local interface/address/stat information only; no network probes."""
    if psutil is None:
        return {"ok": False, "error": "psutil is not installed"}

    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    io = psutil.net_io_counters(pernic=True)
    interfaces = []
    for name, values in addresses.items():
        stat = stats.get(name)
        counters = io.get(name)
        interfaces.append({
            "name": name,
            "is_up": stat.isup if stat else None,
            "speed_mbps": stat.speed if stat else None,
            "mtu": stat.mtu if stat else None,
            "addresses": [
                {
                    "family": str(value.family),
                    "address": value.address,
                    "netmask": value.netmask,
                    "broadcast": value.broadcast,
                }
                for value in values
            ],
            "io": {
                "bytes_sent": counters.bytes_sent,
                "bytes_received": counters.bytes_recv,
                "packets_sent": counters.packets_sent,
                "packets_received": counters.packets_recv,
            } if counters else None,
        })
    return {"ok": True, "interfaces": interfaces}


def list_processes() -> dict:
    if psutil is None:
        return {"ok": False, "error": "psutil is not installed"}
    processes = []
    for process in psutil.process_iter(["pid", "name", "username"]):
        try:
            processes.append(process.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"ok": True, "processes": processes}


# Ports/services this machine itself is listening on - not a scanner. Reads
# the same local connection table `netstat -an` would show; never sends a
# single packet to another host and never touches any other device.
_KNOWN_PORT_NAMES = {
    20: "FTP-data", 21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    53: "DNS", 80: "HTTP", 110: "POP3", 123: "NTP", 135: "RPC (Windows)",
    139: "NetBIOS", 143: "IMAP", 443: "HTTPS", 445: "SMB",
    3306: "MySQL", 3389: "RDP", 5000: "Flask/dev server", 5432: "PostgreSQL",
    5900: "VNC", 6379: "Redis", 8080: "HTTP-alt", 11434: "Ollama",
}
# Ports that are routine on localhost but worth a second look if bound to
# every interface (0.0.0.0/::) instead of just 127.0.0.1 - informational
# flag only, never a verdict.
_COMMONLY_RISKY_IF_EXPOSED = {23, 135, 139, 445, 3389, 5900}


def local_open_ports() -> dict:
    """Local listening ports/services only, cross-referenced with the owning
    process name - no scanning, no probing, no packets sent anywhere."""
    if psutil is None:
        return {"ok": False, "error": "psutil is not installed"}
    listening = []
    seen = set()
    for conn in psutil.net_connections(kind="inet"):
        if conn.status != psutil.CONN_LISTEN or not conn.laddr:
            continue
        addr, port = conn.laddr.ip, conn.laddr.port
        key = (addr, port)
        if key in seen:
            continue
        seen.add(key)
        proc_name = None
        if conn.pid:
            try:
                proc_name = psutil.Process(conn.pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc_name = None
        listening.append({
            "address": addr,
            "port": port,
            "service_guess": _KNOWN_PORT_NAMES.get(port),
            "process": proc_name,
            "pid": conn.pid,
            "exposed_beyond_localhost": addr not in ("127.0.0.1", "::1"),
            "commonly_risky_if_exposed": port in _COMMONLY_RISKY_IF_EXPOSED,
        })
    listening.sort(key=lambda item: item["port"])
    return {"ok": True, "listening_ports": listening}


# ---------- Home network device scan ----------
# Unlike everything else in this module, this ACTIVELY sends traffic
# (a ping sweep) to other devices - it is restricted to the private LAN
# subnet(s) this machine's own interfaces already sit on, never anything
# beyond that, and the caller (diana_coding.py) always asks the user for
# y/n confirmation before running it - same as write_file or a shell command.
import ipaddress
import platform
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed


def _own_ipv4_lan_networks():
    if psutil is None:
        return []
    networks = []
    for name, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET and addr.netmask and not addr.address.startswith("127."):
                try:
                    network = ipaddress.ip_interface(f"{addr.address}/{addr.netmask}").network
                except ValueError:
                    continue
                # Cap at /22 (1024 addresses) - a home LAN is normally /24;
                # this is a safety limit against accidentally sweeping
                # something much larger than a home network.
                if network.is_private and network.num_addresses <= 1024:
                    networks.append((name, network))
    return networks


def _ping_once(ip, timeout_ms=250):
    if platform.system() == "Windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), str(ip)]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), str(ip)]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=(timeout_ms / 1000) + 1,
        )
        return result.returncode == 0
    except Exception:
        return False


def _read_arp_table():
    """Reads the OS's own ARP cache (already populated by the ping sweep
    above) for IP -> MAC - this is reading existing OS state, not a
    separate probe of its own."""
    table = {}
    try:
        if platform.system() == "Windows":
            output = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5).stdout
            for line in output.splitlines():
                m = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})", line)
                if m:
                    table[m.group(1)] = m.group(2).replace("-", ":").lower()
        else:
            output = subprocess.run(["arp", "-n"], capture_output=True, text=True, timeout=5).stdout
            for line in output.splitlines():
                m = re.match(r"(\d+\.\d+\.\d+\.\d+)\s+.*?([0-9a-fA-F:]{17})", line)
                if m:
                    table[m.group(1)] = m.group(2).lower()
    except Exception:
        pass
    return table


def _reverse_dns(ip, timeout_sec=0.4):
    try:
        socket.setdefaulttimeout(timeout_sec)
        return socket.gethostbyaddr(str(ip))[0]
    except Exception:
        return None
    finally:
        socket.setdefaulttimeout(None)


def local_network_scan(timeout_ms=250, max_workers=64) -> dict:
    networks = _own_ipv4_lan_networks()
    if not networks:
        return {"ok": False, "error": "No private IPv4 LAN interface found to scan"}

    own_ips = {
        addr.address
        for addrs in psutil.net_if_addrs().values()
        for addr in addrs
        if addr.family == socket.AF_INET
    }

    alive = {}
    for iface_name, network in networks:
        hosts = list(network.hosts())
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_ping_once, ip, timeout_ms): ip for ip in hosts}
            for future in as_completed(futures):
                ip = futures[future]
                if future.result():
                    alive[str(ip)] = iface_name

    arp_table = _read_arp_table()
    devices = [
        {
            "ip": ip,
            "mac": arp_table.get(ip),
            "hostname": _reverse_dns(ip),
            "interface": iface_name,
            "is_this_machine": ip in own_ips,
        }
        for ip, iface_name in alive.items()
    ]
    devices.sort(key=lambda d: tuple(int(p) for p in d["ip"].split(".")))
    return {
        "ok": True,
        "devices": devices,
        "subnets_scanned": [str(n) for _, n in networks],
    }
