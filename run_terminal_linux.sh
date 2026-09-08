#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export DIANA_MODEL="${DIANA_MODEL:-qwen2.5-coder:7b}"
export DIANA_MEMORY_DIR="${DIANA_MEMORY_DIR:-$PWD/memory}"
export DIANA_EXECUTION_LOG="${DIANA_EXECUTION_LOG:-$PWD/logs/diana_execution_log.txt}"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python terminal/diana_coding.py "$@"
fi
exec python3 terminal/diana_coding.py "$@"
