@echo off
REM MAIOS — arranque completo (Cloud + Connector) en el PC del dueño
REM Doble clic para arrancar todo. Cierra la ventana para detener.
cd /d "%~dp0"
echo ============================================
echo  MAIOS - MOOVING PAPER (Cloud + Connector)
echo ============================================
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No se encuentra el entorno virtual.
    echo Ejecuta primero: python install_all.py
    pause
    exit /b 1
)

echo.
echo [1/2] Arrancando MAIOS Cloud en http://127.0.0.1:8000 ...
start "MAIOS Cloud" cmd /k ".venv\Scripts\python.exe -m uvicorn cloud.main:app --host 127.0.0.1 --port 8000"

echo [2/2] Arrancando MAIOS Connector ...
start "MAIOS Connector" cmd /k ".venv\Scripts\python.exe connector\connector.py"

echo.
echo ============================================
echo  Todo arrancado.
echo  Abre el dashboard en:  http://127.0.0.1:8000
echo  Login: ceo / mooving2026
echo ============================================
pause
