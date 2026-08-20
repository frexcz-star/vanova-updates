"""FASE 8 — tests del motor de detección empresarial determinista.

Cada detector se prueba contra su umbral: dataset insuficiente → sin finding;
margen bajo → finding; muestra diminuta → sin tendencia; cross-sell con muestra
suficiente → finding; tesorería sin saldo bancario → nunca afirmar liquidez;
dedupe por firma; datos desactualizados → degradar.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from desktop.runtime import business_signals as bs
from desktop.runtime import detection_engine as de

TODAY = datetime.now(timezone.utc).date()


def _d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def _prod(sku: str, net: float | None = None, rrp: float | None = None):
    return {"name": sku, "sku": sku, "netPrice": net, "rrp": rrp, "source": "excel"}


def _sale(order_id: str, date: str, *items):
    return {"order_id": order_id, "date": date, "total": sum(i[2] * i[1] for i in items), "line_items": [{"sku": s, "quantity": q, "price": p} for s, q, p in items]}


def _rich_data():
    """30 pedidos en 30 días con 5 SKUs con coste: A con margen bajo y mucho
    revenue; B–E con margen alto. Proporciona base para 'mucho revenue + poco
    margen' y para el promedio de empresa."""
    products = [_prod("A", 9.0, 10.0), _prod("B", 1.0, 10.0), _prod("C", 1.0, 10.0), _prod("D", 1.0, 10.0), _prod("E", 1.0, 10.0)]
    sales = []
    for i in range(30):
        sales.append(_sale(f"O{i}", _d(i % 30), ("A", 1, 10.0), ("B", 1, 10.0), ("C", 1, 10.0), ("D", 1, 10.0), ("E", 1, 10.0)))
    return {"organizedProducts": products, "organizedSales": sales}


class DataQualityTests(unittest.TestCase):
    def test_insufficient_orders_no_analysis(self):
        data = {"organizedSales": [_sale("O1", _d(1), ("A", 1, 10.0))], "organizedProducts": [_prod("A", 1.0)]}
        q = de.data_quality(data)
        self.assertFalse(q["canAnalyzeProducts"])

    def test_stale_data_disables_product_analysis(self):
        data = _rich_data()
        data["facturascriptSync"] = {"lastSync": _d(30)}
        data["dashboardSnapshot"] = {"fetchedAt": _d(30)}
        q = de.data_quality(data)
        self.assertTrue(q["stale"])
        self.assertFalse(q["canAnalyzeProducts"])

    def test_missing_costs_disable_product_analysis(self):
        data = _rich_data()
        data["organizedProducts"] = [_prod("A"), _prod("B"), _prod("C"), _prod("D"), _prod("E")]
        q = de.data_quality(data)
        self.assertFalse(q["costCoverageOk"])
        self.assertFalse(q["canAnalyzeProducts"])

    def test_identity_note_is_inverted_percentage(self):
        """PRE-BETA: la nota de identidad dice el % SIN match (100 − cov), no
        el % con match. Bug real de wording encontrado en validación."""
        data = _rich_data()
        q = de.data_quality(data)
        cov = q.get("identityCoveragePct") or 0.0
        for note in q.get("notes") or []:
            if "identidad de producto" in note:
                # la nota usa 100 − cov, nunca cov como "sin correspondencia"
                self.assertNotIn(f"el {round(cov, 1)}% del revenue no tiene", note)
                self.assertIn(str(round(100 - cov, 1)), note)

    def test_data_quality_exposes_products_coverage(self):
        """PRE-BETA: la cobertura de coste por Nº de productos está disponible
        junto a la de revenue (bases distintas, ambas expuestas)."""
        data = _rich_data()
        q = de.data_quality(data)
        self.assertIn("costCoverage", q)  # por producto (fracción)
        self.assertIn("revenueWithVerifiedCost", q)  # por revenue (€)
        self.assertGreaterEqual(q["costCoverage"], 0.0)
        self.assertLessEqual(q["costCoverage"], 1.0)


