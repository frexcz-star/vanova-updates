"""VANOVA Connector — bridge service on the owner's PC.

The Connector establishes an OUTBOUND, authenticated connection to VANOVA Cloud.
It NEVER opens a public port, never does port forwarding, and never exposes
Hermes (127.0.0.1) to the internet.

Flow:
    Owner PC
        VANOVA Connector
            secure outbound (HTTPS + device key + optional TLS)
                VANOVA Cloud
                    WebSocket realtime
                        Dashboard

Connector responsibilities:
- Register as a device in the workspace (device key)
- Heartbeat to Cloud (so Cloud knows it's online)
- Proxy dashboard requests to local Hermes Agent (127.0.0.1:8642)
- Forward Hermes activity/insights/decisions up to Cloud
- Reconnect automatically after network loss
"""
from __future__ import annotations

import os
import sys
import json
import time
import shutil
import hashlib
import asyncio
import logging
import socket
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent))
from shared.version_info import current_version  # single source of VANOVA version

load_dotenv(BASE_DIR / ".env", override=True)
# BUG-009 FIX: _user_connector_env y _legacy_connector_env eran la MISMA ruta
# (LOCALAPPDATA/VANOVA/config/connector.env), así que el elif era código muerto.
# Se unifica en una sola ruta de config del usuario.
_user_connector_env = Path(os.environ.get("LOCALAPPDATA", "")) / "VANOVA" / "config" / "connector.env"
if _user_connector_env.exists():
    load_dotenv(_user_connector_env, override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [VANOVA Connector] %(levelname)s %(message)s")
log = logging.getLogger("maios-connector")

CLOUD_URL = os.getenv("MAIOS_CLOUD_URL", "http://127.0.0.1:8000")  # local cloud in dev; public URL in prod
DEVICE_KEY = os.getenv("MAIOS_DEVICE_KEY", "")
WORKSPACE_ID = os.getenv("MAIOS_WORKSPACE_ID", "")
HERMES_URL = os.getenv("HERMES_URL", "http://127.0.0.1:8642")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "")
# Option A: Hermes via CLI. If HERMES_CLI is set, use that path; else find "hermes" in PATH.
HERMES_CLI = os.getenv("HERMES_CLI", "")
HEARTBEAT_SECONDS = int(os.getenv("MAIOS_HEARTBEAT_SECONDS", "30"))
# Insight generation runs on a long schedule, NEVER on every heartbeat.
INSIGHT_INTERVAL_SECONDS = int(os.getenv("MAIOS_INSIGHT_INTERVAL_SECONDS", "1800"))
# Full disk scan of Documents/Downloads/Desktop is expensive — throttle it to a
# long schedule instead of running on every 30s heartbeat (P3: polling excess).
SCAN_INTERVAL_SECONDS = int(os.getenv("MAIOS_SCAN_INTERVAL_SECONDS", "1800"))
RECONNECT_BASE_SECONDS = 2
RECONNECT_MAX_SECONDS = 60
AUTH = "VANOVA-AUTH-TOKEN"  # placeholder; real device key flow below


