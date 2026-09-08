@echo off
cd /d "%~dp0"
where ollama >nul 2>nul || (echo ollama is not in PATH & exit /b 1)
ollama create diana-texty -f ollama\Modelfile.texty
ollama create diana-coding -f ollama\Modelfile.coding
ollama list
