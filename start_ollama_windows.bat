@echo off
cd /d "%~dp0"
set OLLAMA_HOST=127.0.0.1:11434
if exist models\ollama set OLLAMA_MODELS=%CD%\models\ollama
ollama serve
