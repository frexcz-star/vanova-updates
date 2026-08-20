"""RBAC permission tests (Phase 7)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloud"))

from rbac import has_permission, list_permissions, normalize_role  # noqa: E402


class RbacTests(unittest.TestCase):
    def test_owner_has_all_permissions(self):
        self.assertTrue(has_permission("owner", "integrations.configure"))
        self.assertTrue(has_permission("owner", "billing.manage"))

    def test_viewer_cannot_configure_integrations(self):
        self.assertFalse(has_permission("viewer", "integrations.configure"))
        self.assertTrue(has_permission("viewer", "integrations.read"))

    def test_operator_can_execute_agents(self):
        self.assertTrue(has_permission("operator", "agents.execute"))
        self.assertFalse(has_permission("operator", "members.manage"))

    def test_admin_can_decide_approvals(self):
        self.assertTrue(has_permission("admin", "approvals.decide"))

    def test_unknown_role_defaults_to_viewer(self):
        self.assertEqual(normalize_role("superuser"), "viewer")
        perms = list_permissions("viewer")
        self.assertIn("workspace.read", perms)
        self.assertNotIn("integrations.configure", perms)


if __name__ == "__main__":
    unittest.main()
