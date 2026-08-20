"""Workspace isolation tests (Phase 8)."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloud"))

from fastapi import HTTPException  # noqa: E402
from tenancy import assert_row_in_workspace, ensure_memberships_table, sync_membership_from_user  # noqa: E402


class TenancyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT, created_at TEXT);
            CREATE TABLE users (id TEXT PRIMARY KEY, workspace_id TEXT, username TEXT, password_hash TEXT, role TEXT, created_at TEXT);
            CREATE TABLE guardrails (id TEXT PRIMARY KEY, workspace_id TEXT, agent TEXT, action TEXT, target TEXT, risk TEXT, status TEXT, created_at TEXT, decided_at TEXT);
            """
        )
        self.conn.execute("INSERT INTO workspaces VALUES ('ws-a', 'A', 't')")
        self.conn.execute("INSERT INTO workspaces VALUES ('ws-b', 'B', 't')")
        self.conn.execute(
            "INSERT INTO guardrails VALUES ('g1', 'ws-a', 'agent', 'delete', 'x', 'high', 'pending', 't', NULL)"
        )
        ensure_memberships_table(self.conn)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_resource_in_own_workspace_allowed(self):
        row = assert_row_in_workspace(
            self.conn, table="guardrails", resource_id="g1", workspace_id="ws-a"
        )
        self.assertEqual(row["id"], "g1")

    def test_cross_workspace_access_denied(self):
        with self.assertRaises(HTTPException) as ctx:
            assert_row_in_workspace(
                self.conn, table="guardrails", resource_id="g1", workspace_id="ws-b"
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_membership_sync(self):
        self.conn.execute(
            "INSERT INTO users VALUES ('u1', 'ws-a', 'ceo', 'hash', 'owner', 't')"
        )
        sync_membership_from_user(self.conn, self.conn.execute("SELECT * FROM users WHERE id='u1'").fetchone())
        self.conn.commit()
        row = self.conn.execute(
            "SELECT role FROM memberships WHERE workspace_id='ws-a' AND user_id='u1'"
        ).fetchone()
        self.assertEqual(row["role"], "owner")


if __name__ == "__main__":
    unittest.main()
