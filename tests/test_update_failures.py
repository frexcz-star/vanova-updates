"""Failure-path tests for update system — each leaves safe state."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime.update.update_manager import UpdateManager
from desktop.runtime.update.manifest_provider import UpdateManifest
from desktop.runtime.update import state_store
from desktop.runtime.update.state_machine import UpdateState


class UpdateFailureTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data = Path(self._tmpdir.name)
        patcher = patch("desktop.runtime.update.state_store.data_dir", return_value=self.data)
        self.addCleanup(patcher.stop)
        patcher.start()
        patcher2 = patch("desktop.runtime.update.downloader.data_dir", return_value=self.data)
        self.addCleanup(patcher2.stop)
        patcher2.start()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_invalid_manifest_rejected(self):
        mgr = UpdateManager()
        with patch.object(mgr.provider, "fetch", side_effect=ValueError("Invalid manifest")):
            with patch("desktop.runtime.updater.current_version", return_value="0.9.0"):
                r = mgr.check_for_updates(force=True)
        self.assertEqual(r["state"], UpdateState.OFFLINE.value)

    def test_checksum_mismatch_stays_on_101(self):
        """Wrong SHA-256 on 1.0.2 package → rejected; installed version unchanged."""
        mgr = UpdateManager()
        manifest = UpdateManifest(
            version="1.0.2",
            download_url="local:release/VANOVA-Setup-1.0.2.exe",
            sha256="0" * 64,
            size=100,
        )
        state_store.set_state(UpdateState.AVAILABLE, manifest=manifest.__dict__, targetVersion="1.0.2")
        pkg = self.data / "temp" / "update" / "1.0.2" / "VANOVA-Setup.exe"
        pkg.parent.mkdir(parents=True, exist_ok=True)
        pkg.write_bytes(b"wrong-content-for-102")
        state_store.set_state(UpdateState.DOWNLOADED, packagePath=str(pkg))
        with patch("desktop.runtime.updater.current_version", return_value="1.0.1"):
            r = mgr.verify_package()
        self.assertEqual(r["state"], UpdateState.FAILED.value)
        self.assertFalse(pkg.exists())

    def test_corrupted_package_aborted(self):
        """Truncated/corrupted package → verify fails, no install."""
        mgr = UpdateManager()
        manifest = UpdateManifest(
            version="1.0.2",
            download_url="local:release/VANOVA-Setup-1.0.2.exe",
            sha256="a" * 64,
            size=999999,
        )
        state_store.set_state(UpdateState.AVAILABLE, manifest=manifest.__dict__, targetVersion="1.0.2")
        pkg = self.data / "temp" / "update" / "1.0.2" / "VANOVA-Setup.exe"
        pkg.parent.mkdir(parents=True, exist_ok=True)
        pkg.write_bytes(b"corrupt")
        state_store.set_state(UpdateState.DOWNLOADED, packagePath=str(pkg))
        r = mgr.verify_package()
        self.assertEqual(r["state"], UpdateState.FAILED.value)

    def test_checksum_mismatch(self):
        mgr = UpdateManager()
        manifest = UpdateManifest(
            version="0.9.1",
            download_url="local:release/VANOVA-Setup.exe",
            sha256="0" * 64,
            size=100,
        )
        state_store.set_state(UpdateState.AVAILABLE, manifest=manifest.__dict__, targetVersion="0.9.1")
        # Create fake package with wrong hash
        pkg = self.data / "temp" / "update" / "0.9.1" / "VANOVA-Setup.exe"
        pkg.parent.mkdir(parents=True, exist_ok=True)
        pkg.write_bytes(b"wrong-content")
        state_store.set_state(UpdateState.DOWNLOADED, packagePath=str(pkg))
        r = mgr.verify_package()
        self.assertEqual(r["state"], UpdateState.FAILED.value)
        self.assertFalse(pkg.exists())

    def test_cancel_download(self):
        mgr = UpdateManager()
        r = mgr.cancel()
        self.assertEqual(r["state"], UpdateState.CANCELLED.value)


if __name__ == "__main__":
    unittest.main()
