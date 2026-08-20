"""MAIOS — instalador completo (local)

Crea el entorno virtual, instala dependencias y genera los archivos .env
para el Cloud y el Connector. NO lanza los procesos (eso lo hace start_all.bat).

Uso:
    python install_all.py

Requisitos:
- Python 3.11+ en el PATH (python --version).
- Ejecutar desde la raíz del proyecto (contiene cloud/, connector/, web/).
"""
import os
import secrets
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV = BASE / ".venv"
PY = VENV / "Scripts" / "python.exe" if os.name == "nt" else VENV / "bin" / "python"


def run(cmd, cwd=None):
    print(">>", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=cwd or BASE, check=True)


def write_env(path, content):
    if not path.exists():
        path.write_text(content, encoding="utf-8")
        print(f"   [CREADO] {path}")
    else:
        print(f"   {path.name} ya existe — se mantiene.")


def main():
    print("=" * 70)
    print("MAIOS — Instalador completo (LOCAL)")
    print("=" * 70)

    # 1. Crear entorno virtual
    if not VENV.exists():
        print("\n[1/4] Creando entorno virtual .venv...")
        run(["python", "-m", "venv", str(VENV)])
    else:
        print("\n[1/4] Entorno virtual .venv ya existe.")

    # 2. Instalar dependencias
    print("[2/4] Instalando dependencias del Cloud...")
    run([str(PY), "-m", "pip", "install", "-r", "cloud/requirements.txt"])
    print("[2/4] Instalando dependencias del Connector...")
    run([str(PY), "-m", "pip", "install", "-r", "connector/requirements.txt"])

    # 3. Generar .env (solo si no existen)
    print("[3/4] Generando archivos .env...")
    # Generate a strong random admin password for this deployment (P2-27: no
    # hardcoded demo credentials as production fallback).
    admin_pass = secrets.token_urlsafe(12)
    admin_user = "ceo"

    # Cloud .env
    cloud_env_path = BASE / "cloud" / ".env"
    cloud_env = f"""# MAIOS Cloud config (local)
MAIOS_CLOUD_SECRET_KEY={secrets.token_urlsafe(48)}
MAIOS_DEMO_USER={admin_user}
MAIOS_DEMO_PASSWORD={admin_pass}
MAIOS_TOKEN_MINUTES=60
MAIOS_REFRESH_DAYS=7
MAIOS_DB=maios_cloud.db
MAIOS_AUDIT_LOG=audit.jsonl
MAIOS_ALLOWED_ORIGINS=
MAIOS_STATIC_DIR=web/dist
"""
    write_env(cloud_env_path, cloud_env)

    # Connector .env
    connector_env_path = BASE / "connector" / ".env"
    connector_env = f"""# MAIOS Connector config (local)
MAIOS_CLOUD_URL=http://127.0.0.1:8000
MAIOS_DEVICE_KEY={secrets.token_urlsafe(32)}
MAIOS_WORKSPACE_ID=
MAIOS_OWNER_TOKEN={secrets.token_urlsafe(32)}
HERMES_CLI=
HERMES_API_KEY=
MAIOS_HEARTBEAT_SECONDS=30
"""
    write_env(connector_env_path, connector_env)

    # 4. Verificar que compila
    print("[4/4] Verificando que el código compila...")
    for f in ["cloud/main.py", "connector/connector.py", "shared/contracts.py", "shared/mock_data.py"]:
        try:
            run([str(PY), "-m", "py_compile", str(BASE / f)])
        except Exception as e:
            print(f"   ✗ Error compilando {f}: {e}")

    print("\n" + "=" * 70)
    print("Instalación completada.")
    print()
    print("Siguientes pasos:")
    print("  1. Edita connector/.env y pon la ruta de hermes.exe en HERMES_CLI")
    print("  2. Arranca todo con:  start_all.bat")
    print("  3. Abre el dashboard:  http://127.0.0.1:8000")
    print(f"     Login: {admin_user} / {admin_pass}   (guárdala en un gestor de contraseñas)")
    print("=" * 70)


if __name__ == "__main__":
    main()
