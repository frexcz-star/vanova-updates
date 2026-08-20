"""Desktop Runtime API — local HTTP server for Electron onboarding UI.

Endpoint classification (Phase 2):
  READ (GET, no Bearer required): health, status, tasks queue, files list, etc.
  MUTATION (POST, Bearer required): tasks/run, services, install, files/add, etc.

See ``runtime_security.READ_GET_PATHS`` and ``MUTATION_POST_PATHS``.
"""
from __future__ import annotations

import importlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import config_store, port_utils
from .runtime_security import (
    cors_allow_origin,
    is_mutation_post_path,
    is_sensitive_read_path,
    validate_agent_id,
    validate_insight_action,
    validate_integration_id,
    validate_mutation_auth,
    validate_recovery_component,
)
from .rate_limit import check_rate_limit
from .company_profile import CompanyProfile, load_profile, save_profile
from .logger import get_logger

log = get_logger("maios.api", "runtime-api")

_INTEGRATION_CONFIG_PREFIX = "/api/integrations/"
_INTEGRATION_CONFIG_SUFFIX = "/config"


def _parse_integration_config_path(path: str) -> str | None:
    if not path.startswith(_INTEGRATION_CONFIG_PREFIX) or not path.endswith(_INTEGRATION_CONFIG_SUFFIX):
        return None
    integration_id = path[len(_INTEGRATION_CONFIG_PREFIX): -len(_INTEGRATION_CONFIG_SUFFIX)].strip("/")
    return integration_id or None

_MODULE_CACHE: dict[str, Any] = {}


def _mod(name: str):
    """Load runtime submodules lazily so one broken import does not block the API."""
    if name not in _MODULE_CACHE:
        try:
            _MODULE_CACHE[name] = importlib.import_module(f".{name}", __package__)
        except Exception as exc:
            log.warning("Module %s unavailable: %s", name, exc)
            _MODULE_CACHE[name] = None
    return _MODULE_CACHE[name]


def _require(name: str):
    mod = _mod(name)
    if mod is None:
        raise RuntimeError(f"Module {name} is unavailable")
    return mod

PORT = 8765
_install_progress: dict[str, Any] = {
    "step": "",
    "status": "",
    "percent": 0,
    "done": False,
    "error": None,
}
_install_lock = threading.Lock()
_install_running = False


class RuntimeHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _cors_origin(self) -> str | None:
        return cors_allow_origin(self.headers.get("Origin"))

    def _apply_cors_headers(self) -> None:
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization, X-VANOVA-Correlation-Id")

    def _bind_request_context(self) -> str:
        from .observability import bind_correlation

        incoming = self.headers.get("X-VANOVA-Correlation-Id")
        return bind_correlation(incoming)

    def _clear_request_context(self) -> None:
        from .observability import clear_correlation

        clear_correlation()

    def _json(self, data: Any, status: int = 200):
        from .observability import get_correlation_id

        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        cid = get_correlation_id()
        if cid:
            self.send_header("X-VANOVA-Correlation-Id", cid)
        self._apply_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _require_mutation_auth(self) -> bool:
        if validate_mutation_auth(self.headers.get("Authorization")):
            return True
        log.warning("Unauthorized mutation %s %s", self.command, urlparse(self.path).path)
        self._json({"error": "Unauthorized"}, 401)
        return False

    def _check_rate_limit(self, category: str) -> bool:
        client = self.client_address[0] if self.client_address else "unknown"
        allowed, message = check_rate_limit(category, client)
        if allowed:
            return True
        log.warning("Rate limit %s for %s %s", category, self.command, urlparse(self.path).path)
        self._json({"error": message}, 429)
        return False

    def _scan_mode_clean(self, body: dict[str, Any]) -> bool:
        """True si el usuario eligió «Limpiar y volver a importar» (mode=clean)."""
        return str(body.get("mode") or "").strip().lower() in ("clean", "wipe", "reimport-clean")

    def _clean_then_scan(self) -> dict[str, Any]:
        """Limpia el estado empresarial (con backup) y arranca el escaneo.

        La limpieza exige confirmación explícita del usuario (la UI la envía
        como mode=clean tras el diálogo). Si algo falla, no se escanea nada y
        se devuelve el error sin tocar datos.
        """
        cleared = _require("data_governance").clear_business_data(confirmed=True)
        if not cleared.get("ok"):
            return {"ok": False, "error": cleared.get("error") or "No se pudo limpiar los datos."}
        scanner = _require("business_scanner")
        started = scanner.run_scan_async()
        return {"ok": True, "cleaned": True, "backupPath": cleared.get("backupPath"), "scan": started}

    def do_OPTIONS(self):
        self.send_response(204)
        self._apply_cors_headers()
        self.end_headers()

    def do_GET(self):
        self._bind_request_context()
        path = urlparse(self.path).path
        try:
            # P2-1 (auditoría comercial): los GET de DATOS EMPRESARIALES exigen
            # el token de instalación, igual que los POST de mutación. El
            # frontend ya adjunta el token (runtimeApi → getRuntimeAuthHeaders);
            # solo los endpoints de bootstrap (health/setup/version) quedan
            # abiertos para las sondas del launcher.
            if is_sensitive_read_path(path) and not validate_mutation_auth(self.headers.get("Authorization")):
                log.warning("Unauthorized read %s %s", self.command, path)
                return self._json({"error": "Unauthorized"}, 401)
            routes = {
                "/api/health": lambda: {"status": "ok", "service": "vanova-desktop-runtime"},
                "/api/setup/status": lambda: {
                    "complete": config_store.is_setup_complete(),
                    "configPath": str(config_store.CONFIG_FILE),
                },
                "/api/system/analyze": lambda: _require("system_analyzer").analyze(),
                "/api/system/plan": lambda: _require("dependency_resolver").resolve(
                    _require("system_analyzer").analyze()
                ),
                "/api/install/progress": lambda: dict(_install_progress),
                "/api/company/profile": lambda: load_profile().to_dict(),
                "/api/company/model": lambda: _require("company_model").load_stored(),
                "/api/agents/recommendations": lambda: _require("business_analyst").recommend(load_profile()),
                "/api/agents": lambda: _require("agent_architect").list_agents(),
                "/api/agents/catalog": lambda: _require("agent_architect").catalog(),
                "/api/agents/scheduler": lambda: _require("agent_scheduler").status(),
                "/api/hermes/status": lambda: _require("hermes_service").status(),
                "/api/hermes/chat-ready": lambda: _require("hermes_chat").chat_ready(),
                "/api/hermes/conversations": lambda: _require("hermes_chat").list_conversations(),
                "/api/hermes/config": lambda: _require("hermes_config").full_status(),
                "/api/hermes/providers": lambda: _require("ai_providers").get_hermes_provider_catalog(),
                "/api/ai/status": lambda: _require("ai_providers").get_provider_status(),
                "/api/health/all": lambda: _require("health_monitor").check_all(),
                "/api/health/ports": lambda: port_utils.check_ports(),
                "/api/system/verify": lambda: _verify_system(),
                "/api/tasks": lambda: _require("task_queue").get_queue_status(),
                "/api/updates/status": lambda: _require("updater").get_update_status(),
                "/api/updates/manifest": lambda: _local_manifest(),
                "/api/diagnostics": lambda: _require("diagnostics_service").run_diagnostics(),
                "/api/startup/status": lambda: _require("startup_gate").validate_startup(install_deps=False),
                "/api/integrations/lifecycle": lambda: {
                    "integrations": _require("integrations_lifecycle").list_lifecycles(),
                },
                "/api/backups/status": lambda: _require("backup_service").status(),
                "/api/version": lambda: {"version": _require("updater").current_version()},
                "/api/data/version": lambda: _require("data_version").status(),
                "/api/scan/status": lambda: _scanner_call("scan_status"),
                "/api/dashboard/local": lambda: _scanner_call("load_local_dashboard") or {"dataMode": "empty"},
                "/api/files": lambda: _require("file_inventory").list_imported_files(),
                "/api/products": lambda: _require("file_organizer").get_products(),
                "/api/sales": lambda: _require("file_organizer").get_sales(),
                "/api/customers": lambda: _require("file_organizer").get_customers(),
                "/api/organize/status": lambda: _require("file_organizer").organization_status(),
                "/api/shopify/sync/status": lambda: _require("shopify_sync").sync_status(),
                "/api/facturascript/status": lambda: _require("facturascripts_sync").sync_status(),
                "/api/finance/overview": lambda: _require("agent_data_tools").get_finance_overview(),
                "/api/finance/reconcile": lambda: _finance_reconcile(),
                "/api/business/findings": lambda: _findings_with_status(urlparse(self.path).query),
                "/api/products/reconciliation": lambda: _require("agent_data_tools").get_product_reconciliation(),
                "/api/products/reconciliation/export": lambda: _reconciliation_export(urlparse(self.path).query),
                "/api/products/coverage": lambda: _coverage(),
                "/api/sources": lambda: _sources(),
                "/api/costs/preview": lambda: _costs_preview(),
                "/api/costs/status": lambda: _require("product_identity").cost_coverage(
                    _require("file_organizer").get_sales(),
                    _require("file_organizer").get_products(),
                ),
                "/api/gmail/skill/status": lambda: _require("gmail_skill_bridge").gmail_skill_status(),
                "/api/hermes/activity": lambda: _require("hermes_activity").current(),
                "/api/hermes/operational-context": lambda: _require("hermes_chat").operational_context(),
                "/api/ui/prefs": lambda: {
                    "architectureDismissed": config_store.is_architecture_dismissed(),
                    "uiPrefs": config_store.get_ui_prefs(),
                },
                "/api/insight-actions": lambda: _require("insight_actions").load_all(),
                "/api/data-health": lambda: _require("data_governance").data_health(),
                "/api/insights": lambda: _require("insight_store").list_insights(),
                "/api/recommendations": lambda: _require("recommendation_store").list_recommendations(),
                "/api/important": lambda: {"items": _require("important_store").list_important()},
                "/api/integrations/providers": lambda: {"providers": _provider_manifest()},
                "/api/integrations/test": lambda: {"ok": False, "error": "Usa POST con la configuración"},
                "/api/files/candidates": lambda: _require("file_inventory").list_candidates(),
                "/api/approvals": lambda: _approvals_with_tasks(),
                "/api/audit": lambda: {"entries": _require("audit_log").recent(50)},
                "/api/command-center": lambda: _require("command_center").get_home_snapshot(),
                "/api/autonomy": lambda: {
                    "current": _require("autonomy_config").describe(),
                    "levels": _require("autonomy_config").list_levels(),
                },
                "/api/auth/local-session": lambda: _local_owner_session(self.client_address[0]),
            }
            if path in routes:
                return self._json(routes[path]())
            if path.startswith("/api/hermes/requests/"):
                req_id = path.rsplit("/", 1)[-1]
                row = _require("hermes_chat").get_request(req_id)
                if not row:
                    return self._json({"error": "Petición no encontrada"}, 404)
                return self._json(row)
            if path.startswith("/api/tasks/"):
                parts = path[len("/api/tasks/"):].strip("/").split("/")
                task_id = parts[0]
                task = _require("task_store").get_task(task_id)
                if not task:
                    return self._json({"error": "Tarea no encontrada"}, 404)
                if len(parts) > 1 and parts[1] == "events":
                    events = _require("task_store").get_task_events(task_id)
                    return self._json({"task": task, "events": events})
                return self._json({"task": task})
            if path.startswith("/api/agent/data/"):
                tool = path[len("/api/agent/data/"):].strip("/").split("/")[0]
                if tool == "tools":
                    from . import agent_data_tools

                    return self._json({
                        "tools": agent_data_tools.tool_manifest(),
                        "availability": agent_data_tools.availability(),
                    })
                from . import agent_data_tools

                params = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
                return self._json(agent_data_tools.call_tool(tool, params))
            if path.startswith("/api/hermes/conversations/") and path.endswith("/messages"):
                conv_id = path[len("/api/hermes/conversations/") : -len("/messages")].strip("/")
                return self._json(_require("hermes_chat").get_messages(conv_id))
            integration_id = _parse_integration_config_path(path)
            if integration_id:
                return self._json(_require("integrations_store").get_config(integration_id))
        except RuntimeError as exc:
            return self._json({"error": str(exc)}, 503)
        except Exception as exc:
            log.error("GET %s failed: %s", path, exc)
            return self._json({"error": str(exc)}, 500)
        finally:
            self._clear_request_context()
        self._json({"error": "Not found"}, 404)

    def _handle_local_login(self) -> None:
        """Manual password login resolved by the local runtime.

        The dashboard is served by the runtime (127.0.0.1:8765), so the
        frontend's login form posts to /api/auth/login on THIS origin — not the
        Cloud. This validates the submitted credentials against the local
        cloud.env owner credentials and returns the same JWT shape the Cloud
        would.
        """
        length = int(self.headers.get("Content-Length", 0))
        try:
            raw = self.rfile.read(length) if length else b""
            ctype = self.headers.get("Content-Type", "")
            if "application/x-www-form-urlencoded" in ctype:
                from urllib.parse import parse_qs
                body = {k: v[0] for k, v in parse_qs(raw.decode("utf-8")).items()}
            else:
                body = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._json({"error": "Cuerpo inválido"}, 400)
        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        pm = _require("process_manager")
        cloud_env = {}
        try:
            from .paths import config_dir
            cloud_env = pm._load_env_file(config_dir() / "cloud.env") if hasattr(pm, "_load_env_file") else {}
        except Exception:
            cloud_env = {}
        expected_user = str(cloud_env.get("MAIOS_DEMO_USER") or "ceo")
        expected_pass = str(cloud_env.get("MAIOS_DEMO_PASSWORD") or "")
        if not expected_pass:
            return self._json({"error": "Login local no configurado"}, 503)
        if username != expected_user or password != expected_pass:
            return self._json({"error": "Credenciales incorrectas"}, 401)
        session = _local_owner_session(self.client_address[0] if self.client_address else "")
        if not session.get("ok") or not session.get("access_token"):
            return self._json({"error": session.get("error") or "Servicio de acceso no disponible"}, 503)
        return self._json({
            "access_token": session["access_token"],
            "refresh_token": session.get("refresh_token", ""),
            "role": session.get("role", "owner"),
            "token_type": "bearer",
            "expires_in": 43200,
        })

    def do_POST(self):
        self._bind_request_context()
        path = urlparse(self.path).path
        # Local login: the dashboard is served by the runtime, so /api/auth/login
        # must resolve here (validating against cloud.env owner credentials) and
        # may be called without a bearer token.
        if path == "/api/auth/login":
            return self._handle_local_login()
        if not is_mutation_post_path(path):
            return self._json({"error": "Not found"}, 404)
        if not self._require_mutation_auth():
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except UnicodeDecodeError:
            return self._json({"error": "Cuerpo no UTF-8 válido"}, 400)
        except json.JSONDecodeError:
            return self._json({"error": "JSON inválido"}, 400)
        if not isinstance(body, dict):
            body = {}

        try:
            if path == "/api/company/profile":
                profile = CompanyProfile.from_dict(body)
                save_profile(profile)
                return self._json({"ok": True, "profile": profile.to_dict()})

            if path == "/api/ai/configure":
                ai = _require("ai_providers")
                result = ai.save_provider_config(
                    body.get("providerId", "openrouter"),
                    body.get("apiKey", ""),
                    body.get("model", ""),
                    body.get("roles"),
                )
                return self._json({"ok": True, "provider": result})

            if path == "/api/ai/test":
                ai = _require("ai_providers")
                return self._json(ai.test_connection(body.get("providerId", ""), body.get("apiKey", "")))

            if path == "/api/hermes/provider/select":
                ai = _require("ai_providers")
                return self._json(
                    ai.select_hermes_provider(
                        body.get("providerId", "ollama-launch"),
                        body.get("model", ""),
                    )
                )

            if path == "/api/agents/create":
                agents = _require("agent_architect").create_agents(body.get("agents", []))
                return self._json({"ok": True, "agents": agents})

            if path == "/api/agents/add":
                arch = _require("agent_architect")
                defs = body.get("agents") or []
                if body.get("agentIds"):
                    cat = {a["id"]: a for a in arch.catalog()}
                    defs = defs + [cat[i] for i in body["agentIds"] if i in cat]
                if not defs:
                    return self._json({"error": "No se especificaron agentes"}, 400)
                added = arch.add_agents(defs)
                return self._json({"ok": True, "added": added, "agents": arch.list_agents()})

            if path == "/api/agents/run":
                agent_id = body.get("agentId", "")
                if not agent_id:
                    return self._json({"error": "agentId requerido"}, 400)
                result = _require("agent_architect").run_agent_now(agent_id)
                if not result.get("ok"):
                    return self._json(result, 404 if result.get("error") == "Agente no encontrado" else 400)
                return self._json(result)

            if path == "/api/install/run":
                return self._json(_start_install_background())

            if path == "/api/setup/complete":
                config_store.mark_setup_complete()
                svc = _require("process_manager").start_all()
                scanner = _mod("business_scanner")
                scan = scanner.run_scan_async() if scanner else {"ok": False, "message": "Scanner unavailable"}
                organizer = _mod("file_organizer")
                if organizer:
                    threading.Thread(
                        target=lambda: organizer.organize_files(trigger_hermes=True),
                        daemon=True,
                    ).start()
                return self._json({"ok": True, "services": svc, "scan": scan})

            if path == "/api/setup/scan":
                scanner = _require("business_scanner")
                if self._scan_mode_clean(body):
                    return self._json(self._clean_then_scan())
                return self._json(scanner.run_scan_async())

            if path == "/api/scan/folders":
                folders = body.get("folders") if isinstance(body.get("folders"), list) else None
                scanner = _require("business_scanner")
                if folders is None:
                    return self._json({"ok": True, "folders": scanner.scan_dirs()})
                cleaned = [str(f).strip() for f in folders if str(f or "").strip()]
                config_store.save({"scanFolders": cleaned})
                if self._scan_mode_clean(body):
                    return self._json(self._clean_then_scan())
                started = scanner.run_scan_async()
                return self._json({"ok": True, "folders": cleaned, "scan": started})

            if path == "/api/setup/reset":
                config_store.reset_setup()
                return self._json({"ok": True, "complete": False})

            if path == "/api/data/integrity":
                # FASE 14 — auditoría de integridad reutilizable (manual/debug).
                # READ-ONLY salvo persist del informe en dataGovernance.
                return self._json(_require("data_governance").validate_data_integrity(persist=True))

            if path == "/api/setup/factory-reset":
                # FASE 14 — restablecimiento EXPLÍCITO con backup previo. Exige
                # confirmación; nunca es consecuencia automática de un update.
                confirmed = bool(body.get("confirmed")) or bool(body.get("confirm"))
                return self._json(_require("data_governance").factory_reset(confirmed=confirmed))

            if path == "/api/ui/dismiss-architecture":
                config_store.dismiss_architecture()
                return self._json({"ok": True, "architectureDismissed": True})

            if path == "/api/data/version":
                return self._json(_require("data_version").status())

            if path == "/api/data/review/dismiss":
                return self._json(_require("data_version").dismiss())

            if path == "/api/data/review/rearm":
                return self._json(_require("data_version").rearm())

            if path == "/api/data/reimport":
                # Safe re-import: scan + organize using the same idempotent
                # pipeline as setup — never wipes, never duplicates. Con
                # mode=clean primero limpia el estado empresarial (con backup)
                # para reconstruirlo desde los archivos encontrados.
                if self._scan_mode_clean(body):
                    cleaned = self._clean_then_scan()
                    if not cleaned.get("ok"):
                        return self._json(cleaned)
                    scanner = _mod("business_scanner")
                    scan = cleaned.get("scan") or (scanner.run_scan_async() if scanner else None)
                else:
                    scanner = _mod("business_scanner")
                    scan = scanner.run_scan_async() if scanner else {"ok": False, "message": "Scanner unavailable"}
                organizer = _mod("file_organizer")
                if organizer:
                    threading.Thread(
                        target=lambda: organizer.organize_files(trigger_hermes=True),
                        daemon=True,
                    ).start()
                return self._json({"ok": True, "scan": scan, "started": True})

            if path == "/api/ui/prefs":
                prefs = body.get("uiPrefs") if isinstance(body.get("uiPrefs"), dict) else body
                saved = config_store.save_ui_prefs(prefs)
                return self._json({"ok": True, "uiPrefs": saved})

            if path == "/api/services/start":
                svc = _require("process_manager").start_all()
                return self._json({"ok": svc.get("cloud", False), **svc})

            if path == "/api/repair/run":
                return self._json(_require("repair_service").run_repair())

            if path == "/api/hermes/install":
                return self._json(_require("hermes_service").install())

            if path == "/api/hermes/restart":
                ok = _require("hermes_service").restart()
                return self._json({"ok": ok})

            if path == "/api/hermes/ask":
                if not self._check_rate_limit("hermes"):
                    return
                chat = _require("hermes_chat")
                return self._json(
                    chat.ask(body.get("message", ""), body.get("conversation_id", ""))
                )

            if path == "/api/hermes/warm":
                chat = _require("hermes_chat")
                return self._json(chat.warm_chat())

            if path == "/api/tasks/run":
                if not self._check_rate_limit("tasks"):
                    return
                agent_err = validate_agent_id(body.get("agentId", ""))
                if agent_err:
                    return self._json({"error": agent_err}, 400)
                payload = {
                    k: v
                    for k, v in body.items()
                    if k not in ("agentId", "type") and v is not None
                }
                task = _require("task_queue").enqueue(
                    body.get("agentId", ""),
                    body.get("type", "manual"),
                    payload or None,
                )
                return self._json(task)

            if path == "/api/tasks/create":
                if not self._check_rate_limit("tasks"):
                    return
                agent_id = str(body.get("agentId") or "")
                agent_err = validate_agent_id(agent_id)
                if agent_err:
                    return self._json({"error": agent_err}, 400)
                mode = str(body.get("mode") or "now")
                if mode not in ("now", "once", "recurring"):
                    return self._json({"error": "Modo inválido (now|once|recurring)"}, 400)
                result = _require("agent_scheduler").schedule_task(
                    agent_id,
                    mode=mode,
                    message=str(body.get("message") or ""),
                    due=body.get("due"),
                    schedule_spec=str(body.get("schedule") or ""),
                )
                if not result.get("ok"):
                    return self._json(result, 400)
                _require("audit_log").record(
                    "runtime", "task_delegated", {"agentId": agent_id, "mode": mode}
                )
                return self._json(result)

            if path == "/api/tasks/schedule/delete":
                result = _require("agent_scheduler").delete_schedule(
                    str(body.get("scheduleId") or body.get("id") or "")
                )
                if not result.get("ok"):
                    return self._json(result, 404)
                return self._json(result)

            if path == "/api/tasks/retry":
                task_id = str(body.get("taskId") or body.get("id") or "")
                if not task_id:
                    return self._json({"error": "taskId requerido"}, 400)
                result = _require("task_queue").retry_task(task_id)
                if not result:
                    return self._json({"error": "Tarea no encontrada"}, 404)
                return self._json(result)

            if path == "/api/autonomy":
                level = str(body.get("level") or body.get("autonomyLevel") or "")
                result = _require("autonomy_config").set_level(level)
                if not result.get("ok"):
                    return self._json(result, 400)
                _require("audit_log").record("runtime", "autonomy_changed", {"level": result.get("level")})
                return self._json(result)

            if path == "/api/approvals/decide":
                approval_id = str(body.get("approvalId") or body.get("id") or "")
                decision = str(body.get("decision") or body.get("status") or "")
                if not approval_id:
                    return self._json({"error": "approvalId requerido"}, 400)
                result = _require("approval_store").decide(approval_id, decision)
                if not result.get("ok"):
                    return self._json(result, 400)
                approval = result.get("approval") or {}
                if approval.get("status") == "approved" and approval.get("taskId"):
                    # The owner explicitly approved this action: the task must run
                    # without re-requesting approval (approval loop fix).
                    resumed = _require("task_queue").resume_task(approval["taskId"], approved=True)
                    result["task"] = resumed
                _require("audit_log").record("runtime", "approval_decided", {
                    "approvalId": approval_id,
                    "decision": decision,
                })
                return self._json(result)

            if path == "/api/recovery":
                comp_err = validate_recovery_component(body.get("component", ""))
                if comp_err:
                    return self._json({"error": comp_err}, 400)
                result = _require("health_monitor").attempt_recovery(body.get("component", "").strip().lower())
                return self._json(result)

            updater = _mod("updater")
            if path == "/api/updates/check":
                force = body.get("force", True)
                return self._json(updater.check_for_updates(force=force) if updater else {"error": "Updater unavailable"})

            if path == "/api/updates/download":
                return self._json(updater.download_update() if updater else {"error": "Updater unavailable"})

            if path == "/api/updates/install":
                return self._json(updater.install_update() if updater else {"error": "Updater unavailable"})

            if path == "/api/updates/cancel":
                return self._json(updater.cancel_update() if updater else {"error": "Updater unavailable"})

            if path == "/api/updates/recovery":
                return self._json(updater.startup_recovery() if updater else {"error": "Updater unavailable"})

            if path == "/api/updates/postpone":
                return self._json(
                    updater.postpone_update(
                        version=str(body.get("version") or ""),
                        hours=body.get("hours"),
                    )
                    if updater
                    else {"error": "Updater unavailable"}
                )

            if path == "/api/notifications/send":
                title = str(body.get("title") or "VANOVA")
                msg_body = str(body.get("body") or "")
                if not msg_body:
                    return self._json({"error": "body requerido"}, 400)
                # Forward to Electron for Windows notification
                return self._json({"ok": True, "title": title, "body": msg_body})

            if path == "/api/files/candidates/decide":
                result = _require("file_inventory").decide_candidate(
                    str(body.get("path") or ""),
                    bool(body.get("approve")),
                )
                if not result.get("ok") and result.get("error"):
                    return self._json(result, 400)
                return self._json(result)

            if path == "/api/files/add":
                result = _require("file_inventory").add_imported_file(body)
                if not result.get("ok") and result.get("error"):
                    return self._json(result, 400)
                return self._json(result)

            if path == "/api/files/remove":
                result = _require("file_inventory").remove_imported_file(body.get("path", ""))
                if not result.get("ok") and result.get("error"):
                    return self._json(result, 400)
                return self._json(result)

            if path == "/api/products/add":
                return self._json(_require("file_organizer").add_product(body))

            if path == "/api/products/match":
                # FASE 11 (P5): mapping manual verificado de identidad. Es una
                # RELACIÓN de identidad, no una copia de datos: nunca modifica
                # el SKU de la fuente ni el producto canónico. FASE 13 (P5): la
                # clave es genérica (sourceSku) — sirve para cualquier fuente.
                pi = _require("product_identity")
                result = pi.add_mapping(
                    source_sku=str(body.get("sourceSku") or body.get("shopifySku") or ""),
                    source=str(body.get("source") or "manual"),
                    variant_id=str(body.get("variantId") or body.get("sourceVariantId") or ""),
                    barcode=str(body.get("barcode") or ""),
                    canonical_product_id=str(body.get("canonicalProductId") or ""),
                    match_method=str(body.get("matchMethod") or "manual"),
                    confidence=body.get("confidence", 1.0),
                )
                _require("audit_log").record(
                    "runtime", "product_mapping_added",
                    {"sourceSku": str(body.get("sourceSku") or body.get("shopifySku") or "")[:80], "ok": bool(result.get("ok"))},
                )
                if not result.get("ok"):
                    return self._json(result, 400)
                return self._json(result)

            if path == "/api/products/match/remove":
                pi = _require("product_identity")
                result = pi.remove_mapping(
                    str(body.get("sourceSku") or ""),
                    shopify_sku=str(body.get("shopifySku") or ""),
                )
                if not result.get("ok"):
                    return self._json(result, 404)
                return self._json(result)

            if path == "/api/products/ignore":
                # FASE 12 (P2): ignorar un SKU de venta (nunca vincula; revisable).
                result = _require("product_identity").ignore_sku(
                    str(body.get("sourceSku") or body.get("shopifySku") or "")
                )
                if not result.get("ok"):
                    return self._json(result, 400)
                return self._json(result)

            if path == "/api/products/ignore/remove":
                result = _require("product_identity").unignore_sku(
                    str(body.get("sourceSku") or body.get("shopifySku") or "")
                )
                if not result.get("ok"):
                    return self._json(result, 404)
                return self._json(result)

            if path == "/api/shopify/identity-recovery":
                # FASE 12 (P3): recupera variant id + barcode de Shopify y los
                # persiste en el catálogo. Idempotente y no destructivo.
                result = _require("shopify_sync").recover_variant_identity()
                if not result.get("ok"):
                    return self._json(result, 400)
                return self._json(result)

            if path == "/api/costs/import":
                # FASE 12 (P6): importador SEGURO de costes reales.
                # preview: true → solo plan (nunca escribe).
                # preview: false → BACKUP → CONFIRM → IMPORT → INTEGRITY.
                ci = _require("cost_importer")
                rows = body.get("rows") or []
                if body.get("preview"):
                    return self._json(ci.preview(rows))
                backup_service = _require("backup_service")
                backup_service.run_backup()  # BACKUP antes de cualquier escritura
                result = ci.apply(rows, cost_source=str(body.get("costSource") or "supplier"))
                if not result.get("ok"):
                    return self._json(result, 400)
                _require("audit_log").record(
                    "runtime", "costs_imported",
                    {"applied": result.get("applied"), "counts": result.get("counts") or {}},
                )
                # PRODUCT LEAP — cerrar el ciclo: tras aplicar costes se
                # re-analiza, se sincronizan insights/prioridades y se re-miden
                # las recomendaciones realizadas/resueltas (la de costes
                # desaparece si el coste ya existe y el resultado se clasifica).
                try:
                    from . import detection_engine, insight_store, prioritization, recommendation_store

                    det = detection_engine.run_detection()
                    findings = (det or {}).get("findings") or []
                    insight_store.sync_from_findings(findings, active_signatures=(det or {}).get("freshSignatures"))
                    prioritization.persist(prioritization.build_priorities(findings))
                    for p in prioritization.build_priorities(findings, top=5):
                        fnd = next((x for x in findings if x.get("id") == p.get("findingId")), None)
                        if fnd:
                            recommendation_store.record_finding(fnd)
                    recommendation_store.sync_resolutions(findings, active_signatures=(det or {}).get("freshSignatures"))
                    recommendation_store.measure_all()
                except Exception:  # noqa: BLE001 — el cierre del ciclo nunca rompe el import
                    pass
                return self._json(result)

            if path == "/api/organize/run":
                organizer = _require("file_organizer")
                return self._json(organizer.organize_files(body.get("files")))

            if path == "/api/shopify/sync":
                return self._json(_require("shopify_sync").sync_now())

            if path == "/api/shopify/backfill":
                # FASE 9: recupera line_items de pedidos guardados sin líneas.
                return self._json(_require("shopify_sync").backfill_line_items())

            if path == "/api/facturascript/sync":
                # FASE 4: deep FacturaScripts sync (invoices, treasury, partners).
                return self._json(_require("facturascripts_sync").sync_now())

            if path == "/api/facturascript/backfill":
                # FASE 9: re-intenta recursos fallidos de la última sync de FS
                # (incremental, idempotente — la sync ya protege datos parciales).
                return self._json(_require("facturascripts_sync").sync_now())

            if path == "/api/integrity":
                # FASE 3: run the model integrity checks on demand.
                return self._json(_require("business_model").integrity_report())

            if path == "/api/recommendations/status":
                # PRODUCT LEAP — ciclo de vida de recomendaciones desde la UI:
                # open / in_progress / done / not_done / resolved. Al marcar
                # done/resolved se re-mide el resultado automáticamente.
                rec = _require("recommendation_store")
                rec_id = str(body.get("id") or "")
                status = str(body.get("status") or "")
                if not rec_id or status not in rec.VALID_STATUSES:
                    return self._json({"ok": False, "error": "id o estado inválido"}, 400)
                updated = rec.set_status(rec_id, status)
                if updated is None:
                    return self._json({"ok": False, "error": "recomendación no encontrada"}, 404)
                return self._json({"ok": True, "recommendation": updated})

            if path == "/api/actions/prepare":
                # PRODUCT LEAP — Action Center: acciones PREPARADAS (solo
                # lectura + audit). Nunca modifica sistemas externos.
                kind = str(body.get("kind") or "")
                return self._json(_require("action_center").prepare(kind))

            if path == "/api/business/analyze":
                # FASE 8: run the deterministic detection engine on the canonical
                # model, then bridge the active findings into user insights
                # (dedup por firma + lifecycle) and real priorities (score
                # económico). El usuario nunca tiene que preguntar: VANOVA
                # analiza y surfacea lo que encuentra.
                result = _require("detection_engine").run_detection()
                try:
                    from . import insight_store, prioritization, recommendation_store

                    findings = (result or {}).get("findings") or []
                    insight_store.sync_from_findings(findings, active_signatures=(result or {}).get("freshSignatures"))
                    prioritization.persist(prioritization.build_priorities(findings))
                    # FASE 8 — memoria de recomendaciones: registrar los hallazgos
                    # con prioridad real (dedup por firma; nunca spam).
                    for f in prioritization.build_priorities(findings, top=5):
                        fnd = next((x for x in findings if x.get("id") == f.get("findingId")), None)
                        if fnd:
                            recommendation_store.record_finding(fnd)
                    # Cierre del ciclo: resoluciones + re-medición automática.
                    recommendation_store.sync_resolutions(findings, active_signatures=(result or {}).get("freshSignatures"))
                    recommendation_store.measure_all()
                except Exception:  # noqa: BLE001 — los insights nunca rompen el análisis
                    pass
                return self._json(result)

            if path == "/api/business/findings/status":
                f_id = str(body.get("id") or "")
                new_status = str(body.get("status") or "")
                if not f_id:
                    return self._json({"ok": False, "error": "id del hallazgo requerido"}, 400)
                return self._json(_require("detection_engine").update_finding_status(f_id, new_status))

            if path == "/api/backups/run":
                return self._json(
                    _require("backup_service").run_backup(reason=str(body.get("reason") or "manual"))
                )

            if path == "/api/backups/restore":
                result = _require("backup_service").restore_pre_update(
                    str(body.get("id") or body.get("backupId") or "")
                )
                return self._json(result, 200 if result.get("ok") else 400)

            if path == "/api/integrations/disconnect":
                iid = str(body.get("integrationId") or body.get("integration") or "")
                return self._json(_require("integrations_store").disconnect(iid))

            if path == "/api/integrations/test":
                iid = str(body.get("integrationId") or body.get("integration") or "")
                config = body.get("config") if isinstance(body.get("config"), dict) else {}
                mode = str(body.get("mode") or "web")
                from . import integration_providers

                return self._json(integration_providers.test_connection(iid, config, mode=mode))

            if path == "/api/integrations/hermes-prompt":
                iid = str(body.get("integrationId") or body.get("integration") or "")
                config = body.get("config") if isinstance(body.get("config"), dict) else {}
                mode = str(body.get("mode") or "web")
                from . import integration_providers

                return self._json({"prompt": integration_providers.to_hermes_prompt(iid, config, mode=mode)})

            if path == "/api/important/mark":
                result = _require("important_store").mark_important(
                    kind=str(body.get("kind") or "item"),
                    ref_id=str(body.get("refId") or body.get("id") or ""),
                    title=str(body.get("title") or ""),
                    body=str(body.get("body") or ""),
                    agent_id=str(body.get("agentId") or ""),
                    meta=body.get("meta") if isinstance(body.get("meta"), dict) else None,
                )
                if not result.get("ok") and result.get("error"):
                    return self._json(result, 400)
                return self._json(result)

            if path == "/api/important/unmark":
                result = _require("important_store").unmark(
                    kind=str(body.get("kind") or "item"),
                    ref_id=str(body.get("refId") or body.get("id") or ""),
                )
                if not result.get("ok") and result.get("error"):
                    return self._json(result, 400)
                return self._json(result)

            if path == "/api/insight-actions":
                action_err = validate_insight_action(body.get("action", ""))
                if action_err:
                    return self._json({"error": action_err}, 400)
                return self._json(
                    _require("insight_actions").set_action(
                        body.get("insight_id", ""),
                        body.get("action", ""),
                    )
                )

            integration_id = _parse_integration_config_path(path)
            if integration_id:
                id_err = validate_integration_id(integration_id)
                if id_err:
                    return self._json({"error": id_err}, 400)
                return self._json(_require("integrations_store").save_config(integration_id, body))
        except RuntimeError as exc:
            return self._json({"error": str(exc)}, 503)
        except Exception as exc:
            log.error("POST %s failed: %s", path, exc)
            return self._json({"error": str(exc)}, 500)
        finally:
            self._clear_request_context()

        self._json({"error": "Not found"}, 404)


