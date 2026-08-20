"""Role-based access control for VANOVA Cloud (Phase 7)."""
from __future__ import annotations

ROLES = frozenset({"owner", "admin", "operator", "viewer"})

# Explicit permissions per role. Owner receives all permissions.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset({"*"}),
    "admin": frozenset(
        {
            "workspace.read",
            "workspace.update",
            "members.read",
            "members.manage",
            "agents.read",
            "agents.configure",
            "agents.execute",
            "tasks.read",
            "tasks.create",
            "tasks.cancel",
            "approvals.read",
            "approvals.decide",
            "integrations.read",
            "integrations.configure",
            "billing.read",
            "billing.manage",
            "settings.read",
            "settings.manage",
        }
    ),
    "operator": frozenset(
        {
            "workspace.read",
            "agents.read",
            "agents.execute",
            "tasks.read",
            "tasks.create",
            "approvals.read",
            "integrations.read",
            "settings.read",
        }
    ),
    "viewer": frozenset(
        {
            "workspace.read",
            "agents.read",
            "tasks.read",
            "approvals.read",
            "integrations.read",
            "billing.read",
            "settings.read",
        }
    ),
}


def normalize_role(role: str | None) -> str:
    value = (role or "viewer").strip().lower()
    return value if value in ROLES else "viewer"


def has_permission(role: str | None, permission: str) -> bool:
    normalized = normalize_role(role)
    perms = ROLE_PERMISSIONS.get(normalized, ROLE_PERMISSIONS["viewer"])
    if "*" in perms:
        return True
    return permission in perms


def list_permissions(role: str | None) -> list[str]:
    normalized = normalize_role(role)
    perms = ROLE_PERMISSIONS.get(normalized, ROLE_PERMISSIONS["viewer"])
    if "*" in perms:
        return sorted({p for values in ROLE_PERMISSIONS.values() for p in values if p != "*"})
    return sorted(perms)
