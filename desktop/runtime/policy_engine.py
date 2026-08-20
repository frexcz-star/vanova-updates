"""Central policy engine for agent actions (Phase 12)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyDecision:
    effect: str  # allow | deny | require_approval
    reason: str = ""
    risk_level: str = "low"


DENY_ACTIONS = frozenset(
    {
        "delete_all",
        "drop_database",
        "format_disk",
        "rm_rf",
    }
)

HIGH_RISK_KEYWORDS = frozenset({"delete", "remove", "publish", "send", "transfer", "pay"})
CRITICAL_ALWAYS_APPROVAL = frozenset(
    {
        "delete",
        "delete_all",
        "publish",
        "send",
        "purchase",
        "payment",
        "transfer",
        "shopify.delete",
        "products.delete",
        "instagram.publish",
        "email.send",
    }
)

APPROVAL_ACTIONS = frozenset(
    {
        "shopify.delete",
        "instagram.publish",
        "email.send",
        "erp.write",
        "products.delete",
    }
)


def evaluate(
    *,
    action: str,
    integration: str = "",
    tool: str = "",
    risk: str = "",
    agent: dict[str, Any] | None = None,
) -> PolicyDecision:
    from . import autonomy_config

    act = (action or tool or "task.execute").strip().lower()
    integ = (integration or "").strip().lower()
    risk_level = (risk or _infer_risk(act)).strip().lower()
    global_level = autonomy_config.get_level()

    if act in DENY_ACTIONS:
        return PolicyDecision("deny", f"Acción prohibida: {act}", "critical")

    if act in CRITICAL_ALWAYS_APPROVAL or any(act.endswith(f".{kw}") for kw in ("delete", "publish", "send", "transfer", "payment")):
        return PolicyDecision("require_approval", f"Acción crítica — requiere aprobación: {act}", "critical")

    if global_level == "manual":
        return PolicyDecision("require_approval", "Nivel manual — requiere aprobación", "medium")

    if act in APPROVAL_ACTIONS:
        return PolicyDecision("require_approval", f"Requiere aprobación: {act}", "high")

    if risk_level in ("high", "critical"):
        if global_level == "autonomous" and risk_level != "critical":
            return PolicyDecision("allow", f"Autónomo — riesgo {risk_level} aceptado", risk_level)
        if global_level == "supervised" and risk_level == "high":
            return PolicyDecision("require_approval", f"Supervisado — riesgo alto: {act}", risk_level)
        return PolicyDecision("require_approval", f"Riesgo {risk_level}: {act}", risk_level)

    if any(kw in act for kw in HIGH_RISK_KEYWORDS) and integ:
        if global_level == "autonomous":
            return PolicyDecision("allow", f"Autónomo — acción en {integ}", "medium")
        return PolicyDecision("require_approval", f"Acción sensible en {integ}", "high")

    if agent and agent.get("autonomy") == "manual":
        return PolicyDecision("require_approval", "Autonomía manual — requiere aprobación", "medium")

    if global_level == "approval_required" and risk_level == "medium":
        return PolicyDecision("require_approval", f"Aprobación requerida — riesgo medio: {act}", "medium")

    return PolicyDecision("allow", "Acción permitida", risk_level or "low")


def _infer_risk(action: str) -> str:
    act = action.lower()
    if act in DENY_ACTIONS:
        return "critical"
    if act in APPROVAL_ACTIONS or any(k in act for k in HIGH_RISK_KEYWORDS):
        return "high"
    if act.endswith(".read") or act.startswith("read"):
        return "low"
    return "medium"
