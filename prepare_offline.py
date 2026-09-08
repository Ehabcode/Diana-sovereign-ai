#!/usr/bin/env python3
"""Offline readiness checker for Diana. It only checks local files and localhost services."""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
REQUIRED_FILES = [
    ROOT / "app" / "main.cjs",
    ROOT / "app" / "preload.cjs",
    ROOT / "python" / "server.py",
    ROOT / "python" / "language_filter.py",
    ROOT / "python" / "reference_voice.wav",
    ROOT / "renderer" / "index.html",
    ROOT / "renderer" / "ide.html",
    ROOT / "renderer" / "ide-renderer.js",
    ROOT / "renderer" / "style.css",
    ROOT / "vendor" / "monaco-vs" / "loader.js",
    ROOT / "vendor" / "monaco-vs" / "editor" / "editor.main.js",
    ROOT / "vendor" / "xterm" / "xterm.js",
    ROOT / "vendor" / "xterm" / "xterm.css",
    ROOT / "vendor" / "xterm-addon-fit" / "xterm-addon-fit.js",
]
PYTHON_MODULES = ["flask", "requests", "numpy", "soundfile", "sounddevice", "torch", "torchaudio", "TTS"]
MODEL_GROUPS = {
    "texty": ["diana-texty", "qwen3:8b"],
    "coding": ["diana-coding", "qwen2.5-coder:7b"],
}


def local_get(url: str):
    request = Request(url, headers={"User-Agent": "Diana-Offline-Check"})
    with urlopen(request, timeout=2) as response:
        return response.read().decode("utf-8")


def local_module_status():
    status = {}
    for name in PYTHON_MODULES:
        try:
            importlib.import_module(name)
            status[name] = True
        except Exception as exc:
            status[name] = f"ERROR: {exc}"
    return status


def main() -> int:
    report = {
        "files": {},
        "ollama": {},
        "python": {},
        "network_policy": "local-only",
    }
    problems = []

    for path in REQUIRED_FILES:
        ok = path.is_file()
        report["files"][str(path.relative_to(ROOT))] = ok
        if not ok:
            problems.append(f"missing: {path.relative_to(ROOT)}")

    report["python"] = {
        "executable": sys.executable,
        "version": sys.version.split()[0],
        "modules": local_module_status(),
        "ollama_binary": shutil.which("ollama") or "not found",
    }
    for module, present in report["python"]["modules"].items():
        if present is not True:
            problems.append(f"Python module unavailable: {module} ({present})")

    try:
        raw = local_get("http://127.0.0.1:11434/api/tags")
        tags = json.loads(raw).get("models", [])
        names = {item.get("name") for item in tags}
        report["ollama"]["reachable"] = True
        report["ollama"]["models"] = sorted(name for name in names if name)
        report["ollama"]["selected_models"] = {}
        for role, choices in MODEL_GROUPS.items():
            selected = next((name for name in choices if name in names), None)
            report["ollama"]["selected_models"][role] = selected
            if not selected:
                problems.append(f"Ollama model missing for {role}: one of {choices}")
    except Exception as exc:
        report["ollama"] = {"reachable": False, "error": str(exc)}
        problems.append("Ollama is not reachable at 127.0.0.1:11434")

    out = ROOT / "offline_readiness.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if problems:
        print("\nNOT READY:")
        print("\n".join(f"- {item}" for item in problems))
        return 1
    print("\nREADY: local files, Python dependencies, and Ollama models are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
