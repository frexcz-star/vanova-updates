"""Regression tests — BUG-017 (RMW atómico en file_inventory).

Los mutadores de scanFiles/fileCandidates deben usar config_store.update()
(RMW atómico bajo un solo lock), no load() → modificar → save() que pierde
escrituras concurrentes.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import config_store, file_inventory  # noqa: E402


class Bug017FileInventoryAtomicTests(unittest.TestCase):
    def test_add_imported_file_uses_atomic_update(self):
        stored = {"scanFiles": []}
        with patch.object(config_store, "load", return_value=stored), patch.object(
            config_store, "update", side_effect=lambda mutator: mutator(stored)
        ) as mock_update, patch.object(file_inventory, "_organize_after_import", return_value=None):
            r = file_inventory.add_imported_file({"name": "a.csv", "ext": "csv", "path": "a.csv"})
        self.assertTrue(r["ok"])
        mock_update.assert_called_once()
        self.assertEqual(r["count"], 1)

    def test_remove_imported_file_uses_atomic_update(self):
        stored = {"scanFiles": [{"path": "a.csv", "name": "a.csv"}]}
        with patch.object(config_store, "load", return_value=stored), patch.object(
            config_store, "update", side_effect=lambda mutator: mutator(stored)
        ) as mock_update, patch.object(file_inventory, "_organize_after_import", return_value=None):
            r = file_inventory.remove_imported_file("a.csv")
        self.assertTrue(r["ok"])
        mock_update.assert_called_once()
        self.assertEqual(r["count"], 0)

    def test_decide_candidate_uses_atomic_update(self):
        cand = {"path": "C:/x.csv", "status": "pending"}
        stored = {"fileCandidates": [dict(cand)], "scanFiles": []}
        with patch.object(config_store, "load", return_value=stored), patch.object(
            config_store, "update", side_effect=lambda mutator: mutator(stored)
        ) as mock_update, patch.object(file_inventory, "_organize_after_import", return_value=None):
            r = file_inventory.decide_candidate("C:/x.csv", approve=True)
        self.assertTrue(r["ok"])
        # approve=True escribe fileCandidates Y scanFiles → 2 updates atómicos
        self.assertEqual(mock_update.call_count, 2)
        self.assertEqual(stored["fileCandidates"][0]["status"], "approved")


class Bug028FileRemovalPersistsTests(unittest.TestCase):
    """BUG-028: eliminar un archivo en la vista Archivos debe persistir tras
    reiniciar. La causa raíz era que remove_imported_file solo lo quitaba de
    scanFiles, pero un scan futuro lo reintroducía del disco. Fix: registrar la
    exclusión en scanExclusions Y que _scan_files la respete."""

    def test_remove_adds_exclusion(self):
        stored = {"scanFiles": [{"path": "C:/empresa/a.csv", "name": "a.csv"}], "scanExclusions": []}
        with patch.object(config_store, "load", return_value=stored), patch.object(
            config_store, "update", side_effect=lambda mutator: mutator(stored)
        ), patch.object(file_inventory, "_organize_after_import", return_value=None):
            r = file_inventory.remove_imported_file("C:/empresa/a.csv")
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 0)
        self.assertIn("C:/empresa/a.csv", stored["scanExclusions"])

    def test_scan_skips_excluded_files(self):
        from desktop.runtime import business_scanner
        stored = {"scanFiles": [], "scanExclusions": ["C:/empresa/eliminado.csv"]}
        with patch.object(config_store, "load", return_value=stored):
            found = business_scanner._scan_files(0)
        self.assertEqual(found, [])


class Bug032FileExclusionsExposedTests(unittest.TestCase):
    """BUG-032: la vista Archivos mezcla cloud+runtime y, si el sync cloud de
    removeFile falla (best-effort), el snapshot cloud reintroduce el archivo
    eliminado. El fix: list_imported_files expone las scanExclusions para que
    el frontend las filtre. Este test verifica que las exclusiones se exponen.
    Fallaría sin el fix (sin el campo `excluded`)."""

    def test_list_exposes_exclusions(self):
        stored = {
            "scanFiles": [{"path": "C:/empresa/a.csv", "name": "a.csv"}],
            "scanExclusions": ["C:/empresa/borrado.csv", "C:/empresa/a.csv"],
        }
        with patch.object(config_store, "load", return_value=stored):
            r = file_inventory.list_imported_files()
        self.assertIn("excluded", r)
        self.assertIn("C:/empresa/borrado.csv", r["excluded"])
        self.assertIn("C:/empresa/a.csv", r["excluded"])
        self.assertEqual(r["excludedCount"], 2)


if __name__ == "__main__":
    unittest.main()
