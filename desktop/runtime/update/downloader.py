"""Secure update downloader with progress, retry, and temp storage."""
from __future__ import annotations

import hashlib
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from ..logger import get_logger
from ..paths import data_dir

log = get_logger("maios.update.downloader", "updater")

ProgressCallback = Callable[[int, int], None]  # downloaded, total


class UpdateDownloader:
    def __init__(self, temp_root: Optional[Path] = None):
        self.temp_root = temp_root or (data_dir() / "temp" / "update")
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def package_dir(self, version: str) -> Path:
        path = self.temp_root / version
        path.mkdir(parents=True, exist_ok=True)
        return path

    def package_path(self, version: str, filename: str = "VANOVA-Setup.exe") -> Path:
        return self.package_dir(version) / filename

    def download(
        self,
        url: str,
        dest: Path,
        expected_size: int = 0,
        progress: Optional[ProgressCallback] = None,
        retries: int = 3,
    ) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_suffix(dest.suffix + ".partial")

        for attempt in range(1, retries + 1):
            try:
                resume_from = partial.stat().st_size if partial.exists() else 0
                want_resume = resume_from > 0 and expected_size and resume_from < expected_size
                headers = {}
                if want_resume:
                    headers["Range"] = f"bytes={resume_from}-"
                    log.info("Resuming download from byte %d", resume_from)

                req = urllib.request.Request(url, headers=headers)
                # Timeout generoso por lectura: descargas de ~93MB a traves de
                # tuneles/CDNs pueden ralentizarse; 60s provocaba falsos fallos.
                with urllib.request.urlopen(req, timeout=300) as resp:
                    total = expected_size or int(resp.headers.get("Content-Length", 0) or 0)
                    # Solo se reanuda si el servidor respondio 206 (rango). Si
                    # responde 200 (contenido completo) se descarta el partial:
                    # anadir el archivo entero al partial duplicaria bytes y
                    # romperia el checksum.
                    if want_resume and resp.status != 206:
                        resume_from = 0
                        if partial.exists():
                            partial.unlink(missing_ok=True)
                    elif not want_resume and partial.exists():
                        partial.unlink(missing_ok=True)

                    mode = "ab" if resume_from else "wb"
                    downloaded = resume_from
                    with open(partial, mode) as f:
                        while True:
                            chunk = resp.read(256 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress:
                                progress(downloaded, total or downloaded)

                shutil.move(str(partial), str(dest))
                log.info("Download complete: %s", dest)
                return dest
            except Exception as exc:
                log.warning("Download attempt %d failed: %s", attempt, exc)
                if attempt >= retries:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("Download failed")

    @staticmethod
    def sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def cleanup_version(self, version: str) -> None:
        path = self.temp_root / version
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def cleanup_all(self) -> None:
        if self.temp_root.exists():
            shutil.rmtree(self.temp_root, ignore_errors=True)
            self.temp_root.mkdir(parents=True, exist_ok=True)
