"""Owner auth sync after Cloud restart / update."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bcrypt

from desktop.runtime import process_manager


class AuthSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name)
        self.db = self.cfg / "maios_cloud.db"
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TABLE users (id TEXT PRIMARY KEY, workspace_id TEXT, username TEXT, password_hash TEXT, role TEXT, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO users VALUES ('u1', 'ws1', 'ceo', ?, 'owner', '2026-01-01T00:00:00+00:00')",
            (bcrypt.hashpw(b"old-password", bcrypt.gensalt()).decode("utf-8"),),
        )
        conn.commit()
        conn.close()
        self.cloud_env = self.cfg / "cloud.env"
        self.cloud_env.write_text(
            "MAIOS_DEMO_USER=ceo\nMAIOS_DEMO_PASSWORD=new-password-123\n"
            f"MAIOS_DB={self.db}\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_sync_owner_password_in_db_updates_hash(self):
        with patch.object(process_manager, "config_dir", return_value=self.cfg):
            self.assertTrue(process_manager._sync_owner_password_in_db())
        conn = sqlite3.connect(self.db)
        row = conn.execute("SELECT password_hash FROM users WHERE username='ceo'").fetchone()
        conn.close()
        self.assertTrue(bcrypt.checkpw(b"new-password-123", row[0].encode("utf-8")))

    def test_load_env_file_strips_bom(self):
        bom_env = self.cfg / "bom.env"
        bom_env.write_bytes(b"\xef\xbb\xbfMAIOS_DEMO_USER=ceo\nMAIOS_DEMO_PASSWORD=x\n")
        loaded = process_manager._load_env_file(bom_env)
        self.assertEqual(loaded.get("MAIOS_DEMO_USER"), "ceo")
        self.assertEqual(loaded.get("MAIOS_DEMO_PASSWORD"), "x")


if __name__ == "__main__":
    unittest.main()
