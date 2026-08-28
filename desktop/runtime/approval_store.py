"""Persistent approval workflow for agent actions (Phase 13)."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .install_secrets import get_installation_id
from .paths import data_dir

APPROVALS_DB = data_dir() / "approvals.db"
STATUSES = frozenset({"pending", "approved", "denied", "expired"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _workspace_id() -> str:
    return get_installation_id() or "local"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(APPROVALS_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            task_id TEXT,
            agent_id TEXT NOT NULL,
            action TEXT NOT NULL,
            risk_level TEXT DEFAULT 'medium',
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
        """
    )
    conn.commit()
    conn.close()


def create_approval(
    *,
    task_id: str,
    agent_id: str,
    action: str,
    risk_level: str = "medium",
    reason: str = "",
) -> dict[str, Any]:
    init_db()
    conn = _connect()
    # BUG-008: deduplicar aprobaciones. Una misma tarea+acción no debe generar
    # solicitudes de aprobación duplicadas (p.ej. si la política se re-evalúa para
    # la misma tarea). Si ya existe una 'pending' con la misma (task_id, action),
    # se devuelve esa en vez de crear otra.
    existing = conn.execute(
        "SELECT * FROM approvals WHERE workspace_id=? AND task_id=? AND action=? AND status='pending' "
        "ORDER BY created_at ASC LIMIT 1",
        (_workspace_id(), str(task_id), str(action)),
    ).fetchone()
    if existing:
        conn.close()
        return _row_to_dict(existing)

    approval_id = str(uuid.uuid4())
    now = _now()
    conn.execute(
        """INSERT INTO approvals
           (id, workspace_id, task_id, agent_id, action, risk_level, reason, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (approval_id, _workspace_id(), task_id, agent_id, action, risk_level, reason, "pending", now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_approvals(*, status: str | None = "pending", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    conn = _connect()
    if status:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE workspace_id=? AND status=? ORDER BY created_at DESC LIMIT ?",
            (_workspace_id(), status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
            (_workspace_id(), limit),
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_approval(approval_id: str) -> dict[str, Any] | None:
    init_db()
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM approvals WHERE id=? AND workspace_id=?",
        (approval_id, _workspace_id()),
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def decide(approval_id: str, decision: str, resolved_by: str = "user") -> dict[str, Any]:
    init_db()
    decision = (decision or "").strip().lower()
    if decision not in ("approved", "denied"):
        return {"ok": False, "error": "Decisión inválida"}

    conn = _connect()
    row = conn.execute(
        "SELECT * FROM approvals WHERE id=? AND workspace_id=?",
        (approval_id, _workspace_id()),
    ).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "Aprobación no encontrada"}
    if row["status"] != "pending":
        conn.close()
        return {"ok": False, "error": "Aprobación ya resuelta"}

    now = _now()
    conn.execute(
        "UPDATE approvals SET status=?, resolved_at=?, resolved_by=? WHERE id=?",
        (decision, now, resolved_by, approval_id),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    conn.close()
    return {"ok": True, "approval": _row_to_dict(updated)}


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "taskId": row["task_id"],
        "agentId": row["agent_id"],
        "action": row["action"],
        "riskLevel": row["risk_level"],
        "reason": row["reason"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "resolvedAt": row["resolved_at"],
        "resolvedBy": row["resolved_by"],
    }
