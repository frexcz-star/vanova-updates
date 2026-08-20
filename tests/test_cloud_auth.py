"""Cloud auth session tests (Phase 5)."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOUD_DIR = ROOT / "cloud"
sys.path.insert(0, str(CLOUD_DIR))

from auth_session import (  # noqa: E402
    check_login_rate_limit,
    issue_refresh_token,
    revoke_all_user_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
)
from fastapi import HTTPException  # noqa: E402


class CloudAuthSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE users (id TEXT PRIMARY KEY, workspace_id TEXT, username TEXT, password_hash TEXT, role TEXT, created_at TEXT)"
        )
        self.conn.execute(
            "INSERT INTO users VALUES ('u1', 'ws1', 'demo', 'hash', 'owner', '2026-01-01T00:00:00+00:00')"
        )
        from auth_session import ensure_refresh_tokens_table

        ensure_refresh_tokens_table(self.conn)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_refresh_token_rotation(self):
        raw = issue_refresh_token(self.conn, "u1", "device-a")
        self.conn.commit()
        new_raw, row = rotate_refresh_token(self.conn, raw)
        self.conn.commit()
        self.assertNotEqual(raw, new_raw)
        self.assertEqual(row["user_id"], "u1")
        with self.assertRaises(HTTPException):
            rotate_refresh_token(self.conn, raw)

    def test_logout_revokes_token(self):
        raw = issue_refresh_token(self.conn, "u1")
        self.conn.commit()
        self.assertTrue(revoke_refresh_token(self.conn, raw))
        self.conn.commit()
        self.assertFalse(revoke_refresh_token(self.conn, raw))

    def test_logout_all_revokes_everything(self):
        issue_refresh_token(self.conn, "u1", "d1")
        issue_refresh_token(self.conn, "u1", "d2")
        self.conn.commit()
        count = revoke_all_user_tokens(self.conn, "u1")
        self.conn.commit()
        self.assertEqual(count, 2)

    def test_login_rate_limit(self):
        key = "login:test:demo"
        for _ in range(5):
            check_login_rate_limit(key)
        with self.assertRaises(HTTPException) as ctx:
            check_login_rate_limit(key)
        self.assertEqual(ctx.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
