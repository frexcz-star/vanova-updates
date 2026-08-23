"""CALIDAD DE DATOS (Nico) — 'Dependencia de un solo producto' no debe emitirse
para productos OBSOLETOS / sin ventas recientes.

Reporte real: el dashboard mostraba 'Dependencia de un solo producto' sobre la
Agenda 2025 (edición del año pasado, ya no se vende). Técnicamente había
concentración de revenue histórico, pero el producto ya no se comercializa.

Fix: en `detect_products` (detection_engine.py), la oportunidad
`product_concentration` solo se emite si el producto top tiene ventas recientes
(revenue30d > 0 o units30d > 0). Si revenue30d == 0 (sin ventas en los últimos
30 días), el producto es obsoleto y NO se emite la señal (sería una oportunidad
falsa). Aplica la regla de honestidad: sin datos suficientes, no emitir.

Falla con el código anterior (el fix no existía → emitía la oportunidad incluso
para productos sin ventas recientes).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import detection_engine


def _prod(sku, revenue, share, revenue30d, units30d=0.0, revenuePrev30d=0.0, revenuePrev60d=0.0):
    return {
        "sku": sku, "name": sku, "cost": 1.0, "hasCost": True, "marginPct": None, "marginEuro": None,
        "units": 100.0, "revenue": revenue, "revenueShare": share,
        "units30d": units30d, "unitsPrev30d": 0.0,
        "revenue30d": revenue30d, "revenuePrev30d": revenuePrev30d,
        "unitsPrev60d": 0.0, "revenuePrev60d": revenuePrev60d,
    }


class ProductConcentrationObsoleteTests(unittest.TestCase):
    def _detect(self, prods):
        return detection_engine.detect_products(
            prods,
            {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "productCost": "verified"},
            {"current30d": "2026-07", "previous30d": "2026-06"},
        )

    def test_obsolete_product_no_concentration_finding(self):
        """Un producto top sin ventas recientes (obsoleto) NO genera la
        oportunidad de dependencia."""
        prods = [
            # Producto dominante pero SIN ventas en los últimos 30 días (obsoleto)
            _prod("AGENDA-2025", 2000.0, 0.60, 0.0, units30d=0.0),
            # Sustituto activo
            _prod("AGENDA-2026", 500.0, 0.15, 500.0, units30d=10.0),
        ]
        findings = self._detect(prods)
        conc = [f for f in findings if f.get("type") == "product_concentration"]
        self.assertEqual(len(conc), 0, "No debe emitirse dependencia para producto obsoleto")

    def test_active_product_still_emits_concentration(self):
        """Un producto dominante CON ventas recientes SÍ genera la oportunidad."""
        prods = [
            _prod("PLANNER-A5", 2000.0, 0.60, 800.0, units30d=20.0),
            _prod("PLANNER-B", 600.0, 0.20, 300.0, units30d=8.0),
        ]
        findings = self._detect(prods)
        conc = [f for f in findings if f.get("type") == "product_concentration"]
        self.assertEqual(len(conc), 1, "Debe emitir dependencia para producto activo")


if __name__ == "__main__":
    unittest.main()
