from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")


def find_adb() -> str | None:
    candidates = [
        os.environ.get("DIANA_ADB_PATH"),
        shutil.which("adb"),
        os.path.join(os.environ.get("ANDROID_SDK_ROOT", ""), "platform-tools", "adb.exe"),
        os.path.join(os.environ.get("ANDROID_HOME", ""), "platform-tools", "adb.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def run_adb(args: list[str], serial: str | None = None, timeout: int = 20):
    adb = find_adb()
    if not adb:
        return {"ok": False, "error": "adb.exe not found; install Android SDK Platform-Tools"}

    command = [adb]
    if serial:
        command += ["-s", serial]
    command += args

    try:
        result = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ADB command timed out", "command": command}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "command": command}

    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
        "command": command,
    }


def list_devices():
    result = run_adb(["devices", "-l"])
    if not result["ok"]:
        return result
    devices = []
    for line in result["stdout"].splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "state": parts[1], "details": parts[2:]})
    return {"ok": True, "devices": devices}


def get_device_info(serial: str):
    if not serial.strip():
        return {"ok": False, "error": "serial is required"}
    props = {}
    errors = {}
    for name in [
        "ro.product.manufacturer",
        "ro.product.model",
        "ro.build.version.release",
        "ro.build.version.sdk",
    ]:
        result = run_adb(["shell", "getprop", name], serial=serial)
        if result["ok"]:
            props[name] = result.get("stdout", "")
        else:
            errors[name] = result.get("stderr") or result.get("error", "unknown ADB error")
    return {"ok": not errors, "serial": serial, "properties": props, "errors": errors}


def list_user_apps(serial: str):
    # -3 means third-party/user-installed packages; this is a read-only query.
    result = run_adb(["shell", "pm", "list", "packages", "-3"], serial=serial)
    if not result["ok"]:
        return result
    packages = [line.removeprefix("package:") for line in result["stdout"].splitlines() if line]
    return {"ok": True, "serial": serial, "packages": packages}


def read_only_device_check(serial: str):
    # Fixed read-only commands only; user input is never inserted into shell text.
    checks = {
        "state": ["get-state"],
        "battery": ["shell", "dumpsys", "battery"],
        "storage": ["shell", "df", "-h", "/sdcard"],
    }
    output = {}
    for name, args in checks.items():
        output[name] = run_adb(args, serial=serial)
    return {"ok": all(item["ok"] for item in output.values()), "checks": output}


def validate_package_name(package_name: str) -> bool:
    return bool(PACKAGE_RE.fullmatch(package_name.strip()))