"""Request correlation IDs and structured log context (Phase 27)."""
from __future__ import annotations

import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str | None] = ContextVar("maios_correlation_id", default=None)


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


def bind_correlation(correlation_id: str | None = None) -> str:
    cid = (correlation_id or "").strip() or new_correlation_id()
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def clear_correlation() -> None:
    _correlation_id.set(None)
