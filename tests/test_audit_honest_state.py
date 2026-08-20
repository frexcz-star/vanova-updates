"""Audit log and honest state tests (Phase 14-15)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import audit_log, honest_state


class AuditAndHonestStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.audit_file = Path(self.tmp.name) / "audit.jsonl"
        self.patcher = patch.object(audit_log, "AUDIT_FILE", self.audit_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_audit_redacts_secrets(self):
        audit_log.record("user:1", "login", {"token": "secret-value", "note": "ok"})
        lines = self.audit_file.read_text(encoding="utf-8").strip().splitlines()
        entry = json.loads(lines[0])
        self.assertEqual(entry["detail"]["token"], "[REDACTED]")
        self.assertEqual(entry["detail"]["note"], "ok")

    def test_honest_state_mock_label(self):
        meta = honest_state.describe_mode("mock")
        self.assertTrue(meta["isDemo"])
        self.assertEqual(meta["label"], "Demo")

    def test_honest_state_partial_with_files(self):
        mode = honest_state.normalize_mode("empty", has_local_files=True)
        self.assertEqual(mode, "partial")


if __name__ == "__main__":
    unittest.main()
