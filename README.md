# Diana

> **The zero-cloud, hardware-native AI studio and autonomous terminal agent.**  
> Built for engineers who want local models, zero telemetry, and real OS-level agency without paying a monthly API ransom.

[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![Local First](https://img.shields.io/badge/Privacy-100%25%20Air--Gapped-blue.svg)](#privacy--security-boundary)
[![Engine](https://img.shields.io/badge/Ollama-Native-orange.svg)](#architecture)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-purple.svg)](#quickstart)

---

## Why Diana?

Most AI desktop assistants are just Electron wrappers around cloud APIs. Your keystrokes leave your machine, your code hits remote servers, and you are one billing spike away from a dead workspace.

**Diana is built on a different philosophy: your silicon, your rules.**

It combines a retro-futuristic, peak-liquid-glass desktop interface with an air-gapped terminal runtime. It talks to local Ollama instances, synthesizes local voice clones on-demand, executes code in controlled local workspaces, and can interact with real hardware (Android debugging, removable storage, local network introspection).

```
   ┌────────────────────────────────────────────────────────┐
   │                  DIANA DESKTOP CORE                    │
   │  Liquid-Glass UI  •  Monaco Code Studio  •  CRT HUD    │
   └───────────────────────────┬────────────────────────────┘
                               │ Local IPC (127.0.0.1)
   ┌───────────────────────────┴────────────────────────────┐
   │                 LOCAL RUNTIME ENGINE                   │
   │  Multi-Persona Agents  •  Memory Vault  •  File Studio │
   └───────────────┬────────────────────────┬───────────────┘
                   │                        │
       ┌───────────┴──────────┐   ┌─────────┴────────────┐
       │     Ollama LLM       │   │   Local XTTS Engine  │
       │ (Qwen / DeepSeek / …)│   │  (On-Demand Pipeline)│
       └──────────────────────┘   └──────────────────────┘
```

---

## Key Capabilities

### 1. Retro-Futuristic Peak-Liquid-Glass Studio
- Hand-crafted desktop UI featuring CRT scanlines, hardware telemetry meters, and collapsible workspace panes.
- Embedded Monaco code editor with diff viewing and instant patch application.
- Live VRAM/RAM resource pulse: models load on demand and can unload automatically after generation.

### 2. Autonomous Terminal Agent
- Local workspace boundary protection: tools only touch your designated project root.
- User-in-the-loop confirmation for shell execution and destructive operations.
- Hardware introspection: safe Android ADB diagnostics, USB inventory, and local network adapter inspection.

### 3. Isolated Multi-Persona Intelligence
- Instant persona-switching (Hasty for rapid feedback, Clearly for deep technical planning and code reviews).
- Encrypted local private sessions powered by OS-native credential storage (`safeStorage`).
- Zero telemetry. No trackers. No analytics calls.

---

## Prerequisites

- **Python 3.10+** (tested on Python 3.11)
- **Node.js 18+** & **npm**
- **[Ollama](https://ollama.com/)** installed and running locally

---

## Quickstart

### 1. Clone & Set Up Dependencies
```bash
git clone https://github.com/<your-username>/diana.git
cd diana

# Install Node dependencies
npm install

# Set up Python virtual environment
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux:
source .venv/bin/activate

pip install -r python/requirements-offline.txt
```

### 2. Pull Recommended Local Models
```bash
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:7b
```

### 3. Launch the Studio
```bash
npm start
```

---

## Privacy & Security Boundary

- **Localhost Only**: All internal HTTP and IPC channels bind strictly to `127.0.0.1`.
- **Pass Key Protection**: Private workspaces require your personal passkey set in `renderer/passkey.config.js` (gitignored).
- **Workspace Confinement**: File mutations and command runners restrict execution scope to your `/cwd` project path.

---

## Project Structure

```
Diana/
├── app/          # Electron main lifecycle & secure IPC bridge
├── renderer/     # Liquid-glass UI, Monaco editor & terminal view
├── python/       # Flask local backend & agent orchestrator
├── terminal/     # Standalone CLI agent & hardware tools
├── ollama/       # Local Modelfiles & quantization templates
└── tests/        # Security, safety, and integration test suite
```

---

## Author & Credits

Designed and engineered independently by **[Ehab.R](AUTHORS.md)**.

## License

Released under the [MIT License](LICENSE).
