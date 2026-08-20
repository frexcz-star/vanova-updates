"""E2E limpio de los fixes B-01/B-02/P2-1/P2-2 en perfil aislado.

INSTALL LIMPIA -> SETUP -> IMPORTACIÓN (válidas+inválidas) -> DASHBOARD ->
DATA HEALTH -> REVENUE -> REIMPORTACIÓN -> AUTH -> CONFLICTO DE INSTANCIA.

El perfil se aísla con LOCALAPPDATA propio (nunca toca producción).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

SANDBOX = Path(tempfile.mkdtemp(prefix="vanova-e2e-fixes-"))
os.environ["LOCALAPPDATA"] = str(SANDBOX)
os.environ["APPDATA"] = str(SANDBOX)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.runtime import config_store, install_secrets  # noqa: E402
from desktop.runtime.api_server import Handler, RuntimeHTTPServer, start_server  # noqa: E402
from desktop.runtime import port_utils  # noqa: E402

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}  {detail}")


def req(port: int, method: str, path: str, body: dict | None = None, token: str | None = None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"error": raw}


def main() -> int:
    # ---- setup limpio ----
    secrets = install_secrets.ensure_install_secrets()
    token = secrets["runtimeToken"]
    print("[1] INSTALL LIMPIA (perfil aislado)")
    st = config_store.is_setup_complete()
    check("setupComplete inicial = False", st is False)

    print("[2] PRIMER ARRANQUE del runtime en puerto libre")
    server = start_server(0)  # puerto efímero
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    status, payload = req(port, "GET", "/api/setup/status")
    check("setup/status 200", status == 200)
    check("configPath en sandbox", str(payload.get("configPath", "")).startswith(str(SANDBOX)),
          f"configPath={payload.get('configPath')}")

    # ---- importación: 3 válidas (295) + 2 inválidas ----
    print("[3] IMPORTACIÓN (3 válidas + 2 inválidas)")
    sales_csv = SANDBOX / "ventas.csv"
    sales_csv.write_text(
        "order_id,customer,total,date\n"
        "O1,Acme,100,2026-01-15\n"
        "O2,Acme,95,2026-01-20\n"
        "O3,Acme,100,2026-02-01\n"
        "BAD1,Acme,100,2026-13-45\n"
        "BAD2,Acme,-100,2026-01-10\n",
        encoding="utf-8",
    )
    status, r = req(port, "POST", "/api/files/add", {"name": sales_csv.name, "path": str(sales_csv), "ext": "csv"}, token=token)
    check("files/add 200", status == 200, f"status={status} body={r}")

    status, r = req(port, "POST", "/api/organize/run", {}, token=token)
    check("organize/run 200", status == 200, f"status={status} body={r}")
    org = (r.get("organization") or r) if isinstance(r, dict) else {}
    check("sales válidas = 3", r.get("sales") == 3, f"sales={r.get('sales')}")
    check("salesReview = 2", r.get("salesReview") == 2, f"review={r.get('salesReview')}")

    print("[4] DASHBOARD / REVENUE (las inválidas NO contaminan)")
    status, sales = req(port, "GET", "/api/sales", token=token)
    check("GET /api/sales 200 con token", status == 200)
    check("revenue total = 295.0", abs((sales.get("summary") or {}).get("revenue", -1) - 295.0) < 0.01,
          f"revenue={sales.get('summary', {}).get('revenue')}")
    period_sum = round(sum(m["revenue"] for m in (sales.get("summary") or {}).get("byMonth", [])), 2)
    check("total == Σ periodos", abs(period_sum - 295.0) < 0.01, f"periodos={period_sum}")

    print("[5] DATA HEALTH (filas en revisión visibles)")
    status, dh = req(port, "GET", "/api/data-health", token=token)
    check("data-health 200", status == 200, f"status={status}")
    check("needsReviewCount >= 2", dh.get("needsReviewCount", 0) >= 2, f"needsReview={dh.get('needsReviewCount')}")

    print("[6] REIMPORTACIÓN idempotente")
    status, r = req(port, "POST", "/api/files/add", {"name": sales_csv.name, "path": str(sales_csv), "ext": "csv"}, token=token)
    status, r = req(port, "POST", "/api/organize/run", {}, token=token)
    status, sales = req(port, "GET", "/api/sales", token=token)
    check("reimport no duplica: sales = 3", (sales.get("summary") or {}).get("orders") == 3,
          f"orders={sales.get('summary', {}).get('orders')}")
    data = config_store.load()
    check("review no duplica: 2", len(data.get("organizedSalesReview") or []) == 2,
          f"review={len(data.get('organizedSalesReview') or [])}")

    print("[7] AUTH en GET sensibles (P2-1)")
    for path in ("/api/products", "/api/sales", "/api/business/findings", "/api/files", "/api/company/profile", "/api/finance/overview"):
        status, _ = req(port, "GET", path)
        check(f"GET {path} sin token -> 401", status == 401, f"status={status}")
        status, _ = req(port, "GET", path, token="token-invalido")
        check(f"GET {path} token inválido -> 401", status == 401, f"status={status}")
        status, _ = req(port, "GET", path, token=token)
        check(f"GET {path} token válido -> 200", status == 200, f"status={status}")
    status, _ = req(port, "GET", "/api/health")
    check("GET /api/health abierto -> 200", status == 200)

    print("[8] CONFLICTO DE INSTANCIA (P2-2)")
    # Otro perfil con runtime sano: un segundo start_server en el mismo puerto debe
    # rechazar el attach porque el configPath pertenece a otra instalación.
    other_sandbox = Path(tempfile.mkdtemp(prefix="vanova-e2e-other-"))
    other_config = other_sandbox / "VANOVA" / "config" / "maios.json"
    with tempfile.TemporaryDirectory() as tmp:
        pass
    foreign = str(other_sandbox / "config" / "maios.json")
    with tempfile.TemporaryDirectory() as _:
        pass
    try:
        from desktop.runtime.api_server import _ExistingRuntimeServer

        with __import__("unittest.mock").mock.patch.object(port_utils, "ensure_runtime_port",
                                                           return_value={"ok": True, "port": port, "action": "already_running"}), \
             __import__("unittest.mock").mock.patch.object(port_utils, "runtime_config_path", return_value=foreign):
            start_server(port)
        check("segunda instalación (otro config) rechazada", False, "no lanzó RuntimeError")
    except RuntimeError as exc:
        check("segunda instalación (otro config) rechazada", "otra instalación" in str(exc), str(exc))

    print("[9] CERRAR")
    server.shutdown()
    server.server_close()

    print(f"\nE2E RESULTADO: {PASS} PASS, {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
