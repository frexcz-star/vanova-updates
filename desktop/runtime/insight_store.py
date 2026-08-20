"""Insight Store — results produced by agent ROUTINES (autonomous work).

A routine run (scheduled agent execution) is NOT a task: the user did not ask
for it, so it must not pollute the Tasks view. Its completed result becomes an
*insight* shown in the Insights view and in the agent's real-time card.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from . import config_store
from .logger import get_logger


def _routine_identity(agent_id: str, kind: str, title: str, meta: dict[str, Any] | None) -> str:
    """Build a stable identity for recurring reports across process restarts.

    ``routineKey`` lets callers keep the same identity even if the display title
    changes (for example when an agent is renamed). The fallback keeps legacy
    reports compatible with the old agent+title matching behavior.
    """
    routine_key = str((meta or {}).get("routineKey") or "").strip()
    return routine_key or f"{agent_id or ''}|{kind or 'insight'}|{title or ''}"

log = get_logger("maios.insights", "insight-store")

INSIGHTS_KEY = "insights"
MAX_INSIGHTS = 300


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> list[dict[str, Any]]:
    data = config_store.load().get(INSIGHTS_KEY) or []
    if not isinstance(data, list):
        return []
    return [i for i in data if isinstance(i, dict)]


def record(
    agent_id: str,
    agent_name: str,
    *,
    title: str,
    summary: str,
    kind: str = "insight",
    meta: dict[str, Any] | None = None,
    refresh_created: bool = True,
) -> dict[str, Any]:
    """Persist a new insight, newest first, capped at MAX_INSIGHTS.

    Stable ID: a routine report from the same agent with the same title reuses
    the existing id instead of minting a new UUID. This keeps user actions
    (approve/reject/dismiss, saved in insight_actions) attached to the same
    id, so a routine that runs every day does not resurrect itself with a
    fresh UUID every time.
    """
    if agent_name is None:
        agent_name = agent_id or "Agente"
    title = (title or "Informe de rutina").strip()
    items = _load()
    incoming_meta = dict(meta or {})
    identity = _routine_identity(agent_id or "", kind, title, incoming_meta)
    existing = next(
        (
            i for i in items
            if (
                (
                    str((i.get("meta") or {}).get("routineKey") or "").strip() == identity
                    or (
                        str(i.get("agentId") or "") == (agent_id or "")
                        and str(i.get("title") or "") == title
                    )
                )
                if incoming_meta.get("routineKey")
                else (
                    str(i.get("agentId") or "") == (agent_id or "")
                    and str(i.get("title") or "") == title
                )
            )
        ),
        None,
    )
    if existing:
        insight = dict(existing)
        insight["id"] = existing.get("id") or str(uuid.uuid4())
        insight["agentName"] = agent_name or agent_id or "Agente"
        insight["kind"] = kind
        insight["title"] = title
        insight["summary"] = (summary or "").strip()
        # VANOVA PROACTIVA: al refrescar un insight de detección existente se
        # conserva createdAt — un reanálisis del MISMO finding no debe reactivar
        # el badge como si fuera una notificación nueva.
        if refresh_created:
            insight["createdAt"] = _now()
        # Keep the action association alive when a recurring routine refreshes
        # its report. The separate action store is the source of truth for
        # visibility, so an approved/dismissed insight cannot resurrect.
        insight["status"] = insight.get("status") or "new"
        if incoming_meta:
            insight["meta"] = {**(insight.get("meta") or {}), **incoming_meta}
        items = [i for i in items if i.get("id") != insight["id"]]
        items.insert(0, insight)
        config_store.save({INSIGHTS_KEY: items[:MAX_INSIGHTS]})
        log.info("Insight updated (stable id) for agent %s: %s", agent_id, title[:60])
        return insight

    insight = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "vanova:insight:" + identity)),
        "agentId": agent_id or "",
        "agentName": agent_name or agent_id or "Agente",
        "kind": kind,
        "title": title,
        "summary": (summary or "").strip(),
        "createdAt": _now(),
        "status": "new",
    }
    if incoming_meta:
        insight["meta"] = incoming_meta
    items.insert(0, insight)
    config_store.save({INSIGHTS_KEY: items[:MAX_INSIGHTS]})
    log.info("Insight recorded for agent %s: %s", agent_id, title[:60])
    return insight


def list_insights(limit: int = 100) -> list[dict[str, Any]]:
    """Return only actionable insights; handled reports stay archived.

    Filtering at the runtime boundary prevents a new scan, a polling refresh,
    or a restart from reintroducing an item that the owner already approved,
    rejected, or dismissed. The UI still keeps the action map for optimistic
    rendering and cross-view synchronization.
    """
    from . import insight_actions

    actions = insight_actions.load_all()
    items = [i for i in _load() if str(i.get("id") or "") not in actions]
    items.sort(key=lambda i: str(i.get("createdAt") or ""), reverse=True)
    return items[:limit]


def count_by_agent() -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in list_insights(limit=MAX_INSIGHTS):
        aid = str(item.get("agentId") or "")
        if aid:
            counts[aid] = counts.get(aid, 0) + 1
    return counts


def latest_for_agent(agent_id: str) -> dict[str, Any] | None:
    aid = str(agent_id or "")
    for item in list_insights(limit=MAX_INSIGHTS):
        if str(item.get("agentId") or "") == aid:
            return item
    return None


# ----------------------------------------------------------------
# VANOVA PROACTIVA — puente detection_engine → insights de usuario
# ----------------------------------------------------------------
# Los findings del motor determinista (con evidencia y acción) se convierten
# en insights con identidad ESTABLE por firma del finding. Reanalizar la misma
# empresa NO crea 20 notificaciones: el mismo finding actualiza su insight
# (mismo id), y el lifecycle (new → visto/descartado → resuelto) evita spam.
# Un finding resuelto marca su insight como resuelto; si reaparece, vuelve a
# NEW para que el usuario vuelva a verlo.

FINDINGS_SOURCE = "detection_engine"
FINDINGS_AGENT = "VANOVA Proactiva"


def _finding_identity(f: dict[str, Any]) -> str:
    sig = str((f.get("meta") or {}).get("findingSignature") or f.get("signature") or "")
    return "detection:" + (sig or str(f.get("id") or ""))


def sync_from_findings(
    findings: list[dict[str, Any]] | None,
    *,
    data: dict[str, Any] | None = None,
    active_signatures: set[str] | list[str] | None = None,
) -> dict[str, Any]:
    """Sincroniza los insights de usuario con los findings activos del motor.

    * cada finding activo (problem/opportunity con evidencia) → un insight;
    * identidad estable por firma → dedup total entre análisis;
    * los insights cuyo finding ya no está activo se marcan ``resolved``;
    * un finding que reaparece vuelve a ``new`` (nueva evidencia).

    Nunca inventa: sin finding → sin insight. No borra nada: los insights
    resueltos se conservan en el historial.

    ``data`` (opcional): dict en memoria que contiene la clave ``insights``.
    Lo usan los callers con store inyectado (organize_files) para que el
    análisis post-import nunca relea/reescriba el config de otra instalación
    (aislamiento de tests y de instalaciones).

    ``active_signatures`` (opcional): firmas DETECTADAS EN LA ÚLTIMA EJECUCIÓN
    (result.freshSignatures del motor). Sin él, los findings históricos que
    run_detection conserva con lastSeenAt viejo impedirían marcar los insights
    como resolved cuando la condición ya no existe.
    """
    findings = [f for f in (findings or []) if isinstance(f, dict)]
    items = list(_load() if data is None else (data.get(INSIGHTS_KEY) or []))
    if data is None:
        items = _load()
    else:
        raw = data.get(INSIGHTS_KEY) or []
        items = [i for i in raw if isinstance(i, dict)]

    if active_signatures is not None:
        active_sigs: set[str] = {str(s) for s in active_signatures}
    else:
        active_sigs = set()
    reactivated: set[str] = set()
    created = 0
    updated = 0

    def _prev_status(sig: str) -> str | None:
        for item in items:
            if str((item.get("meta") or {}).get("findingSignature") or "") == sig and sig:
                return str(item.get("status") or "")
        return None

    def _save(items_list: list[dict[str, Any]]) -> None:
        if data is not None:
            data[INSIGHTS_KEY] = items_list[:MAX_INSIGHTS]
        else:
            config_store.save({INSIGHTS_KEY: items_list[:MAX_INSIGHTS]})

    for f in findings:
        status = str(f.get("status") or "active")
        category = str(f.get("category") or "")
        if status in ("resolved", "archived"):
            continue
        if category not in ("problem", "opportunity", "positive"):
            continue
        sig = str(f.get("signature") or "")
        if sig:
            active_sigs.add(sig)
        title = str(f.get("title") or f.get("finding_type") or "Hallazgo detectado")
        observation = str(f.get("observation") or "").strip()
        evidence = f.get("evidence") or []
        action = str(f.get("recommendedAction") or "").strip()
        imp = f.get("estimatedImpact") or {}
        euro = (
            imp.get("economicImpactEuro")
            or imp.get("inventoryValue")
            or imp.get("revenueAtRisk")
            or imp.get("marginPotential")
            or imp.get("monthlyIncrease")
        )
        summary = observation
        if evidence:
            summary += "\n\nEvidencia:\n" + "\n".join("- " + str(e) for e in evidence[:6])
        if action:
            summary += "\n\nAcción recomendada: " + action

        prev_status = _prev_status(sig) if sig else None
        if prev_status == "resolved" and sig:
            reactivated.add(sig)

        meta = {
            "source": "detection_engine",
            "findingSignature": sig,
            "routineKey": _finding_identity(f),
            "findingId": f.get("id"),
            "findingType": f.get("type") or f.get("finding_type") or "",
            "category": category,
            "severity": f.get("severity") or "",
            "entity": f.get("entity") or "",
            "impactEuro": euro,
            "confidence": f.get("confidence") or "",
            "evidence": evidence[:6],
            "recommendedAction": action,
        }
        identity = _finding_identity(f)
        existing = next((i for i in items if str(i.get("id") or "") == identity), None)
        if existing:
            existing.update({
                "agentName": FINDINGS_AGENT,
                "kind": "finding",
                "title": title,
                "summary": (summary or "").strip()[:2000],
                # Un reanálisis del MISMO finding conserva createdAt: no reactiva
                # el badge como notificación nueva.
                "meta": {**(existing.get("meta") or {}), **meta},
            })
            updated += 1
        else:
            items.insert(0, {
                "id": identity,
                "agentId": FINDINGS_SOURCE,
                "agentName": FINDINGS_AGENT,
                "kind": "finding",
                "title": title,
                "summary": (summary or "").strip()[:2000],
                "createdAt": _now(),
                "status": "new",
                "meta": meta,
            })
            created += 1

    # Lifecycle:
    # 1) finding ya no activo → insight RESOLVED;
    # 2) finding que reaparece tras resolverse → insight de vuelta a NEW.
    changed = False
    for item in items:
        meta = item.get("meta") or {}
        if meta.get("source") != "detection_engine":
            continue
        sig = str(meta.get("findingSignature") or "")
        if sig and sig not in active_sigs and str(item.get("status") or "") not in ("resolved", "archived"):
            item["status"] = "resolved"
            item["resolvedAt"] = _now()
            changed = True
        if sig in reactivated and str(item.get("status") or "") in ("resolved", "archived"):
            item["status"] = "new"
            item["resolvedAt"] = None
            item["reactivatedAt"] = _now()
            changed = True
    # Solo persiste cuando hay algo nuevo: un reanálisis sin cambios no escribe
    # (evita escrituras innecesarias y preserva el aislamiento en tests).
    if created or updated or changed:
        _save(items)

    return {"created": created, "updated": updated, "resolved": changed, "active": len(active_sigs)}
