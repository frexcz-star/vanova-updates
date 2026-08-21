"""Local runtime security helpers — auth, CORS, input validation (Phase 2)."""
from __future__ import annotations

import os
import re
from typing import Any

from . import install_secrets

# Origins allowed to call the runtime API from a browser (no wildcard in production).
CORS_ALLOWED_ORIGINS = frozenset(
    {
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "null",  # Electron file:// pages send Origin: null
    }
)

# Extra dev origins when MAIOS_DEV=1 (local dashboard experiments).
if os.environ.get("MAIOS_DEV", "").strip() in ("1", "true", "yes"):
    CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS | {
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    }

READ_GET_PATHS = frozenset(
    {
        "/api/health",
        "/api/setup/status",
        "/api/system/analyze",
        "/api/system/plan",
        "/api/install/progress",
        "/api/company/profile",
        "/api/agents/recommendations",
        "/api/agents",
        "/api/agents/catalog",
        "/api/agents/scheduler",
        "/api/hermes/status",
        "/api/hermes/chat-ready",
        "/api/hermes/conversations",
        "/api/hermes/config",
        "/api/hermes/providers",
        "/api/ai/status",
        "/api/health/all",
        "/api/health/ports",
        "/api/system/verify",
        "/api/tasks",
        "/api/updates/status",
        "/api/updates/manifest",
        "/api/diagnostics",
        "/api/version",
        "/api/scan/status",
        "/api/dashboard/local",
        "/api/files",
        "/api/products",
        "/api/sales",
        "/api/customers",
        "/api/organize/status",
        "/api/shopify/sync/status",
        "/api/facturascript/status",
        "/api/finance/overview",
        "/api/finance/reconcile",
        "/api/business/findings",
        "/api/products/reconciliation",
        "/api/products/reconciliation/export",
        "/api/products/coverage",
        "/api/sources",
        "/api/costs/status",
        "/api/costs/preview",
        "/api/integrity",
        "/api/hermes/activity",
        "/api/hermes/operational-context",
        "/api/ui/prefs",
        "/api/insight-actions",
        "/api/insights",
        "/api/files/candidates",
        "/api/approvals",
        "/api/audit",
        "/api/command-center",
        "/api/autonomy",
        "/api/integrations/lifecycle",
        "/api/backups/status",
        "/api/startup/status",
    }
)

# Prefix routes that remain READ (GET only).
READ_GET_PREFIXES = (
    "/api/hermes/requests/",
    "/api/hermes/conversations/",
    "/api/integrations/",
    "/api/tasks/",
    "/api/agent/data/",
)

# P2-1 (auditoría comercial): GET que exponen DATOS EMPRESARIALES. Aunque el
# runtime escucha solo en 127.0.0.1, cualquier proceso local podría leerlos;
# exigen el mismo token de instalación que los POST de mutación. El frontend ya
# adjunta el token (runtimeApi → getRuntimeAuthHeaders).
SENSITIVE_READ_PATHS = frozenset(
    {
        "/api/products",
        "/api/sales",
        "/api/business/findings",
        "/api/files",
        "/api/company/profile",
        "/api/finance/overview",
        # VANOVA 3.0 (auditoría completa): TODO GET que exponga datos
        # empresariales exige el token de instalación. Endpoints de bootstrap
        # (health/setup/version/scan-status/updates) quedan fuera a propósito.
        "/api/customers",
        "/api/data-health",
        "/api/command-center",
        "/api/insights",
        "/api/important",
        "/api/approvals",
        "/api/audit",
        "/api/insight-actions",
        "/api/backups/status",
        "/api/products/coverage",
        "/api/products/reconciliation",
        "/api/products/reconciliation/export",
        "/api/costs/status",
        "/api/costs/preview",
        "/api/sources",
        "/api/finance/reconcile",
        "/api/dashboard/local",
        "/api/tasks",
        "/api/company/model",
        "/api/recommendations",
    }
)

# Prefijos de GET sensibles: el payload completo (datos de empresa, listas de
# tareas con contenido de negocio) no debe leerse sin token.
SENSITIVE_READ_PREFIXES = (
    "/api/agent/data/",
    "/api/hermes/requests/",
    "/api/hermes/conversations/",
    "/api/tasks/",
)

