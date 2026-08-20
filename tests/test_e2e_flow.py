"""FASE 9 — E2E del flujo completo de VANOVA (sandbox, sin red real).

Flujo verificado de principio a fin:

  Conectar Shopify → Sincronizar → Backfill → Validar → Calcular métricas
  → Conectar FacturaScripts → Sincronizar → Reconciliar → Actualizar dashboard
  → Generar findings → Consultar Hermes → Mostrar recomendación

Cada paso usa la MISMA fuente de verdad en memoria (config_store parcheado), y
el test comprueba que los datos son idénticos en todas las capas.
"""
from __future__ import annotations

import datetime as _dt_mod
import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import agent_data_tools, business_model, config_store, detection_engine, facturascripts_sync as fs, shopify_sync

from test_facturascripts_sync import _FakeClient, _cfg, _full_payloads

URL = "https://demo.myshopify.com"
TOKEN = "shpat_e2e_token"

# FASE B (fix de determinismo): `_shopify_orders()` generaba fechas relativas a
# `datetime.now()`, por lo que el número de pedidos de julio (y la expectativa
# de reconciliación "ventas julio = 480 €") cambiaba según el día en que se
# ejecutase la suite. Se congela la fecha para que el flujo E2E sea reproducible.
_FIXED_NOW = _dt_mod.datetime(2026, 8, 16, 12, 0, 0)





def _shopify_products():
    """6 SKUs con coste (netPrice) y precio (rrp). A caro → margen bajo."""
    rows = []
    for sku, net, rrp in [
        ("A", 9.0, 10.0), ("B", 1.0, 10.0), ("C", 1.0, 10.0),
        ("D", 1.0, 10.0), ("E", 1.0, 10.0), ("F", 1.0, 10.0),
    ]:
        rows.append({"title": sku, "variants": [{"sku": sku, "price": str(rrp)}]})
    return rows


def _shopify_orders():
    """40 pedidos en los últimos 45 días SIN line_items (simula datos legacy).
    Fecha base FIJA (_FIXED_NOW) para que la reconciliación julio=480 € sea
    determinista y no dependa del día en que se ejecute la suite."""
    from datetime import timedelta

    now = _FIXED_NOW
    orders = []
    for i in range(40):
        date = (now - timedelta(days=i % 45)).isoformat() + "Z"
        orders.append({
            "id": 1000 + i,
            "name": f"#E2E-{i:04d}",
            "total_price": "20.00",
            "created_at": date,
        })
    return orders


def _lines_for(order_name: str) -> dict:
    """Líneas deterministas por pedido. A+B co-comprados en 10 pedidos para
    cross-selling; los 6 SKUs con coste aparecen (muestra de margen ≥5);
    X en caída (pedidos 30-39 previos, 5-8 actuales)."""
    idx = int(order_name.split("-")[1])
    lines = []
    # A en 15 pedidos; A+B juntos en 10 de ellos (cross-selling)
    if idx % 15 < 15:
        lines.append({"title": "A", "quantity": 1, "price": "10.00", "variant": {"sku": "A"}})
        if idx % 15 < 10:
            lines.append({"title": "B", "quantity": 1, "price": "10.00", "variant": {"sku": "B"}})
    # Un SKU base rotatorio (B..F) en cada pedido → los 6 productos venden
    base = ["B", "C", "D", "E", "F"][idx % 5]
    lines.append({"title": base, "quantity": 1, "price": "10.00", "variant": {"sku": base}})
    # X: solo en pedidos 30..39 (previos) y 5..8 (actuales) — caída real
    if 30 <= idx < 50:
        lines.append({"title": "X", "quantity": 1, "price": "10.00", "variant": {"sku": "X"}})
    return {"orders": [{"name": order_name, "line_items": lines}]}


