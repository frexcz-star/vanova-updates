"""Agent permission enforcement during task execution (Phase 11)."""
from __future__ import annotations

from typing import Any


def _agent_permissions(agent: dict[str, Any]) -> set[str]:
    raw = agent.get("permissions") or []
    return {str(p).strip().lower() for p in raw if str(p).strip()}


def _agent_integrations(agent: dict[str, Any]) -> set[str]:
    raw = agent.get("integrations") or []
    return {str(i).strip().lower() for i in raw if str(i).strip()}


def _agent_tools(agent: dict[str, Any]) -> set[str]:
    raw = agent.get("tools") or []
    return {str(t).strip().lower() for t in raw if str(t).strip()}


def has_permission(agent: dict[str, Any], permission: str) -> bool:
    perms = _agent_permissions(agent)
    if "*" in perms:
        return True
    if not perms:
        return False
    return permission.strip().lower() in perms


def can_use_integration(agent: dict[str, Any], integration_id: str) -> bool:
    integrations = _agent_integrations(agent)
    if not integrations:
        return False
    return integration_id.strip().lower() in integrations


def can_use_tool(agent: dict[str, Any], tool: str) -> bool:
    tools = _agent_tools(agent)
    if not tools:
        return False
    return tool.strip().lower() in tools


def validate_task_execution(agent: dict[str, Any] | None, payload: dict[str, Any] | None) -> tuple[bool, str]:
    """Return (allowed, error_message)."""
    if agent is None:
        return False, "Agente no encontrado"

    if agent.get("enabled") is False:
        return False, "Agente deshabilitado"

    data = payload or {}
    permission = str(data.get("permission") or "tasks.execute").strip().lower()
    if not has_permission(agent, permission):
        return False, f"Permiso denegado: {permission}"

    integration = str(data.get("integration") or "").strip().lower()
    if integration and not can_use_integration(agent, integration):
        return False, f"Integración no autorizada: {integration}"

    tool = str(data.get("tool") or "").strip().lower()
    if tool and not can_use_tool(agent, tool):
        return False, f"Herramienta no autorizada: {tool}"

    return True, ""
