@echo off
cd /d "%~dp0"
set OLLAMA_HOST=127.0.0.1:11434
if exist models\ollama set OLLAMA_MODELS=%CD%\models\ollama
rem Flash attention + quantized KV cache: real speed/VRAM win for Texty
rem (qwen3:8b is on Ollama's flash-attention architecture allowlist), and a
rem harmless no-op for Diana Coding (qwen2.5-coder:7b, qwen2 architecture,
rem isn't on that allowlist - silently keeps running exactly as before).
rem KV_CACHE_TYPE alone does nothing without FLASH_ATTENTION also set.
set OLLAMA_FLASH_ATTENTION=1
set OLLAMA_KV_CACHE_TYPE=q8_0
ollama serve
