"""Agent Scheduler — runs enabled agents automatically on their schedules.

Agents declare schedules like ``"Daily 18:00"`` or ``"Weekly Monday 09:00"``
(local time). This module wakes every minute, finds schedules that have come
due since their last run, and enqueues a routine analysis task for the agent.

State (last-run timestamps) is persisted under the user data dir so a runtime
restart never re-runs a schedule that already fired.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import config_store, paths, task_queue
from .logger import get_logger

log = get_logger("maios.scheduler", "agent-scheduler")

TICK_INTERVAL_SEC = 60

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_lock = threading.Lock()
_started = False
_thread: threading.Thread | None = None
_stop_event: threading.Event | None = None


def _state_file() -> Path:
    return paths.data_dir() / "agent_scheduler_state.json"


def _load_state() -> dict[str, Any]:
    try:
        raw = _state_file().read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        _state_file().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("Could not persist scheduler state: %s", exc)


def parse_schedule(spec: str) -> dict[str, Any] | None:
    """Parse ``"Daily HH:MM"`` or ``"Weekly <weekday> HH:MM"`` into a rule dict."""
    s = " ".join((spec or "").lower().split())
    if not s:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", s)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    if s.startswith("daily"):
        return {"freq": "daily", "hour": hour, "minute": minute}
    if s.startswith("weekly"):
        weekday = next((idx for name, idx in _WEEKDAYS.items() if name in s), None)
        if weekday is None:
            return None
        return {"freq": "weekly", "weekday": weekday, "hour": hour, "minute": minute}
    return None


def _most_recent_occurrence(rule: dict[str, Any], now: datetime) -> datetime | None:
    """Most recent scheduled time <= now (local naive datetimes)."""
    if rule["freq"] == "daily":
        today = now.replace(hour=rule["hour"], minute=rule["minute"], second=0, microsecond=0)
        if today <= now:
            return today
        return today - timedelta(days=1)

    if rule["freq"] == "weekly":
        days_since = (now.weekday() - rule["weekday"]) % 7
        occ = (now - timedelta(days=days_since)).replace(
            hour=rule["hour"], minute=rule["minute"], second=0, microsecond=0
        )
        if occ <= now:
            return occ
        return occ - timedelta(days=7)

    return None


def _parse_last_run(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt
    except ValueError:
        return None


def _run_scheduled(agent: dict[str, Any], spec: str) -> None:
    from . import agent_architect

    try:
        payload = agent_architect.build_agent_payload(agent, scheduled=True, schedule_spec=spec)
        task = task_queue.enqueue(agent["id"], "scheduled", payload)
        log.info("Scheduled run queued: agent=%s task=%s", agent["id"], task["id"])
    except Exception as exc:
        log.warning("Scheduled enqueue failed for %s: %s", agent["id"], exc)


def _enqueue_manual(agent_id: str, message: str) -> dict[str, Any]:
    """Enqueue a human-delegated task: the message is the exact instruction sent to Hermes."""
    from . import agent_architect

    agent = next(
        (a for a in config_store.load().get("agents", []) if a.get("id") == agent_id),
        None,
    )
    payload: dict[str, Any] = {"message": message, "action": "analyze", "risk": "low"}
    if agent:
        base = agent_architect.build_agent_payload(agent, scheduled=False)
        payload.setdefault("permission", base.get("permission", "tasks.execute"))
    else:
        payload["permission"] = "tasks.execute"
    return task_queue.enqueue(agent_id, "manual", payload)


def _parse_due(due: str | None) -> datetime | None:
    if not due:
        return None
    try:
        return datetime.fromisoformat(str(due).replace("Z", "+00:00"))
    except ValueError:
        return None


def schedule_task(
    agent_id: str,
    *,
    mode: str,
    message: str,
    due: str | None = None,
    schedule_spec: str = "",
) -> dict[str, Any]:
    """Delegate a task to an agent: now / once (due ISO) / recurring (Daily|Weekly)."""
    msg = (message or "").strip()
    if not msg:
        return {"ok": False, "error": "La descripción de la tarea es obligatoria"}
    if mode == "now":
        task = _enqueue_manual(agent_id, msg)
        return {"ok": True, "mode": "now", "task": task}

    state = _load_state()
    if not isinstance(state.get("one_time"), list):
        state["one_time"] = []
    if not isinstance(state.get("recurring"), list):
        state["recurring"] = []

    if mode == "once":
        due_dt = _parse_due(due)
        if due_dt is None:
            return {"ok": False, "error": "Fecha de programación requerida (formato inválido)"}
        entry = {
            "id": uuid.uuid4().hex[:12],
            "agentId": agent_id,
            "message": msg,
            "due": due_dt.isoformat(),
            "createdAt": datetime.now().isoformat(),
        }
        state["one_time"].append(entry)
        _save_state(state)
        return {"ok": True, "mode": "once", "scheduleId": entry["id"], "due": entry["due"]}

    if mode == "recurring":
        rule = parse_schedule(schedule_spec)
        if not rule:
            return {
                "ok": False,
                "error": "Programación recurrente inválida (ej: 'Daily 18:00' o 'Weekly monday 09:00')",
            }
        entry = {
            "id": uuid.uuid4().hex[:12],
            "agentId": agent_id,
            "message": msg,
            "schedule": schedule_spec,
            "lastRun": None,
            "createdAt": datetime.now().isoformat(),
        }
        state["recurring"].append(entry)
        _save_state(state)
        return {"ok": True, "mode": "recurring", "scheduleId": entry["id"], "schedule": schedule_spec}

    return {"ok": False, "error": "Modo de ejecución desconocido: %s" % mode}


def delete_schedule(schedule_id: str) -> dict[str, Any]:
    """Remove a one-time or recurring delegated task schedule by id."""
    sid = str(schedule_id or "")
    if not sid:
        return {"ok": False, "error": "scheduleId requerido"}
    state = _load_state()
    changed = False
    for key in ("one_time", "recurring"):
        items = state.get(key)
        if isinstance(items, list):
            before = len(items)
            state[key] = [e for e in items if str(e.get("id")) != sid]
            if len(state[key]) != before:
                changed = True
    if changed:
        _save_state(state)
        return {"ok": True, "deleted": sid}
    return {"ok": False, "error": "Programación no encontrada"}


def next_runs() -> list[dict[str, Any]]:
    """Human-readable next-run info for the UI (agent, schedule, due in)."""
    now = datetime.now()
    out: list[dict[str, Any]] = []
    last_runs = _load_state().get("last_runs", {})
    for agent in config_store.load().get("agents", []):
        if agent.get("enabled") is False:
            continue
        for spec in agent.get("schedules", []):
            rule = parse_schedule(spec)
            if not rule:
                continue
            last = _parse_last_run(last_runs.get(f"{agent['id']}::{spec}"))
            occ = _most_recent_occurrence(rule, now)
            next_occ = occ + (timedelta(days=1) if rule["freq"] == "daily" else timedelta(days=7)) if occ else None
            out.append(
                {
                    "agentId": agent["id"],
                    "agentName": agent.get("name", agent["id"]),
                    "schedule": spec,
                    "lastRun": last.isoformat() if last else None,
                    "nextRun": next_occ.isoformat() if next_occ else None,
                }
            )
    return out


def _tick() -> None:
    now = datetime.now()
    agents = [a for a in config_store.load().get("agents", []) if a.get("enabled") is not False]
    state = _load_state()
    last_runs: dict[str, str] = state.get("last_runs", {}) if isinstance(state.get("last_runs"), dict) else {}
    changed = False

    # 0) VANOVA PRODUCT 8 — análisis proactivo recurrente: cada 6h re-ejecuta
    #    el motor sobre los datos actuales. Los findings se deduplican por
    #    firma (insight_store.sync_from_findings) y solo notifican cuando hay
    #    novedad real (lifecycle + createdAt estable). Nunca bloquea el tick.
    #    Solo se ejecuta cuando el scheduler real está arrancado (start()): una
    #    llamada directa a _tick() desde tests/scripts no debe tocar el config.
    try:
        proactive_key = "proactive_analysis"
        last_pro = _parse_last_run(last_runs.get(proactive_key))
        PROACTIVE_INTERVAL_HOURS = 6
        if _started and (last_pro is None or (now - last_pro) >= timedelta(hours=PROACTIVE_INTERVAL_HOURS)):
            data = config_store.load()
            if data.get("organizedSales") or data.get("organizedProducts"):
                from . import detection_engine, insight_store, prioritization

                res = detection_engine.run_detection(data, persist=False)
                findings = (res or {}).get("findings") or []
                if findings:
                    data["businessFindings"] = findings
                    data["detectionRunAt"] = (res or {}).get("ranAt")
                    insight_store.sync_from_findings(findings, data=data, active_signatures=(res or {}).get("freshSignatures"))
                    prioritization.persist(prioritization.build_priorities(findings), data=data)
                    # PRODUCT LEAP — medicion automatica: cada analisis recurrente
                    # re-mide las recomendaciones realizadas/resueltas con los
                    # datos actuales (sin esperar al usuario).
                    try:
                        from . import recommendation_store

                        # ESTABILIZACIÓN: el análisis recurrente también debe
                        # CREAR recomendaciones para findings nuevos (antes solo
                        # se creaban en la importación, así que un hallazgo
                        # detectado a las 6h nunca llegaba al ciclo
                        # recomendar→actuar→medir). ID estable por firma: el
                        # dedup evita duplicados en re-análisis.
                        for p in prioritization.build_priorities(findings, top=5):
                            fnd = next((x for x in findings if x.get("id") == p.get("findingId")), None)
                            if fnd:
                                recommendation_store.record_finding(fnd, data=data)
                        recommendation_store.sync_resolutions(findings, active_signatures=(res or {}).get("freshSignatures"), data=data)
                        recommendation_store.measure_all(data=data)
                    except Exception:  # noqa: BLE001
                        pass
                    config_store.save({
                        "businessFindings": findings,
                        "detectionRunAt": (res or {}).get("ranAt"),
                        "insights": data.get("insights") or [],
                        "priorities": data.get("priorities") or [],
                        "recommendations": data.get("recommendations") or [],
                    })
                last_runs[proactive_key] = now.isoformat()
                changed = True
                log.info(
                    "Proactive analysis tick: %s",
                    str((res or {}).get("counts") or {}),
                )
    except Exception as exc:  # noqa: BLE001 — el tick nunca debe caer por esto
        log.warning("Proactive analysis tick error: %s", exc)

    # 1) Agent routines declared in config (Daily/Weekly).
    for agent in agents:
        for spec in agent.get("schedules", []):
            rule = parse_schedule(spec)
            if not rule:
                continue
            occ = _most_recent_occurrence(rule, now)
            if occ is None:
                continue
            key = f"{agent['id']}::{spec}"
            last = _parse_last_run(last_runs.get(key))
            if last is not None and last >= occ:
                continue
            _run_scheduled(agent, spec)
            last_runs[key] = now.isoformat()
            changed = True

    # 2) Human-delegated one-time tasks (due <= now).
    one_time = state.get("one_time") if isinstance(state.get("one_time"), list) else []
    if one_time:
        pending = []
        kept = []
        for entry in one_time:
            due_dt = _parse_due(entry.get("due"))
            if due_dt is not None and due_dt <= now:
                pending.append(entry)
            else:
                kept.append(entry)
        for entry in pending:
            try:
                _enqueue_manual(entry.get("agentId", ""), entry.get("message", ""))
                log.info("One-time delegated task fired: %s", entry.get("id"))
            except Exception as exc:
                log.warning("One-time delegated enqueue failed %s: %s", entry.get("id"), exc)
        if pending:
            state["one_time"] = kept
            changed = True

    # 3) Human-delegated recurring tasks (Daily/Weekly with custom message).
    recurring = state.get("recurring") if isinstance(state.get("recurring"), list) else []
    if recurring:
        new_recurring = []
        for entry in recurring:
            rule = parse_schedule(entry.get("schedule", ""))
            if not rule:
                new_recurring.append(entry)
                continue
            occ = _most_recent_occurrence(rule, now)
            if occ is None:
                new_recurring.append(entry)
                continue
            last = _parse_last_run(entry.get("lastRun"))
            if last is not None and last >= occ:
                new_recurring.append(entry)
                continue
            try:
                _enqueue_manual(entry.get("agentId", ""), entry.get("message", ""))
                entry["lastRun"] = now.isoformat()
                changed = True
                log.info("Recurring delegated task fired: %s", entry.get("id"))
            except Exception as exc:
                log.warning("Recurring delegated enqueue failed %s: %s", entry.get("id"), exc)
            new_recurring.append(entry)
        state["recurring"] = new_recurring

    if changed:
        state["last_runs"] = last_runs
        _save_state(state)


def _loop(stop_event: threading.Event) -> None:
    log.info("Agent scheduler started (tick=%ds)", TICK_INTERVAL_SEC)
    while not stop_event.wait(TICK_INTERVAL_SEC):
        try:
            _tick()
        except Exception as exc:
            log.warning("Scheduler tick error: %s", exc)
    log.info("Agent scheduler stopped")


def start() -> bool:
    """Idempotently start the scheduler thread. Returns True if started now."""
    global _started, _thread, _stop_event
    with _lock:
        if _started:
            return False
        if _thread is not None and _thread.is_alive():
            _started = True
            return False
        _stop_event = threading.Event()
        _thread = threading.Thread(target=_loop, args=(_stop_event,), daemon=True, name="agent-scheduler")
        _thread.start()
        _started = True
        return True


def stop() -> None:
    global _started
    with _lock:
        if _stop_event is not None:
            _stop_event.set()
        _started = False


def status() -> dict[str, Any]:
    state = _load_state()
    one_time = state.get("one_time") if isinstance(state.get("one_time"), list) else []
    recurring = state.get("recurring") if isinstance(state.get("recurring"), list) else []
    now = datetime.now()
    def _agent_name(aid: str) -> str:
        agent = next((a for a in config_store.load().get("agents", []) if a.get("id") == aid), None)
        return agent.get("name", aid) if agent else aid
    for e in one_time:
        e.setdefault("agentName", _agent_name(e.get("agentId", "")))
    for e in recurring:
        e.setdefault("agentName", _agent_name(e.get("agentId", "")))
    return {
        "running": _started,
        "tickSeconds": TICK_INTERVAL_SEC,
        "nextRuns": next_runs(),
        "oneTime": one_time,
        "recurring": recurring,
        "delegatedCount": len(one_time) + len(recurring),
    }
