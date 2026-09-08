#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export OLLAMA_HOST=127.0.0.1:11434
if [ -d "models/ollama" ]; then export OLLAMA_MODELS="$PWD/models/ollama"; fi
exec ollama serve
