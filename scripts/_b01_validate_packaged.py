"""B-01 validation against the PACKAGED runtime (win-unpacked bundle).

Simulates CLEAN / CONTAMINATED / EXPLICIT / RESTART machine profiles against
the exact packaged code (release/win-unpacked/resources/vanova), with both
LOCALAPPDATA and USERPROFILE isolated so the machine-global `.hermes/.env`
cannot leak into the test unless the code itself looks for it.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

BUNDLE = Path(r"C:/Users/Admin/maios/release/win-unpacked/resources/vanova").resolve()
sys.path.insert(0, str(BUNDLE))

from desktop.runtime import config_store, hermes_config, integrations_store, shopify_sync

PROFILE = Path(os.environ["ISOLATED_PROFILE"]).resolve()
HERMES_ENV = PROFILE / ".hermes" / ".env"
LOCAL_HERMES_ENV = PROFILE / "Local" / "hermes" / ".env"

COMPANY_A = ("a-store.myshopify.com", "shpat_company_a_real_like")
COMPANY_B = ("https://b-store.myshopify.com", "shpat_company_b_real_like")


def fresh_install() -> None:
    data = config_store.data_dir()
    for item in list(data.iterdir()):
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


def dump(label: str, **fields) -> None:
    print(json.dumps({"scenario": label, **fields}, ensure_ascii=False))


def run_scenario(label: str) -> dict:
    fresh_install()
    bridge = integrations_store.sync_shopify_from_hermes_if_needed()
    shopify_sync.start_background_sync()
    sync = shopify_sync._run_sync()
    data = config_store.load()
    shopify_entry = integrations_store.get_shopify_entry()
    creds = integrations_store.get_shopify_credentials()
    return {
        "label": label,
        "bridge": bridge,
        "syncOk": bool(sync.get("ok")),
        "syncError": sync.get("error"),
        "creds": creds,
        "shopifyEntryConnected": bool(shopify_entry.get("connected")),
        "products": len(data.get("organizedProducts") or []),
        "sales": len(data.get("organizedSales") or []),
        "integrationsFile": integrations_store.CONFIG_FILE.exists(),
    }


def main() -> None:
    print(f"PROFILE={PROFILE}")
    print(f"hermes_env_path() -> {hermes_config.hermes_env_path()}")

    # ---- CLEAN MACHINE ----
    if HERMES_ENV.exists():
        HERMES_ENV.unlink()
    if LOCAL_HERMES_ENV.exists():
        LOCAL_HERMES_ENV.unlink()
    clean = run_scenario("CLEAN")

    # ---- CONTAMINATED (company A in BOTH candidate locations) ----
    HERMES_ENV.parent.mkdir(parents=True, exist_ok=True)
    HERMES_ENV.write_text(
        f"SHOPIFY_STORE_DOMAIN={COMPANY_A[0]}\nSHOPIFY_ACCESS_TOKEN={COMPANY_A[1]}\n",
        encoding="utf-8",
    )
    LOCAL_HERMES_ENV.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_HERMES_ENV.write_text(
        f"SHOPIFY_STORE_DOMAIN={COMPANY_A[0]}\nSHOPIFY_ACCESS_TOKEN={COMPANY_A[1]}\n",
        encoding="utf-8",
    )
    contaminated = run_scenario("CONTAMINATED_A")

    # ---- EXPLICIT B on the contaminated machine ----
    fresh_install()
    save = integrations_store.save_config(
        "shopify", {"url": COMPANY_B[0], "token": COMPANY_B[1]}
    )
    bridge_b = integrations_store.sync_shopify_from_hermes_if_needed()
    creds_b = integrations_store.get_shopify_credentials()
    explicit = {
        "label": "EXPLICIT_B",
        "saveOk": bool(save.get("ok")),
        "bridge": bridge_b,
        "creds": creds_b,
        "usesCompanyA": creds_b.get("token") == COMPANY_A[1],
    }

    # ---- RESTART ----
    bridge_restart = integrations_store.sync_shopify_from_hermes_if_needed()
    creds_restart = integrations_store.get_shopify_credentials()
    restart = {
        "label": "RESTART",
        "bridge": bridge_restart,
        "creds": creds_restart,
        "keepsCompanyB": creds_restart.get("token") == COMPANY_B[1],
    }

    for r in (clean, contaminated, explicit, restart):
        dump(**r)

    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        if not cond:
            ok = False
            print(f"FAIL: {msg}")

    check(clean["bridge"].get("reason") == "not_configured", "clean: bridge must be no-op")
    check(not clean["creds"], "clean: no credentials")
    check(clean["products"] == 0 and clean["sales"] == 0, "clean: no data")
    check(clean["syncError"] == "Shopify no conectado", "clean: honest sync error")

    check(contaminated["bridge"].get("reason") == "not_configured", "contaminated: must NOT import A")
    check(not contaminated["creds"], "contaminated: no A credentials")
    check(contaminated["products"] == 0 and contaminated["sales"] == 0, "contaminated: no A data")
    check(not contaminated["integrationsFile"], "contaminated: nothing written")
    check(contaminated["syncError"] == "Shopify no conectado", "contaminated: honest sync error")

    check(explicit["saveOk"], "explicit B: config saved")
    check(explicit["bridge"].get("reason") == "shop_mismatch", "explicit B: A must not replace B")
    check(explicit["creds"].get("token") == COMPANY_B[1], "explicit B: uses B token")
    check(not explicit["usesCompanyA"], "explicit B: never uses A")

    check(restart["keepsCompanyB"], "restart: keeps B")
    check(restart["bridge"].get("reason") == "shop_mismatch", "restart: A not re-discovered")

    print("RESULT=" + ("PASS" if ok else "FAIL"))


if __name__ == "__main__":
    main()
