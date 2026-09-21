@echo off
cd /d "%~dp0"
start "Arseniy server" /min python web_app.py
timeout /t 2 /nobreak > nul
start "Arseniy" http://127.0.0.1:8765
