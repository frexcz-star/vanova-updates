"""Update manifest provider — configurable remote manifest source."""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from ..logger import get_logger
from ..paths import app_root, config_dir
from .semver import satisfies_minimum, gt

log = get_logger("maios.update.manifest", "updater")


def _normalize_release_notes(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    return [str(x) for x in raw if x is not None and str(x).strip()]


@dataclass
class UpdateManifest:
    product: str = "VANOVA"
    channel: str = "stable"
    version: str = "0.0.0"
    minimum_supported_version: str = "0.0.0"
    mandatory: bool = False
    published_at: str = ""
    download_url: str = ""
    sha256: str = ""
    size: int = 0
    signature: str = ""
    release_notes: list[str] = field(default_factory=list)
    required_hermes: str = ""
    db_schema_version: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UpdateManifest":
        return cls(
            product=data.get("product", "VANOVA"),
            channel=data.get("channel", "stable"),
            version=data.get("version", "0.0.0"),
            minimum_supported_version=data.get("minimumSupportedVersion", data.get("minimum_supported_version", "0.0.0")),
            mandatory=bool(data.get("mandatory", False)),
            published_at=data.get("publishedAt", data.get("published_at", "")),
            download_url=data.get("downloadUrl", data.get("download_url", "")),
            sha256=data.get("sha256", ""),
            size=int(data.get("size", 0) or 0),
            signature=data.get("signature", ""),
            release_notes=_normalize_release_notes(data.get("releaseNotes", data.get("release_notes", []))),
            required_hermes=data.get("requiredHermes", data.get("required_hermes", "")),
            db_schema_version=int(data.get("dbSchemaVersion", data.get("db_schema_version", 0)) or 0),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.version or self.version == "0.0.0":
            errors.append("missing version")
        if not self.download_url:
            errors.append("missing downloadUrl")
        if not self.sha256 or len(self.sha256) < 32:
            errors.append("missing or invalid sha256")
        if not self.download_url.startswith("https://") and not self.download_url.startswith("file://") and not self.download_url.startswith("local:"):
            errors.append("downloadUrl must use HTTPS, file://, or local:")
        return errors


class UpdateManifestProvider:
    """Fetch and parse update manifests from a configurable URL."""

    def __init__(self, manifest_url: Optional[str] = None, channel: str = "stable"):
        self.channel = channel or os.getenv("MAIOS_UPDATE_CHANNEL", "stable")
        self.manifest_url = manifest_url or self._default_url()

    def _default_url(self) -> str:
        env = (os.getenv("MAIOS_UPDATE_MANIFEST_URL") or "").strip()
        if env:
            return env
        from . import state_store
        cfg = state_store.load_config()
        configured = (cfg.get("manifestUrl") or "").strip()
        if configured:
            return configured
        vf = app_root() / "version.json"
        if vf.exists():
            data = json.loads(vf.read_text(encoding="utf-8-sig"))
            url = (data.get("updateManifestUrl") or "").strip()
            if url:
                return url
        cfg_path = config_dir() / "updates.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            url = (data.get("manifestUrl") or "").strip()
            if url:
                return url
        return "https://releases.moovingpaper.com/vanova/latest.json"

    def refresh_url(self) -> str:
        """Re-read manifest URL from env/config (supports in-app config changes)."""
        self.manifest_url = self._default_url()
        return self.manifest_url

    @staticmethod
    def _path_from_file_url(url: str) -> Path:
        parsed = urlparse(url)
        path = unquote(parsed.path or "")
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return Path(path)

    def fetch(self) -> UpdateManifest:
        url = self.refresh_url()
        # Local dev: serve from release/latest.json if URL is relative
        if url.startswith("local:"):
            path = app_root() / url.replace("local:", "", 1)
            raw = json.loads(path.read_text(encoding="utf-8"))
        elif url.startswith("file://"):
            path = self._path_from_file_url(url)
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        else:
            log.info("Fetching manifest from %s", url.split("?")[0])
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        manifest = UpdateManifest.from_dict(raw)
        if manifest.channel and manifest.channel != self.channel:
            log.info("Manifest channel %s != configured %s", manifest.channel, self.channel)
        errors = manifest.validate()
        if errors:
            raise ValueError("Invalid manifest: " + ", ".join(errors))
        return manifest

    def is_update_available(self, installed_version: str, manifest: UpdateManifest) -> bool:
        if not gt(manifest.version, installed_version):
            return False
        if not satisfies_minimum(installed_version, manifest.minimum_supported_version):
            return False
        return True
