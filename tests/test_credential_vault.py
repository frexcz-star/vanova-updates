"""Credential encryption at rest tests (Phase 4)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import credential_vault, install_secrets


class CredentialVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.secrets_file = base / "config" / "install_secrets.json"
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
        self.patcher = patch.object(install_secrets, "SECRETS_FILE", self.secrets_file)
        self.patcher.start()
        install_secrets.ensure_install_secrets()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_encrypt_decrypt_roundtrip(self):
        plain = "shpat_test_secret_token_12345"
        encrypted = credential_vault.encrypt_value(plain)
        self.assertTrue(credential_vault.is_encrypted(encrypted))
        self.assertNotIn(plain, encrypted)
        self.assertEqual(credential_vault.decrypt_value(encrypted), plain)

    def test_legacy_plaintext_passthrough(self):
        legacy = "old-plaintext-token"
        self.assertEqual(credential_vault.decrypt_value(legacy), legacy)

    def test_empty_values(self):
        self.assertEqual(credential_vault.encrypt_value(""), "")
        self.assertEqual(credential_vault.decrypt_value(""), "")


if __name__ == "__main__":
    unittest.main()
