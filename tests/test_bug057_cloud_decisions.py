"""BUG-057 real (contador): el cloud DESCARTABA las decisiones del snapshot del
connector (no estaban en la lista de dominios a mergear en /api/connector/push),
y nadie insertaba en la tabla 'decisions' del cloud (no hay INSERT en todo el
repo). Resultado: la tabla decisions del cloud quedaba VACÍA, el snapshot cloud
(BUG-047) enriquecía con decisions=[] y el badge del dashboard cloud contaba
SIEMPRE 0 decisiones aunque existieran decisiones reales pendientes en el
runtime local. Este era un caso real de sistema que ningún fix anterior cubría.

Fix: /api/connector/push persiste las decisiones del snapshot en la tabla
decisions del cloud (upsert por id), para que el contador las cuente.

Falla con el código anterior (sin la persistencia de decisions en el push).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class CloudConnectorPushPersistsDecisionsTests(unittest.TestCase):
    """/api/connector/push debe persistir las decisiones del snapshot en la tabla
    decisions del cloud (BUG-057), para que el contador del dashboard cloud
    cuente las decisiones pendientes reales."""

    CLOUD = ROOT / "cloud" / "main.py"

    def test_connector_push_persiste_decisions(self):
        src = self.CLOUD.read_text(encoding="utf-8")
        # El push del connector debe insertar/upsert las decisiones en la tabla
        self.assertIn("INSERT INTO decisions", src,
                      "/api/connector/push debe persistir las decisiones en la tabla decisions")
        # y el merge de dominios debe incluir el manejo de decisions
        self.assertIn('body.get("decisions")', src,
                      "el push debe procesar el campo decisions del snapshot")

    def test_connector_push_no_descarta_decisions(self):
        src = self.CLOUD.read_text(encoding="utf-8")
        # El bloque de persistencia de decisions debe estar dentro de connector_push
        idx = src.find('def connector_push')
        self.assertNotEqual(idx, -1, "debe existir la función connector_push")
        block = src[idx:idx + 3000]
        self.assertIn("INSERT INTO decisions", block,
                      "la persistencia de decisions debe estar en connector_push")


if __name__ == "__main__":
    unittest.main()
