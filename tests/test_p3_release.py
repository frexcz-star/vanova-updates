"""P3 release hardening tests (Phases 26–33)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import (
    backup_service,
    diagnostics_service,
    integrations_lifecycle,
    observability,
    runtime_security,
)
from desktop.runtime.update import backup as update_backup


class ObservabilityTests(unittest.TestCase):
    def test_correlation_bind_and_read(self):
        observability.clear_correlation()
        cid = observability.bind_correlation()
        self.assertTrue(len(cid) >= 8)
        self.assertEqual(observability.get_correlation_id(), cid)
        observability.clear_correlation()
        self.assertIsNone(observability.get_correlation_id())


class BackupServiceTests(unittest.TestCase):
    def test_run_backup_creates_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "cfg" / "maios.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text("{}", encoding="utf-8")
            with patch.object(backup_service, "BACKUP_ROOT", root / "backups"):
                with patch.object(backup_service, "_prune_old_backups"):
                    with patch("desktop.runtime.config_store.CONFIG_FILE", cfg):
                        result = backup_service.run_backup(reason="test")
            self.assertTrue(result.get("ok"))
            self.assertTrue(any((root / "backups").iterdir()))

    def test_database_health_shape(self):
        rows = backup_service.database_health()
        self.assertTrue(any(r["id"] == "config" for r in rows))


class PreUpdateBackupTests(unittest.TestCase):
    def test_pre_update_backup_contains_all_normalized_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "config"
            cfg.mkdir(parents=True)
            cfg_file = cfg / "maios.json"
            cfg_file.write_text(
                '{"organizedProducts": [{"sku": "A1"}], "organizedSales": [{"id": "O1"}]}',
                encoding="utf-8",
            )
            (root / "insight-actions.json").write_text('{"i-1": "important"}', encoding="utf-8")
            with patch.object(update_backup, "data_dir", return_value=root), patch.object(
                update_backup, "config_dir", return_value=cfg
            ):
                folder = update_backup.create_backup("2.0.13")
                manifest = json.loads((folder / "backup-manifest.json").read_text(encoding="utf-8"))
                self.assertTrue((folder / "config" / "maios.json").exists())
                self.assertTrue((folder / "data" / "insight-actions.json").exists())
                self.assertEqual(manifest["dataSummary"]["organizedProducts"], 1)

    def test_pre_update_restore_keeps_recovery_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "config"
            cfg.mkdir(parents=True)
            cfg_file = cfg / "maios.json"
            cfg_file.write_text('{"organizedProducts": [{"sku": "GOOD"}]}', encoding="utf-8")
            with patch.object(update_backup, "data_dir", return_value=root), patch.object(
                update_backup, "config_dir", return_value=cfg
            ):
                folder = update_backup.create_backup("2.0.13")
                cfg_file.write_text('{"organizedProducts": []}', encoding="utf-8")
                self.assertTrue(update_backup.restore_backup(folder))
                restored = json.loads(cfg_file.read_text(encoding="utf-8"))
                self.assertEqual(restored["organizedProducts"][0]["sku"], "GOOD")


class DiagnosticsTests(unittest.TestCase):
    def test_run_diagnostics_has_checks(self):
        diag = diagnostics_service.run_diagnostics()
        self.assertIn("checks", diag)
        self.assertIn("overall", diag)
        self.assertGreaterEqual(len(diag["checks"]), 5)

    def test_diagnostics_routes_allowed(self):
        self.assertIn("/api/diagnostics", runtime_security.READ_GET_PATHS)
        self.assertIn("/api/backups/status", runtime_security.READ_GET_PATHS)
        self.assertIn("/api/backups/run", runtime_security.MUTATION_POST_PATHS)
        self.assertIn("/api/backups/restore", runtime_security.MUTATION_POST_PATHS)


class ShopifyLifecycleTests(unittest.TestCase):
    def test_disconnected_state(self):
        with patch("desktop.runtime.integrations_lifecycle.integrations_store.get_config", return_value={"connected": False}):
            with patch("desktop.runtime.integrations_lifecycle.shopify_sync.sync_status", return_value={"status": "idle"}):
                lc = integrations_lifecycle.shopify_lifecycle()
        self.assertEqual(lc["state"], "disconnected")
        self.assertIn("connect", lc["actions"])

    def test_lifecycle_route(self):
        self.assertIn("/api/integrations/lifecycle", runtime_security.READ_GET_PATHS)


if __name__ == "__main__":
    unittest.main()
