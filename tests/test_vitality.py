"""Capa de vitalidad de producto (SPEC) — filtro de señales sobre productos muertos.

Criterios de aceptación del SPEC:
1. Unidad vitalidad: producto sin ventas en >=90d -> es_vivo=False; con >=1 venta -> es_vivo=True.
2. Filtro de concentración: producto que concentra revenue histórico pero 0 ventas en 90d
   -> NO emite "dependencia" como riesgo; emite la señal descartada con kind='no_signal'.
3. Producto vivo: con ventas recientes reales, la dependencia SI se emite (riesgo real).
4. Declive->muerte: producto con ventas en 180d pero 0 en 90d -> "producto en declive".
5. Degradacion honesta: sin datos de ventas con fecha -> estimated, no se descarta.
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
    d = (REF - timedelta(days=days_ago)).isoformat()
    return {"sku": sku, "date": d, "total": 100.0, "quantity": 1}


def _prod(sku, revenue, share, revenue30d=0.0, units30d=0.0):
    return {
        "sku": sku, "name": sku, "cost": 1.0, "hasCost": True, "marginPct": None, "marginEuro": None,
        "units": 100.0, "revenue": revenue, "revenueShare": share,
        "units30d": units30d, "unitsPrev30d": 0.0,
        "revenue30d": revenue30d, "revenuePrev30d": 0.0,
        "unitsPrev60d": 0.0, "revenuePrev60d": 0.0,
    }


class VitalityUnitTests(unittest.TestCase):
    def test_product_sin_ventas_90d_no_vivo(self):
        v = detection_engine.product_vitality("A", [_sale("A", 200)], ref=REF)
        self.assertFalse(v["es_vivo"])
        self.assertTrue(v["calculable"])

    def test_product_con_venta_reciente_vivo(self):
        v = detection_engine.product_vitality("A", [_sale("A", 10)], ref=REF)
        self.assertTrue(v["es_vivo"])

    def test_product_en_declive(self):
        # venta hace 100 dias (entre 90 y 180) -> en declive, no vivo
        v = detection_engine.product_vitality("A", [_sale("A", 100)], ref=REF)
        self.assertFalse(v["es_vivo"])
        self.assertTrue(v["en_declive"])


class ConcentrationVitalityFilterTests(unittest.TestCase):
    def _detect(self, prods, sales):
        return detection_engine.detect_products(
            prods,
            {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "productCost": "verified"},
            {"current30d": "2026-07", "previous30d": "2026-06"},
            sales,
        )

    def test_producto_muerto_emite_no_signal(self):
        # Producto dominante SIN ventas en el dataset (muerto) -> descartada (no_signal)
        prods = [_prod("AGENDA-2025", 2000.0, 0.60), _prod("AGENDA-2026", 500.0, 0.15)]
        sales = [_sale("AGENDA-2026", 30)]
        findings = self._detect(prods, sales)
        conc = [f for f in findings if f.get("type") == "product_concentration"]
        no_signal = [f for f in conc if f.get("kind") == "no_signal"]
        risk = [f for f in conc if f.get("kind") != "no_signal"]
        self.assertEqual(len(no_signal), 1, "Debe emitir no_signal explicada")
        self.assertEqual(len(risk), 0, "No debe emitir riesgo real sobre producto muerto")

    def test_producto_vivo_emite_riesgo(self):
        # Producto dominante CON ventas recientes -> riesgo real
        prods = [_prod("PLANNER-A5", 2000.0, 0.60), _prod("PLANNER-B", 600.0, 0.20)]
        sales = [_sale("PLANNER-A5", 5), _sale("PLANNER-B", 20)]
        findings = self._detect(prods, sales)
        conc = [f for f in findings if f.get("type") == "product_concentration"]
        no_signal = [f for f in conc if f.get("kind") == "no_signal"]
        risk = [f for f in conc if f.get("kind") != "no_signal"]
        self.assertEqual(len(risk), 1, "Producto vivo -> emite dependencia real")

    def test_producto_en_declive_emite_decline(self):
        # Producto dominante con ventas hace 120d (dentro de 180d pero fuera de 90d
        # respecto a la referencia del dataset) -> declive, no dependencia.
        prods = [_prod("AGENDA-TRIM", 2000.0, 0.60), _prod("NUEVA", 400.0, 0.15)]
        sales = [_sale("AGENDA-TRIM", 120), _sale("NUEVA", 10)]
        findings = self._detect(prods, sales)
        decline = [f for f in findings if f.get("type") == "product_decline"]
        self.assertEqual(len(decline), 1, "Debe emitir hallazgo de declive")
        conc = [f for f in findings if f.get("type") == "product_concentration"]
        self.assertEqual(len(conc), 0, "No emite dependencia para producto en declive")

    def test_sin_datos_fecha_degrada_estimated(self):
        # Sin sales con fecha -> no se puede validar vitalidad -> degrada a estimated
        prods = [_prod("X", 2000.0, 0.60), _prod("Y", 400.0, 0.15)]
        findings = self._detect(prods, [])  # sales vacias
        conc = [f for f in findings if f.get("type") == "product_concentration"]
        self.assertEqual(len(conc), 1, "Degrada a estimated, no descarta")
        self.assertEqual(conc[0].get("kind"), "estimated")


if __name__ == "__main__":
    unittest.main()
