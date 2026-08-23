"""CAUSA RAÍZ CONTADOR (BUG-036 residual) — las decisiones reales del cloud no
llegaban al badge/drawer.

Hallazgo: el snapshot del Connector (CloudDataSource.get_dashboard) podía traer
decisions=[] aunque hubiera decisiones reales pendientes en la tabla 'decisions'
del cloud. El badge y el drawer cuentan store.decisions, que salía SIEMPRE vacío
-> el contador no reflejaba las decisiones pendientes reales del usuario.

Fix:
1. cloud/main.py CloudDataSource.get_dashboard: enriquece el snapshot con las
   decisiones reales de la tabla 'decisions' del workspace.
2. web/dashboard.html: el badge y el drawer cuentan SOLO decisiones pendientes
   (status='pending'), no todas (aprobadas/rechazadas/resueltas).

Falla con el código anterior (get_dashboard devolvía decisions=[] y el badge
contaba todas las decisiones sin filtrar por pendiente).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class CloudGetDashboardDecisionsTests(unittest.TestCase):
    """CloudDataSource.get_dashboard debe incluir las decisiones reales."""

    def test_get_dashboard_incluye_decisiones_reales(self):
        from cloud import main as cm

        snapshot_json = '{"dataMode":"real","overview":{},"priorities":[],"decisions":[],"sources":[]}'
        real_decisions = [
            {"id": "d1", "title": "Decisión 1", "status": "pending"},
            {"id": "d2", "title": "Decisión 2", "status": "approved"},
        ]

        class FakeRow(dict):
            pass

        class FakeConn:
            # primera llamada = fetchone (snapshot); siguientes = fetchall (decisions)
            def __init__(self):
                self._calls = 0
            def execute(self, *a, **k):
                return self
            def fetchone(self):
                self._calls += 1
                return FakeRow({"data": snapshot_json}) if self._calls == 1 else None
            def fetchall(self):
                self._calls += 1
                return real_decisions if self._calls > 1 else []
            def close(self):
                pass

        conn = FakeConn()
        with patch("cloud.main.get_db", return_value=conn):
            src = cm.CloudDataSource(workspace_id="ws1")
            result = src.get_dashboard()

        # El snapshot se enriquece con las decisiones reales (no [])
        self.assertEqual(len(result["decisions"]), 2, "get_dashboard debe incluir las decisiones reales de la tabla")


class BadgeDecisionFilterTests(unittest.TestCase):
    """El badge y el drawer deben contar SOLO decisiones pendientes."""

    DASH = ROOT / "web" / "dashboard.html"

    def test_badge_filtra_decisiones_pendientes(self):
        html = self.DASH.read_text(encoding="utf-8")
        # El badge filtra por status pending en el conteo de decisiones.
        self.assertIn("(dc.status||'pending') === 'pending'", html, "badge no filtra decisiones pendientes")

    def test_drawer_filtra_decisiones_pendientes(self):
        html = self.DASH.read_text(encoding="utf-8")
        # El drawer filtra por status pending en el conteo de decisiones.
        self.assertIn("store.decisions || []).filter(function(dc){ return (dc.status||'pending') === 'pending'; }).length", html, "drawer no filtra decisiones pendientes")


if __name__ == "__main__":
    unittest.main()