class E2EFlowTests(unittest.TestCase):
    def setUp(self):
        self.store: dict = {}

    def _patch_store(self):
        return [
            patch.object(config_store, "load", side_effect=lambda: dict(self.store)),
            patch.object(config_store, "save", side_effect=lambda d: self.store.update(d)),
        ]

    def test_full_flow_shopify_to_hermes(self):
        # ---- 1. Conectar Shopify (credenciales simuladas) ----
        with ExitStack() as stack:
            stack.enter_context(patch.object(shopify_sync.integrations_store, "get_shopify_credentials", return_value={"url": URL, "token": TOKEN}))
            stack.enter_context(patch.object(shopify_sync.integrations_store, "sync_shopify_from_hermes_if_needed"))
            stack.enter_context(patch.object(shopify_sync, "check_credentials", return_value={"ok": True, "missingScopes": []}))
            stack.enter_context(patch.object(shopify_sync, "_shopify_get_all", side_effect=lambda url, token, path, limit=250: _shopify_products() if "products" in path else _shopify_orders()))
            stack.enter_context(patch.object(shopify_sync, "_shopify_get", side_effect=lambda url, token, path: _lines_for(path.split("name=")[1].split("&")[0].replace("%23", "#"))))
            for p in self._patch_store():
                stack.enter_context(p)

            # ---- 2. Sincronizar (con backfill automático de datos legacy) ----
            r = shopify_sync.sync_now()
            self.assertTrue(r["ok"])
            self.assertEqual(len(self.store["organizedProducts"]), 6)
            self.assertEqual(len(self.store["organizedSales"]), 40)
            # La sync detectó pedidos legacy sin líneas y el backfill automático
            # los recuperó al vuelo (sin re-descargar el catálogo)
            bf_status = self.store["shopifySync"].get("backfill", {})
            self.assertEqual(bf_status.get("updated"), 40)
            self.assertEqual(bf_status.get("failed"), 0)

            # ---- 3. Backfill explícito: idempotente (nada que hacer) ----
            bf = shopify_sync.backfill_line_items()
            self.assertTrue(bf["ok"])
            self.assertEqual(bf["candidates"], 0)
            self.assertEqual(bf["updated"], 0)
            sales = self.store["organizedSales"]
            self.assertTrue(all(s.get("line_items") for s in sales))
            by_id = {s["id"]: s for s in sales}
            # Relación pedido → línea → SKU → cantidad → precio
            s0 = by_id["#E2E-0000"]
            self.assertEqual(s0["line_items"][0]["sku"], "A")
            self.assertEqual(s0["line_items"][0]["quantity"], 1)
            self.assertEqual(s0["line_items"][0]["price"], 10.0)
            # Campos originales intactos
            self.assertEqual(s0["total"], 20.0)
            self.assertIsNotNone(s0["date"])

            # ---- 4. Validar ----
            rep = business_model.integrity_report(self.store)
            self.assertTrue(rep["ok"])
            self.assertEqual(rep["issues"], [])

            # ---- 5. Calcular métricas (margen y markup separados) ----
            # Shopify no expone costes: vienen del catálogo local (Excel).
            # Lo simulamos sobre los productos ya sincronizados.
            for p in self.store["organizedProducts"]:
                p["netPrice"] = 9.0 if p["sku"] == "A" else 1.0
            prof = business_model.profitability(self.store)
            rows = {p["sku"]: p for p in prof["products"]}
            self.assertIn("A", rows)
            self.assertEqual(rows["A"]["marginPct"], 10.0)   # (10-9)/10
            self.assertEqual(rows["A"]["markupPct"], 11.1)   # (10-9)/9
            self.assertEqual(rows["B"]["marginPct"], 90.0)
            summary = business_model.sales_summary(self.store["organizedSales"], products=self.store["organizedProducts"])
            self.assertEqual(summary["orders"], 40)

        # ---- 6. Conectar FacturaScripts + Sincronizar ----
        fs_client = _FakeClient(_full_payloads())
        with ExitStack() as stack:
            stack.enter_context(patch.object(fs.integrations_store, "get_config", return_value=_cfg()))
            stack.enter_context(patch("httpx.Client", return_value=fs_client))
            for p in self._patch_store():
                stack.enter_context(p)
            rfs = fs.sync_now()
            self.assertTrue(rfs["ok"])
            self.assertEqual(len(self.store["organizedInvoices"]), 2)   # 1 emitida + 1 recibida
            self.assertEqual(len(self.store["organizedInvoiceLines"]), 2)
            self.assertEqual(len(self.store["organizedFinance"]), 2)    # 1 cobro + 1 pago
            self.assertGreaterEqual(len(self.store["organizedSuppliers"]), 1)

            # ---- 7. Reconciliar (sin corregir en silencio) ----
            rec = business_model.financial_reconciliation(self.store)
            # Σ líneas (100.00) = neto factura emitida (100.00) → sin issue de líneas
            line_issues = [i for i in rec["items"] if i["scope"] == "invoice_lines"]
            self.assertEqual([i for i in line_issues if i["severity"] in ("high", "medium")], [])

            # Ventas julio (480€) ≠ facturación emitida (121€): conceptos
            # distintos, pero la diferencia se DETECTA, se cuantifica y se
            # explica — nunca se corrige el dato.
            period = [i for i in rec["items"] if i["scope"] == "period_reconciliation"]
            self.assertEqual(len(period), 1)
            self.assertEqual(period[0]["severity"], "medium")
            self.assertEqual(period[0]["expected"], 480.0)   # ventas
            self.assertEqual(period[0]["actual"], 121.0)      # facturas emitidas
            self.assertIn("ventas", period[0]["sources"])
            self.assertIn("facturascript", period[0]["sources"])

            # ---- 8. Actualizar dashboard (fuente única canónica) ----
            fin = agent_data_tools.get_finance_overview()
            self.assertTrue(fin["ok"])
            self.assertEqual(fin["invoices"]["issued"], 1)
            self.assertEqual(fin["invoices"]["received"], 1)
            self.assertEqual(fin["invoices"]["issuedTotal"], 121.0)

        # ---- 9. Generar findings (motor determinista) ----
        with ExitStack() as stack:
            for p in self._patch_store():
                stack.enter_context(p)
            res = detection_engine.run_detection(self.store, persist=True)
            types = {f["type"] for f in res["findings"]}
            # Con 40 pedidos recientes + costes + co-compra A+B + caída de X
            self.assertIn("cross_sell", types)
            self.assertIn("product_declining", types)
            self.assertIn("high_revenue_low_margin", types)
            # Cada finding lleva evidencia + acción + impacto etiquetado
            for f in res["findings"]:
                self.assertTrue(f["evidence"])
                self.assertTrue(f["recommendedAction"])
                self.assertIn(f["estimatedImpact"]["kind"], ("calculated", "estimated"))
                self.assertTrue(f["source"])

            # ---- 10. Consultar Hermes (mismos números que el modelo) ----
            sales_tool = agent_data_tools.call_tool("get_sales", {"limit": 50})
            self.assertEqual(sales_tool["summary"]["orders"], 40)
            prof_tool = agent_data_tools.call_tool("get_profitability", {})
            # 6 de Shopify + 2 de líneas de factura FS (AG1, PAP)
            self.assertEqual(len(prof_tool["products"]), 8)
            self.assertTrue(any(p["sku"] == "A" for p in prof_tool["products"]))
            fin_tool = agent_data_tools.call_tool("get_finance_overview", {})
            self.assertEqual(fin_tool["invoices"]["issued"], 1)
            findings_tool = agent_data_tools.call_tool("get_business_findings", {"limit": 50})
            self.assertGreater(findings_tool["count"], 0)
            # ---- 11. Recomendación accionable (no genérica) ----
            cross = [f for f in findings_tool["findings"] if f["type"] == "cross_sell"]
            self.assertTrue(cross)
            self.assertIn("aparecen juntos", cross[0]["observation"])


if __name__ == "__main__":
    unittest.main()
