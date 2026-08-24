"""VANOVA PRODUCT 8 — Priorización real de hallazgos.

Convierte los findings activos del detection engine en las 1-3 cosas que la
empresa debería mirar AHORA, con un score determinista:

    score = impacto económico × confianza × severidad × urgencia

Reglas:
* Nunca inventa impacto: sin importe cuantificable se usa peso de señal
  (severidad × confianza), nunca un 0 € ni una cifra arbitraria.
* UNKNOWN ≠ 0: un finding sin evidencia económica se prioriza por severidad,
  pero su impacto se muestra como «no cuantificable» y eso baja su score.
* Determinista y reproducible: mismo estado → misma prioridad.
* Lifecycle: los findings resueltos/archivados nunca entran.
"""
from __future__ import annotations

from typing import Any

PRIORITIES_KEY = "priorities"

_SEVERITY_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0}
_CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.7, "low": 0.4}

# Mapeo category -> type que el frontend (updateBellBadge / buildNotificationsBody)
# usa para filtrar las prioridades que cuentan como "Riesgos detectados" en el
# contador de la campana (store.priorities.filter(p.type === 'risk')). BUG-054:
# sin este campo, el badge y el drawer contaban SIEMPRE 0 riesgos (sub-conteo).
_CATEGORY_TO_TYPE = {
    "risk": "risk",
    "problem": "risk",
    "anomaly": "risk",
    "prediction": "risk",
    "opportunity": "opportunity",
}


def _priority_type(f: dict[str, Any]) -> str:
    """Tipo que el frontend usa para el contador de notificaciones.

    Un finding category='risk'/'problem' es un riesgo; category='opportunity'
    es una oportunidad. Cualquier otra cosa se trata conservadoramente como
    riesgo (un hallazgo sin clasificar requiere atención)."""
    cat = str(f.get("category") or "problem").lower()
    return _CATEGORY_TO_TYPE.get(cat, "risk")


def _impact_euro(f: dict[str, Any]) -> float | None:
    """Importe económico cuantificado del finding (todas las fuentes del motor).
    None = no cuantificable (UNKNOWN ≠ 0)."""
    imp = f.get("estimatedImpact") or {}
    for key in ("economicImpactEuro", "inventoryValue", "revenueAtRisk",
                "marginPotential", "cashRequired", "monthlyIncrease"):
        v = imp.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


def _impact_kind(f: dict[str, Any]) -> str:
    imp = f.get("estimatedImpact") or {}
    return "calculated" if imp.get("kind") == "calculated" else "estimated"


def _urgency_boost(f: dict[str, Any]) -> float:
    """Señales de urgencia temporal reales (nunca inventadas)."""
    boost = 1.0
    typ = str(f.get("type") or "")
    if typ in ("stockout_risk", "treasury_cash_shortfall", "inconsistent_order_total"):
        boost = 1.25
    return boost


def score_finding(f: dict[str, Any]) -> float:
    sev = _SEVERITY_WEIGHT.get(str(f.get("severity") or ""), 1.0)
    conf = _CONFIDENCE_WEIGHT.get(str(f.get("confidence") or ""), 0.5)
    euro = _impact_euro(f)
    base = sev * conf * _urgency_boost(f)
    if euro is not None and euro > 0:
        # Log-scale: el impacto importa pero un gap de €1.000 vs €100.000 no
        # multiplica por 100 el score (evita que un solo finding lo domine todo).
        return base * (1.0 + min(2.0, euro / 10000.0))
    return base


def _why_it_matters(f: dict[str, Any]) -> str:
    imp = f.get("estimatedImpact") or {}
    expl = str(imp.get("explanation") or "").strip()
    if expl:
        return expl
    return str(f.get("observation") or "")[:200]


def _priority_label(rank: int) -> str:
    return {1: "🔴 Prioridad 1", 2: "🟠 Prioridad 2", 3: "🟢 Prioridad 3"}.get(rank, f"Prioridad {rank}")


def build_priorities(findings: list[dict[str, Any]] | None, *, top: int = 3) -> list[dict[str, Any]]:
    """Top-N prioridades desde los findings ACTIVOS del motor.

    Cada prioridad lleva: id estable (finding id), por qué importa, evidencia,
    qué haría VANOVA (acción recomendada), impacto (€ o «no cuantificable»),
    confianza y score — todo derivado del finding, nada inventado.
    """
    findings = [f for f in (findings or []) if isinstance(f, dict)]
    active = [
        f for f in findings
        if str(f.get("status") or "") not in ("resolved", "archived")
    ]
    ranked = sorted(active, key=score_finding, reverse=True)

    out: list[dict[str, Any]] = []
    for i, f in enumerate(ranked[:top]):
        euro = _impact_euro(f)
        out.append({
            "id": f"priority:{f.get('id') or f.get('signature') or i}",
            "findingId": f.get("id"),
            "findingSignature": f.get("signature"),
            "findingType": f.get("type") or f.get("finding_type") or "",
            "type": _priority_type(f),
            "category": f.get("category") or "problem",
            "severity": f.get("severity") or "",
            "confidence": f.get("confidence") or "",
            "label": _priority_label(i + 1),
            "title": str(f.get("title") or "Hallazgo detectado"),
            "whyItMatters": _why_it_matters(f),
            "evidence": list(f.get("evidence") or [])[:5],
            "recommendedAction": str(f.get("recommendedAction") or ""),
            "impactEuro": euro,
            "impactKind": _impact_kind(f),
            "entity": f.get("entity") or "",
            "score": round(score_finding(f), 3),
            "rank": i + 1,
        })
    return out


def persist(priorities: list[dict[str, Any]], *, data: dict[str, Any] | None = None) -> None:
    """Guarda las prioridades en el config (store inyectable para tests)."""
    if data is not None:
        data[PRIORITIES_KEY] = priorities
        return
    from . import config_store

    config_store.save({PRIORITIES_KEY: priorities})


def compute_and_persist(findings: list[dict[str, Any]] | None = None, *,
                        data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Calcula, persiste y devuelve las prioridades del estado actual."""
    if findings is None:
        from . import detection_engine

        res = detection_engine.run_detection(data, persist=False)
        findings = (res or {}).get("findings") or []
    priorities = build_priorities(findings)
    persist(priorities, data=data)
    return priorities