def _approvals_with_tasks() -> list[dict[str, Any]]:
    """Pending approvals enriched with their task context (type + payload), so
    the UI can show the owner WHAT exactly they are approving."""
    from . import approval_store, task_store

    approvals = approval_store.list_approvals(status="pending")
    out: list[dict[str, Any]] = []
    for a in approvals:
        task = None
        if a.get("taskId"):
            try:
                task = task_store.get_task(a["taskId"])
            except Exception:
                task = None
        if task:
            a = dict(a)
            payload = task.get("payload") or {}
            counts = []
            for key in ("productFiles", "salesFiles", "otherFiles"):
                if key in payload:
                    counts.append(f"{key.replace('Files', '').lower()}: {payload[key]}")
            a["taskType"] = task.get("type") or ""
            a["taskPayload"] = ", ".join(counts)
            a["taskCreatedAt"] = task.get("createdAt") or ""
        out.append(a)
    return out


def _scanner_call(method: str):
    scanner = _mod("business_scanner")
    if scanner is None:
        return {"error": "Business scanner unavailable", "status": "unavailable"}
    fn = getattr(scanner, method, None)
    if not fn:
        raise RuntimeError(f"Scanner method {method} unavailable")
    return fn()


def _findings_with_status(query: str) -> dict[str, Any]:
    from . import detection_engine

    params = {k: v[0] for k, v in parse_qs(query).items()}
    return detection_engine.list_findings(status=str(params.get("status") or ""))


