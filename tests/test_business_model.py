"""FASE 3 — tests del modelo de datos canónico (business_model).

Cubre: validación de entidades (los errores de integración nunca entran al
modelo), margen canónico (una sola definición), resumen de ventas de fuente
única, y el informe de integridad (duplicados, entidades corruptas,
reconciliación agregados-vs-datos originales).
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from desktop.runtime import business_model


class ValidationTests(unittest.TestCase):
    def test_error_payloads_rejected_generically(self):
        # Unknown error message — must NOT pass just because it is not in a list.
        for row in (
            {"name": "Faltan permisos de Shopify", "netPrice": 1, "rrp": 2},
            {"name": "Error de conexión con la API", "netPrice": 1},
            {"name": "producto normal", "netPrice": 1, "rrp": 2},
        ):
            ok, _ = business_model.validate_product(row)
        self.assertFalse(business_model.validate_product({"name": "Faltan permisos de Shopify", "netPrice": 1})[0])
        self.assertFalse(business_model.validate_product({"name": "No se pudieron descargar datos de shopify"})[0])
        self.assertTrue(business_model.validate_product({"name": "Agenda 2026", "sku": "AG1", "netPrice": 1, "rrp": 2})[0])

    def test_metadata_only_payload_rejected(self):
        self.assertTrue(business_model.is_error_payload({"status": "error", "message": "API key inválida"}))
        self.assertTrue(business_model.is_error_payload({"error": "timeout"}))
        self.assertFalse(business_model.is_error_payload({"name": "Agenda", "sku": "A1", "total": 10}))

    def test_product_non_numeric_prices_rejected(self):
        ok, _ = business_model.validate_product({"name": "X", "netPrice": "faltan permisos", "rrp": "2"})
        self.assertFalse(ok)

    def test_sale_and_customer_validation(self):
        self.assertTrue(business_model.validate_sale({"order_id": "O1", "total": 10.0, "date": "2026-01-01"})[0])
        self.assertFalse(business_model.validate_sale({"order_id": "O2", "total": "error"})[0])
        self.assertTrue(business_model.validate_customer({"name": "Acme", "email": "a@b.c"})[0])
        self.assertFalse(business_model.validate_customer({"status": "error"})[0])

    def test_invoice_and_cash_validation(self):
        good_invoice = {"id": "1", "code": "F1", "type": "issued", "total": 121.0, "date": "2026-01-01"}
        self.assertTrue(business_model.validate_invoice(good_invoice)[0])
        self.assertFalse(business_model.validate_invoice({**good_invoice, "type": "otro"})[0])
        self.assertFalse(business_model.validate_invoice({**good_invoice, "total": "error"})[0])
        self.assertTrue(business_model.validate_cash_row({"id": "c1", "type": "collection", "amount": 50.0})[0])
        self.assertFalse(business_model.validate_cash_row({"id": "c2", "type": "collection", "amount": "nope"})[0])


class CanonicalMetricsTests(unittest.TestCase):
    def test_margin_canonical_definition(self):
        m = business_model.margin(1.0, 2.5)
        self.assertEqual(m["margin"], 1.5)
        self.assertEqual(m["marginPct"], 60.0)  # ON SALE PRICE — same as dashboard
        self.assertEqual(m["markupPct"], 150.0)  # ON COST — explicit, not ambiguous

    def test_margin_none_safe(self):
        self.assertEqual(business_model.margin(None, 2.5)["marginPct"], None)
        self.assertEqual(business_model.margin(1.0, 0)["marginPct"], None)

    def test_sales_summary_matches_raw_totals(self):
        sales = [
            {"order_id": "O1", "total": 100.0, "date": "2026-01-15"},
            {"order_id": "O2", "total": 50.0, "date": "2026-01-20"},
        ]
        summary = business_model.sales_summary(sales)
        self.assertEqual(summary["orders"], 2)
        self.assertEqual(summary["revenue"], 150.0)
        # Sales are in Jan, today is 2026-08 → current-month is empty, year is full
        self.assertIsNone(summary["month"]["revenue"])
        self.assertEqual(summary["year"]["revenue"], 150.0)
        self.assertEqual(summary["byMonth"], [{"period": "2026-01", "revenue": 150.0, "orders": 2}])


class IntegrityReportTests(unittest.TestCase):
    def _clean_data(self):
        return {
            "organizedProducts": [
                {"name": "Agenda", "sku": "A1", "netPrice": 1.0, "rrp": 2.0},
                {"name": "Bolígrafo", "sku": "B1", "netPrice": 0.5, "rrp": 1.0},
            ],
            "organizedSales": [
                {"order_id": "O1", "total": 30.0, "date": "2026-01-15"},
                {"order_id": "O2", "total": 60.0, "date": "2026-02-01"},
            ],
            "dashboardSnapshot": {
                "overview": {"orders": 2, "revenue": 90.0},
                "dataMode": "real",
            },
            "organizedInvoices": [],
            "organizedFinance": [],
        }

    def test_clean_model_passes(self):
        report = business_model.integrity_report(self._clean_data())
        self.assertTrue(report["ok"])
        self.assertEqual(report["issues"], [])

    def test_error_entity_detected(self):
        data = self._clean_data()
        data["organizedProducts"].append({"name": "Faltan permisos de Shopify", "netPrice": 1, "rrp": 2})
        report = business_model.integrity_report(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("entidad inválida" in i["detail"] for i in report["issues"]))

    def test_duplicates_detected(self):
        data = self._clean_data()
        data["organizedSales"].append({"order_id": "O1", "total": 30.0, "date": "2026-01-15"})
        report = business_model.integrity_report(data)
        self.assertTrue(any("duplicado" in i["detail"] for i in report["issues"]))

    def test_snapshot_vs_raw_reconciliation(self):
        data = self._clean_data()
        # Snapshot says €14.200 while raw sales sum €90 — the exact "dashboard
        # dice una cosa y Hermes otra" failure mode.
        data["dashboardSnapshot"]["overview"]["revenue"] = 14200.0
        report = business_model.integrity_report(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("revenue del snapshot" in i["detail"] for i in report["issues"]))

    def test_provenance_stamping(self):
        row = business_model.stamp({"name": "X"}, "shopify", fetched_at="2026-08-16T10:00:00+00:00")
        self.assertEqual(row["_source"], "shopify")
        self.assertEqual(row["_fetchedAt"], "2026-08-16T10:00:00+00:00")
        self.assertEqual(row["_updatedAt"], "2026-08-16T10:00:00+00:00")
        self.assertTrue(row["_validated"])


class ReconciliationTests(unittest.TestCase):
    def _data(self):
        return {
            "organizedInvoices": [
                {"id": "101", "code": "F1", "type": "issued", "net": 100.0, "total": 121.0, "paid": False, "date": "2026-07-01"},
                {"id": "7", "code": "FP-7", "type": "received", "net": 55.0, "total": 55.0, "paid": True, "date": "2026-06-15"},
            ],
            "organizedInvoiceLines": [
                {"id": "issued:1", "invoiceId": "101", "invoiceType": "issued", "lineTotal": 100.0},
                {"id": "received:1", "invoiceId": "7", "invoiceType": "received", "lineTotal": 55.0},
            ],
            "organizedSales": [],
        }

    def test_lines_match_invoice_net_no_issue(self):
        report = business_model.financial_reconciliation(self._data())
        self.assertTrue(report["ok"])
        self.assertEqual(report["items"], [])

    def test_mismatch_registered_not_corrected(self):
        data = self._data()
        data["organizedInvoiceLines"][0]["lineTotal"] = 80.0  # Σ 80 ≠ neto 100
        report = business_model.financial_reconciliation(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("Σ líneas 80.0 ≠ neto factura 100.0" in i["detail"] for i in report["items"]))

    def test_invoice_without_lines_flagged_low(self):
        data = self._data()
        data["organizedInvoiceLines"] = [data["organizedInvoiceLines"][0]]
        report = business_model.financial_reconciliation(data)
        self.assertTrue(any("sin líneas" in i["detail"] for i in report["items"]))

    def test_period_reconciliation_cross_source(self):
        data = self._data()
        data["organizedSales"] = [{"order_id": "O1", "total": 121.0, "date": "2026-07-01"}]
        report = business_model.financial_reconciliation(data)
        # issued 121.0 vs sales 121.0 → coincide, sin issue
        self.assertFalse(any(i["scope"] == "period_reconciliation" for i in report["items"]))
        data["organizedSales"] = [{"order_id": "O1", "total": 50.0, "date": "2026-07-01"}]
        report2 = business_model.financial_reconciliation(data)
        self.assertTrue(any(i["scope"] == "period_reconciliation" for i in report2["items"]))


class InvoiceLineRelationTests(unittest.TestCase):
    def test_match_by_sku_never_by_name(self):
        products = [{"sku": "AG1", "name": "Agenda", "netPrice": 30.0}]
        rel = business_model.resolve_line_product({"sku": "ag1", "description": "Nombre totalmente distinto"}, products)
        self.assertTrue(rel["productMatched"])
        self.assertEqual(rel["cost"], 30.0)
        self.assertEqual(rel["matchReason"], "match por SKU")

    def test_unmatched_declared_explicitly(self):
        rel = business_model.resolve_line_product({"sku": "NOEXISTE"}, [{"sku": "AG1", "name": "Agenda"}])
        self.assertFalse(rel["productMatched"])
        self.assertIn("NOEXISTE", rel["matchReason"])

    def test_line_without_sku_declared(self):
        rel = business_model.resolve_line_product({"description": "solo texto"}, [])
        self.assertFalse(rel["productMatched"])
        self.assertIn("no trae referencia", rel["matchReason"])


class ProfitabilityTests(unittest.TestCase):
    def test_margin_and_markup_separated_per_product(self):
        data = {
            "organizedProducts": [
                {"name": "Agenda", "sku": "AG1", "netPrice": 30.0, "rrp": 60.0},
                {"name": "Boli", "sku": "B1", "netPrice": 5.0, "rrp": 10.0},
            ],
            "organizedSales": [
                {
                    "order_id": "O1",
                    "line_items": [
                        {"sku": "AG1", "title": "Agenda", "quantity": 2, "price": 60.0},
                        {"sku": "B1", "title": "Boli", "quantity": 1, "price": 10.0},
                    ],
                }
            ],
        }
        report = business_model.profitability(data)
        by_sku = {p["sku"]: p for p in report["products"]}
        ag = by_sku["AG1"]
        self.assertEqual(ag["revenue"], 120.0)
        self.assertEqual(ag["cost"], 60.0)
        self.assertEqual(ag["margin"], 60.0)
        self.assertEqual(ag["marginPct"], 50.0)  # on sale price
        self.assertEqual(ag["markupPct"], 100.0)  # on cost
        self.assertEqual(report["orders"]["total"], 1)
        self.assertEqual(report["orders"]["withCost"], 1)

    def test_margin_from_invoice_lines(self):
        """P1: cadena Factura → Línea → SKU → Coste → Margen desde facturas."""
        data = {
            "organizedProducts": [{"name": "Agenda", "sku": "AG1", "netPrice": 30.0}],
            "organizedSales": [],
            "organizedInvoiceLines": [
                {"id": "issued:1", "invoiceId": "101", "invoiceType": "issued", "sku": "AG1", "quantity": 2, "lineTotal": 100.0},
                {"id": "issued:2", "invoiceId": "101", "invoiceType": "issued", "sku": "SINCOSTE", "quantity": 1, "lineTotal": 10.0},
            ],
        }
        report = business_model.profitability(data)
        by_sku = {p["sku"]: p for p in report["products"]}
        ag = by_sku["AG1"]
        self.assertEqual(ag["revenue"], 100.0)
        self.assertEqual(ag["cost"], 60.0)
        self.assertEqual(ag["margin"], 40.0)
        self.assertEqual(ag["marginPct"], 40.0)
        self.assertEqual(ag["sources"], ["invoice_lines"])
        self.assertEqual(by_sku["SINCOSTE"]["costCoverage"], "missing")

    def test_orders_without_cost_declared_not_invented(self):
        data = {
            "organizedProducts": [{"name": "Agenda", "sku": "AG1", "netPrice": 30.0}],
            "organizedSales": [
                {"order_id": "O1", "line_items": [{"sku": "DESCONOCIDO", "quantity": 1, "price": 10.0}]}
            ],
        }
        report = business_model.profitability(data)
        self.assertEqual(report["orders"]["withCost"], 0)
        # El producto se declara con su revenue y costCoverage "missing" — nunca
        # se inventa un coste ni se calcula un margen sin él.
        self.assertEqual(len(report["products"]), 1)
        p = report["products"][0]
        self.assertEqual(p["costCoverage"], "missing")
        self.assertIsNone(p["margin"])
        self.assertIsNone(p["marginPct"])

    def test_revenue_excludes_invalid_rows(self):
        """B-01 (auditoría comercial): las filas inválidas (fecha imposible,
        total negativo, total no numérico) NUNCA contribuyen al revenue."""
        sales = [
            {"order_id": "O1", "total": 100.0, "date": "2026-01-15"},
            {"order_id": "O2", "total": 95.0, "date": "2026-01-20"},
            {"order_id": "O3", "total": 100.0, "date": "2026-02-01"},
            {"order_id": "BAD-1", "total": 100.0, "date": "2026-13-45"},   # fecha imposible
            {"order_id": "BAD-2", "total": -100.0, "date": "2026-01-10"},  # total negativo
            {"order_id": "BAD-3", "total": "abc", "date": "2026-01-11"},  # total no numérico
        ]
        self.assertEqual(business_model.revenue(sales), 295.0)
        self.assertIsNone(business_model.sale_validation_issue(sales[0]))
        self.assertIsNotNone(business_model.sale_validation_issue(sales[3]))
        self.assertIsNotNone(business_model.sale_validation_issue(sales[4]))
        self.assertIsNotNone(business_model.sale_validation_issue(sales[5]))

    def test_revenue_total_matches_period_breakdown(self):
        """B-01: revenue(Todo) == Σ revenue(periodos) cuando todas las filas
        válidas están dentro del rango (coherencia total vs desglose)."""
        sales = [
            {"order_id": "O1", "total": 100.0, "date": "2026-01-15"},
            {"order_id": "O2", "total": 95.0, "date": "2026-01-20"},
            {"order_id": "O3", "total": 100.0, "date": "2026-02-01"},
            {"order_id": "BAD", "total": 999.0, "date": "no-es-fecha"},
        ]
        summary = business_model.sales_summary(sales)
        total = business_model.revenue(sales)
        period_sum = round(sum(m["revenue"] for m in summary["byMonth"]), 2)
        self.assertEqual(total, 295.0)
        self.assertEqual(period_sum, 295.0)
        self.assertEqual(summary["orders"], 4)  # filas físicas, no revenue

    def test_period_revenue_string_totals_consistent_with_total(self):
        """VANOVA 3.0: un total en STRING parseable ("10.5", decimal europeo
        "5,50") debe sumar igual en Todo/Mes/Trimestre/Año que en revenue().
        Antes month/year saltaban los strings → total 36 € pero mes 20 €."""
        sales = [
            {"id": "S1", "total": "10.5", "date": "2026-08-01"},
            {"id": "S2", "total": 20.0, "date": "2026-08-02"},
            {"id": "S3", "total": "5,50", "date": "2026-08-03"},
        ]
        s = business_model.sales_summary(sales, products=[])
        self.assertEqual(s["revenue"], 36.0)
        self.assertEqual(s["month"]["revenue"], 36.0)
        self.assertEqual(s["year"]["revenue"], 36.0)
        self.assertEqual(s["byMonth"][0]["revenue"], 36.0)
        self.assertEqual(sum(m["revenue"] for m in s["byMonth"]), s["revenue"])

    def test_quarter_revenue_matches_month_sum(self):
        """VANOVA 3.0: Trimestre = Σ de los meses del trimestre (misma
        validez, mismos totales parseados)."""
        from datetime import datetime

        now = datetime.now()
        q_month = f"{now.year}-{((now.month - 1) // 3) * 3 + 1:02d}"
        sales = [
            {"id": "A", "total": "12.5", "date": f"{q_month}-01"},
            {"id": "B", "total": 7.5, "date": f"{q_month}-15"},
            {"id": "C", "total": "20", "date": f"{q_month}-20"},
        ]
        s = business_model.sales_summary(sales, products=[])
        self.assertIsNotNone(s["quarter"]["revenue"])
        self.assertEqual(s["quarter"]["revenue"], 40.0)
        self.assertEqual(s["quarter"]["orders"], 3)
        self.assertEqual(s["quarter"]["revenue"], s["revenue"])

    def test_period_revenue_excludes_invalid_rows_everywhere(self):
        """VANOVA 3.0: las filas inválidas se excluyen del TODO y de CADA
        periodo — ninguna vista puede mostrar un total distinto."""
        sales = [
            {"id": "A", "total": 100.0, "date": "2026-08-01"},
            {"id": "BAD", "total": -50.0, "date": "2026-08-02"},
            {"id": "BAD2", "total": "abc", "date": "2026-08-03"},
            {"id": "BAD3", "total": 999.0, "date": "no-es-fecha"},
        ]
        s = business_model.sales_summary(sales, products=[])
        self.assertEqual(s["revenue"], 100.0)
        self.assertEqual(s["month"]["revenue"], 100.0)
        self.assertEqual(s["year"]["revenue"], 100.0)
        self.assertEqual(sum(m["revenue"] for m in s["byMonth"]), 100.0)
        # Los pedidos físicos siguen contándose (4 filas), el revenue no se inventa.
        self.assertEqual(s["orders"], 4)

    def test_sales_summary_with_current_month_orders_no_crash(self):
        """H18 regression: `sales_summary` usaba una variable inexistente (`t`)
        al sumar el revenue del mes, rompiendo /api/integrity con datos reales
        (99 pedidos). El resumen debe devolver el revenue real del mes."""
        from datetime import datetime

        now = datetime.now()
        month = now.strftime("%Y-%m")
        sales = [
            {"id": "A", "total": 100.0, "date": f"{month}-01", "source": "shopify"},
            {"id": "B", "total": 50.5, "date": f"{month}-05", "source": "shopify"},
            {"id": "C", "total": None, "date": f"{month}-10", "source": "shopify"},
        ]
        summary = business_model.sales_summary(sales, products=[])
        self.assertEqual(summary["orders"], 3)
        self.assertEqual(summary["month"]["revenue"], 150.5)
        self.assertEqual(summary["year"]["revenue"], 150.5)
        self.assertIsNotNone(summary["byMonth"])
        # El reporte de integridad (agregados vs raw) también debe correr sin crash
        report = business_model.integrity_report({"organizedSales": sales, "organizedProducts": []})
        self.assertTrue(report["ok"])


class PeriodRevenueTests(unittest.TestCase):
    """VANOVA PROACTIVA — revenue temporal (hoy/semana/mes/trimestre/año/total)
    con comparación honesta vs periodo anterior (nunca inventa variación)."""

    def _fixed_now(self):
        # Miércoles 2026-08-19 (semana ISO W34)
        from datetime import datetime

        return datetime(2026, 8, 19, 12, 0, 0)

    def test_periods_match_expected_buckets(self):
        now = self._fixed_now()
        sales = [
            # hoy (19/08)
            {"id": "H1", "total": 100.0, "date": "2026-08-19"},
            {"id": "H2", "total": 50.0, "date": "2026-08-19"},
            # esta semana (lunes 17/08 - domingo 23/08)
            {"id": "W1", "total": 30.0, "date": "2026-08-17"},
            # este mes
            {"id": "M1", "total": 20.0, "date": "2026-08-05"},
            # este trimestre (Q3)
            {"id": "Q1", "total": 10.0, "date": "2026-07-01"},
            # este año
            {"id": "Y1", "total": 5.0, "date": "2026-01-15"},
            # inválida (no cuenta en NINGÚN periodo)
            {"id": "BAD", "total": 999.0, "date": "no-es-fecha"},
        ]
        pr = business_model.period_revenue(sales, now=now)
        self.assertEqual(pr["today"]["revenue"], 150.0)
        self.assertEqual(pr["today"]["orders"], 2)
        self.assertEqual(pr["today"]["avgTicket"], 75.0)
        self.assertEqual(pr["week"]["revenue"], 180.0)      # 100+50+30
        self.assertEqual(pr["week"]["orders"], 3)
        self.assertEqual(pr["month"]["revenue"], 200.0)     # +20
        self.assertEqual(pr["quarter"]["revenue"], 210.0)   # +10
        self.assertEqual(pr["year"]["revenue"], 215.0)      # +5
        self.assertEqual(pr["total"]["revenue"], 215.0)
        self.assertIsNone(pr["total"]["changePct"])
        self.assertFalse(pr["total"]["comparable"])

    def test_comparison_with_previous_period(self):
        now = self._fixed_now()
        sales = [
            # mes anterior (julio) 1000 €
            {"id": "PM", "total": 1000.0, "date": "2026-07-10"},
            # este mes 1100 € → +10%
            {"id": "M1", "total": 1100.0, "date": "2026-08-10"},
        ]
        pr = business_model.period_revenue(sales, now=now)
        self.assertEqual(pr["month"]["revenue"], 1100.0)
        self.assertEqual(pr["month"]["prevRevenue"], 1000.0)
        self.assertEqual(pr["month"]["changePct"], 10.0)
        self.assertTrue(pr["month"]["comparable"])
        self.assertIsNone(pr["month"]["comparisonNote"])

    def test_no_previous_data_is_honest(self):
        """Sin datos del periodo anterior → comparable=False y note explícito
        (UNKNOWN ≠ 0, nunca se inventa un −100% ni un 0%)."""
        now = self._fixed_now()
        sales = [
            {"id": "M1", "total": 500.0, "date": "2026-08-10"},
        ]
        pr = business_model.period_revenue(sales, now=now)
        self.assertEqual(pr["month"]["revenue"], 500.0)
        self.assertIsNone(pr["month"]["prevRevenue"])
        self.assertIsNone(pr["month"]["changePct"])
        self.assertFalse(pr["month"]["comparable"])
        self.assertEqual(pr["month"]["comparisonNote"], "Sin datos suficientes para comparar")

    def test_invalid_rows_never_enter_any_period(self):
        now = self._fixed_now()
        sales = [
            {"id": "M1", "total": 100.0, "date": "2026-08-10"},
            {"id": "NEG", "total": -10.0, "date": "2026-08-11"},
            {"id": "NAN", "total": "abc", "date": "2026-08-12"},
            {"id": "FUT", "total": 999.0, "date": "2026-08-32"},  # fecha imposible
        ]
        pr = business_model.period_revenue(sales, now=now)
        self.assertEqual(pr["month"]["revenue"], 100.0)
        self.assertEqual(pr["total"]["revenue"], 100.0)
        self.assertEqual(pr["month"]["orders"], 1)

    def test_week_uses_calendar_week(self):
        """'Esta semana' = semana natural (lunes-domingo); la del lunes 17/08
        pertenece a la semana actual (W34), no a la anterior."""
        now = self._fixed_now()
        sales = [
            {"id": "MON", "total": 40.0, "date": "2026-08-17"},
            {"id": "WED", "total": 60.0, "date": "2026-08-19"},
            {"id": "PWMON", "total": 25.0, "date": "2026-08-10"},  # semana anterior
        ]
        pr = business_model.period_revenue(sales, now=now)
        self.assertEqual(pr["week"]["revenue"], 100.0)
        self.assertEqual(pr["week"]["prevRevenue"], 25.0)
        self.assertEqual(pr["week"]["changePct"], 300.0)


if __name__ == "__main__":
    unittest.main()
