"""Agent scheduler + agent catalog tests.

Covers the schedule parser, add_agents merge semantics, the catalog endpoint
data, and the policy/permission-safe payload builder.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import agent_scheduler
from desktop.runtime.agent_architect import add_agents, build_agent_payload, catalog


class ScheduleParserTests(unittest.TestCase):
    def test_daily(self):
        self.assertEqual(agent_scheduler.parse_schedule("Daily 18:00"), {"freq": "daily", "hour": 18, "minute": 0})
        self.assertEqual(agent_scheduler.parse_schedule("daily 08:00"), {"freq": "daily", "hour": 8, "minute": 0})

    def test_weekly(self):
        self.assertEqual(
            agent_scheduler.parse_schedule("Weekly Monday 09:00"),
            {"freq": "weekly", "weekday": 0, "hour": 9, "minute": 0},
        )
        self.assertEqual(
            agent_scheduler.parse_schedule("Weekly Sunday 23:59"),
            {"freq": "weekly", "weekday": 6, "hour": 23, "minute": 59},
        )

    def test_invalid(self):
        self.assertIsNone(agent_scheduler.parse_schedule(""))
        self.assertIsNone(agent_scheduler.parse_schedule("Hourly"))
        self.assertIsNone(agent_scheduler.parse_schedule("Daily 25:00"))
        self.assertIsNone(agent_scheduler.parse_schedule("Weekly Funday 09:00"))


class OccurrenceTests(unittest.TestCase):
    def test_daily_before_and_after(self):
        rule = {"freq": "daily", "hour": 18, "minute": 0}
        before = datetime(2026, 8, 13, 10, 0)
        self.assertEqual(
            agent_scheduler._most_recent_occurrence(rule, before),
            datetime(2026, 8, 12, 18, 0),
        )
        after = datetime(2026, 8, 13, 19, 0)
        self.assertEqual(
            agent_scheduler._most_recent_occurrence(rule, after),
            datetime(2026, 8, 13, 18, 0),
        )

    def test_weekly(self):
        # 2026-08-13 is a Thursday (weekday 3). Monday rule.
        rule = {"freq": "weekly", "weekday": 0, "hour": 9, "minute": 0}
        thursday = datetime(2026, 8, 13, 10, 0)
        self.assertEqual(
            agent_scheduler._most_recent_occurrence(rule, thursday),
            datetime(2026, 8, 10, 9, 0),
        )
        # Same day before the time -> previous Monday.
        monday_before = datetime(2026, 8, 10, 8, 0)
        self.assertEqual(
            agent_scheduler._most_recent_occurrence(rule, monday_before),
            datetime(2026, 8, 3, 9, 0),
        )


class AgentCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_file = Path(self.tmp.name) / "maios.json"
        self.patch = patch("desktop.runtime.config_store.CONFIG_FILE", self.config_file)
        self.patch.start()
        add_agents(
            [
                {"id": "marketing-agent", "name": "Marketing Agent", "permissions": ["read_analytics"]},
                {"id": "sales-analyst", "name": "Sales Analyst", "permissions": ["read_orders"]},
            ]
        )

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_add_agents_merges_without_removing(self):
        added = add_agents([{"id": "content-agent", "name": "Content Agent", "permissions": ["generate_content"]}])
        self.assertEqual([a["id"] for a in added], ["content-agent"])
        # Adding the same agent again is a no-op.
        again = add_agents([{"id": "content-agent", "name": "Content Agent"}])
        self.assertEqual(again, [])
        # Existing agents must still be present.
        from desktop.runtime import config_store

        ids = {a["id"] for a in config_store.load().get("agents", [])}
        self.assertIn("marketing-agent", ids)
        self.assertIn("sales-analyst", ids)
        self.assertIn("content-agent", ids)

    def test_catalog_flags_installed(self):
        entries = {a["id"]: a for a in catalog()}
        self.assertTrue(entries["marketing-agent"]["installed"])
        self.assertTrue(entries["sales-analyst"]["installed"])
        self.assertFalse(entries["content-agent"]["installed"])

    def test_build_payload_is_permission_and_policy_safe(self):
        agent = {"id": "sales-analyst", "name": "Sales Analyst", "permissions": ["read_orders", "read_products"]}
        payload = build_agent_payload(agent, scheduled=True, schedule_spec="Daily 08:00")
        self.assertEqual(payload["permission"], "read_orders")
        self.assertEqual(payload["action"], "analyze")
        self.assertEqual(payload["risk"], "low")
        self.assertTrue(payload["scheduled"])
        self.assertEqual(payload["schedule"], "Daily 08:00")
        self.assertIn("Sales Analyst", payload["message"])


class DelegatedTaskTests(unittest.TestCase):
    """Human-delegated tasks: now / once / recurring + delete + tick firing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp.name) / "scheduler_state.json"
        self.cfg = Path(self.tmp.name) / "maios.json"
        self.patch_state = patch("desktop.runtime.agent_scheduler._state_file", lambda: self.state_file)
        self.patch_state.start()
        self.patch_cfg = patch("desktop.runtime.config_store.CONFIG_FILE", self.cfg)
        self.patch_cfg.start()
        from desktop.runtime import config_store
        cfg = config_store.load()
        cfg.setdefault("agents", [])
        config_store.save(cfg)
        self.calls: list[tuple[str, str]] = []

    def tearDown(self):
        self.patch_state.stop()
        self.patch_cfg.stop()
        self.tmp.cleanup()

    def _record(self, agent_id: str, message: str) -> dict:
        self.calls.append((agent_id, message))
        return {"ok": True, "id": "fake"}

    def test_once_schedule_and_delete(self):
        due = (datetime.now().replace(microsecond=0) + timedelta(minutes=5)).isoformat()
        r = agent_scheduler.schedule_task("marketing-agent", mode="once", message="Haz X", due=due)
        self.assertTrue(r["ok"])
        self.assertEqual(r["mode"], "once")
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(len(state["one_time"]), 1)
        self.assertEqual(state["one_time"][0]["message"], "Haz X")
        d = agent_scheduler.delete_schedule(r["scheduleId"])
        self.assertTrue(d["ok"])
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(len(state["one_time"]), 0)

    def test_once_missing_due_rejected(self):
        r = agent_scheduler.schedule_task("marketing-agent", mode="once", message="X", due=None)
        self.assertFalse(r["ok"])

    def test_recurring_tick_fires_once(self):
        r = agent_scheduler.schedule_task(
            "marketing-agent", mode="recurring", message="Revisa X", schedule_spec="Daily 00:01"
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["mode"], "recurring")
        with patch.object(agent_scheduler, "_enqueue_manual", side_effect=self._record):
            agent_scheduler._tick()
        self.assertEqual(self.calls, [("marketing-agent", "Revisa X")])
        # Second tick must NOT re-fire (lastRun persisted).
        self.calls = []
        with patch.object(agent_scheduler, "_enqueue_manual", side_effect=self._record):
            agent_scheduler._tick()
        self.assertEqual(self.calls, [])

    def test_recurring_invalid_spec_rejected(self):
        r = agent_scheduler.schedule_task("marketing-agent", mode="recurring", message="X", schedule_spec="Hourly")
        self.assertFalse(r["ok"])

    def test_now_requires_message_and_enqueues(self):
        r = agent_scheduler.schedule_task("marketing-agent", mode="now", message="")
        self.assertFalse(r["ok"])
        with patch.object(agent_scheduler, "_enqueue_manual", side_effect=self._record):
            r = agent_scheduler.schedule_task("marketing-agent", mode="now", message="Haz algo ya")
        self.assertTrue(r["ok"])
        self.assertEqual(self.calls, [("marketing-agent", "Haz algo ya")])