class Connector:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=20.0)
        self.device_id = None
        self.online = False

    # ------------------------------------------------------------------
    # Registration + auth
    # ------------------------------------------------------------------
    async def ensure_registered(self):
        """Register this connector as a device using the configured device key."""
        if not DEVICE_KEY:
            log.warning("MAIOS_DEVICE_KEY not set — connector cannot authenticate. Run onboarding to generate one.")
            return False
        if self.device_id:
            return True
        headers = {"Authorization": f"Device {DEVICE_KEY}"}
        try:
            r = await self.client.post(
                f"{CLOUD_URL}/api/connector/heartbeat", headers=headers, timeout=10
            )
            if r.status_code == 200:
                self.online = True
                return True
            # Not registered -> try registration (JWT, then localhost recovery)
            owner_token = self._owner_token()
            if owner_token:
                r = await self.client.post(
                    f"{CLOUD_URL}/api/devices/register",
                    headers={"Authorization": f"Bearer {owner_token}"},
                    json={"deviceKey": DEVICE_KEY, "name": socket.gethostname(), "os": "windows", "version": current_version()},
                )
                if r.status_code in (200, 201):
                    self.device_id = r.json().get("device_id")
                    self.online = True
                    log.info("Registered device %s", self.device_id)
                    return True
                log.warning("Device registration failed: %s", r.text[:200])
            r = await self.client.post(
                f"{CLOUD_URL}/api/devices/register-local",
                json={"deviceKey": DEVICE_KEY, "name": socket.gethostname(), "os": "windows", "version": current_version()},
            )
            if r.status_code in (200, 201):
                self.device_id = r.json().get("device_id")
                self.online = True
                log.info("Registered device via localhost recovery %s", self.device_id)
                return True
            if not owner_token:
                log.warning("Connector not registered — localhost recovery failed. Revisa connector.env.")
            return False
        except httpx.ConnectError as exc:
            log.warning("Cloud unreachable: %s", exc)
            return False

    def _owner_token(self) -> str:
        # In production the connector holds a service/owner token in its .env.
        # For local dev we use the same credential set.
        return os.getenv("MAIOS_OWNER_TOKEN", "")

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------
    async def heartbeat_loop(self):
        while True:
            try:
                if not DEVICE_KEY:
                    await asyncio.sleep(HEARTBEAT_SECONDS)
                    continue
                headers = {"Authorization": f"Device {DEVICE_KEY}"}
                r = await self.client.post(f"{CLOUD_URL}/api/connector/heartbeat", headers=headers, timeout=10)
                self.online = r.status_code == 200
                if not self.online:
                    log.warning("Heartbeat rejected (%s); attempting re-registration", r.status_code)
                    await self.ensure_registered()
            except httpx.ConnectError:
                self.online = False
                log.warning("Cloud unreachable during heartbeat")
            await asyncio.sleep(HEARTBEAT_SECONDS)

    # ------------------------------------------------------------------
    # Hermes integration — via CLI (Option A). No HTTP port exposed.
    #   Connector -> subprocess `hermes chat -q "<prompt>"` -> response
    # ------------------------------------------------------------------
    @staticmethod
    def _hermes_available() -> bool:
        return bool(HERMES_CLI) or shutil.which("hermes") is not None

    @staticmethod
    def _hermes_cli_path() -> list[str]:
        if HERMES_CLI:
            return [HERMES_CLI]
        exe = shutil.which("hermes")
        return [exe] if exe else ["hermes"]

    async def hermes_status(self) -> dict:
        """Check whether the Hermes CLI is available locally (no server needed)."""
        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(None, self._hermes_available)
        if not ok:
            return {"connected": False, "error": "Hermes CLI no encontrado en PATH"}
        return {"connected": True, "mode": "cli", "cli": "hermes"}

    async def hermes_query(self, message: str, provider: str = "ollama-launch", model: str = "", timeout: int = 120, session_id: str = "") -> dict:
        """Ask local Hermes via CLI. If session_id is given, resume that Hermes
        session so the conversation continues in the same thread. Returns a
        structured result — only the final answer + labels, never chain-of-thought."""
        if not self._hermes_available():
            return {"status": "error", "summary": "Hermes CLI no disponible", "agentsUsed": []}
        # Orchestration-aware framing so Hermes knows it can ACT (connect sources,
        # run tools, delegate to agents) when the user asks it to. Prefixed to the
        # message because `hermes chat` has no system-prompt flag.
        action_hint = (
            "[Sistema] Eres el orquestador de VANOVA. Si el usuario te pide CONECTAR "
            "una fuente, HACER algo en el dashboard, EJECUTAR una acción o DELEGAR una "
            "tarea a un agente, usa tus herramientas (terminal, archivos, etc.) para "
            "intentarlo y describe qué has hecho. Si no puedes, explica con honestidad "
            "qué se necesita. Ahora responde al mensaje del usuario.] "
        )
        full_message = action_hint + message
        cmd = self._hermes_cli_path() + ["chat", "-q", full_message, "--quiet"]
        if session_id:
            cmd += ["--resume", session_id]
        if model:
            cmd += ["-m", model]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return {"status": "error", "summary": "Hermes CLI excedió el tiempo de espera", "agentsUsed": []}
            if proc.returncode != 0:
                return {"status": "error", "summary": "Hermes CLI falló (exit %s)" % proc.returncode, "agentsUsed": []}
            out = stdout.decode("utf-8", "replace")
            err = stderr.decode("utf-8", "replace")
            summary = out.strip()
            if not summary:
                return {"status": "error", "summary": "Hermes devolvió respuesta vacía", "agentsUsed": []}
            # Extract the session id from the CLI output. It is printed to
            # stderr (e.g. "session_id: 20260811_132702_def699").
            new_session = session_id
            for line in (out + "\n" + err).splitlines():
                if line.strip().startswith("session_id:"):
                    new_session = line.split(":", 1)[1].strip()
                    break
            return {
                "status": "completed",
                "summary": summary,
                "session_id": new_session,
                "sourcesUsed": ["Hermes Agent (local)"],
                "agentsUsed": ["Hermes / CEO Copilot"],
                "dataUsed": [],
                "actionsTaken": [],
            }
        except FileNotFoundError:
            return {"status": "error", "summary": "Hermes CLI no encontrado", "agentsUsed": []}
        except Exception as exc:
            return {"status": "error", "summary": str(exc), "agentsUsed": []}

    async def hermes_insight(self) -> dict:
        """Generate one real business insight via Hermes CLI, for the dashboard."""
        # Fetch the configured company name so insights are on-brand for the workspace.
        company = "MOOVING PAPER"
        company_desc = "empresa de papelería y licencias"
        try:
            c = await self._get_company()
            if c and c.get("company"):
                company = c["company"]
                ck = (c.get("company_key") or "").lower()
                company_desc = "empresa de papelería y licencias" if ck != "blis" \
                    else "marca de papelería artesanal y arte"
        except Exception:
            pass
        prompt = (
            f"Actúa como el CEO Copilot de {company} ({company_desc}). "
            "Genera UN insight empresarial ejecutivo breve (máx 3 frases), con prioridad (high/medium/low), "
            "impacto estimado en euros y una recomendación accionable. "
            "Formato: TÍTULO | DESCRIPCIÓN | PRIORIDAD | IMPACTO | RECOMENDACIÓN. "
            "No inventes números de fuentes a las que no tengas acceso; usa tu conocimiento general de negocio."
        )
        res = await self.hermes_query(prompt, timeout=150)
        if res.get("status") != "completed":
            return None
        # P0-8: honest provenance. The insight is generated from the model's general
        # knowledge (no business data connected), so it is a HYPOTHESIS, never
        # presented as an OBSERVED fact from internal data.
        provenance = "HYPOTHESIS"
        note = "Esta es una hipótesis del modelo, no una observación de tus datos de negocio."
        return {
            "id": "hermes-" + hashlib.sha256(res["summary"].encode("utf-8")).hexdigest()[:16],
            "agent": "CEO Copilot",
            "type": "hypothesis",
            "provenance": provenance,
            "provenanceNote": note,
            "priority": "medium",
            "title": res["summary"][:90] + ("…" if len(res["summary"]) > 90 else ""),
            "description": res["summary"],
            "impact": "—",
            "confidence": "—",
            "recommendation": res["summary"],
            "status": "open",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }

    async def _get_company(self) -> dict:
        """Read the configured company name from the Cloud (device-authenticated)."""
        if not DEVICE_KEY:
            return {"company": "MOOVING PAPER", "company_key": "MOOVING"}
        try:
            r = await self.client.get(
                f"{CLOUD_URL}/api/connector/company",
                headers={"Authorization": f"Device {DEVICE_KEY}"}, timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {"company": "MOOVING PAPER", "company_key": "MOOVING"}

    # ------------------------------------------------------------------
    # Scan the owner's PC for real data files (Excel, CSV, PDF, docs)
    # ------------------------------------------------------------------
    DATA_EXTENSIONS = {".xlsx", ".xls", ".csv", ".pdf", ".docx", ".doc", ".txt", ".json"}
    SCAN_DIRS = [
        Path.home() / "Documents",
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path.home() / "OneDrive" if (Path.home() / "OneDrive").exists() else None,
    ]

    def _scan_files(self, max_files: int = 200) -> list[dict]:
        found = []
        seen = set()
        for d in self.SCAN_DIRS:
            if not d or not d.exists():
                continue
            try:
                for p in d.rglob("*"):
                    if len(found) >= max_files:
                        break
                    if p.is_file() and p.suffix.lower() in self.DATA_EXTENSIONS:
                        try:
                            key = str(p).lower()
                            if key in seen:
                                continue
                            seen.add(key)
                            found.append({
                                "path": str(p),
                                "name": p.name,
                                "ext": p.suffix.lower().lstrip("."),
                                "size": p.stat().st_size,
                                "modified": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
                            })
                        except OSError:
                            continue
            except (PermissionError, OSError):
                continue
        return found

    async def scan_and_push(self):
        """Scan the PC for data files and push the inventory to Cloud."""
        if not DEVICE_KEY:
            return
        files = self._scan_files()
        if not files:
            return
        headers = {"Authorization": f"Device {DEVICE_KEY}"}
        try:
            r = await self.client.post(
                f"{CLOUD_URL}/api/connector/files",
                json={"files": files, "count": len(files)},
                headers=headers, timeout=15,
            )
            if r.status_code == 200:
                log.info("Escaneo de archivos: %d archivos de datos encontrados", len(files))
        except httpx.ConnectError:
            log.warning("No se pudo enviar el escaneo de archivos (cloud offline)")

    # ------------------------------------------------------------------
    # Push snapshot to Cloud
    # ------------------------------------------------------------------
    async def push_dashboard(self, snapshot: dict):
        if not DEVICE_KEY:
            return
        headers = {"Authorization": f"Device {DEVICE_KEY}"}
        try:
            await self.client.post(f"{CLOUD_URL}/api/connector/push", json=snapshot, headers=headers, timeout=10)
        except httpx.ConnectError:
            log.warning("Could not push snapshot (cloud offline)")

    # ------------------------------------------------------------------
    # Process pending Hermes requests from the Cloud queue
    # ------------------------------------------------------------------
    async def process_pending_requests(self):
        if not DEVICE_KEY:
            return
        headers = {"Authorization": f"Device {DEVICE_KEY}"}
        try:
            r = await self.client.get(f"{CLOUD_URL}/api/connector/requests/pending", headers=headers, timeout=10)
            if r.status_code != 200:
                return
            pending = r.json()
        except httpx.ConnectError:
            return
        if not pending:
            return
        # Process ALL pending requests in order (keeps conversation session
        # coherent and prevents the queue from accumulating). Each request is
        # answered promptly rather than waiting for the next heartbeat cycle.
        for req in pending:
            req_id = req.get("id")
            message = req.get("message", "")
            conv_id = req.get("conversation_id", "")
            hermes_session = req.get("hermes_session_id") or ""
            log.info("Procesando petición Hermes %s (conv=%s, session=%s): %s",
                     req_id, conv_id, hermes_session or "nueva", message[:60])
            # Run against local Hermes CLI, resuming the session if one exists
            res = await self.hermes_query(message, timeout=120, session_id=hermes_session)
            payload = {"request_id": req_id}
            if res.get("status") == "completed":
                payload["result"] = res.get("summary", "")
                if res.get("session_id"):
                    payload["hermes_session_id"] = res["session_id"]
            else:
                payload["error"] = res.get("summary", "Hermes no disponible")
            try:
                await self.client.post(
                    f"{CLOUD_URL}/api/connector/requests/result",
                    json=payload, headers=headers, timeout=10,
                )
            except httpx.ConnectError:
                log.warning("No se pudo enviar resultado de %s (cloud offline)", req_id)

    async def _build_heartbeat_snapshot(self, hermes: dict) -> dict:
        """Build heartbeat snapshot — prefer stored scan data from runtime setup."""
        stored = None
        try:
            cfg_path = Path(os.getenv("LOCALAPPDATA", "")) / "VANOVA" / "maios.json"
            if cfg_path.exists():
                import json
                stored = json.loads(cfg_path.read_text(encoding="utf-8-sig")).get("dashboardSnapshot")
        except Exception:
            stored = None

        if stored and stored.get("dataMode") in ("real", "partial"):
            snapshot = dict(stored)
            snapshot["hermes"] = hermes
            snapshot["activity"] = [{
                "id": "connector-" + str(int(time.time())),
                "agent": "VANOVA Connector",
                "action": "Heartbeat — datos escaneados activos",
                "status": "running" if self.online else "failed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
            return snapshot

        snapshot = {
            "dataMode": "partial" if hermes["connected"] else "empty",
            "hermes": hermes,
            "activity": [{
                "id": "connector-" + str(int(time.time())),
                "agent": "VANOVA Connector",
                "action": "Heartbeat",
                "status": "running" if self.online else "failed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
            "priorities": [],
            "sources": [],
        }
        if hermes["connected"]:
            snapshot["sources"] = [
                {"id": "hermes", "name": "Hermes Agent", "status": "connected", "source": "local", "recordCount": 0, "dataMode": "partial"}
            ]
        return snapshot

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    async def run(self):
        log.info("VANOVA Connector starting (cloud=%s, hermes=%s)", CLOUD_URL, HERMES_URL)
        await self.ensure_registered()
        asyncio.create_task(self.heartbeat_loop())

        # Main loop: cheap heartbeat only. Insight generation and the full disk
        # scan are throttled to a long schedule (INSIGHT_INTERVAL / SCAN_INTERVAL)
        # and must NOT run on every heartbeat (P0-7 / P3 polling excess).
        last_insight = 0.0
        last_scan = 0.0
        while True:
            hermes = await self.hermes_status()
            snapshot = await self._build_heartbeat_snapshot(hermes)
            if hermes["connected"]:
                # User questions always have priority (answered promptly).
                await self.process_pending_requests()
                # Insight generation runs on a long schedule, not every heartbeat.
                now = time.time()
                if now - last_insight >= INSIGHT_INTERVAL_SECONDS:
                    last_insight = now
                    insight = await self.hermes_insight()
                    if insight:
                        snapshot["priorities"] = [insight]
                        # Also push the insight as a standalone business event so it
                        # is not lost when the next heartbeat replaces priorities.
                        await self._push_insight_event(insight)
            await self.push_dashboard(snapshot)
            # Scan the PC for real data files — throttled to a long schedule.
            now = time.time()
            if now - last_scan >= SCAN_INTERVAL_SECONDS:
                last_scan = now
                await self.scan_and_push()
            await asyncio.sleep(HEARTBEAT_SECONDS)

    async def _push_insight_event(self, insight: dict):
        """Persist an insight as a business event on the Cloud so it survives
        snapshot churn (P0-9: a heartbeat must not destroy it)."""
        if not DEVICE_KEY:
            return
        try:
            await self.client.post(
                f"{CLOUD_URL}/api/connector/insight-event",
                json=insight,
                headers={"Authorization": f"Device {DEVICE_KEY}"}, timeout=10,
            )
        except Exception:
            log.warning("No se pudo persistir el insight como evento")


async def amain():
    c = Connector()
    try:
        await c.run()
    except asyncio.CancelledError:
        pass
    finally:
        await c.client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        log.info("Connector stopped")
