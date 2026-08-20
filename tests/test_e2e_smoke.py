"""E2E smoke tests — critical API paths respond (Phase 25 starter)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import autonomy_config, command_center, runtime_security


class E2ESmokeTests(unittest.TestCase):
    def setUp(self):
        os.environ["MAIOS_DISABLE_TASK_SWEEPER"] = "1"

    def test_command_center_route_allowed(self):
        self.assertIn("/api/command-center", runtime_security.READ_GET_PATHS)

    def test_autonomy_route_allowed(self):
        self.assertIn("/api/autonomy", runtime_security.READ_GET_PATHS)
        self.assertIn("/api/autonomy", runtime_security.MUTATION_POST_PATHS)

    def test_autonomy_levels_complete(self):
        levels = {row["level"] for row in autonomy_config.list_levels()}
        self.assertEqual(levels, {"manual", "approval_required", "supervised", "autonomous"})

    def test_command_center_returns_json_serializable_keys(self):
        with patch("desktop.runtime.command_center.task_queue.list_tasks", return_value=[]):
            with patch("desktop.runtime.command_center.task_queue.get_queue_status", return_value={"queued": 0}):
                with patch("desktop.runtime.command_center.agent_architect.list_agents", return_value=[]):
                    with patch("desktop.runtime.command_center.approval_store.list_approvals", return_value=[]):
                        with patch(
                            "desktop.runtime.command_center.config_store.load",
                            return_value={"lastScan": {"dataMode": "empty"}},
                        ):
                            snap = command_center.get_home_snapshot(force=True)
        for key in ("attention", "runningNow", "recentResults", "queue"):
            self.assertIn(key, snap)

    def test_diagnostics_overall_present(self):
        from desktop.runtime import diagnostics_service

        diag = diagnostics_service.run_diagnostics()
        self.assertIn(diag["overall"], ("healthy", "degraded", "critical"))
        self.assertTrue(len(diag.get("checks", [])) >= 5)


if __name__ == "__main__":
    unittest.main()
