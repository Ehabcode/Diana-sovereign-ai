from __future__ import annotations

import os
import shutil
from pathlib import Path

try:
    import psutil
except ImportError:  # optional until storage inventory is used
    psutil = None


def list_storage_mounts() -> list[dict]:
    """Return mounted filesystems visible to the current user, read-only."""
    if psutil is None:
        return []
    items = []
    for partition in psutil.disk_partitions(all=False):
        mountpoint = partition.mountpoint
        try:
            usage = shutil.disk_usage(mountpoint)
        except OSError:
            continue
        items.append({
            "device": partition.device,
            "mountpoint": mountpoint,
            "filesystem": partition.fstype,
            "options": partition.opts,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
        })
    return items


def list_removable_mounts() -> list[dict]:
    """Return removable mounts where the host OS exposes that classification."""
    mounts = list_storage_mounts()
    if not mounts:
        return mounts
    if os.name == "nt":
        import ctypes
        removable = []
        for item in mounts:
            try:
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(item["mountpoint"])
                if drive_type == 2:  # DRIVE_REMOVABLE
                    removable.append(item)
            except (AttributeError, OSError):
                continue
        return removable
    removable = []
    for item in mounts:
        device = item.get("device", "")
        name = os.path.basename(device)
        flag = Path("/sys/class/block") / name / "removable"
        try:
            if flag.read_text(encoding="ascii").strip() == "1":
                removable.append(item)
        except (OSError, UnicodeError):
            continue
    return removable


def list_directory(path: str, max_entries: int = 200) -> dict:
    """Read a directory listing without opening files or executing anything."""
    target = Path(os.path.expanduser(path)).resolve()
    if not target.is_dir():
        return {"ok": False, "error": f"not a directory: {target}"}
    try:
        entries = []
        for item in sorted(target.iterdir(), key=lambda p: p.name.lower())[:max_entries]:
            entries.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else None,
            })
        return {"ok": True, "path": str(target), "entries": entries}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
