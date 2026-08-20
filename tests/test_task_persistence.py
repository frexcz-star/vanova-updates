"""Persistent task queue tests (Phase 9)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import install_secrets, task_queue, task_store


class TaskPersistenceTests(unittest.TestCase):
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
        self.thread_patch = patch.object(task_queue.threading, "Thread", return_value=MagicMock())
        self.thread_patch.start()

    def tearDown(self):
        self.thread_patch.stop()
        self.secrets_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_enqueue_persists_task(self):
        with patch.object(task_queue, "_process_next"):
            task = task_queue.enqueue("agent-test", "manual", {"message": "hello"})
        self.assertEqual(task["status"], "queued")
        stored = task_store.list_recent_tasks(limit=10)
        self.assertTrue(any(t["id"] == task["id"] for t in stored))

    def test_tasks_survive_reload(self):
        with patch.object(task_queue, "_process_next"):
            task = task_queue.enqueue("agent-reload", "manual")
        task_id = task["id"]

        task_queue._loaded = False
        task_queue._queue.clear()
        task_queue._history.clear()
        with patch.object(task_queue, "_process_next"):
            task_queue._ensure_loaded()

        found = task_queue.get_task_by_id(task_id)
        self.assertIsNotNone(found)
        self.assertEqual(found["agentId"], "agent-reload")

    def test_task_events_recorded(self):
        with patch.object(task_queue, "_process_next"):
            task = task_queue.enqueue("agent-events", "manual")
        events = task_store.get_task_events(task["id"])
        types = {e["type"] for e in events}
        self.assertIn("created", types)
        self.assertIn("queued", types)


if __name__ == "__main__":
    unittest.main()
