@echo off
REM MAIOS Connector — arranque en Windows
REM Doble clic para arrancar el Connector en el PC del dueño.
cd /d "%~dp0"
echo ============================================
echo  MAIOS Connector - MOOVING PAPER
echo ============================================
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No se encuentra el entorno virtual.
    echo Ejecuta primero: python install_connector.py
    pause
    exit /b 1
)
echo Arrancando Connector...
.venv\Scripts\python.exe connector.py
pause
