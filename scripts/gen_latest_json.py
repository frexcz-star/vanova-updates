import hashlib
import json
import os
from datetime import datetime, timezone

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
exe = os.path.join(root, "release", "VANOVA-Setup-3.2.0.exe")

with open(exe, "rb") as f:
    sha = hashlib.sha256(f.read()).hexdigest()
size = os.path.getsize(exe)

manifest = {
    "version": "3.2.0",
    "product": "VANOVA",
    "channel": "stable",
    "notes": "Release 3.2.0: rediseno dashboard (navegacion simplificada, cero emojis, glassmorphism ligero) + BUG-063 (supervisor externo del cloud). Suite 826 passed.",
    "installer": "VANOVA-Setup-3.2.0.exe",
    "size": size,
    "sha256": sha,
    "downloadUrl": "https://releases.moovingpaper.com/vanova/VANOVA-Setup-3.2.0.exe",
    "releaseNotesUrl": "https://github.com/frexcz-star/vanova-updates/releases/tag/v.3.2.0",
    "publishedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "minSupportedVersion": "3.1.2",
    "mandatory": False,
    "dbSchemaVersion": 0,
}

with open(os.path.join(root, "release", "latest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print("latest.json written")
print("version:", manifest["version"])
print("sha256:", sha)
print("size:", size)
