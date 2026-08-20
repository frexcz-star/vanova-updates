"""Dependency Resolver — builds a minimal installation plan from environment profile."""
from __future__ import annotations

from typing import Any

from .paths import app_root
from .logger import get_logger

log = get_logger("maios.resolver", "dependency-resolver")


def resolve(profile: dict[str, Any]) -> dict[str, Any]:
    plan = {
        "required": [],
        "optional": [],
        "notRequired": [],
        "steps": [],
    }

    # VANOVA Runtime always required
    plan["required"].append({
        "id": "maios-runtime",
        "name": "VANOVA Runtime",
        "description": "Core application services",
        "status": "pending",
    })

    # Python — bundled (portable python-bundle ships with the installer) or
    # existing venv. The installer packages the standalone interpreter under
    # python-bundle/, NOT python/ — checking only python/ made the setup wizard
    # ask a fresh user to "create a Python environment" even though the bundled
    # runtime was already present (no Python on the machine needed).
    root = app_root()
    venv_exists = (root / ".venv" / "Scripts" / "python.exe").exists()
    bundled = (
        (root / "python" / "python.exe").exists()
        or (root / "python-bundle" / "python.exe").exists()
    )
    python_ok = profile.get("dependencies", {}).get("python", {}).get("ok", False)
    if venv_exists or bundled:
        plan["notRequired"].append({"id": "python", "name": "Python", "reason": "Already bundled or configured"})
    elif python_ok:
        plan["required"].append({
            "id": "python-venv",
            "name": "VANOVA Python Environment",
            "description": "Creates isolated Python environment for Cloud and Connector",
            "status": "pending",
        })
    else:
        plan["required"].append({
            "id": "python-bundled",
            "name": "VANOVA Python Runtime",
            "description": "Portable Python runtime for VANOVA services",
            "status": "pending",
        })

    # Hermes
    hermes_ok = profile.get("dependencies", {}).get("hermes", {}).get("ok", False)
    plan["required"].append({
        "id": "hermes",
        "name": "Hermes",
        "description": "Agent execution runtime",
        "status": "ok" if hermes_ok else "pending",
    })

    # Cloud + Connector
    plan["required"].append({
        "id": "maios-cloud",
        "name": "VANOVA Cloud",
        "description": "Local API and dashboard server",
        "status": "pending",
    })
    plan["required"].append({
        "id": "maios-connector",
        "name": "VANOVA Connector",
        "description": "Secure outbound bridge to Cloud",
        "status": "pending",
    })

    # Optional — Docker is not required for VANOVA V1
    docker_ok = profile.get("dependencies", {}).get("docker", {}).get("ok", True)
    if not docker_ok:
        plan["optional"].append({
            "id": "docker",
            "name": "Docker",
            "reason": "Optional — not required for VANOVA V1",
        })

    plan["notRequired"].append({"id": "git", "name": "Git", "reason": "Not required for end users"})
    plan["notRequired"].append({"id": "node", "name": "Node.js", "reason": "Bundled in desktop shell"})

    plan["steps"] = [
        {"id": "analyze", "label": "Analyzing your computer", "order": 1},
        {"id": "runtime", "label": "Preparing VANOVA runtime", "order": 2},
        {"id": "python", "label": "Setting up services", "order": 3},
        {"id": "hermes", "label": "Installing Hermes", "order": 4},
        {"id": "configure", "label": "Configuring VANOVA", "order": 5},
        {"id": "validate", "label": "Validating installation", "order": 6},
    ]

    log.info("Installation plan resolved — %d required items", len(plan["required"]))
    return plan
