@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo       PROVEEDOR IA - CONFIGURACION
echo ==========================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configurar-local.ps1"

if errorlevel 1 (
  echo.
  echo La configuracion no pudo completarse.
  pause
  exit /b 1
)

endlocal
