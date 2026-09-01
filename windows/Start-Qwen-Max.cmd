@echo off
setlocal
set "DISTRO=%~1"
if "%DISTRO%"=="" set "DISTRO=Ubuntu"
set "LAN_HELPER=%~dp0Enable-Qwen-LAN.ps1"
if "%QWEN_WSL_REPO%"=="" (
  for /f "usebackq delims=" %%I in (`wsl.exe -d "%DISTRO%" -- wslpath -a "%~dp0.."`) do set "QWEN_WSL_REPO=%%I"
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LAN_HELPER%" -Distro "%DISTRO%" -Port 1234
if errorlevel 1 (
  echo Failed to enable Private-LAN access on port 1234.
  exit /b 1
)
wsl.exe -d "%DISTRO%" -- bash -lc "cd \"$QWEN_WSL_REPO\" && bash scripts/keepalive.sh"
endlocal
