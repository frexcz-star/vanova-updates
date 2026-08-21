"""Production hardening tests — VANOVA 1.0.1 audit."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import agent_permissions, installer, policy_engine, python_runtime


class InstallerSemanticsTests(unittest.TestCase):
    def test_critical_failure_not_ok(self):
        with patch("desktop.runtime.installer.analyze", return_value={}), patch(
            "desktop.runtime.installer.dependency_resolver.resolve", return_value={}
        ), patch("desktop.runtime.installer.config_store.save"), patch(
            "desktop.runtime.installer.process_manager._ensure_venv",
            side_effect=RuntimeError("venv failed"),
        ), patch(
            "desktop.runtime.installer.process_manager.start_all",
            return_value={"cloud": False, "connector": False, "warnings": ["Cloud down"]},
        ), patch(
            "desktop.runtime.installer.hermes_service.install",
            return_value={"ok": False},
        ), patch(
            "desktop.runtime.installer.validate_startup",
            return_value={"status": "failed", "checks": [{"status": "critical", "id": "cloud"}]},
        ):
            result = installer.run_installation()
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["criticalErrors"])


class PythonRuntimeTests(unittest.TestCase):
    def test_production_missing_python_raises(self):
        with patch.dict(os.environ, {"MAIOS_PACKAGED": "1", "MAIOS_DEV": ""}, clear=False), patch(
            "desktop.runtime.python_runtime.app_root",
            return_value=Path("/nonexistent/maios"),
        ), patch("desktop.runtime.python_runtime.venv_dir", return_value=Path("/nonexistent/venv")):
            with self.assertRaises(python_runtime.PythonRuntimeError) as ctx:
                python_runtime.resolve_python(required=True)
            self.assertEqual(ctx.exception.code, python_runtime.PYTHON_RUNTIME_MISSING)


class AgentPermissionDenyTests(unittest.TestCase):
    def test_no_permission_denies(self):
        agent = {"id": "x", "permissions": [], "integrations": [], "tools": []}
        allowed, err = agent_permissions.validate_task_execution(agent, {"permission": "tasks.execute"})
        self.assertFalse(allowed)

    def test_wildcard_allows(self):
        agent = {"id": "hermes", "permissions": ["*"]}
        allowed, _ = agent_permissions.validate_task_execution(agent, {"permission": "tasks.execute"})
        self.assertTrue(allowed)


class CriticalActionTests(unittest.TestCase):
    def test_publish_requires_approval_even_autonomous(self):
        with patch("desktop.runtime.autonomy_config.get_level", return_value="autonomous"):
            decision = policy_engine.evaluate(action="instagram.publish")
        self.assertEqual(decision.effect, "require_approval")

    def test_delete_requires_approval(self):
        with patch("desktop.runtime.autonomy_config.get_level", return_value="autonomous"):
            decision = policy_engine.evaluate(action="delete")
        self.assertEqual(decision.effect, "require_approval")


class CorsProductionTests(unittest.TestCase):
    def test_production_cors_not_wildcard(self):
        with patch.dict(os.environ, {"MAIOS_ENV": "production", "MAIOS_ALLOWED_ORIGINS": ""}, clear=False):
            origins = [o.strip() for o in os.getenv("MAIOS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
            if not origins:
                origins = [
                    "http://127.0.0.1:8000",
                    "http://localhost:8000",
                    "http://127.0.0.1:8765",
                    "http://localhost:8765",
                ]
            self.assertNotIn("*", origins)
            self.assertGreaterEqual(len(origins), 1)


class DefaultPasswordTests(unittest.TestCase):
    def test_weak_password_in_known_set(self):
        from cloud.main import KNOWN_WEAK_PASSWORDS

        self.assertIn("mooving2026", KNOWN_WEAK_PASSWORDS)

    def test_production_bootstrap_rejects_weak_password(self):
        from cloud import main as cm

        with patch.object(cm, "MAIOS_ENV", "production"), patch.dict(
            os.environ, {"MAIOS_DEMO_PASSWORD": "mooving2026"}, clear=False
        ), patch("cloud.main.init_db"), patch("cloud.main.get_db"):
            with self.assertRaises(RuntimeError):
                cm.bootstrap()


class Bug031WeakPasswordAutoRegenTests(unittest.TestCase):
    """BUG-031: el fix de raíz — si el cloud.env desplegado trae una contraseña
    débil/por defecto (la del instalador, p.ej. mooving2026), _ensure_env_files
    debe regenerarla automáticamente para que el cloud no bloquee el arranque
    ("cloud start failed"). El test falla sin el fix (la contraseña débil se
    mantendría)."""

    def test_ensure_env_files_regenertes_weak_password(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch as _patch

        from desktop.runtime import process_manager

        tmp = tempfile.TemporaryDirectory()
        env_file = Path(tmp.name) / "cloud.env"
        # cloud.env desplegado con la contraseña débil por defecto del instalador
        env_file.write_text("MAIOS_DEMO_PASSWORD=mooving2026\nMAIOS_ENV=production\n", encoding="utf-8")

        cfg_dir = Path(tmp.name)
        with _patch.object(process_manager, "config_dir", return_value=cfg_dir), \
             _patch.object(process_manager, "logs_dir", return_value=cfg_dir), \
             _patch.object(process_manager, "app_root", return_value=cfg_dir), \
             _patch.object(process_manager.install_secrets, "ensure_install_secrets", return_value={}), \
             _patch("desktop.runtime.process_manager.install_secrets", side_effect=lambda: None):
            process_manager._ensure_env_files()

        new_content = env_file.read_text(encoding="utf-8")
        new_pw = next(
            (line.split("=", 1)[1].strip() for line in new_content.splitlines()
             if line.strip().startswith("MAIOS_DEMO_PASSWORD=")),
            "",
        )
        self.assertTrue(new_pw)
        self.assertNotEqual(new_pw.lower(), "mooving2026")
        self.assertNotIn(new_pw.lower(), process_manager.KNOWN_WEAK_PASSWORDS)


if __name__ == "__main__":
    unittest.main()