def _coverage() -> dict[str, Any]:
    """FASE 11 (P7/P8) — cobertura de coste e identidad sobre el negocio real."""
    from . import agent_data_tools

    cc = agent_data_tools.get_cost_coverage()
    ic = agent_data_tools.get_identity_coverage()
    rec = agent_data_tools.get_product_reconciliation()
    return {
        "ok": True,
        "cost": cc,
        "identity": ic,
        "reconciliation": rec.get("summary") or {},
        "basis": "datos canónicos (organizedProducts/organizedSales); ningún valor se estima",
    }


def _sources() -> dict[str, Any]:
    """FASE 13 (P3/P10) — «Fuentes de datos»: conectores + capabilities.
    El core y la UI nunca asumen Shopify; preguntan aquí qué fuentes existen,
    cuáles están conectadas y qué datos puede dar cada una."""
    from . import connector_base

    return {
        "ok": True,
        "sources": connector_base.source_summaries(),
        "aggregate": connector_base.aggregate_capabilities(),
        "basis": "capabilities declaradas por conector; conectado/desconectado real; nada se simula",
    }


def _reconciliation_export(query: str) -> dict[str, Any]:
    """FASE 12 (P4) — exportación de la reconciliación en CSV o JSON.
    Solo lectura: nunca modifica datos. Parámetros: format=csv|json."""
    from urllib.parse import parse_qs

    from . import agent_data_tools, product_identity

    fmt = (parse_qs(query).get("format") or ["json"])[0]
    rec = agent_data_tools.get_product_reconciliation()
    items = rec.get("items") or []
    if fmt == "csv":
        import csv
        import io

        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=[
                "sourceSku", "sourceVariantId", "title", "canonicalProductId",
                "suggestedProductId", "matchMethod", "confidence", "status", "reason",
            ],
        )
        writer.writeheader()
        for it in items:
            row = {}
            for k in (
                "sourceSku", "sourceVariantId", "title", "canonicalProductId",
                "suggestedProductId", "matchMethod", "confidence", "status", "reason",
            ):
                alias = {"sourceSku": "shopifySku", "sourceVariantId": "shopifyVariantId"}.get(k)
                row[k] = it.get(k) if it.get(k) is not None else it.get(alias) if alias else None
            writer.writerow(row)
        return {"ok": True, "format": "csv", "content": buf.getvalue(), "rows": len(items)}
    return {"ok": True, "format": "json", "items": items, "summary": rec.get("summary") or {}, "rows": len(items)}


