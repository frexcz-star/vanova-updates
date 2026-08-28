"""Agent Architect — structured agent definitions and creation."""
from __future__ import annotations

import copy
import time
from datetime import datetime, timezone
from typing import Any

from . import config_store, hermes_service, process_manager, task_queue
from .logger import get_logger

log = get_logger("maios.agents", "agent-architect")

FAILED_STATUS_TTL_HOURS = 6


def _normalize_agent(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": a["id"],
        "name": a["name"],
        "description": a.get("description", ""),
        # BUG-029 FIX: preservar role y hermesBot (antes se descartaban, de ahí
        # que el config mostrara role=None y hermesBot=None).
        "role": a.get("role", ""),
        "hermesBot": a.get("hermesBot", ""),
        "responsibilities": a.get("responsibilities", []),
        "tools": a.get("tools", []),
        "integrations": a.get("integrations", []),
        "triggers": a.get("triggers", ["manual"]),
        "schedules": a.get("schedules", []),
        "permissions": a.get("permissions", []),
        "status": "idle",
        "enabled": True,
    }


# SISTEMA DE AGENTES MVP — el empresario crea su propio agente sin código
# (p.ej. "agente de ventas", "agente de contabilidad", "agente de stock").
_CUSTOM_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "sales": ["read_orders", "read_products", "read_analytics"],
    "accounting": ["read_invoices", "read_finance", "read_treasury"],
    "inventory": ["read_inventory", "read_products"],
    "marketing": ["read_analytics", "read_orders"],
    "support": ["read_customers", "read_orders"],
    "ceo": ["read_all"],
    "general": ["read_products", "read_orders"],
}


def create_custom_agent(*, name: str, role: str = "", description: str = "", responsibilities: list[str] | None = None) -> dict[str, Any]:
    """Crea un agente personalizado (MVP) desde la UI, sin código.

    El empresario da un nombre y un rol (ventas/contabilidad/stock/...); el
    sistema traduce el rol a permisos seguros y guarda el agente idempotente.
    El agente se ejecuta igual que el resto (task_queue → Hermes CLI).
    """
    import re

    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "El nombre del agente es obligatorio"}
    role = (role or "general").strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "agente"
    slug = f"custom-{base[:32]}"

    agent_def = {
        "id": slug,
        "name": name,
        "description": description or f"Agente personalizado de {name} creado desde VANOVA.",
        "role": role,
        "responsibilities": responsibilities or [f"Ejecutar la rutina de {name}"],
        "tools": [],
        "integrations": [],
        "triggers": ["manual"],
        "schedules": [],
        "permissions": _CUSTOM_ROLE_PERMISSIONS.get(role, _CUSTOM_ROLE_PERMISSIONS["general"]),
        "enabled": True,
    }
    added = add_agents([agent_def])
    if not added:
        return {"ok": False, "error": "El agente ya existe o no se pudo crear"}
    result = {"ok": True, "agent": added[0]}
    # FASE B — sincronizar a bot Hermes persistente (coexiste con Fase A).
    # add_agents ya sincroniza; aquí se reporta el estado honesto del bot.
    # BUG-029 FIX: si el bot NO se pudo sincronizar (Hermes no disponible), se
    # reporta explícitamente en vez de fallar en silencio.
    from . import agent_hermes_bot

    profile_name = str(added[0].get("hermesBot") or "")
    if profile_name and agent_hermes_bot.profile_exists(profile_name):
        result["bot"] = {"ok": True, "profile": profile_name, "exists": True}
        if added[0].get("schedules"):
            routines = agent_hermes_bot.sync_agent_routines(added[0])
            if routines.get("ok"):
                result["routines"] = routines.get("routines", [])
    else:
        # Sincronizar de nuevo por si add_agents no pudo (p.ej. Hermes arrancó
        # después) y reportar el estado real.
        bot = agent_hermes_bot.sync_agent_to_bot(added[0])
        if bot.get("ok") and bot.get("profile"):
            result["bot"] = bot
            added[0]["hermesBot"] = bot.get("profile")
        else:
            # Honesto: el agente existe pero su bot persistente no está listo.
            result["bot"] = {"ok": False, "error": (bot or {}).get("error") or "Bot de Hermes no disponible"}
            result["agent"]["hermesBot"] = ""

    return result


