"""No-Python-installed regression tests — a fresh user with no system Python
must be able to run VANOVA straight from the installer.

Hallazgo #7: the setup plan resolver checked for a bundled interpreter under
`python/` but the installer actually ships it under `python-bundle/`. On a
machine with no Python installed the wizard would ask the user to "create a
Python environment" even though the portable runtime was already present, and
`resolve_python` must always prefer the bundled interpreter in production
(never fall back to bare `python` on PATH).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import dependency_resolver, python_runtime


def _make_layout(tmp: Path, *, with_bundle: bool) -> Path:
    """Build a fake packaged app root: resources/vanova/..."""
    root = tmp / "resources" / "vanova"
    if with_bundle:
        (root / "python-bundle").mkdir(parents=True)
        (root / "python-bundle" / "python.exe").write_bytes(b"fake")
    return root


class NoPythonInstalledTests(unittest.TestCase):
    def test_resolve_python_prefers_bundled_interpreter_in_production(self):
        """Packaged installs resolve to the bundled interpreter, never to bare
        `python` on PATH (which does not exist on a fresh machine)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_layout(Path(tmp), with_bundle=True)
            with patch.object(python_runtime, "app_root", return_value=root), \
                 patch.object(python_runtime, "venv_dir", return_value=Path(tmp) / "data" / "venv"):
                py = python_runtime.resolve_python(required=True)
            self.assertIsNotNone(py)
            self.assertIn("python-bundle", str(py))

    def test_resolve_python_raises_when_no_bundle(self):
        """If the bundled interpreter is missing (e.g. antivirus removed it)
        production must fail closed with the structured error, not silently
        fall back to the system python."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_layout(Path(tmp), with_bundle=False)
            with patch.object(python_runtime, "app_root", return_value=root), \
                 patch.object(python_runtime, "is_production", return_value=True), \
                 patch.object(python_runtime, "venv_dir", return_value=Path(tmp) / "data" / "venv"):
                with self.assertRaises(python_runtime.PythonRuntimeError) as ctx:
                    python_runtime.resolve_python(required=True)
            self.assertEqual(ctx.exception.code, python_runtime.PYTHON_RUNTIME_MISSING)

    def test_setup_plan_marks_python_not_required_when_bundle_present(self):
        """Regression (Hallazgo #7): with python-bundle/ present the wizard must
        NOT ask the user to install or create a Python environment."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_layout(Path(tmp), with_bundle=True)
            with patch.object(dependency_resolver, "app_root", return_value=root):
                plan = dependency_resolver.resolve(
                    {"dependencies": {"python": {"ok": False}}}
                )
            py_item = next(
                (x for x in plan["required"] if x.get("id") == "python"), None
            )
            self.assertIsNone(py_item, "setup must not require Python when bundled")
            not_required = next(
                (x for x in plan["notRequired"] if x.get("id") == "python"), None
            )
            self.assertIsNotNone(not_required)
            self.assertIn("bundled", not_required.get("reason", "").lower())

    def test_setup_plan_marks_python_not_required_without_any_system_python(self):
        """Same as above but even when the analyzer found no system python at
        all — the bundle alone must satisfy the plan."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_layout(Path(tmp), with_bundle=True)
            with patch.object(dependency_resolver, "app_root", return_value=root):
                plan = dependency_resolver.resolve(
                    {"dependencies": {"python": {"ok": False}}}
                )
            ids = [x.get("id") for x in plan["required"]]
            self.assertNotIn("python", ids)
            self.assertNotIn("python-venv", ids)
            self.assertNotIn("python-bundled", ids)

    def test_requirements_are_covered_by_bundle(self):
        """Every module required by cloud/connector/runtime must import with
        the bundled interpreter — verified live on the installed bundle."""
        import importlib

        exe = None
        bundled = (
            ROOT / "desktop" / "python-bundle" / "python.exe"
        )
        if bundled.exists():
            exe = bundled
        if not exe:
            self.skipTest("python-bundle not present in this checkout")
        mods = [
            "fastapi", "uvicorn", "httpx", "dotenv", "bcrypt", "jose",
            "pydantic", "multipart", "yaml", "websockets", "watchfiles",
            "cryptography",
        ]
        # Probe with the bundled interpreter itself (fresh process, no system
        # python involvement).
        import subprocess

        probe = ";".join(f"import {m}" for m in mods)
        proc = subprocess.run(
            [str(exe), "-c", probe],
            capture_output=True, text=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"bundled interpreter missing modules:\n{proc.stderr[:500]}",
        )


if __name__ == "__main__":
    unittest.main()
