"""VANOVA PRODUCT 8 — tests de priorización real y memoria de recomendaciones."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import prioritization, recommendation_store


def _finding(**overrides):
    f = {
        "id": "f1",
        "signature": "sig:1",
        "type": "missing_cost",
        "finding_type": "missing_cost",
        "title": "Productos sin coste",
        "category": "problem",
        "severity": "high",
        "confidence": "high",
        "status": "active",
        "observation": "47 productos no tienen coste",
        "evidence": ["47 registros sin coste", "Registros preservados"],
        "recommendedAction": "Importa costes por SKU",
        "estimatedImpact": {"kind": "calculated", "economicImpactEuro": 1200.0, "explanation": "Margen no fiable"},
        "metrics": {"sku": "SKU-1"},
        "entity": "SKU-1",
    }
    f.update(overrides)
    return f


class PrioritizationTests(unittest.TestCase):
    def test_ranks_by_score_and_keeps_top_n(self):
        items = [
            _finding(id="a", signature="s:a", type="high_impact", severity="high",
                     estimatedImpact={"kind": "calculated", "economicImpactEuro": 50000.0}),
            _finding(id="b", signature="s:b", type="medium_impact", severity="medium", confidence="medium",
                     estimatedImpact={"kind": "calculated", "economicImpactEuro": 500.0}),
            _finding(id="c", signature="s:c", type="low_impact", severity="low", confidence="low"),
            _finding(id="d", signature="s:d", type="resolved_one", severity="high", status="resolved"),
        ]
        top = prioritization.build_priorities(items, top=2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["findingId"], "a")  # mayor impacto
        self.assertEqual(top[1]["findingId"], "b")
        # El resuelto nunca entra
        self.assertNotIn("d", [p["findingId"] for p in top])
        # Determinista
        top_again = prioritization.build_priorities(items, top=2)
        self.assertEqual([p["findingId"] for p in top], [p["findingId"] for p in top_again])

    def test_unquantifiable_impact_is_not_zero(self):
        items = [_finding(id="x", signature="s:x", severity="high",
                          estimatedImpact={"kind": "estimated", "explanation": "Sin cifra"})]
        top = prioritization.build_priorities(items)
        self.assertIsNone(top[0]["impactEuro"])
        self.assertEqual(top[0]["impactKind"], "estimated")

    def test_score_ranks_high_severity_high_confidence_first(self):
        low = _finding(id="a", signature="s:a", severity="low", confidence="low")
        high = _finding(id="b", signature="s:b", severity="high", confidence="high")
        top = prioritization.build_priorities([low, high], top=1)
        self.assertEqual(top[0]["findingId"], "b")

    def test_empty_findings_no_priorities(self):
        self.assertEqual(prioritization.build_priorities([]), [])


class RecommendationStoreTests(unittest.TestCase):
    def _cfg(self):
        return {
            "organizedSales": [{
                "id": "#1", "total": 30.0, "date": "2026-07-15",
                "line_items": [{"sku": "SKU-1", "price": 10.0, "quantity": 3}],
            }],
            "businessFindings": [_finding()],
            "recommendations": [],
        }

    def test_record_dedup_by_signature(self):
        cfg = self._cfg()
        r1 = recommendation_store.record_finding(_finding(), data=cfg)
        r2 = recommendation_store.record_finding(_finding(), data=cfg)
        self.assertEqual(r1["id"], r2["id"])  # mismo finding → misma recomendación
        self.assertEqual(len(cfg["recommendations"]), 1)

    def test_mark_done_and_measure(self):
        cfg = self._cfg()
        rec = recommendation_store.record_finding(_finding(), data=cfg)
        recommendation_store.mark_done(rec["id"], data=cfg)
        # PRODUCT LEAP: marcar como realizada auto-mide el resultado.
        r = cfg["recommendations"][0]
        self.assertEqual(r["status"], "measured")
        self.assertIn(r["outcome"], ("no_change", "improved", "worsened", "unmeasurable"))

    def test_set_status_lifecycle(self):
        cfg = self._cfg()
        rec = recommendation_store.record_finding(_finding(), data=cfg)
        # open → in_progress → not_done (sin medir)
        recommendation_store.set_status(rec["id"], "in_progress", data=cfg)
        self.assertEqual(cfg["recommendations"][0]["status"], "in_progress")
        recommendation_store.set_status(rec["id"], "not_done", data=cfg)
        self.assertEqual(cfg["recommendations"][0]["status"], "not_done")
        # estado inválido → rechazado
        self.assertIsNone(recommendation_store.set_status(rec["id"], "hack", data=cfg))

    def test_unmeasurable_when_no_sales(self):
        cfg = {"organizedSales": [], "businessFindings": [], "recommendations": []}
        rec = recommendation_store.record_finding(_finding(), data=cfg)
        outcome = recommendation_store.measure(rec["id"], data=cfg)
        self.assertEqual(outcome["outcome"], "unmeasurable")  # UNKNOWN ≠ inventado

    def test_sync_resolutions_never_overwrites_user_status(self):
        """Regresión 3.0.4 (estabilización): un re-análisis automático NO puede
        pisar los estados que el usuario eligió. Antes, sync_resolutions
        convertía «En curso» / «Realizada» / «No realizada» en «Resuelta» en
        cuanto la condición no aparecía en las firmas frescas."""
        cfg = self._cfg()
        rec = recommendation_store.record_finding(_finding(), data=cfg)

        for user_status in ("in_progress", "done", "not_done"):
            recommendation_store.set_status(rec["id"], user_status, data=cfg)
            res = recommendation_store.sync_resolutions([], active_signatures=set(), data=cfg)
            final = cfg["recommendations"][0]["status"]
            # El estado del usuario se respeta: 'done' puede pasar a 'measured'
            # por la auto-medición (comportamiento de producto), pero NUNCA a
            # 'resolved' por un re-análisis automático.
            self.assertNotEqual(final, "resolved",
                                f"sync_resolutions pisó el estado {user_status} del usuario")
            if user_status == "done":
                self.assertIn(final, ("done", "measured"))
            else:
                self.assertEqual(final, user_status)

    def test_sync_resolutions_resolves_only_open(self):
        """Solo las recomendaciones que el usuario no ha tocado (open) se
        auto-resuelven cuando la condición desaparece."""
        cfg = self._cfg()
        rec = recommendation_store.record_finding(_finding(), data=cfg)
        res = recommendation_store.sync_resolutions([], active_signatures=set(), data=cfg)
        self.assertEqual(res["resolved"], 1)
        self.assertEqual(cfg["recommendations"][0]["status"], "resolved")

    def test_sync_resolutions_keeps_open_when_active(self):
        cfg = self._cfg()
        rec = recommendation_store.record_finding(_finding(), data=cfg)
        res = recommendation_store.sync_resolutions([], active_signatures={_finding()["signature"]}, data=cfg)
        self.assertEqual(res["resolved"], 0)
        self.assertEqual(cfg["recommendations"][0]["status"], "open")

    def test_set_status_done_returns_post_measure_state(self):
        """La respuesta de marcar como realizada refleja el estado REAL tras la
        auto-medición (status 'measured' + outcome), no el dict previo."""
        cfg = self._cfg()
        rec = recommendation_store.record_finding(_finding(), data=cfg)
        updated = recommendation_store.set_status(rec["id"], "done", data=cfg)
        self.assertEqual(cfg["recommendations"][0]["status"], updated["status"])
        self.assertIn(updated["outcome"], ("no_change", "improved", "worsened", "unmeasurable"))


if __name__ == "__main__":
    unittest.main()