class ProductDetectorTests(unittest.TestCase):
    def test_high_revenue_low_margin_found(self):
        data = _rich_data()
        res = de.run_detection(data, persist=False)
        findings = [f for f in res["findings"] if f["type"] == "high_revenue_low_margin"]
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f["metrics"]["sku"], "a")  # el motor normaliza a minúsculas
        self.assertEqual(f["category"], "problem")
        self.assertEqual(f["severity"], "high")
        self.assertTrue(f["estimatedImpact"]["kind"] in ("calculated", "estimated"))
        self.assertGreater(len(f["evidence"]), 0)
        # A: revenue share 20%, margen 10% vs promedio 74%
        self.assertLess(f["metrics"]["marginPct"], f["metrics"]["avgMarginPct"] - 10)

    def test_no_finding_when_margins_normal(self):
        data = _rich_data()
        for p in data["organizedProducts"]:
            p["netPrice"] = 5.0  # todos margen 50% — ninguno bajo
        res = de.run_detection(data, persist=False)
        self.assertEqual([f for f in res["findings"] if f["type"] == "high_revenue_low_margin"], [])

    def test_declining_product_found_with_equivalent_periods(self):
        data = _rich_data()
        # X: 20 pedidos en el período previo, 4 en el actual → caída fuerte
        for i in range(20):
            data["organizedSales"].append(_sale(f"PX{i}", _d(40 + i % 20), ("X", 1, 10.0)))
        for i in range(4):
            data["organizedSales"].append(_sale(f"CX{i}", _d(5 + i), ("X", 1, 10.0)))
        res = de.run_detection(data, persist=False)
        decl = [f for f in res["findings"] if f["type"] == "product_declining" and f["metrics"].get("sku") == "x"]
        self.assertEqual(len(decl), 1)
        self.assertEqual(decl[0]["category"], "problem")
        self.assertLessEqual(decl[0]["metrics"]["revenueChangePct"], -30)

    def test_small_variation_no_trend(self):
        data = _rich_data()
        # X con variación de +8% (bajo el umbral 30%)
        for i in range(20):
            data["organizedSales"].append(_sale(f"P{i}", _d(40 + i), ("X", 1, 10.0)))
        for i in range(21):
            data["organizedSales"].append(_sale(f"C{i}", _d(i), ("X", 1, 10.0)))
        res = de.run_detection(data, persist=False)
        self.assertEqual([f for f in res["findings"] if f["type"] in ("product_growing", "product_declining") and f["metrics"].get("sku") == "x"], [])

    def test_tiny_sample_never_flagged_as_trend(self):
        data = _rich_data()
        # X solo en 3 pedidos previos → muestra diminuta, sin caída marcada
        for i in range(3):
            data["organizedSales"].append(_sale(f"P{i}", _d(40 + i), ("X", 1, 10.0)))
        res = de.run_detection(data, persist=False)
        self.assertEqual([f for f in res["findings"] if f["type"] == "product_declining" and f["metrics"].get("sku") == "x"], [])

    def test_decline_detected_without_margin_sample(self):
        """FASE 9 regression: el gate de margen (<5 productos con coste)
        bloqueaba TAMBIÉN las caídas/crecimientos, que no necesitan coste.
        Una caída real entre períodos equivalentes debe detectarse aunque no
        haya suficientes productos con coste para el promedio de margen."""
        # Solo 2 productos con coste (menos de 5) + X en caída real
        products = [_prod("A", 9.0, 10.0), _prod("B", 1.0, 10.0)]
        sales = []
        for i in range(30):
            sales.append(_sale(f"O{i}", _d(i % 30), ("A", 1, 10.0), ("B", 1, 10.0)))
        for i in range(20):
            sales.append(_sale(f"PX{i}", _d(40 + i % 20), ("X", 1, 10.0)))
        for i in range(4):
            sales.append(_sale(f"CX{i}", _d(5 + i), ("X", 1, 10.0)))
        res = de.run_detection({"organizedProducts": products, "organizedSales": sales}, persist=False)
        decl = [f for f in res["findings"] if f["type"] == "product_declining" and f["metrics"].get("sku") == "x"]
        self.assertEqual(len(decl), 1)
        # Sin muestra de margen suficiente: NINGÚN hallazgo de margen
        self.assertEqual([f for f in res["findings"] if "margin" in f["type"]], [])


class CrossSellTests(unittest.TestCase):
    def _cross_data(self, with_a: int, with_ab: int, total: int):
        # Base construida desde cero: cada pedido lleva UN único SKU, así no hay
        # co-pares espurios. El total de pedidos es exactamente `total`.
        products = [_prod("A", 9.0, 10.0), _prod("B", 1.0, 10.0), _prod("C", 1.0, 10.0), _prod("D", 1.0, 10.0), _prod("E", 1.0, 10.0)]
        base_skus = ["B", "C", "D", "E", "H"]
        sales = []
        for i in range(max(0, total - with_a)):
            sales.append(_sale(f"X{i}", _d(i % 30), (base_skus[i % len(base_skus)], 1, 10.0)))
        for i in range(with_a):
            items = [("A", 1, 10.0)]
            if i < with_ab:
                items.append(("F", 1, 5.0))
            else:
                items.append(("G", 1, 5.0))
            sales.append(_sale(f"AB{i}", _d(i % 30), *items))
        return {"organizedProducts": products, "organizedSales": sales}

    def test_cross_sell_with_sufficient_sample_found(self):
        data = self._cross_data(with_a=15, with_ab=10, total=40)
        res = de.run_detection(data, persist=False)
        cs = [f for f in res["findings"] if f["type"] == "cross_sell"]
        self.assertGreaterEqual(len(cs), 1)
        f = cs[0]
        self.assertGreaterEqual(f["metrics"]["frequency"], 0.15)
        self.assertGreaterEqual(f["metrics"]["ordersWithA"], 10)
        self.assertIn("aparecen juntos", f["observation"])

    def test_cross_sell_insufficient_sample_no_finding(self):
        data = self._cross_data(with_a=3, with_ab=2, total=8)
        res = de.run_detection(data, persist=False)
        self.assertEqual([f for f in res["findings"] if f["type"] == "cross_sell"], [])


class TreasuryTests(unittest.TestCase):
    def test_payments_concentration_never_claims_liquidity(self):
        data = _rich_data()
        data["organizedFinance"] = [
            {"id": "c1", "type": "collection", "amount": 100.0},
            {"id": "p1", "type": "payment", "amount": 10.0},
        ]
        data["organizedInvoices"] = [
            {"id": "1", "type": "issued", "total": 200.0, "paid": True, "date": _d(2)},
            {"id": "2", "type": "received", "total": 80.0, "paid": False, "date": _d(3), "dueDate": _d(-10)},
        ]
        res = de.run_detection(data, persist=False)
        t = [f for f in res["findings"] if f["type"] == "upcoming_payments_concentration"]
        self.assertEqual(len(t), 1)
        combined_evidence = " ".join(t[0]["evidence"])
        self.assertIn("NO se puede afirmar tensión de liquidez", combined_evidence)
        self.assertIn("no hay saldo bancario real", combined_evidence)


