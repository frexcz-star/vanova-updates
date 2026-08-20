"""Check update availability from baseline to target using latest.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime.update.manifest_provider import UpdateManifest, UpdateManifestProvider


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: e2e-check-update.py <baseline_version> <latest_json_path>")
        return 2
    baseline = sys.argv[1]
    latest_path = Path(sys.argv[2])
    data = json.loads(latest_path.read_text(encoding="utf-8"))
    manifest = UpdateManifest(
        version=data["version"],
        download_url=data["downloadUrl"],
        sha256=data["sha256"],
        size=data["size"],
    )
    provider = UpdateManifestProvider()
    avail = provider.is_update_available(baseline, manifest)
    print(f"update_available_from_{baseline}:", avail)
    return 0 if avail else 1


if __name__ == "__main__":
    raise SystemExit(main())
