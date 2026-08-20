"""Tests for agent dashboard status derivation."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import agent_architect


class AgentStatusTests(unittest.TestCase):
    def setUp(self):
        # H20: los tests con `config_store.load` parcheado nunca deben escribir
        # en el config real → `save` siempre es no-op.
        self._save_patch = patch.object(agent_architect.config_store, "save")
        self._save_patch.start()

    def tearDown(self):
        self._save_patch.stop()

    def test_latest_completed_task_shows_idle_not_stale_failed(self):
        now = datetime.now(timezone.utc)
        tasks = [
            {
                "agentId": "marketing-agent",
                "status": "failed",
                "updatedAt": (now - timedelta(hours=10)).isoformat(),
                "completedAt": (now - timedelta(hours=10)).isoformat(),
            },
            {
                "agentId": "marketing-agent",
                "status": "completed",
                "updatedAt": now.isoformat(),
                "completedAt": now.isoformat(),
            },
        ]
        agents = [{"id": "marketing-agent", "name": "Marketing Agent", "enabled": True}]
        with patch.object(agent_architect.config_store, "load", return_value={"agents": agents}), patch.object(
            agent_architect.process_manager, "status", return_value={"cloud": {"running": True}}
        ), patch.object(
            agent_architect.hermes_service, "status", return_value={"healthy": True}
        ), patch.object(agent_architect, "_runtime_available", return_value=True), patch.object(
            agent_architect.task_queue, "list_tasks", return_value=tasks
        ):
            rows = agent_architect.list_agents()
        self.assertEqual(rows[0]["status"], "idle")

    def test_recent_failed_task_shows_error(self):
        now = datetime.now(timezone.utc)
        tasks = [
            {
                "agentId": "sales-analyst",
                "status": "failed",
                "updatedAt": (now - timedelta(hours=1)).isoformat(),
                "completedAt": (now - timedelta(hours=1)).isoformat(),
            }
        ]
        agents = [{"id": "sales-analyst", "name": "Sales Analyst", "enabled": True}]
        with patch.object(agent_architect.config_store, "load", return_value={"agents": agents}), patch.object(
            agent_architect.process_manager, "status", return_value={"cloud": {"running": True}}
        ), patch.object(
            agent_architect.hermes_service, "status", return_value={"healthy": True}
        ), patch.object(agent_architect, "_runtime_available", return_value=True), patch.object(
            agent_architect.task_queue, "list_tasks", return_value=tasks
        ):
            rows = agent_architect.list_agents()
        self.assertEqual(rows[0]["status"], "error")

    def test_timed_out_latest_task_shows_idle(self):
        now = datetime.now(timezone.utc)
        tasks = [
            {
                "agentId": "sales-analyst",
                "status": "timed_out",
                "updatedAt": now.isoformat(),
                "completedAt": now.isoformat(),
            }
        ]
        agents = [{"id": "sales-analyst", "name": "Sales Analyst", "enabled": True}]
        with patch.object(agent_architect.config_store, "load", return_value={"agents": agents}), patch.object(
            agent_architect.process_manager, "status", return_value={"cloud": {"running": True}}
        ), patch.object(
            agent_architect.hermes_service, "status", return_value={"healthy": True}
        ), patch.object(agent_architect, "_runtime_available", return_value=True), patch.object(
            agent_architect.task_queue, "list_tasks", return_value=tasks
        ):
            rows = agent_architect.list_agents()
        self.assertEqual(rows[0]["status"], "idle")


if __name__ == "__main__":
    unittest.main()
