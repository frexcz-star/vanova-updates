"""WebSocket auth tests — VANOVA 1.0.3."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "cloud"))

os.environ.setdefault("MAIOS_ENV", "development")
os.environ.setdefault("MAIOS_CLOUD_SECRET_KEY", "test-ws-secret-key-for-unit-tests-only")

from jose import jwt  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import cloud.main as cm  # noqa: E402


class WebSocketAuthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(cm.app)
        self.secret = cm.SECRET_KEY

    def _token(self, *, typ: str = "access", exp_offset: int = 900) -> str:
        expire = datetime.now(timezone.utc).timestamp() + exp_offset
        payload = {"sub": "u1", "ws": "ws1", "role": "owner", "exp": expire, "typ": typ}
        return jwt.encode(payload, self.secret, algorithm=cm.ALGORITHM)

    def test_ws_accepts_valid_access_token(self):
        with self.client.websocket_connect(f"/ws/dashboard?token={self._token()}") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg.get("type"), "connected")
            ws.send_text('{"type":"ping"}')
            pong = ws.receive_json()
            self.assertEqual(pong.get("type"), "pong")

    def test_ws_rejects_missing_token_with_auth_failed(self):
        with self.client.websocket_connect("/ws/dashboard") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg.get("type"), "auth_failed")

    def test_ws_rejects_refresh_token_type(self):
        with self.client.websocket_connect(f"/ws/dashboard?token={self._token(typ='refresh')}") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg.get("type"), "auth_failed")

    def test_ws_rejects_expired_token(self):
        with self.client.websocket_connect(f"/ws/dashboard?token={self._token(exp_offset=-60)}") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg.get("type"), "auth_failed")


if __name__ == "__main__":
    unittest.main()
