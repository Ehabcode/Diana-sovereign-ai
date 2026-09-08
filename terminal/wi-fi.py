import psutil


def local_network_inventory():
    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    result = []
    for name, values in addresses.items():
        result.append({
            "name": name,
            "is_up": stats.get(name).isup if name in stats else None,
            "addresses": [
                {"family": str(v.family), "address": v.address, "netmask": v.netmask}
                for v in values
            ],
        })
    return result