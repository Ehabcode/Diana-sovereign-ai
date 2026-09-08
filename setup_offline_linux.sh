#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -m venv --system-site-packages .venv
source .venv/bin/activate
if compgen -G "wheels/*.whl" > /dev/null; then
  python -m pip install --no-index --find-links wheels -r python/requirements-offline.txt
else
  echo "No local wheels found. Put compatible wheel files in wheels/ before running offline."
fi
python prepare_offline.py || true
echo "Setup complete. Start Ollama separately, then run: npm install --offline && npm start"
