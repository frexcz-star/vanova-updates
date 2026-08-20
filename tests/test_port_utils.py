"""Tests for port_utils.check_ports."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from desktop.runtime import port_utils


class PortUtilsTests(unittest.TestCase):
    @patch.object(port_utils, "probe_cloud", return_value=True)
    @patch.object(port_utils, "probe_runtime", return_value=True)
    @patch.object(port_utils, "is_port_in_use", return_value=True)
    def test_check_ports_both_ok(self, *_mocks):
        result = port_utils.check_ports()
        self.assertEqual(result["overall"], "ok")
        self.assertEqual(result["runtime"]["status"], "ok")
        self.assertEqual(result["cloud"]["status"], "ok")

    @patch.object(port_utils, "probe_cloud", return_value=False)
    @patch.object(port_utils, "probe_runtime", return_value=False)
    @patch.object(port_utils, "is_port_in_use", return_value=True)
    @patch.object(port_utils, "find_pids_on_port", return_value=[1234])
    @patch.object(port_utils, "kill_pid", return_value=True)
    @patch.object(port_utils, "process_name", return_value="python.exe")
    def test_ensure_port_recovers_zombie(self, *_mocks):
        with patch.object(port_utils, "is_port_in_use", side_effect=[True, True, False]):
            result = port_utils.ensure_port_available(
                8765,
                label="test",
                probe=lambda: False,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "recovered")

    @patch.object(port_utils, "probe_runtime", return_value=True)
    @patch.object(port_utils, "is_port_in_use", return_value=True)
    def test_ensure_port_reuses_healthy_runtime(self, *_mocks):
        result = port_utils.ensure_runtime_port()
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "already_running")

    @patch.object(port_utils, "probe_cloud", return_value=False)
    @patch.object(port_utils, "probe_runtime", return_value=False)
    @patch.object(port_utils, "is_port_in_use", return_value=True)
    @patch.object(port_utils, "find_pids_on_port", return_value=[1234])
    def test_check_ports_blocked(self, *_mocks):
        result = port_utils.check_ports()
        self.assertIn(result["overall"], ("degraded", "critical"))
        self.assertEqual(result["runtime"]["status"], "blocked")
        self.assertIn("8765", result["runtime"]["message"])
        self.assertEqual(result["runtime"]["pids"], [1234])

    @patch.object(port_utils, "probe_cloud", return_value=False)
    @patch.object(port_utils, "probe_runtime", return_value=False)
    @patch.object(port_utils, "is_port_in_use", return_value=False)
    def test_check_ports_offline(self, *_mocks):
        result = port_utils.check_ports()
        self.assertEqual(result["runtime"]["status"], "offline")
        self.assertIn("8765", result["runtime"]["message"])

    def test_foreign_process_never_killed(self):
        """VANOVA 3.0: un proceso ajeno que ocupa el puerto NUNCA se mata — se
        reporta recovery_failed con mensaje claro (antes se hacía taskkill /F)."""
        with patch.object(port_utils, "is_port_in_use", return_value=True), \
             patch.object(port_utils, "probe_runtime", return_value=False), \
             patch.object(port_utils, "find_pids_on_port", return_value=[99999]), \
             patch.object(port_utils, "process_name", return_value="notepad.exe") as pn, \
             patch.object(port_utils, "kill_pid") as kill:
            result = port_utils.ensure_port_available(8765, label="VANOVA runtime", probe=lambda: False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "recovery_failed")
        kill.assert_not_called()
        pn.assert_called_once()
        self.assertIn("no es de VANOVA", result["message"])

    def test_own_runtime_pid_is_killed(self):
        """Un proceso identificado como runtime propio sí se recupera."""
        with patch.object(port_utils, "is_port_in_use", side_effect=[True, True, False]) as pin, \
             patch.object(port_utils, "find_pids_on_port", return_value=[777]), \
             patch.object(port_utils, "process_name", return_value="python.exe"), \
             patch.object(port_utils, "kill_pid", return_value=True) as kill:
            result = port_utils.ensure_port_available(8765, label="VANOVA runtime", probe=lambda: False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "recovered")
        kill.assert_called()
        self.assertTrue(all(c.args == (777,) for c in kill.call_args_list))

    def test_runtime_matches_install_same_config(self):
        """P2-2: runtime con el MISMO configPath se considera nuestra instalación."""
        with patch.object(port_utils, "runtime_config_path", return_value=r"C:\Users\Acme\AppData\Local\VANOVA\config\maios.json"):
            self.assertTrue(
                port_utils.runtime_matches_install(
                    8765, expected_config=r"C:\Users\Acme\AppData\Local\VANOVA\config\maios.json"
                )
            )

    def test_runtime_matches_install_different_config(self):
        """P2-2: un runtime con OTRO configPath (otra instalación/perfil) NO
        puede reutilizarse — se rechaza el attach."""
        with patch.object(port_utils, "runtime_config_path", return_value=r"C:\Users\Other\AppData\Local\VANOVA\config\maios.json"):
            self.assertFalse(
                port_utils.runtime_matches_install(
                    8765, expected_config=r"C:\Users\Acme\AppData\Local\VANOVA\config\maios.json"
                )
            )

    def test_runtime_matches_install_unknown_owner(self):
        """P2-2: si el runtime activo NO reporta configPath, nunca se asume que
        es nuestra instalación (fail-safe)."""
        with patch.object(port_utils, "runtime_config_path", return_value=None):
            self.assertFalse(
                port_utils.runtime_matches_install(8765, expected_config=r"C:\Users\Acme\AppData\Local\VANOVA\config\maios.json")
            )


class RuntimeProbeAuthTests(unittest.TestCase):
    """VANOVA 3.0 (regresión): un runtime protegido (P2-1 — los GET de datos
    exigen token) devuelve 401 en /api/files SIN token. urllib.urlopen LANZA
    HTTPError para 401; probe_runtime debe capturarlo y contar el 401 como
    sano (el comentario lo decía, el código no lo hacía → cualquier runtime
    protegido se marcaba "Runtime desactualizado — reiniciar")."""

    def _serve(self, files_status: int) -> int:
        import http.server
        import json
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/api/health":
                    body = json.dumps({"status": "ok", "service": "vanova-desktop-runtime"})
                    self.send_response(200)
                elif self.path == "/api/setup/status":
                    body = json.dumps({"complete": True, "configPath": r"C:\\Acme\\config\\maios.json"})
                    self.send_response(200)
                elif self.path == "/api/files":
                    body = json.dumps({"error": "Unauthorized"})
                    self.send_response(files_status)
                else:
                    body = json.dumps({})
                    self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return port

    def test_protected_runtime_401_counts_healthy(self):
        """Runtime con auth: /api/files → 401 (sin token) debe contar como
        sano — NO como "desactualizado"."""
        port = self._serve(401)
        self.assertTrue(port_utils.probe_runtime(port))

    def test_runtime_200_still_healthy(self):
        port = self._serve(200)
        self.assertTrue(port_utils.probe_runtime(port))

    def test_runtime_error_response_stale(self):
        """Cualquier otro estado (p.ej. 500) sigue siendo runtime no sano."""
        port = self._serve(500)
        self.assertFalse(port_utils.probe_runtime(port))


if __name__ == "__main__":
    unittest.main()
