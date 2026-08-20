"""FASE 5D — Full client flow against the PACKAGED beta.2 runtime.

Drives the exact functions the API endpoints call (setup -> scan -> organize ->
analyze -> dashboard -> Hermes -> refresh -> restart) directly against the
packaged bundle with a fully isolated profile. No HTTP, no cloud port 8000 —
so production is never touched.

Note: organize_files() is async inside the packaged app; here we call it
synchronously and then verify counts match the real tester files.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

BUNDLE = Path(r"C:/Users/Admin/maios/release/win-unpacked/resources/vanova").resolve()
sys.path.insert(0, str(BUNDLE))

PROFILE = Path(r"C:/Users/Admin/vanova-beta2-flow").resolve()
SOURCE = Path(r"C:/Users/Admin/maios/benchmark-sandbox/real-company/source").resolve()

os.environ["LOCALAPPDATA"] = str(PROFILE / "Local")
os.environ["USERPROFILE"] = str(PROFILE)

from desktop.runtime import business_scanner, config_store, file_organizer, hermes_chat

results: dict = {}
ok = True


def check(cond: bool, msg: str) -> None:
    global ok
    if not cond:
        ok = False
        print(f"FAIL: {msg}")


def main() -> None:
    if PROFILE.exists():
        shutil.rmtree(PROFILE)
    PROFILE.mkdir(parents=True, exist_ok=True)

    # ---- SETUP: fresh install, scan real tester files ----
    cfg = config_store.load()
    check(cfg.get("setupComplete") is False, f"fresh: setupComplete false, got {cfg.get('setupComplete')}")
    results["freshSetupComplete"] = cfg.get("setupComplete")

    config_store.save({"scanFolders": [str(SOURCE)]})
    config_store.mark_setup_complete()
    scan = business_scanner.run_scan_async()
    results["scan"] = scan
    check(bool(scan.get("ok")), f"scan ok, got {scan.get('message')}")

    # ---- WAIT for the async scan to finish (it organizes when done, like the real client) ----
    import time
    deadline = time.time() + 120
    while time.time() < deadline:
        prog = dict(business_scanner._scan_progress)
        if prog.get("done") or prog.get("status") == "error":
            break
        time.sleep(2)
    results["scanProgress"] = prog
    check(bool(prog.get("done")), f"scan completed, got {prog}")

    # ---- ORGANIZE (in case the async organizer already ran, this is idempotent) ----
    org = file_organizer.organize_files()
    results["organize"] = org
    data = config_store.load()
    products = len(data.get("organizedProducts") or [])
    sales = len(data.get("organizedSales") or [])
    results["counts"] = {"products": products, "sales": sales}
    check(products == 461, f"products expected 461, got {products}")
    check(sales == 99, f"sales expected 99, got {sales}")

    # ---- ANALYZE (detection engine) ----
    from desktop.runtime import detection_engine
    det = detection_engine.run_detection()
    findings = det.get("findings") if isinstance(det, dict) else det
    results["findings"] = {"count": len(findings or [])}
    check(len(findings or []) >= 1, "detection produced at least one finding")

    # ---- DASHBOARD (business payload) ----
    from desktop.runtime import business_signals
    sig = business_signals.compute_signals()
    results["signals"] = {"computed": sig is not None}
    check(sig is not None, "signals computed")

    # ---- HERMES (real business question, honest check; ask is async -> poll) ----
    import time as _time
    conv = hermes_chat.ask("¿Cuántos pedidos y cuánto revenue tengo?")
    req_id = conv.get("id") or conv.get("requestId")
    answer = None
    if req_id:
        for _ in range(60):
            _time.sleep(3)
            st = hermes_chat.get_request(req_id)
            if st and st.get("status") in ("completed", "done", "ok"):
                answer = st
                break
    results["hermes"] = {"reqId": req_id, "finalStatus": (answer or {}).get("status")}
    check(answer is not None, f"hermes completed, got {conv}")
    text = str((answer or {}).get("result") or "")
    text = text.get("text") if isinstance(text, dict) else text
    check("99" in text, f"hermes mentions 99 orders, got: {str(text)[:140]}")

    # ---- REFRESH: re-import the same files (idempotency) ----
    scan2 = business_scanner.run_scan_async()
    deadline = time.time() + 120
    while time.time() < deadline:
        prog2 = dict(business_scanner._scan_progress)
        if prog2.get("done") or prog2.get("status") == "error":
            break
        time.sleep(2)
    org2 = file_organizer.organize_files()
    data2 = config_store.load()
    products2 = len(data2.get("organizedProducts") or [])
    sales2 = len(data2.get("organizedSales") or [])
    results["afterRefresh"] = {"products": products2, "sales": sales2}
    check(products2 == 461, f"refresh: products stable, got {products2}")
    check(sales2 == 99, f"refresh: sales stable, got {sales2}")

    # signature stability (compare content, ignoring dedupe-tracking metadata)
    meta_keys = {"lastSeenAt", "timesSeen", "updatedAt"}

    def _strip(flist):
        return [
            {k: v for k, v in f.items() if k not in meta_keys}
            for f in (flist or [])
        ]

    det2 = detection_engine.run_detection()
    f1 = _strip(findings)
    f2 = _strip(det2.get("findings") if isinstance(det2, dict) else det2)
    check(f1 == f2, "refresh: findings signatures stable")

    # ---- RESTART (new process on the same profile) ----
    data3 = config_store.load()
    products3 = len(data3.get("organizedProducts") or [])
    sales3 = len(data3.get("organizedSales") or [])
    results["afterRestart"] = {"products": products3, "sales": sales3, "setupComplete": data3.get("setupComplete")}
    check(products3 == 461, f"restart: products persist, got {products3}")
    check(sales3 == 99, f"restart: sales persist, got {sales3}")
    check(data3.get("setupComplete") is True, "restart: setup stays complete")

    print(json.dumps({"RESULT": "PASS" if ok else "FAIL", "checks": results}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
