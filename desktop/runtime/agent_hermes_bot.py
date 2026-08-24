"""FASE B — Sincronización de agente VANOVA → bot Hermes persistente.

Cada agente creado en VANOVA (Fase A) puede existir también como un **bot de
Hermes real**: un perfil (`~/.hermes/profiles/vanova-<slug>/`) con su SOUL.md
(personalidad), memoria propia y chat persistente. El bot es visible en el
Hermes desktop (pestaña Bots) y en CLI con `hermes -p <bot> chat`.

Coexistencia: la Fase A (task_queue → one-shot) sigue intacta. Este módulo
añade la capa persistente SIN romper nada: si Hermes no está disponible, el
agente VANOVA funciona igual (la sincronización a bot es un efecto secundario
opcional).

Honestidad: el SOUL.md y las memorias del bot incluyen la regla de VANOVA
(usa datos reales; nunca inventes € ni resultados sin métrica comparable).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import hermes_service
from .logger import get_logger

log = get_logger("maios.agents.bot", "agent-hermes-bot")

# Prefijo de perfil para los bots de agentes de VANOVA (namespaced).
BOT_PROFILE_PREFIX = "vanova-"

# Mapa rol → personalidad/responsabilidades del SOUL.md (en español).
_ROLE_SOUL: dict[str, dict[str, str]] = {
    "sales": {
        "titulo": "Agente de Ventas",
        "desc": "Analiza las ventas y oportunidades de crecimiento de tu negocio.",
    },
    "accounting": {
        "titulo": "Agente de Contabilidad",
        "desc": "Vigila facturas, tesorería y la salud financiera del negocio.",
    },
    "inventory": {
        "titulo": "Agente de Stock",
        "desc": "Monitoriza inventario, alerta de rotura de stock y sugiere reposiciones.",
    },
    "marketing": {
        "titulo": "Agente de Marketing",
        "desc": "Propone campañas y analiza el rendimiento de los canales de venta.",
    },
    "support": {
        "titulo": "Agente de Atención al Cliente",
        "desc": "Ayuda a responder y priorizar las consultas de los clientes.",
    },
    "ceo": {
        "titulo": "Copiloto de Dirección",
        "desc": "Resumen ejecutivo, KPIs y recomendaciones estratégicas.",
    },
    "general": {
        "titulo": "Agente General",
        "desc": "Asistente de análisis de negocio con los datos reales de VANOVA.",
    },
}

_HONESTY_RULE = (
    "Reglas de honestidad de VANOVA (obligatorias):\n"
    "- Usa SOLO datos reales del negocio (productos, ventas, clientes, facturas).\n"
    "- NUNCA inventes una cifra, un resultado o un importe en euros.\n"
    "- Si falta un dato (por ejemplo el coste de un producto), dilo con claridad\n"
    "  en lugar de suponerlo. UNKNOWN es distinto de cero.\n"
    "- Cuando reportes un resultado, apóyalo en métricas comparables reales."
)


def hermes_home() -> Path | None:
    """Directorio raíz de Hermes (donde viven los perfiles)."""
    base = os.getenv("HERMES_HOME")
    if base:
        return Path(base)
    if os.name == "nt":
        cand = Path(os.getenv("LOCALAPPDATA", "")) / "hermes"
        if cand.exists():
            return cand
    home = Path.home() / ".hermes"
    return home if home.exists() else None


def profiles_dir() -> Path | None:
    root = hermes_home()
    if root is None:
        return None
    p = root / "profiles"
    return p if p.is_dir() else None


def _hermes_cli() -> list[str] | None:
    try:
        from . import hermes_service

        path = hermes_service._find_hermes()  # noqa: SLF001
        if path:
            return [path]
    except Exception:  # noqa: BLE001
        pass
    exe = shutil.which("hermes")
    if exe:
        return [exe]
    # BUG-001 real (Nico): el CLI de Hermes vive en el venv de la instalación
    # (LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/hermes) que NO está en el
    # PATH. Si no está en el PATH, buscarlo en las rutas de la instalación local
    # para poder crear/verificar los perfiles (antes devolvía None y el perfil
    # de ventas nunca se creaba -> chat a Hermes fallaba con 'profile does not
    # exist').
    if os.name == "nt":
        local = Path(os.getenv("LOCALAPPDATA", "")) / "hermes"
        candidates = [
            local / "hermes-agent" / "venv" / "Scripts" / "hermes.exe",
            local / "hermes-agent" / "venv" / "Scripts" / "hermes",
            local / "venv" / "Scripts" / "hermes.exe",
        ]
        for c in candidates:
            if c.exists():
                return [str(c)]
    return None


def _profile_dir(slug: str) -> Path | None:
    base = profiles_dir()
    return (base / slug) if base else None


def _profile_region(slug: str) -> Path | None:
    return _profile_dir(slug)


def agent_slug(agent: dict[str, Any]) -> str:
    """Nombre de perfil Hermes para un agente VANOVA (namespaced)."""
    aid = str(agent.get("id") or "").strip()
    if aid:
        base = aid.replace("custom-", "")
    else:
        base = str(agent.get("name") or "agente")
    import re

    base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "agente"
    return f"{BOT_PROFILE_PREFIX}{base[:32]}"


def _build_soul(agent: dict[str, Any]) -> str:
    role = str(agent.get("role") or "").strip().lower()
    role_info = _ROLE_SOUL.get(role, _ROLE_SOUL["general"])
    name = str(agent.get("name") or role_info["titulo"] or "Agente")
    desc = str(agent.get("description") or role_info["desc"] or "")
    resp = agent.get("responsibilities") or []
    resp_txt = "\n".join(f"- {r}" for r in resp) or "- Analizar el negocio con datos reales."
    return (
        f"# {name}\n\n"
        f"Eres {name}, un agente de IA de VANOVA que ayuda al empresario a "
        f"entender y mejorar su negocio.\n\n"
        f"## Misión\n{desc or role_info['desc']}\n\n"
        f"## Responsabilidades\n{resp_txt}\n\n"
        f"## Datos\nLos datos reales del negocio se te pasan en cada ejecución "
        f"desde el sistema VANOVA (productos, ventas, clientes, facturas).\n\n"
        f"{_HONESTY_RULE}"
    )


def _write_soul(profile: Path, agent: dict[str, Any]) -> None:
    profile.mkdir(parents=True, exist_ok=True)
    soul = profile / "SOUL.md"
    soul.write_text(_build_soul(agent), encoding="utf-8")
    log.info("SOUL.md escrito en %s", soul)


def _write_initial_memory(profile: Path, agent: dict[str, Any]) -> None:
    mem = profile / "memories"
    mem.mkdir(parents=True, exist_ok=True)
    mem_file = mem / "MEMORY.md"
    if mem_file.exists():
        return  # no pisar memoria ya existente
    mem_file.write_text(
        f"# Memoria de {agent.get('name') or 'agente'}\n\n"
        f"Eres el agente de IA del negocio. Ayudas al empresario a "
        f"interpretar sus datos reales de VANOVA y a tomar decisiones.\n\n"
        f"{_HONESTY_RULE}\n",
        encoding="utf-8",
    )


def profile_exists(slug: str) -> bool:
    d = _profile_region(slug)
    return d is not None and d.is_dir()


def _profile_region(slug: str) -> Path | None:
    base = profiles_dir()
    return (base / slug) if base else None


def sync_agent_to_bot(agent: dict[str, Any]) -> dict[str, Any]:
    """Crea o actualiza el perfil Hermes del agente (idempotente).

    Si Hermes no está disponible o el directorio de perfiles no existe, devuelve
    un resultado honesto con ``ok=False`` sin romper el flujo VANOVA.
    """
    slug = agent_slug(agent)
    cli = _hermes_cli()
    if not cli:
        return {"ok": False, "error": "Hermes CLI no disponible", "profile": slug}
    profile_dir = _profile_region(slug)
    if profile_dir is None:
        return {"ok": False, "error": "Directorio de perfiles de Hermes no encontrado", "profile": slug}

    created = False
    if not profile_dir.exists():
        # Crear el perfil con `hermes profile create <slug> --no-alias`.
        try:
            proc = subprocess.run(
                cli + ["profile", "create", slug, "--no-alias"],
                capture_output=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            created = proc.returncode == 0
            if not created and (proc.stderr or proc.stdout):
                detail = (proc.stderr or proc.stdout).decode("utf-8", "replace").strip()
                log.warning("hermes profile create fallo: %s", detail[:400])
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo crear el perfil Hermes: %s", exc)

    # Escribir/actualizar SOUL.md y memoria inicial (idempotente).
    _write_soul(profile_dir, agent)
    _write_initial_memory(profile_dir, agent)

    return {
        "ok": True,
        "profile": slug,
        "created": created,
        "exists": profile_dir.is_dir(),
        "soul": (profile_dir / "SOUL.md").exists(),
    }


def remove_bot(slug: str) -> dict[str, Any]:
    """Elimina el perfil Hermes del agente (coherente al eliminar el agente)."""
    cli = _hermes_cli()
    if not cli:
        return {"ok": False, "error": "Hermes CLI no disponible"}
    try:
        proc = subprocess.run(
            cli + ["profile", "delete", slug, "-y"],
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return {"ok": proc.returncode == 0, "profile": slug}
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo borrar el perfil Hermes: %s", exc)
        return {"ok": False, "error": str(exc), "profile": slug}


# ---------------------------------------------------------------------------
# FASE B, PASO 3 — rutina cron persistente por agente ([bot:<name>]).
# ---------------------------------------------------------------------------

# Mapeo weekday (agente_scheduler) -> cron weekday (0=domingo en cron).
_WEEKDAY_CRON = {
    "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4,
    "friday": 5, "saturday": 6, "sunday": 0,
}


def schedule_to_cron(spec: str) -> str | None:
    """Traduce un schedule de VANOVA ('Daily 18:00' / 'Weekly Monday 09:00')
    al formato cron de Hermes ('0 18 * * *' / '0 9 * * 1'). Devuelve None si
    no se puede interpretar."""
    try:
        from . import agent_scheduler
        rule = agent_scheduler.parse_schedule(spec)
    except Exception:  # noqa: BLE001
        return None
    if not rule:
        return None
    minute = rule["minute"]
    hour = rule["hour"]
    if rule["freq"] == "daily":
        return f"{minute} {hour} * * *"
    if rule["freq"] == "weekly":
        wd = _WEEKDAY_CRON.get(agent_scheduler._WEEKDAYS.get(list(agent_scheduler._WEEKDAYS.keys())[rule["weekday"]], ""), None) if isinstance(rule.get("weekday"), int) else None
        # Resolver weekday por indice de _WEEKDAYS
        wd = None
        for name, idx in agent_scheduler._WEEKDAYS.items():
            if idx == rule["weekday"]:
                wd = _WEEKDAY_CRON.get(name)
                break
        if wd is None:
            return None
        return f"{minute} {hour} * * {wd}"
    return None


def sync_agent_routines(agent: dict[str, Any]) -> dict[str, Any]:
    """Crea/actualiza un cron job de Hermes por cada schedule del agente
    (namespaced `[bot:<name>]`). Coexiste con la Fase A (task_queue)."""
    slug = agent_slug(agent)
    cli = _hermes_cli()
    if not cli:
        return {"ok": False, "error": "Hermes CLI no disponible"}
    schedules = agent.get("schedules") or []
    if not schedules:
        return {"ok": True, "profile": slug, "routines": []}
    created = []
    for spec in schedules:
        cron_expr = schedule_to_cron(str(spec))
        if not cron_expr:
            continue
        name = f"[bot:{slug}] {spec}"
        prompt = _routine_prompt(agent)
        # Intentar borrar un cron previo del mismo nombre para no duplicar.
        try:
            subprocess.run(
                cli + ["cron", "remove", name, "-y"],
                capture_output=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            proc = subprocess.run(
                cli + ["cron", "create", cron_expr, prompt, "--name", name, "--deliver", "local"],
                capture_output=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            created.append({"schedule": str(spec), "cron": cron_expr, "ok": proc.returncode == 0})
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo crear cron para %s: %s", name, exc)
            created.append({"schedule": str(spec), "cron": cron_expr, "ok": False})
    return {"ok": True, "profile": slug, "routines": created}


def _routine_prompt(agent: dict[str, Any]) -> str:
    """Prompt de la rutina del agente (datos reales, honestidad)."""
    name = str(agent.get("name") or agent.get("id") or "agente")
    resp = agent.get("responsibilities") or []
    resp_txt = ", ".join(str(r) for r in resp) if resp else "analizar el negocio con datos reales"
    return (
        f"{name}, ejecuta tu rutina programada de análisis.\n"
        f"Responsabilidades: {resp_txt}.\n"
        f"Usa SOLO datos reales disponibles en VANOVA. NUNCA inventes cifras ni euros. "
        f"Si falta un dato, dilo con claridad. Resume acciones concretas."
    )
