"""Tests for Hermes CLI session sync from state.db."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.runtime import hermes_sessions


class HermesSessionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "state.db"
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT,
                started_at REAL NOT NULL,
                ended_at REAL,
                message_count INTEGER DEFAULT 0
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_name TEXT,
                timestamp REAL NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
            ("20260101_120000_abc123", "cli", None, 1700000000.0, 1700000100.0, 4),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_name, timestamp) VALUES (?,?,?,?,?)",
            ("20260101_120000_abc123", "user", "[Sistema] prompt] hola mundo", None, 1700000001.0),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_name, timestamp) VALUES (?,?,?,?,?)",
            ("20260101_120000_abc123", "tool", "{}", "terminal", 1700000002.0),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_name, timestamp) VALUES (?,?,?,?,?)",
            ("20260101_120000_abc123", "assistant", "Respuesta de prueba", None, 1700000003.0),
        )
        conn.commit()
        conn.close()
        self.db_patch = patch.object(hermes_sessions, "_db_path", return_value=self.db_path)
        self.db_patch.start()

    def tearDown(self) -> None:
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_list_sessions_returns_cli_rows(self) -> None:
        rows = hermes_sessions.list_sessions(limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["conversation_id"], "cli:20260101_120000_abc123")
        self.assertEqual(rows[0]["hermes_session_id"], "20260101_120000_abc123")
        self.assertEqual(rows[0]["title"], "hola mundo")
        self.assertEqual(rows[0]["source"], "hermes_cli")

    def test_get_session_messages_pairs_turns(self) -> None:
        msgs = hermes_sessions.get_session_messages("20260101_120000_abc123")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["message"], "hola mundo")
        self.assertEqual(msgs[0]["result"], "Respuesta de prueba")
        self.assertTrue(any(a["step"] == "terminal" for a in msgs[0]["activityLog"]))

    def test_parse_cli_conversation_id(self) -> None:
        self.assertEqual(
            hermes_sessions.parse_cli_conversation_id("cli:20260101_120000_abc123"),
            "20260101_120000_abc123",
        )
        self.assertEqual(hermes_sessions.parse_cli_conversation_id("conv-local"), "")

    def test_agent_task_sessions_are_filtered_out(self) -> None:
        # An agent-task execution persists as a Hermes CLI session with the
        # generated prompt as its title — it must NOT appear as a chat session.
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
            ("20260101_130000_def456", "cli", None, 1700001000.0, 1700001100.0, 2),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_name, timestamp) VALUES (?,?,?,?,?)",
            (
                "20260101_130000_def456",
                "user",
                "Inventory Agent, ejecuta tu rutina de análisis. Descripción: stock monitoring.",
                None,
                1700001001.0,
            ),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_name, timestamp) VALUES (?,?,?,?,?)",
            ("20260101_130000_def456", "assistant", "rutina completada", None, 1700001002.0),
        )
        conn.commit()
        conn.close()

        rows = hermes_sessions.list_sessions(limit=10)
        # Only the real "hola mundo" session remains.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["conversation_id"], "cli:20260101_120000_abc123")

    def test_agent_task_title_detection(self) -> None:
        self.assertTrue(hermes_sessions._is_agent_task_title("Sales Analyst, ejecuta tu rutina de análisis. Descripción:"))
        self.assertTrue(hermes_sessions._is_agent_task_title("Ejecuta la tarea manual asignada al agente hermes (id=hermes)."))
        self.assertFalse(hermes_sessions._is_agent_task_title("¿Cuántos pedidos hay hoy?"))
        self.assertFalse(hermes_sessions._is_agent_task_title("hola mundo"))


if __name__ == "__main__":
    unittest.main()
