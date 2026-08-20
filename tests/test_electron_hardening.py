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


if __name__ == "__main__":
    unittest.main()
