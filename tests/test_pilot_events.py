"""Registro de eventos del piloto (SPEC 3 §5/§6) — métrica 'tiempo hasta el €'.

Regresión: el runtime debe registrar eventos reales (conexión OK, 1ª oportunidad
€ vista, recomendación marcada, medición) en JSONL con timestamps y exponer la
métrica "tiempo hasta el €" SIN inventarla. Si faltan eventos reales -> status
'unavailable' (nunca un número fabricado).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import pilot_events


class PilotEventsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self._patcher = patch.object(
            pilot_events, "PILOT_EVENTS_FILE", Path(tmp) / "pilot_events.jsonl"
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_record_writes_jsonl_with_ts(self):
        """record() escribe una línea JSONL con timestamp UTC."""
        entry = pilot_events.record("source.connected", source="shopify", url="https://x.myshopify.com")
        self.assertEqual(entry["event"], "source.connected")
        self.assertIn("ts", entry)
        lines = pilot_events._load()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["detail"]["source"], "shopify")

    def test_metric_unavailable_without_events(self):
        """Sin eventos reales -> status unavailable (nunca un número inventado)."""
        m = pilot_events.metric_time_to_euro()
        self.assertEqual(m["status"], "unavailable")
        self.assertIsNone(m["seconds"])

    def test_time_to_euro_computed_from_real_events(self):
        """Con conexión + 1ª oportunidad vistas, calcula el tiempo real."""
        # Simular dos eventos con timestamps reales separados 5 minutos.
        import json as _json
        from datetime import datetime, timedelta

        base = datetime.now(pilot_events.timezone.utc)
        e1 = {"ts": base.isoformat(), "event": "source.connected", "detail": {}}
        e2 = {
            "ts": (base + timedelta(minutes=5)).isoformat(),
            "event": "opportunity.seen",
            "detail": {"upsideEuro": 36.0},
        }
        with pilot_events.PILOT_EVENTS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(e1) + "\n")
            fh.write(_json.dumps(e2) + "\n")
        m = pilot_events.metric_time_to_euro()
        self.assertEqual(m["status"], "ok")
        self.assertAlmostEqual(m["seconds"], 300.0, delta=1.0)
        self.assertTrue(m["target_lt_15min"])

    def test_time_over_15min_flagged(self):
        """Más de 15 min -> target_lt_15min False (Go/No-Go honesto)."""
        import json as _json
        from datetime import datetime, timedelta

        base = datetime.now(pilot_events.timezone.utc)
        e1 = {"ts": base.isoformat(), "event": "source.connected", "detail": {}}
        e2 = {
            "ts": (base + timedelta(minutes=20)).isoformat(),
            "event": "opportunity.seen",
            "detail": {},
        }
        with pilot_events.PILOT_EVENTS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(e1) + "\n")
            fh.write(_json.dumps(e2) + "\n")
        m = pilot_events.metric_time_to_euro()
        self.assertEqual(m["status"], "ok")
        self.assertFalse(m["target_lt_15min"])

    def test_summary_counts_and_metric(self):
        """summary() expone recuentos por evento + la métrica."""
        pilot_events.record("source.connected")
        pilot_events.record("recommendation.marked", id="r1", status="done")
        s = pilot_events.summary()
        self.assertEqual(s["events_count"], 2)
        self.assertEqual(s["by_event"].get("source.connected"), 1)
        self.assertIn("time_to_euro", s)


if __name__ == "__main__":
    unittest.main()
