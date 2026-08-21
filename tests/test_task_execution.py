"""Real Hermes task execution tests (Phase 10)."""
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


class TaskExecutionTests(unittest.TestCase):
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

    def test_execute_task_requires_hermes_success(self):
        with patch("desktop.runtime.hermes_service.status", return_value={"healthy": True}):
            with patch(
                "desktop.runtime.hermes_chat.execute_sync",
                return_value={"status": "completed", "summary": "Done"},
            ):
                with patch("desktop.runtime.config_store.load", return_value={"agents": [{"id": "a1", "name": "Test"}]}):
                    result = task_queue._execute_task({"agentId": "a1", "payload": {}})
        self.assertEqual(result, "Done")

    def test_execute_task_fails_when_hermes_errors(self):
        with patch("desktop.runtime.hermes_service.status", return_value={"healthy": True}):
            with patch(
                "desktop.runtime.hermes_chat.execute_sync",
                return_value={"status": "error", "summary": "CLI failed"},
            ):
                with patch("desktop.runtime.config_store.load", return_value={"agents": []}):
                    with self.assertRaises(RuntimeError):
                        task_queue._execute_task({"agentId": "a1", "payload": {}})

    def test_execute_task_fails_when_hermes_offline(self):
        with patch("desktop.runtime.hermes_service.status", return_value={"healthy": False}):
            with self.assertRaises(RuntimeError):
                task_queue._execute_task({"agentId": "a1", "payload": {}})

    def test_execute_task_passes_agent_bot_profile(self):
        """FASE B (BUG-030): una tarea de un agente con bot Hermes debe ejecutarse
        bajo el perfil del bot (hermesBot) para que la conversación quede
        persistida en su perfil, no one-shot en el perfil por defecto."""
        calls = []
        with patch("desktop.runtime.hermes_service.status", return_value={"healthy": True}), \
             patch("desktop.runtime.hermes_chat.execute_sync",
                   side_effect=lambda *a, **kw: calls.append(kw) or {"status": "completed", "summary": "Done"}), \
             patch("desktop.runtime.config_store.load",
                   return_value={"agents": [{"id": "a1", "name": "Ventas", "hermesBot": "vanova-ventas"}]}), \
             patch("desktop.runtime.task_store.touch_heartbeat", return_value=None), \
             patch("desktop.runtime.agent_data_tools.render_context_block", return_value=""):
            result = task_queue._execute_task({"agentId": "a1", "payload": {}})
        self.assertEqual(result, "Done")
        self.assertEqual(calls[0].get("profile"), "vanova-ventas")


if __name__ == "__main__":
    unittest.main()
