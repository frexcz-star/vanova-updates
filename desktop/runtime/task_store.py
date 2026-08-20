"""Persistent task storage for local runtime (Phase 9)."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .install_secrets import get_installation_id
from .paths import data_dir

TASKS_DB = data_dir() / "tasks.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _workspace_id() -> str:
    return get_installation_id() or "local"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(TASKS_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    additions = {
        "started_at": "TEXT",
        "heartbeat_at": "TEXT",
        "progress": "INTEGER DEFAULT 0",
        "attempts": "INTEGER DEFAULT 0",
        "completed_at": "TEXT",
        "approved_at": "TEXT",
    }
    for name, typedef in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {typedef}")


def init_db() -> None:
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            title TEXT,
            description TEXT,
            status TEXT NOT NULL,
            priority TEXT DEFAULT 'normal',
            task_type TEXT DEFAULT 'manual',
            payload TEXT,
            result TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT,
            started_at TEXT,
            heartbeat_at TEXT,
            progress INTEGER DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS task_runs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            status TEXT NOT NULL,
            result TEXT,
            error TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS task_events (
            id TEXT PRIMARY KEY,
            task_run_id TEXT,
            task_id TEXT NOT NULL,
            type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            payload TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks(workspace_id);
        """
    )
    _migrate_schema(conn)
    conn.commit()
    conn.close()