class ThresholdUnitTests(unittest.TestCase):
    """FASE 16 H28 — los umbrales porcentuales se comparan en puntos de
    porcentaje (no fracciones): un AOV de -3.2% NO puede disparar con un
    umbral de 10%, y unos gastos +5% no pueden disparar con un umbral de 25%."""

    def _quality(self):
        return {
            "ordersTotal": 100,
            "canAnalyzeProducts": True,
            "canAnalyzeMargin": True,
            "canAnalyzeTreasury": True,
            "canAnalyzeExpenses": True,
        }

    def test_aov_small_change_below_threshold_no_finding(self):
        """-3.2% está por debajo del umbral de 10% → NUNCA finding."""
        aov = {"currentAov": 161.5, "previousAov": 166.9, "changePct": -3.2, "currentOrders": 690, "previousOrders": 528}
        self.assertEqual(de.detect_aov(aov, self._quality()), [])

    def test_aov_change_above_threshold_found(self):
        """+15% supera el 10% → finding (categoría positive)."""
        aov = {"currentAov": 190.0, "previousAov": 165.0, "changePct": 15.2, "currentOrders": 700, "previousOrders": 530}
        findings = de.detect_aov(aov, self._quality())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["type"], "aov_change")
        self.assertEqual(findings[0]["category"], "positive")
        self.assertIn("al alza", findings[0]["title"])

    def test_expenses_small_growth_below_threshold_no_finding(self):
        """+5% de gastos está por debajo del umbral de 25% → sin finding."""
        exp = {"currentTotal": 52500.0, "previousTotal": 50000.0, "growthPct": 5.0,
               "currentMonth": "2026-08", "previousMonth": "2026-07"}
        self.assertEqual(de.detect_expenses(exp, self._quality()), [])

    def test_expenses_growth_above_threshold_found(self):
        """+40% de gastos supera el 25% → finding expenses_growing."""
        exp = {"currentTotal": 70000.0, "previousTotal": 50000.0, "growthPct": 40.0,
               "currentMonth": "2026-08", "previousMonth": "2026-07"}
        findings = de.detect_expenses(exp, self._quality())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["type"], "expenses_growing")


class DataQualityDetectorTests(unittest.TestCase):
    """FASE C (B8) — detectores de calidad de datos: las anomalías PRESERVADAS
    se convierten en findings sin borrar nada (UNKNOWN ≠ 0)."""

    def _base(self):
        return {"organizedProducts": [], "organizedSales": [], "organizedCustomers": [],
                "organizedInvoices": [], "organizedFinance": []}

    def test_duplicate_sku_found(self):
        data = self._base()
        data["organizedProducts"] = [
            {"name": "A", "sku": "DUP-1", "source": "excel"},
            {"name": "B", "sku": "DUP-1", "source": "excel"},
        ]
        res = de.run_detection(data, persist=False)
        f = [x for x in res["findings"] if x["type"] == "duplicate_sku"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["metrics"]["sku"], "dup-1")
        self.assertEqual(f[0]["metrics"]["records"], 2)

    def test_missing_sku_and_missing_cost_found(self):
        data = self._base()
        data["organizedProducts"] = [
            {"name": "Sin ref", "sku": "", "source": "excel"},
            {"name": "Sin coste", "sku": "NC-1", "netPrice": 10.0, "rrp": 10.0, "source": "excel"},
        ]
        res = de.run_detection(data, persist=False)
        types = {x["type"] for x in res["findings"]}
        self.assertIn("missing_sku", types)
        self.assertIn("missing_cost", types)

    def test_duplicate_customer_and_inconsistent_order_found(self):
        data = self._base()
        data["organizedCustomers"] = [
            {"name": "A", "email": "dup@test.es", "source": "excel"},
            {"name": "B", "email": "dup@test.es", "source": "excel"},
        ]
        data["organizedSales"] = [{
            "id": "O1", "customer": "A", "total": 100.0, "date": _d(2), "source": "excel",
            "line_items": [{"sku": "X", "quantity": 1, "price": 10.0}],
        }]
        res = de.run_detection(data, persist=False)
        types = {x["type"] for x in res["findings"]}
        self.assertIn("duplicate_customer", types)
        self.assertIn("inconsistent_order_total", types)

    def test_clean_data_no_quality_findings(self):
        data = self._base()
        data["organizedProducts"] = [{"name": "A", "sku": "S1", "cost": 5.0, "costSource": "supplier", "costStatus": "verified", "rrp": 10.0, "source": "excel"}]
        data["organizedSales"] = [{
            "id": "O1", "customer": "A", "total": 10.0, "date": _d(2), "source": "excel",
            "line_items": [{"sku": "S1", "quantity": 1, "price": 10.0}],
        }]
        res = de.run_detection(data, persist=False)
        qtypes = {"duplicate_sku", "missing_sku", "duplicate_customer", "missing_cost", "inconsistent_order_total"}
        self.assertEqual({x["type"] for x in res["findings"]} & qtypes, set())

    def test_customer_without_orders_found(self):
        data = self._base()
        data["organizedCustomers"] = [{"name": "Cliente Sin Pedidos", "email": "sin@test.es", "source": "excel", "sourceFile": "clientes.csv"}]
        data["organizedSales"] = [{
            "id": "O1", "customer": "Otro Cliente", "total": 10.0, "date": _d(2), "source": "excel",
            "line_items": [{"sku": "S1", "quantity": 1, "price": 10.0}],
        }]
        res = de.run_detection(data, persist=False)
        f = [x for x in res["findings"] if x["type"] == "customer_no_orders"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["metrics"]["customer"], "Cliente Sin Pedidos")


