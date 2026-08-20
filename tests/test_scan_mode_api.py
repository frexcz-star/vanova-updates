"""Escaneo seguro — decisión explícita conservar/limpiar antes de escanear.

Cubre la lógica del runtime: mode=keep (por defecto, no borra nada) vs
mode=clean (backup + limpieza del estado empresarial + escaneo), y que
jamás se tocan archivos físicos del PC.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime.api_server import Handler  # noqa: E402


class ScanModeApiTests(unittest.TestCase):
    def test_mode_clean_is_detected(self):
        h = Handler.__new__(Handler)
        self.assertTrue(h._scan_mode_clean({"mode": "clean"}))
        self.assertTrue(h._scan_mode_clean({"mode": "CLEAN"}))
        self.assertTrue(h._scan_mode_clean({"mode": "wipe"}))
        self.assertFalse(h._scan_mode_clean({}))
        self.assertFalse(h._scan_mode_clean({"mode": "keep"}))
        self.assertFalse(h._scan_mode_clean({"mode": "conservar"}))

    def test_clean_then_scan_wipes_with_backup_then_starts_scan(self):
        h = Handler.__new__(Handler)
        cleared = {"ok": True, "backupPath": "/tmp/bk"}
        started = {"ok": True, "started": True}
        fake_modules = {
            "data_governance": type("DG", (), {
                "clear_business_data": staticmethod(lambda confirmed=True: cleared),
            })(),
            "business_scanner": type("BS", (), {
                "run_scan_async": staticmethod(lambda: started),
            })(),
        }
        with patch("desktop.runtime.api_server._require",
                   side_effect=lambda name: fake_modules[name]):
            result = h._clean_then_scan()
        self.assertTrue(result["ok"])
        self.assertTrue(result["cleaned"])
        self.assertEqual(result["backupPath"], "/tmp/bk")
        self.assertEqual(result["scan"], started)

    def test_clean_then_scan_aborts_if_clean_fails(self):
        h = Handler.__new__(Handler)
        cleared = {"ok": False, "error": "El backup previo falló"}
        fake_modules = {
            "data_governance": type("DG", (), {
                "clear_business_data": staticmethod(lambda confirmed=True: cleared),
            })(),
        }
        with patch("desktop.runtime.api_server._require",
                   side_effect=lambda name: fake_modules[name]):
            result = h._clean_then_scan()
        self.assertFalse(result["ok"])
        self.assertIn("backup", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
