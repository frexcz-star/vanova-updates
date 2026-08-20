"""Generate release manifests for VANOVA 3.0.0 (channel stable)."""
from __future__ import annotations

import datetime
import hashlib
import json
import pathlib

ROOT = pathlib.Path(r"C:/Users/Admin/maios")
SETUP = ROOT / "release" / "VANOVA-Setup-3.0.0.exe"


def main() -> None:
    data = SETUP.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    size = len(data)

    notes_raw = (ROOT / "release" / "release-notes.md").read_text(encoding="utf-8-sig")
    section: list[str] = []
    capture = False
    for line in notes_raw.splitlines():
        if line.startswith("# VANOVA 3.0.0"):
            capture = True
            continue
        if capture and line.startswith("# VANOVA "):
            break
        if capture and line.strip().startswith("- "):
            section.append(line.strip()[2:].strip())
    if not section:
        section = ["VANOVA 3.0.0 release"]

    manifest = {
        "product": "VANOVA",
        "channel": "stable",
        "version": "3.0.0",
        "minimumSupportedVersion": "0.9.0",
        "mandatory": False,
        "publishedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "downloadUrl": "https://releases.moovingpaper.com/vanova/VANOVA-Setup-3.0.0.exe",
        "sha256": sha,
        "size": size,
        "signature": "",
        "releaseNotes": section,
        "requiredHermes": ">=1.0.0",
        "dbSchemaVersion": 0,
    }
    (ROOT / "release" / "latest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    local = dict(manifest)
    local["downloadUrl"] = "file:///" + str(SETUP.resolve()).replace("\\", "/")
    (ROOT / "release" / "latest.local.json").write_text(
        json.dumps(local, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("sha256:", sha)
    print("size:", size)
    print("notes bullets:", len(section))
    print("local url:", local["downloadUrl"])


if __name__ == "__main__":
    main()
