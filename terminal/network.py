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
