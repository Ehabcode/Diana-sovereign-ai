@echo off
setlocal
python "%~dp0diana_coding.py" %*
exit /b %ERRORLEVEL%
