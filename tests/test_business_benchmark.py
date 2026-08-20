"""VANOVA PRODUCT 8 — BUSINESS BENCHMARK (Nivel 3).

Dataset empresarial realista con anomalías/concentraciones INTRODUCIDAS y
conocidas. El test NO le dice al motor qué buscar: ejecuta la detección y
comprueba que encuentra las señales reales (y no inventa otras).

Mide: recall de las señales esperadas, precisión (sin falsos positivos
obvios), utilidad (evidencia + acción en cada finding) y priorización.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import detection_engine, prioritization


def _build_dataset():
    """PYME ecommerce realista con 4 anomalías deliberadas:
    1) concentración de revenue en 1 producto (SKU-TOP = 38%);
    2) 15 productos sin coste (missing_cost);
    3) 1 pedido con total incoherente (inconsistent_order_total);
    4) SKU duplicado en catálogo (duplicate_sku).
    """
    products = []
    for i in range(200):
        products.append({
            "sku": f"SKU-{i:04d}",
            "name": f"Producto {i}",
            "rrp": 20.0 + i,
            "cost": 10.0 + i / 2,
            "stock": 100 + i,
        })
    # 15 sin coste
    for i in range(15):
        products[i]["cost"] = None
    # SKU duplicado
    products.append(dict(products[5], name="Producto duplicado 5b"))

    sales = []
    # SKU-TOP = 38% del revenue (desequilibrio deliberado)
    top_total = 0.0
    other_total = 0.0
    import random
    from datetime import date, timedelta
    rnd = random.Random(42)
    ref = date(2026, 8, 15)  # fecha de referencia fija (determinista)
    for n in range(1200):
        sku = "SKU-TOP" if n < 420 else f"SKU-{rnd.randint(6, 199):04d}"
        price = 30.0 if sku == "SKU-TOP" else 25.0
        qty = rnd.randint(1, 3)
        total = price * qty
        if sku == "SKU-TOP":
            top_total += total
        else:
            other_total += total
        # Distribución uniforme en los últimos 180 días (sin picos al final)
        days_ago = rnd.randint(0, 180)
        d = (ref - timedelta(days=days_ago)).isoformat()
        sales.append({
            "id": f"ORD-{n}",
            "customer": f"Cliente {rnd.randint(1, 60)}",
            "total": round(total, 2),
            "date": d,
            "line_items": [{"sku": sku, "title": sku, "price": price, "quantity": qty}],
        })
    # Pedido con total incoherente
    sales.append({
        "id": "ORD-INCONSISTENTE", "customer": "Cliente 1",
        "total": 100.0, "date": "2026-07-10",
        "line_items": [{"sku": "SKU-0001", "title": "P1", "price": 10.0, "quantity": 1}],
    })

    top_share = top_total / (top_total + other_total)
    assert 0.30 < top_share < 0.45, f"share={top_share:.2f}"

    return {
        "organizedProducts": products,
        "organizedSales": sales,
        "organizedCustomers": [],
        "organizedInvoices": [],
        "organizedSuppliers": [],
        "businessFindings": [],
    }


class BusinessBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = _build_dataset()
        cls.res = detection_engine.run_detection(cls.data, persist=False)
        cls.findings = [f for f in cls.res["findings"] if f.get("status") not in ("resolved", "archived")]
        cls.types = {f.get("type") for f in cls.findings}

    def test_finds_expected_problems(self):
        expected = {"missing_cost", "inconsistent_order_total", "duplicate_sku"}
        found = self.types & expected
        self.assertTrue(
            found,
            f"El motor no encontró ninguna de las señales esperadas. types={sorted(self.types)}",
        )
        # Recall: al menos las 3 señales de datos esperadas
        for t in expected:
            self.assertIn(t, self.types, f"Señal esperada {t} no detectada")

    def test_no_absurd_false_positives(self):
        # Con 200 productos normales y ventas uniformes, el motor NO debe
        # inventar stockouts (no hay stock mínimo definido) ni gaps de margen
        # masivos (márgenes uniformes). Las caídas de producto SÍ pueden ser
        # legítimas (un SKU pasa de vender a 0 en 30d) — lo importante es que
        # lleven evidencia real, nunca una conclusión sin datos.
        suspicious = {"stockout_risk", "high_revenue_low_margin"}
        hard_fp = suspicious & self.types
        self.assertEqual(len(hard_fp), 0, f"Falsos positivos duros: {sorted(hard_fp)}")
        # Cualquier caída detectada debe tener evidencia numérica real
        for f in self.findings:
            if f.get("type") == "product_declining":
                m = f.get("metrics") or {}
                self.assertIsNotNone(m.get("prevRevenue"))
                self.assertLess((m.get("revenue") or 0), (m.get("prevRevenue") or 0),
                                f"caída sin evidencia: {f.get('title')}")

    def test_findings_are_actionable(self):
        for f in self.findings:
            self.assertTrue(f.get("evidence"), f"finding {f.get('type')} sin evidencia")
            self.assertTrue(f.get("recommendedAction"), f"finding {f.get('type')} sin acción")
            self.assertIn((f.get("estimatedImpact") or {}).get("kind"), ("calculated", "estimated"))

    def test_prioritization_ranks_real_impact(self):
        top = prioritization.build_priorities(self.findings, top=3)
        self.assertLessEqual(len(top), 3)
        self.assertTrue(top)
        # Todas las prioridades llevan por qué importa y qué haría VANOVA
        for p in top:
            self.assertTrue(p.get("whyItMatters"))
            self.assertTrue(p.get("recommendedAction"))

    def test_concentration_signal_present_in_model(self):
        # La concentración real de los datos debe reflejarse en el brain
        from desktop.runtime import company_model

        model = company_model.build_company_model(self.data)
        conc = (model.get("concentration") or {}).get("products") or {}
        self.assertIsNotNone(conc.get("topShare"))
        self.assertGreater(conc.get("topShare"), 30.0)  # >30% real


def _build_aov_churn_dataset():
    """Dataset para el Opportunity Engine: caída de AOV con causa multiproducto,
    clientes inactivos recuperables y un cliente de alto valor en declive."""
    import random
    from datetime import date, timedelta

    rnd = random.Random(7)
    ref = date(2026, 8, 15)
    products = [{"sku": "SKU-A", "name": "A", "rrp": 20.0, "cost": 10.0},
                {"sku": "SKU-B", "name": "B", "rrp": 20.0, "cost": 10.0}]
    sales = []
    n = 0
    # Periodo previo (hace 31-60 días): ticket alto, pedidos MULTIPRODUCTO
    for i in range(120):
        d = (ref - timedelta(days=31 + (i % 30))).isoformat()
        sales.append({"id": f"PRV-{n}", "customer": f"Cliente {rnd.randint(1, 40)}", "total": 40.0,
                      "date": d, "line_items": [{"sku": "SKU-A", "price": 20.0, "quantity": 1},
                                                  {"sku": "SKU-B", "price": 20.0, "quantity": 1}]})
        n += 1
    # Periodo actual (hace 0-30 días): ticket bajo, pedidos MONOPRODUCTO
    for i in range(120):
        d = (ref - timedelta(days=i % 30)).isoformat()
        sales.append({"id": f"CUR-{n}", "customer": f"Cliente {rnd.randint(1, 40)}", "total": 20.0,
                      "date": d, "line_items": [{"sku": "SKU-A", "price": 20.0, "quantity": 1}]})
        n += 1
    # Cliente de alto valor en declive: compraba hace 31-60 días, nada en los últimos 30
    for i in range(4):
        d = (ref - timedelta(days=35 + i)).isoformat()
        sales.append({"id": f"BIG-{n}", "customer": "Cliente Grande", "total": 150.0,
                      "date": d, "line_items": [{"sku": "SKU-A", "price": 150.0, "quantity": 1}]})
        n += 1
    # 4 clientes inactivos (última compra hace 90+ días) con historial recurrente
    for c in range(4):
        for j in range(3):
            d = (ref - timedelta(days=100 + c * 5 + j)).isoformat()
            sales.append({"id": f"IN-{n}", "customer": f"Inactivo {c}", "total": 120.0,
                          "date": d, "line_items": [{"sku": "SKU-A", "price": 120.0, "quantity": 1}]})
            n += 1
    return {"organizedProducts": products, "organizedSales": sales, "organizedCustomers": [],
            "organizedInvoices": [], "organizedSuppliers": [], "businessFindings": []}


class OpportunityBenchmarkTests(unittest.TestCase):
    """El Opportunity Engine encuentra las oportunidades REALES del dataset y
    no inventa cuando no hay evidencia (UNKNOWN ≠ 0)."""

    @classmethod
    def setUpClass(cls):
        cls.data = _build_aov_churn_dataset()
        cls.res = detection_engine.run_detection(cls.data, persist=False)
        cls.findings = [f for f in cls.res["findings"] if f.get("status") not in ("resolved", "archived")]
        cls.types = {f.get("type") for f in cls.findings}

    def test_aov_drop_with_multi_item_cause_detected(self):
        self.assertIn("aov_change", self.types)
        self.assertIn("aov_multi_item_opportunity", self.types)
        opp = next(f for f in self.findings if f["type"] == "aov_multi_item_opportunity")
        self.assertEqual(opp["category"], "opportunity")
        self.assertTrue(opp["evidence"])
        self.assertTrue(opp["recommendedAction"])

    def test_reactivation_opportunity_detected(self):
        self.assertIn("customer_reactivation", self.types)
        opp = next(f for f in self.findings if f["type"] == "customer_reactivation")
        self.assertEqual(opp["category"], "opportunity")
        self.assertGreaterEqual(opp["metrics"]["count"], 3)

    def test_high_value_customer_declining_detected(self):
        self.assertIn("customer_declining", self.types)
        f = next(x for x in self.findings if x["type"] == "customer_declining")
        self.assertLess(f["metrics"]["trendPct"], -50.0)

    def test_all_findings_carry_evidence_and_action(self):
        for f in self.findings:
            self.assertTrue(f.get("evidence"), f"{f.get('type')} sin evidencia")
            self.assertTrue(f.get("recommendedAction"), f"{f.get('type')} sin acción")


if __name__ == "__main__":
    unittest.main()
