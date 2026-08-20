"""Workspace isolation helpers for VANOVA Cloud (Phase 8)."""
from __future__ import annotations

import sqlite3

from fastapi import HTTPException


def ensure_memberships_table(conn: sqlite3.Connection) -> None:
    """Membership links users to workspaces (supports future multi-user workspaces)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memberships (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL,
            UNIQUE(workspace_id, user_id),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )


def sync_membership_from_user(conn: sqlite3.Connection, user_row: sqlite3.Row) -> None:
    """Ensure a membership row exists for legacy single-workspace users."""
    ensure_memberships_table(conn)
    membership_id = f"{user_row['workspace_id']}:{user_row['id']}"
    conn.execute(
        """
        INSERT INTO memberships (id, workspace_id, user_id, role, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id, user_id) DO UPDATE SET role=excluded.role
        """,
        (
            membership_id,
            user_row["workspace_id"],
            user_row["id"],
            user_row["role"],
            user_row["created_at"],
        ),
    )


def assert_row_in_workspace(
    conn: sqlite3.Connection,
    *,
    table: str,
    resource_id: str,
    workspace_id: str,
    id_column: str = "id",
    workspace_column: str = "workspace_id",
) -> sqlite3.Row:
    """Return row if it belongs to workspace; otherwise 404 (no cross-tenant leak)."""
    if not resource_id or not workspace_id:
        raise HTTPException(status_code=404, detail="Recurso no encontrado")
    allowed_tables = {
        "guardrails",
        "decisions",
        "hermes_requests",
        "hermes_conversations",
        "devices",
        "insights",
        "activity",
    }
    if table not in allowed_tables:
        raise ValueError(f"Table not allowed for tenancy check: {table}")

    row = conn.execute(
        f"SELECT * FROM {table} WHERE {id_column}=? AND {workspace_column}=?",
        (resource_id, workspace_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Recurso no encontrado")
    return row


def user_workspace_id(user: dict) -> str:
    ws = str(user.get("workspace_id") or "").strip()
    if not ws:
        raise HTTPException(status_code=403, detail="Workspace no disponible")
    return ws
