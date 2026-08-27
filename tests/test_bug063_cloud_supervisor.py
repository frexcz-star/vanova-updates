"""BUG-063 (HIGH): the cloud (:8000) dies silently and nothing relaunches it.

Root cause: the watchdog lived INSIDE the runtime process (launcher.py
health_watchdog thread -> health_monitor.watchdog_tick). When the runtime also
died, the watchdog died with it, and the Electron app (the only thing that
relaunches the runtime) was not running -> the cloud stayed dead indefinitely.

Fix: a SEPARATE, DETACHED supervisor process (cloud_supervisor.py) spawned by
the launcher with DETACHED_PROCESS, which survives the runtime's death and
independently watches cloud (:8000) + runtime (:8765), relaunching whichever
is down.

These tests FAIL with the pre-fix code (no supervisor module, no detached
spawn in the launcher) and PASS with the fix.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "desktop" / "runtime" / "launcher.py"
SUPERVISOR = ROOT / "desktop" / "runtime" / "cloud_supervisor.py"


class CloudSupervisorExistsTests(unittest.TestCase):
    """The external supervisor module must exist and be self-contained."""

    def test_supervisor_module_exists(self):
        self.assertTrue(SUPERVISOR.exists(), "cloud_supervisor.py missing")

    def test_supervisor_relaunches_cloud(self):
        src = SUPERVISOR.read_text(encoding="utf-8")
        # Must be able to relaunch the cloud with the same uvicorn command.
        self.assertIn("uvicorn", src, "supervisor must relaunch the cloud")
        self.assertIn("cloud.main:app", src, "supervisor must target cloud.main:app")
        self.assertIn("8000", src, "supervisor must watch the cloud port")

    def test_supervisor_watches_runtime_too(self):
        src = SUPERVISOR.read_text(encoding="utf-8")
        # If the runtime dies, the supervisor must relaunch it so the cloud
        # does not stay orphaned.
        self.assertIn("launcher.py", src, "supervisor must relaunch the runtime")
        self.assertIn("8765", src, "supervisor must watch the runtime port")

    def test_supervisor_is_detached_survives_runtime(self):
        src = SUPERVISOR.read_text(encoding="utf-8")
        # The supervisor must be a standalone process (has a __main__ loop),
        # not a thread that dies with the runtime.
        self.assertIn("if __name__ == \"__main__\":", src)
        self.assertIn("while True:", src, "supervisor must run an independent loop")


class LauncherSpawnsSupervisorTests(unittest.TestCase):
    """The launcher must spawn the supervisor as a DETACHED process."""

    def test_launcher_spawns_cloud_supervisor(self):
        src = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("cloud_supervisor", src, "launcher must reference the supervisor")

    def test_launcher_uses_detached_process(self):
        src = LAUNCHER.read_text(encoding="utf-8")
        # DETACHED_PROCESS is what lets the supervisor survive the runtime's death.
        self.assertIn("DETACHED_PROCESS", src, "supervisor must be spawned detached")

    def test_launcher_imports_subprocess(self):
        src = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("import subprocess", src, "launcher must import subprocess")


if __name__ == "__main__":
    unittest.main()
