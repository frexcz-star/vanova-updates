"""BUG-038 — RMW atómico en business_scanner (_save_scan_files/_save_candidates).

Root cause: ambas hacían load() → construir lista merged → config_store.save({...})
SOBRESCRIBIENDO la lista completa. Si un hilo concurrente (decideFileCandidate del
usuario, scan doble, import) modificaba scanFiles/fileCandidates entre el load y
el save, se perdían escrituras (lost-update, patrón BUG-006/015/019/023/034/037).

Fix: usar config_store.update(_mutate) que hace el RMW dentro del _config_lock,
sin sobrescribir datos escritos por otros hilos.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import config_store
from desktop.runtime.business_scanner import _save_candidates, _save_scan_files


def _file(path, **kw):
    d = {"path": path, "name": path.split("/")[-1], "ext": "csv", "size": 10, "modified": "2026-01-01T00:00:00Z"}
    d.update(kw)
    return d


class Bug038AtomicScannerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self._config_patch = patch.object(config_store, "CONFIG_FILE", Path(tmp) / "maios.json")
        self._config_patch.start()
        self.addCleanup(self._config_patch.stop)
        config_store.save({})

    def test_save_scan_files_uses_update_not_save(self):
        with patch.object(config_store, "save", wraps=config_store.save) as mock_save, \
             patch.object(config_store, "update", wraps=config_store.update) as mock_update:
            _save_scan_files([_file("/c.csv")])
        mock_update.assert_called_once()
        cfg = config_store.load()
        self.assertEqual([f["path"] for f in cfg.get("scanFiles", [])], ["/c.csv"])

    def test_save_scan_files_preserves_user_files_and_concurrent_add(self):
        """Un archivo userAdded existente no se pierde, y uno añadido durante el RMW se conserva."""
        _save_scan_files([_file("/imported.csv", source="import")])
        _save_scan_files([_file("/new.csv")])
        cfg = config_store.load()
        paths = {f["path"] for f in cfg.get("scanFiles", [])}
        self.assertIn("/imported.csv", paths)   # se preserva el import
        self.assertIn("/new.csv", paths)        # se añade el nuevo

    def test_save_candidates_uses_update_and_preserves_decided(self):
        """Un candidato ya decidido no se re-superficia; update() se usa."""
        _save_candidates([_file("/a.csv")])
        # Simular que el usuario decidió /a.csv (se escribe en el config real)
        def _mark_decided(cfg):
            for c in cfg.get("fileCandidates", []):
                if c.get("path") == "/a.csv":
                    c["decision"] = "approved"
            return cfg
        config_store.update(_mark_decided)
        # Nuevo scan con /a.csv + /b.csv
        _save_candidates([_file("/a.csv"), _file("/b.csv")])
        cfg = config_store.load()
        cands = cfg.get("fileCandidates", [])
        paths = {c["path"] for c in cands}
        self.assertIn("/b.csv", paths)          # nuevo candidato
        self.assertNotIn("/a.csv", paths)       # ya decidido, no se re-supera


if __name__ == "__main__":
    unittest.main()
