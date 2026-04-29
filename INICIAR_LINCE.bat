@echo off
title Lince - Asistente Virtual UAdeO
color 1F
echo.
echo  ============================================
echo   LINCE - Asistente Virtual UAdeO
echo  ============================================
echo.

cd /d "%~dp0"

echo  Iniciando servidor...
start "" /B .venv\Scripts\python.exe app.py

echo  Esperando que arranque...
timeout /t 2 /nobreak >nul

echo  Abriendo navegador...
start "" "http://localhost:5000"

echo.
echo  Lince esta corriendo en http://localhost:5000
echo  Cierra esta ventana para DETENER el servidor.
echo.
pause
taskkill /F /IM python.exe >nul 2>&1
