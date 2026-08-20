"""Diagnostics overall status — non-core issues should not mark critical."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import diagnostics_service, health_monitor, task_queue


class DiagnosticsOverallTests(unittest.TestCase):
    def test_overall_critical_only_for_core_checks(self):
        checks = [
            {"id": "runtime_port", "status": "ok"},
            {"id": "health_runtime", "status": "ok"},
            {"id": "health_cloud", "status": "ok"},
            {"id": "health_connector", "status": "warning"},
            {"id": "shopify", "status": "warning"},
        ]
        self.assertEqual(diagnostics_service._overall_from_checks(checks), "degraded")

    def test_shopify_reauth_is_warning_not_critical(self):
        status = diagnostics_service._shopify_diag_status("reauth_required")
        self.assertEqual(status, "warning")

    def test_connector_warning_does_not_degrade_overall(self):
        components = {
            "runtime": {"status": "ok"},
            "cloud": {"status": "ok"},
            "connector": {"status": "warning", "running": True, "authenticated": False},
            "hermes": {"status": "ok"},
            "aiProvider": {"status": "ok"},
            "maios": {"status": "ok"},
            "network": {"status": "ok"},
        }
        self.assertEqual(health_monitor._overall_from_components(components), "healthy")

    def test_hermes_virtual_agent_loads(self):
        agent = task_queue._load_agent("hermes")
        self.assertIsNotNone(agent)
        self.assertEqual(agent["id"], "hermes")


if __name__ == "__main__":
    unittest.main()
