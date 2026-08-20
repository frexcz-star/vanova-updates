"""Approval loop regression tests (P2 fix).

Bug: approving a needs_approval task re-queued it, but _prepare_execution
re-evaluated the policy and requested approval AGAIN — so approving never ran
the task, created a new identical approval, and duplicated the task in the
list.

Fix: resume_task(approved=True) records explicit human approval; the policy
gate is bypassed for that execution and the previous history entry is removed.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import approval_store, install_secrets, task_queue, task_store
from desktop.runtime import autonomy_config as _autonomy_config


class ApprovalLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.secrets_file = base / "config" / "install_secrets.json"
        self.tasks_db = base / "tasks.db"
        self.approvals_db = base / "approvals.db"
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)

        self.secrets_patch = patch.object(install_secrets, "SECRETS_FILE", self.secrets_file)
        self.db_patch = patch.object(task_store, "TASKS_DB", self.tasks_db)
        self.appr_patch = patch.object(approval_store, "APPROVALS_DB", self.approvals_db)
        self.secrets_patch.start()
        self.db_patch.start()
        self.appr_patch.start()
        install_secrets.ensure_install_secrets()

        task_queue._loaded = False
        task_queue._queue.clear()
        task_queue._history.clear()
        task_queue._sweeper_started = False
        os.environ["MAIOS_DISABLE_TASK_SWEEPER"] = "1"
        self.thread_patch = patch.object(task_queue.threading, "Thread", return_value=MagicMock())
        self.thread_patch.start()

    def tearDown(self):
        self.thread_patch.stop()
        self.appr_patch.stop()
        self.db_patch.stop()
        self.secrets_patch.stop()
        self.tmp.cleanup()

    def _enqueue_pending_approval(self):
        """Enqueue a task and force the policy gate to request approval."""
        with patch.object(task_queue, "_process_next"):
            task = task_queue.enqueue("hermes", "manual", {"permission": "task.execute", "message": "x"})
        task_id = task["id"]
        with patch.object(_autonomy_config, "get_level", return_value="manual"):
            outcome = task_queue._prepare_execution(dict(task))
        self.assertEqual(outcome, "needs_approval")
        pending = approval_store.list_approvals(status="pending")
        self.assertEqual(len(pending), 1)
        return task_id, pending[0]["id"]

    def test_approved_resume_bypasses_policy_and_does_not_duplicate(self):
        task_id, approval_id = self._enqueue_pending_approval()

        # Approve + resume (exactly what /api/approvals/decide does).
        with patch.object(task_queue, "_process_next"):
            resumed = task_queue.resume_task(task_id, approved=True)
        self.assertIsNotNone(resumed)
        self.assertTrue(resumed.get("approved") or resumed.get("approvedAt"))

        # Task must appear exactly once in the queue and NOT in history.
        queue_ids = [t["id"] for t in task_queue._queue]
        hist_ids = [t["id"] for t in task_queue._history]
        self.assertEqual(queue_ids.count(task_id), 1)
        self.assertNotIn(task_id, hist_ids)

        # Re-evaluating the gate on the approved task must bypass and create
        # NO new approval (the original loop).
        before = len(approval_store.list_approvals(status="pending"))
        with patch.object(_autonomy_config, "get_level", return_value="manual"):
            outcome = task_queue._prepare_execution(dict(resumed))
        self.assertEqual(outcome, "continue")
        after = len(approval_store.list_approvals(status="pending"))
        self.assertEqual(after, before, "approval must not be requested again")

    def test_unapproved_resume_still_requests_approval(self):
        task_id, _ = self._enqueue_pending_approval()
        with patch.object(task_queue, "_process_next"):
            resumed = task_queue.resume_task(task_id, approved=False)
        self.assertIsNotNone(resumed)
        # Without approval, the gate must still require approval (no bypass).
        with patch.object(_autonomy_config, "get_level", return_value="manual"):
            outcome = task_queue._prepare_execution(dict(resumed))
        self.assertEqual(outcome, "needs_approval")

    def test_approved_flag_persists_in_db(self):
        task_id, _ = self._enqueue_pending_approval()
        with patch.object(task_queue, "_process_next"):
            task_queue.resume_task(task_id, approved=True)
        stored = task_store.get_task(task_id)
        self.assertIsNotNone(stored)
        self.assertIsNotNone(stored.get("approvedAt"), "approved_at must persist for restarts")


if __name__ == "__main__":
    unittest.main()
