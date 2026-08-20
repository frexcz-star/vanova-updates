"""Gmail skill bridge tests (Hallazgo #2 regression).

The UI could show "Gmail conectado" while Hermes had no usable email access,
because saving credentials in integrations.json never provisioned them to the
Hermes email skill (himalaya). These tests pin the bridge.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import gmail_skill_bridge

USER = "nicolo@example.com"
PASS = "app-pass-1234"


class GmailSkillBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg_path = Path(self.tmp.name) / "himalaya" / "config.toml"
        self.path_patch = patch.object(
            gmail_skill_bridge, "himalaya_config_path", return_value=self.cfg_path
        )
        self.which_patch = patch.object(gmail_skill_bridge, "himalaya_available", return_value=True)
        self.path_patch.start()
        self.which_patch.start()

    def tearDown(self):
        self.which_patch.stop()
        self.path_patch.stop()
        self.tmp.cleanup()

    def test_render_himalaya_config_uses_v2_schema(self):
        """Himalaya v2 dropped the old `backend.type = "imap"` layout; the
        bridge must render the URI-style schema (imap.server/imap.sasl.plain.*)
        or the CLI rejects the config even when valid.
        """
        text = gmail_skill_bridge.render_himalaya_config(USER, PASS)
        self.assertIn("[accounts.gmail]", text)
        self.assertIn('imap.server = "imaps://imap.gmail.com:993"', text)
        self.assertIn('smtp.server = "smtps://smtp.gmail.com:465"', text)
        self.assertIn('imap.sasl.plain.username = "nicolo@example.com"', text)
        self.assertIn('imap.sasl.plain.password.raw = "app-pass-1234"', text)
        self.assertIn('smtp.sasl.plain.password.raw = "app-pass-1234"', text)
        # Old v1 keys must NOT appear — himalaya 2.x ignores them.
        self.assertNotIn('backend.type = "imap"', text)
        self.assertNotIn('backend.auth.raw', text)

    def test_render_escapes_toml_special_chars(self):
        text = gmail_skill_bridge.render_himalaya_config("a\"b@x.com", 'p"a\\ss')
        self.assertIn("a\\\"b@x.com", text)
        self.assertIn("p\\\"a\\\\ss", text)

    def test_provision_writes_config_after_validation(self):
        with patch.object(
            gmail_skill_bridge,
            "validate_gmail_credentials",
            return_value={"ok": True, "folders": ["INBOX"]},
        ):
            result = gmail_skill_bridge.provision_gmail_skill(USER, PASS, validate=True)
        self.assertTrue(result.get("ok"))
        self.assertTrue(self.cfg_path.exists())
        content = self.cfg_path.read_text(encoding="utf-8")
        self.assertIn(USER, content)

    def test_provision_fails_without_password(self):
        result = gmail_skill_bridge.provision_gmail_skill(USER, "", validate=False)
        self.assertFalse(result.get("ok"))
        self.assertFalse(self.cfg_path.exists())

    def test_provision_skips_validation_when_disabled(self):
        with patch.object(gmail_skill_bridge, "validate_gmail_credentials") as mock_validate:
            result = gmail_skill_bridge.provision_gmail_skill(USER, PASS, validate=False)
        mock_validate.assert_not_called()
        self.assertTrue(result.get("ok"))

    def test_status_reports_unsynced_when_no_config(self):
        import json
        from desktop.runtime import integrations_store

        # Empty store: Gmail not connected, no himalaya config → "Sin configurar".
        tmp2 = tempfile.TemporaryDirectory()
        store_file = Path(tmp2.name) / "integrations.json"
        store_file.write_text(json.dumps({}), encoding="utf-8")
        with patch.object(integrations_store, "CONFIG_FILE", store_file):
            status = gmail_skill_bridge.gmail_skill_status()
        tmp2.cleanup()

        self.assertFalse(status.get("synced"))
        self.assertFalse(status.get("configExists"))
        self.assertIn("Sin configurar", status.get("detail", ""))

    def test_status_synced_when_config_matches_store(self):
        import json
        from desktop.runtime import integrations_store

        # Write a himalaya config matching the stored user.
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg_path.write_text(
            gmail_skill_bridge.render_himalaya_config(USER, PASS), encoding="utf-8"
        )

        # Fake the integrations store entry.
        tmp2 = tempfile.TemporaryDirectory()
        store_file = Path(tmp2.name) / "integrations.json"
        store_file.write_text(
            json.dumps({"gmail": {"connected": True, "user": USER}}), encoding="utf-8"
        )
        with patch.object(integrations_store, "CONFIG_FILE", store_file):
            status = gmail_skill_bridge.gmail_skill_status()
        tmp2.cleanup()

        self.assertTrue(status.get("synced"))
        self.assertEqual(status.get("detail"), "Operativo")

    def test_sync_from_store_provisions_when_connected(self):
        import json
        from desktop.runtime import integrations_store

        tmp2 = tempfile.TemporaryDirectory()
        store_file = Path(tmp2.name) / "integrations.json"
        store_file.write_text(
            json.dumps({"gmail": {"connected": True, "user": USER, "pass": PASS}}),
            encoding="utf-8",
        )
        with patch.object(integrations_store, "CONFIG_FILE", store_file):
            result = gmail_skill_bridge.sync_from_integrations_store()
        tmp2.cleanup()

        self.assertTrue(result.get("ok"))
        self.assertTrue(self.cfg_path.exists())

    def test_install_himalaya_downloads_and_verifies(self):
        """Auto-install downloads the official zip, extracts the binary and
        verifies it runs (himalaya --version).
        """
        import io
        import subprocess
        import urllib.request
        import zipfile
        from unittest.mock import MagicMock

        # Fake a real zip payload with a himalaya.exe member.
        fake_zip = io.BytesIO()
        with zipfile.ZipFile(fake_zip, "w") as zf:
            zf.writestr("himalaya.exe", b"MZ fake binary")
        fake_zip.seek(0)

        fake_resp = MagicMock()
        fake_resp.read.return_value = fake_zip.read()
        fake_resp.__enter__.return_value = fake_resp

        bin_dir = Path(self.tmp.name) / "bin"
        exe_path = bin_dir / "himalaya.exe"

        with patch.object(gmail_skill_bridge, "himalaya_bin_dir", return_value=bin_dir), \
             patch.object(gmail_skill_bridge, "himalaya_bin_path", return_value=exe_path), \
             patch.object(urllib.request, "urlopen", return_value=fake_resp), \
             patch.object(gmail_skill_bridge, "_ensure_on_path", return_value=True), \
             patch.object(
                 subprocess, "run",
                 return_value=subprocess.CompletedProcess(
                     [str(exe_path), "--version"], 0, stdout="himalaya 2.0.0", stderr=""
                 ),
             ):
            result = gmail_skill_bridge.install_himalaya()

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("himalayaInstalled"))
        self.assertTrue(exe_path.exists())
        self.assertIn("2.0.0", result.get("version", ""))

    def test_install_himalaya_failure_returns_structured_error(self):
        """Network failure never raises — returns a structured error."""
        import urllib.request

        with patch.object(urllib.request, "urlopen", side_effect=OSError("no network")):
            result = gmail_skill_bridge.install_himalaya()
        self.assertFalse(result.get("ok"))
        self.assertIn("error", result)

    def test_ensure_himalaya_skips_install_when_available(self):
        with patch.object(gmail_skill_bridge, "himalaya_available", return_value=True), \
             patch.object(gmail_skill_bridge, "install_himalaya") as mock_install:
            result = gmail_skill_bridge.ensure_himalaya()
        mock_install.assert_not_called()
        self.assertTrue(result.get("ok"))

    def test_ensure_himalaya_installs_when_missing(self):
        with patch.object(gmail_skill_bridge, "himalaya_available", return_value=False), \
             patch.object(
                 gmail_skill_bridge, "install_himalaya",
                 return_value={"ok": True, "himalayaInstalled": True, "version": "2.0.0"},
             ):
            result = gmail_skill_bridge.ensure_himalaya()
        self.assertTrue(result.get("ok"))

    def test_api_exposes_gmail_skill_status_endpoint(self):
        """The UI reads the real skill status via GET /api/gmail/skill/status."""
        source = (ROOT / "desktop" / "runtime" / "api_server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            '"/api/gmail/skill/status"', source,
            "api_server must expose the real Gmail skill status endpoint",
        )

    def test_launcher_provisions_skill_at_startup(self):
        """Regression (Hallazgo #5): credentials saved BEFORE the bridge existed
        never reached the Hermes email skill because the sync only ran on save.
        The launcher must also provision at startup, so updating clients with
        an already-connected Gmail become operational without re-saving.
        """
        source = (ROOT / "desktop" / "runtime" / "launcher.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "gmail_skill_bridge.sync_from_integrations_store()", source,
            "launcher must call the Gmail skill sync at startup",
        )
        self.assertIn("gmail_skill_loop", source)


if __name__ == "__main__":
    unittest.main()
