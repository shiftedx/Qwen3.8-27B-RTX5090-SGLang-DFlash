@echo off
setlocal
set "DISTRO=%~1"
if "%DISTRO%"=="" set "DISTRO=Ubuntu"
if "%QWEN_WSL_REPO%"=="" (
  for /f "usebackq delims=" %%I in (`wsl.exe -d "%DISTRO%" -- wslpath -a "%~dp0.."`) do set "QWEN_WSL_REPO=%%I"
)
wsl.exe -d "%DISTRO%" -- bash -lc "cd \"$QWEN_WSL_REPO\" && bash scripts/server.sh stop"
endlocal
