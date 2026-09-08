@echo off
cd /d "%~dp0"
if defined PYTHON_BIN (set PY=%PYTHON_BIN%) else (set PY=py)
%PY% -m venv --system-site-packages .venv
call .venv\Scripts\activate.bat
if exist wheels\*.whl (
  %PY% -m pip install --no-index --find-links wheels -r python\requirements-offline.txt
) else (
  echo No local wheels found. Put compatible wheel files in wheels before running offline.
)
python prepare_offline.py
if errorlevel 1 echo Some local dependencies or Ollama models are missing.
echo Setup complete. Start Ollama separately, then run npm install --offline and npm start.
