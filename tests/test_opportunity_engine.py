"""PRODUCT LEAP — tests de producto del Opportunity Engine y el Action Center.

Verifican que las oportunidades solo se emiten CON evidencia real y que la
falta de evidencia produce silencio (UNKNOWN ≠ 0, nunca inventar):
  * AOV a la baja: solo se afirma la causa multiproducto si los pedidos con
    2+ SKUs también caen; si no, la oportunidad NO se emite.
  * Reactivación: solo con masa crítica (>=3 clientes, valor conjunto >= umbral).
  * Declive de cliente de alto valor: solo con revenue/pedidos reales.
  * Concentración de producto: share real + sustitutos con crecimiento.
  * Action Center: prepara CSV de costes/segmento (solo lectura + audit).
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from desktop.runtime import action_center, detection_engine

REF = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def _d(days_before: int) -> str:
    return (REF - timedelta(days=days_before)).date().isoformat()


def _sale(order_id: str, days_before: int, total: float, skus: list[str], customer: str = "C") -> dict:
    return {
        "id": order_id,
        "total": total,
        "date": _d(days_before),
        "customer": customer,
        "line_items": [
            {"sku": s, "price": total / max(1, len(skus)), "quantity": 1} for s in skus
        ],
    }


def _quality(orders: int = 30) -> dict:
    return {
        "ordersTotal": orders,
        "canAnalyzeProducts": True,
        "canAnalyzeMargin": True,
        "notes": [],
    }


class AovMultiItemTests(unittest.TestCase):
    """AOV a la baja: la oportunidad SOLO se emite si cae la parte multiproducto."""

    def _aov(self, current: float, previous: float, cur_orders: int, prev_orders: int) -> dict:
        change = round((current - previous) / previous * 100, 1) if previous else None
        return {
            "currentAov": current, "previousAov": previous,
            "changePct": change, "currentOrders": cur_orders, "previousOrders": prev_orders,
        }

    def test_aov_drop_with_multi_item_cause_emits_opportunity(self):
        # 30d actuales: ticket bajo y pocos pedidos multiproducto.
        sales = []
        for i in range(20):  # prev: AOV alto, todos con 2+ SKUs
            sales.append(_sale(f"p{i}", 45 + i, 40.0, ["A", "B"]))
        for i in range(20):  # cur: AOV bajo, todos con 1 SKU
            sales.append(_sale(f"c{i}", 5 + i, 25.0, ["A"]))
        aov = self._aov(25.0, 40.0, 20, 20)
        findings = detection_engine.detect_aov(aov, _quality(40), REF, sales)
        types = {f["type"] for f in findings}
        self.assertIn("aov_change", types)
        self.assertIn("aov_multi_item_opportunity", types)
        opp = next(f for f in findings if f["type"] == "aov_multi_item_opportunity")
        self.assertEqual(opp["category"], "opportunity")
        self.assertLess(opp["metrics"]["multiItemShareNow"], opp["metrics"]["multiItemSharePrev"])
        self.assertTrue(any("multiproducto" in str(e) for e in opp["evidence"]))

    def test_aov_drop_without_multi_item_cause_no_opportunity(self):
        # AOV cae pero los pedidos siguen siendo multiproducto → NO hay causa
        # demostrada → NO se emite la oportunidad (honestidad, no inventar).
        sales = []
        for i in range(20):
            sales.append(_sale(f"p{i}", 45 + i, 40.0, ["A", "B"]))
        for i in range(20):
            sales.append(_sale(f"c{i}", 5 + i, 25.0, ["A", "B"]))  # 2+ SKUs siguen
        aov = self._aov(25.0, 40.0, 20, 20)
        findings = detection_engine.detect_aov(aov, _quality(40), REF, sales)
        types = {f["type"] for f in findings}
        self.assertIn("aov_change", types)
        self.assertNotIn("aov_multi_item_opportunity", types)


class CustomerOpportunityTests(unittest.TestCase):
    """Reactivación agregada y declive de cliente de alto valor."""

    def _cust(self, name: str, revenue: float, orders: int, days_since: int, trend: float | None = None) -> dict:
        return {
            "id": name, "name": name, "revenue": revenue, "orders": orders,
            "avgTicket": round(revenue / orders, 2) if orders else None,
            "marginPct": None, "trendPct": trend,
            "lastOrder": _d(days_since), "daysSinceLastOrder": days_since,
            "orders30d": 0, "revenue30d": 0.0, "revenueShare": 0.0,
        }

    def test_reactivation_emitted_with_mass(self):
        cust = [self._cust(f"Cliente {i}", 600.0, 4, 75) for i in range(4)]
        findings = detection_engine.detect_customers(cust, {}, REF)
        types = {f["type"] for f in findings}
        self.assertIn("customer_reactivation", types)
        opp = next(f for f in findings if f["type"] == "customer_reactivation")
        self.assertEqual(opp["category"], "opportunity")
        self.assertEqual(opp["metrics"]["count"], 4)
        self.assertAlmostEqual(opp["metrics"]["combinedRevenue"], 2400.0)

    def test_reactivation_not_emitted_without_mass(self):
        # Solo 1 cliente inactivo → no hay campaña, no hay oportunidad.
        cust = [self._cust("Cliente A", 5000.0, 10, 80)]
        findings = detection_engine.detect_customers(cust, {}, REF)
        self.assertNotIn("customer_reactivation", {f["type"] for f in findings})

    def test_customer_declining_high_value(self):
        cust = [self._cust("Cliente Top", 3000.0, 8, 10, trend=-62.0)]
        findings = detection_engine.detect_customers(cust, {}, REF)
        types = {f["type"] for f in findings}
        self.assertIn("customer_declining", types)
        f = next(x for x in findings if x["type"] == "customer_declining")
        self.assertEqual(f["category"], "problem")
        self.assertLess(f["metrics"]["trendPct"], -50.0)

    def test_no_declining_without_trend(self):
        cust = [self._cust("Cliente A", 3000.0, 8, 10, trend=None)]
        findings = detection_engine.detect_customers(cust, {}, REF)
        self.assertNotIn("customer_declining", {f["type"] for f in findings})


class ProductConcentrationTests(unittest.TestCase):
    def _sig(self, sku: str, revenue: float, share: float, rev30: float, prev30: float) -> dict:
        return {
            "sku": sku, "revenue": revenue, "revenueShare": share,
            "revenue30d": rev30, "revenuePrev30d": prev30,
            "units30d": 10, "unitsPrev30d": 10, "unitsPrev60d": 20, "revenuePrev60d": prev30,
            "hasCost": True, "marginPct": 30.0, "costStatus": "ok",
        }

    def test_concentration_with_diversifiers(self):
        prod = [
            self._sig("TOP", 900.0, 0.45, 500.0, 500.0),
            self._sig("ALT1", 200.0, 0.10, 60.0, 30.0),  # crece
            self._sig("ALT2", 150.0, 0.07, 50.0, 25.0),  # crece
        ]
        findings = detection_engine.detect_products(prod, _quality(), {"current30d": "x", "previous30d": "y"})
        types = {f["type"] for f in findings}
        self.assertIn("product_concentration", types)
        f = next(x for x in findings if x["type"] == "product_concentration")
        self.assertEqual(f["category"], "opportunity")
        self.assertIn("ALT1", f["metrics"]["diversifiers"])
        self.assertTrue(any("Sustitutos" in str(e) for e in f["evidence"]))

    def test_concentration_without_revenue_not_emitted(self):
        prod = [self._sig("TOP", 0.0, 0.0, 0.0, 0.0)]
        findings = detection_engine.detect_products(prod, _quality(), {"current30d": "x", "previous30d": "y"})
        self.assertNotIn("product_concentration", {f["type"] for f in findings})


class ActionCenterTests(unittest.TestCase):
    def _data(self) -> dict:
        return {
            "organizedProducts": [
                {"sku": "SKU-1", "name": "Producto 1", "price": 12.0, "cost": 5.0},
                {"sku": "SKU-2", "name": "Producto 2", "price": 20.0},  # sin coste
                {"name": "Producto 3"},  # sin coste ni sku
            ],
            "organizedSales": [],
            "organizedCustomers": [],
        }

    def test_cost_template_read_only(self):
        r = action_center.prepare_cost_template(self._data())
        self.assertTrue(r["ok"])
        self.assertEqual(r["kind"], "cost_template")
        self.assertEqual(r["count"], 2)  # SKU-2 y Producto 3 no tienen coste
        self.assertIn("SKU-2", r["csv"])
        self.assertIn("cost", r["csv"].splitlines()[0])

    def test_unknown_kind_rejected(self):
        r = action_center.prepare("hack", self._data())
        self.assertFalse(r["ok"])
        self.assertIn("desconocida", r["error"].lower())

    def test_reactivation_segment_csv(self):
        sales = []
        for i in range(4):  # 4 clientes recurrentes, inactivos (última venta hace 80+ días)
            for j in range(4):
                sales.append(_sale(f"o{i}-{j}", 80 + i + j, 100.0, ["A"], customer=f"Cliente {i}"))
        for k in range(6):  # ventas recientes de otros clientes (fijan la fecha de referencia)
            sales.append(_sale(f"r{k}", 1 + k, 50.0, ["B"], customer=f"Reciente {k}"))
        data = {"organizedSales": sales, "organizedProducts": [], "organizedCustomers": []}
        r = action_center.prepare_reactivation_segment(data)
        self.assertTrue(r["ok"])
        self.assertGreaterEqual(r["count"], 3)
        self.assertIn("Cliente 0", r["csv"])


if __name__ == "__main__":
    unittest.main()