def _row_to_task(row: sqlite3.Row, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    payload = {}
    if row["payload"]:
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            payload = {}
    started_at = row["started_at"] if "started_at" in row.keys() else None
    if not started_at and conn is not None:
        run = conn.execute(
            "SELECT started_at FROM task_runs WHERE task_id=? AND started_at IS NOT NULL "
            "ORDER BY started_at DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        if run:
            started_at = run["started_at"]
    completed_at = None
    if "completed_at" in row.keys() and row["completed_at"]:
        completed_at = row["completed_at"]
    elif row["status"] in ("completed", "failed", "timed_out", "cancelled", "needs_approval", "blocked"):
        completed_at = row["updated_at"]
    heartbeat_at = row["heartbeat_at"] if "heartbeat_at" in row.keys() else None
    progress = int(row["progress"] or 0) if "progress" in row.keys() else 0
    attempts = int(row["attempts"] or 0) if "attempts" in row.keys() else 0
    approved_at = row["approved_at"] if "approved_at" in row.keys() else None
    return {
        "id": row["id"],
        "agentId": row["agent_id"],
        "type": row["task_type"],
        "status": row["status"],
        "payload": payload,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "startedAt": started_at,
        "heartbeatAt": heartbeat_at,
        "completedAt": completed_at,
        "progress": progress,
        "attempts": attempts,
        "approvedAt": approved_at,
        "result": row["result"],
        "error": row["error"],
    }


def create_task(
    agent_id: str,
    task_type: str = "manual",
    payload: dict | None = None,
    *,
    created_by: str = "runtime",
) -> dict[str, Any]:
    init_db()
    task_id = str(uuid.uuid4())
    now = _now()
    ws = _workspace_id()
    conn = _connect()
    conn.execute(
        """INSERT INTO tasks
           (id, workspace_id, agent_id, title, description, status, priority, task_type, payload,
            result, error, created_at, updated_at, created_by, started_at, heartbeat_at, progress, attempts, completed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id,
            ws,
            agent_id,
            f"Task for {agent_id}",
            "",
            "queued",
            "normal",
            task_type,
            json.dumps(payload or {}, ensure_ascii=False),
            None,
            None,
            now,
            now,
            created_by,
            None,
            None,
            0,
            0,
            None,
        ),
    )
    _append_event(conn, task_id, None, "created", {"agentId": agent_id})
    _append_event(conn, task_id, None, "queued", {})
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    task = _row_to_task(row, conn)
    conn.close()
    return task


def update_task_status(
    task_id: str,
    status: str,
    *,
    result: str | None = None,
    error: str | None = None,
    started_at: str | None = None,
    heartbeat_at: str | None = None,
    progress: int | None = None,
    attempts: int | None = None,
) -> None:
    init_db()
    conn = _connect()
    now = _now()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        conn.close()
        return
    fields: list[str] = ["status=?", "updated_at=?"]
    values: list[Any] = [status, now]
    if result is not None:
        fields.append("result=?")
        values.append(result)
    if error is not None:
        fields.append("error=?")
        values.append(error)
    elif status in ("completed", "failed", "timed_out", "cancelled"):
        pass
    if started_at:
        fields.append("started_at=?")
        values.append(started_at)
    if heartbeat_at:
        fields.append("heartbeat_at=?")
        values.append(heartbeat_at)
    elif status == "running":
        fields.append("heartbeat_at=?")
        values.append(now)
    if progress is not None:
        fields.append("progress=?")
        values.append(progress)
    if attempts is not None:
        fields.append("attempts=?")
        values.append(attempts)
    if status in ("completed", "failed", "timed_out", "cancelled", "needs_approval", "blocked"):
        fields.append("completed_at=?")
        values.append(now)
    values.append(task_id)
    conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=?", values)
    event_type = status if status in ("started", "completed", "failed", "cancelled", "timed_out") else "updated"
    _append_event(conn, task_id, None, event_type, {"status": status, "result": result, "error": error})
    if started_at and status in ("running", "starting"):
        run_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO task_runs (id, task_id, started_at, completed_at, status, result, error)
               VALUES (?,?,?,?,?,?,?)""",
            (run_id, task_id, started_at, None, "running", None, None),
        )
        _append_event(conn, task_id, run_id, "started", {})
    if status in ("completed", "failed", "timed_out", "cancelled"):
        conn.execute(
            """UPDATE task_runs SET completed_at=?, status=?, result=?, error=?
               WHERE task_id=? AND completed_at IS NULL""",
            (now, status, result, error, task_id),
        )
    conn.commit()
    conn.close()


def mark_approved(task_id: str) -> None:
    """Record that the task has explicit human approval for this execution.

    Used when a needs_approval task is resumed after the owner approved it, so
    the policy gate is bypassed and the task is NOT re-queued for approval.
    """
    init_db()
    conn = _connect()
    conn.execute(
        "UPDATE tasks SET approved_at=?, updated_at=? WHERE id=?",
        (_now(), _now(), task_id),
    )
    conn.commit()
    conn.close()


def touch_heartbeat(task_id: str, *, progress: int | None = None) -> None:
    init_db()
    conn = _connect()
    now = _now()
    if progress is not None:
        conn.execute(
            "UPDATE tasks SET heartbeat_at=?, updated_at=?, progress=? WHERE id=?",
            (now, now, progress, task_id),
        )
    else:
        conn.execute(
            "UPDATE tasks SET heartbeat_at=?, updated_at=? WHERE id=?",
            (now, now, task_id),
        )
    conn.commit()
    conn.close()


def list_active_tasks() -> list[dict[str, Any]]:
    init_db()
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE workspace_id=? AND status IN ('queued','starting','running') ORDER BY created_at ASC",
        (_workspace_id(),),
    ).fetchall()
    out = [_row_to_task(r, conn) for r in rows]
    conn.close()
    return out


def list_recent_tasks(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE workspace_id=? ORDER BY updated_at DESC LIMIT ?",
        (_workspace_id(), limit),
    ).fetchall()
    out = [_row_to_task(r, conn) for r in rows]
    conn.close()
    return out


def get_task(task_id: str) -> dict[str, Any] | None:
    init_db()
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM tasks WHERE id=? AND workspace_id=?",
        (task_id, _workspace_id()),
    ).fetchone()
    if not row:
        conn.close()
        return None
    task = _row_to_task(row, conn)
    conn.close()
    return task


def increment_attempts(task_id: str) -> int:
    init_db()
    conn = _connect()
    row = conn.execute("SELECT attempts FROM tasks WHERE id=?", (task_id,)).fetchone()
    attempts = int(row["attempts"] or 0) + 1 if row else 1
    conn.execute(
        "UPDATE tasks SET attempts=?, updated_at=? WHERE id=?",
        (attempts, _now(), task_id),
    )
    conn.commit()
    conn.close()
    return attempts


def _append_event(
    conn: sqlite3.Connection,
    task_id: str,
    task_run_id: str | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        """INSERT INTO task_events (id, task_run_id, task_id, type, timestamp, payload)
           VALUES (?,?,?,?,?,?)""",
        (
            str(uuid.uuid4()),
            task_run_id,
            task_id,
            event_type,
            _now(),
            json.dumps(payload, ensure_ascii=False),
        ),
    )


def get_task_events(task_id: str) -> list[dict[str, Any]]:
    init_db()
    conn = _connect()
    rows = conn.execute(
        "SELECT type, timestamp, payload FROM task_events WHERE task_id=? ORDER BY timestamp ASC",
        (task_id,),
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        payload = {}
        if row["payload"]:
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                payload = {}
        out.append({"type": row["type"], "timestamp": row["timestamp"], "payload": payload})
    return out
