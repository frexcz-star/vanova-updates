"""B-01 — Isolation: a fresh VANOVA installation must NEVER inherit Shopify
credentials from a machine-global Hermes `.env`.

A machine may have a legacy global `~/.hermes/.env` (or
`%LOCALAPPDATA%/hermes/.env`) belonging to ANOTHER company. VANOVA must not
auto-detect it: the only sanctioned import path is the guided setup flow,
which requires explicit user consent and shows which shop / what data will be
synced. Credentials may only be REFRESHED from Hermes `.env` for a shop this
installation has explicitly configured (`connected=True`), and never for a
different shop.

Regression scenarios (tester B-01):
  1. Clean machine (no .env)  → fresh install has no Shopify, no credentials.
  2. Contaminated machine     → `.hermes/.env` of company A; fresh install for
     company B must NOT use A's credentials or sync A's data.
  3. Explicit config          → deliberately configured shop B connects and
     syncs B; A is never used.
  4. Restart                  → after close/reopen, B is kept and A is not
     re-discovered.
  5. Separation               → two independent installations never share
     credentials or data.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import config_store, hermes_config, integrations_store, shopify_sync

COMPANY_A_URL = "https://a-store.myshopify.com"
COMPANY_A_TOKEN = "shpat_company_a_token"
COMPANY_B_URL = "https://b-store.myshopify.com"
COMPANY_B_TOKEN = "shpat_company_b_token"


class HermesEnvIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.integrations_file = base / "integrations.json"
        self.hermes_env = base / "hermes.env"
        self.integrations_patch = patch.object(integrations_store, "CONFIG_FILE", self.integrations_file)
        self.env_patch = patch.object(hermes_config, "hermes_env_path", return_value=self.hermes_env)
        self.integrations_patch.start()
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.integrations_patch.stop()
        self.tmp.cleanup()

    def _write_hermes_env(self, domain: str, token: str) -> None:
        self.hermes_env.write_text(
            f"SHOPIFY_STORE_DOMAIN={domain}\nSHOPIFY_ACCESS_TOKEN={token}\n",
            encoding="utf-8",
        )

    def _write_shopify_config(self, url: str, token: str, **extra) -> None:
        entry = {"connected": True, "url": url, "token": token}
        entry.update(extra)
        self.integrations_file.write_text(json.dumps({"shopify": entry}), encoding="utf-8")

    # ---------------------------------------------------------------- TEST 1
    def test_clean_machine_no_hermes_env_no_shopify(self):
        """TEST 1 — máquina limpia: sin .hermes/.env → instalación nueva sin
        Shopify, sin credenciales, sin sincronización automática."""
        with patch.object(hermes_config, "hermes_env_path", return_value=None):
            with patch.object(integrations_store, "_trigger_shopify_sync") as trigger:
                result = integrations_store.sync_shopify_from_hermes_if_needed()
        # Sin config explícita, el bridge es un no-op (guard de aislamiento) —
        # nunca importa, nunca sincroniza.
        self.assertEqual(result.get("reason"), "not_configured")
        self.assertFalse(result.get("imported"))
        self.assertEqual(integrations_store.get_shopify_credentials(), {})
        trigger.assert_not_called()
        self.assertFalse(self.integrations_file.exists())

    def test_clean_machine_no_hermes_env_sync_is_honest_noop(self):
        """Máquina limpia: el arranque llama al bridge y al loop de sync;
        sin credenciales la sync termina de forma honesta sin escribir datos."""
        with patch.object(hermes_config, "hermes_env_path", return_value=None):
            r = shopify_sync._run_sync()
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("error"), "Shopify no conectado")

    # ---------------------------------------------------------------- TEST 2
    def test_contaminated_machine_fresh_install_does_not_import(self):
        """TEST 2 — máquina contaminada: `.hermes/.env` con credenciales de la
        empresa A; instalación nueva de VANOVA NO usa A, NO conecta A, NO
        importa productos/pedidos de A."""
        self._write_hermes_env("a-store.myshopify.com", COMPANY_A_TOKEN)
        with patch.object(integrations_store, "_trigger_shopify_sync") as trigger:
            result = integrations_store.sync_shopify_from_hermes_if_needed()

        self.assertEqual(
            result,
            {"imported": False, "source": "maios", "ok": False, "reason": "not_configured"},
        )
        self.assertEqual(integrations_store.get_shopify_credentials(), {})
        trigger.assert_not_called()
        # Nada se escribió: la instalación nueva sigue sin integración alguna.
        self.assertFalse(self.integrations_file.exists())

    def test_contaminated_machine_startup_chain_never_syncs_company_a(self):
        """Cadena completa de arranque (launcher: bridge + start_background_sync)
        en máquina contaminada: la sync NO descarga productos/pedidos de A."""
        self._write_hermes_env("a-store.myshopify.com", COMPANY_A_TOKEN)
        store: dict = {}
        with ExitStack() as stack:
            stack.enter_context(patch.object(integrations_store, "_trigger_shopify_sync"))
            stack.enter_context(patch.object(config_store, "load", side_effect=lambda: dict(store)))
            stack.enter_context(patch.object(config_store, "save", side_effect=lambda d: store.update(d)))
            r = shopify_sync._run_sync()
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("error"), "Shopify no conectado")
        self.assertNotIn("organizedProducts", store)
        self.assertNotIn("organizedSales", store)

    # ---------------------------------------------------------------- TEST 3
    def test_explicit_config_company_b_never_uses_company_a(self):
        """TEST 3 — configuración explícita: la tienda B está deliberadamente
        conectada; la existencia de A en `.hermes/.env` NO la reemplaza."""
        self._write_hermes_env("a-store.myshopify.com", COMPANY_A_TOKEN)
        self._write_shopify_config(COMPANY_B_URL, COMPANY_B_TOKEN)
        with patch.object(integrations_store, "_trigger_shopify_sync") as trigger:
            result = integrations_store.sync_shopify_from_hermes_if_needed()

        self.assertFalse(result.get("imported"))
        self.assertEqual(result.get("reason"), "shop_mismatch")
        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["url"], COMPANY_B_URL)
        self.assertEqual(creds["token"], COMPANY_B_TOKEN)
        trigger.assert_not_called()

    def test_explicit_config_company_b_sync_uses_b_credentials(self):
        """TEST 3 (sync) — con B explícitamente conectada, la sync descarga B
        usando SOLO el token de B; el token de A nunca llega a la red."""
        self._write_hermes_env("a-store.myshopify.com", COMPANY_A_TOKEN)
        self._write_shopify_config(COMPANY_B_URL, COMPANY_B_TOKEN)
        seen: dict[str, str] = {}

        def fake_get_all(url: str, token: str, path: str, limit: int = 250):
            seen["url"] = url
            seen["token"] = token
            if "products" in path:
                return [{"title": "B-1", "variants": [{"sku": "B-1", "price": "10.00"}]}]
            return []

        store: dict = {}
        with ExitStack() as stack:
            stack.enter_context(patch.object(integrations_store, "_trigger_shopify_sync"))
            stack.enter_context(
                patch.object(
                    shopify_sync,
                    "check_credentials",
                    return_value={"ok": True, "grantedScopes": ["read_products", "read_orders"], "missingScopes": []},
                )
            )
            stack.enter_context(patch.object(shopify_sync, "_shopify_get_all", side_effect=fake_get_all))
            stack.enter_context(patch.object(config_store, "load", side_effect=lambda: dict(store)))
            stack.enter_context(patch.object(config_store, "save", side_effect=lambda d: store.update(d)))
            stack.enter_context(patch("desktop.runtime.file_organizer.sync_dashboard_overview"))
            stack.enter_context(patch("desktop.runtime.hermes_activity.log_step"))
            r = shopify_sync._run_sync()

        self.assertTrue(r.get("ok"))
        self.assertEqual(seen["url"], COMPANY_B_URL)
        self.assertEqual(seen["token"], COMPANY_B_TOKEN)
        self.assertEqual(len(store.get("organizedProducts") or []), 1)

    # ---------------------------------------------------------------- TEST 4
    def test_restart_keeps_company_b_and_never_rescans_company_a(self):
        """TEST 4 — reinicio: al cerrar y volver a abrir, VANOVA mantiene B y
        no vuelve a buscar A automáticamente."""
        self._write_hermes_env("a-store.myshopify.com", COMPANY_A_TOKEN)
        self._write_shopify_config(COMPANY_B_URL, COMPANY_B_TOKEN)
        for run in (1, 2):  # primer arranque + tras reiniciar
            with patch.object(integrations_store, "_trigger_shopify_sync") as trigger:
                result = integrations_store.sync_shopify_from_hermes_if_needed()
            self.assertFalse(result.get("imported"), f"run {run}: A importada")
            self.assertEqual(result.get("reason"), "shop_mismatch", f"run {run}")
            creds = integrations_store.get_shopify_credentials()
            self.assertEqual(creds["token"], COMPANY_B_TOKEN, f"run {run}")
            trigger.assert_not_called()

    # ---------------------------------------------------------------- TEST 5
    def test_two_installations_do_not_share_credentials(self):
        """TEST 5 — separación entre instalaciones: dos configuraciones
        independientes no comparten credenciales ni datos."""
        self._write_hermes_env("a-store.myshopify.com", COMPANY_A_TOKEN)
        install1 = Path(self.tmp.name) / "install-1" / "integrations.json"
        install2 = Path(self.tmp.name) / "install-2" / "integrations.json"
        install1.parent.mkdir(parents=True)
        install2.parent.mkdir(parents=True)
        install1.write_text(
            json.dumps(
                {"shopify": {"connected": True, "url": COMPANY_A_URL, "token": COMPANY_A_TOKEN, "source": "hermes-env"}}
            ),
            encoding="utf-8",
        )
        # install-2 es una instalación nueva: no existe integrations.json.

        with patch.object(integrations_store, "CONFIG_FILE", install1), patch(
            "desktop.runtime.shopify_sync.check_credentials",
            return_value={"ok": True, "grantedScopes": ["read_products", "read_orders"]},
        ):
            r1 = integrations_store.sync_shopify_from_hermes_if_needed()
        with patch.object(integrations_store, "CONFIG_FILE", install2):
            r2 = integrations_store.sync_shopify_from_hermes_if_needed()
            creds2 = integrations_store.get_shopify_credentials()

        # Instalación 1 (empresa A, ya conectada) refresca su propio token A.
        self.assertIn(r1.get("source"), ("hermes-env", "maios"))
        self.assertFalse(r1.get("imported"))
        # Instalación 2 (nueva) NO hereda nada de la máquina global.
        self.assertEqual(r2.get("reason"), "not_configured")
        self.assertEqual(creds2, {})

    # ------------------------------------------------- explicit consent path
    def test_explicit_consent_guided_setup_still_works(self):
        """El flujo guiado (consentimiento explícito: muestra la tienda, pide
        confirmación y guarda en ESTA instalación) sigue funcionando."""
        self._write_hermes_env("demo.myshopify.com", "shpat_hermes_token")
        with patch(
            "desktop.runtime.shopify_sync.check_credentials",
            return_value={"ok": True, "grantedScopes": ["read_products", "read_orders"]},
        ), patch.object(integrations_store, "_trigger_shopify_sync"):
            save = integrations_store.save_config(
                "shopify",
                {"url": "demo.myshopify.com", "token": "shpat_hermes_token"},
            )
        self.assertTrue(save.get("ok"))
        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["token"], "shpat_hermes_token")

    def test_existing_configured_install_still_refreshes_same_shop(self):
        """Requisito 8: una instalación YA configurada con la misma tienda
        puede refrescar el token desde Hermes .env (rotación de token), sin
        cambiar de tienda."""
        self._write_hermes_env("demo.myshopify.com", "shpat_hermes_new")
        self._write_shopify_config(
            "https://demo.myshopify.com",
            "shpat_stale",
            source="hermes-env",
        )

        def fake_check(url: str, token: str) -> dict:
            if token == "shpat_stale":
                return {"ok": False, "missingScopes": ["read_products", "read_orders"]}
            return {"ok": True, "grantedScopes": ["read_products", "read_orders"]}

        with patch("desktop.runtime.shopify_sync.check_credentials", side_effect=fake_check), patch.object(
            integrations_store, "_trigger_shopify_sync"
        ):
            result = integrations_store.sync_shopify_from_hermes_if_needed()

        self.assertTrue(result.get("imported"))
        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["url"], "https://demo.myshopify.com")
        self.assertEqual(creds["token"], "shpat_hermes_new")


if __name__ == "__main__":
    unittest.main()
