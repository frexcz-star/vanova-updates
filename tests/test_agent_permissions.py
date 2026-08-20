"""Agent permission enforcement tests (Phase 11)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import agent_permissions


class AgentPermissionTests(unittest.TestCase):
    def test_denies_missing_permission(self):
        agent = {
            "id": "marketing",
            "permissions": ["instagram.read", "content.create"],
            "integrations": ["instagram"],
            "tools": ["content.create"],
        }
        allowed, err = agent_permissions.validate_task_execution(
            agent, {"permission": "shopify.delete", "integration": "shopify"}
        )
        self.assertFalse(allowed)
        self.assertIn("shopify.delete", err)

    def test_allows_granted_permission(self):
        agent = {"id": "m", "permissions": ["tasks.execute"], "integrations": ["shopify"]}
        allowed, err = agent_permissions.validate_task_execution(
            agent, {"permission": "tasks.execute", "integration": "shopify"}
        )
        self.assertTrue(allowed)
        self.assertEqual(err, "")

    def test_denies_unauthorized_integration(self):
        agent = {"id": "m", "permissions": ["shopify.read"], "integrations": ["shopify"]}
        allowed, err = agent_permissions.validate_task_execution(
            agent, {"permission": "shopify.read", "integration": "instagram"}
        )
        self.assertFalse(allowed)
        self.assertIn("instagram", err)


if __name__ == "__main__":
    unittest.main()
