"""Policy engine tests (Phase 12)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import policy_engine


class PolicyEngineTests(unittest.TestCase):
    def test_read_action_allowed(self):
        decision = policy_engine.evaluate(action="shopify.read", integration="shopify")
        self.assertEqual(decision.effect, "allow")

    def test_delete_requires_approval(self):
        decision = policy_engine.evaluate(action="shopify.delete", integration="shopify")
        self.assertEqual(decision.effect, "require_approval")

    def test_denied_action(self):
        decision = policy_engine.evaluate(action="delete_all")
        self.assertEqual(decision.effect, "deny")


if __name__ == "__main__":
    unittest.main()
