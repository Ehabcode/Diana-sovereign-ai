@echo off
setlocal
cd /d "%~dp0"
if not defined DIANA_MODEL set DIANA_MODEL=qwen2.5-coder:7b
if not defined DIANA_MEMORY_DIR set DIANA_MEMORY_DIR=%CD%\memory
if not defined DIANA_EXECUTION_LOG set DIANA_EXECUTION_LOG=%CD%\logs\diana_execution_log.txt
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe terminal\diana_coding.py %*
) else (
  py terminal\diana_coding.py %*
)
exit /b %ERRORLEVEL%
