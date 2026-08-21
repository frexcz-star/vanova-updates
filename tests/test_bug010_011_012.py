"""Regression tests para BUG-010/011/012 (RMW atómico + retention de snapshots)."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloud import main as cm  # noqa: E402


class Bug010SnapshotRetentionTests(unittest.TestCase):
    """BUG-010 (HIGH, Cloud): la tabla `snapshots` no debe crecer sin límite."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_cloud.db"
        # Aislar la conexión de DB: patch de get_db a una conexión en el archivo
        # temporal, para NO tocar maios_cloud.db de producción.
        def _fake_get_db():
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            conn.row_factory = sqlite3.Row
            return conn

        self._get_db_patcher = patch.object(cm, "get_db", side_effect=_fake_get_db)
        self._get_db_patcher.start()
        # Inicializar el esquema creando las tablas vía la función real parcheada
        conn = cm.get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                workspace_id TEXT, kind TEXT, data TEXT, ts TEXT
            );
        """)
        conn.close()

    def tearDown(self):
        self._get_db_patcher.stop()
        self.tmp.cleanup()

    def _count(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
            return conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        finally:
            conn.close()

    def test_bug010_snapshots_pruned_to_retention(self):
        """Tras insertar muchos snapshots, solo quedan SNAPSHOT_RETENTION por (ws, kind)."""
        cm.store_snapshot("ws-1", "dashboard", {"data": 1})
        cm.store_snapshot("ws-1", "dashboard", {"data": 2})
        # Insertar más de la retention
        for i in range(cm.SNAPSHOT_RETENTION + 20):
            cm.store_snapshot("ws-1", "dashboard", {"i": i})
        self.assertLessEqual(self._count(), cm.SNAPSHOT_RETENTION)
        # Los SELECT usan ORDER BY rowid DESC LIMIT 1: debe devolver el último
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT data FROM snapshots WHERE workspace_id=? AND kind='dashboard' ORDER BY rowid DESC LIMIT 1",
            ("ws-1",),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        payload = json.loads(row["data"])
        # El más reciente es el último insertado
        self.assertEqual(payload["i"], cm.SNAPSHOT_RETENTION + 19)

    def test_bug010_different_kinds_kept_separate(self):
        cm.store_snapshot("ws-1", "dashboard", {"k": "d"})
        cm.store_snapshot("ws-1", "products", {"k": "p"})
        self.assertEqual(self._count(), 2)


class Bug011HermesActivityAtomicTests(unittest.TestCase):
    """BUG-011 (MEDIUM): log_step debe usar RMW atómico (config_store.update)."""

    def setUp(self):
        from desktop.runtime import config_store

        self.tmp = tempfile.TemporaryDirectory()
        self.config_file = Path(self.tmp.name) / "maios.json"
        self.config_patcher = patch.object(config_store, "CONFIG_FILE", self.config_file)
        self.config_patcher.start()
        # Iniciar con un config en disco
        config_store.save({"setupComplete": True})

    def tearDown(self):
        self.config_patcher.stop()
        self.tmp.cleanup()

    def test_bug011_log_step_uses_atomic_update(self):
        from desktop.runtime import config_store, hermes_activity

        # update() debe ser invocado (no save() directo del RMW no atómico)
        with patch.object(
            config_store, "update", side_effect=lambda mutator: mutator(config_store.load())
        ) as mock_update:
            hermes_activity.log_step("paso A", step="info", source="hermes")
        mock_update.assert_called_once()

    def test_bug011_log_accumulates_and_trims(self):
        from desktop.runtime import hermes_activity

        for i in range(hermes_activity.MAX_LOG + 5):
            hermes_activity.log_step(f"paso {i}", step="info", source="hermes")
        cur = hermes_activity.current()
        self.assertEqual(len(cur.get("log") or []), hermes_activity.MAX_LOG)


class Bug012AddProductAtomicTests(unittest.TestCase):
    """BUG-012 (MEDIUM): file_organizer.add_product debe usar RMW atómico."""

    def setUp(self):
        from desktop.runtime import config_store

        self.tmp = tempfile.TemporaryDirectory()
        self.config_file = Path(self.tmp.name) / "maios.json"
        self.config_patcher = patch.object(config_store, "CONFIG_FILE", self.config_file)
        self.config_patcher.start()
        config_store.save({"organizedProducts": []})

    def tearDown(self):
        self.config_patcher.stop()
        self.tmp.cleanup()

    def test_bug012_add_product_uses_atomic_update(self):
        from desktop.runtime import config_store, file_organizer

        with patch.object(
            config_store, "update", side_effect=lambda mutator: mutator(config_store.load())
        ) as mock_update, patch.object(
            file_organizer, "sync_dashboard_overview", return_value=None
        ):
            r = file_organizer.add_product({"name": "Producto A", "sku": "SKU-A", "netPrice": 10, "rrp": 15})
        self.assertTrue(r["ok"])
        mock_update.assert_called_once()
        self.assertEqual(r["count"], 1)

    def test_bug012_add_product_persists(self):
        from desktop.runtime import config_store, file_organizer

        file_organizer.add_product({"name": "Prod 1", "sku": "S1"})
        file_organizer.add_product({"name": "Prod 2", "sku": "S2"})
        data = config_store.load()
        skus = [p.get("sku") for p in data.get("organizedProducts", [])]
        self.assertIn("S1", skus)
        self.assertIn("S2", skus)


if __name__ == "__main__":
    unittest.main()
