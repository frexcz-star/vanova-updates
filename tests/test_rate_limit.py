"""Runtime rate limiting tests (Phase 6)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import rate_limit


class RuntimeRateLimitTests(unittest.TestCase):
    def setUp(self):
        rate_limit.reset_for_tests()

    def tearDown(self):
        rate_limit.reset_for_tests()

    def test_tasks_category_blocks_after_limit(self):
        with patch.dict(rate_limit.LIMITS, {"tasks": (3, 60)}):
            for _ in range(3):
                allowed, _ = rate_limit.check_rate_limit("tasks", "127.0.0.1")
                self.assertTrue(allowed)
            allowed, message = rate_limit.check_rate_limit("tasks", "127.0.0.1")
            self.assertFalse(allowed)
            self.assertIn("Límite", message)

    def test_hermes_category_has_limit(self):
        self.assertIn("hermes", rate_limit.LIMITS)
        allowed, _ = rate_limit.check_rate_limit("hermes", "test-client")
        self.assertTrue(allowed)

    def test_unknown_category_allows(self):
        allowed, message = rate_limit.check_rate_limit("unknown", "client")
        self.assertTrue(allowed)
        self.assertEqual(message, "")


if __name__ == "__main__":
    unittest.main()
