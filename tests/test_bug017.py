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


if __name__ == "__main__":
    unittest.main()
