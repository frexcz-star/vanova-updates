"""SPEC STRATI §4.4 — tests del resumen de impacto total (ROI visible).

Verifica que GET /api/recommendations/impact (helper _recommendations_impact)
suma SOLO el delta € de recomendaciones measured+improved con revenue
comparable, y nunca inventa 0 ni cifras sin base.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.runtime import api_server
import unittest


def _recommendation(status, outcome, before, now):
    return {
        "id": f"rec-{status}-{outcome}",
        "status": status,
        "outcome": outcome,
        "metricBefore": {"revenue": before},
        "metricNow": {"revenue": now},
    }


class RecommendationImpactTests(unittest.TestCase):
    """El total capturado suma solo mejoras medidas y comparables."""

    def test_sums_only_measured_improved_with_comparable_revenue(self):
        recs = [
            _recommendation("measured", "improved", 100, 150),   # +50
            _recommendation("measured", "improved", 200, 220),   # +20
            _recommendation("measured", "no_change", 100, 102),  # no suma
            _recommendation("measured", "worsened", 100, 60),    # no suma
            _recommendation("done", "improved", 100, 130),       # no measured
            _recommendation("measured", "improved", 0, 100),     # before 0 → no comparable
        ]
        with patch.object(_store(), "list_recommendations", return_value=recs):
            impact = api_server._recommendations_impact()
        self.assertEqual(impact["capturedEuro"], 70.0)
        self.assertEqual(impact["improvedCount"], 2)

    def test_zero_when_no_comparable_improved(self):
        recs = [
            _recommendation("measured", "no_change", 100, 105),
            _recommendation("measured", "unmeasurable", None, None),
        ]
        with patch.object(_store(), "list_recommendations", return_value=recs):
            impact = api_server._recommendations_impact()
        self.assertEqual(impact["capturedEuro"], 0.0)
        self.assertEqual(impact["improvedCount"], 0)


def _store():
    from desktop.runtime import recommendation_store
    return recommendation_store


if __name__ == "__main__":
    unittest.main()
