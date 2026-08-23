"""Regression contract tests for the VANOVA UX flows.

These tests intentionally cover the seams between the runtime data contract and
its rendered views. They do not replace a browser smoke test, but they prevent
small releases from silently dropping the fields that make the UI live.
"""
from __future__ import annotations

import re
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.runtime.task_queue import _is_internal_task


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "web" / "dashboard.html"
SERVICES = ROOT / "web" / "data-services.js"
THEMES = ROOT / "web" / "themes.js"


class CrossViewSyncContractTests(unittest.TestCase):
    def test_internal_context_work_is_not_a_user_task(self):
        self.assertTrue(_is_internal_task({"id": "x", "type": "scheduled"}))
        self.assertTrue(_is_internal_task({"id": "x", "type": "manual", "payload": {"origin": "hermes_context"}}))
        self.assertTrue(_is_internal_task({"id": "x", "type": "manual", "payload": {"source": "scanner"}}))
        self.assertFalse(_is_internal_task({"id": "x", "type": "manual", "payload": {"message": "Analiza ventas"}}))

    def test_dashboard_has_one_unified_activity_builder_and_live_polling(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertEqual(html.count("function buildUnifiedActivity("), 1)
        self.assertIn("startLiveSyncPolling", html)
        self.assertIn("buildUnifiedActivity(store.tasks, store.internalTasks, store.insights", html)
        self.assertIn("state.view === 'agentdetail'", html)
        # Internal task ids must be removed from the legacy snapshot too.
        self.assertIn("allTaskIds.has(item.id)", html)


class HermesPresentationContractTests(unittest.TestCase):
    def test_hermes_request_contract_keeps_progress_and_commands(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        services = SERVICES.read_text(encoding="utf-8")
        for field in ("activityLog", "progress", "events", "commands"):
            self.assertIn(field, html)
        self.assertIn("/api/hermes/requests/", services)
        self.assertIn("Herramientas y comandos ejecutados", html)
        self.assertIn("Progreso", html)

    def test_hermes_text_is_cleaned_before_display(self):
        runtime = (ROOT / "desktop" / "runtime" / "hermes_chat.py").read_text(encoding="utf-8")
        self.assertIn("_clean_display_text", runtime)
        self.assertIn("box-drawing", runtime)
        self.assertIn("creationflags=subprocess.CREATE_NO_WINDOW", runtime)

    def test_hermes_stream_does_not_steal_scroll_and_enter_sends(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("previousScrollTop", html)
        self.assertIn("stickToBottom", html)
        self.assertIn("e.target.id === 'hermes-q'", html)
        self.assertIn("renderOrchestration().catch", html)

    def test_hermes_chat_does_not_append_global_shopify_activity(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        start = html.index("function pollHermesBackgroundActivity()")
        end = html.index("function setHermesThinking", start)
        block = html[start:end]
        self.assertIn("store.hermesActivity = info", block)
        self.assertNotIn("appendHermesActivityEntries(info.log || [])", block)

    def test_hermes_message_sections_stack_instead_of_collapsing_to_columns(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn(".orch-node{display:flex;align-items:flex-start", html)
        self.assertIn(".orch-node .st2{font-size:12px", html)
        self.assertIn("flex-direction:column;align-items:stretch", html)
        self.assertIn(".orch-node > div:nth-child(2){flex:1 1 auto;min-width:0;width:100%}", html)
        self.assertIn(".hermes-execution{display:grid;gap:8px;width:100%", html)

    def test_hermes_shows_active_conversation_context(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("hermes-conversation-context", html)
        self.assertIn("hermes-conversation-title", html)
        self.assertIn("updateHermesConversationContext", html)
        self.assertIn("data-conv-title", html)
        self.assertIn("function continueConversation(convId, title)", html)


class CommerceLiveSyncContractTests(unittest.TestCase):
    def test_sales_and_shopify_status_are_polled_without_manual_navigation(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("async function pollCommerceNow", html)
        self.assertIn("ds.getShopifySyncStatus", html)
        self.assertIn("startCommercePolling()", html)
        # Commerce + finance + business findings + DATA QUALITY + DATA HEALTH
        # keep polling every 30s without manual navigation (one shared interval)
        self.assertIn("setInterval(function(){ pollCommerceNow(); pollFinanceNow(); pollBusinessNow(); pollCoverageNow(); pollDataHealthNow(); }, 30000)", html)
        self.assertIn("function pollFinanceNow", html)
        self.assertIn("ds.getFinanceOverview", html)
        self.assertIn("state.view === 'sales'", html)
        self.assertIn("state.view === 'finance'", html)
        self.assertIn("pollBusinessNow", html)
        self.assertIn("ds.getBusinessFindings", html)
        # FASE 9 — proactividad: toast de hallazgo nuevo + badge de problemas
        self.assertIn("Nuevo hallazgo", html)
        self.assertIn("activeFindingCount('problem')", html)
        self.assertIn("updateNavBadges", html)
        # FASE 11 — DATA QUALITY (P7/P8/P11): cobertura de coste e identidad
        # en el dashboard y reconciliación de identidad de producto (P4/P5).
        self.assertIn("function pollCoverageNow", html)
        self.assertIn("ds.getCoverage", html)
        self.assertIn("dataQualityHTML", html)
        self.assertIn("Calidad de datos", html)
        self.assertIn("function viewReconcile", html)
        self.assertIn("Reconciliación de productos", html)
        self.assertIn("data-act=\"recon-save\"", html)
        self.assertIn("data-act=\"prod-recon\"", html)


class PreferencesAndInsightContractTests(unittest.TestCase):
    def test_home_cards_and_font_are_persisted(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        config = (ROOT / "desktop" / "runtime" / "config_store.py").read_text(encoding="utf-8")
        self.assertIn("function applyUiPrefs", html)
        self.assertIn("function persistUiPrefs", html)
        self.assertIn("data-home-card-slot", html)
        self.assertIn("settings-font-family", html)
        self.assertIn('"homeCards"', config)
        self.assertIn('"fontFamily"', config)

    def test_insights_have_persistent_actions_and_important_state(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        services = SERVICES.read_text(encoding="utf-8")
        actions = (ROOT / "desktop" / "runtime" / "insight_actions.py").read_text(encoding="utf-8")
        self.assertIn('data-insight-action="approved"', html)
        self.assertIn('data-insight-action="rejected"', html)
        self.assertIn('data-insight-action="dismissed"', html)
        self.assertIn("isMarkedImportant", html)
        self.assertRegex(services, r"async markImportant\(kind, refId, title, body, agentId\)")
        # FASE 11 (P10) — Hermes tools de calidad de datos
        self.assertRegex(services, r"async getCoverage\(\)")
        self.assertRegex(services, r"async getProductReconciliation\(\)")
        self.assertRegex(services, r"async saveProductMapping\(shopifySku, canonicalProductId\)")
        self.assertIn("VALID_ACTIONS", actions)
        self.assertIn("homeRecentInsightsHTML", html)
        self.assertIn("applyInsightActionFilter", html)
        queue = (ROOT / "desktop" / "runtime" / "task_queue.py").read_text(encoding="utf-8")
        self.assertIn("routineKey", queue)

    def test_theme_palette_preview_uses_root_scope(self):
        themes = THEMES.read_text(encoding="utf-8")
        self.assertIn("Temporarily", themes)
        self.assertIn("root.setAttribute('data-theme', id)", themes)
        self.assertNotIn("selector flotante", themes)

    def test_settings_has_one_diagnostics_surface_and_theme_owned_palette(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("function viewDiagnostics", html)
        self.assertNotIn("settings-diagnostics-host", html)
        self.assertNotIn("Color de acento", html)
        self.assertNotIn('data-act="accent"', html)
        self.assertNotIn('[data-accent=', html)

    def test_typography_changes_visibly_and_survives_stale_runtime(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        services = SERVICES.read_text(encoding="utf-8")
        electron = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8")
        # The WebView used to block Google Fonts, making every option fall back
        # to the same default. Each preset now also has a distinct local stack.
        self.assertIn("https://fonts.googleapis.com", electron)
        self.assertIn("https://fonts.gstatic.com", electron)
        self.assertIn("font-src 'self' data: https://fonts.gstatic.com", electron)
        self.assertIn("document.body.style.fontFamily = font.css", html)
        self.assertIn("localStorage.setItem('vanova-font-family', font.id)", html)
        self.assertIn("localStorage.getItem(\"vanova-font-family\")", services)
        # LocalStorage wins if an older runtime preference is returned after an
        # update; otherwise the server's durable preference is used.
        self.assertIn("Object.assign({}, (runtime && runtime.uiPrefs) || {}, localPrefs)", services)
        for fallback in ("Trebuchet MS", "Century Gothic", "Arial Narrow"):
            self.assertIn(fallback, html)



class NotificationsBadgeRefreshContractTests(unittest.TestCase):
    """BUG-036 — el badge de la campana debe re-calcudarse tras CUALQUIER
    mutación de notificaciones (render()) y contar lo MISMO que el drawer.

    Falla con el código anterior a 16fa6c8/e59850b:
    - Antes contaba store.pendingApprovals (no guardrails/risks/decisions/files).
    - Antes solo se llamaba en loadAppData/drawer/decisión, no al final de render.
    """

    def test_badge_counts_what_drawer_shows(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # El badge DEBE contar guardrails + risks + decisions + fileCandidates
        # (lo que buildNotificationsBody muestra), no solo pendingApprovals.
        self.assertIn("const gr = (store.guardrails || []).length;", html)
        self.assertIn("const risks = (store.priorities || []).filter(function(p){ return p.type === 'risk'; }).length;", html)
        self.assertIn("const decisions = (store.decisions || []).length;", html)
        self.assertIn("const files = (store.fileCandidates || []).length;", html)
        self.assertIn("const pending = gr + risks + decisions + files + newInsights;", html)

    def test_badge_refreshes_on_any_render(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # updateBellBadge se debe llamar al final de render() (tras la mutación),
        # además de en loadAppData/poll, para que el badge nunca quede stale tras
        # una decisión/insight/guardrail/fileCandidate.
        # Localizar el cuerpo de render() y verificar que termina llamando updateBellBadge.
        start = html.index("function render(){")
        end = html.index("/* ---- HOME / COMMAND CENTER ---- */", start)
        render_body = html[start:end]
        self.assertIn("updateBellBadge();", render_body)
        # Debe estar tras el manejo de hermes polling (final del render).
        self.assertLess(render_body.index("stopHermesActivityPolling"), render_body.index("updateBellBadge();"))

    def test_badge_refreshes_in_live_sync_poll(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # El polling de live sync (pollLiveTaskState) debe recargar approvals e
        # insights y re-calcular el badge.
        self.assertIn("ds.loadApprovals", html)
        self.assertIn("updateBellBadge();", html)


class HermesContextSalesSummaryTests(unittest.TestCase):
    """FASE 10 (H19): el contexto operacional debe incluir los agregados de
    ventas (revenue total, ticket medio, evolución mensual) para que Hermes
    responda con datos reales en vez de pedir que le consulten las tools."""

    def test_context_includes_sales_summary(self):
        from desktop.runtime import hermes_chat as hc

        sales = [
            {"id": "A", "total": 100.0, "date": "2026-08-01", "source": "shopify"},
            {"id": "B", "total": 50.0, "date": "2026-08-05", "source": "shopify"},
            {"id": "C", "total": 50.0, "date": "2026-07-20", "source": "shopify"},
        ]
        ctx = hc.build_operational_context()
        # Hermes recibe el resumen en el texto del contexto
        text = json.dumps(ctx, ensure_ascii=False)
        self.assertIn("ticket medio", text)
        # Con datos reales en config, el revenue total aparece en el contexto.
        # H20: el build del contexto pasa por `file_organizer._ensure_normalized_data`,
        # que PERSISTE organizedProducts/Sales derivados del load. Si el test solo
        # parchea `load`, puede sobrescribir el config real con los datos del test.
        # Por eso `save` se parchea SIEMPRE como no-op en este test.
        hc._context_cache = None  # el contexto tiene TTL — resetear para forzar rebuild
        hc._context_cache_ts = 0.0
        with patch.object(hc.config_store, "load", return_value={"organizedSales": sales, "organizedProducts": []}), \
             patch.object(hc.config_store, "save") as mock_save:
            ctx2 = hc.build_operational_context()
            text2 = json.dumps(ctx2, ensure_ascii=False)
        # H20: el contexto puede avanzar la versión de normalización, pero
        # NUNCA debe persistir organized* derivados del load.
        for call in mock_save.call_args_list:
            payload = call[0][0] if call[0] else {}
            self.assertNotIn("organizedSales", payload)
            self.assertNotIn("organizedProducts", payload)
        self.assertIn("200.00", text2)  # revenue total 100+50+50
        self.assertIn("66.67", text2)   # ticket medio 200/3


if __name__ == "__main__":
    unittest.main()
