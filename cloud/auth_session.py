"""Refresh token persistence, rotation, and login rate limiting (Phase 5)."""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from time import time
from typing import Any

from fastapi import HTTPException

REFRESH_TOKEN_EXPIRE_DAYS = 7
ACCESS_TOKEN_EXPIRE_MINUTES = 15
LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW_SEC = 60

_login_attempts: dict[str, list[float]] = defaultdict(list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_refresh_tokens_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            device_id TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            last_used_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )


def check_login_rate_limit(client_key: str) -> None:
    now = time()
    window_start = now - LOGIN_RATE_WINDOW_SEC
    attempts = [t for t in _login_attempts[client_key] if t >= window_start]
    if len(attempts) >= LOGIN_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Demasiados intentos de inicio de sesión")
    attempts.append(now)
    _login_attempts[client_key] = attempts


def issue_refresh_token(conn: sqlite3.Connection, user_id: str, device_id: str = "") -> str:
    raw = secrets.token_urlsafe(48)
    token_id = str(uuid.uuid4())
    created = datetime.now(timezone.utc)
    expires = created + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    conn.execute(
        """INSERT INTO refresh_tokens
           (id, user_id, token_hash, device_id, created_at, expires_at, revoked_at, last_used_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            token_id,
            user_id,
            _hash_token(raw),
            device_id or None,
            created.isoformat(),
            expires.isoformat(),
            None,
            None,
        ),
    )
    return raw


def _fetch_active_token(conn: sqlite3.Connection, raw_token: str) -> sqlite3.Row | None:
    row = conn.execute(
        "SELECT * FROM refresh_tokens WHERE token_hash=? AND revoked_at IS NULL",
        (_hash_token(raw_token),),
    ).fetchone()
    if not row:
        return None
    expires = datetime.fromisoformat(str(row["expires_at"]))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        conn.execute(
            "UPDATE refresh_tokens SET revoked_at=? WHERE id=?",
            (_now_iso(), row["id"]),
        )
        return None
    return row


def rotate_refresh_token(conn: sqlite3.Connection, raw_token: str) -> tuple[str, sqlite3.Row]:
    row = _fetch_active_token(conn, raw_token)
    if not row:
        raise HTTPException(status_code=401, detail="Refresh token inválido o expirado")

    conn.execute(
        "UPDATE refresh_tokens SET revoked_at=?, last_used_at=? WHERE id=?",
        (_now_iso(), _now_iso(), row["id"]),
    )
    new_raw = issue_refresh_token(conn, str(row["user_id"]), str(row["device_id"] or ""))
    return new_raw, row


def revoke_refresh_token(conn: sqlite3.Connection, raw_token: str) -> bool:
    row = conn.execute(
        "SELECT id FROM refresh_tokens WHERE token_hash=? AND revoked_at IS NULL",
        (_hash_token(raw_token),),
    ).fetchone()
    if not row:
        return False
    conn.execute(
        "UPDATE refresh_tokens SET revoked_at=? WHERE id=?",
        (_now_iso(), row["id"]),
    )
    return True


def revoke_all_user_tokens(conn: sqlite3.Connection, user_id: str) -> int:
    cur = conn.execute(
        "UPDATE refresh_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
        (_now_iso(), user_id),
    )
    return cur.rowcount


def revoke_device_tokens(conn: sqlite3.Connection, user_id: str, device_id: str) -> int:
    cur = conn.execute(
        """UPDATE refresh_tokens SET revoked_at=?
           WHERE user_id=? AND device_id=? AND revoked_at IS NULL""",
        (_now_iso(), user_id, device_id),
    )
    return cur.rowcount


def login_response_fields(role: str) -> dict[str, Any]:
    return {
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "role": role,
    }