def _costs_preview() -> dict[str, Any]:
    """FASE 12 (P6) — PREVIEW del importador de costes (nunca escribe).
    Los rows se pasan por query (?rows=...) para GET, o se puede usar el POST
    /api/costs/import con "preview": true."""
    from . import cost_importer, file_organizer

    return cost_importer.preview([], file_organizer.get_products())


def _finance_reconcile() -> dict[str, Any]:
    """Fresh financial reconciliation (P2): records discrepancies, never
    corrects data silently. Persists the report so the dashboard can show it."""
    from . import business_model, config_store

    report = business_model.financial_reconciliation()
    try:
        config_store.save({"financialReconciliation": report})
    except Exception:
        pass
    return report


def _start_install_background() -> dict[str, Any]:
    global _install_running
    with _install_lock:
        if _install_running:
            return {"ok": True, "started": False, "message": "Installation already in progress"}
        _install_running = True
        _install_progress.update({"step": "Starting", "status": "running", "percent": 1, "done": False, "error": None})

    def run_bg():
        global _install_running
        try:
            def progress(step, status, pct):
                _install_progress.update({
                    "step": step,
                    "status": status,
                    "percent": pct,
                    "done": pct >= 100,
                })

            result = _require("installer").run_installation(progress)
            _install_progress.update({"result": result, "done": True, "percent": 100, "status": "ok"})
        except Exception as exc:
            log.error("Background install failed: %s", exc)
            _install_progress.update({
                "error": str(exc),
                "done": True,
                "percent": 100,
                "status": "error",
                "step": "Setup completed with warnings",
            })
        finally:
            with _install_lock:
                _install_running = False

    threading.Thread(target=run_bg, daemon=True).start()
    return {"ok": True, "started": True}


