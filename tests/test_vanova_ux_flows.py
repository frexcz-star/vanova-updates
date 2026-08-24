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
        # COPY (Nico, 2026-08-23): "Reconciliación de productos" → "Vincula tus productos"
        # (lenguaje empresarial llano para no-técnicos).
        self.assertIn("Vincula tus productos", html)
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
        # (lo que buildNotificationsBody muestra), y NO duplicar los findings:
        # los insights kind='finding' ya se representan en priorities type='risk'
        # (que el drawer lista como "Riesgos detectados").
        self.assertIn("const gr = (store.guardrails || []).length;", html)
        self.assertIn("const risks = (store.priorities || []).filter(function(p){ return p.type === 'risk'; }).length;", html)
        # BUG-047 (causa raíz contador): decisions ahora cuentan SOLO las pendientes
        # (status='pending'), no todas (aprobadas/rechazadas/resueltas).
        self.assertIn("store.decisions || []).filter(function(dc){ return (dc.status||'pending') === 'pending'; }).length;", html)
        self.assertIn("const files = (store.fileCandidates || []).length;", html)
        self.assertIn("const pending = gr + risks + decisions + files;", html)
        # No debe sumar newInsights en el cálculo del badge (evita duplicar findings).
        badge_block = html.split("function updateBellBadge()")[1].split("function openNotificationsDrawer")[0]
        self.assertNotIn("+ newInsights", badge_block)
        self.assertNotIn("files + newInsights", badge_block)

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

    def test_live_poll_recarga_guardrails_decisions_candidates(self):
        """BUG-036 (causa raíz real): el poll de 3s debe recargar guardrails,
        decisions y fileCandidates (que el badge cuenta), no solo insights y
        approvals. Sin esto, el badge quedaba stale cuando estas llegaban o
        desaparecían en el backend (solo se cargaban en loadAppData inicial).
        Falla con el código anterior a esta corrección (el poll no las recargaba)."""
        html = DASHBOARD.read_text(encoding="utf-8")
        # Localizar el cuerpo de pollLiveTaskState
        start = html.index("async function pollLiveTaskState()")
        end = html.index("let _liveCommerceSignature = ''", start)
        poll = html[start:end]
        # Debe recargar guardrails, fileCandidates y decisions (vía dashboard).
        self.assertIn("ds.getGuardrails", poll)
        self.assertIn("ds.loadFileCandidates", poll)
        self.assertIn("ds.loadDashboard", poll)
        # Debe actualizar los stores que el badge cuenta.
        self.assertIn("store.guardrails = nextGuardrails", poll)
        self.assertIn("store.decisions = nextDecisions", poll)
        self.assertIn("store.fileCandidates = nextCandidates", poll)
        # Y el badge se re-calcula al final del poll.
        self.assertIn("updateBellBadge();", poll)

    def test_notif_dismiss_boton_tiene_handler(self):
        """BUG-036: el botón 'Marcar como leídas' (data-act='notif-dismiss') debe
        tener un handler en el dispatcher que marque notifSeenAt y re-calcule el
        badge. Falla con el código anterior (el botón no tenía handler -> no
        hacía nada al pulsarlo, el badge no se aclaraba)."""
        html = DASHBOARD.read_text(encoding="utf-8")
        # El botón se define con data-act="notif-dismiss"
        self.assertIn('data-act="notif-dismiss"', html)
        # El dispatcher debe manejar notif-dismiss (marcar leídas + re-calcudar badge)
        self.assertIn("a==='notif-dismiss'", html)
        # Debe persistir notifSeenAt y re-calcular el badge
        self.assertIn("persistUiPrefs({ notifSeenAt: new Date().toISOString() })", html)
        self.assertIn("updateBellBadge();", html)

    def test_decidir_decision_recarga_badge(self):
        """BUG-036: al aprobar/rechazar una decisión, el badge debe re-calcudarse
        (recargar decisions + updateBellBadge), no quedarse stale hasta el poll.
        Falla con el código anterior (los handlers approve/reject solo hacían
        toast, sin reload ni updateBellBadge)."""
        html = DASHBOARD.read_text(encoding="utf-8")
        # El handler approve de decisión debe recargar y re-calcudar el badge.
        approve_block = html.split("DataServices.decide(card.dataset.did,'approve')")[1].split("const pcard")[0]
        self.assertIn("loadAppData().then", approve_block)
        self.assertIn("updateBellBadge();", approve_block)
        # El handler reject de decisión también.
        reject_block = html.split("DataServices.decide(card.dataset.did,'reject')")[1].split("const pcard")[0]
        self.assertIn("loadAppData().then", reject_block)
        self.assertIn("updateBellBadge();", reject_block)


