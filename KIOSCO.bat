@echo off
title Lince Interactivo - UAdeO
cd /d "%~dp0"

:inicio
echo Iniciando Lince Interactivo...
python lince_app.py
echo El bot se cerro. Reiniciando en 3 segundos...
timeout /t 3 /nobreak >nul
goto inicio
