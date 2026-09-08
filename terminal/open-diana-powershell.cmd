@echo off
setlocal
set "DIANA_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%DIANA_POWERSHELL%" set "DIANA_POWERSHELL=powershell.exe"
start "" "%DIANA_POWERSHELL%" -NoLogo -NoProfile -NoExit -Command "diana"
exit /b 0
