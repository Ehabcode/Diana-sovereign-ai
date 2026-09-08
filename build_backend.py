#!/usr/bin/env python3
"""Build the Diana Flask backend with PyInstaller when dependencies are installed."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "python" / "server.py"
DIST = ROOT / "backend"

if shutil.which("pyinstaller") is None:
    raise SystemExit("PyInstaller is not installed. Install it during the online build step.")

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm", "--clean", "--onedir",
    "--name", "diana-backend",
    "--distpath", str(DIST),
    "--workpath", str(ROOT / "build" / "pyinstaller"),
    "--specpath", str(ROOT / "build"),
    "--collect-all", "TTS",
    "--collect-all", "torch",
    "stripped-placeholder",
]
cmd[-1] = str(SERVER)
subprocess.run(cmd, cwd=ROOT, check=True)
print(f"Backend built under: {DIST / 'diana-backend'}")
print("Copy the XTTS-v2 cache into models/tts before packaging Electron/Tauri.")
