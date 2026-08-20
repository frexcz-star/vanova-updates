"""Smart Installer — executes installation plan with human-readable progress."""
from __future__ import annotations

from typing import Any, Callable

from . import config_store, dependency_resolver, hermes_service, process_manager
from .logger import get_logger
from .startup_gate import validate_startup
from .system_analyzer import analyze

log = get_logger("maios.installer", "installer")

ProgressCallback = Callable[[str, str, int], None]

CRITICAL_STEPS = frozenset({"runtime", "cloud", "python", "dependencies", "database"})


def run_installation(progress: ProgressCallback | None = None) -> dict[str, Any]:
    errors: list[str] = []
    critical_errors: list[str] = []
    profile: dict[str, Any] = {}
    plan: dict[str, Any] = {}
    gate: dict[str, Any] = {}

    def report(step: str, status: str, pct: int):
        if progress:
            progress(step, status, pct)
        log.info("Install progress: %s — %s (%d%%)", step, status, pct)

    try:
        report("Analyzing your computer", "running", 5)
        profile = analyze()
        report("Analyzing your computer", "ok", 15)

        report("Preparing installation plan", "running", 20)
        plan = dependency_resolver.resolve(profile)
        config_store.save({"installationPlan": plan, "environmentProfile": profile})
        report("Preparing installation plan", "ok", 25)

        report("Preparing VANOVA runtime", "running", 30)
        try:
            process_manager._ensure_venv()
            report("Preparing VANOVA runtime", "ok", 45)
        except Exception as exc:
            msg = f"Runtime setup: {exc}"
            errors.append(msg)
            critical_errors.append(msg)
            report("Preparing VANOVA runtime", "failed", 45)

        report("Setting up services", "running", 50)
        try:
            svc = process_manager.start_all()
            if not svc.get("cloud"):
                msg = "Cloud failed to start"
                errors.append(msg)
                critical_errors.append(msg)
                report("Setting up services", "failed", 60)
            else:
                report("Setting up services", "ok", 60)
            errors.extend(svc.get("warnings", []))
        except Exception as exc:
            msg = f"Services: {exc}"
            errors.append(msg)
            critical_errors.append(msg)
            report("Setting up services", "failed", 60)

        report("Installing Hermes", "running", 65)
        try:
            hermes_result = hermes_service.install(skip_start=True)
            report("Installing Hermes", "ok" if hermes_result.get("ok") else "warning", 80)
            if not hermes_result.get("ok"):
                errors.append("Hermes install incomplete (optional)")
        except Exception as exc:
            errors.append(f"Hermes: {exc}")
            report("Installing Hermes", "warning", 80)

        report("Validating installation", "running", 85)
        gate = validate_startup(install_deps=False)
        for check in gate.get("checks", []):
            if check.get("status") == "critical":
                critical_errors.append(check.get("message") or check.get("id", "critical"))
        report("Validating installation", "ok" if not critical_errors else "failed", 95)
    except Exception as exc:
        log.error("Install failed: %s", exc)
        critical_errors.append(str(exc))
        errors.append(str(exc))
    finally:
        report("Validating installation", "ok", 100)

    if critical_errors:
        status = "failed"
        ok = False
        partial = False
    elif errors:
        status = "partial"
        ok = False
        partial = True
    else:
        status = gate.get("status", "success")
        ok = status == "success"
        partial = status == "partial"

    return {
        "ok": ok,
        "partial": partial,
        "status": status,
        "errors": errors,
        "criticalErrors": critical_errors,
        "profile": profile,
        "plan": plan,
        "gate": gate,
    }
