"""Command Center home snapshot — attention, running-now, recent results (Phase 18)."""
from __future__ import annotations

import time
from typing import Any

from . import agent_architect, approval_store, config_store, task_queue
from .honest_state import describe_mode

_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_CACHE_TTL_SEC = 2.0


def _is_internal_task(task: dict[str, Any]) -> bool:
    """Scheduled routines and internal context work belong to Insights, not Tasks."""
    task_type = str(task.get("type") or task.get("taskType") or "").strip().lower()
    payload = task.get("payload") or {}
    return task_type in {"scheduled", "organize_files", "hermes_context", "context", "scanner", "system"} or bool(
        isinstance(payload, dict) and (
            payload.get("internal")
            or payload.get("source") in {"context", "scanner", "system", "hermes_context"}
            or payload.get("origin") in {"runtime", "scanner", "hermes_context"}
        )
    )


def get_home_snapshot(*, force: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    if not force and _CACHE["data"] is not None and (now - _CACHE["at"]) < _CACHE_TTL_SEC:
        return _CACHE["data"]
    data = _build_snapshot()
    _CACHE["at"] = now
    _CACHE["data"] = data
    return data


def _build_snapshot() -> dict[str, Any]:
    tasks = task_queue.list_tasks()
    queue_status = task_queue.get_queue_status()
    agents = agent_architect.list_agents()
    pending = approval_store.list_approvals(status="pending")

    # Agent routines remain visible in the agent status/Insights feed, but are
    # deliberately excluded from user task counts and recent task results.
    user_tasks = [t for t in tasks if not _is_internal_task(t)]
    running_agents = [a for a in agents if a.get("status") in ("running", "queued")]
    running_tasks = [t for t in user_tasks if t.get("status") == "running"]
    queued_tasks = [t for t in user_tasks if t.get("status") == "queued"]
    recent_completed = [
        t for t in user_tasks if t.get("status") == "completed" and t.get("result")
    ][:5]

    cfg = config_store.load()
    # VANOVA 3.0 (auditoría): lastScan puede existir con valor None (config de
    # instalación nueva) — nunca asumir dict. Sin datos → modo empty, no 500.
    last_scan = cfg.get("lastScan") or {}
    data_mode = describe_mode(last_scan.get("dataMode") or "empty")

    attention: list[dict[str, str]] = []
    if pending:
        attention.append(
            {
                "type": "approval",
                "title": f"{len(pending)} aprobación(es) pendiente(s)",
                "action": "approvals",
            }
        )
    from .integrations_store import VALID_IDS, _load_store

    integ_store = _load_store()
    configured = [iid for iid in VALID_IDS if iid in integ_store]
    disconnected = sum(1 for iid in configured if not integ_store[iid].get("connected"))
    if disconnected:
        attention.append(
            {
                "type": "integration",
                "title": f"{disconnected} integración(es) desconectada(s)",
                "action": "integrations",
            }
        )
    if data_mode.get("isDemo"):
        attention.append(
            {
                "type": "demo",
                "title": "Dashboard en modo demo",
                "action": "integrations",
            }
        )
    failed_tasks = [
        t
        for t in user_tasks
        if t.get("status") in ("failed", "timed_out", "blocked")
    ]
    if failed_tasks:
        attention.append(
            {
                "type": "task_failed",
                "title": f"{len(failed_tasks)} tarea(s) fallida(s)",
                "action": "tasks",
            }
        )

    # VANOVA PRODUCT 8 — prioridades REALES del motor (findings activos con
    # score económico). Se calculan sobre la marcha desde businessFindings; si
    # no hay findings con evidencia, no se inventa nada (lista vacía).
    recommendations = []
    try:
        from . import prioritization

        recommendations = prioritization.build_priorities(cfg.get("businessFindings") or [])
    except Exception:
        recommendations = []

    # Ingresos por periodo — calculados por el motor canónico (business_model),
    # el frontend solo presenta. UNKNOWN ≠ 0: si no hay evidencia, comparable
    # = False y revenue = None, nunca 0 € inventado.
    revenue_periods: dict[str, Any] = {}
    try:
        from . import business_model

        revenue_periods = business_model.period_revenue(cfg.get("organizedSales") or [])
    except Exception:
        revenue_periods = {}

    # Insights proactivos pendientes de revisión (nuevos primero).
    proactive: list[dict[str, Any]] = []
    try:
        from . import insight_store

        for ins in insight_store.list_insights(limit=100):
            if str(ins.get("status") or "") == "resolved":
                continue
            proactive.append(
                {
                    "id": ins.get("id", ""),
                    "agentId": ins.get("agentId", ""),
                    "agentName": ins.get("agentName", ""),
                    "kind": ins.get("kind", "insight"),
                    "title": ins.get("title", ""),
                    "summary": (ins.get("summary") or "")[:400],
                    "createdAt": ins.get("createdAt", ""),
                    "status": ins.get("status", "new"),
                    "impactEuro": (ins.get("meta") or {}).get("impactEuro"),
                }
            )
            if len(proactive) >= 6:
                break
    except Exception:
        proactive = []

    return {
        "revenuePeriods": revenue_periods,
        "proactiveInsights": proactive,
        "priorities": recommendations,
        "dataMode": data_mode,
        "attention": attention,
        "attentionCount": len(attention),
        "runningNow": {
            "agents": [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "status": a.get("status"),
                    "reason": a.get("statusReason", ""),
                }
                for a in running_agents[:8]
            ],
            "tasks": {
                "running": len(running_tasks),
                "queued": len(queued_tasks),
                "items": running_tasks + queued_tasks,
            },
        },
        "recentResults": [
            {
                "taskId": t.get("id"),
                "agentId": t.get("agentId"),
                "result": (t.get("result") or "")[:500],
                "completedAt": t.get("completedAt") or t.get("createdAt"),
            }
            for t in recent_completed
        ],
        "recommendations": recommendations,
        "queue": queue_status,
    }
