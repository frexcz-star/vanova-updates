"""Task stale detection and retry tests — VANOVA 1.0.3."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import install_secrets, task_queue, task_store


class TaskStaleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.secrets_file = base / "config" / "install_secrets.json"
        self.tasks_db = base / "tasks.db"
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)

        self.secrets_patch = patch.object(install_secrets, "SECRETS_FILE", self.secrets_file)
        self.db_patch = patch.object(task_store, "TASKS_DB", self.tasks_db)
        self.secrets_patch.start()
        self.db_patch.start()
        install_secrets.ensure_install_secrets()

        task_queue._loaded = False
        task_queue._queue.clear()
        task_queue._history.clear()
        task_queue._sweeper_started = False
        os.environ["MAIOS_DISABLE_TASK_SWEEPER"] = "1"

    def tearDown(self):
        self.secrets_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_row_to_task_includes_started_at_from_db(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=5)
        task = task_store.create_task("sales-analyst", "manual", {})
        task_store.update_task_status(
            task["id"],
            "running",
            started_at=old.isoformat(),
            heartbeat_at=old.isoformat(),
        )
        loaded = task_store.get_task(task["id"])
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["startedAt"], old.isoformat())

    def test_stale_running_task_times_out(self):
        stale = datetime.now(timezone.utc) - timedelta(minutes=45)
        task = task_store.create_task("sales-analyst", "manual", {})
        task_store.update_task_status(
            task["id"],
            "running",
            started_at=stale.isoformat(),
            heartbeat_at=stale.isoformat(),
        )
        with patch.object(task_queue, "_queue", [{"id": task["id"], "agentId": "sales-analyst", "status": "running", "startedAt": stale.isoformat(), "heartbeatAt": stale.isoformat(), "createdAt": stale.isoformat()}]):
            with patch.object(task_queue, "_history", []):
                with patch.object(task_queue, "_process_next"):
                    task_queue._reconcile_stale_active_tasks()
        updated = task_store.get_task(task["id"])
        self.assertEqual(updated["status"], "timed_out")

    def test_retry_failed_task_requeues(self):
        task = task_store.create_task("marketing-agent", "manual", {})
        task_store.update_task_status(task["id"], "failed", error="CLI failed")
        task_queue._loaded = True
        with patch.object(task_queue, "_process_next"):
            result = task_queue.retry_task(task["id"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["task"]["status"], "queued")
        self.assertGreaterEqual(result["task"]["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
