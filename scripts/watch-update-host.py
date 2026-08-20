"""Watchdog del host de updates: mantiene vivo el servidor estatico del tunel.

Comprueba cada 30s que http://127.0.0.1:8137/latest.json responde; si no,
relanza range-static-server.py. No toca cloudflared (si ese muere, la URL
cambia y los clientes perderian la ruta — hay que republicar a mano).
"""
import subprocess
import sys
import time
import urllib.request

SERVER_ARGS = [
    sys.executable,
    r"C:/Users/Admin/maios/scripts/range-static-server.py",
    r"C:/Users/Admin/maios/release",
    "8137",
]
LOG = r"C:/Users/Admin/maios-ux-audit/range_server.log"
PORT = 8137


def _alive() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/latest.json", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _log(msg: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] watchdog: {msg}\n")


proc = None
_log("watchdog arrancado")
while True:
    if not _alive():
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
        _log("servidor caido — relanzando")
        proc = subprocess.Popen(
            SERVER_ARGS,
            stdout=open(LOG, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        time.sleep(6)
    else:
        proc = None
    time.sleep(30)
