"""BUG-054 — Contador de notificaciones: 'Riesgos detectados' del badge y del
drawer siempre en 0 y no refrescado en tiempo real.

Root cause verificado (Hermes, 2026-08-24):
  A) `prioritization.build_priorities` (fuente de store.priorities vía el
     endpoint /api/command-center) emite prioridades con campo `category` pero
     SIN campo `type`. El badge (updateBellBadge) y el drawer
     (buildNotificationsBody) filtran `store.priorities.filter(p=>p.type==='risk')`.
     Como ninguna fuente emite `type='risk'`, la componente 'Riesgos detectados'
     del contador es SIEMPRE 0 (sub-conteo sistemático).
  B) `pollLiveTaskState` (poll 3s) NO incluye `cc.priorities` en su signature,
     y `pollBusinessNow` (invocado tras 'Reconocer'/'Resolver') refresca
     store.businessFindings pero NO store.priorities ni llama updateBellBadge().
     Así, cuando cambian los businessFindings (nuevo riesgo, o riesgo reconocido
     que deja de ser prioridad) pero ningún otro campo de la signature cambia,
     el poll retorna pronto y el badge NO se actualiza (síntoma del usuario).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DASHBOARD = Path(ROOT) / "web" / "dashboard.html"


def _finding(**overrides):
    f = {
        "id": "find_risk1",
        "signature": "sig:risk1",
        "type": "product_concentration",
        "finding_type": "product_concentration",
        "title": "Dependencia de un solo producto",
        "category": "risk",
        "severity": "high",
        "confidence": "high",
        "status": "new",
        "observation": "El 40% del revenue viene de un producto",
        "evidence": ["Top share 40%"],
        "recommendedAction": "Diversifica el catálogo",
        "estimatedImpact": {"kind": "calculated", "economicImpactEuro": 5000.0},
        "entity": "SKU-TOP",
    }
    f.update(overrides)
    return f


class CounterRiskTypeContractTests(unittest.TestCase):
    """BUG-054 Defect A — build_priorities debe emitir `type` para que el badge
    y el drawer puedan filtrar riesgos (p.type === 'risk')."""

    def test_prioritization_emits_type_for_risk_findings(self):
        from desktop.runtime import prioritization

        pri = prioritization.build_priorities([_finding(category="risk")], top=5)
        self.assertTrue(pri, "build_priorities devolvió vacío para un finding activo")
        self.assertEqual(
            pri[0].get("type"), "risk",
            "un finding category='risk' debe emitir type='risk' para que el "
            "badge (filter p.type==='risk') lo cuente",
        )

    def test_prioritization_emits_type_for_problem_findings(self):
        from desktop.runtime import prioritization

        pri = prioritization.build_priorities([_finding(category="problem")], top=5)
        self.assertTrue(pri)
        self.assertEqual(
            pri[0].get("type"), "risk",
            "un finding category='problem' es un riesgo y debe emitir type='risk'",
        )

    def test_prioritization_emits_type_for_opportunity_findings(self):
        from desktop.runtime import prioritization

        pri = prioritization.build_priorities(
            [_finding(id="opp1", category="opportunity", type="opportunity")], top=5
        )
        self.assertTrue(pri)
        self.assertEqual(
            pri[0].get("type"), "opportunity",
            "un finding category='opportunity' debe emitir type='opportunity'",
        )

    def test_badge_and_drawer_count_risks_by_type(self):
        # El badge y el drawer dependen de que store.priorities tenga type='risk'.
        html = DASHBOARD.read_text(encoding="utf-8")
        # El badge cuenta riesgos por type==='risk'
        self.assertIn("store.priorities || []).filter(function(p){ return p.type === 'risk'; }).length",
                      html, "updateBellBadge debe filtrar p.type === 'risk'")
        # El drawer también
        self.assertIn("store.priorities.filter(p=>p.type==='risk').length",
                      html, "buildNotificationsBody debe filtrar p.type === 'risk'")


class CounterLiveRefreshTests(unittest.TestCase):
    """BUG-054 Defect B — el poll 3s y pollBusinessNow deben refrescar
    store.priorities y re-calcular el badge para que el contador baje/suba en
    tiempo real cuando cambian los businessFindings."""

    def test_live_poll_includes_priorities_in_signature(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        start = html.index("async function pollLiveTaskState()")
        end = html.index("let _liveCommerceSignature = ''", start)
        poll = html[start:end]
        # El poll recarga command center (fuente de priorities/risks)
        self.assertIn("ds.loadCommandCenter", poll)
        # La SIGNATURE debe incluir cc.priorities: si no, un cambio en los
        # riesgos (priorities) con el resto de campos igual hace que el poll
        # retorne pronto (early return por signature idéntica) y store.priorities
        # queda stale -> el badge no se actualiza.
        # Buscar el objeto de signature (desde 'const signature = JSON.stringify({').
        sig_start = poll.index("const signature = JSON.stringify({")
        sig_end = poll.index("});", sig_start)
        signature = poll[sig_start:sig_end]
        self.assertIn(
            "cc.priorities", signature,
            "la signature del poll 3s debe incluir cc.priorities "
            "(si no, un cambio de riesgos con el resto igual no refresca el badge)",
        )
        # Y store.priorities se actualiza desde cc.priorities (tras el early-return)
        self.assertIn("store.priorities = cc.priorities", poll)

    def test_poll_business_refreshes_priorities_and_badge(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        start = html.index("function pollBusinessNow()")
        end = html.index("function updateNavBadges()", start)
        pb = html[start:end]
        # Tras 'Reconocer'/'Resolver' (que llama pollBusinessNow) el badge debe
        # re-calcudarse: store.priorities se refresca y updateBellBadge se llama.
        self.assertIn("store.priorities", pb,
                      "pollBusinessNow debe refrescar store.priorities (los riesgos)")
        self.assertIn("updateBellBadge();", pb,
                      "pollBusinessNow debe llamar updateBellBadge() tras refrescar riesgos")

    def test_ack_flow_recarga_badge(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # El handler 'Reconocer' (act==='ack') setea status acknowledged y debe
        # recargar para que el riesgo desaparezca del badge.
        self.assertIn("DataServices.setFindingStatus(id, status)", html)
        # Tras setFindingStatus ok -> pollBusinessNow (que ahora refresca badge)
        self.assertIn("if (r && r.ok) { toast('Hallazgo ' + status + '.'); pollBusinessNow(); }", html)


if __name__ == "__main__":
    unittest.main()
