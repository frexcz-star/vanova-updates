"""BUG-058 (Mathew): _organize_after_scan silenciaba los fallos de
file_organizer.organize_files() con try/except Exception que solo logueaba
warning. Resultado: el scan reportaba éxito pero el catálogo NO se actualizaba
(bug 3 de Nico: "archivos escaneados no actualizan el catálogo").

Fix: el error se PROPAGA (sin silenciarlo) para que el scan (_run) lo marque
como 'error' y se exponga en la UI / scanStatus.

Falla con el código anterior (que silenciaba la excepción).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class OrganizeAfterScanNotSilencedTests(unittest.TestCase):
    """_organize_after_scan debe propagar el error de organize_files (BUG-058)."""

    def test_organize_after_scan_no_tiene_except_silencioso(self):
        # El cuerpo de _organize_after_scan NO debe envolver organize_files() en
        # try/except Exception que silencie el fallo.
        src = (ROOT / "desktop" / "runtime" / "business_scanner.py").read_text(encoding="utf-8")
        idx = src.find("def _organize_after_scan")
        self.assertNotEqual(idx, -1)
        block = src[idx:src.find("def _now()", idx)]
        # NO debe contener log.warning del fallo silenciado
        self.assertNotIn("log.warning(\"Post-scan file organization failed", block,
                         "_organize_after_scan no debe silenciar el fallo con log.warning")
        # Debe llamar a organize_files directamente
        self.assertIn("file_organizer.organize_files()", block,
                      "_organize_after_scan debe llamar a organize_files")

    def test_organize_after_scan_se_llama_en_run(self):
        # _run debe llamar a _organize_after_scan en el flujo del scan
        src = (ROOT / "desktop" / "runtime" / "business_scanner.py").read_text(encoding="utf-8")
        self.assertIn("_organize_after_scan()", src,
                      "_run debe llamar a _organize_after_scan tras guardar resultados")


if __name__ == "__main__":
    unittest.main()
