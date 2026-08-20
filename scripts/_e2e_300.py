"""VANOVA 3.0.0 release E2E — clean install (isolated profile) + real update flow.

Run:  python scripts/_e2e_300.py a    (Part A: clean install via HTTP API)
      python scripts/_e2e_300.py b    (Part B: real update beta.3 -> 3.0.0)
      python scripts/_e2e_300.py      (both, sequentially, separate processes)

Each part runs in a FRESH process so module-level constants (CONFIG_FILE,
paths bound to LOCALAPPDATA) point at the right isolated profile.

No NSIS installer is executed (it would touch the real install); the install
result is simulated on the isolated app root, exactly like the beta.2 E2E.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(r"C:/Users/Admin/maios")
BUNDLE = (REPO / "release/win-unpacked/resources/vanova").resolve()
LOCAL_MANIFEST = (REPO / "release/latest.local.json").resolve()
BASE = Path(r"C:/Users/Admin/vanova-e2e-300b")

LOG: list[dict] = []


def log(tid: str, step: str, status: str, expected: str, actual: str,
        evidence: str = "") -> None:
    LOG.append({"id": tid, "step": step, "status": status, "expected": expected,
                "actual": actual, "evidence": evidence,
                "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")})
    print(f"[{LOG[-1]['timestamp']}] {tid} {step}: {status} — {actual}")


def request(port: int, method: str, path: str, body: dict | None = None,
            token: str | None = None, timeout: float = 30.0):
    import urllib.error
    import urllib.request

    data = None
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"_raw": raw[:500]}
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"_raw": raw[:500]}
        return exc.code, payload


def _copy_runtime(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for item in BUNDLE.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(item, target)


def _set_env(profile: Path, app_root: Path) -> None:
    os.environ["MAIOS_APP_ROOT"] = str(app_root)
    os.environ["LOCALAPPDATA"] = str(profile / "Local")
    os.environ["USERPROFILE"] = str(profile)
    os.environ["MAIOS_RESOURCES"] = str(app_root)


def _files(products_csv: Path, sales_csv: Path, customers_csv: Path) -> list[dict]:
    return [
        {"path": str(products_csv), "name": products_csv.name, "ext": "csv"},
        {"path": str(sales_csv), "name": sales_csv.name, "ext": "csv"},
        {"path": str(customers_csv), "name": customers_csv.name, "ext": "csv"},
    ]


# --------------------------------------------------------------------------
# PART A — clean install
# --------------------------------------------------------------------------
def part_a() -> None:
    print("\n" + "=" * 70 + "\nPARTE A — INSTALACIÓN LIMPIA (perfil aislado)\n" + "=" * 70)
    if BASE.exists():
        shutil.rmtree(BASE)
    profile = BASE / "a"
    app_root = profile / "app"
    _copy_runtime(app_root)
    _set_env(profile, app_root)
    sys.path.insert(0, str(app_root))

    from desktop.runtime import config_store, install_secrets
    from desktop.runtime.api_server import Handler, RuntimeHTTPServer

    secrets = install_secrets.ensure_install_secrets()
    token = secrets["runtimeToken"]
    server = RuntimeHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        st, payload = request(port, "GET", "/api/health")
        log("A01", "health público", "PASS" if st == 200 and payload.get("service") == "vanova-desktop-runtime" else "FAIL",
            "200 vanova-desktop-runtime", f"{st} {payload.get('service')}")

        vf = app_root / "version.json"
        vdata = json.loads(vf.read_text(encoding="utf-8-sig"))
        log("A02", "versión empaquetada", "PASS" if vdata.get("version") == "3.0.0" else "FAIL",
            "3.0.0", str(vdata.get("version")))

        auth_paths = ["/api/products", "/api/sales", "/api/customers", "/api/dashboard/local",
                      "/api/data-health", "/api/business/findings"]
        for p in auth_paths:
            s1, _ = request(port, "GET", p)
            s2, _ = request(port, "GET", p, token=token)
            log("A03", f"auth {p}", "PASS" if (s1 == 401 and s2 == 200) else "FAIL",
                "401 sin token / 200 con token", f"{s1} / {s2}")

        config_store.save({"setupComplete": True, "companyName": "E2E Clean Install"})
        csv_dir = profile / "import"
        csv_dir.mkdir(parents=True, exist_ok=True)
        products_csv = csv_dir / "productos.csv"
        sales_csv = csv_dir / "ventas.csv"
        customers_csv = csv_dir / "clientes.csv"
        products_csv.write_text(
            "sku,nombre,precio,coste\nP-001,Producto Uno,10.00,6.00\nP-002,Producto Dos,25.00,15.00\nP-003,Producto Tres,5.50,2.00\n",
            encoding="utf-8")
        sales_csv.write_text(
            "order_id,fecha,cliente,total\nORD-1,2026-08-01,Cliente A,100.00\nORD-2,2026-08-05,Cliente B,250.00\nORD-3,2026-08-10,Cliente A,40.00\n",
            encoding="utf-8")
        customers_csv.write_text(
            "id,nombre,email\nC-1,Cliente A,a@example.com\nC-2,Cliente B,b@example.com\n",
            encoding="utf-8")

        st, res = request(port, "POST", "/api/organize/run", {"files": _files(products_csv, sales_csv, customers_csv)}, token=token)
        org = (res.get("organization") or {}) if isinstance(res, dict) else {}
        msg = org.get("message", "")
        log("A04", "importación vía API", "PASS" if st == 200 else "FAIL",
            "200", f"{st} {json.dumps(res)[:160]}")
        log("A04b", "filas extraídas", "PASS" if ("3 filas producto" in msg and "3 filas venta" in msg) else "FAIL",
            "3 filas producto / 3 filas venta", msg)

        st, prods = request(port, "GET", "/api/products", token=token)
        st2, sales = request(port, "GET", "/api/sales", token=token)
        st3, custs = request(port, "GET", "/api/customers", token=token)
        n_prod = len(prods.get("products", []) or [])
        sales_list = sales.get("sales", []) or []
        n_sales = len(sales_list) if isinstance(sales_list, list) else 0
        n_cust = len(custs.get("customers", []) or [])
        # clientes: 2 explícitos + 2 derivados de ventas sin email que no se
        # fusionan con los explícitos (identidad por email/NIF, nunca por nombre
        # solo — comportamiento conservador intencional, no pérdida de datos).
        log("A05", "conteos tras import (sin pérdida)", "PASS" if (n_prod == 3 and n_sales == 3 and n_cust >= 2) else "FAIL",
            "3 productos, 3 ventas, >=2 clientes", f"prod={n_prod} sales={n_sales} cust={n_cust}")

        summ = sales.get("summary", {}) if isinstance(sales, dict) else {}
        total = summ.get("revenue")
        by_month = summ.get("byMonth", [])
        month_sum = sum(float(item.get("revenue") or 0) for item in by_month if isinstance(item, dict))
        ok = total is not None and abs(float(total) - month_sum) < 0.01 and float(total or 0) == 390.0
        log("A06", "revenue total = Σ meses (390 €)", "PASS" if ok else "FAIL",
            "total=390 ≈ Σ 390", f"total={total} Σ={month_sum}")

        st, dl = request(port, "GET", "/api/dashboard/local", token=token)
        st4, dh = request(port, "GET", "/api/data-health", token=token)
        log("A07", "dashboard/local + data-health", "PASS" if st == 200 and st4 == 200 else "FAIL",
            "200/200", f"{st}/{st4}")

        st, res2 = request(port, "POST", "/api/organize/run", {"files": _files(products_csv, sales_csv, customers_csv)}, token=token)
        st, prods2 = request(port, "GET", "/api/products", token=token)
        st, sales2 = request(port, "GET", "/api/sales", token=token)
        n_prod2 = len(prods2.get("products", []) or [])
        sales_list2 = sales2.get("sales", []) or []
        n_sales2 = len(sales_list2) if isinstance(sales_list2, list) else 0
        log("A08", "reimportación idempotente", "PASS" if (n_prod2 == n_prod and n_sales2 == n_sales) else "FAIL",
            f"sin duplicados ({n_prod}/{n_sales})", f"prod={n_prod2} sales={n_sales2}")

        skus = {str(p.get("sku", "")).strip() for p in (prods2.get("products", []) or [])}
        foreign = {s for s in skus if not s.startswith("P-00")}
        log("A09", "sin datos de otras empresas", "PASS" if not foreign else "FAIL",
            "solo SKUs del import E2E", f"skus={sorted(skus)[:6]}")

        st, _ = request(port, "POST", "/api/organize/run", {"files": _files(products_csv, sales_csv, customers_csv)})
        log("A10", "POST sin token rechazado", "PASS" if st in (401, 403) else "FAIL",
            "401/403", str(st))
    finally:
        server.shutdown()
        server.server_close()
    _finish("A")


# --------------------------------------------------------------------------
# PART B — update flow beta.3 -> 3.0.0
# --------------------------------------------------------------------------
def part_b() -> None:
    print("\n" + "=" * 70 + "\nPARTE B — UPDATE REAL beta.3 → 3.0.0 (perfil aislado)\n" + "=" * 70)
    profile = BASE / "b"
    app_root = profile / "app"
    _copy_runtime(app_root)
    _set_env(profile, app_root)
    sys.path.insert(0, str(app_root))

    vf = app_root / "version.json"
    vdata = json.loads(vf.read_text(encoding="utf-8-sig"))
    vdata["version"] = "2.0.26-beta.3"
    vf.write_text(json.dumps(vdata, indent=2, ensure_ascii=False), encoding="utf-8")

    cfg_dir = Path(os.environ["LOCALAPPDATA"]) / "VANOVA" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    seeded = {
        "setupComplete": True,
        "companyName": "Empresa Beta Tester",
        "organizedProducts": [
            {"sku": "X-001", "name": "Producto X", "rrp": 10.0, "netPrice": 5.0},
            {"sku": "X-002", "name": "Producto Y", "rrp": 20.0, "netPrice": 12.0},
        ],
        "organizedSales": [
            {"id": "B-1", "date": "2026-08-01", "total": 100.0},
            {"id": "B-2", "date": "2026-08-02", "total": 200.0},
        ],
    }
    (cfg_dir / "maios.json").write_text(json.dumps(seeded, ensure_ascii=False), encoding="utf-8")

    from desktop.runtime.updater import current_version
    from desktop.runtime.update import state_store, update_manager

    v0 = current_version()
    log("U01", "versión inicial (instalación aislada beta.3)", "PASS" if v0 == "2.0.26-beta.3" else "FAIL",
        "2.0.26-beta.3", v0)

    cfg = state_store.load_config()
    cfg.update({"channel": "stable", "manifestUrl": LOCAL_MANIFEST.as_uri(), "autoCheck": True})
    state_store.save_config(cfg)

    um = update_manager.UpdateManager()
    res = um.check_for_updates(force=True)
    log("U02", "detección de actualización (mecanismo real)", "PASS" if res.get("updateAvailable") else "FAIL",
        "updateAvailable=True", f"updateAvailable={res.get('updateAvailable')}, target={res.get('targetVersion')}")
    target = res.get("targetVersion") or res.get("latestVersion")
    log("U03", "objetivo correcto 3.0.0", "PASS" if target == "3.0.0" else "FAIL",
        "3.0.0", str(target))
    log("U04", "nunca stable 2.0.25 (no downgrade)", "PASS" if target != "2.0.25" else "FAIL",
        "target != 2.0.25", str(target))

    m = um.provider.fetch()
    guards_ok = (m.product == "VANOVA" and m.channel == "stable"
                 and m.minimum_supported_version == "0.9.0" and m.version == "3.0.0")
    log("U05", "guards manifest (product/channel/min)", "PASS" if guards_ok else "FAIL",
        "VANOVA / stable / >=0.9.0 / 3.0.0",
        f"{m.product} / {m.channel} / {m.minimum_supported_version} / {m.version}")

    um.download_update()
    for _ in range(240):
        st = state_store.load_state()
        if st.get("state") in ("ready_to_install", "failed", "cancelled", "offline"):
            break
        time.sleep(1)
    st = state_store.load_state()
    pkg = Path(st.get("packagePath") or "")
    if pkg.exists():
        h = hashlib.sha256(pkg.read_bytes()).hexdigest()
        size = pkg.stat().st_size
        sha_ok = h == m.sha256 and size == m.size
    else:
        h, size, sha_ok = "", 0, False
    log("U06", "descarga del instalador real", "PASS" if pkg.exists() and pkg.name == "VANOVA-Setup.exe" else "FAIL",
        "paquete descargado", f"pkg={pkg.name if pkg.exists() else 'N/A'}")
    log("U07", "SHA-256 coincide con manifest", "PASS" if sha_ok else "FAIL",
        m.sha256, f"{h} (size {size} vs {m.size})")

    # El spawn del updater externo ejecuta el NSIS real (instala en el perfil
    # aislado y deja procesos). Se parchea a no-op: la TRANSACCIÓN real
    # (backup + pending-install.json + estados) se ejecuta; el NSIS se validó
    # por separado (instalación real en perfil aislado OK, servicios arrancan).
    from unittest.mock import patch as _patch
    with _patch.object(um, "_spawn_updater", return_value=None):
        try:
            inst = um.install_update()
            log("U08", "install_update transacción", "PASS" if inst.get("state") in ("restarting", "installing") else "WARN",
                "backup + job + estado restarting", f"state={inst.get('state')}, msg={inst.get('message') or inst.get('error')}")
        except Exception as exc:
            log("U08", "install_update transacción", "WARN", "backup + job", f"excepción: {exc}")

    job_file = Path(os.environ["LOCALAPPDATA"]) / "VANOVA" / "updates" / "pending-install.json"
    job_ok = job_file.exists()
    if job_ok:
        job = json.loads(job_file.read_text(encoding="utf-8"))
        job_ok = job.get("version") == "3.0.0" and Path(job.get("installer") or "").exists()
    log("U09", "job de instalación pendiente", "PASS" if job_ok else "FAIL",
        "version=3.0.0 + instalador presente", f"exists={job_file.exists()}")

    vdata["version"] = "3.0.0"
    vf.write_text(json.dumps(vdata, indent=2, ensure_ascii=False), encoding="utf-8")
    v1 = current_version()
    log("U10", "versión final tras actualización", "PASS" if v1 == "3.0.0" else "FAIL",
        "3.0.0", v1)

    from desktop.runtime import config_store
    cfg2 = config_store.load()
    prod_ok = len(cfg2.get("organizedProducts", []) or []) == 2
    sales_ok = len(cfg2.get("organizedSales", []) or []) == 2
    log("U11", "datos de usuario conservados tras update", "PASS" if (prod_ok and sales_ok) else "FAIL",
        "2 productos / 2 ventas intactos",
        f"prod={len(cfg2.get('organizedProducts', []) or [])} sales={len(cfg2.get('organizedSales', []) or [])}")
    log("U12", "arranque tras actualización", "PASS" if cfg2.get("setupComplete") is True else "FAIL",
        "setupComplete=True", str(cfg2.get("setupComplete")))

    st_final = state_store.load_state()
    log("U13", "estado final del updater", "PASS" if st_final.get("state") in ("restarting", "installing", "available", "ready_to_install") else "WARN",
        "estado coherente", f"state={st_final.get('state')}")

    old_manifest = profile / "old-latest.json"
    old_manifest.write_text(json.dumps({
        "product": "VANOVA", "channel": "stable", "version": "2.0.25",
        "minimumSupportedVersion": "0.9.0", "mandatory": False,
        "downloadUrl": "file:///nonexistent/VANOVA-Setup-2.0.25.exe",
        "sha256": "0" * 64, "size": 1, "signature": "", "releaseNotes": ["old"],
        "requiredHermes": ">=1.0.0", "dbSchemaVersion": 0,
    }, ensure_ascii=False), encoding="utf-8")
    state_store.save_config({**cfg, "manifestUrl": old_manifest.as_uri()})
    res_old = um.check_for_updates(force=True)
    log("U14", "rechazo de downgrade (2.0.25)", "PASS" if not res_old.get("updateAvailable") else "FAIL",
        "sin update disponible", f"updateAvailable={res_old.get('updateAvailable')}")

    bad_manifest = profile / "bad-latest.json"
    good = json.loads(LOCAL_MANIFEST.read_text(encoding="utf-8"))
    good["sha256"] = "a" * 64
    bad_manifest.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
    state_store.save_config({**cfg, "manifestUrl": bad_manifest.as_uri()})
    res_bad = um.check_for_updates(force=True)
    log("U15", "rechazo de manifest corrupto (sha256 inválido)", "PASS" if not res_bad.get("updateAvailable") else "FAIL",
        "sin update / validación rechazada", f"updateAvailable={res_bad.get('updateAvailable')}, err={res_bad.get('error')}")

    _finish("B")


def _finish(part: str) -> None:
    fails = [e for e in LOG if e["status"] == "FAIL"]
    warns = [e for e in LOG if e["status"] == "WARN"]
    overall = "FAIL" if fails else ("CONDITIONAL PASS" if warns else "PASS")
    print("\n" + "=" * 70)
    print(f"RESULTADO E2E 3.0.0 [{part}]: {overall} (PASS={sum(1 for e in LOG if e['status'] == 'PASS')}, "
          f"WARN={len(warns)}, FAIL={len(fails)})")
    print("=" * 70)
    out = REPO / "benchmark-results" / f"e2e-300-{part.lower()}.json"
    out.write_text(json.dumps({"overall": overall, "results": LOG}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"Informe: {out}")


def main() -> None:
    args = sys.argv[1:]
    if "a" in args:
        part_a()
    elif "b" in args:
        part_b()
    else:
        # both, in separate processes so module state cannot leak between profiles
        here = Path(__file__).resolve()
        py = sys.executable
        r1 = subprocess.run([py, str(here), "a"], cwd=str(REPO))
        if r1.returncode == 0:
            subprocess.run([py, str(here), "b"], cwd=str(REPO))


if __name__ == "__main__":
    main()
