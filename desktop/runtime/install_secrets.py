"""Per-installation secrets — generated on first run under %LOCALAPPDATA%/VANOVA/config/."""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .logger import get_logger
from .paths import config_dir

log = get_logger("maios.secrets")

SECRETS_FILE = config_dir() / "install_secrets.json"
_SECRETS_VERSION = 1
_MAX_GRACE_TOKENS = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_secrets() -> dict[str, Any]:
    return {
        "version": _SECRETS_VERSION,
        "installationId": secrets.token_hex(16),
        "runtimeToken": secrets.token_urlsafe(48),
        "encryptionKeyFoundation": secrets.token_urlsafe(32),
        "deviceIdentity": secrets.token_urlsafe(32),
        "createdAt": _now(),
        "rotatedAt": None,
        "previousRuntimeTokens": [],
    }


def _write_atomic(data: dict[str, Any]) -> None:
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SECRETS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, SECRETS_FILE)
    _restrict_permissions(SECRETS_FILE)


def _restrict_permissions(path: Path) -> None:
    # %LOCALAPPDATA% already inherits an ACL limited to the signed-in user and
    # administrators. Replacing it can make this critical file unreadable when
    # the account name is resolved incorrectly, rotating identity/tokens and
    # breaking encrypted credentials. Keep the secure inherited ACL instead.
    return


def _is_valid(data: dict[str, Any]) -> bool:
    required = ("installationId", "runtimeToken", "encryptionKeyFoundation", "deviceIdentity")
    return all(str(data.get(key) or "").strip() for key in required)


def ensure_install_secrets() -> dict[str, Any]:
    """Generate unique per-installation secrets on first run."""
    if SECRETS_FILE.exists():
        try:
            data = json.loads(SECRETS_FILE.read_text(encoding="utf-8-sig"))
            if _is_valid(data):
                return data
        except (json.JSONDecodeError, OSError):
            log.warning("Invalid install_secrets file — recreating")

    data = _generate_secrets()
    _write_atomic(data)
    install_id = str(data.get("installationId", ""))
    log.info("Generated per-installation secrets (installationId=%s...)", install_id[:8])
    return data


def load_secrets() -> dict[str, Any]:
    return ensure_install_secrets()


def get_runtime_token() -> str:
    return str(load_secrets().get("runtimeToken") or "")


def get_installation_id() -> str:
    return str(load_secrets().get("installationId") or "")


def get_encryption_key_foundation() -> str:
    return str(load_secrets().get("encryptionKeyFoundation") or "")


def get_device_identity() -> str:
    return str(load_secrets().get("deviceIdentity") or "")


def validate_runtime_token(token: str) -> bool:
    """Accept current token or a grace-period previous token after rotation."""
    if not token:
        return False
    data = load_secrets()
    if token == data.get("runtimeToken"):
        return True
    return token in (data.get("previousRuntimeTokens") or [])


def rotateRuntimeCredentials(*, grace_period: bool = True) -> dict[str, Any]:
    """Rotate runtime token without breaking an existing install.

    Behavior:
    - Generates a new ``runtimeToken`` (``MAIOS_RUNTIME_TOKEN``).
    - Preserves ``installationId``, ``deviceIdentity``, and
      ``encryptionKeyFoundation`` so install identity stays stable.
    - When ``grace_period`` is True (default), retains the previous token in
      ``previousRuntimeTokens`` so in-flight clients can authenticate until
      they pick up the new token (Phase 2 will enforce Bearer auth).
    - Returns metadata only; raw tokens are never included.
    """
    data = load_secrets()
    old_token = str(data.get("runtimeToken") or "")
    new_token = secrets.token_urlsafe(48)

    previous: list[str] = list(data.get("previousRuntimeTokens") or [])
    if grace_period and old_token:
        previous = [old_token, *previous[: _MAX_GRACE_TOKENS]]

    data["runtimeToken"] = new_token
    data["previousRuntimeTokens"] = previous
    data["rotatedAt"] = _now()
    _write_atomic(data)

    install_id = str(data.get("installationId") or "")
    log.info("Runtime credentials rotated (installationId=%s...)", install_id[:8])
    return {
        "rotated": True,
        "rotatedAt": data["rotatedAt"],
        "installationId": install_id,
        "graceTokensRetained": len(previous),
    }
