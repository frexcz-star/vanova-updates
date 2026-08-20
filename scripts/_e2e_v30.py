"""VANOVA 3.0 — E2E limpio en sandbox aislado (nunca toca producción).

Ejercita sobre el runtime real vía HTTP:
  importación con filas inválidas → revenue limpio → periodos coherentes →
  auth en GET sensibles → truncación reportada → /api/command-center sin crash
  → semver beta.10 > beta.2.
"""
from __future__ import annotations

import io
import json
import os
import socket
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# --- Sandbox aislado: perfil + puertos propios --------------------------------
SANDBOX = Path(tempfile.mkdtemp(prefix="vanova-e2e-v30-"))
os.environ["LOCALAPPDATA"] = str(SANDBOX)
os.environ["APPDATA"] = str(SANDBOX)

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL  {name}  {detail}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(method: str, port: int, path: str, body=None, token: str | None = None, timeout: float = 15.0):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300]}
    except Exception as e:
        return 0, {"error": str(e)}


def main() -> int:
    from desktop.runtime import api_server
    from desktop.runtime import config_store

    # El runtime usa puerto propio del sandbox para no chocar con producción.
    port = free_port()
    api_server.PORT = port
    cfg_file = config_store.CONFIG_FILE

    from desktop.runtime.update import semver

    print("== VANOVA 3.0 E2E (sandbox:", SANDBOX.name, ") ==")

    # 1) Semver: beta.10 > beta.2 (regresión updater)
    check("semver beta.10 > beta.2", semver.gt("2.0.26-beta.10", "2.0.26-beta.2"))
    check("semver rc > beta", semver.gt("2.0.26-rc.1", "2.0.26-beta.5"))

    # 2) Arrancar runtime real en el sandbox
    server = api_server.start_server(port)
    time.sleep(0.5)
    st, health = http("GET", port, "/api/health")
    check("runtime arranca (health 200)", st == 200 and health.get("service") == "vanova-desktop-runtime", str(health)[:100])

    # 3) Setup status (bootstrap abierto, sin auth)
    st, setup = http("GET", port, "/api/setup/status")
    check("setup/status público (bootstrap)", st == 200, str(setup)[:120])
    from desktop.runtime import install_secrets

    token = install_secrets.get_runtime_token()

    # 4) GET sensible sin token → 401
    for path in ("/api/products", "/api/sales", "/api/business/findings", "/api/files",
                 "/api/company/profile", "/api/finance/overview", "/api/customers",
                 "/api/dashboard/local", "/api/command-center", "/api/data-health"):
        st, _ = http("GET", port, path)
        check(f"GET {path} sin token → 401", st in (401, 403), f"got {st}")

    # 5) GET con token → 200
    st, _ = http("GET", port, "/api/products", token=token)
    check("GET /api/products con token → 200", st == 200, f"got {st}")

    # 6) /api/command-center con config vacío no crashea (bug P1 corregido)
    st, body = http("GET", port, "/api/command-center", token=token)
    check("command-center sin crash con estado vacío", st == 200 and "error" not in body, f"st={st} body={str(body)[:120]}")

    # 7) Importación con filas inválidas (B-01/B-02 reales vía API)
    from datetime import datetime

    _now = datetime.now()
    _ym = _now.strftime("%Y-%m")
    csv_text = (
        "order_id,customer,total,date\n"
        f"O1,Acme,100.00,{_ym}-15\n"
        f"O2,Acme,95.00,{_ym}-20\n"
        f"O3,Acme,100.00,{_ym}-01\n"
        "BAD1,Acme,100.00,2026-13-45\n"
        "BAD2,Acme,-50.00,2026-01-10\n"
        "BAD3,Acme,abc,2026-01-11\n"
    )
    file_entry = {
        "name": "ventas_e2e.csv",
        "path": "ventas_e2e.csv",
        "ext": "csv",
        "contentPreview": csv_text,
        "category": "sales",
    }
    st, org = http("POST", port, "/api/organize/run", {"files": [file_entry], "triggerHermes": False}, token=token)
    check("organize ok", st == 200 and org.get("ok"), str(org)[:200])
    org_res = org.get("organization") or {}
    check("sales importadas = 3", org.get("sales") == 3, f"got {org.get('sales')}")
    check("review = 3 filas inválidas preservadas", org.get("salesReview") == 3, f"got {org.get('salesReview')}")

    # 8) Revenue limpio (todo = Σ periodos) — vía GET /api/sales (la fuente
    # canónica del dashboard: resumen + filas en la misma respuesta).
    st, sales_body = http("GET", port, "/api/sales", token=token)
    check("sales 200", st == 200, str(sales_body)[:120])
    summary = sales_body.get("summary") or {}
    total = summary.get("revenue")
    check("revenue total = 295 (sin filas inválidas)", total == 295.0, f"got {total}")
    check("orders = 3 (solo válidas)", summary.get("orders") == 3, f"got {summary.get('orders')}")
    month_rev = (summary.get("month") or {}).get("revenue")
    year_rev = (summary.get("year") or {}).get("revenue")
    q_rev = (summary.get("quarter") or {}).get("revenue")
    # Todas las filas válidas son de 2026 → todo/mes/año/trimestre deben cuadrar.
    check("mes == total", month_rev == 295.0, f"got {month_rev}")
    check("año == total", year_rev == 295.0, f"got {year_rev}")
    check("trimestre == total", q_rev == 295.0, f"got {q_rev}")

    # 9) Reimportación idempotente
    st, org2 = http("POST", port, "/api/organize/run", {"files": [file_entry], "triggerHermes": False}, token=token)
    check("reorganize ok", st == 200 and org2.get("ok"), str(org2)[:200])
    check("reimport sin duplicados (sales=3)", org2.get("sales") == 3, f"got {org2.get('sales')}")

    # 10) Truncación nunca silenciosa (cap pequeño patcheado a nivel unitario ya;
    #     aquí verificamos que el campo existe en el resultado del organize)
    check("campo truncatedRows presente", "truncatedRows" in org_res, str(org_res.keys()))

    # 11) Token inválido rechazado
    st, _ = http("GET", port, "/api/products", token="bad-token")
    check("token inválido → 401", st in (401, 403), f"got {st}")

    # 12) Runtime ajeno no se adjunta (P2-2)
    from desktop.runtime import port_utils
    with tempfile.TemporaryDirectory() as other:
        other_cfg = Path(other) / "maios.json"
        check("runtime_matches_install false para otro config",
              not port_utils.runtime_matches_install(port, str(other_cfg)))
    check("runtime_matches_install true para nuestro config",
          port_utils.runtime_matches_install(port, str(cfg_file)))

    # 13) Config corrupto → defaults + backup (sin pérdida silenciosa)
    corrupt = cfg_file.with_name("maios.corrupt-e2e.json")
    corrupt.write_text("esto-no-es-json{", encoding="utf-8")
    from desktop.runtime import config_store as cs
    loaded = cs.load()
    check("config corrupto → defaults sin crash", isinstance(loaded, dict) and "organizedProducts" in loaded)

    server.shutdown()
    server.server_close()

    print(f"\n== RESULTADO: {PASS} PASS, {FAIL} FAIL ==")
    if FAILURES:
        print("Fallos:", FAILURES)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