MUTATION_POST_PATHS = frozenset(
    {
        "/api/company/profile",
        "/api/ai/configure",
        "/api/ai/test",
        "/api/hermes/provider/select",
        "/api/agents/create",
        "/api/agents/add",
        "/api/agents/run",
        "/api/install/run",
        "/api/setup/complete",
        "/api/setup/scan",
        "/api/scan/folders",
        "/api/setup/reset",
        "/api/setup/factory-reset",
        "/api/auth/login",
        "/api/ui/dismiss-architecture",
        "/api/ui/prefs",
        "/api/services/start",
        "/api/hermes/install",
        "/api/hermes/restart",
        "/api/hermes/ask",
        "/api/hermes/warm",
        "/api/tasks/run",
        "/api/tasks/retry",
        "/api/tasks/create",
        "/api/tasks/schedule/delete",
        "/api/recovery",
        "/api/updates/check",
        "/api/updates/download",
        "/api/updates/install",
        "/api/updates/cancel",
        "/api/updates/recovery",
        "/api/updates/postpone",
        "/api/files/add",
        "/api/files/candidates/decide",
        "/api/files/remove",
        "/api/products/add",
        "/api/products/match",
        "/api/products/match/remove",
        "/api/products/ignore",
        "/api/products/ignore/remove",
        "/api/shopify/identity-recovery",
        "/api/costs/import",
        "/api/organize/run",
        "/api/shopify/sync",
        "/api/shopify/backfill",
        "/api/facturascript/sync",
        "/api/facturascript/backfill",
        "/api/business/analyze",
        "/api/business/findings/status",
        "/api/integrity",
        "/api/insight-actions",
        "/api/approvals/decide",
        "/api/autonomy",
        "/api/backups/run",
        "/api/backups/restore",
        "/api/integrations/disconnect",
        "/api/integrations/test",
        "/api/integrations/hermes-prompt",
        "/api/important/mark",
        "/api/important/unmark",
        "/api/repair/run",
        "/api/data/reimport",
        "/api/data/review/dismiss",
        "/api/data/review/rearm",
        "/api/recommendations/status",
        "/api/actions/prepare",
        "/api/opportunities/done",
        "/api/data/integrity",
        "/api/notifications/send",
    }
)

MUTATION_POST_PREFIX = "/api/integrations/"
MUTATION_POST_SUFFIX = "/config"

RECOVERY_COMPONENTS = frozenset({"hermes", "connector", "cloud", "maios", "runtime"})
INTEGRATION_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
AGENT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
INSIGHT_ACTIONS = frozenset({"approved", "rejected", "dismissed"})


def cors_allow_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    if origin in CORS_ALLOWED_ORIGINS:
        return origin
    return None


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    value = authorization.strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


def validate_mutation_auth(authorization: str | None) -> bool:
    token = extract_bearer_token(authorization)
    return install_secrets.validate_runtime_token(token)


def is_read_get_path(path: str) -> bool:
    if path in READ_GET_PATHS:
        return True
    if path.startswith(READ_GET_PREFIXES[0]):
        return True
    if path.startswith(READ_GET_PREFIXES[1]) and path.endswith("/messages"):
        return True
    if path.startswith(READ_GET_PREFIXES[2]) and path.endswith("/config"):
        return True
    return False


def is_sensitive_read_path(path: str) -> bool:
    """GET de datos empresariales que requieren token de instalación (P2-1 +
    auditoría VANOVA 3.0). Cubre rutas exactas y prefijos de datos de negocio."""
    if path in SENSITIVE_READ_PATHS:
        return True
    for prefix in SENSITIVE_READ_PREFIXES:
        if path.startswith(prefix):
            return True
    # Config de integración (url/user de la conexión — no secretos, pero sí
    # datos de la empresa).
    if path.startswith("/api/integrations/") and path.endswith("/config"):
        return True
    return False


def is_mutation_post_path(path: str) -> bool:
    if path in MUTATION_POST_PATHS:
        return True
    if path.startswith(MUTATION_POST_PREFIX) and path.endswith(MUTATION_POST_SUFFIX):
        return True
    return False


def validate_integration_id(integration_id: str) -> str | None:
    iid = (integration_id or "").strip().lower()
    if not iid or not INTEGRATION_ID_RE.match(iid):
        return "Integración no válida"
    return None


def validate_agent_id(agent_id: str) -> str | None:
    aid = (agent_id or "").strip()
    if not aid:
        return "agentId requerido"
    if not AGENT_ID_RE.match(aid):
        return "agentId no válido"
    return None


def validate_recovery_component(component: str) -> str | None:
    comp = (component or "").strip().lower()
    if not comp:
        return "component requerido"
    if comp not in RECOVERY_COMPONENTS:
        return "component no válido"
    return None


def validate_insight_action(action: str) -> str | None:
    act = (action or "").strip().lower()
    if act not in INSIGHT_ACTIONS:
        return "action no válida"
    return None


def sanitize_import_path(raw: str) -> tuple[str | None, str | None]:
    """Normalize import path metadata; reject traversal sequences."""
    path = (raw or "").strip()
    if not path:
        return None, "Falta la ruta del archivo"
    normalized = path.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None, "Ruta no permitida"
    if normalized.startswith("//") or path.startswith("\\\\"):
        return None, "Ruta no permitida"
    return path, None


def validation_error(message: str) -> dict[str, Any]:
    return {"error": message}
