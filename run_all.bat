@echo off
REM =========================================================
REM MAIOS — Instalador + Arranque completo (Cloud + Connector)
REM ==========================================================
echo ==========================================================
echo  MAIOS — Instalador + Arranque (modo LOCAL)
echo ==========================================================

REM ==== 1. Verificar Python ==================================================
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python no encontrado en el PATH.
    echo Instala Python 3.11+ desde https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

REM ==== 2. Crear entorno virtual si no existe ==========================
if not exist ".venv" (
    echo [1/6] Creando entorno virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
) else (
    echo [1/6] Entorno virtual ya existe.
)

REM ==== 3. Activar entorno virtual (usando python directamente) ====
REM No usamos 'activate' sino que llamamos al python del venv directamente.

REM ==== 3. Instalar dependencias del Cloud ==========================
echo [2/5] Instalando dependencias del Cloud...
python -m pip install --upgrade pip
python -m pip install -r cloud\requirements.txt

REM ==== 3. Instalar dependencias del Connector =================
echo [3/5] Instalando dependencias del Connector...
python -m pip install -r connector\requirements.txt

REM ==== 5. Ejecutar instalador del Connector (crea .env) =========
echo [5/5] Ejecutando instalador del Connector...
python connector\install_connector.py

REM ==== 6. Verificar que todo compila ==========================
echo [6/5] Verificando que todo compila...
python -m py_compile cloud\main.py connector\connector.py shared\contracts.py shared\mock_data.py

REM ==== 6. Lanzar los procesos ==============================
echo [6/5] Arrancando Connector y Cloud...
start "Connector" cmd /c ".venv\Scripts\python.exe connector\connector.py"
start "Cloud" cmd /k ".venv\Scripts\python.exe -m uvicorn cloud.main:app --host 127.0.0.1 --port 8000"

echo.
echo ============================================
echo  MAIOS está corriendo:
echo   - Dashboard: http://127.0.0.1:8000
echo   - Login: ceo / mooving2026
echo   - Conector: en segundo plano (ver logs en consola)
echo ============================================
echo.
echo Instalación completada. Usa start_all.bat para volver a lanzar.
pause