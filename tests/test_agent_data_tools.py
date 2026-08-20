"""Tests for agent_data_tools — the single source of truth agents consult."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from desktop.runtime import agent_data_tools


def _sample_data():
    return {
        "organizedProducts": [
            {"name": "Post-it 3M", "sku": "SKU1", "netPrice": 1.0, "rrp": 2.5, "source": "excel"},
            {"name": "Bolígrafo BIC", "sku": "SKU2", "netPrice": 0.5, "rrp": 1.25, "source": "excel"},
            {"name": "Nota adhesiva", "sku": "", "netPrice": None, "rrp": None, "source": "excel"},
            {"name": "faltan permisos de shopify", "sku": "X", "netPrice": 1, "rrp": 2, "source": "shopify"},
        ],
        "organizedSales": [
            {"order_id": "O1", "customer": "Acme", "total": 99.5, "date": "2026-01-15", "source": "excel"},
            {"order_id": "O2", "customer": "Beta", "total": 50.0, "date": "2026-02-01", "source": "excel"},
        ],
    }


class AgentDataToolsTests(unittest.TestCase):
    def setUp(self):
        # H20: las tools de datos pasan por `file_organizer._ensure_normalized_data`,
        # que puede PERSISTIR organized* derivados del load parcheado. El test
        # NUNCA debe escribir en el config real → `save` siempre es no-op.
        self._save_patch = patch.object(agent_data_tools.config_store, "save")
        self._save_patch.start()

    def tearDown(self):
        self._save_patch.stop()

    def test_get_products_excludes_integration_errors(self):
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()):
            res = agent_data_tools.get_products()
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 3)  # 4 rows, 1 is a Shopify permission error string
        skus = [p["sku"] for p in res["products"]]
        self.assertIn("SKU1", skus)
        self.assertNotIn("X", skus)

    def test_product_by_sku_and_prices_with_margin(self):
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()):
            by = agent_data_tools.get_product_by_sku("sku1")
        self.assertTrue(by["ok"])
        self.assertEqual(by["product"]["netPrice"], 1.0)
        self.assertEqual(by["product"]["rrp"], 2.5)
        self.assertEqual(by["product"]["margin"], 1.5)
        # FASE 3: canonical margin definition = gross margin ON SALE PRICE,
        # the same one the dashboard uses. (Before: markup on cost = 150%.)
        self.assertEqual(by["product"]["marginPct"], 60.0)
        self.assertEqual(by["product"]["markupPct"], 150.0)

        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()):
            pr = agent_data_tools.get_product_prices("SKU2")
        self.assertTrue(pr["ok"])
        self.assertEqual(pr["costPrice"], 0.5)
        self.assertEqual(pr["salePrice"], 1.25)
        self.assertEqual(pr["marginPct"], 60.0)
        self.assertEqual(pr["markupPct"], 150.0)

    def test_product_by_sku_missing(self):
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()):
            res = agent_data_tools.get_product_by_sku("NOEXISTE")
        self.assertFalse(res["ok"])
        self.assertIn("noexiste", res["error"].lower())

    def test_availability_reports_exactly_what_exists(self):
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            av = agent_data_tools.availability()
        self.assertTrue(av["products"]["available"])
        self.assertEqual(av["products"]["count"], 3)
        self.assertEqual(av["products"]["withCostPrice"], 2)
        self.assertEqual(av["products"]["withSalePrice"], 2)
        self.assertTrue(av["sales"]["available"])
        self.assertEqual(av["sales"]["count"], 2)
        self.assertEqual(av["sales"]["revenue"], 149.5)

    def test_availability_empty_when_no_data(self):
        with patch.object(agent_data_tools.config_store, "load", return_value={}), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            av = agent_data_tools.availability()
        self.assertFalse(av["products"]["available"])
        self.assertFalse(av["sales"]["available"])

    def test_sales_range_filter(self):
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()):
            res = agent_data_tools.get_sales(start="2026-01-01", end="2026-01-31")
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["sales"][0]["order_id"], "O1")

    def test_product_performance_honest_when_no_sku_per_line(self):
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()):
            perf = agent_data_tools.get_product_performance()
        self.assertEqual(perf["count"], 0)
        self.assertIn("no puedo desglosar", perf["note"])

    def test_product_performance_expands_shopify_line_items(self):
        """Regression (Sales Analyst): orders with per-line SKU+qty must yield a
        real top-seller ranking, not an honest "no puedo" message."""
        data = {
            "organizedSales": [
                {
                    "id": "#1001",
                    "customer": "Maria",
                    "total": 53.22,
                    "date": "2026-08-15",
                    "line_items": [
                        {"sku": "SKU-AGENDA", "title": "Agenda 2026", "quantity": 2, "price": 4.47},
                        {"sku": "SKU-BOLI", "title": "Bolígrafo BIC", "quantity": 3, "price": 1.25},
                    ],
                    "source": "shopify",
                },
                {
                    "id": "#1002",
                    "customer": "Pablo",
                    "total": 8.94,
                    "date": "2026-08-16",
                    "line_items": [
                        {"sku": "SKU-AGENDA", "title": "Agenda 2026", "quantity": 2, "price": 4.47},
                    ],
                    "source": "shopify",
                },
            ]
        }
        with patch.object(agent_data_tools.config_store, "load", return_value=data):
            perf = agent_data_tools.get_product_performance()
        self.assertEqual(perf["count"], 2)
        by_sku = {p["sku"]: p for p in perf["performance"]}
        self.assertEqual(by_sku["SKU-AGENDA"]["units"], 4)
        self.assertEqual(by_sku["SKU-AGENDA"]["revenue"], 17.88)
        self.assertEqual(by_sku["SKU-BOLI"]["units"], 3)
        self.assertEqual(by_sku["SKU-BOLI"]["revenue"], 3.75)
        # FASE 13: etiqueta genérica de fuente (no hardcodea Shopify)
        self.assertEqual(perf["source"], "line_items de pedidos")

    def test_context_block_contains_real_rows_and_never_asks_to_upload(self):
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            block = agent_data_tools.render_context_block(limit=10)
        self.assertIn("SKU1", block)
        self.assertIn("coste=1.00", block)
        self.assertIn("PVD=2.50", block)
        self.assertIn("O1", block)
        self.assertIn("pida", block.lower())
        self.assertIn("no pidas al usuario que suba archivos", block.lower())

    # ------------------------------------------------------------------
    # MEGA UPDATE (A6) — contexto selectivo por dominio de la pregunta
    # ------------------------------------------------------------------

    def test_question_domain_classifier_conservative(self):
        self.assertEqual(agent_data_tools._question_domain(""), "general")
        self.assertEqual(agent_data_tools._question_domain("¿cómo va todo?"), "general")
        self.assertEqual(agent_data_tools._question_domain("¿cómo está mi empresa?"), "general")
        self.assertEqual(agent_data_tools._question_domain("¿quienes son mis mejores clientes?"), "customer")
        self.assertEqual(agent_data_tools._question_domain("¿qué proveedor me cuesta más?"), "supplier")
        self.assertEqual(agent_data_tools._question_domain("¿cómo está mi tesorería?"), "finance")
        self.assertEqual(agent_data_tools._question_domain("¿tengo riesgo de quedarme sin stock?"), "stock")
        self.assertEqual(agent_data_tools._question_domain("¿qué productos venden más?"), "product")

    def test_context_block_drops_product_rows_for_customer_questions(self):
        """A6: una pregunta de clientes NO arrastra las 30 filas de producto
        (ruido) pero conserva el resumen y el resto del bloque."""
        data = _sample_data()
        data["organizedProducts"] = [
            {"name": f"Prod {i}", "sku": f"SKU{i:04d}", "netPrice": 1.0, "rrp": 2.5, "source": "excel"}
            for i in range(40)
        ]
        with patch.object(agent_data_tools.config_store, "load", return_value=data), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            general = agent_data_tools.render_context_block(domain="general")
            customer = agent_data_tools.render_context_block(domain="customer")
        # El resumen de productos (conteo) se conserva en ambos
        self.assertIn("Productos: 40 filas", general)
        self.assertIn("Productos: 40 filas", customer)
        # Las filas individuales de producto solo están en el contexto general
        self.assertIn("coste=1.00", general)
        self.assertNotIn("coste=1.00", customer)
        # Las ventas (pedidos) se conservan para la pregunta de clientes
        self.assertIn("O1", customer)

    def test_context_block_keeps_product_rows_for_product_questions(self):
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            block = agent_data_tools.render_context_block(domain="product")
        self.assertIn("coste=1.00", block)
        self.assertIn("PVD=2.50", block)

    def test_call_tool_dispatcher(self):
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            res = agent_data_tools.call_tool("get_products")
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 3)
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            av = agent_data_tools.call_tool("data_availability")
        self.assertTrue(av["ok"])
        self.assertIn("availability", av)
        bad = agent_data_tools.call_tool("no_such_tool")
        self.assertFalse(bad["ok"])

    def test_task_retry_resolution(self):
        """_resolve_claimed_missing_data returns real rows when the model claims
        missing data that actually exists, and nothing when it truly lacks it."""
        from desktop.runtime.task_queue import _resolve_claimed_missing_data

        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            extra = _resolve_claimed_missing_data("no tengo precios por SKU, necesito un CSV")
        self.assertIn("PRODUCTOS REALES", extra)
        self.assertIn("SKU1", extra)
        # Sales exist but the claim is only about prices — no sales block needed
        with patch.object(agent_data_tools.config_store, "load", return_value=_sample_data()), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            extra2 = _resolve_claimed_missing_data("no tengo nada de nada")
        self.assertNotIn("PRODUCTOS REALES", extra2)

    # ------------------------------------------------------------------
    # H1: the catalog must NEVER be silently truncated. Agents previously
    # saw 400 rows when 461 existed and presented that as the total.
    # ------------------------------------------------------------------

    def test_catalog_never_truncated_above_real_business_scale(self):
        data = _sample_data()
        data["organizedProducts"] = [
            {"name": f"Prod {i}", "sku": f"SKU{i:04d}", "netPrice": 1.0, "rrp": 2.5, "source": "excel"}
            for i in range(461)  # > the old 400 cap — the exact reported bug
        ]
        with patch.object(agent_data_tools.config_store, "load", return_value=data), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            res = agent_data_tools.get_products()
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 461)
        self.assertEqual(len(res["products"]), 461)

    def test_availability_counts_are_honest_not_capped(self):
        data = _sample_data()
        data["organizedProducts"] = [
            {"name": f"Prod {i}", "sku": f"SKU{i:04d}", "netPrice": 1.0, "rrp": 2.5, "source": "excel"}
            for i in range(461)
        ]
        with patch.object(agent_data_tools.config_store, "load", return_value=data), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            av = agent_data_tools.availability()
        self.assertEqual(av["products"]["count"], 461)
        self.assertEqual(av["products"]["withCostPrice"], 461)
        self.assertEqual(av["products"]["withSalePrice"], 461)

    def test_sales_never_truncated(self):
        data = _sample_data()
        data["organizedSales"] = [
            {"order_id": f"O{i:04d}", "customer": f"C{i}", "total": 10.0, "date": "2026-01-01", "source": "excel"}
            for i in range(450)
        ]
        with patch.object(agent_data_tools.config_store, "load", return_value=data), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            res = agent_data_tools.get_sales()
        self.assertEqual(res["count"], 450)
        self.assertEqual(len(res["sales"]), 450)

    def test_render_context_block_reports_real_total(self):
        data = _sample_data()
        data["organizedProducts"] = [
            {"name": f"Prod {i}", "sku": f"SKU{i:04d}", "netPrice": 1.0, "rrp": 2.5, "source": "excel"}
            for i in range(461)
        ]
        with patch.object(agent_data_tools.config_store, "load", return_value=data), patch.object(
            agent_data_tools.file_inventory, "list_imported_files", return_value={"files": []}
        ):
            block = agent_data_tools.render_context_block()
        self.assertIn("Productos: 461 filas", block)


if __name__ == "__main__":
    unittest.main()
