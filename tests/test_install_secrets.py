"""Tests for per-installation secrets (Phase 1)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import install_secrets


class InstallSecretsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.secrets_file = base / "config" / "install_secrets.json"
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
        self.secrets_patcher = patch.object(install_secrets, "SECRETS_FILE", self.secrets_file)
        self.secrets_patcher.start()

    def tearDown(self):
        self.secrets_patcher.stop()
        self.tmp.cleanup()

    def test_first_run_generates_unique_secrets(self):
        data = install_secrets.ensure_install_secrets()
        self.assertTrue(self.secrets_file.exists())
        self.assertTrue(data["runtimeToken"])
        self.assertTrue(data["installationId"])
        self.assertTrue(data["encryptionKeyFoundation"])
        self.assertTrue(data["deviceIdentity"])

        again = install_secrets.ensure_install_secrets()
        self.assertEqual(again["installationId"], data["installationId"])
        self.assertEqual(again["runtimeToken"], data["runtimeToken"])

    def test_rotate_runtime_credentials_preserves_install_identity(self):
        original = install_secrets.ensure_install_secrets()
        result = install_secrets.rotateRuntimeCredentials()
        rotated = install_secrets.load_secrets()

        self.assertTrue(result["rotated"])
        self.assertEqual(rotated["installationId"], original["installationId"])
        self.assertEqual(rotated["encryptionKeyFoundation"], original["encryptionKeyFoundation"])
        self.assertNotEqual(rotated["runtimeToken"], original["runtimeToken"])
        self.assertTrue(install_secrets.validate_runtime_token(original["runtimeToken"]))

    def test_validate_rejects_unknown_token(self):
        install_secrets.ensure_install_secrets()
        self.assertFalse(install_secrets.validate_runtime_token("not-a-real-token"))

    def test_corrupt_secrets_file_is_regenerated(self):
        self.secrets_file.write_text("{not-json", encoding="utf-8")
        data = install_secrets.ensure_install_secrets()
        self.assertTrue(data["runtimeToken"])
        loaded = json.loads(self.secrets_file.read_text(encoding="utf-8"))
        self.assertIn("installationId", loaded)


if __name__ == "__main__":
    unittest.main()