class NonTechnicalCopyTests(unittest.TestCase):
    """UX/usabilidad para no-técnicos (Nico): la UI debe usar lenguaje
    empresarial llano en español, no jerga técnica. Root cause = jerga técnica
    (Runtime, Cloud, MCP, Payload, Sync) confundía a un empresario normal.

    Falla con el código anterior (la jerga técnica estaba en la UI visible).
    """

    def test_jerga_tecnica_eliminada_de_la_ui(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # Jerga técnica que no debe aparecer en la UI visible al usuario.
        for jargon in [
            ">Runtime<",
            ">Cloud<",
            ">Connector<",
            ">MCP Servers<",
            "Reiniciar runtime",
            "Sync Shopify",
            "Reconciliación de productos",
            ">Payload<",
        ]:
            self.assertNotIn(jargon, html, f"jerga técnica visible en UI: {jargon}")

    def test_textos_empresariales_presentes(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # Los textos en lenguaje empresarial llano deben estar presentes.
        for good in [
            "Motor de VANOVA",
            "Nube de VANOVA",
            "Conexión",
            "Herramientas externas",
            "Vincula tus productos",
            "Reiniciar VANOVA",
            "Última actualización de la tienda",
            "Instrucción (lo que pidió el usuario)",
        ]:
            self.assertIn(good, html, f"texto empresarial ausente en UI: {good}")


class FloatingRoundedCardsStyleTests(unittest.TestCase):
    """Estilo de UI (Nico): las secciones/tarjetas del dashboard deben verse como
    tarjetas FLOTANTES REDONDEADAS (glassmorphism flotante), no bloques rectos
    planos. Root cause: las tarjetas usaban fondo sólido plano con radio medio.

    Falla con el código anterior (tarjetas planas sin glassmorphism ni sombra
    flotante ni radio amplio).
    """

    def test_tarjetas_usan_estilo_flotante_redondeado(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # Las tarjetas principales deben usar fondo glass, radio amplio y sombra flotante.
        for card in [".metric{", ".card{", ".dash-card{", ".priority{", ".agent-card{"]:
            self.assertIn(card, html, f"clase de tarjeta ausente: {card}")
        # Estilo flotante: fondo translúcido (glassmorphism) + sombra de elevación + radio amplio.
        self.assertIn("--surface-glass", html, "fondo glass ausente")
        self.assertIn("--shadow-float", html, "sombra flotante ausente")
        self.assertIn("--radius-xl", html, "radio amplio ausente")
        self.assertIn("backdrop-filter:blur", html, "glassmorphism (blur) ausente")
        self.assertIn("border-radius:var(--radius-xl)", html, "las tarjetas no usan radio amplio")


class FinancingSectionTests(unittest.TestCase):
    """Sección de gráficas de Financiación (Nico/Strati). FIJAS, no rotativas,
    con € real. Solo se pintan indicadores con datos verificados (honestidad:
    sin coste real no se pinta margen inventado, sin facturación no hay barras).
    Prioriza Valor Capturado (defiende el precio).

    Falla con el código anterior (la sección de Financiación no existía).
    """

    def test_seccion_financiacion_existe_y_usa_datos_reales(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # La sección de Financiación debe existir y estar en la home.
        self.assertIn("function financingHTML", html, "financingHTML ausente")
        self.assertIn("function financingSectionHTML", html, "sección Financiación ausente")
        self.assertIn("financingSectionHTML()", html, "sección no insertada en la home")
        # Fija, no rotativa: gráficas de € real.
        self.assertIn("Valor Capturado", html, "Valor Capturado ausente (prioridad)")
        self.assertIn("Facturación por periodo", html)
        # Honestidad: si no hay datos, muestra vacío, no inventa.
        self.assertIn("Sin datos suficientes", html)
        self.assertIn("Sin coste real detrás", html)
        # Estilo flotante redondeado coherente.
        self.assertIn("border-radius:var(--radius-xl)", html)


class ThemeToggleParTests(unittest.TestCase):
    """BUG real (Nico): al estar en tema 'medianoche' (midnight) y pulsar el toggle
    sol/luna, iba a 'ember' de forma no determinista (sin par claro explícito en
    autoPairs). Fix: 'midnight' y 'graphite' ahora tienen par claro ('ember') en
    autoPairs, así el toggle va a un tema claro real y predecible."""

    DASH = ROOT / "web" / "dashboard.html"

    def test_midnight_y_graphite_tienen_par_claro(self):
        html = self.DASH.read_text(encoding="utf-8")
        # autoPairs debe incluir midnight->ember y graphite->ember
        self.assertIn("midnight:'ember'", html, "midnight debe tener par claro 'ember' en autoPairs")
        self.assertIn("graphite:'ember'", html, "graphite debe tener par claro 'ember' en autoPairs")


class RuntimeApiRetry401Tests(unittest.TestCase):
    """BUG real (Nico, logs): el runtime devolvía 401 persistente ('Unauthorized
    read GET /api/files' x16758) porque el frontend adjuntaba un token que ya no
    coincidía con el runtimeToken del secrets tras un reinicio/rotación. Sin
    reintento, la sesión quedaba rota y los datos (files/products/sales) no se
    cargaban → el catálogo no se actualizaba. Fix: runtimeApi reintenta UNA vez
    tras un 401, releyendo la auth (el main process lee el token actual)."""

    DS = ROOT / "web" / "data-services.js"

    def test_runtime_api_reintenta_tras_401(self):
        js = self.DS.read_text(encoding="utf-8")
        # Debe reintentar tras 401, releyendo la auth
        self.assertIn("res.status === 401 && !options._retried", js,
                      "runtimeApi debe reintentar tras un 401")
        self.assertIn("const auth2 = await runtimeAuthHeaders();", js,
                      "el reintento debe re-leer la auth (token actual del secrets)")


class LiveSyncPollAllViewsTests(unittest.TestCase):
    """BUG-053 (Mathew): el poll de 3s que recalcula el badge (updateBellBadge)
    estaba condicionado a la whitelist home/activity/tasks/agents/agentdetail.
    En cualquier otra vista (Ventas, Finanzas, Productos, Insights, Clientes,
    Archivos, Ajustes...) el poll NO corría → el badge no se actualizaba aunque
    llegaran decisiones/guardrails nuevos al backend. Fix: pollLiveTaskState
    corre en TODAS las vistas (el badge es global)."""

    DASH = ROOT / "web" / "dashboard.html"

    def test_poll_3s_no_condicionado_a_whitelist(self):
        html = self.DASH.read_text(encoding="utf-8")
        # El intervalo de 3s NO debe tener el condicional de whitelist; debe llamar
        # pollLiveTaskState incondicionalmente para que el badge se recalcule en
        # todas las vistas.
        # Extraer el bloque del setInterval de 3s dentro de startLiveSyncPolling
        idx = html.find("function startLiveSyncPolling")
        self.assertNotEqual(idx, -1, "debe existir startLiveSyncPolling")
        block = html[idx:idx + 900]
        # El condicional whitelisted debe haber desaparecido
        self.assertNotIn("state.view === 'home' || state.view === 'activity'", block,
                         "el poll NO debe estar condicionado a la whitelist de vistas")
        # Debe llamar pollLiveTaskState en el intervalo de 3s
        self.assertIn("setInterval(function()", block)
        self.assertIn("pollLiveTaskState();", block)


class DiagnosticsBackupRestoreTests(unittest.TestCase):
    """BUG-008 real (Nico): la UI de restaurar copias no existía — los handlers
    diag-restore-backup no tenían botones que los invocaran (no había lista de
    backups en el diagnóstico). Fix: se añadió la sección 'Copias de seguridad'
    al diagnóstico con botón 'Restaurar' (data-backup-id) por cada backup y
    botón 'Crear copia'."""

    DASH = ROOT / "web" / "dashboard.html"

    def test_diagnostico_tiene_seccion_de_copias(self):
        html = self.DASH.read_text(encoding="utf-8")
        # El diagnóstico debe tener la sección de copias de seguridad
        self.assertIn("Copias de seguridad", html)
        self.assertIn("diag-backups-panel", html, "debe existir el panel de copias en el diagnóstico")

    def test_boton_restaurar_tiene_data_backup_id(self):
        html = self.DASH.read_text(encoding="utf-8")
        # El botón de restaurar debe llevar data-backup-id (que el handler usa)
        self.assertIn("data-act=\"diag-restore-backup\"", html)
        self.assertIn("data-backup-id=\"${escAttr(b.id||'')}\"", html,
                      "el botón de restaurar debe llevar data-backup-id")

    def test_load_diag_backups_se_ejecuta_al_abrir_diagnostico(self):
        html = self.DASH.read_text(encoding="utf-8")
        # Al renderizar el diagnóstico debe llamarse loadDiagBackups
        self.assertIn("loadDiagBackups()", html)
        # Buscar el bloque del if del render de diagnostics (el último)
        idx = html.rfind("state.view === 'diagnostics'")
        self.assertNotEqual(idx, -1)
        block = html[idx:idx + 400]
        self.assertIn("loadDiagBackups()", block, "loadDiagBackups debe llamarse al abrir el diagnóstico")


class MarginSaveRuntimeFetchTests(unittest.TestCase):
    """BUG real (Nico, post-3.1.6): declarar el margen (pone 50) daba error del
    runtime. Root cause: promptQuickMargin (y el guardado del margen del drawer)
    usaban fetch() DIRECTO al runtime sin el reintento 401 (solo en runtimeApi).
    Si el token del secrets fallaba/rotaba (patrón BUG-051), el POST daba 401 y
    el margen no se guardaba, mientras el diagnóstico decía 'todo correcto'.
    Fix: se añadió runtimeFetch (auth + reintento 401) y se usa para guardar el
    margen."""

    DASH = ROOT / "web" / "dashboard.html"

    def test_existe_helper_runtime_fetch_con_retry_401(self):
        html = self.DASH.read_text(encoding="utf-8")
        self.assertIn("async function runtimeFetch", html, "debe existir el helper runtimeFetch")
        self.assertIn("res.status === 401 && !options._retried", html,
                      "runtimeFetch debe reintentar tras un 401")

    def test_guardado_margen_usa_runtime_fetch(self):
        html = self.DASH.read_text(encoding="utf-8")
        # El guardado del margen debe usar runtimeFetch, no fetch() directo al runtime
        idx = html.find("function promptQuickMargin")
        self.assertNotEqual(idx, -1)
        block = html[idx:idx + 1100]
        self.assertIn("runtimeFetch('/api/company/profile'", block,
                      "promptQuickMargin debe usar runtimeFetch para guardar el margen")


class BusinessFindingsDedupAndAckTests(unittest.TestCase):
    """BUG-DUP y BUG-RECON (Mathew):
    1. "Qué hacer hoy" (store.actionPlan) y "Hallazgos del motor"
       (store.businessFindings) se alimentan del MISMO endpoint → duplican.
       "Hallazgos del motor" debe excluir los del actionPlan.
    2. "Reconocer" (status=acknowledged) no filtraba el hallazgo → seguía
       visible. Debe excluirse acknowledged.

    Falla con el código anterior (duplicación + acknowledged visible).
    """

    def test_hallazgos_excluyen_actionplan_y_acknowledged(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # "Hallazgos del motor" debe excluir los del actionPlan (dedup).
        self.assertIn("planIds", html, "dedup con actionPlan ausente")
        self.assertIn("!planIds.has(x.id)", html, "no excluye findings del actionPlan")
        # "Reconocer" (acknowledged) debe excluirse del motor.
        self.assertIn("x.status !== 'acknowledged'", html, "acknowledged no se filtra")


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
