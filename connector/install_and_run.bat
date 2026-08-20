@echo off
REM -------------------------------------------------
REM MAIOS Connector + Cloud — instalación y arranque
REM -------------------------------------------------
echo ==========================================================
echo  MAIOS Connector + Cloud — instalador y arranque (LOCAL)
echo ============================================

REM ==== 1. Verificar Python 3.11+ ==========================
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python no está en el PATH.
    echo Descarga Python 3.11+ desde https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

REM ==== 2. Crear entorno virtual ==========================
if not exist ".venv" (
    echo [1/5] Creando entorno virtual...
    python -m venv .venv
) else (
    echo [1/5] Entorno virtual ya existe.
)

REM ==== 2. Instalar dependencias del Cloud =================
echo [2/5] Instalando dependencias del Cloud...
python -m pip install --upgrade pip
python -m pip install -r cloud\requirements.txt

echo [2/5] Instalando dependencias del Connector...
python -m pip install -r connector\requirements.txt

REM ==== 5. Verificar instalación ==========================
echo [5/5] Verificando instalación...
python -c "import httpx, dotenv; print('   deps OK')"

REM ==== 6. Lanzar los procesos ============================
echo [5/5] Arrancando Connector y Cloud...
start "Connector" cmd /c ".venv\Scripts\python.exe connector\connector.py"
start "Cloud" cmd /k ".venv\Scripts\python.exe -m uvicorn cloud.main:app --host 127.0.0.1 --port 8000"

echo.
echo ============================================
echo  MAIOS está corriendo:
echo   - Conector: http://127.0.0.1:8642 (si está configurado)
echo   - Dashboard: http://127.0.0.1:8000
echo   Login: ceo / mooving2026
echo ============================================
pause