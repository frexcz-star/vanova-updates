"""Unit tests for VANOVA update system."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime.update.semver import compare, gt, gte, satisfies_minimum, Version
from desktop.runtime.update.manifest_provider import UpdateManifest, UpdateManifestProvider
from desktop.runtime.update.state_machine import UpdateState, can_transition, transition
from desktop.runtime.update.downloader import UpdateDownloader
from desktop.runtime.update.update_manager import UpdateManager
from desktop.runtime.update import state_store


class SemverTests(unittest.TestCase):
    def test_patch_minor_major(self):
        self.assertEqual(compare("0.9.0", "0.10.0"), -1)
        self.assertTrue(gt("0.10.0", "0.9.0"))
        self.assertFalse(gt("0.9.0", "0.9.1"))
        self.assertTrue(gte("0.9.0", "0.9.0"))

    def test_prerelease(self):
        self.assertTrue(gt("1.0.0", "1.0.0-beta.1"))
        self.assertTrue(gt("1.0.0-beta.2", "1.0.0-beta.1"))

    def test_prerelease_numeric_identifiers(self):
        # VANOVA 3.0: prerelease con identificadores numéricos — beta.10 > beta.2
        # (la comparación de strings habría bloqueado la actualización en beta.10).
        self.assertTrue(gt("2.0.26-beta.10", "2.0.26-beta.2"))
        self.assertTrue(gt("2.0.26-beta.10", "2.0.26-beta.9"))
        self.assertTrue(gt("2.0.26-rc.1", "2.0.26-beta.5"))  # rc > beta (alfanumérica)
        self.assertFalse(gt("2.0.26-beta.2", "2.0.26-beta.10"))
        self.assertEqual(compare("2.0.26-beta.2", "2.0.26-beta.02"), 0)  # ceros a la izquierda

    def test_invalid_version(self):
        with self.assertRaises(ValueError):
            Version.parse("not-a-version")

    def test_minimum_supported(self):
        self.assertTrue(satisfies_minimum("0.9.0", "0.8.0"))
        self.assertFalse(satisfies_minimum("0.7.0", "0.8.0"))


class ManifestTests(unittest.TestCase):
    def test_parse_and_validate(self):
        data = {
            "product": "VANOVA",
            "channel": "stable",
            "version": "0.10.0",
            "minimumSupportedVersion": "0.8.0",
            "mandatory": False,
            "publishedAt": "2026-08-12T00:00:00Z",
            "downloadUrl": "local:release/VANOVA-Setup-0.10.0.exe",
            "sha256": "a" * 64,
            "size": 123456,
            "releaseNotes": ["Fix bugs"],
        }
        m = UpdateManifest.from_dict(data)
        self.assertEqual(m.version, "0.10.0")
        self.assertEqual(m.release_notes, ["Fix bugs"])
        self.assertEqual(m.validate(), [])

    def test_invalid_manifest(self):
        m = UpdateManifest(version="0.0.0", download_url="http://bad.example/x.exe", sha256="short")
        errors = m.validate()
        self.assertTrue(any("sha256" in e for e in errors))
        self.assertTrue(any("HTTPS" in e for e in errors))

    def test_update_available(self):
        provider = UpdateManifestProvider(manifest_url="local:release/latest.json")
        manifest = UpdateManifest(version="0.10.0", download_url="local:x", sha256="b" * 64, size=1)
        self.assertTrue(provider.is_update_available("0.9.0", manifest))
        self.assertFalse(provider.is_update_available("0.10.0", manifest))



class StateMachineTests(unittest.TestCase):
    def test_happy_path(self):
        s = UpdateState.IDLE
        s = transition(s, UpdateState.CHECKING)
        s = transition(s, UpdateState.AVAILABLE)
        s = transition(s, UpdateState.DOWNLOADING)
        s = transition(s, UpdateState.DOWNLOADED)
        s = transition(s, UpdateState.VERIFYING)
        s = transition(s, UpdateState.READY_TO_INSTALL)
        s = transition(s, UpdateState.BACKING_UP)
        s = transition(s, UpdateState.INSTALLING)
        self.assertEqual(s, UpdateState.INSTALLING)

    def test_invalid_transition(self):
        with self.assertRaises(ValueError):
            transition(UpdateState.IDLE, UpdateState.INSTALLING)

    def test_failed_to_idle(self):
        self.assertTrue(can_transition(UpdateState.FAILED, UpdateState.IDLE))


class ManifestConfigTests(unittest.TestCase):
    def test_refresh_url_from_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            patcher = patch("desktop.runtime.update.state_store.data_dir", return_value=data)
            patcher.start()
            self.addCleanup(patcher.stop)
            cfg_path = data / "updates" / "updates-config.json"
            cfg_path.parent.mkdir(parents=True)
            cfg_path.write_text(
                json.dumps({"manifestUrl": "file:///C:/test/latest.local.json"}),
                encoding="utf-8",
            )
            provider = UpdateManifestProvider(manifest_url="https://old.example/latest.json")
            url = provider.refresh_url()
            self.assertEqual(url, "file:///C:/test/latest.local.json")

    def test_empty_manifest_url_falls_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            patcher = patch("desktop.runtime.update.state_store.data_dir", return_value=data)
            patcher.start()
            self.addCleanup(patcher.stop)
            # Isolate from the repo's version.json: app_root must not provide one.
            root_patcher = patch("desktop.runtime.update.manifest_provider.app_root", return_value=data)
            root_patcher.start()
            self.addCleanup(root_patcher.stop)
            provider = UpdateManifestProvider()
            self.assertEqual(
                provider.refresh_url(),
                "https://releases.moovingpaper.com/vanova/latest.json",
            )



class ChecksumTests(unittest.TestCase):
    def test_sha256(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"maios-test")
            path = Path(f.name)
        digest = UpdateDownloader.sha256(path)
        path.unlink(missing_ok=True)
        self.assertEqual(len(digest), 64)


class UpdateDetectionTests(unittest.TestCase):
    def test_100_to_101_available(self):
        provider = UpdateManifestProvider()
        manifest = UpdateManifest(
            version="1.0.1",
            download_url="https://releases.moovingpaper.com/vanova/VANOVA-Setup-1.0.1.exe",
            sha256="0a4a7c7a897c13f01c26905a3443e2af958261d0208df7f2a4e98479225d4f44",
            size=92721732,
        )
        self.assertTrue(provider.is_update_available("1.0.0", manifest))
        self.assertFalse(provider.is_update_available("1.0.1", manifest))

    def test_101_to_102_available(self):
        provider = UpdateManifestProvider()
        latest = ROOT / "release" / "latest.json"
        if not latest.exists():
            self.skipTest("release/latest.json not present")
        data = json.loads(latest.read_text(encoding="utf-8"))
        if data["version"] != "1.0.2":
            self.skipTest("latest.json not yet at 1.0.2")
        manifest = UpdateManifest(
            version=data["version"],
            download_url=data["downloadUrl"],
            sha256=data["sha256"],
            size=data["size"],
        )
        self.assertTrue(provider.is_update_available("1.0.1", manifest))
        self.assertFalse(provider.is_update_available("1.0.2", manifest))

    def test_latest_json_102_fields(self):
        latest = ROOT / "release" / "latest.json"
        if not latest.exists():
            self.skipTest("release/latest.json not present")
        data = json.loads(latest.read_text(encoding="utf-8"))
        expected = json.loads((ROOT / "version.json").read_text(encoding="utf-8-sig"))["version"]
        self.assertEqual(data["version"], expected)
        self.assertEqual(len(data["sha256"]), 64)
        self.assertGreater(data["size"], 0)
        self.assertIn(f"VANOVA-Setup-{expected}.exe", data["downloadUrl"])
        self.assertEqual(data.get("dbSchemaVersion"), 0)

    def test_latest_json_101_baseline_fields(self):
        """Frozen 1.0.1 baseline manifest (release/baseline/) for upgrade-path tests."""
        baseline = ROOT / "release" / "baseline" / "latest-1.0.1.json"
        if not baseline.exists():
            self.skipTest("release/baseline/latest-1.0.1.json not present")
        data = json.loads(baseline.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "1.0.1")
        self.assertIn("VANOVA-Setup-1.0.1.exe", data["downloadUrl"])


class PostponeTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data = Path(self._tmpdir.name)
        patcher = patch("desktop.runtime.update.state_store.data_dir", return_value=self.data)
        self.addCleanup(patcher.stop)
        patcher.start()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_force_check_overrides_postpone(self):
        """A manual check (force=True) must clear a previous postponement and
        surface the available update — this is the 'Buscar actualizaciones'
        button behavior (regression: user pressed search and nothing happened)."""
        mgr = UpdateManager()
        manifest = UpdateManifest(
            version="1.0.2",
            download_url="local:release/VANOVA-Setup-1.0.2.exe",
            sha256="b" * 64,
            size=100,
        )
        until = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        cfg_path = self.data / "updates" / "updates-config.json"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text(
            json.dumps({
                "postponedVersion": "1.0.2",
                "postponedUntil": until,
                "lastCheck": None,
            }),
            encoding="utf-8",
        )
        with patch.object(mgr.provider, "fetch", return_value=manifest):
            with patch("desktop.runtime.updater.current_version", return_value="1.0.1"):
                r = mgr.check_for_updates(force=True)
        self.assertFalse(r.get("postponed"))
        self.assertTrue(r.get("updateAvailable"))
        self.assertEqual(r["state"], UpdateState.AVAILABLE.value)
        self.assertEqual(r.get("targetVersion"), "1.0.2")
        cfg = state_store.load_config()
        self.assertIsNone(cfg.get("postponedVersion"))
        self.assertIsNone(cfg.get("postponedUntil"))

    def test_auto_check_still_honors_postpone(self):
        """Non-forced checks (startup / periodic) keep honoring the postpone so
        a 'Más tarde' deferral is not immediately overridden in the background."""
        mgr = UpdateManager()
        manifest = UpdateManifest(
            version="1.0.1",
            download_url="local:release/VANOVA-Setup-1.0.1.exe",
            sha256="a" * 64,
            size=100,
        )
        until = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        cfg_path = self.data / "updates" / "updates-config.json"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text(
            json.dumps({
                "postponedVersion": "1.0.1",
                "postponedUntil": until,
                "lastCheck": None,
            }),
            encoding="utf-8",
        )
        with patch.object(mgr.provider, "fetch", return_value=manifest):
            with patch("desktop.runtime.updater.current_version", return_value="1.0.0"):
                r = mgr.check_for_updates(force=False)
        self.assertTrue(r.get("postponed"))
        self.assertFalse(r.get("updateAvailable"))
        self.assertEqual(r["state"], UpdateState.UP_TO_DATE.value)

    def test_postpone_api(self):
        mgr = UpdateManager()
        state_store.set_state(UpdateState.AVAILABLE, targetVersion="1.0.1")
        r = mgr.postpone_update(version="1.0.1", hours=12)
        self.assertTrue(r.get("ok"))
        cfg = state_store.load_config()
        self.assertEqual(cfg["postponedVersion"], "1.0.1")
        self.assertIsNotNone(cfg["postponedUntil"])


class AutoDownloadTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data = Path(self._tmpdir.name)
        patcher = patch("desktop.runtime.update.state_store.data_dir", return_value=self.data)
        self.addCleanup(patcher.stop)
        patcher.start()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_auto_download_102_triggers_thread(self):
        mgr = UpdateManager()
        cfg_path = self.data / "updates" / "updates-config.json"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text(json.dumps({"autoDownload": True, "lastCheck": None}), encoding="utf-8")
        manifest = UpdateManifest(
            version="1.0.2",
            download_url="local:release/VANOVA-Setup-1.0.2.exe",
            sha256="c" * 64,
            size=100,
        )
        with patch.object(mgr.provider, "fetch", return_value=manifest):
            with patch("desktop.runtime.updater.current_version", return_value="1.0.1"):
                with patch.object(mgr, "download_update") as mock_dl:
                    r = mgr.check_for_updates(force=True)
        self.assertTrue(r.get("updateAvailable"))
        self.assertEqual(r.get("targetVersion"), "1.0.2")
        mock_dl.assert_called_once()

    def test_auto_download_triggers_thread(self):
        mgr = UpdateManager()
        cfg_path = self.data / "updates" / "updates-config.json"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text(json.dumps({"autoDownload": True, "lastCheck": None}), encoding="utf-8")
        manifest = UpdateManifest(
            version="1.0.1",
            download_url="local:release/VANOVA-Setup-1.0.1.exe",
            sha256="a" * 64,
            size=100,
        )
        with patch.object(mgr.provider, "fetch", return_value=manifest):
            with patch("desktop.runtime.updater.current_version", return_value="1.0.0"):
                with patch.object(mgr, "download_update") as mock_dl:
                    r = mgr.check_for_updates(force=True)
        self.assertTrue(r.get("updateAvailable"))
        mock_dl.assert_called_once()


class CheckIntervalTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data = Path(self._tmpdir.name)
        patcher = patch("desktop.runtime.update.state_store.data_dir", return_value=self.data)
        self.addCleanup(patcher.stop)
        patcher.start()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_skips_check_within_interval(self):
        mgr = UpdateManager()
        recent = datetime.now(timezone.utc).isoformat()
        cfg_path = self.data / "updates" / "updates-config.json"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text(
            json.dumps({"lastCheck": recent, "checkIntervalHours": 4, "autoCheck": True}),
            encoding="utf-8",
        )
        with patch("desktop.runtime.updater.current_version", return_value="1.0.0"):
            with patch.object(mgr.provider, "fetch") as mock_fetch:
                r = mgr.check_for_updates(force=False)
                mock_fetch.assert_not_called()
        self.assertTrue(r.get("skippedCheck"))

class StuckStateRecoveryTests(unittest.TestCase):
    """Regresión: VANOVA cerrado durante un check/descarga dejaba la UI en
    'Buscando actualizaciones…' para siempre (spinner infinito). El arranque
    debe resetear los estados transitorios huérfanos a IDLE."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data = Path(self._tmpdir.name)
        patcher = patch("desktop.runtime.update.state_store.data_dir", return_value=self.data)
        self.addCleanup(patcher.stop)
        patcher.start()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write_state(self, state: str):
        st_path = self.data / "updates" / "update-state.json"
        st_path.parent.mkdir(parents=True, exist_ok=True)
        st_path.write_text(json.dumps({"state": state, "installedVersion": "", "message": ""}), encoding="utf-8")

    def test_stale_checking_is_reset_to_idle(self):
        self._write_state(UpdateState.CHECKING.value)
        mgr = UpdateManager()
        r = mgr.startup_recovery()
        self.assertEqual(r.get("state"), UpdateState.IDLE.value)
        self.assertIn("interrumpida", r.get("message", ""))
        st = state_store.load_state()
        self.assertEqual(st.get("state"), UpdateState.IDLE.value)

    def test_stale_downloading_is_reset_to_idle(self):
        self._write_state(UpdateState.DOWNLOADING.value)
        mgr = UpdateManager()
        r = mgr.startup_recovery()
        self.assertEqual(r.get("state"), UpdateState.IDLE.value)

    def test_stale_verifying_is_reset_to_idle(self):
        self._write_state(UpdateState.VERIFYING.value)
        mgr = UpdateManager()
        r = mgr.startup_recovery()
        self.assertEqual(r.get("state"), UpdateState.IDLE.value)

    def test_idle_state_is_left_alone(self):
        self._write_state(UpdateState.IDLE.value)
        mgr = UpdateManager()
        r = mgr.startup_recovery()
        self.assertEqual(r.get("state"), UpdateState.IDLE.value)