class MegaUpdateTests(unittest.TestCase):
    """MEGA UPDATE — tests de regresión para A1 (trazabilidad
    proveedor→producto→SKU), A2 (impacto económico cuantificado) y A4
    (ranking de oportunidades por valor económico). UNKNOWN ≠ 0: sin
    evidencia real no se emite ningún finding ni se inventa un importe."""

    # ------------------------------------------------------------------
    # A1 — trazabilidad proveedor → SKU (línea de factura → factura → proveedor)
    # ------------------------------------------------------------------

    def _received_invoices(self):
        return [
            {"id": "F1", "type": "received", "supplierId": "SUP-A", "date": "2026-06-01", "total": 100.0},
            {"id": "F2", "type": "received", "supplierId": "SUP-B", "date": "2026-06-02", "total": 50.0},
        ]

    def test_supplier_sku_traceability_from_invoice_lines(self):
        """A1: la relación proveedor→SKU se reconstruye desde líneas→factura→
        proveedor (los datos que SÍ existen), sin hardcodear proveedores."""
        invoices = self._received_invoices()
        lines = [
            {"invoiceId": "F1", "sku": "S1", "price": 1.0, "quantity": 1},
            {"invoiceId": "F1", "sku": "S2", "price": 1.0, "quantity": 1},
            {"invoiceId": "F1", "sku": "S3", "price": 1.0, "quantity": 1},
            {"invoiceId": "F1", "sku": "S4", "price": 1.0, "quantity": 1},
            {"invoiceId": "F1", "sku": "S5", "price": 1.0, "quantity": 1},
            {"invoiceId": "F1", "sku": "S6", "price": 1.0, "quantity": 1},
            {"invoiceId": "F2", "sku": "S6", "price": 1.0, "quantity": 1},
        ]
        out = bs.supplier_sku_signals(lines, invoices)
        sup_a = next(s for s in out if s["name"] == "SUP-A")
        self.assertEqual(sup_a["skuCount"], 6)
        self.assertEqual(sup_a["totalTrackedSkus"], 6)
        self.assertEqual(sup_a["skuShare"], 1.0)
        # La señal alimenta el detector de dependencia por nº de SKUs
        findings = de.detect_suppliers([], [], out)
        deps = [f for f in findings if f["type"] == "supplier_dependency"]
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["metrics"]["skuCount"], 6)

    def test_supplier_sku_dependency_requires_minimum_evidence(self):
        """A1: dependencia por SKUs exige ≥5 SKUs distintos y ≥40% del catálogo
        de compra. Con 3 SKUs → INSUFFICIENT_EVIDENCE, nunca un finding."""
        supp_skus = [{"name": "SUP-A", "skuCount": 3, "skuShare": 0.30, "totalTrackedSkus": 10}]
        findings = de.detect_suppliers([], [], supp_skus)
        self.assertEqual([f for f in findings if f["type"] == "supplier_dependency"], [])

    def test_supplier_dependency_no_duplicate_when_spend_and_skus_both_fire(self):
        """A1: el mismo proveedor señalado por SKUs y por gasto solo genera un
        finding (sin duplicados)."""
        supp = [{"name": "SUP-A", "spend": 1000.0, "invoices": 3, "spendShare": 0.9}]
        supp_skus = [{"name": "SUP-A", "skuCount": 20, "skuShare": 0.8, "totalTrackedSkus": 25}]
        findings = de.detect_suppliers(supp, [], supp_skus)
        deps = [f for f in findings if f["type"] == "supplier_dependency"]
        self.assertEqual(len(deps), 1)

    def test_supplier_spend_dependency_still_works(self):
        """A1: la dependencia por gasto (≥40% del gasto) se conserva."""
        supp = [{"name": "SUP-B", "spend": 5000.0, "invoices": 5, "spendShare": 0.55}]
        findings = de.detect_suppliers(supp, [], [])
        deps = [f for f in findings if f["type"] == "supplier_dependency"]
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["metrics"]["supplier"], "SUP-B")

    # ------------------------------------------------------------------
    # A2 — impacto económico cuantificado (nunca inventado)
    # ------------------------------------------------------------------

    def test_stockout_impact_quantifies_lost_revenue(self):
        """A2: stockout estima la venta perdida = revenue 30d × fracción de días
        sin cobertura (aritmética sobre datos reales)."""
        prod = [{
            "sku": "x", "hasStock": True, "stock": 5, "velocityPerDay": 2.0,
            "daysOfStock": 2.5, "inventoryValue": 50.0, "revenue30d": 1000.0,
        }]
        findings = de.detect_inventory(prod)
        so = [f for f in findings if f["type"] == "stockout_risk"]
        self.assertEqual(len(so), 1)
        # (14 - 2.5) / 14 = 0.8214 → 821.43 €
        self.assertAlmostEqual(so[0]["metrics"]["lostRevenueEstimate"], 821.43, places=2)
        self.assertEqual(so[0]["estimatedImpact"]["economicImpactEuro"], so[0]["metrics"]["lostRevenueEstimate"])

    def test_stockout_out_of_stock_impact_full_revenue(self):
        """A2: stock a 0 → el 100% del revenue 30d está en riesgo."""
        prod = [{
            "sku": "y", "hasStock": True, "stock": 0, "velocityPerDay": 1.0,
            "daysOfStock": 0, "inventoryValue": 0.0, "revenue30d": 500.0,
        }]
        findings = de.detect_inventory(prod)
        so = [f for f in findings if f["type"] == "stockout_risk"]
        self.assertEqual(len(so), 1)
        self.assertAlmostEqual(so[0]["metrics"]["lostRevenueEstimate"], 500.0)

    def test_churn_impact_quantifies_revenue_at_risk(self):
        """A2: el churn cuantifica el revenue histórico del cliente en riesgo."""
        cust = [{
            "name": "Cliente X", "orders": 5, "revenue": 3000.0,
            "daysSinceLastOrder": 90, "lastOrder": "2026-05-01", "revenueShare": 0.1,
        }]
        findings = de.detect_customers(cust, {})
        ch = [f for f in findings if f["type"] == "customer_churn"]
        self.assertEqual(len(ch), 1)
        self.assertEqual(ch[0]["estimatedImpact"]["revenueAtRisk"], 3000.0)
        self.assertEqual(ch[0]["estimatedImpact"]["economicImpactEuro"], 3000.0)

    def test_churn_requires_recurrence_and_value(self):
        """A2: un cliente con 1 pedido o <200 € no se marca en churn."""
        cust = [{
            "name": "Cliente Y", "orders": 1, "revenue": 50.0,
            "daysSinceLastOrder": 120, "lastOrder": "2026-03-01", "revenueShare": 0.01,
        }]
        findings = de.detect_customers(cust, {})
        self.assertEqual([f for f in findings if f["type"] == "customer_churn"], [])

    def test_supplier_cost_increase_impact_euro_calculated(self):
        """A2: subida de proveedor con unidades conocidas → coste extra €
        CALCULADO (diferencia de precio × unidades)."""
        supp_price = [{
            "name": "SUP-A", "priceTrendPct": 45.0, "trackedSkus": 3,
            "increasingSkus": [{"sku": "S1", "firstPrice": 10.0, "lastPrice": 15.0, "changePct": "+50.0%", "units": 100}],
        }]
        findings = de.detect_suppliers([], supp_price, [])
        inc = [f for f in findings if f["type"] == "supplier_cost_increase"]
        self.assertEqual(len(inc), 1)
        self.assertEqual(inc[0]["estimatedImpact"]["kind"], "calculated")
        self.assertEqual(inc[0]["estimatedImpact"]["economicImpactEuro"], 500.0)  # 5 € × 100 uds
        self.assertEqual(inc[0]["metrics"]["extraCostEuro"], 500.0)

    def test_supplier_increase_without_units_no_invented_euro(self):
        """A2: sin unidades compradas conocidas → se expresa el % sin inventar
        un importe € (UNKNOWN ≠ 0)."""
        supp_price = [{
            "name": "SUP-A", "priceTrendPct": 45.0, "trackedSkus": 1,
            "increasingSkus": [{"sku": "S1", "firstPrice": 10.0, "lastPrice": 15.0, "changePct": "+50.0%", "units": None}],
        }]
        findings = de.detect_suppliers([], supp_price, [])
        inc = [f for f in findings if f["type"] == "supplier_cost_increase"]
        self.assertEqual(len(inc), 1)
        self.assertEqual(inc[0]["estimatedImpact"]["kind"], "estimated")
        self.assertNotIn("economicImpactEuro", inc[0]["estimatedImpact"])
        self.assertIsNone(inc[0]["metrics"]["extraCostEuro"])

    # ------------------------------------------------------------------
    # A4 — ranking de oportunidades por valor económico
    # ------------------------------------------------------------------

    @staticmethod
    def _sig_prod(sku: str, revenue: float, margin: float, share: float):
        return {
            "sku": sku, "revenue": revenue, "revenue30d": revenue, "revenuePrev30d": 0.0,
            "revenuePrev60d": 0.0, "units30d": 0.0, "unitsPrev30d": 0.0, "unitsPrev60d": 0.0,
            "revenueShare": share, "hasCost": True, "marginPct": margin,
        }

    def test_opportunity_cap_keeps_highest_value(self):
        """A4: cuando hay más de 8 oportunidades de "alto margen poco revenue",
        el cap anti-ruido conserva las 8 de MAYOR VALOR (revenue × margen), no
        las primeras encontradas ni las de mayor margen aislado."""
        # 6 productos de relleno (margen bajo, sin finding) bajan el promedio
        prods = [self._sig_prod(f"fill{i}", 500.0, 10.0, 500.0 / 4450.0) for i in range(6)]
        # 10 oportunidades: revenue 100..190 €, margen 70% (todas cualifican)
        prods += [self._sig_prod(f"o{i}", 100.0 + i * 10.0, 70.0, (100.0 + i * 10.0) / 4450.0) for i in range(10)]
        quality = {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "ordersTotal": 100}
        period = {"current30d": ["2026-01-01", "2026-01-30"], "previous30d": ["2025-12-01", "2025-12-30"]}
        findings = de.detect_products(prods, quality, period)
        opps = [f for f in findings if f["type"] == "low_revenue_high_margin"]
        self.assertEqual(len(opps), 8)  # cap activo: >8 → top 8
        kept_skus = {f["metrics"]["sku"] for f in opps}
        self.assertIn("o9", kept_skus)  # el de mayor valor (190 € × 70%) se conserva
        self.assertNotIn("o0", kept_skus)  # el de menor valor (100 € × 70%) se descarta
        self.assertNotIn("o1", kept_skus)

    def test_opportunity_value_beats_margin_only(self):
        """A4: un producto con revenue relevante y margen bueno debe superar a
        uno con margen altísimo pero revenue casi nulo (el caso LH-031 de FASE C)."""
        # Promedio: rellenos bajan el avg para que todo cualifique
        total_rev = 6 * 500.0 + 190.0 + 100.0 + sum(105.0 + 10.0 * i for i in range(7))
        prods = [self._sig_prod(f"fill{i}", 500.0, 10.0, 500.0 / total_rev) for i in range(6)]
        # o-a: revenue 190, margen 70 (valor 13.300) — el que debe ganar
        prods.append(self._sig_prod("o-a", 190.0, 70.0, 190.0 / total_rev))
        # o-b: revenue 100, margen 95 (valor 9.500) — margen mayor pero valor menor
        prods.append(self._sig_prod("o-b", 100.0, 95.0, 100.0 / total_rev))
        # 7 más de relleno-cola (105..165 €, margen 70)
        prods += [self._sig_prod(f"o{i}", 105.0 + 10.0 * i, 70.0, (105.0 + 10.0 * i) / total_rev) for i in range(7)]
        quality = {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "ordersTotal": 100}
        period = {"current30d": ["2026-01-01", "2026-01-30"], "previous30d": ["2025-12-01", "2025-12-30"]}
        findings = de.detect_products(prods, quality, period)
        opps = [f for f in findings if f["type"] == "low_revenue_high_margin"]
        kept_skus = {f["metrics"]["sku"] for f in opps}
        self.assertIn("o-a", kept_skus)  # valor 13.300 → top
        self.assertEqual(len(opps), 8)

    # ------------------------------------------------------------------
    # A3 — plan de acción "Qué hacer hoy" (impacto € × confianza × severidad)
    # ------------------------------------------------------------------

    def test_action_plan_ranks_by_economic_impact(self):
        """A3: el plan de acción prioriza por impacto € × confianza; los
        hallazgos resueltos/archivados se excluyen; sin importe → UNKNOWN (None),
        nunca 0."""
        stored = [
            {"id": "a", "signature": "x:1", "type": "stockout_risk", "category": "problem", "severity": "high", "confidence": "high",
             "title": "stockout", "observation": "", "recommendedAction": "reponer",
             "estimatedImpact": {"kind": "estimated", "economicImpactEuro": 821.0, "explanation": "x"}, "status": "active", "metrics": {}},
            {"id": "b", "signature": "x:2", "type": "customer_churn", "category": "problem", "severity": "low", "confidence": "medium",
             "title": "churn", "observation": "", "recommendedAction": "reactivar",
             "estimatedImpact": {"kind": "estimated", "revenueAtRisk": 3000.0, "explanation": "y"}, "status": "active", "metrics": {}},
            {"id": "c", "signature": "x:3", "type": "expenses_growing", "category": "problem", "severity": "medium", "confidence": "low",
             "title": "gastos", "observation": "", "recommendedAction": "revisar",
             "estimatedImpact": {"kind": "estimated", "explanation": "sin euro"}, "status": "active", "metrics": {}},
            {"id": "d", "signature": "x:4", "type": "resolved_one", "category": "problem", "severity": "high", "confidence": "high",
             "title": "resuelto", "observation": "", "recommendedAction": "",
             "estimatedImpact": {"kind": "estimated", "economicImpactEuro": 99999.0, "explanation": ""}, "status": "resolved", "metrics": {}},
        ]
        with patch.object(de.config_store, "load", return_value={"businessFindings": stored}):
            plan = de.action_plan(limit=5)
        self.assertEqual(len(plan), 3)  # resuelto excluido
        self.assertEqual(plan[0]["type"], "customer_churn")  # 3000 € → primero
        self.assertEqual(plan[0]["impactEuro"], 3000.0)
        self.assertEqual(plan[1]["type"], "stockout_risk")
        self.assertEqual(plan[2]["type"], "expenses_growing")  # sin € → último
        self.assertIsNone(plan[2]["impactEuro"])  # UNKNOWN ≠ 0
        self.assertEqual(plan[0]["recommendedAction"], "reactivar")

    def test_action_plan_empty_when_no_active(self):
        stored = [{"id": "a", "signature": "x:1", "type": "x", "category": "problem", "severity": "high", "confidence": "high",
                   "title": "x", "observation": "", "recommendedAction": "", "estimatedImpact": {}, "status": "resolved", "metrics": {}}]
        with patch.object(de.config_store, "load", return_value={"businessFindings": stored}):
            plan = de.action_plan()
        self.assertEqual(plan, [])

    # ------------------------------------------------------------------
    # A10 — semáforo de salud empresarial (UNKNOWN ≠ 0, resuelto no cuenta)
    # ------------------------------------------------------------------

    @staticmethod
    def _mk_f(fid, ftype, category, severity, status="active", euro=None, key="economicImpactEuro"):
        imp = {"kind": "estimated", "explanation": ""}
        if euro is not None:
            imp[key] = euro
        return {"id": fid, "type": ftype, "category": category, "severity": severity,
                "confidence": "high", "status": status, "title": fid, "observation": "",
                "recommendedAction": "", "estimatedImpact": imp, "metrics": {}}

    def test_health_scores_overall_is_worst_dimension(self):
        stored = [
            self._mk_f("a", "stockout_risk", "problem", "high", euro=821.0),
            self._mk_f("b", "supplier_dependency", "problem", "medium"),
            self._mk_f("c", "customer_churn", "problem", "low", status="resolved", euro=3000.0, key="revenueAtRisk"),
        ]
        q = {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "canAnalyzeTreasury": False, "canAnalyzeExpenses": False, "notes": []}
        hs = de.health_scores(stored, q)
        self.assertEqual(hs["overall"]["state"], "CRITICAL")  # el peor manda
        self.assertEqual(hs["dimensions"]["inventario"]["state"], "CRITICAL")
        self.assertEqual(hs["dimensions"]["proveedores"]["state"], "WARNING")
        self.assertEqual(hs["dimensions"]["clientes"]["state"], "UNKNOWN")  # churn resuelto NO cuenta
        self.assertEqual(hs["dimensions"]["finanzas"]["state"], "UNKNOWN")  # sin datos ≠ GOOD

    def test_health_scores_good_only_with_data(self):
        q = {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "canAnalyzeTreasury": True, "canAnalyzeExpenses": True, "notes": []}
        hs = de.health_scores([], q)
        self.assertEqual(hs["dimensions"]["ventas"]["state"], "GOOD")
        self.assertEqual(hs["dimensions"]["finanzas"]["state"], "GOOD")
        # Sin datos de productos, ventas NO puede ser GOOD
        q_empty = {"canAnalyzeProducts": False, "canAnalyzeMargin": False, "canAnalyzeTreasury": False, "canAnalyzeExpenses": False, "notes": []}
        hs2 = de.health_scores([], q_empty)
        self.assertEqual(hs2["dimensions"]["ventas"]["state"], "UNKNOWN")
        self.assertEqual(hs2["dimensions"]["finanzas"]["state"], "UNKNOWN")

    def test_health_scores_datos_unknown_without_data(self):
        """PRE-BETA: la dimensión Calidad de datos NO puede ser GOOD si no hay
        entidades reales que auditar (instalación nueva). UNKNOWN ≠ GOOD."""
        q_empty = {"canAnalyzeProducts": False, "canAnalyzeMargin": False, "canAnalyzeTreasury": False, "canAnalyzeExpenses": False, "notes": [], "ordersTotal": 0, "productsTotal": 0}
        hs = de.health_scores([], q_empty)
        self.assertEqual(hs["dimensions"]["datos"]["state"], "UNKNOWN")
        # Con entidades reales y sin problemas de calidad → GOOD
        q_data = {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "canAnalyzeTreasury": False, "canAnalyzeExpenses": False, "notes": [], "ordersTotal": 99, "productsTotal": 461}
        hs2 = de.health_scores([], q_data)
        self.assertEqual(hs2["dimensions"]["datos"]["state"], "GOOD")

    # ------------------------------------------------------------------
    # A11 — brief ejecutivo basado en evidencia del motor
    # ------------------------------------------------------------------

    def test_executive_brief_from_evidence(self):
        stored = [
            self._mk_f("a", "stockout_risk", "problem", "high", euro=821.0),
            self._mk_f("d", "low_revenue_high_margin", "opportunity", "medium", euro=5000.0, key="marginPotential"),
            self._mk_f("c", "customer_churn", "problem", "low", status="resolved", euro=9999.0, key="revenueAtRisk"),
        ]
        q = {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "canAnalyzeTreasury": False, "canAnalyzeExpenses": False, "notes": ["muestra insuficiente"]}
        eb = de.executive_brief(stored, q)
        self.assertEqual(eb["health"], "CRITICAL")
        self.assertEqual(eb["topProblem"]["type"], "stockout_risk")
        self.assertEqual(eb["moneyAtRisk"], 821.0)  # el churn resuelto NO suma
        self.assertEqual(eb["topOpportunity"]["type"], "low_revenue_high_margin")
        self.assertEqual(eb["opportunityPotential"], 5000.0)
        self.assertIn("muestra insuficiente", eb["missingInfo"])
        # acción plan: el problema y la oportunidad activos con €; el resuelto NO
        self.assertEqual(len(eb["actionPlan"]), 2)
        self.assertEqual({a["type"] for a in eb["actionPlan"]}, {"stockout_risk", "low_revenue_high_margin"})

    def test_executive_brief_empty_honest(self):
        q = {"canAnalyzeProducts": False, "canAnalyzeMargin": False, "canAnalyzeTreasury": False, "canAnalyzeExpenses": False, "notes": ["sin datos"]}
        eb = de.executive_brief([], q)
        self.assertIsNone(eb["topProblem"])
        self.assertIsNone(eb["topOpportunity"])
        self.assertIsNone(eb["moneyAtRisk"])  # UNKNOWN != 0: sin impacto cuantificado NO es 0
        self.assertIsNone(eb["opportunityPotential"])
        self.assertEqual(eb["actionPlan"], [])

    def test_executive_brief_money_at_risk_none_when_unquantified(self):
        """Validación real: findings sin impacto € cuantificado → moneyAtRisk
        es None (desconocido), NUNCA 0.0. (UNKNOWN != 0.)"""
        stored = [
            self._mk_f("a", "missing_cost", "problem", "high", euro=None),
            self._mk_f("b", "inconsistent_order_total", "problem", "medium", euro=None),
        ]
        q = {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "canAnalyzeTreasury": False, "canAnalyzeExpenses": False, "notes": []}
        eb = de.executive_brief(stored, q)
        self.assertIsNone(eb["moneyAtRisk"])
        self.assertIsNone(eb["opportunityPotential"])

    def test_inconsistent_order_total_prioritizes_largest_delta(self):
        """Validación real: los desvíos se ordenan por magnitud (no por orden
        de lista) para que los casos más graves salgan primero en el tope 5."""
        data = {
            "organizedProducts": [{"name": "P", "sku": "SKU-1", "cost": 1.0, "rrp": 2.0}],
            "organizedSales": [
                {"id": "#A", "total": 10.0, "line_items": [{"price": 9.9, "quantity": 1}], "status": "paid"},
                {"id": "#B", "total": 5.0, "line_items": [{"price": 9.0, "quantity": 1}], "status": "paid"},
                {"id": "#C", "total": 30.0, "line_items": [{"price": 2.0, "quantity": 1}], "status": "paid"},
                {"id": "#D", "total": 8.0, "line_items": [{"price": 1.0, "quantity": 1}], "status": "paid"},
                {"id": "#E", "total": 50.0, "line_items": [{"price": 47.0, "quantity": 1}], "status": "paid"},
                {"id": "#F", "total": 12.0, "line_items": [{"price": 2.0, "quantity": 1}], "status": "paid"},
            ],
            "organizedCustomers": [],
        }
        findings = de.detect_data_quality(data)
        mismatches = [f for f in findings if f.get("type") == "inconsistent_order_total"]
        self.assertEqual(len(mismatches), 5)  # tope anti-ruido
        order_ids = [(f.get("metrics") or {}).get("orderId") for f in mismatches]
        # el mayor desvío (#C: 28.0) debe aparecer primero
        self.assertEqual(order_ids[0], "#C")

    # ------------------------------------------------------------------
    # A9 — eficiencia: los helpers A3/A10/A11 reutilizan datos ya cargados
    # ------------------------------------------------------------------

    def test_helpers_do_not_reload_config_when_data_preloaded(self):
        """A9: action_plan / health_scores / executive_brief NO vuelven a leer
        config cuando el llamador ya les pasa findings y quality (una sola
        lectura por request)."""
        stored = [self._mk_f("a", "stockout_risk", "problem", "high", euro=100.0)]
        q = {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "canAnalyzeTreasury": False, "canAnalyzeExpenses": False, "notes": []}
        calls = {"n": 0}
        with patch.object(de.config_store, "load", side_effect=lambda: calls.__setitem__("n", calls["n"] + 1) or {"businessFindings": stored}):
            de.action_plan(findings=stored)
            de.health_scores(stored, q)
            de.executive_brief(stored, q)
        self.assertEqual(calls["n"], 0)

    def test_opportunity_cap_never_fires_with_few_opportunities(self):
        """A4: con ≤8 oportunidades no se descarta ninguna."""
        prods = [self._sig_prod(f"fill{i}", 500.0, 10.0, 0.05) for i in range(6)]
        prods += [self._sig_prod(f"o{i}", 150.0, 70.0, 150.0 / 3500.0) for i in range(5)]
        quality = {"canAnalyzeProducts": True, "canAnalyzeMargin": True, "ordersTotal": 100}
        period = {"current30d": ["2026-01-01", "2026-01-30"], "previous30d": ["2025-12-01", "2025-12-30"]}
        findings = de.detect_products(prods, quality, period)
        opps = [f for f in findings if f["type"] == "low_revenue_high_margin"]
        self.assertEqual(len(opps), 5)  # ≤8 → sin cap


