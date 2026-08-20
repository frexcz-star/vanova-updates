"""Version consistency tests — every source must agree with version.json."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared import version_info


def _expected_version() -> str:
    data = json.loads((ROOT / "version.json").read_text(encoding="utf-8-sig"))
    return str(data.get("version") or "0.0.0")


class VersionConsistencyTests(unittest.TestCase):
    def test_version_json_matches_shared(self):
        expected = _expected_version()
        self.assertEqual(version_info.current_version(), expected)

    def test_version_bundle_labels(self):
        expected = _expected_version()
        bundle = version_info.version_bundle()
        self.assertEqual(bundle["maios"], expected)
        self.assertEqual(bundle["cloud"], expected)
        self.assertEqual(bundle["runtime"], expected)
        self.assertEqual(bundle["connector"], expected)

    def test_health_monitor_uses_installed_version(self):
        from desktop.runtime import health_monitor

        expected = _expected_version()
        with patch("desktop.runtime.config_store.load", return_value={"setupComplete": True, "version": "1.0.1"}):
            with patch("desktop.runtime.updater.current_version", return_value=expected):
                row = health_monitor._check_maios()
        self.assertEqual(row["version"], expected)

    def test_desktop_package_version(self):
        pkg = json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(pkg.get("version"), _expected_version())


if __name__ == "__main__":
    unittest.main()
