"""Tests for Hermes operational context parity (VANOVA UI vs CLI injection)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from desktop.runtime import hermes_chat


class HermesOperationalContextTests(unittest.TestCase):
    def test_build_operational_context_counts_and_lines(self):
        products = [
            {"name": "P1", "source": "local", "sku": "a"},
            {"name": "P2", "source": "local", "sku": "b"},
            {"name": "S1", "source": "shopify", "sku": "c"},
        ]
        sales = [{"id": "1", "source": "shopify"}, {"id": "2", "source": "local"}]
        fake_data = {
            "organizedProducts": products,
            "organizedSales": sales,
            "fileOrganization": {
                "productFiles": 2,
                "salesFiles": 1,
                "message": "Organizados 2 archivos de productos",
            },
            "dashboardSnapshot": {"dataMode": "partial"},
            "scanFiles": [
                {"path": "cat.xlsx", "category": "products"},
                {"path": "sales.csv", "category": "sales"},
            ],
        }
        shop_sync = {
            "connected": True,
            "status": "ok",
            "counts": {"products": 50, "orders": 50},
            "missingScopes": [],
            "url": "https://demo.myshopify.com",
        }
        shop_cfg = {"connected": True, "url": "https://demo.myshopify.com"}
        # H20: el build del contexto pasa por `_ensure_normalized_data`/organize_files,
        # que PERSISTE organized* derivados del load parcheado → `save` es no-op
        # para que el test NUNCA escriba en el config real.
        with patch.object(hermes_chat.config_store, "load", return_value=fake_data), \
             patch.object(hermes_chat.config_store, "save"), \
             patch(
            "desktop.runtime.integrations_store.get_config", return_value=shop_cfg
        ), patch(
            "desktop.runtime.integrations_store.get_shopify_entry", return_value={"source": "hermes-env"}
        ), patch(
            "desktop.runtime.shopify_sync.sync_status", return_value=shop_sync
        ), patch(
            "desktop.runtime.shopify_sync.needs_reauth", return_value=False
        ), patch(
            "desktop.runtime.file_inventory.list_imported_files",
            return_value={"files": fake_data["scanFiles"], "count": 2},
        ), patch(
            "desktop.runtime.hermes_service.status",
            return_value={"healthy": True, "activeModel": "deepseek-v4-flash:cloud", "launchMode": "ollama-launch"},
        ), patch(
            "desktop.runtime.hermes_config.load_config",
            return_value={"model": "deepseek-v4-flash:cloud", "providerId": "ollama"},
        ), patch(
            "desktop.runtime.process_manager.status",
            return_value={"cloud": {"running": True}, "connector": {"running": True}},
        ), patch(
            "desktop.runtime.health_monitor.check_all",
            return_value={
                "components": {
                    "cloud": {"status": "ok", "message": "Online"},
                    "connector": {"status": "ok", "message": "Autenticado"},
                }
            },
        ), patch(
            "desktop.runtime.agent_architect.list_agents",
            return_value=[{"id": "a1", "name": "Analyst", "status": "idle", "statusReason": "Listo"}],
        ):
            ctx = hermes_chat.build_operational_context()

        self.assertIn("[Contexto VANOVA", ctx["textBlock"])
        self.assertEqual(ctx["counts"]["organizedProductsTotal"], 3)
        self.assertEqual(ctx["counts"]["organizedProductsLocal"], 2)
        self.assertEqual(ctx["counts"]["organizedProductsShopify"], 1)
        self.assertEqual(ctx["counts"]["catalogExcelRows"], 2)
        self.assertEqual(ctx["counts"]["shopifySyncedProducts"], 50)
        self.assertEqual(ctx["counts"]["shopifySyncedOrders"], 50)
        self.assertEqual(ctx["summary"]["productos"]["shopifySynced"], 50)
        self.assertTrue(any("dataMode" in ln for ln in ctx["lines"]))
        self.assertTrue(any("50 productos" in ln for ln in ctx["lines"]))

    def test_build_chat_context_uses_text_block(self):
        # FASE 15: "Hola" es casual → ruta ligera sin contexto. Se usa una
        # pregunta de negocio para verificar que el textBlock se inyecta.
        with patch.object(
            hermes_chat,
            "build_operational_context",
            return_value={"textBlock": "[Contexto VANOVA]\n- test"},
        ) as mock_ctx:
            block = hermes_chat._build_chat_context("¿Cuántos pedidos tengo?")
        mock_ctx.assert_called_once_with(include_shopify=False, domain="general")
        self.assertIn("[Contexto VANOVA]", block)
        self.assertIn("no menciones Shopify", block)

    def test_casual_greeting_skips_heavy_context(self):
        with patch.object(hermes_chat, "build_operational_context") as mock_ctx:
            block = hermes_chat._build_chat_context("Hola")
        mock_ctx.assert_not_called()
        self.assertIn("conversación casual", block)

    def test_canonical_invoices_recognized_even_without_live_connector(self):
        """FASE 16 H31 regression: cuando el modelo canónico YA contiene facturas
        y movimientos de tesorería (importados vía CSV/canónico), el contexto de
        Hermes debe decir que ESOS DATOS EXISTEN y que la integración en vivo
        está desconectada — NO negar los datos que el motor de detección ya usa.
        Sin esto, Hermes contradice al motor: detection_engine encuentra
        vencimientos/concentración pero Hermes dice "tesorería no disponible"."""
        products = [{"name": "P1", "source": "local", "sku": "a"}]
        sales = [{"id": "1", "source": "local"}]
        fake_data = {
            "organizedProducts": products,
            "organizedSales": sales,
            "organizedInvoices": [
                {"id": "RCV-1", "type": "received", "total": 500.0, "paid": False, "dueDate": "2099-01-01"},
                {"id": "ISS-1", "type": "issued", "total": 800.0, "paid": True},
            ],
            "organizedFinance": [
                {"id": "c1", "type": "collection", "amount": 100.0},
                {"id": "p1", "type": "payment", "amount": 50.0},
            ],
            "fileOrganization": {"productFiles": 1, "salesFiles": 1},
            "dashboardSnapshot": {"dataMode": "full"},
            "scanFiles": [{"path": "cat.xlsx", "category": "products"}],
        }
        with patch.object(hermes_chat.config_store, "load", return_value=fake_data), \
             patch.object(hermes_chat.config_store, "save"), \
             patch("desktop.runtime.integrations_store.get_config", return_value={}), \
             patch("desktop.runtime.integrations_store.get_shopify_entry", return_value={}), \
             patch("desktop.runtime.shopify_sync.sync_status", return_value={"connected": False, "counts": {}, "missingScopes": []}), \
             patch("desktop.runtime.shopify_sync.needs_reauth", return_value=False), \
             patch("desktop.runtime.file_inventory.list_imported_files", return_value={"files": [], "count": 0}), \
             patch("desktop.runtime.hermes_service.status", return_value={"healthy": True}), \
             patch("desktop.runtime.hermes_config.load_config", return_value={}), \
             patch("desktop.runtime.process_manager.status", return_value={}), \
             patch("desktop.runtime.health_monitor.check_all", return_value={"components": {}}), \
             patch("desktop.runtime.agent_architect.list_agents", return_value=[]):
            ctx = hermes_chat.build_operational_context()

        caps = next((ln for ln in ctx["lines"] if "CAPACIDADES" in ln), "")
        self.assertIn("2 facturas", caps)
        self.assertIn("2 movimientos", caps)
        self.assertIn("modelo canónico", caps)
        self.assertIn("desconectad", caps)

    # ------------------------------------------------------------------
    # FASE HERMES — PRIORIDAD 2: el total NUNCA se presenta como la suma de
    # los meses visibles. Si la muestra mensual no cubre el total, el contexto
    # debe advertirlo explícitamente para que Hermes no fabrique una
    # "evolución" con una ventana parcial.
    # ------------------------------------------------------------------
    def test_monthly_window_note_when_total_exceeds_visible_months(self):
        products = [{"name": "P1", "source": "local", "sku": "a"}]
        sales = [{"id": "1", "source": "local"}]
        fake_data = {
            "organizedProducts": products,
            "organizedSales": sales,
            "fileOrganization": {"productFiles": 1, "salesFiles": 1},
            "dashboardSnapshot": {"dataMode": "full"},
            "scanFiles": [],
        }
        # 4 meses con datos; la suma de los 3 visibles (650) NO es el total
        # (1000) → debe aparecer la NOTA de ventana.
        sm = {
            "orders": 10,
            "revenue": 1000.0,
            "byMonth": [
                {"period": "2026-06", "revenue": 100.0, "orders": 2},
                {"period": "2026-07", "revenue": 200.0, "orders": 3},
                {"period": "2026-08", "revenue": 150.0, "orders": 1},
                {"period": "2026-09", "revenue": 300.0, "orders": 2},
            ],
        }
        with patch.object(hermes_chat.config_store, "load", return_value=fake_data), \
             patch.object(hermes_chat.config_store, "save"), \
             patch("desktop.runtime.integrations_store.get_config", return_value={}), \
             patch("desktop.runtime.integrations_store.get_shopify_entry", return_value={}), \
             patch("desktop.runtime.shopify_sync.sync_status", return_value={"connected": False, "counts": {}, "missingScopes": []}), \
             patch("desktop.runtime.shopify_sync.needs_reauth", return_value=False), \
             patch("desktop.runtime.file_inventory.list_imported_files", return_value={"files": [], "count": 0}), \
             patch("desktop.runtime.hermes_service.status", return_value={"healthy": True}), \
             patch("desktop.runtime.hermes_config.load_config", return_value={}), \
             patch("desktop.runtime.process_manager.status", return_value={}), \
             patch("desktop.runtime.health_monitor.check_all", return_value={"components": {}}), \
             patch("desktop.runtime.agent_architect.list_agents", return_value=[]), \
             patch("desktop.runtime.business_model.sales_summary", return_value=sm):
            ctx = hermes_chat.build_operational_context()

        lines = ctx["lines"]
        self.assertTrue(any("TODO el histórico importado" in ln for ln in lines))
        self.assertTrue(any("NOTA de ventana" in ln for ln in lines))
        note = next(ln for ln in lines if "NOTA de ventana" in ln)
        self.assertIn("NO es el total", note)
        self.assertIn("tendencia completa", note)

    def test_no_window_note_when_visible_months_cover_total(self):
        products = [{"name": "P1", "source": "local", "sku": "a"}]
        sales = [{"id": "1", "source": "local"}]
        fake_data = {
            "organizedProducts": products,
            "organizedSales": sales,
            "fileOrganization": {"productFiles": 1, "salesFiles": 1},
            "dashboardSnapshot": {"dataMode": "full"},
            "scanFiles": [],
        }
        sm = {
            "orders": 3,
            "revenue": 450.0,
            "byMonth": [
                {"period": "2026-07", "revenue": 200.0, "orders": 1},
                {"period": "2026-08", "revenue": 250.0, "orders": 2},
            ],
        }
        with patch.object(hermes_chat.config_store, "load", return_value=fake_data), \
             patch.object(hermes_chat.config_store, "save"), \
             patch("desktop.runtime.integrations_store.get_config", return_value={}), \
             patch("desktop.runtime.integrations_store.get_shopify_entry", return_value={}), \
             patch("desktop.runtime.shopify_sync.sync_status", return_value={"connected": False, "counts": {}, "missingScopes": []}), \
             patch("desktop.runtime.shopify_sync.needs_reauth", return_value=False), \
             patch("desktop.runtime.file_inventory.list_imported_files", return_value={"files": [], "count": 0}), \
             patch("desktop.runtime.hermes_service.status", return_value={"healthy": True}), \
             patch("desktop.runtime.hermes_config.load_config", return_value={}), \
             patch("desktop.runtime.process_manager.status", return_value={}), \
             patch("desktop.runtime.health_monitor.check_all", return_value={"components": {}}), \
             patch("desktop.runtime.agent_architect.list_agents", return_value=[]), \
             patch("desktop.runtime.business_model.sales_summary", return_value=sm):
            ctx = hermes_chat.build_operational_context()

        self.assertFalse(any("NOTA de ventana" in ln for ln in ctx["lines"]))

    # ------------------------------------------------------------------
    # FASE HERMES — PRIORIDAD 7: DATA COVERAGE con estados por dominio.
    # ------------------------------------------------------------------
    def test_data_coverage_block_present_with_statuses(self):
        products = [{"name": "P1", "source": "local", "sku": "a"}]
        sales = [{"id": "1", "source": "local"}]
        fake_data = {
            "organizedProducts": products,
            "organizedSales": sales,
            "fileOrganization": {"productFiles": 1, "salesFiles": 1},
            "dashboardSnapshot": {"dataMode": "full"},
            "scanFiles": [],
        }
        with patch.object(hermes_chat.config_store, "load", return_value=fake_data), \
             patch.object(hermes_chat.config_store, "save"), \
             patch("desktop.runtime.integrations_store.get_config", return_value={}), \
             patch("desktop.runtime.integrations_store.get_shopify_entry", return_value={}), \
             patch("desktop.runtime.shopify_sync.sync_status", return_value={"connected": False, "counts": {}, "missingScopes": []}), \
             patch("desktop.runtime.shopify_sync.needs_reauth", return_value=False), \
             patch("desktop.runtime.file_inventory.list_imported_files", return_value={"files": [], "count": 0}), \
             patch("desktop.runtime.hermes_service.status", return_value={"healthy": True}), \
             patch("desktop.runtime.hermes_config.load_config", return_value={}), \
             patch("desktop.runtime.process_manager.status", return_value={}), \
             patch("desktop.runtime.health_monitor.check_all", return_value={"components": {}}), \
             patch("desktop.runtime.agent_architect.list_agents", return_value=[]):
            ctx = hermes_chat.build_operational_context()

        lines = ctx["lines"]
        self.assertTrue(any("DATA COVERAGE" in ln for ln in lines))
        joined = "\n".join(lines)
        self.assertIn("· Ventas: DISPONIBLE", joined)
        self.assertIn("· Costes: PARTIAL", joined)
        self.assertIn("· Identidad: PARTIAL", joined)
        self.assertIn("· Facturas/Tesorería: NO DISPONIBLE", joined)
        self.assertIn("no digas 0 €", joined)

    # ------------------------------------------------------------------
    # FASE HERMES — PRIORIDAD 5/3/4: instrucciones de estilo ejecutivo y
    # separación HECHO / INFERENCIA / NO DISPONIBLE.
    # ------------------------------------------------------------------
    def test_executive_style_and_logic_instructions_present(self):
        products = [{"name": "P1", "source": "local", "sku": "a"}]
        sales = [{"id": "1", "source": "local"}]
        fake_data = {
            "organizedProducts": products,
            "organizedSales": sales,
            "fileOrganization": {"productFiles": 1, "salesFiles": 1},
            "dashboardSnapshot": {"dataMode": "full"},
            "scanFiles": [],
        }
        with patch.object(hermes_chat.config_store, "load", return_value=fake_data), \
             patch.object(hermes_chat.config_store, "save"), \
             patch("desktop.runtime.integrations_store.get_config", return_value={}), \
             patch("desktop.runtime.integrations_store.get_shopify_entry", return_value={}), \
             patch("desktop.runtime.shopify_sync.sync_status", return_value={"connected": False, "counts": {}, "missingScopes": []}), \
             patch("desktop.runtime.shopify_sync.needs_reauth", return_value=False), \
             patch("desktop.runtime.file_inventory.list_imported_files", return_value={"files": [], "count": 0}), \
             patch("desktop.runtime.hermes_service.status", return_value={"healthy": True}), \
             patch("desktop.runtime.hermes_config.load_config", return_value={}), \
             patch("desktop.runtime.process_manager.status", return_value={}), \
             patch("desktop.runtime.health_monitor.check_all", return_value={"components": {}}), \
             patch("desktop.runtime.agent_architect.list_agents", return_value=[]):
            ctx = hermes_chat.build_operational_context()

        joined = "\n".join(ctx["lines"])
        self.assertIn("ESTADO GENERAL", joined)
        self.assertIn("SIGUIENTE ACCIÓN", joined)
        self.assertIn("HECHO", joined)
        self.assertIn("INFERENCIA", joined)
        self.assertIn("NO DISPONIBLE", joined)
        self.assertIn("Correlación ≠ causalidad", joined)

    # ------------------------------------------------------------------
    # FASE 14 (auditoría pre-release): DATA HEALTH — Hermes debe saber qué
    # entidades están LEGACY / NEEDS_REVIEW / INVALID y NO presentarlas como
    # hechos confirmados.
    # ------------------------------------------------------------------
    def test_data_health_line_when_review_entities_exist(self):
        products = [{"name": "P1", "source": "local", "sku": "a"}]
        sales = [{"id": "1", "source": "local"}]
        fake_data = {
            "organizedProducts": products,
            "organizedSales": sales,
            "fileOrganization": {"productFiles": 1, "salesFiles": 1},
            "dashboardSnapshot": {"dataMode": "full"},
            "scanFiles": [],
        }
        with patch.object(hermes_chat.config_store, "load", return_value=fake_data), \
             patch.object(hermes_chat.config_store, "save"), \
             patch("desktop.runtime.integrations_store.get_config", return_value={}), \
             patch("desktop.runtime.integrations_store.get_shopify_entry", return_value={}), \
             patch("desktop.runtime.shopify_sync.sync_status", return_value={"connected": False, "counts": {}, "missingScopes": []}), \
             patch("desktop.runtime.shopify_sync.needs_reauth", return_value=False), \
             patch("desktop.runtime.file_inventory.list_imported_files", return_value={"files": [], "count": 0}), \
             patch("desktop.runtime.hermes_service.status", return_value={"healthy": True}), \
             patch("desktop.runtime.hermes_config.load_config", return_value={}), \
             patch("desktop.runtime.process_manager.status", return_value={}), \
             patch("desktop.runtime.health_monitor.check_all", return_value={"components": {}}), \
             patch("desktop.runtime.agent_architect.list_agents", return_value=[]), \
             patch("desktop.runtime.data_governance._review_counts",
                   return_value={"needs_review": 12, "legacy": 4, "invalid": 1, "total": 17}):
            ctx = hermes_chat.build_operational_context()

        lines = ctx["lines"]
        health = next((ln for ln in lines if "SALUD DE DATOS" in ln), "")
        self.assertIn("12 entidades requieren revisión", health)
        self.assertIn("4 datos heredados", health)
        self.assertIn("1 son inválidas", health)
        self.assertIn("no las presentes como hechos confirmados", health.lower())

    def test_no_data_health_line_when_all_verified(self):
        products = [{"name": "P1", "source": "local", "sku": "a"}]
        sales = [{"id": "1", "source": "local"}]
        fake_data = {
            "organizedProducts": products,
            "organizedSales": sales,
            "fileOrganization": {"productFiles": 1, "salesFiles": 1},
            "dashboardSnapshot": {"dataMode": "full"},
            "scanFiles": [],
        }
        with patch.object(hermes_chat.config_store, "load", return_value=fake_data), \
             patch.object(hermes_chat.config_store, "save"), \
             patch("desktop.runtime.integrations_store.get_config", return_value={}), \
             patch("desktop.runtime.integrations_store.get_shopify_entry", return_value={}), \
             patch("desktop.runtime.shopify_sync.sync_status", return_value={"connected": False, "counts": {}, "missingScopes": []}), \
             patch("desktop.runtime.shopify_sync.needs_reauth", return_value=False), \
             patch("desktop.runtime.file_inventory.list_imported_files", return_value={"files": [], "count": 0}), \
             patch("desktop.runtime.hermes_service.status", return_value={"healthy": True}), \
             patch("desktop.runtime.hermes_config.load_config", return_value={}), \
             patch("desktop.runtime.process_manager.status", return_value={}), \
             patch("desktop.runtime.health_monitor.check_all", return_value={"components": {}}), \
             patch("desktop.runtime.agent_architect.list_agents", return_value=[]), \
             patch("desktop.runtime.data_governance._review_counts",
                   return_value={"needs_review": 0, "legacy": 0, "invalid": 0, "total": 0}):
            ctx = hermes_chat.build_operational_context()

        self.assertFalse(any("SALUD DE DATOS" in ln for ln in ctx["lines"]))

    # ------------------------------------------------------------------
    # MEGA UPDATE (A11) — brief ejecutivo en el contexto de Hermes
    # ------------------------------------------------------------------
    def test_render_context_block_includes_executive_brief_from_engine(self):
        from desktop.runtime import agent_data_tools

        brief = {
            "ok": True, "health": "CRITICAL", "healthLabel": "Inventario",
            "moneyAtRisk": 821.0,
            "topProblem": {"title": "x en riesgo de rotura de stock", "observation": "x tiene 5 uds"},
            "topOpportunity": {"title": "y alto margen", "observation": "y margen 45%"},
            "missingInfo": ["sin coste de 3 productos"],
        }
        cc = {"coveragePct": 41.6, "revenueWithVerifiedCost": 10.0, "revenueWithMissingCost": 14.0}
        ic = {"coveragePct": 75.2, "matchedLines": 10, "unmatchedLines": 3}
        with patch("desktop.runtime.product_identity.cost_coverage") as mock_cc, \
             patch("desktop.runtime.product_identity.identity_coverage") as mock_ic, \
             patch("desktop.runtime.detection_engine.list_findings",
                   return_value={"findings": [], "executiveBrief": brief}):
            block = agent_data_tools.render_context_block(limit=5, precomputed_coverage={"cc": cc, "ic": ic})
        mock_cc.assert_not_called()  # coberturas precalculadas: sin recalcular
        self.assertIn("SALUD GENERAL", block)
        self.assertIn("CRITICAL", block)
        self.assertIn("821.00 €", block)  # dinero en riesgo
        self.assertIn("MAYOR PROBLEMA", block)
        self.assertIn("MAYOR OPORTUNIDAD", block)
        self.assertIn("PARA ANALIZAR MEJOR FALTA", block)

    # ------------------------------------------------------------------
    # FASE HERMES — PRIORIDAD 1: render_context_block NO recalcula las
    # coberturas cuando el llamador se las pasa precalculadas (dedup).
    # ------------------------------------------------------------------
    def test_render_context_block_reuses_precomputed_coverage(self):
        from unittest.mock import MagicMock
        from desktop.runtime import agent_data_tools

        cc = {"coveragePct": 41.6, "revenueWithVerifiedCost": 10.0, "revenueWithMissingCost": 14.0}
        ic = {"coveragePct": 75.2, "matchedLines": 10, "unmatchedLines": 3}
        # list_findings llama internamente a cost_coverage (motor de detección);
        # se neutraliza para aislar SOLO la sección de cobertura de este bloque.
        with patch("desktop.runtime.product_identity.cost_coverage") as mock_cc, \
             patch("desktop.runtime.product_identity.identity_coverage") as mock_ic, \
             patch("desktop.runtime.detection_engine.list_findings", return_value={"findings": []}):
            block = agent_data_tools.render_context_block(limit=5, precomputed_coverage={"cc": cc, "ic": ic})
        mock_cc.assert_not_called()
        mock_ic.assert_not_called()
        # El llamador ya escribe la línea CALIDAD DE DATOS → no debe duplicarse
        self.assertNotIn("CALIDAD DE DATOS", block)

    def test_render_context_block_computes_without_precomputed(self):
        from unittest.mock import MagicMock
        from desktop.runtime import agent_data_tools

        cc = {"coveragePct": 0.0, "revenueWithVerifiedCost": 0.0, "revenueWithMissingCost": 0.0}
        ic = {"coveragePct": 0.0, "matchedLines": 0, "unmatchedLines": 0}
        with patch("desktop.runtime.product_identity.cost_coverage", return_value=cc) as mock_cc, \
             patch("desktop.runtime.product_identity.identity_coverage", return_value=ic) as mock_ic, \
             patch("desktop.runtime.detection_engine.list_findings", return_value={"findings": []}):
            block = agent_data_tools.render_context_block(limit=5)
        mock_cc.assert_called_once()
        mock_ic.assert_called_once()
        self.assertIn("CALIDAD DE DATOS", block)


if __name__ == "__main__":
    unittest.main()
