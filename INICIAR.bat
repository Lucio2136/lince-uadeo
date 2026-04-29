@echo off
echo Cerrando procesos anteriores...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Iniciando Lince...
start "" /B cmd /c ".venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000 > server.log 2>&1"
timeout /t 3 /nobreak >nul

echo Abriendo navegador...
start "" "http://localhost:8000"
echo.
echo Lince corriendo en http://localhost:8000
echo NO cierres esta ventana.
pause
