"""Tests for Hermes-guided Shopify setup conversation."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import hermes_shopify_setup, integrations_store


class HermesShopifySetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.integrations_file = Path(self.tmp.name) / "integrations.json"
        self.integrations_patch = patch.object(
            integrations_store, "CONFIG_FILE", self.integrations_file
        )
        self.integrations_patch.start()
        self.conv: dict = {}

    def tearDown(self):
        self.integrations_patch.stop()
        self.tmp.cleanup()

    def test_detects_setup_intent(self):
        self.assertTrue(hermes_shopify_setup.wants_shopify_setup("Configura Shopify"))
        self.assertTrue(hermes_shopify_setup.wants_shopify_setup("Conecta mi tienda"))
        self.assertTrue(hermes_shopify_setup.wants_shopify_setup("Configura la integración de Shopify"))
        self.assertFalse(hermes_shopify_setup.wants_shopify_setup("¿Cuántos productos tengo?"))

    def test_starts_manual_flow_without_hermes_env(self):
        with patch.object(hermes_shopify_setup, "_hermes_credentials_available", return_value={}):
            result = hermes_shopify_setup.handle("Configura Shopify", self.conv)
        self.assertIsNotNone(result)
        self.assertIn("Paso 1/2", result["summary"])
        self.assertTrue(self.conv.get("shopify_setup", {}).get("active"))
        self.assertEqual(result["shopifySetup"]["step"], "ask_url")

    def test_offers_hermes_import_when_env_available(self):
        hermes = {"url": "https://demo.myshopify.com", "token": "shpat_hermes_token"}
        with patch.object(hermes_shopify_setup, "_hermes_credentials_available", return_value=hermes):
            with patch(
                "desktop.runtime.shopify_sync.check_credentials",
                return_value={"ok": True, "grantedScopes": ["read_products", "read_orders"]},
            ):
                result = hermes_shopify_setup.handle("Configura Shopify", self.conv)
        self.assertIn("credenciales de Shopify en Hermes", result["summary"])
        self.assertEqual(result["shopifySetup"]["step"], "offer_hermes")
        replies = [r["label"] for r in result["shopifySetup"]["quickReplies"]]
        self.assertIn("Sí, usar Hermes", replies)

    def test_imports_hermes_credentials_on_yes(self):
        hermes = {"url": "https://demo.myshopify.com", "token": "shpat_hermes_token"}
        self.conv["shopify_setup"] = {
            "active": True,
            "step": "offer_hermes",
            "hermes_url": hermes["url"],
            "hermes_token": hermes["token"],
        }
        with patch(
            "desktop.runtime.shopify_sync.check_credentials",
            return_value={"ok": True, "grantedScopes": ["read_products", "read_orders"]},
        ):
            with patch.object(integrations_store, "_trigger_shopify_sync"):
                result = hermes_shopify_setup.handle("Sí, usar credenciales de Hermes", self.conv)
        self.assertIn("Listo", result["summary"])
        self.assertFalse(result["shopifySetup"]["active"])
        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["token"], "shpat_hermes_token")

    def test_manual_url_and_token_flow(self):
        self.conv["shopify_setup"] = {"active": True, "step": "ask_url"}
        result = hermes_shopify_setup.handle("demo.myshopify.com", self.conv)
        self.assertIn("Paso 2/2", result["summary"])
        self.assertEqual(self.conv["shopify_setup"]["step"], "ask_token")

        with patch(
            "desktop.runtime.shopify_sync.check_credentials",
            return_value={"ok": True, "grantedScopes": ["read_products", "read_orders"]},
        ):
            with patch.object(integrations_store, "_trigger_shopify_sync"):
                result = hermes_shopify_setup.handle("shpat_abc1234567890", self.conv)
        self.assertIn("Listo", result["summary"])
        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["url"], "https://demo.myshopify.com")
        self.assertEqual(creds["token"], "shpat_abc1234567890")

    def test_reports_missing_scopes(self):
        self.conv["shopify_setup"] = {"active": True, "step": "ask_token", "url": "https://demo.myshopify.com"}
        with patch(
            "desktop.runtime.shopify_sync.check_credentials",
            return_value={
                "ok": False,
                "grantedScopes": ["read_products"],
                "missingScopes": ["read_orders"],
            },
        ):
            with patch.object(integrations_store, "_trigger_shopify_sync"):
                result = hermes_shopify_setup.handle("shpat_partial1234567890", self.conv)
        self.assertIn("read_orders", result["summary"])
        self.assertTrue(result["shopifySetup"]["reloadIntegrations"])

    def test_redacts_tokens_in_logs(self):
        redacted = hermes_shopify_setup.redact_sensitive("token shpat_secret1234567890 ok")
        self.assertNotIn("shpat_secret", redacted)
        self.assertIn("[token redactado]", redacted)

    def test_cancel_clears_setup(self):
        self.conv["shopify_setup"] = {"active": True, "step": "ask_url"}
        result = hermes_shopify_setup.handle("cancelar", self.conv)
        self.assertIn("cancelada", result["summary"])
        self.assertFalse(result["shopifySetup"]["active"])


if __name__ == "__main__":
    unittest.main()
