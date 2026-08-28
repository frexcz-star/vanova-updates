"""BUG-070: copy en inglés visible en system-status.js ("Correlation ID").

Regla de UI: textos en español. El diagnóstico mostraba "Correlation ID:" en
inglés. Fix: renombrado a "ID de correlación:".

Estos tests FALLAN con el código anterior (inglés) y PASAN con el fix.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYSTEM_STATUS = ROOT / "web" / "system-status.js"


class Bug070SpanishUISystemStatusTests(unittest.TestCase):
    def test_no_copy_ingles_correlation(self):
        src = SYSTEM_STATUS.read_text(encoding="utf-8")
        self.assertNotIn("Correlation ID", src, "copy en inglés 'Correlation ID' visible")
        self.assertIn("ID de correlación", src, "'ID de correlación' en español ausente")

    def test_textos_diagnostico_espanol(self):
        src = SYSTEM_STATUS.read_text(encoding="utf-8")
        # Textos de UI del diagnóstico deben estar en español.
        self.assertIn("Runtime no disponible", src)
        self.assertIn("Estado de conexiones", src)


if __name__ == "__main__":
    unittest.main()
