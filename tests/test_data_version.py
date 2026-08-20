"""VANOVA 2.0.26-beta.3 — post-update data validation.

Cubre el flujo completo:
  * instalación nueva sin datos → no hay aviso;
  * datos importados con una versión anterior → aviso needsReview;
  * "Ahora no" → no reaparece para esa versión;
  * rearm → el aviso vuelve a mostrarse si sigue siendo debido;
  * reimportación idempotente: organizar dos veces no duplica;
  * stamp_import registra versión + conteos.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import config_store, data_version  # noqa: E402


class DataVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.config_file = base / "config" / "maios.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(json.dumps({}), encoding="utf-8")

        self.config_patcher = patch.object(config_store, "CONFIG_FILE", self.config_file)
        self.config_patcher.start()
        self.version_patcher = patch.object(
            data_version, "current_app_version", return_value="2.0.26-beta.3"
        )
        self.version_patcher.start()

    def tearDown(self):
        self.version_patcher.stop()
        self.config_patcher.stop()
        self.tmp.cleanup()

    def _write_business_data(self, products=2, sales=3):
        self.config_file.write_text(
            json.dumps(
                {
                    "organizedProducts": [{"id": f"p{i}", "name": f"Prod {i}"} for i in range(products)],
                    "organizedSales": [{"id": f"s{i}", "total": 10.0} for i in range(sales)],
                }
            ),
            encoding="utf-8",
        )

    def test_clean_install_no_notice(self):
        st = data_version.status()
        self.assertFalse(st["hasData"])
        self.assertFalse(st["needsReview"])

    def test_data_from_previous_version_triggers_review(self):
        self._write_business_data()
        data_version.stamp_import(source="files", counts={"products": 2, "sales": 3})
        # Simulate an update: app version changes
        with patch.object(data_version, "current_app_version", return_value="2.0.27.0"):
            st = data_version.status()
        self.assertTrue(st["hasData"])
        self.assertEqual(st["storedVersion"], "2.0.26-beta.3")
        self.assertEqual(st["currentVersion"], "2.0.27.0")
        self.assertTrue(st["needsReview"])

    def test_same_version_no_notice(self):
        self._write_business_data()
        data_version.stamp_import(source="files", counts={"products": 2})
        st = data_version.status()
        self.assertFalse(st["needsReview"])

    def test_dismiss_hides_notice_for_that_version(self):
        self._write_business_data()
        data_version.stamp_import(source="files")
        with patch.object(data_version, "current_app_version", return_value="2.0.27.0"):
            self.assertTrue(data_version.status()["needsReview"])
            st = data_version.dismiss()
            self.assertFalse(st["needsReview"])
            self.assertTrue(st["dismissed"])
            # Repeated status calls stay quiet
            self.assertFalse(data_version.status()["needsReview"])

    def test_rearm_reshows_notice(self):
        self._write_business_data()
        data_version.stamp_import(source="files")
        with patch.object(data_version, "current_app_version", return_value="2.0.27.0"):
            data_version.dismiss()
            self.assertFalse(data_version.status()["needsReview"])
            st = data_version.rearm()
            self.assertTrue(st["needsReview"])

    def test_stamp_records_counts_and_source(self):
        self._write_business_data()
        rec = data_version.stamp_import(source="shopify", counts={"products": 2, "sales": 3})
        self.assertEqual(rec["version"], "2.0.26-beta.3")
        self.assertEqual(rec["source"], "shopify")
        self.assertEqual(rec["counts"]["products"], 2)
        self.assertIsNone(rec["dismissedFor"])

    def test_fresh_import_clears_dismissal(self):
        self._write_business_data()
        data_version.stamp_import(source="files")
        data_version.dismiss()
        # Re-import with the same version clears the notice
        data_version.stamp_import(source="files")
        st = data_version.status()
        self.assertFalse(st["needsReview"])
        self.assertFalse(st["dismissed"])


class IdempotentReimportTests(unittest.TestCase):
    """organize_files twice must not duplicate persisted rows."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.config_file = base / "config" / "maios.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_patcher = patch.object(config_store, "CONFIG_FILE", self.config_file)
        self.config_patcher.start()
        self.version_patcher = patch.object(
            data_version, "current_app_version", return_value="2.0.26-beta.3"
        )
        self.version_patcher.start()

    def tearDown(self):
        self.version_patcher.stop()
        self.config_patcher.stop()
        self.tmp.cleanup()

    def test_organize_twice_is_idempotent(self):
        from desktop.runtime import file_organizer as fo

        files = [
            {"path": "productos.xlsx", "name": "productos.xlsx", "category": "products"},
            {"path": "ventas.csv", "name": "ventas.csv", "category": "sales"},
        ]
        with patch.object(fo.config_store, "load", return_value={"scanFiles": files}), patch.object(
            fo.config_store, "save", side_effect=lambda d: _save(d, self.config_file)
        ):
            # First run
            with patch.object(fo, "_extract_products", return_value=[{"sku": "A1", "name": "Prod A"}]):
                pass
        # Simpler: call organize_files with files and a real config file
        stored: dict = {}
        with patch.object(
            fo.config_store, "load", side_effect=lambda: dict(stored)
        ), patch.object(fo.config_store, "save", side_effect=lambda d: stored.update(d)):
            with patch.object(fo, "_extract_products", return_value=[{"sku": "A1", "name": "Prod A"}]), patch.object(
                fo, "_extract_sales", return_value=[{"id": "O1", "total": 25.0, "date": "2026-07-01"}]
            ), patch.object(fo, "_extract_customers", return_value=[]):
                r1 = fo.organize_files(files, trigger_hermes=False)
                r2 = fo.organize_files(files, trigger_hermes=False)
        self.assertTrue(r1["ok"])
        self.assertTrue(r2["ok"])
        self.assertEqual(len(stored.get("organizedProducts") or []), 1)
        self.assertEqual(len(stored.get("organizedSales") or []), 1)
        dv = stored.get("dataVersion") or {}
        self.assertEqual(dv.get("version"), "2.0.26-beta.3")
        self.assertEqual(dv.get("counts", {}).get("products"), 1)


class DataVersionHttpEndpointTests(unittest.TestCase):
    """Regression: GET /api/data/version must answer 200 (banner state),
    not 404. The endpoint was originally registered only in do_POST.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.config_file = base / "config" / "maios.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(json.dumps({}), encoding="utf-8")
        self.config_patcher = patch.object(config_store, "CONFIG_FILE", self.config_file)
        self.config_patcher.start()
        self.version_patcher = patch.object(
            data_version, "current_app_version", return_value="2.0.26-beta.3"
        )
        self.version_patcher.start()

    def tearDown(self):
        self.version_patcher.stop()
        self.config_patcher.stop()
        self.tmp.cleanup()

    def test_get_data_version_endpoint(self):
        from desktop.runtime import api_server
        from http.server import BaseHTTPRequestHandler

        captured: dict = {}

        class _Handler(api_server.Handler):
            def _json(self, payload, status=200):
                captured["status"] = status
                captured["body"] = payload
                return None

        handler = _Handler.__new__(_Handler)
        handler.path = "/api/data/version"
        handler.client_address = ("127.0.0.1", 12345)
        handler._bind_request_context = lambda: None
        handler.do_GET()

        self.assertEqual(captured.get("status"), 200)
        body = captured.get("body") or {}
        self.assertIn("hasData", body)
        self.assertIn("needsReview", body)


def _save(d, path):
    path.write_text(json.dumps(d), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
