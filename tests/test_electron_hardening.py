"""Electron shell security regression tests (Phase 3)."""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_JS = ROOT / "desktop" / "main.js"
PRELOAD_JS = ROOT / "desktop" / "preload.js"


class ElectronHardeningTests(unittest.TestCase):
    def test_main_js_syntax(self):
        result = subprocess.run(
            ["node", "--check", str(MAIN_JS)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_preload_syntax(self):
        result = subprocess.run(
            ["node", "--check", str(PRELOAD_JS)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_web_preferences_hardened(self):
        source = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("sandbox: true", source)
        self.assertIn("webSecurity: true", source)
        self.assertNotIn("webSecurity: false", source)
        self.assertNotIn("sandbox: false", source)
        self.assertNotIn("allowRunningInsecureContent: true", source)
        self.assertIn("contextIsolation: true", source)
        self.assertIn("nodeIntegration: false", source)

    def test_preload_exposes_minimal_api(self):
        source = PRELOAD_JS.read_text(encoding="utf-8")
        self.assertIn("contextBridge.exposeInMainWorld('maios'", source)
        self.assertNotIn("exposeInMainWorld('require'", source)
        self.assertNotIn("exposeInMainWorld('ipcRenderer'", source)
        allowed = re.findall(r"(\w+):\s*\(\)", source)
        for method in (
            "openDashboard",
            "getRuntimeAuthHeaders",
            "restartRuntime",
            "getVersion",
        ):
            self.assertIn(method, allowed)

    # BUG-0001 (QA baseline): un runtime huérfano de una sesión muerta
    # (crash / force-kill de Electron) NO debe reutilizarse en silencio.
    # Si responde /api/health pero no fue lanzado por este proceso
    # (runtimeProcess === null), debe reemplazarse para que cloud/connector/
    # Hermes se levanten limpios.
    def test_bug0001_orphaned_runtime_is_replaced_not_reused(self):
        source = MAIN_JS.read_text(encoding="utf-8")
        # El código debe comprobar si el runtime fue lanzado por este proceso.
        self.assertIn("runtimeBelongsToThisInstall", source)
        self.assertIn("!runtimeProcess", source)
        # Debe existir el log que distingue el huérfano del caso sano.
        self.assertIn(
            "Runtime healthy but orphaned from a previous session — replacing",
            source,
        )
        self.assertIn("killPidsOnPort(RUNTIME_PORT)", source)
        # El caso sano (mismo proceso Electron) sigue reutilizando el runtime.
        self.assertIn("Runtime already healthy — skipping spawn", source)
        # El caso foráneo sigue rechazándose (P2-2, nunca mezclar perfiles).
        self.assertIn("FOREIGN_RUNTIME", source)
        self.assertIn("refusing to attach", source)

    # BUG-0002 (QA baseline): lanzar VANOVA con --remote-debugging-port
    # mientras otra instancia corre en background no debe perder el flag.
    # La instancia existente debe relanzarse con el flag de depuración.
    def test_bug0002_remote_debugging_flag_is_relayed(self):
        source = MAIN_JS.read_text(encoding="utf-8")
        # El handler de segunda instancia debe detectar el flag de depuración.
        self.assertIn("--remote-debugging-port=", source)
        self.assertIn("app.relaunch", source)
        # Debe relanzarse con el flag, nunca abrir un segundo perfil.
        self.assertIn("app.quit()", source)
        # El focus normal de segunda instancia debe seguir existiendo.
        self.assertIn("focusPrimaryWindow()", source)
        self.assertNotIn("remote-debugging-port", source.split("second-instance")[0])


if __name__ == "__main__":
    unittest.main()
