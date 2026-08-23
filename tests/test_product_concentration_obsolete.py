"""BUG-040 / SPEC vitalidad — dependencia de producto obsoleto/muerto.

Un producto muerto (sin ventas en 90 días contra la fecha de referencia del
dataset) no debe emitir 'Dependencia de un solo producto' como riesgo real.
Según el SPEC, emite la señal DESCARTADA con kind='no_signal' y explicación en €.
Un producto vivo (con ventas recientes) SÍ emite la dependencia real.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import detection_engine


REF = datetime(2026, 7, 31, tzinfo=timezone.utc)


def _sale(sku, days_ago):
    return {"sku": sku, "date": (REF - timedelta(days=days_ago)).isoformat(), "total": 100.0, "quantity": 1}


def _prod(sku, revenue, share, revenue30d=0.0, units30d=0.0):
    return {
        "sku": sku, "name": sku, "cost": 1.0, "hasCost": True, "marginPct": None, "marginEuro": None,
        "units": 100.0, "revenue": revenue, "revenueShare": share,
        "units30d": units30d, "unitsPrev30d": 0.0,
        "revenue30d": revenue30d, "revenuePrev30d": 0.0,
        "unitsPrev60d": 0.0, "revenuePrev60d": 0.0,
    }


class ProductConcentrationObsoleteTests(unittest.TestCase):
    def _detect(self, prods, sales=None):
        return detection_engine.detect_products(
            prods,
            {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "productCost": "verified"},
            {"current30d": "2026-07", "previous30d": "2026-06"},
            sales,
        )

    def test_obsolete_product_no_risk_finding(self):
        """Producto obsoleto (sin ventas) NO emite riesgo real de dependencia —
        emite no_signal descartada."""
        prods = [_prod("AGENDA-2025", 2000.0, 0.60), _prod("AGENDA-2026", 500.0, 0.15)]
        sales = [_sale("AGENDA-2026", 10)]
        findings = self._detect(prods, sales)
        conc = [f for f in findings if f.get("type") == "product_concentration"]
        risk = [f for f in conc if f.get("kind") != "no_signal"]
        self.assertEqual(len(risk), 0, "No debe emitirse dependencia real para producto obsoleto")

    def test_obsolete_emite_no_signal(self):
        """El producto obsoleto emite la señal descartada (no_signal) con explicación."""
        prods = [_prod("OBSOLETO", 2000.0, 0.60), _prod("ACTIVO", 500.0, 0.15)]
        sales = [_sale("ACTIVO", 10)]
        findings = self._detect(prods, sales)
        conc = [f for f in findings if f.get("type") == "product_concentration"]
        no_signal = [f for f in conc if f.get("kind") == "no_signal"]
        self.assertEqual(len(no_signal), 1, "Debe emitir no_signal explicada")

    def test_active_product_still_emits_concentration(self):
        """Producto dominante CON ventas recientes SÍ genera la oportunidad."""
        prods = [_prod("PLANNER-A5", 2000.0, 0.60, 800.0, units30d=20.0), _prod("PLANNER-B", 600.0, 0.20)]
        sales = [_sale("PLANNER-A5", 5), _sale("PLANNER-B", 20)]
        findings = self._detect(prods, sales)
        conc = [f for f in findings if f.get("type") == "product_concentration"]
        risk = [f for f in conc if f.get("kind") != "no_signal"]
        self.assertEqual(len(risk), 1, "Debe emitir dependencia para producto activo")


if __name__ == "__main__":
    unittest.main()
