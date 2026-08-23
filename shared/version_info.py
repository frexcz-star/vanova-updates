"""Single source for VANOVA product version metadata."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# Cloud API semver — tracks VANOVA release line (not a separate product).
CLOUD_API_VERSION = "3.1.4"


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    if (here.parent / "version.json").is_file():
        return here.parent
    return here


@lru_cache(maxsize=1)
def read_version_file() -> dict[str, Any]:
    vf = _repo_root() / "version.json"
    if not vf.is_file():
        return {"version": "3.0.6", "productName": "VANOVA"}
    try:
        return json.loads(vf.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {"version": "3.0.6", "productName": "VANOVA"}


def current_version() -> str:
    return str(read_version_file().get("version") or "0.0.0")


def version_bundle() -> dict[str, str]:
    """Versions exposed to health/diagnostics/UI."""
    maios = current_version()
    return {
        "maios": maios,
        "cloud": CLOUD_API_VERSION,
        "runtime": maios,
        "connector": maios,
    }
