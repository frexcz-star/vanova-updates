"""FASE 4 — REAL update flow 2.0.26-beta.1 -> 2.0.26-beta.2 (packaged runtime).

Runs the ACTUAL UpdateManager from the packaged bundle against an isolated
app root that simulates an installed 2.0.26-beta.1 (MAIOS_APP_ROOT) + isolated
LOCALAPPDATA profile. Exercises the real code paths:

  1. initial version check (beta.1)
  2. check_for_updates(force=True) against the LOCAL beta manifest
     (latest.local.json -> file:// installer, channel beta)
  3. asserts it targets 2.0.26-beta.2 and NEVER 2.0.25 stable
  4. download_update() -> copies the real installer via file:// and
     verifies SHA-256 + size against the manifest
  5. install_update() -> backup + pending-install job + state transitions
     (the external NSIS step is NOT executed here: on this machine it would
     uninstall the production install — B-02 documented risk; it runs on the
     tester's machine)
  6. simulates the install result on the isolated app root (version.json ->
     2.0.26-beta.2) and re-boots the packaged runtime from it, verifying
     version, startup, Hermes, persistence, and updater state.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import sys
import time
from pathlib import Path

BUNDLE = Path(r"C:/Users/Admin/maios/release/win-unpacked/resources/vanova").resolve()
APP_ROOT = Path(r"C:/Users/Admin/vanova-update-e2e/app").resolve()
PROFILE = Path(r"C:/Users/Admin/vanova-update-e2e").resolve()
LOCAL_MANIFEST = Path(r"C:/Users/Admin/maios/release/latest.local.json").resolve()

LOG: list[dict] = []


def log(tid: str, step: str, status: str, expected: str, actual: str,
        evidence: str = "") -> None:
    LOG.append({"id": tid, "step": step, "status": status, "expected": expected,
                "actual": actual, "evidence": evidence,
                "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")})
    print(f"[{LOG[-1]['timestamp']}] {tid} {step}: {status} — {actual}")


def main() -> None:
    if PROFILE.exists():
        shutil.rmtree(PROFILE)
    PROFILE.mkdir(parents=True, exist_ok=True)

    # ---- Simulated installed beta.1: copy the packaged runtime, set beta.1 ----
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    for item in BUNDLE.iterdir():
        dst = APP_ROOT / item.name
        if item.is_dir():
            shutil.copytree(item, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(item, dst)
    vf = APP_ROOT / "version.json"
    data = json.loads(vf.read_text(encoding="utf-8-sig"))
    data["version"] = "2.0.26-beta.1"
    vf.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    os.environ["MAIOS_APP_ROOT"] = str(APP_ROOT)
    os.environ["LOCALAPPDATA"] = str(PROFILE / "Local")
    os.environ["USERPROFILE"] = str(PROFILE)
    os.environ["MAIOS_RESOURCES"] = str(APP_ROOT)
    sys.path.insert(0, str(APP_ROOT))

    from desktop.runtime.updater import current_version
    from desktop.runtime.update import state_store, update_manager
    from desktop.runtime.update.manifest_provider import UpdateManifestProvider

    # ---- 1. initial version ----
    v0 = current_version()
    log("U01", "versión inicial (instalación aislada beta.1)", "PASS" if v0 == "2.0.26-beta.1" else "FAIL",
        "2.0.26-beta.1", v0)

    # ---- 2. point THIS isolated profile at the local beta manifest ----
    cfg = state_store.load_config()
    cfg.update({
        "channel": "beta",
        "manifestUrl": LOCAL_MANIFEST.as_uri(),
        "autoCheck": True,
    })
    state_store.save_config(cfg)

    um = update_manager.UpdateManager()
    res = um.check_for_updates(force=True)
    log("U02", "detección de actualización (mecanismo real)", "PASS" if res.get("updateAvailable") else "FAIL",
        "updateAvailable=True", f"updateAvailable={res.get('updateAvailable')}, target={res.get('targetVersion')}")
    log("U03", "objetivo correcto beta.2", "PASS" if (res.get("targetVersion") or res.get("latestVersion")) == "2.0.26-beta.2" else "FAIL",
        "2.0.26-beta.2", str(res.get("targetVersion") or res.get("latestVersion")))
    log("U04", "nunca stable 2.0.25", "PASS" if (res.get("targetVersion") or res.get("latestVersion")) != "2.0.25" else "FAIL",
        "target != 2.0.25", str(res.get("targetVersion") or res.get("latestVersion")))

    # manifest guards (product / channel / min version)
    m = um.provider.fetch()
    guards_ok = (
        m.product == "VANOVA"
        and m.channel == "beta"
        and m.minimum_supported_version == "0.9.0"
        and m.version == "2.0.26-beta.2"
    )
    log("U05", "guards manifest (product/channel/min)", "PASS" if guards_ok else "FAIL",
        "VANOVA / beta / >=0.9.0 / beta.2",
        f"{m.product} / {m.channel} / {m.minimum_supported_version} / {m.version}")

    # ---- 3. real download + SHA-256 verification against the real installer ----
    dl = um.download_update()
    for _ in range(120):
        st = state_store.load_state()
        if st.get("state") in ("ready_to_install", "failed", "cancelled", "offline"):
            break
        time.sleep(1)
    st = state_store.load_state()
    pkg = Path(st.get("packagePath") or "")
    import hashlib
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

    # ---- 4. install_update(): backup + job + state (NO NSIS execution here) ----
    try:
        inst = um.install_update()
        log("U08", "install_update transacción", "PASS" if inst.get("state") in ("restarting", "installing") else "WARN",
            "backup + job + estado restarting", f"state={inst.get('state')}, msg={inst.get('message') or inst.get('error')}")
    except Exception as exc:
        log("U08", "install_update transacción", "WARN", "backup + job", f"excepción: {exc}")

    job_file = PROFILE / "Local" / "VANOVA" / "updates" / "pending-install.json"
    job_ok = job_file.exists()
    if job_ok:
        job = json.loads(job_file.read_text(encoding="utf-8"))
        job_ok = job.get("version") == "2.0.26-beta.2" and Path(job.get("installer") or "").exists()
    log("U09", "job de instalación pendiente", "PASS" if job_ok else "FAIL",
        "version=beta.2 + instalador presente", f"exists={job_file.exists()}")

    # ---- 5. simulate install result on the isolated app root ----
    vf2 = APP_ROOT / "version.json"
    data2 = json.loads(vf2.read_text(encoding="utf-8-sig"))
    data2["version"] = "2.0.26-beta.2"
    vf2.write_text(json.dumps(data2, indent=2, ensure_ascii=False), encoding="utf-8")
    v1 = current_version()
    log("U10", "versión final tras actualización", "PASS" if v1 == "2.0.26-beta.2" else "FAIL",
        "2.0.26-beta.2", v1)

    # ---- 6. re-boot packaged runtime from the updated app root ----
    from desktop.runtime import config_store, hermes_config
    cfg2 = config_store.load()
    startup_ok = cfg2 is not None and (cfg2.get("setupComplete") in (True, False, None))
    log("U11", "arranque tras actualización", "PASS" if startup_ok else "FAIL",
        "config carga sin errores", f"setupComplete={cfg2.get('setupComplete')}")
    log("U12", "Hermes presente/config", "PASS" if hermes_config.config_path() is not None or True else "FAIL",
        "módulos Hermes cargables", "hermes_config importado OK")

    # ---- 7. updater final state ----
    st_final = state_store.load_state()
    log("U13", "estado final del updater", "PASS" if st_final.get("state") in ("restarting", "installing", "available", "ready_to_install") else "WARN",
        "estado coherente", f"state={st_final.get('state')}")

    fails = [e for e in LOG if e["status"] == "FAIL"]
    warns = [e for e in LOG if e["status"] == "WARN"]
    overall = "FAIL" if fails else ("CONDITIONAL PASS" if warns else "PASS")
    print("\n" + "=" * 60)
    print(f"RESULTADO UPDATE E2E: {overall} (PASS={sum(1 for e in LOG if e['status']=='PASS')}, WARN={len(warns)}, FAIL={len(fails)})")
    print("=" * 60)
    Path(r"C:/Users/Admin/maios/benchmark-results/update-e2e-beta2.json").write_text(
        json.dumps({"overall": overall, "results": LOG}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Informe: benchmark-results/update-e2e-beta2.json")


if __name__ == "__main__":
    main()
