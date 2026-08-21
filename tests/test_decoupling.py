"""FASE 13 — VANOVA ≠ Shopify: el core no depende de ninguna fuente concreta.

Demuestra (P12) que profitability, detection_engine, identidad, costes,
capabilities y Hermes funcionan con datos de CUALQUIER fuente (CSV/Excel,
ERP, WooCommerce-like, FacturaScripts) o sin Shopify.

Ningún test toca la instalación real: load y save se parchean SIEMPRE.
"""
from __future__ import annotations

import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import (  # noqa: E402
    business_model,
    config_store,
    connector_base,
    detection_engine,
    product_identity,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _csv_catalog() -> list[dict]:
    """Catálogo importado por CSV/Excel (sin Shopify)."""
    return [
        {"sku": "CSV-1", "name": "Producto CSV 1", "netPrice": 6.0, "rrp": 12.0, "source": "excel"},
        {"sku": "CSV-2", "name": "Producto CSV 2", "netPrice": 5.0, "rrp": 10.0, "source": "excel"},
        {"sku": "CSV-3", "name": "Producto CSV 3", "netPrice": 4.0, "rrp": 8.0, "source": "excel"},
    ]


def _erp_catalog() -> list[dict]:
    """Catálogo con coste procedente de ERP (facturascripts-like)."""
    return [
        {"sku": "ERP-1", "name": "Producto ERP 1", "cost": 3.0, "costSource": "facturascripts", "rrp": 12.0},
        {"sku": "ERP-2", "name": "Producto ERP 2", "cost": 2.5, "costSource": "erp", "rrp": 10.0},
    ]


def _csv_sales(n: int = 25) -> list[dict]:
    """Ventas importadas por CSV (filas planas con sku/qty/total, sin Shopify)."""
    rows = []
    now = datetime.now(timezone.utc)
    for i in range(n):
        rows.append({
            "id": f"CSV-O{i}",
            "order_id": f"CSV-O{i}",
            "sku": "CSV-1" if i % 2 == 0 else "CSV-2",
            "qty": 1,
            "total": 12.0 if i % 2 == 0 else 10.0,
            "date": (now - timedelta(days=i % 40)).isoformat(),
            "source": "excel",
        })
    return rows


def _store(**data) -> dict:
    base = {
        "organizedProducts": [],
        "organizedSales": [],
        "organizedInvoices": [],
        "organizedInvoiceLines": [],
        "organizedFinance": [],
        "businessFindings": [],
        "productMappings": [],
        "productIgnoredSkus": [],
    }
    base.update(data)
    return base


def _patch_all(store: dict):
    return [
        patch.object(config_store, "load", side_effect=lambda: dict(store)),
        patch.object(config_store, "save", side_effect=lambda d: store.update(d)),
        patch.object(config_store, "update", side_effect=lambda mut: (mut(store) or store)),
    ]


class CoreWorksWithoutShopify(unittest.TestCase):
    """P12 #1, #2, #7, #8, #9 — el core funciona con CSV/ERP y sin Shopify."""

    def test_profitability_with_csv_only_data(self):
        store = _store(organizedProducts=_csv_catalog(), organizedSales=_csv_sales())
        with ExitStack() as stack:
            for p in _patch_all(store):
                stack.enter_context(p)
            prof = business_model.profitability(dict(store))
        self.assertIsNotNone(prof)
        self.assertGreaterEqual(prof["orders"]["total"], 1)
        # CSV-1/CSV-2: netPrice(6/5) < rrp(12/10) → coste imported disponible
        self.assertGreaterEqual(prof["orders"]["withCost"], 1)

    def test_detection_engine_with_csv_data(self):
        store = _store(organizedProducts=_csv_catalog(), organizedSales=_csv_sales())
        with ExitStack() as stack:
            for p in _patch_all(store):
                stack.enter_context(p)
            r = detection_engine.run_detection(dict(store), persist=False)
        self.assertTrue(r["ok"])
        self.assertIn("canAnalyzeProducts", r["quality"])
        # 25 pedidos con fecha → muestra suficiente para analítica de producto
        self.assertTrue(r["quality"]["canAnalyzeProducts"])

    def test_costs_from_erp(self):
        store = _store(organizedProducts=_erp_catalog())
        with ExitStack() as stack:
            for p in _patch_all(store):
                stack.enter_context(p)
            p1 = _erp_catalog()[0]
            rc = product_identity.resolve_cost(p1)
            self.assertEqual(rc["costStatus"], "verified")
            self.assertEqual(rc["cost"], 3.0)
            self.assertEqual(rc["costSource"], "facturascripts")

    def test_costs_from_excel_without_pvd_equality(self):
        # PVD ≠ coste sin evidencia → no asumir; pero coste explícito de Excel cuenta
        p = {"sku": "X", "name": "X", "cost": 4.0, "costSource": "imported_file", "rrp": 8.0}
        rc = product_identity.resolve_cost(p)
        self.assertEqual(rc["costStatus"], "imported")
        self.assertEqual(rc["cost"], 4.0)

    def test_shopify_disconnected_does_not_break_core(self):
        store = _store(organizedProducts=_csv_catalog(), organizedSales=_csv_sales())
        with ExitStack() as stack:
            for p in _patch_all(store):
                stack.enter_context(p)
            # Sin Shopify conectado, el registro de fuentes no debe romper nada
            caps = connector_base.aggregate_capabilities()
            self.assertFalse(caps["invoices"])  # ninguna fuente da facturas aquí
            # El core sigue respondiendo
            prof = business_model.profitability(dict(store))
            self.assertIsNotNone(prof)


class IdentityMultiSource(unittest.TestCase):
    """P12 #6, #12 — identidad entre dos fuentes; IDs de proveedor no contaminan."""

    def test_identity_between_two_sources(self):
        # Línea de WooCommerce-like con source_variant_id → mismo canónico
        catalog = [
            {"sku": "CANON-1", "name": "Canónico 1", "sourceVariantId": "wc-99", "netPrice": 1.0, "rrp": 2.0},
            {"sku": "CANON-2", "name": "Canónico 2", "shopifyVariantId": "sh-55", "netPrice": 1.0, "rrp": 2.0},
        ]
        woocommerce_line = {"sku": "wc-99", "source_variant_id": "wc-99", "title": "Canónico 1"}
        shopify_line = {"sku": "sh-55", "variant_id": "sh-55", "title": "Canónico 2"}
        iw = product_identity.resolve_identity(woocommerce_line, catalog, [])
        iss = product_identity.resolve_identity(shopify_line, catalog, [])
        self.assertTrue(iw["matched"])
        self.assertTrue(iss["matched"])
        self.assertEqual(iw["canonicalProductId"], "CANON-1")
        self.assertEqual(iss["canonicalProductId"], "CANON-2")

    def test_provider_ids_never_contaminate_canonical(self):
        # El core usa sku canónico; los IDs de proveedor quedan en metadata/identidad
        p = {"sku": "CANON", "name": "P", "shopifyVariantId": "sh-123", "sourceVariantId": "wc-456", "netPrice": 1.0, "rrp": 2.0}
        row = business_model.with_margin(p)
        self.assertEqual(row["sku"], "CANON")
        self.assertNotIn("sh-123", str(row.get("sku")))

    def test_manual_mapping_multi_source_generic(self):
        store = _store()
        with ExitStack() as stack:
            for p in _patch_all(store):
                stack.enter_context(p)
            r = product_identity.add_mapping(source_sku="WC-SKU-9", source="woocommerce", canonical_product_id="CANON-9")
            self.assertTrue(r["ok"])
            m = product_identity.load_mappings()[0]
            self.assertEqual(m["sourceSku"], "WC-SKU-9")
            self.assertEqual(m["source"], "woocommerce")
            self.assertEqual(m["shopifySku"], "WC-SKU-9")  # alias de compatibilidad


class CapabilitiesTests(unittest.TestCase):
    """P12 #10, #11 — capabilities correctas; fuente sin invoices no rompe finance."""

    def test_capabilities_declared_vs_effective(self):
        shop = connector_base.source("shopify")
        fs = connector_base.source("facturascript")
        self.assertTrue(shop.capabilities()["products"])
        self.assertFalse(shop.capabilities()["invoices"])  # Shopify no es ERP
        self.assertTrue(fs.capabilities()["invoices"])     # FS sí las declara
        # Efectivas dependen de conexión real
        eff = fs.effective_capabilities()
        self.assertFalse(eff["invoices"]) if not fs.status().get("connected") else None

    def test_missing_capability_reason_distinguishes_cases(self):
        # Si FS está desconectado, la razón NO es "ninguna fuente la da"
        with ExitStack() as stack:
            for p in _patch_all(_store()):
                stack.enter_context(p)
            reason = connector_base.missing_capability_reason(connector_base.CAP_INVOICES)
            self.assertIn("desconectado", reason.lower())
        # Una capacidad que ninguna fuente declara (p. ej. stock) → otro mensaje
        self.assertIn("proporciona", connector_base.missing_capability_reason(connector_base.CAP_STOCK).lower())

    def test_source_without_invoices_does_not_break_finance(self):
        store = _store(organizedProducts=_csv_catalog(), organizedSales=_csv_sales())
        with ExitStack() as stack:
            for p in _patch_all(store):
                stack.enter_context(p)
            # get_finance_overview-like: sin facturas → honesto, no crash
            from desktop.runtime import agent_data_tools

            fin = agent_data_tools.get_finance_overview()
            self.assertTrue(fin.get("ok"))
            # invoices pendiente = 0 explícito (no se inventa)
            self.assertEqual(fin.get("pendingInvoices", 0), 0)


class HermesMultiSource(unittest.TestCase):
    """P12 #3 — el contexto de Hermes refleja fuentes genéricas, no solo Shopify."""

    def test_hermes_context_shows_sources_and_capabilities(self):
        from desktop.runtime import hermes_chat

        store = _store(organizedProducts=_csv_catalog(), organizedSales=_csv_sales())
        with ExitStack() as stack:
            for p in _patch_all(store):
                stack.enter_context(p)
            ctx = hermes_chat.build_operational_context(include_shopify=True)
        text = ctx["textBlock"]
        self.assertIn("Fuentes de datos", text)
        # El registro incluye fileimport siempre (CSV/Excel)
        self.assertIn("Importación CSV/Excel", text)
        # Capacidades faltantes explicadas (no "FS desconectado" como única causa)
        self.assertIn("CAPACIDADES", text)


if __name__ == "__main__":
    unittest.main()