class ManifestDeadlineTests(unittest.TestCase):
    """Regresión: un fetch colgado (DNS que ignora el timeout de socket) no debe
    dejar el check sin respuesta. _fetch_manifest_with_deadline debe abortar
    dentro del deadline y propagar TimeoutError."""

    def test_fetch_hang_raises_timeout(self):
        def hang():
            import time

            time.sleep(30)
            raise AssertionError("no debería llegar aquí")

        mgr = UpdateManager()
        mgr.provider.fetch = hang
        t0 = datetime.now()
        with self.assertRaises(TimeoutError):
            mgr._fetch_manifest_with_deadline(timeout=1.0)
        elapsed = (datetime.now() - t0).total_seconds()
        self.assertLess(elapsed, 10, "el deadline debe abortar, no esperar al hilo colgado")

    def test_fast_fetch_returns_manifest(self):
        manifest = UpdateManifest(
            version="1.0.1",
            download_url="https://releases.moovingpaper.com/vanova/VANOVA-Setup-1.0.1.exe",
            sha256="0a4a7c7a897c13f01c26905a3443e2af958261d0208df7f2a4e98479225d4f44",
            size=92721732,
        )
        mgr = UpdateManager()
        mgr.provider.fetch = lambda: manifest
        result = mgr._fetch_manifest_with_deadline(timeout=5.0)
        self.assertEqual(result.version, "1.0.1")


if __name__ == "__main__":
    unittest.main()
