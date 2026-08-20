"""Post-update data validation — VANOVA 2.0.26-beta.3.

After an update the app must NEVER wipe existing business data, but the user
needs to know the persisted data comes from a previous version and can be
re-imported/re-analysed with the current one.

This module tracks, in config_store, the app version that last wrote the
business dataset, exposes whether a review is due, and supports a safe
re-import that is idempotent (never duplicates) and reports what happened.

The user can dismiss the notice; it never reappears for the same version
unless explicitly re-armed from the UI.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import config_store
from .logger import get_logger

log = get_logger("maios.data_version", "data-version")

_KEY = "dataVersion"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_app_version() -> str:
    try:
        from .updater import current_version

        v = current_version()
        return v or "0.0.0"
    except Exception:  # noqa: BLE001
        return "0.0.0"


def get_record() -> dict[str, Any]:
    data = config_store.load()
    rec = data.get(_KEY)
    if not isinstance(rec, dict):
        rec = {}
    defaults = {
        "version": None,        # app version that last imported/organized data
        "importedAt": None,
        "source": None,         # e.g. "files", "shopify", "facturascript"
        "dismissedFor": None,   # version whose notice the user dismissed
        "rearmed": False,       # user re-ran validation from the UI
        "counts": {},
    }
    return {**defaults, **rec}


def has_business_data() -> bool:
    data = config_store.load()
    return bool(data.get("organizedProducts")) or bool(data.get("organizedSales")) or bool(
        data.get("organizedCustomers")
    )


def stamp_import(*, source: str, counts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record that the current dataset was written by this app version."""
    rec = get_record()
    rec["version"] = current_app_version()
    rec["importedAt"] = _now()
    rec["source"] = source or rec.get("source")
    rec["counts"] = counts or rec.get("counts") or {}
    # A fresh import revalidates the data: the notice is cleared for this version.
    rec["dismissedFor"] = None
    rec["rearmed"] = False
    config_store.save({_KEY: rec})
    log.info("Data version stamped: %s (%s)", rec["version"], source)
    return rec


def status() -> dict[str, Any]:
    """Whether a post-update review is due, in user-friendly terms."""
    rec = get_record()
    stored_version = rec.get("version")
    current = current_app_version()
    has_data = has_business_data()
    needs_review = bool(
        has_data
        and stored_version
        and current
        and stored_version != current
        and rec.get("dismissedFor") != stored_version
    )
    return {
        "hasData": has_data,
        "storedVersion": stored_version,
        "currentVersion": current,
        "needsReview": needs_review,
        "dismissed": rec.get("dismissedFor") == stored_version,
        "dismissedFor": rec.get("dismissedFor"),
        "importedAt": rec.get("importedAt"),
        "source": rec.get("source"),
        "counts": rec.get("counts") or {},
    }


def dismiss() -> dict[str, Any]:
    """User chose 'Ahora no': do not show the notice again for this version."""
    rec = get_record()
    rec["dismissedFor"] = rec.get("version")
    rec["rearmed"] = False
    config_store.save({_KEY: rec})
    return status()


def rearm() -> dict[str, Any]:
    """User re-ran validation from the UI: show the notice again if due."""
    rec = get_record()
    rec["dismissedFor"] = None
    rec["rearmed"] = True
    config_store.save({_KEY: rec})
    return status()