def _provider_manifest() -> list[dict[str, Any]]:
    """List of connectable integrations (gmail, drive, facturascript…)."""
    try:
        from . import integration_providers

        return integration_providers.get_providers()
    except Exception as exc:
        log.error("integration_providers unavailable: %s", exc)
        return []


def _local_manifest() -> dict[str, Any]:
    """Serve release/latest.json from repo for local update testing."""
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / "release" / "latest.json"
    if not manifest_path.exists():
        return {"error": "No local manifest at release/latest.json"}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _local_owner_session(client_host: str | None) -> dict[str, Any]:
    """Localhost-only recovery session using cloud.env owner credentials."""
    host = (client_host or "").strip()
    if host not in ("127.0.0.1", "::1", "localhost"):
        return {"ok": False, "error": "forbidden"}
    return _require("process_manager").local_owner_session()


def _verify_system() -> dict[str, Any]:
    """End-to-end verification — quick checks for UI diagnostics."""
    health_mod = _mod("health_monitor")
    task_mod = _mod("task_queue")
    updater_mod = _mod("updater")
    health = health_mod.check_all() if health_mod else {"overall": "degraded", "components": {}}
    tasks = task_mod.get_queue_status() if task_mod else {}
    issues = []
    for key, comp in health.get("components", {}).items():
        if comp.get("status") not in ("ok",):
            issues.append({"component": key, "status": comp.get("status"), "label": comp.get("label", key)})
    version = updater_mod.current_version() if updater_mod else "?"
    return {
        "ok": health.get("overall") == "healthy",
        "overall": health.get("overall"),
        "health": health,
        "tasks": tasks,
        "issues": issues,
        "version": version,
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


class _ExistingRuntimeServer:
    """No-op server handle when another healthy runtime instance is already listening."""

    def serve_forever(self):
        threading.Event().wait()

    def shutdown(self):
        pass


def start_server(port: int = PORT) -> ThreadingHTTPServer:
    recovery = port_utils.ensure_runtime_port(port)
    if not recovery.get("ok"):
        msg = recovery.get("message", f"Port {port} unavailable")
        log.error("Runtime port recovery failed: %s", msg)
        raise RuntimeError(msg)
    action = recovery.get("action")
    if action == "already_running":
        # P2-2 (auditoría comercial): NUNCA adjuntarse en silencio a un runtime
        # de otra instalación/perfil (mezclaría los datos de dos empresas). Solo
        # se reutiliza el runtime si usa EXACTAMENTE nuestro config.
        from . import config_store as _cs

        if port_utils.runtime_matches_install(port, str(_cs.CONFIG_FILE)):
            log.info("Runtime already healthy on port %d — attaching to existing instance (same install)", port)
            return _ExistingRuntimeServer()  # type: ignore[return-value]
        owner = port_utils.runtime_config_path(port)
        msg = (
            f"Ya hay otra instalación de VANOVA ejecutándose en el puerto {port} con un perfil "
            "de datos diferente. Cierra la otra instancia antes de abrir esta "
            "(una instalación activa por máquina)."
        )
        log.error("Refusing to attach to foreign runtime (ours=%s, theirs=%s): %s", _cs.CONFIG_FILE, owner, msg)
        raise RuntimeError(msg)
    if action == "recovered":
        log.info("Recovered stale runtime on port %d", port)

    server = RuntimeHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("Desktop runtime API listening on http://127.0.0.1:%d", port)
    try:
        _mod("agent_scheduler")
        started = _require("agent_scheduler").start()
        if started:
            log.info("Agent scheduler started")
    except Exception as exc:
        log.warning("Agent scheduler unavailable: %s", exc)
    return server
