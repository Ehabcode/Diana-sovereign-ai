#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v ollama >/dev/null || { echo 'ollama is not in PATH'; exit 1; }
ollama create diana-texty -f ollama/Modelfile.texty
ollama create diana-coding -f ollama/Modelfile.coding
ollama list
