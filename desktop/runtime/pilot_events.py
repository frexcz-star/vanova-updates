"""Registro de eventos del piloto (SPEC 3 §5 / STRATI_AUDIT_IMPL_PILOTO §3.1).

Objetivo: medir el flujo "conexión OK → 1ª oportunidad € vista" del piloto real
para el Go/No-Go de <15 min. Registra eventos con timestamp en JSONL y expone la
métrica "tiempo hasta el €". Todo honesto: solo se registra lo que ocurre de
verdad (eventos emitidos por el runtime), nunca se inventa ni un timestamp ni
un €.

Eventos:
  - source.connected      : una fuente de ventas se conectó con éxito
  - opportunity.seen      : la Home mostró la 1ª oportunidad con € cuantificado
  - recommendation.marked : una recomendación se marcó como hecha/resuelta
  - measure.done          : se realizó una medición (outcome)

La métrica "tiempo hasta el €" = opportunity.seen.ts − source.connected.ts
(punto de conexión del piloto). Solo se computa si ambos eventos reales existen.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .paths import logs_dir

PILOT_EVENTS_FILE = logs_dir() / "pilot_events.jsonl"

# Orden lógico del flujo del piloto (para el cálculo de la métrica).
_CONNECTION_KEYS = ("source.connected", "connection.ok", "connect.ok")
_OPPORTUNITY_KEYS = ("opportunity.seen", "opportunity.first", "first.opportunity")
_MARKED_KEYS = ("milestone.marked", "recommendation.marked", "rec.marked")
_MEASURED_KEYS = ("opportunity.done", "measure.done", "rec.measured")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(event: str, **detail: Any) -> dict[str, Any]:
    """Registra un evento del piloto en el log JSONL (con timestamp UTC)."""
    entry: dict[str, Any] = {
        "ts": _now(),
        "event": event,
        "detail": detail,
    }
    try:
        PILOT_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with PILOT_EVENTS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return entry


def _load() -> list[dict[str, Any]]:
    if not PILOT_EVENTS_FILE.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in PILOT_EVENTS_FILE.read_text(encoding="utf-8").splitlines():
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                out.append(parsed)
        except json.JSONDecodeError:
            continue
    return out


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def metric_time_to_euro() -> dict[str, Any]:
    """Métrica honesta 'tiempo hasta el €' desde los eventos reales.

    Retorna:
      - seconds: segundos reales desde source.connected hasta la 1ª
        opportunity.seen (None si falta algún evento real).
      - connected_ts / opportunity_ts: los timestamps reales.
      - status: 'ok' | 'missing_events' (no se inventa).
    """
    events = _load()
    conn_ts: datetime | None = None
    opp_ts: datetime | None = None
    for ev in events:
        name = str(ev.get("event") or "")
        ts = _parse_ts(ev.get("ts"))
        if not ts:
            continue
        if any(k in name for k in _CONNECTION_KEYS) and conn_ts is None:
            conn_ts = ts
        if any(k in name for k in _OPPORTUNITY_KEYS) and opp_ts is None:
            opp_ts = ts

    if conn_ts is None or opp_ts is None:
        return {
            "status": "unavailable",
            "seconds": None,
            "source_connected_ts": conn_ts.isoformat() if conn_ts else None,
            "opportunity_seen_ts": opp_ts.isoformat() if opp_ts else None,
        }
    seconds = (opp_ts - conn_ts).total_seconds()
    return {
        "status": "ok",
        "seconds": round(seconds, 1),
        "source_connected_ts": conn_ts.isoformat(),
        "opportunity_seen_ts": opp_ts.isoformat(),
        "target_lt_15min": seconds <= 900,
    }


def summary() -> dict[str, Any]:
    """Resumen de eventos del piloto (todos reales, con recuento)."""
    events = _load()
    counts: dict[str, int] = {}
    for ev in events:
        counts[str(ev.get("event"))] = counts.get(str(ev.get("event")), 0) + 1
    metric = metric_time_to_euro()
    return {
        "events_count": len(events),
        "by_event": counts,
        "time_to_euro": metric,
        "log_path": str(PILOT_EVENTS_FILE),
    }
