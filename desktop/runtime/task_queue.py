"""Task Queue — agent execution with permissions, policy, approvals (Phase 11-13)."""
from __future__ import annotations

import threading
import time
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from . import agent_permissions, approval_store, audit_log, policy_engine, task_store
from .logger import get_logger

log = get_logger("maios.queue", "task-queue")

_queue: list[dict] = []
_history: list[dict] = []
_loaded = False
_lock = threading.RLock()
_sweeper_started = False

STALE_STARTING_SEC = 120
STALE_RUNNING_SEC = 30 * 60
HEARTBEAT_INTERVAL_SEC = 30


class TaskStatus(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_APPROVAL = "needs_approval"
    BLOCKED = "blocked"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


def _background_tasks_disabled() -> bool:
    return os.getenv("MAIOS_DISABLE_TASK_SWEEPER", "").strip().lower() in ("1", "true", "yes")


def _ensure_loaded() -> None:
    global _loaded, _queue, _history
    if _loaded:
        return
    task_store.init_db()
    active = task_store.list_active_tasks()
    recent = task_store.list_recent_tasks(limit=100)
    with _lock:
        _queue = [
            t
            for t in active
            if t["status"]
            in (
                TaskStatus.QUEUED.value,
                TaskStatus.STARTING.value,
                TaskStatus.RUNNING.value,
            )
        ]
        finished = [
            t
            for t in recent
            if t["status"]
            in (
                TaskStatus.COMPLETED.value,
                TaskStatus.FAILED.value,
                TaskStatus.NEEDS_APPROVAL.value,
                TaskStatus.TIMED_OUT.value,
                TaskStatus.CANCELLED.value,
                TaskStatus.BLOCKED.value,
            )
        ]
        _history = finished[:100]
        _purge_stale_hermes_failures()
        _reconcile_stale_active_tasks()
    _loaded = True
    _start_sweeper()
    if _queue and not _background_tasks_disabled():
        threading.Thread(target=_process_next, daemon=True).start()


def _start_sweeper() -> None:
    global _sweeper_started
    if _sweeper_started:
        return
    if os.getenv("MAIOS_DISABLE_TASK_SWEEPER", "").strip().lower() in ("1", "true", "yes"):
        return
    _sweeper_started = True

    def loop() -> None:
        while True:
            try:
                _reconcile_stale_active_tasks()
            except Exception as exc:
                log.warning("Task sweeper error: %s", exc)
            time.sleep(60)

    threading.Thread(target=loop, daemon=True, name="task-sweeper").start()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _age_seconds(since: str | None) -> float | None:
    dt = _parse_ts(since)
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _reconcile_stale_active_tasks() -> None:
    """Mark stuck starting/running tasks as timed_out."""
    global _queue, _history
    now = _now()
    changed = False
    with _lock:
        for task in list(_queue):
            status = task.get("status")
            if status not in (TaskStatus.STARTING.value, TaskStatus.RUNNING.value):
                continue
            ref = task.get("heartbeatAt") or task.get("startedAt") or task.get("createdAt")
            age = _age_seconds(ref)
            if age is None:
                continue
            limit = STALE_STARTING_SEC if status == TaskStatus.STARTING.value else STALE_RUNNING_SEC
            if age < limit:
                if status == TaskStatus.RUNNING.value and not task.get("startedAt"):
                    task["startedAt"] = task.get("createdAt") or now
                    task_store.update_task_status(task["id"], TaskStatus.RUNNING.value, started_at=task["startedAt"])
                continue
            task["status"] = TaskStatus.TIMED_OUT.value
            task["error"] = task.get("error") or "Tarea detenida — superó el tiempo máximo sin progreso"
            task["completedAt"] = now
            task_store.update_task_status(
                task["id"],
                TaskStatus.TIMED_OUT.value,
                error=task["error"],
            )
            _history.insert(0, dict(task))
            _queue = [t for t in _queue if t.get("id") != task["id"]]
            changed = True
            audit_log.record(
                f"agent:{task.get('agentId')}",
                "task_timed_out",
                {"taskId": task["id"], "ageSec": age},
            )
            log.warning("Task %s timed out after %.0fs", task["id"], age)
    if changed and not _background_tasks_disabled():
        threading.Thread(target=_process_next, daemon=True).start()


def _purge_stale_hermes_failures() -> None:
    """Remove old failed Hermes tasks that predate virtual agent registration."""
    global _history
    kept: list[dict[str, Any]] = []
    removed = 0
    for task in _history:
        if (
            str(task.get("agentId") or "").lower() == "hermes"
            and task.get("status") == TaskStatus.FAILED.value
            and str(task.get("error") or "") == "Agente no encontrado"
        ):
            removed += 1
            continue
        kept.append(task)
    if removed:
        _history = kept
        log.info("Purged %d stale Hermes task failure(s)", removed)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_agent(agent_id: str) -> dict[str, Any] | None:
    from . import config_store

    aid = (agent_id or "").strip().lower()
    if aid == "hermes":
        return {
            "id": "hermes",
            "name": "Hermes",
            "enabled": True,
            "permissions": ["*"],
            "integrations": [],
            "tools": [],
        }

    agents = config_store.load().get("agents", [])
    return next((a for a in agents if a.get("id") == agent_id), None)


def enqueue(agent_id: str, task_type: str = "manual", payload: dict | None = None) -> dict[str, Any]:
    _ensure_loaded()
    task = task_store.create_task(agent_id, task_type, payload)
    audit_log.record(f"agent:{agent_id}", "task_created", {"taskId": task["id"], "type": task_type})
    with _lock:
        _queue.append(task)
    log.info("Task queued: %s for agent %s", task["id"], agent_id)
    threading.Thread(target=_process_next, daemon=True).start()
    return task


def retry_task(task_id: str) -> dict[str, Any] | None:
    """Re-queue a failed or timed_out task."""
    global _queue, _history
    _ensure_loaded()
    task = get_task_by_id(task_id)
    if not task:
        return None
    if task.get("status") not in (
        TaskStatus.FAILED.value,
        TaskStatus.TIMED_OUT.value,
        TaskStatus.CANCELLED.value,
    ):
        return {"ok": False, "error": "Solo se pueden reintentar tareas fallidas o expiradas"}
    attempts = task_store.increment_attempts(task_id)
    task["status"] = TaskStatus.QUEUED.value
    task["error"] = None
    task["result"] = None
    task["startedAt"] = None
    task["heartbeatAt"] = None
    task["completedAt"] = None
    task["attempts"] = attempts
    task_store.update_task_status(task_id, TaskStatus.QUEUED.value, error="", attempts=attempts)
    with _lock:
        _history = [t for t in _history if t.get("id") != task_id]
        if not any(t.get("id") == task_id for t in _queue):
            _queue.append(dict(task))
    audit_log.record("system", "task_retried", {"taskId": task_id, "attempts": attempts})
    threading.Thread(target=_process_next, daemon=True).start()
    return {"ok": True, "task": task}


def resume_task(task_id: str, *, approved: bool = False) -> dict[str, Any] | None:
    """Re-queue a task after a human decision.

    When ``approved`` is True the task carries explicit human approval, so the
    policy gate is bypassed for this execution (P2: approving a task must run
    it — it must NOT re-request approval and duplicate itself in the queue).
    """
    global _queue, _history
    _ensure_loaded()
    task = get_task_by_id(task_id)
    if not task:
        return None
    task["status"] = TaskStatus.QUEUED.value
    task["error"] = None
    task["result"] = None
    task["startedAt"] = None
    task["heartbeatAt"] = None
    task["completedAt"] = None
    if approved:
        task["approved"] = True
        task_store.mark_approved(task_id)
    task_store.update_task_status(task_id, TaskStatus.QUEUED.value, error="")
    with _lock:
        # Remove any previous history entry so the task is not duplicated.
        _history = [t for t in _history if t.get("id") != task_id]
        if not any(t.get("id") == task_id for t in _queue):
            _queue.append(dict(task))
    audit_log.record("system", "task_resumed", {"taskId": task_id, "approved": bool(approved)})
    threading.Thread(target=_process_next, daemon=True).start()
    return task


def _process_next() -> None:
    global _queue, _history
    with _lock:
        running = [
            t
            for t in _queue
            if t["status"] in (TaskStatus.STARTING.value, TaskStatus.RUNNING.value)
        ]
        if running:
            return
        pending = [t for t in _queue if t["status"] == TaskStatus.QUEUED.value]
        if not pending:
            return
        task = pending[0]
        task["status"] = TaskStatus.STARTING.value
        task["startedAt"] = _now()
        task["heartbeatAt"] = task["startedAt"]

    task_store.update_task_status(
        task["id"],
        TaskStatus.STARTING.value,
        started_at=task["startedAt"],
        heartbeat_at=task["heartbeatAt"],
    )
    audit_log.record(f"agent:{task.get('agentId')}", "task_starting", {"taskId": task["id"]})

    with _lock:
        task["status"] = TaskStatus.RUNNING.value
    task_store.update_task_status(task["id"], TaskStatus.RUNNING.value, heartbeat_at=_now())
    audit_log.record(f"agent:{task.get('agentId')}", "task_started", {"taskId": task["id"]})

    stop_heartbeat = threading.Event()

    def heartbeat_loop() -> None:
        while not stop_heartbeat.wait(HEARTBEAT_INTERVAL_SEC):
            try:
                task_store.touch_heartbeat(task["id"])
                with _lock:
                    task["heartbeatAt"] = _now()
            except Exception:
                pass

    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()

    try:
        outcome = _prepare_execution(task)
        if outcome == "needs_approval":
            task["status"] = TaskStatus.NEEDS_APPROVAL.value
            task["completedAt"] = _now()
            task_store.update_task_status(task["id"], TaskStatus.NEEDS_APPROVAL.value)
        elif outcome == "blocked":
            task["status"] = TaskStatus.BLOCKED.value
            task["error"] = task.get("error") or "Acción bloqueada por política"
            task["completedAt"] = _now()
            task_store.update_task_status(task["id"], TaskStatus.BLOCKED.value, error=task["error"])
        else:
            result = _execute_task(task)
            task["status"] = TaskStatus.COMPLETED.value
            task["result"] = result
            task["completedAt"] = _now()
            task_store.update_task_status(task["id"], TaskStatus.COMPLETED.value, result=result, progress=100)
            audit_log.record(f"agent:{task.get('agentId')}", "task_completed", {"taskId": task["id"]})
            _record_routine_insight(task, result)
    except Exception as exc:
        task["status"] = TaskStatus.FAILED.value
        task["error"] = str(exc)
        task["completedAt"] = _now()
        task_store.update_task_status(task["id"], TaskStatus.FAILED.value, error=str(exc))
        audit_log.record(
            f"agent:{task.get('agentId')}",
            "task_failed",
            {"taskId": task["id"], "error": str(exc)},
        )
        log.error("Task failed: %s", exc)
    finally:
        stop_heartbeat.set()

    with _lock:
        _history.insert(0, dict(task))
        if len(_history) > 100:
            _history.pop()
        _queue = [t for t in _queue if t["id"] != task["id"]]
    threading.Thread(target=_process_next, daemon=True).start()


def _prepare_execution(task: dict) -> str:
    """Permission + policy gate. Returns continue token or terminal status."""
    agent_id = task.get("agentId", "")
    agent = _load_agent(agent_id)
    payload = task.get("payload") or {}

    allowed, perm_err = agent_permissions.validate_task_execution(agent, payload)
    if not allowed:
        task["error"] = perm_err
        audit_log.record(f"agent:{agent_id}", "permission_denied", {"taskId": task["id"], "error": perm_err})
        raise RuntimeError(perm_err)

    if task.get("approved") or task.get("approvedAt"):
        # Human already approved this execution — do not request approval again.
        audit_log.record(f"agent:{agent_id}", "approval_bypassed", {"taskId": task["id"]})
        return "continue"

    action = str(payload.get("action") or payload.get("permission") or "task.execute")
    decision = policy_engine.evaluate(
        action=action,
        integration=str(payload.get("integration") or ""),
        tool=str(payload.get("tool") or ""),
        risk=str(payload.get("risk") or ""),
        agent=agent,
    )
    audit_log.record(
        f"agent:{agent_id}",
        "policy_evaluated",
        {"taskId": task["id"], "effect": decision.effect, "action": action},
    )

    if decision.effect == "deny":
        task["error"] = decision.reason
        audit_log.record(f"agent:{agent_id}", "policy_denied", {"taskId": task["id"], "reason": decision.reason})
        raise RuntimeError(decision.reason)

    if decision.effect == "require_approval":
        approval = approval_store.create_approval(
            task_id=task["id"],
            agent_id=agent_id,
            action=action,
            risk_level=decision.risk_level,
            reason=decision.reason,
        )
        audit_log.record(
            f"agent:{agent_id}",
            "approval_requested",
            {"taskId": task["id"], "approvalId": approval["id"]},
        )
        task["approvalId"] = approval["id"]
        return "needs_approval"

    return "continue"


def _record_routine_insight(task: dict, result: str) -> None:
    """A completed agent ROUTINE (scheduled, not user-delegated) becomes an
    insight — it must never pollute the user's Tasks view."""
    try:
        task_type = str(task.get("type") or "")
        if task_type != "scheduled" or not result:
            return
        from . import insight_store

        agent = _load_agent(task.get("agentId", ""))
        agent_name = (agent or {}).get("name") or task.get("agentId") or "Agente"
        insight_store.record(
            task.get("agentId", ""),
            agent_name,
            title=f"Informe de rutina: {agent_name}",
            summary=str(result)[:2000],
            kind="insight",
            meta={
                "taskId": task.get("id"),
                "scheduled": True,
                # The report belongs to the routine, not to a transient task
                # execution. This keeps the insight identity stable and lets
                # an owner action survive the next scheduled run.
                "routineKey": "scheduled:" + str(task.get("agentId") or ""),
            },
        )
    except Exception as exc:
        log.warning("Could not record routine insight: %s", exc)


def _execute_task(task: dict) -> str:
    """Execute via Hermes CLI — only completes when Hermes returns a real result.

    The agent runs with REAL business data (agent_data_tools.render_context_block
    is part of the operational context every Hermes call receives). If the model
    still claims a dataset is missing that actually exists, we resolve the tool
    and retry ONCE with the data appended — agents never ask the user to
    re-upload files VANOVA already has.
    """
    from . import agent_data_tools, config_store, hermes_chat, hermes_service

    if not hermes_service.status()["healthy"]:
        raise RuntimeError("Hermes offline — cannot execute task")

    agent_id = task.get("agentId", "")
    agents = config_store.load().get("agents", [])
    agent = next((a for a in agents if a.get("id") == agent_id), None)
    agent_name = agent.get("name", agent_id) if agent else agent_id
    payload = task.get("payload") or {}
    message = (
        payload.get("message")
        or f"Ejecuta la tarea manual asignada al agente {agent_name} (id={agent_id}). "
        "Resume acciones concretas realizadas."
    )
    # Task-specific data: the relevant real rows for THIS task/agent.
    try:
        data_block = agent_data_tools.render_context_block(limit=60)
        message = f"{message}\n\n{data_block}"
    except Exception:  # noqa: BLE001
        pass

    if task.get("id"):
        task_store.touch_heartbeat(task["id"], progress=10)
    result = hermes_chat.execute_sync(message)
    if task.get("id"):
        task_store.touch_heartbeat(task["id"], progress=50)
    if result.get("status") == "completed":
        reply = str(result.get("summary") or "")
        extra = _resolve_claimed_missing_data(reply)
        if extra:
            log.info("Agent claimed missing data that exists — retrying once with it")
            retry_msg = (
                f"{message}\n\n[ATENCIÓN: los datos que dices que faltan YA EXISTEN en VANOVA — "
                f"úsalos para responder. No vuelvas a pedir que los suban.]\n{extra}"
            )
            result2 = hermes_chat.execute_sync(retry_msg)
            if result2.get("status") == "completed":
                result = result2
    if task.get("id"):
        task_store.touch_heartbeat(task["id"], progress=90)
    if result.get("status") != "completed":
        raise RuntimeError(result.get("summary") or "Hermes execution failed")
    return str(result.get("summary") or "")


def _resolve_claimed_missing_data(reply: str) -> str:
    """If the model claims a dataset is missing that actually exists, return the
    real rows for it; otherwise empty string (no retry needed)."""
    from . import agent_data_tools

    r = (reply or "").lower()
    av = agent_data_tools.availability()
    blocks: list[str] = []

    wants_products = any(k in r for k in ("precio", "precios", "coste", "pvd", "margen", "margenes", "sku", "no tengo productos", "no tengo datos de producto", "necesito un csv", "necesito un excel", "sube el", "sube un", "no tengo acceso"))
    if wants_products and av["products"]["available"]:
        rows = agent_data_tools.get_products()["products"]
        lines = [f"PRODUCTOS REALES ({len(rows)}):"]
        for p in rows[:200]:
            net = p.get("netPrice")
            rrp = p.get("rrp")
            net_s = f"{net:.2f}" if isinstance(net, (int, float)) else "?"
            rrp_s = f"{rrp:.2f}" if isinstance(rrp, (int, float)) else "?"
            lines.append(f"  {p.get('sku') or '—'} | {p.get('name') or ''} | coste={net_s} | PVD={rrp_s}")
        blocks.append("\n".join(lines))

    wants_sales = any(k in r for k in ("venta", "ventas", "pedido", "pedidos", "orders", "sales", "por fecha", "históricas", "historicas"))
    if wants_sales and av["sales"]["available"]:
        rows = agent_data_tools.get_sales()["sales"]
        lines = [f"VENTAS/PEDIDOS REALES ({len(rows)}):"]
        for s in rows[:100]:
            lines.append(
                f"  {s.get('order_id') or s.get('order') or s.get('id') or '—'} | "
                f"{s.get('customer') or '—'} | {s.get('total') if s.get('total') is not None else '?'} | {s.get('date') or '—'}"
            )
        blocks.append("\n".join(lines))

    wants_inventory = any(k in r for k in ("stock", "inventario", "unidades disponibles"))
    if wants_inventory and av["products"]["available"]:
        inv = agent_data_tools.get_inventory()
        if inv["count"]:
            lines = [f"STOCK REAL ({inv['count']} SKUs con stock):"]
            for s in inv["inventory"][:100]:
                lines.append(f"  {s['sku'] or '—'} | {s['name'] or ''} | {s['stock']}")
            blocks.append("\n".join(lines))

    return "\n\n".join(blocks)

def _is_internal_task(task: dict[str, Any]) -> bool:
    """Return whether a task is platform work rather than a user request.

    This predicate is shared by the queue API and the UI contract. Scheduled
    routines, scanner/context maintenance and explicitly internal work belong
    in Insights/Activity, never in the user's Tasks list.
    """
    task_type = str(task.get("type") or task.get("taskType") or "").strip().lower()
    payload = task.get("payload") or {}
    if task_type in {"scheduled", "organize_files", "hermes_context", "context", "scanner", "system"}:
        return True
    if isinstance(payload, dict):
        return bool(
            payload.get("internal")
            or payload.get("source") in {"context", "scanner", "system", "hermes_context"}
            or payload.get("origin") in {"runtime", "scanner", "hermes_context"}
        )
    return False


def list_tasks() -> list[dict[str, Any]]:
    _ensure_loaded()
    with _lock:
        tasks = _dedupe_task_rows(_queue + _history[:20])
    return tasks


def list_user_tasks() -> list[dict[str, Any]]:
    """Return human-delegated tasks for UI consumers that must exclude routines."""
    return [task for task in list_tasks() if not _is_internal_task(task)]


def _dedupe_task_rows(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide duplicate stale Hermes failures from the UI."""
    seen_failed_hermes: set[str] = set()
    out: list[dict[str, Any]] = []
    for task in tasks:
        agent_id = str(task.get("agentId") or "")
        err = str(task.get("error") or "")
        if (
            agent_id.lower() == "hermes"
            and task.get("status") == TaskStatus.FAILED.value
            and err == "Agente no encontrado"
        ):
            key = agent_id + "|" + err
            if key in seen_failed_hermes:
                continue
            seen_failed_hermes.add(key)
        out.append(task)
    return out


def get_queue_status() -> dict[str, Any]:
    """Return one queue snapshot with an explicit user/internal split.

    ``tasks`` remains the public user-task list for backwards compatibility;
    ``allTasks`` and ``internalTasks`` let Activity/Agents show platform work
    without leaking it into Tasks.
    """
    _ensure_loaded()
    pending_approvals = len(approval_store.list_approvals(status="pending"))
    with _lock:
        all_tasks = _dedupe_task_rows(_queue + _history[:20])
    user_tasks = [t for t in all_tasks if not _is_internal_task(t)]
    internal_tasks = [t for t in all_tasks if _is_internal_task(t)]
    queued = len([t for t in user_tasks if t["status"] == TaskStatus.QUEUED.value])
    running = len([
        t for t in user_tasks
        if t["status"] in (TaskStatus.STARTING.value, TaskStatus.RUNNING.value)
    ])
    all_queued = len([t for t in all_tasks if t["status"] == TaskStatus.QUEUED.value])
    all_running = len([
        t for t in all_tasks
        if t["status"] in (TaskStatus.STARTING.value, TaskStatus.RUNNING.value)
    ])
    return {
        "queued": queued,
        "running": running,
        "allQueued": all_queued,
        "allRunning": all_running,
        "pendingApprovals": pending_approvals,
        "tasks": user_tasks,
        "userTasks": user_tasks,
        "allTasks": all_tasks,
        "internalTasks": internal_tasks,
    }


def get_task_by_id(task_id: str) -> dict[str, Any] | None:
    _ensure_loaded()
    with _lock:
        for task in _queue + _history:
            if task.get("id") == task_id:
                return dict(task)
    stored = task_store.get_task(task_id)
    if stored:
        return stored
    for task in task_store.list_recent_tasks(limit=200):
        if task.get("id") == task_id:
            return task
    return None