def _persist_hermes_bot_flag(cfg: dict[str, Any], profile_name: str) -> dict[str, Any]:
    """Marca en config el agente que tiene bot Hermes persistente (FASE B)."""
    agents = cfg.get("agents") or []
    if not isinstance(agents, list):
        agents = []
    for a in agents:
        if isinstance(a, dict) and str(a.get("id") or "") == "custom-" + profile_name.replace("vanova-", ""):
            a["hermesBot"] = profile_name
        elif isinstance(a, dict) and str(a.get("name") or "").lower() == profile_name.replace("vanova-", "").replace("-", " "):
            a["hermesBot"] = profile_name
    cfg["agents"] = agents
    return cfg


def create_agents(agent_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    created = [_normalize_agent(a) for a in agent_defs]
    config_store.save({"agents": created})
    log.info("Created %d agents", len(created))
    return created


def add_agents(agent_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge agents into the existing set without removing any (idempotent by id).

    BUG-006 FIX: usa config_store.update() (RMW atómico bajo un solo lock).
    Antes hacía load() → modificar → save() sin serializar el ciclo completo;
    con ThreadingHTTPServer dos requests concurrentes podían hacer lost-update
    (el agente guardado primero se perdía si el otro leyó antes).
    """
    added: list[dict[str, Any]] = []
    total: int = 0

    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        nonlocal added, total
        existing = cfg.get("agents", [])
        by_id = {str(a.get("id")): a for a in existing}
        added = []
        for a in agent_defs:
            normalized = _normalize_agent(a)
            if normalized["id"] in by_id:
                continue
            by_id[normalized["id"]] = normalized
            added.append(normalized)
        total = len(by_id)
        cfg["agents"] = list(by_id.values())
        return cfg

    config_store.update(_mutate)
    log.info("Added %d agent(s), total %d", len(added), total)
    # BUG-029 FIX: sincronizar cada agente nuevo a un bot Hermes persistente.
    # Antes solo create_custom_agent lo hacía; los agentes del catálogo
    # (/api/agents/add) quedaban sin hermesBot (bot no disponible). Ahora se
    # sincroniza Y se persiste el campo hermesBot + role.
    if added:
        _sync_added_agents_to_bots(added)
    return added


def _sync_added_agents_to_bots(added: list[dict[str, Any]]) -> None:
    """Sincroniza los agentes recién añadidos a bots Hermes y persiste hermesBot."""
    try:
        from . import agent_hermes_bot

        for agent in added:
            bot = agent_hermes_bot.sync_agent_to_bot(agent)
            if bot.get("ok") and bot.get("profile"):
                profile_name = bot.get("profile")
                agent["hermesBot"] = profile_name
                config_store.update(
                    lambda cfg: _persist_hermes_bot_flag(cfg, profile_name) if profile_name else cfg
                )
                if agent.get("schedules"):
                    agent_hermes_bot.sync_agent_routines(agent)
    except Exception as exc:  # noqa: BLE001
        log.warning("sync_agent_to_bot fallo (no bloquea): %s", exc)


def catalog() -> list[dict[str, Any]]:
    """Full agent catalog with an `installed` flag for each entry."""
    from . import business_analyst

    installed = {str(a.get("id")): a for a in config_store.load().get("agents", [])}
    out = []
    for a in business_analyst.AGENT_CATALOG:
        row = {k: v for k, v in a.items() if not k.startswith("match")}
        row["installed"] = a["id"] in installed
        out.append(row)
    return out


def build_agent_payload(agent: dict[str, Any], *, scheduled: bool = False, schedule_spec: str = "") -> dict[str, Any]:
    """Build a policy-safe, permission-safe task payload for a routine agent run."""
    name = agent.get("name") or agent.get("id")
    desc = (agent.get("description") or "").strip()
    resp = [str(r).strip() for r in (agent.get("responsibilities") or []) if str(r).strip()]
    perms = [str(p).strip() for p in (agent.get("permissions") or []) if str(p).strip()]
    # Prefer a read-type permission so the permission gate matches the agent's own grants.
    permission = next(
        (p for p in perms if p.lower().startswith("read") or p.lower().endswith(".read")),
        perms[0] if perms else "tasks.execute",
    )
    parts = [f"{name}, ejecuta tu rutina de análisis."]
    if desc:
        parts.append(f"Descripción: {desc}.")
    if resp:
        parts.append(f"Responsabilidades: {', '.join(resp)}.")
    parts.append("Usa solo datos reales disponibles en el sistema. Resume acciones concretas realizadas.")
    payload: dict[str, Any] = {
        "permission": permission,
        "action": "analyze",
        "risk": "low",
        "message": " ".join(parts),
        "scheduled": bool(scheduled),
    }
    if schedule_spec:
        payload["schedule"] = schedule_spec
    return payload


def run_agent_now(agent_id: str) -> dict[str, Any]:
    """Trigger an installed agent immediately with a routine analysis task."""
    agent = get_agent(agent_id)
    if not agent:
        return {"ok": False, "error": "Agente no encontrado"}
    if agent.get("enabled") is False:
        return {"ok": False, "error": "Agente deshabilitado"}
    payload = build_agent_payload(agent)
    task = task_queue.enqueue(agent_id, "manual", payload)
    return {"ok": True, "task": task}


# P6 (latencia): list_agents sondea procesos/estado por cada build del contexto
# de Hermes — TTL corto para eliminar las llamadas redundantes.
_agents_cache: list[dict[str, Any]] | None = None
_agents_cache_ts: float = 0.0
AGENTS_CACHE_TTL_SECONDS = 2.0


def list_agents() -> list[dict[str, Any]]:
    global _agents_cache, _agents_cache_ts
    now = time.monotonic()
    if _agents_cache is not None and (now - _agents_cache_ts) < AGENTS_CACHE_TTL_SECONDS:
        return copy.deepcopy(_agents_cache)
    _started = time.monotonic()
    agents = config_store.load().get("agents", [])
    runtime_ok = _runtime_available()
    cloud_ok = process_manager.status()["cloud"]["running"]
    hermes_ok = hermes_service.status()["healthy"]

    tasks = task_queue.list_tasks()
    latest_task_by_agent: dict[str, dict[str, Any]] = {}
    completed_by_agent: dict[str, int] = {}
    for task in tasks:
        agent_id = task.get("agentId")
        if not agent_id:
            continue
        if task.get("status") == "completed":
            completed_by_agent[agent_id] = completed_by_agent.get(agent_id, 0) + 1
        ts = str(
            task.get("updatedAt")
            or task.get("completedAt")
            or task.get("startedAt")
            or task.get("createdAt")
            or ""
        )
        prev = latest_task_by_agent.get(agent_id)
        if not prev or ts >= str(prev.get("_sortTs") or ""):
            latest_task_by_agent[agent_id] = {**task, "_sortTs": ts}

    try:
        from . import agent_scheduler, insight_store

        insights_by_agent = insight_store.count_by_agent()
        latest_insight_by_agent = {}
        for agent in agents:
            item = insight_store.latest_for_agent(agent.get("id"))
            if item:
                latest_insight_by_agent[agent.get("id")] = item
        next_run_by_agent: dict[str, str] = {}
        for nr in agent_scheduler.next_runs():
            aid = nr.get("agentId")
            if aid and nr.get("nextRun") and aid not in next_run_by_agent:
                next_run_by_agent[aid] = nr["nextRun"]
    except Exception:
        insights_by_agent, latest_insight_by_agent, next_run_by_agent = {}, {}, {}

    enriched = []
    for agent in agents:
        row = dict(agent)
        agent_id = agent.get("id")
        # BUG-007: reconciliar hermesBot al slug canónico (agent_slug). Evita que
        # un valor persistido obsoleto (p.ej. 'vanova-sales-analyst') apunte a un
        # perfil que no existe cuando el real es 'vanova-agente-de-ventas'.
        try:
            from . import agent_hermes_bot
            if (row.get("hermesBot") or row.get("hermes_bot")):
                row["hermesBot"] = agent_hermes_bot.agent_slug(agent)
        except Exception:  # noqa: BLE001
            pass
        latest = latest_task_by_agent.get(agent_id) or {}
        task_status = latest.get("status")
        if task_status == "running":
            row["status"] = "running"
            row["statusReason"] = "Ejecutando tarea"
        elif task_status == "queued":
            row["status"] = "queued"
            row["statusReason"] = "En cola de ejecución"
        elif task_status == "needs_approval":
            row["status"] = "waiting"
            row["statusReason"] = "Esperando aprobación"
        elif task_status == "failed":
            age = _task_age_hours(latest)
            if age is not None and age <= FAILED_STATUS_TTL_HOURS:
                row["status"] = "error"
                row["statusReason"] = "Última tarea falló"
            else:
                row["status"] = "idle"
                row["statusReason"] = "Listo"
        elif task_status == "timed_out":
            row["status"] = "idle"
            row["statusReason"] = "Listo"
        elif not runtime_ok:
            row["status"] = "offline"
            row["statusReason"] = "Runtime no disponible — puerto 8765"
        elif not cloud_ok:
            row["status"] = "waiting"
            row["statusReason"] = "Esperando VANOVA Cloud (puerto 8000)"
        elif not hermes_ok:
            row["status"] = "idle"
            row["statusReason"] = "Hermes offline — tareas en espera"
        else:
            row.setdefault("status", "idle")
            row.setdefault("statusReason", "Listo")

        # Real-time context for the Agents view.
        row["insightsGenerated"] = insights_by_agent.get(agent_id, 0)
        row["tasksCompleted"] = completed_by_agent.get(agent_id, 0)
        row["nextRun"] = next_run_by_agent.get(agent_id, "")
        latest_insight = latest_insight_by_agent.get(agent_id)
        row["lastInsight"] = latest_insight or None
        row["currentActivity"] = _describe_current_activity(latest)
        row["progress"] = int(latest.get("progress") or 0) if task_status in ("starting", "running") else 0
        row["taskType"] = latest.get("type") or ""
        enriched.append(row)
    # Solo se cachea una consulta cara (sondas reales); mocks rápidos en tests
    # siempre ven datos frescos.
    if (time.monotonic() - _started) >= 0.15:
        _agents_cache = enriched
        _agents_cache_ts = time.monotonic()
    return copy.deepcopy(enriched)


def _describe_current_activity(task: dict[str, Any]) -> str:
    status = task.get("status")
    if status in ("starting", "running"):
        payload = task.get("payload") or {}
        message = str(payload.get("message") or "").strip()
        base = "Ejecutando rutina de análisis…" if task.get("type") == "scheduled" else "Ejecutando tarea…"
        if message:
            return f"{base} {message[:140]}"
        return base
    if status == "queued":
        return "En cola de ejecución…"
    if status == "needs_approval":
        return "Esperando aprobación"
    return ""


def _runtime_available() -> bool:
    from . import port_utils
    return port_utils.probe_runtime()


def _task_age_hours(task: dict[str, Any]) -> float | None:
    raw = task.get("completedAt") or task.get("updatedAt") or task.get("createdAt")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except ValueError:
        return None


def get_agent(agent_id: str) -> dict | None:
    return next((a for a in list_agents() if a["id"] == agent_id), None)
