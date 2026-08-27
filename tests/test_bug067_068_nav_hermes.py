"""BUG-067 y BUG-068: desincronización del contador sidebar vs drawer + botón Hermes.

BUG-067 (MEDIUM, reproducible 5/5): el badge de la sidebar "Inicio" mostraba un
número (ej. 7) distinto al contenido del drawer de notificaciones ("0 pendientes").
Root cause: el badge de Inicio usaba `activeFindingCount('problem')` (businessFindings
con category='problem'), mientras el drawer y el badge de la campana usan
`store.priorities.filter(p.type==='risk')` (gr+risks+decisions+files). Fuentes
distintas → desincronización del contador.

Fix: `updateNavBadges` y la inicialización del nav-badge usan `activeRiskCount()`,
la MISMA fuente que el drawer (store.priorities type='risk'). badge == drawer.

BUG-068 (botón "Hermes" visible): el botón/nav/título de la página de chat y varios
textos de UI mostraban "Hermes" al cliente. Regla dura: nunca exponer "Hermes";
usar "Asistente"/"Preguntar a VANOVA". Fix: todos los textos visibles renombrados.

Estos tests FALLAN con el código anterior y PASAN con el fix.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "web" / "dashboard.html"


class Bug067NavBadgeSyncTests(unittest.TestCase):
    def test_nav_badge_usa_active_risk_count(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # El badge de Inicio (updateNavBadges e inicialización) debe usar activeRiskCount.
        self.assertIn("function activeRiskCount()", html, "activeRiskCount ausente")
        # updateNavBadges debe usar activeRiskCount, no activeFindingCount('problem').
        idx = html.find("function updateNavBadges()")
        block = html[idx:idx + 700]
        self.assertIn("activeRiskCount()", block, "updateNavBadges no usa activeRiskCount")

    def test_active_risk_count_coincide_con_drawer(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # activeRiskCount debe filtrar store.priorities por type==='risk' (misma fuente que el drawer).
        idx = html.find("function activeRiskCount()")
        block = html[idx:idx + 200]
        self.assertIn("p.type === 'risk'", block, "activeRiskCount no filtra type risk")

    def test_nav_badge_inicial_usa_active_risk_count(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # La inicialización del nav-badge de Inicio debe usar activeRiskCount.
        idx = html.find("const problemCount = it.k==='home'")
        block = html[idx:idx + 120]
        self.assertIn("activeRiskCount()", block, "nav-badge inicial no usa activeRiskCount")

    def test_apply_insight_action_filter_recalcula_badges(self):
        """BUG-067 raíz real: al filtrar prioridades (aprobar/descartar), los badges
        de la sidebar y la campana deben recalcularse para no quedar stale."""
        html = DASHBOARD.read_text(encoding="utf-8")
        idx = html.find("function applyInsightActionFilter()")
        self.assertGreater(idx, -1, "applyInsightActionFilter ausente")
        block = html[idx:idx + 900]
        self.assertIn("updateNavBadges", block, "applyInsightActionFilter no recalcula updateNavBadges")
        self.assertIn("updateBellBadge", block, "applyInsightActionFilter no recalcula updateBellBadge")

    def test_handle_insight_action_recalcula_badges(self):
        """BUG-067: al aprobar/descartar un insight (handleInsightAction), los badges
        se recalcular para que badge == contenido inmediatamente."""
        html = DASHBOARD.read_text(encoding="utf-8")
        idx = html.find("async function handleInsightAction(")
        self.assertGreater(idx, -1, "handleInsightAction ausente")
        block = html[idx:idx + 900]
        self.assertIn("updateNavBadges", block, "handleInsightAction no recalcula updateNavBadges")
        self.assertIn("updateBellBadge", block, "handleInsightAction no recalcula updateBellBadge")


class Bug068NoHermesVisibleTests(unittest.TestCase):
    def test_no_hay_hermes_visible_en_ui(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # Textos visibles de "Hermes" deben estar renombrados a Asistente.
        # (Excluimos "Hermes Agent" porque L6032 es una comparación lógica con el
        #  nombre real de la extensión desde datos, no texto visible hardcodeado;
        #  la tarjeta visible ya se renombró a "Asistente de IA".)
        for bad in [
            "Pregunta a Hermes", "Preguntar a Hermes", "Consultar Hermes",
            "Conversación con Hermes", "Hermes — Interfaz de Comando IA",
            "Enviar a Hermes", "Hermes listo", "Preparando Hermes",
            "Bot de Hermes activo", "Hermes está pensando", "Hermes respondió",
            "a Hermes", "Ask Hermes", "Ask Hermes about this report",
            ">Hermes<", "Conexión con Hermes",
        ]:
            self.assertNotIn(bad, html, f"'Hermes' visible en UI: {bad}")

    def test_asistente_presente(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # Debe haber el reemplazo por Asistente.
        self.assertIn("Asistente", html)
        self.assertIn("Pregunta a VANOVA", html)


if __name__ == "__main__":
    unittest.main()
