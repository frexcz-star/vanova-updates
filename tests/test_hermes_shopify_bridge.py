"""Hermes → VANOVA Shopify credential bridge tests."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import hermes_config, integrations_store


class HermesShopifyBridgeTests(unittest.TestCase):
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

    def test_load_hermes_shopify_credentials(self):
        self._write_hermes_env("demo.myshopify.com", "shpat_hermes_token")
        creds = hermes_config.load_hermes_shopify_credentials()
        self.assertEqual(creds["url"], "https://demo.myshopify.com")
        self.assertEqual(creds["token"], "shpat_hermes_token")

    def test_imports_hermes_token_when_maios_lacks_scopes(self):
        self.integrations_file.write_text(
            json.dumps(
                {
                    "shopify": {
                        "connected": True,
                        "url": "https://demo.myshopify.com",
                        "token": "shpat_stale_token",
                    }
                }
            ),
            encoding="utf-8",
        )
        self._write_hermes_env("demo.myshopify.com", "shpat_hermes_good")

        def fake_check(url: str, token: str) -> dict:
            if token == "shpat_stale_token":
                return {"ok": False, "missingScopes": ["read_products", "read_orders"]}
            if token == "shpat_hermes_good":
                return {"ok": True, "grantedScopes": ["read_products", "read_orders"]}
            return {"ok": False}

        with patch("desktop.runtime.shopify_sync.check_credentials", side_effect=fake_check):
            with patch.object(integrations_store, "_trigger_shopify_sync"):
                result = integrations_store.sync_shopify_from_hermes_if_needed()

        self.assertTrue(result and result.get("imported"))
        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["token"], "shpat_hermes_good")
        entry = integrations_store.get_shopify_entry()
        self.assertEqual(entry.get("source"), "hermes-env")

    def test_skips_import_when_tokens_already_aligned(self):
        self.integrations_file.write_text(
            json.dumps(
                {
                    "shopify": {
                        "connected": True,
                        "url": "https://demo.myshopify.com",
                        "token": "shpat_hermes_good",
                        "source": "hermes-env",
                    }
                }
            ),
            encoding="utf-8",
        )
        self._write_hermes_env("demo.myshopify.com", "shpat_hermes_good")

        with patch(
            "desktop.runtime.shopify_sync.check_credentials",
            return_value={"ok": True, "grantedScopes": ["read_products", "read_orders"]},
        ):
            result = integrations_store.sync_shopify_from_hermes_if_needed()

        self.assertFalse(result and result.get("imported"))
        self.assertTrue(result and result.get("alreadyAligned"))
        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["token"], "shpat_hermes_good")

    def test_imports_when_hermes_token_changed_even_if_maios_valid(self):
        self.integrations_file.write_text(
            json.dumps(
                {
                    "shopify": {
                        "connected": True,
                        "url": "https://demo.myshopify.com",
                        "token": "shpat_maios_good",
                        "source": "hermes-env",
                    }
                }
            ),
            encoding="utf-8",
        )
        self._write_hermes_env("demo.myshopify.com", "shpat_hermes_new")

        def fake_check(url: str, token: str) -> dict:
            return {"ok": True, "grantedScopes": ["read_products", "read_orders"]}

        with patch("desktop.runtime.shopify_sync.check_credentials", side_effect=fake_check):
            with patch.object(integrations_store, "_trigger_shopify_sync"):
                result = integrations_store.sync_shopify_from_hermes_if_needed()

        self.assertTrue(result and result.get("imported"))
        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["token"], "shpat_hermes_new")

    def test_aligns_hermes_token_when_both_lack_maios_scopes(self):
        self.integrations_file.write_text(
            json.dumps(
                {
                    "shopify": {
                        "connected": True,
                        "url": "https://demo.myshopify.com",
                        "token": "shpat_stale_token",
                    }
                }
            ),
            encoding="utf-8",
        )
        self._write_hermes_env("demo.myshopify.com", "shpat_hermes_token")

        def fake_check(url: str, token: str) -> dict:
            granted = ["read_customers", "read_inventory"] + (
                ["read_products"] if token == "shpat_hermes_token" else []
            )
            missing = [s for s in ("read_products", "read_orders") if s not in granted]
            return {
                "ok": not missing,
                "grantedScopes": granted,
                "missingScopes": missing,
            }

        with patch("desktop.runtime.shopify_sync.check_credentials", side_effect=fake_check):
            with patch.object(integrations_store, "_trigger_shopify_sync"):
                result = integrations_store.sync_shopify_from_hermes_if_needed()

        self.assertTrue(result and result.get("imported"))
        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["token"], "shpat_hermes_token")
        self.assertFalse(result.get("ok"))
        self.assertIn("read_orders", result.get("missingScopes") or [])

    def test_does_not_import_different_shop(self):
        self.integrations_file.write_text(
            json.dumps(
                {
                    "shopify": {
                        "connected": True,
                        "url": "https://other.myshopify.com",
                        "token": "shpat_stale_token",
                    }
                }
            ),
            encoding="utf-8",
        )
        self._write_hermes_env("demo.myshopify.com", "shpat_hermes_good")

        def fake_check(url: str, token: str) -> dict:
            if token == "shpat_stale_token":
                return {"ok": False, "missingScopes": ["read_products"]}
            return {"ok": True, "grantedScopes": ["read_products", "read_orders"]}

        with patch("desktop.runtime.shopify_sync.check_credentials", side_effect=fake_check):
            result = integrations_store.sync_shopify_from_hermes_if_needed()

        self.assertEqual(result.get("reason"), "shop_mismatch")
        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["token"], "shpat_stale_token")


if __name__ == "__main__":
    unittest.main()
