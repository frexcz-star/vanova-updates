"""Integration credential encryption tests (Phase 4)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import credential_vault, install_secrets, integrations_store


class IntegrationsEncryptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.secrets_file = base / "config" / "install_secrets.json"
        self.integrations_file = base / "data" / "integrations.json"
        self.integrations_file.parent.mkdir(parents=True, exist_ok=True)
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)

        self.secrets_patch = patch.object(install_secrets, "SECRETS_FILE", self.secrets_file)
        self.integrations_patch = patch.object(integrations_store, "CONFIG_FILE", self.integrations_file)
        self.secrets_patch.start()
        self.integrations_patch.start()
        install_secrets.ensure_install_secrets()

    def tearDown(self):
        self.secrets_patch.stop()
        self.integrations_patch.stop()
        self.tmp.cleanup()

    def test_shopify_token_stored_encrypted(self):
        with patch.object(integrations_store, "_validate_shopify", return_value={"ok": True}):
            with patch.object(integrations_store, "_trigger_shopify_sync"):
                integrations_store.save_config(
                    "shopify",
                    {"url": "https://demo.myshopify.com", "token": "shpat_secret_value"},
                )

        raw = json.loads(self.integrations_file.read_text(encoding="utf-8"))
        stored_token = raw["shopify"]["token"]
        self.assertTrue(credential_vault.is_encrypted(stored_token))
        self.assertNotIn("shpat_secret_value", stored_token)

        creds = integrations_store.get_shopify_credentials()
        self.assertEqual(creds["token"], "shpat_secret_value")

    def test_get_config_never_exposes_secrets(self):
        with patch.object(integrations_store, "_validate_shopify", return_value={"ok": True}):
            with patch.object(integrations_store, "_trigger_shopify_sync"):
                integrations_store.save_config(
                    "shopify",
                    {"url": "https://demo.myshopify.com", "token": "shpat_secret_value"},
                )
        public = integrations_store.get_config("shopify")
        self.assertTrue(public.get("tokenSet"))
        self.assertNotIn("token", public)


if __name__ == "__main__":
    unittest.main()