class LifecycleTests(unittest.TestCase):
    def _run_persisted(self, stored: dict, data: dict):
        captured: dict = {}
        with patch.object(de.config_store, "load", side_effect=lambda: dict(data)), patch.object(
            de.config_store, "save", side_effect=lambda d: captured.update(d)
        ):
            result = de.run_detection(data, persist=True)
        data.update(captured)
        return result

    def test_dedupe_and_times_seen(self):
        data = _rich_data()
        r1 = self._run_persisted({}, data)
        active1 = [f for f in r1["findings"] if f["type"] == "high_revenue_low_margin"]
        self.assertEqual(len(active1), 1)
        r2 = self._run_persisted({}, data)
        active2 = [f for f in r2["findings"] if f["type"] == "high_revenue_low_margin"]
        self.assertEqual(len(active2), 1)  # sin copias
        self.assertEqual(active2[0]["id"], active1[0]["id"])
        self.assertGreaterEqual(active2[0]["timesSeen"], active1[0]["timesSeen"] + 1)

    def test_acknowledged_status_preserved_then_resolved(self):
        data = _rich_data()
        r1 = self._run_persisted({}, data)
        f1 = [f for f in r1["findings"] if f["type"] == "high_revenue_low_margin"][0]
        data.setdefault("businessFindings", [f1])
        r2 = self._run_persisted({}, data)
        f2 = [f for f in r2["findings"] if f["type"] == "high_revenue_low_margin"][0]
        self.assertEqual(f2["status"], f1["status"])  # preservado entre runs

    def test_resolved_reappears_as_active(self):
        data = _rich_data()
        r1 = self._run_persisted({}, data)
        f1 = [f for f in r1["findings"] if f["type"] == "high_revenue_low_margin"][0]
        f1["status"] = "resolved"
        data.setdefault("businessFindings", [f1])
        r2 = self._run_persisted({}, data)
        f2 = [f for f in r2["findings"] if f["type"] == "high_revenue_low_margin"][0]
        self.assertEqual(f2["status"], "active")  # reapareció → vuelve a activo

    def test_update_finding_status(self):
        data = _rich_data()
        r1 = self._run_persisted({}, data)
        f1 = [f for f in r1["findings"] if f["type"] == "high_revenue_low_margin"][0]
        data["businessFindings"] = [f1]
        with patch.object(de.config_store, "load", return_value=data), patch.object(de.config_store, "save", side_effect=lambda d: data.update(d)):
            res = de.update_finding_status(f1["id"], "acknowledged")
        self.assertTrue(res["ok"])
        bad = de.update_finding_status(f1["id"], "noexiste")
        self.assertFalse(bad["ok"])


if __name__ == "__main__":
    unittest.main()
