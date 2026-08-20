"""Command center and autonomy config tests (Phases 18, 24)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import autonomy_config, command_center, policy_engine


class AutonomyConfigTests(unittest.TestCase):
    def test_default_level(self):
        with patch("desktop.runtime.autonomy_config.config_store.load", return_value={}):
            self.assertEqual(autonomy_config.get_level(), "approval_required")

    def test_set_invalid_level(self):
        with patch("desktop.runtime.autonomy_config.config_store.save"):
            result = autonomy_config.set_level("invalid")
            self.assertFalse(result.get("ok"))

    def test_list_levels(self):
        with patch("desktop.runtime.autonomy_config.config_store.load", return_value={"autonomyLevel": "manual"}):
            levels = autonomy_config.list_levels()
            self.assertEqual(len(levels), 4)
            self.assertTrue(any(l["active"] for l in levels if l["level"] == "manual"))


class CommandCenterTests(unittest.TestCase):
    def test_snapshot_shape(self):
        with patch("desktop.runtime.command_center.task_queue.list_tasks", return_value=[]):
            with patch("desktop.runtime.command_center.task_queue.get_queue_status", return_value={"queued": 0}):
                with patch("desktop.runtime.command_center.agent_architect.list_agents", return_value=[]):
                    with patch("desktop.runtime.command_center.approval_store.list_approvals", return_value=[]):
                        with patch("desktop.runtime.command_center.config_store.load", return_value={"lastScan": {"dataMode": "empty"}}):
                            snap = command_center.get_home_snapshot()
        self.assertIn("attention", snap)
        self.assertIn("runningNow", snap)
        self.assertIn("recentResults", snap)


class AutonomyPolicyTests(unittest.TestCase):
    def test_manual_requires_approval(self):
        with patch("desktop.runtime.autonomy_config.get_level", return_value="manual"):
            decision = policy_engine.evaluate(action="shopify.read")
            self.assertEqual(decision.effect, "require_approval")

    def test_autonomous_allows_read(self):
        with patch("desktop.runtime.autonomy_config.get_level", return_value="autonomous"):
            decision = policy_engine.evaluate(action="shopify.read")
            self.assertEqual(decision.effect, "allow")


if __name__ == "__main__":
    unittest.main()
