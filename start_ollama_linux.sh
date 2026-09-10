#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export OLLAMA_HOST=127.0.0.1:11434
if [ -d "models/ollama" ]; then export OLLAMA_MODELS="$PWD/models/ollama"; fi
# Flash attention + quantized KV cache: real speed/VRAM win for Texty
# (qwen3:8b is on Ollama's flash-attention architecture allowlist), and a
# harmless no-op for Diana Coding (qwen2.5-coder:7b, qwen2 architecture,
# isn't on that allowlist - silently keeps running exactly as before).
# KV_CACHE_TYPE alone does nothing without FLASH_ATTENTION also set.
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
exec ollama serve