class ProactiveTickTests(unittest.TestCase):
    """Análisis proactivo recurrente del scheduler (aislado, nunca toca producción)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp.name) / "scheduler_state.json"
        self.cfg = Path(self.tmp.name) / "maios.json"
        self.patch_state = patch("desktop.runtime.agent_scheduler._state_file", lambda: self.state_file)
        self.patch_state.start()
        self.patch_cfg = patch("desktop.runtime.config_store.CONFIG_FILE", self.cfg)
        self.patch_cfg.start()
        self.patch_started = patch("desktop.runtime.agent_scheduler._started", True)
        self.patch_started.start()

    def tearDown(self):
        self.patch_started.stop()
        self.patch_state.stop()
        self.patch_cfg.stop()
        self.tmp.cleanup()

    def _cfg_with_sales(self):
        from desktop.runtime import config_store
        cfg = config_store.load()
        cfg["organizedSales"] = [
            {
                "id": f"#{i}", "total": 25.0, "date": "2026-07-15",
                "line_items": [{"sku": "SKU-1", "price": 25.0, "quantity": 1}],
                "customer": "Cliente A",
            }
            for i in range(3)
        ]
        config_store.save(cfg)
        return cfg

    def test_proactive_tick_runs_detection_and_persists(self):
        from desktop.runtime import agent_scheduler, config_store
        self._cfg_with_sales()
        agent_scheduler._tick()
        cfg = config_store.load()
        self.assertTrue(cfg.get("businessFindings"), "el motor debe producir findings con datos")
        self.assertTrue(cfg.get("insights"), "los findings deben convertirse en insights")
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertIn("proactive_analysis", state.get("last_runs", {}))

    def test_proactive_tick_no_duplicates_on_second_run(self):
        from desktop.runtime import agent_scheduler, config_store
        self._cfg_with_sales()
        agent_scheduler._tick()
        n1 = len(config_store.load().get("insights") or [])
        agent_scheduler._tick()
        n2 = len(config_store.load().get("insights") or [])
        self.assertEqual(n1, n2, "el segundo tick no debe duplicar insights")

    def test_proactive_tick_skipped_when_scheduler_not_started(self):
        # Aislamiento: _tick() directo sin start() nunca escribe en el config.
        from desktop.runtime import agent_scheduler, config_store
        cfg = self._cfg_with_sales()
        cfg.pop("businessFindings", None)
        config_store.save(cfg)
        with patch("desktop.runtime.agent_scheduler._started", False):
            agent_scheduler._tick()
        self.assertFalse(config_store.load().get("businessFindings"), "sin start() no debe analizar ni guardar")


if __name__ == "__main__":
    unittest.main()
