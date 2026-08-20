"""Security regression tests for local runtime API (Phase 2)."""
from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import config_store, install_secrets, port_utils, runtime_security
from desktop.runtime.api_server import Handler, RuntimeHTTPServer, start_server


def _header(headers: dict, name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def _request(port: int, method: str, path: str, body: dict | None = None, headers: dict | None = None):
    data = None
    req_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers=req_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            return resp.status, dict(resp.headers), payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return exc.code, dict(exc.headers), payload


class RuntimeSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.secrets_file = base / "config" / "install_secrets.json"
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
        self.secrets_patcher = patch.object(install_secrets, "SECRETS_FILE", self.secrets_file)
        self.secrets_patcher.start()
        # CRITICAL: also isolate config_store. Mutation tests such as
        # /api/setup/reset call config_store.reset_setup(), which otherwise
        # writes to the user's REAL maios.json and resets their setup state.
        self.config_file = base / "config" / "maios.json"
        self.config_patcher = patch.object(config_store, "CONFIG_FILE", self.config_file)
        self.config_patcher.start()
        self.flag_patcher = patch.object(config_store, "SETUP_FLAG", base / ".setup_complete")
        self.flag_patcher.start()
        self.secrets = install_secrets.ensure_install_secrets()
        self.token = self.secrets["runtimeToken"]

        self.server = RuntimeHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.secrets_patcher.stop()
        self.config_patcher.stop()
        self.flag_patcher.stop()
        self.tmp.cleanup()

    def auth_headers(self, token: str | None = None):
        return {"Authorization": f"Bearer {token or self.token}"}

    def test_read_health_without_auth(self):
        status, _, payload = _request(self.port, "GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload.get("service"), "vanova-desktop-runtime")

    def test_sensitive_get_requires_auth(self):
        """P2-1 (auditoría comercial): los GET de datos empresariales exigen
        token de instalación — sin token → 401, token inválido → 401, token
        válido → 200. VANOVA 3.0 amplía la lista a TODO endpoint con datos de
        negocio (clientes, data-health, insights, audit, tareas, agente…).

        Determinismo: /api/command-center monta el snapshot de agentes, que
        sondea runtime/cloud/Hermes con timeouts de red (~2s cada uno cuando
        están caídos; en esta máquina los puertos fijos hacen SYN-drop). Eso
        supera el timeout HTTP de 5s de este test y lo hace dependiente del
        entorno. Parcheamos los tres probes: este test valida AUTH, no la
        latencia de descubrimiento de servicios."""
        from desktop.runtime import agent_architect, hermes_service, process_manager

        fast_status = {"cloud": {"running": False, "url": "http://127.0.0.1:8000"},
                       "connector": {"running": False, "authenticated": False,
                                     "registered": False, "cloudAvailable": False}}
        with patch.object(agent_architect, "_runtime_available", return_value=False), \
             patch.object(process_manager, "status", return_value=fast_status), \
             patch.object(hermes_service, "status",
                          return_value={"installed": False, "running": False,
                                        "path": "", "url": "http://127.0.0.1:8642",
                                        "healthy": False, "warmed": False,
                                        "latencyMs": None, "checkedAt": None,
                                        "launchMode": "standalone",
                                        "hermesConfigPath": "", "ollamaRunning": None,
                                        "activeModel": "", "activeProvider": ""}):
            self._run_sensitive_path_checks()

    def _run_sensitive_path_checks(self):
        for path in (
            "/api/products",
            "/api/sales",
            "/api/business/findings",
            "/api/files",
            "/api/company/profile",
            "/api/finance/overview",
            "/api/customers",
            "/api/data-health",
            "/api/command-center",
            "/api/insights",
            "/api/important",
            "/api/approvals",
            "/api/audit",
            "/api/insight-actions",
            "/api/backups/status",
            "/api/products/coverage",
            "/api/products/reconciliation",
            "/api/costs/status",
            "/api/costs/preview",
            "/api/sources",
            "/api/finance/reconcile",
            "/api/dashboard/local",
            "/api/tasks",
        ):
            with self.subTest(path=path):
                status, _, _ = _request(self.port, "GET", path)
                self.assertEqual(status, 401, f"{path} sin token debe ser 401")
                status, _, _ = _request(
                    self.port, "GET", path,
                    headers={"Authorization": "Bearer not-a-real-token"},
                )
                self.assertEqual(status, 401, f"{path} con token inválido debe ser 401")
                status, _, payload = _request(self.port, "GET", path, headers=self.auth_headers())
                self.assertEqual(status, 200, f"{path} con token válido debe ser 200")
                self.assertNotIn("error", payload)

    def test_sensitive_get_prefixes_require_auth(self):
        """VANOVA 3.0: los prefijos de datos de negocio (agente, tareas,
        conversaciones Hermes) y la config de integración también exigen token."""
        for path in (
            "/api/agent/data/get_sales",
            "/api/tasks/abc-123",
            "/api/hermes/requests/req-1",
            "/api/hermes/conversations/c1/messages",
            "/api/integrations/shopify/config",
        ):
            with self.subTest(path=path):
                status, _, _ = _request(self.port, "GET", path)
                self.assertEqual(status, 401, f"{path} sin token debe ser 401")

    def test_bootstrap_get_stays_open(self):
        """P2-1: los endpoints de bootstrap (health/setup/version) siguen
        abiertos para las sondas del launcher sin token."""
        for path in ("/api/health", "/api/setup/status", "/api/version"):
            with self.subTest(path=path):
                status, _, _ = _request(self.port, "GET", path)
                self.assertEqual(status, 200, f"{path} debe seguir abierto")

    def test_unauthorized_mutation_rejected(self):
        status, _, payload = _request(self.port, "POST", "/api/tasks/run", {"agentId": "agent-1", "type": "manual"})
        self.assertEqual(status, 401)
        self.assertEqual(payload.get("error"), "Unauthorized")

    def test_invalid_token_rejected(self):
        status, _, payload = _request(
            self.port,
            "POST",
            "/api/setup/reset",
            {},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        self.assertEqual(status, 401)
        self.assertEqual(payload.get("error"), "Unauthorized")

    def test_valid_token_accepts_mutation(self):
        status, _, payload = _request(
            self.port,
            "POST",
            "/api/setup/reset",
            {},
            headers=self.auth_headers(),
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("ok"))

    def test_grace_period_token_after_rotation(self):
        old_token = self.token
        install_secrets.rotateRuntimeCredentials()
        status, _, payload = _request(
            self.port,
            "POST",
            "/api/ui/dismiss-architecture",
            {},
            headers=self.auth_headers(old_token),
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("ok"))

    def test_path_traversal_rejected_on_files_add(self):
        status, _, payload = _request(
            self.port,
            "POST",
            "/api/files/add",
            {"name": "evil.txt", "path": "../../etc/passwd"},
            headers=self.auth_headers(),
        )
        self.assertEqual(status, 400)
        self.assertIn("Ruta no permitida", payload.get("error", ""))

    def test_path_traversal_rejected_on_files_remove(self):
        status, _, payload = _request(
            self.port,
            "POST",
            "/api/files/remove",
            {"path": "..\\..\\Windows\\System32"},
            headers=self.auth_headers(),
        )
        self.assertEqual(status, 400)
        self.assertIn("Ruta no permitida", payload.get("error", ""))

    def test_cors_allowlist_local_dashboard(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/health", headers={"Origin": "http://127.0.0.1:8000", "Accept": "application/json"})
        resp = conn.getresponse()
        resp.read()
        allow = _header(dict(resp.headers), "Access-Control-Allow-Origin")
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertEqual(allow, "http://127.0.0.1:8000")
        self.assertNotEqual(allow, "*")

    def test_cors_blocks_unknown_origin(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/health", headers={"Origin": "https://evil.example.com", "Accept": "application/json"})
        resp = conn.getresponse()
        resp.read()
        allow = _header(dict(resp.headers), "Access-Control-Allow-Origin")
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertIsNone(allow)

    def test_recovery_rejects_unknown_component(self):
        status, _, payload = _request(
            self.port,
            "POST",
            "/api/recovery",
            {"component": "rm -rf /"},
            headers=self.auth_headers(),
        )
        self.assertEqual(status, 400)
        self.assertIn("component", payload.get("error", "").lower())


    def test_factory_reset_endpoint_reachable(self):
        """Regresión 3.0.2: /api/setup/factory-reset estaba fuera del whitelist
        de mutación → 404 y la UI «fingía» reset sin hacer nada. Sin
        confirmación el endpoint debe responder 200 con ok=False (requiere
        confirmación) — prueba que la ruta resuelve y exige auth."""
        status, _, payload = _request(
            self.port, "POST", "/api/setup/factory-reset", body={}, headers=self.auth_headers()
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload.get("ok"))
        self.assertIn("Confirmación", payload.get("error", ""))

    def test_factory_reset_endpoint_requires_auth(self):
        status, _, _ = _request(self.port, "POST", "/api/setup/factory-reset", body={"confirmed": True})
        self.assertEqual(status, 401)

    def test_factory_reset_endpoint_calls_backend_with_confirmation(self):
        from desktop.runtime import data_governance

        captured = {}

        def fake_reset(*, confirmed=False):
            captured["confirmed"] = confirmed
            return {"ok": True, "setupComplete": False, "backupPath": "/tmp/bk"}

        with patch.object(data_governance, "factory_reset", side_effect=fake_reset):
            status, _, payload = _request(
                self.port, "POST", "/api/setup/factory-reset",
                body={"confirmed": True}, headers=self.auth_headers(),
            )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("ok"))
        self.assertFalse(payload.get("setupComplete"))
        self.assertTrue(captured.get("confirmed"))

    def test_frontend_mutation_endpoints_all_registered(self):
        """Auditoría automática: todo endpoint POST que llama el frontend al
        RUNTIME (dashboard.html con fetch(runtime…) y data-services.js con
        runtimeApi) debe estar registrado en el whitelist de mutación. Sin
        esto, un endpoint «existe» en el código pero responde 404 en
        producción (le pasó a /api/setup/factory-reset y a
        /api/recommendations/status). Los endpoints de la nube (api() →
        puerto 8000) no aplican aquí."""
        import re

        dashboard = (ROOT / "web" / "dashboard.html").read_text(encoding="utf-8")
        services = (ROOT / "web" / "data-services.js").read_text(encoding="utf-8")
        # GETs de polling verificados en do_GET (no son mutaciones)
        known_get_polls = {"/api/scan/status"}
        called: set[str] = set()
        for pat in (
            r"fetch\(runtime\s*\+\s*'([^']+)'",
            r"fetch\(runtime\+'([^']+)'",
            r"fetch\(\s*'([^']*?/api/[^']+)'",
        ):
            for match in re.findall(pat, dashboard):
                p = match.split("?")[0].strip()
                if p.startswith("/api") and "/" in p:
                    called.add(p)
        # runtimeApi("/api/...", { ... method: "POST" ... }) en data-services.js
        for match in re.finditer(
            r'runtimeApi\s*\(\s*"(/api/[^"]+)"\s*,\s*\{[^}]*method\s*:\s*["\']POST["\']',
            services,
        ):
            called.add(match.group(1).split("?")[0])
        missing = sorted(
            p for p in called
            if p not in known_get_polls
            and not runtime_security.is_mutation_post_path(p)
            and not runtime_security.is_sensitive_read_path(p)
            and not p.startswith("/api/integrations/")
        )
        self.assertEqual(missing, [], f"Endpoints POST del frontend fuera del whitelist: {missing}")


class CommandCenterNoneConfigTests(unittest.TestCase):
    """VANOVA 3.0 (auditoría): /api/command-center con config de instalación
    nueva (lastScan=None, dashboardSnapshot=None) debe devolver un snapshot
    vacío 200 — nunca 500."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.config_file = base / "config" / "maios.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_patcher = patch.object(config_store, "CONFIG_FILE", self.config_file)
        self.config_patcher.start()
        self.flag_patcher = patch.object(config_store, "SETUP_FLAG", base / ".setup_complete")
        self.flag_patcher.start()
        self.secrets_file = base / "config" / "install_secrets.json"
        self.secrets_patcher = patch.object(install_secrets, "SECRETS_FILE", self.secrets_file)
        self.secrets_patcher.start()
        self.secrets = install_secrets.ensure_install_secrets()
        self.token = self.secrets["runtimeToken"]
        self.addCleanup(self.secrets_patcher.stop)
        self.addCleanup(self.flag_patcher.stop)
        self.addCleanup(self.config_patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_command_center_empty_config_returns_200(self):
        """Regresión: cfg["lastScan"] puede ser None en instalación nueva — el
        snapshot debe ser vacío, no un 500."""
        from desktop.runtime import command_center

        result = command_center.get_home_snapshot(force=True)
        self.assertIn("dataMode", result)
        self.assertIn("attention", result)
        self.assertIn("attentionCount", result)
        self.assertNotIn("error", result)


class RuntimeConflictTests(unittest.TestCase):
    """P2-2 (auditoría comercial): una segunda instalación/perfil NUNCA puede
    adjuntarse en silencio al runtime de otra empresa."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.config_file = base / "config" / "maios.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_patcher = patch.object(config_store, "CONFIG_FILE", self.config_file)
        self.config_patcher.start()
        self.addCleanup(self.config_patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _start(self, owner_config: str | None):
        """Simula que el puerto ya lo ocupa un runtime sano cuyo configPath es
        `owner_config` (o desconocido)."""
        with patch.object(port_utils, "ensure_runtime_port", return_value={"ok": True, "port": 8765, "action": "already_running"}), \
             patch.object(port_utils, "runtime_config_path", return_value=owner_config):
            return start_server(8765)

    def test_same_install_attaches(self):
        """Misma instalación (mismo configPath) → reutilizar el runtime es
        legítimo y se devuelve el server de adjunto."""
        server = self._start(str(self.config_file))
        from desktop.runtime.api_server import _ExistingRuntimeServer

        self.assertIsInstance(server, _ExistingRuntimeServer)
        server.shutdown()

    def test_foreign_install_refused(self):
        """Otra instalación/perfil (configPath diferente) → se lanza RuntimeError
        con mensaje claro y NUNCA se adjunta."""
        foreign = str(Path(self.tmp.name) / "other" / "config" / "maios.json")
        with self.assertRaises(RuntimeError) as ctx:
            self._start(foreign)
        msg = str(ctx.exception)
        self.assertIn("otra instalación", msg)
        self.assertIn("8765", msg)

    def test_unknown_owner_refused(self):
        """Runtime activo sin configPath reportado → fail-safe: rechazar el
        attach (nunca asumir que es nuestra instalación)."""
        with self.assertRaises(RuntimeError):
            self._start(None)



if __name__ == "__main__":
    unittest.main()
