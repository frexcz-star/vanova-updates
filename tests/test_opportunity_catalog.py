"""Regression tests — Detector de Oportunidades de Crecimiento (opportunity_catalog).

Patrón acumulativo del tracker: cada fix añade un test.
- Anti-FP: dataset sano sin anomalías -> 0 oportunidades.
- UNKNOWN != 0: sin coste -> upsideEuro = None, nunca 0.
- Cross-sell con coste verificado -> upsideEuro calculado; sin coste -> None.
- Concentración -> revenueAtRisk enriquecido.
- Dedupe por firma: re-análisis no duplica.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import opportunity_catalog as oc  # noqa: E402


def _finding(typ, category="opportunity", status="active", severity="medium",
             confidence="medium", metrics=None, impact=None, sig=None, title="", action="", evidence=None):
    return {
        "id": f"find_{typ}",
        "signature": sig or f"{typ}:{metrics.get('sku','x') if metrics else 'x'}",
        "type": typ,
        "finding_type": typ,
        "category": category,
        "status": status,
        "severity": severity or ("medium" if category == "opportunity" else "high"),
        "confidence": confidence,
        "metrics": metrics or {},
        "estimatedImpact": impact or {},
        "title": title or typ,
        "recommendedAction": action or "accion",
        "observation": "obs",
        "evidence": ["ev1"],
        "entity": (metrics or {}).get("entity", ""),
        "createdAt": "2026-01-01T00:00:00+00:00",
    }


class OpportunityCatalogBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(ROOT) / ".opportunity_test_tmp"
        self.tmp.mkdir(exist_ok=True)
        self._patch_products = patch.object(oc.config_store, "load", return_value={
            "organizedProducts": [
                {"sku": "A", "rrp": 100.0, "netPrice": 60.0, "cost": 60.0, "costSource": "verified"},
                {"sku": "B", "rrp": 50.0, "netPrice": 25.0, "cost": 25.0, "costSource": "verified"},
            ],
            "opportunities": [],
        })
        self._patch_products.start()

    def tearDown(self):
        self._patch_products.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class BuildCatalogTests(OpportunityCatalogBase):
    def test_anti_fp_sane_dataset_no_opportunities(self):
        # Sin findings de categoría opportunity -> 0
        res = oc.build_catalog([])
        self.assertEqual(len(res), 0)

    def test_filters_only_active_opportunity(self):
        findings = [
            _finding("cross_sell", "opportunity", metrics={"pair": "A+B", "ordersTogether": 30}, sig="cross_sell:ab"),
            _finding("product_concentration", "opportunity", metrics={"entity": "p"},
                     impact={"kind": "estimated", "revenueAtRisk": 500.0}, sig="product_concentration:p"),
            _finding("aov_change", "problem", metrics={"currentAov": 10, "previousAov": 20}),  # problem, descartado
            _finding("cross_sell", "opportunity", status="resolved", metrics={"x": 1}),  # resuelto, descartado
        ]
        res = oc.build_catalog(findings)
        self.assertEqual(len(res), 2)

    def test_cross_sell_with_cost_calculates_upside(self):
        # A: sale 100, cost 60 -> margen 40%; B: sale 50, cost 25 -> margen 50%.
        # avg_margin = 45%. 30 pedidos -> 30 * 0.45 = 13.5 (umitidos)
        f = _finding("cross_sell", "opportunity", metrics={"pair": "A+B", "ordersTogether": 30}, sig="cross_sell:ab")
        res = oc.build_catalog([f])
        self.assertEqual(len(res), 1)
        # 13.5 < 25 -> None (anti-ruido)
        self.assertIsNone(res[0]["upsideEuro"])
        self.assertEqual(res[0]["impactKind"], "not_quantifiable")

    def test_cross_sell_with_cost_and_volume(self):
        # Margenes A=40%, B=50% -> avg 45%. 100 pedidos -> 45 EUR -> calculado
        f = _finding("cross_sell", "opportunity", metrics={"pair": "A+B", "ordersTogether": 100}, sig="cross_sell:ab")
        res = oc.build_catalog([f])
        self.assertEqual(len(res), 1)
        self.assertIsNotNone(res[0]["upsideEuro"])
        self.assertAlmostEqual(res[0]["upsideEuro"], 45.0, places=1)
        self.assertEqual(res[0]["impactKind"], "calculated")

    def test_unknown_not_zero_no_cost(self):
        # Sin coste en el finding: upside None, nunca 0
        f = _finding("low_revenue_high_margin", "opportunity",
                     impact={"kind": "estimated", "marginPotential": None}, sig="low_rev:a")
        res = oc.build_catalog([f])
        self.assertEqual(len(res), 1)
        self.assertIsNone(res[0]["upsideEuro"])
        self.assertEqual(res[0]["impactLabel"], "Impacto no cuantificable")

    def test_upside_below_minimum_not_emitted(self):
        f = _finding("cross_sell", "opportunity", metrics={"pair": "A+B", "ordersTogether": 30}, sig="cross_sell:ab")
        res = oc.build_catalog([f])
        # 13.5 < 25 -> None
        self.assertIsNone(res[0]["upsideEuro"])

    def test_dedupe_by_signature(self):
        f1 = _finding("cross_sell", "opportunity", metrics={"pair": "A+B", "ordersTogether": 100}, sig="cross_sell:ab")
        f2 = _finding("cross_sell", "opportunity", metrics={"pair": "A+B", "ordersTogether": 100}, sig="cross_sell:ab")
        res = oc.build_catalog([f1, f2])
        self.assertEqual(len(res), 1)  # misma firma -> 1

    def test_concentration_uses_revenue_at_risk(self):
        f = _finding("product_concentration", "opportunity", impact={"kind": "estimated", "revenueAtRisk": 1234.5}, sig="product_concentration:p")
        res = oc.build_catalog([f])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["upsideEuro"], 1234.5)
        self.assertEqual(res[0]["impactKind"], "calculated")

    def test_top_returns_limit(self):
        findings = [
            _finding("cross_sell", "opportunity", metrics={"pair": f"A{i}+B{i}", "ordersTogether": 200}, sig=f"cross_sell:{i}")
            for i in range(10)
        ]
        res = oc.build_catalog(findings, top=3)
        self.assertEqual(len(res), 3)


if __name__ == "__main__":
    unittest.main()
