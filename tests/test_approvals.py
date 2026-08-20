"""Approval workflow tests (Phase 13)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import approval_store, install_secrets


class ApprovalStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.secrets_file = base / "config" / "install_secrets.json"
        self.approvals_db = base / "approvals.db"
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
        self.secrets_patch = patch.object(install_secrets, "SECRETS_FILE", self.secrets_file)
        self.db_patch = patch.object(approval_store, "APPROVALS_DB", self.approvals_db)
        self.secrets_patch.start()
        self.db_patch.start()
        install_secrets.ensure_install_secrets()

    def tearDown(self):
        self.secrets_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_create_and_decide_approval(self):
        row = approval_store.create_approval(
            task_id="task-1",
            agent_id="agent-1",
            action="shopify.delete",
            risk_level="high",
            reason="Acción sensible",
        )
        self.assertEqual(row["status"], "pending")
        result = approval_store.decide(row["id"], "approved")
        self.assertTrue(result["ok"])
        self.assertEqual(result["approval"]["status"], "approved")

    def test_list_pending_approvals(self):
        approval_store.create_approval(task_id="t1", agent_id="a1", action="email.send")
        pending = approval_store.list_approvals(status="pending")
        self.assertEqual(len(pending), 1)


if __name__ == "__main__":
    unittest.main()
