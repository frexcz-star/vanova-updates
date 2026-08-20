"""Update Manager — orchestrates check, download, verify, install transaction."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from ..logger import get_logger
from ..paths import app_root, data_dir
from .. import hermes_service
from .backup import create_backup, restore_backup
from .downloader import UpdateDownloader
from .manifest_provider import UpdateManifest, UpdateManifestProvider
from .semver import gt
from .state_machine import UpdateState, transition
from . import state_store
from .state_store import state_file

log = get_logger("maios.update.manager", "updater")

EventCallback = Callable[[str, dict[str, Any]], None]


class UpdateManager:
    def __init__(self, on_event: Optional[EventCallback] = None):
        self.on_event = on_event or (lambda _e, _d: None)
        cfg = state_store.load_config()
        self.provider = UpdateManifestProvider(channel=cfg.get("channel", "stable"))
        self.downloader = UpdateDownloader()
        self._cancel_requested = False
        self._download_thread: Optional[threading.Thread] = None

    @staticmethod
    def _parse_iso(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    def _is_postponed(self, version: str, cfg: Optional[dict[str, Any]] = None) -> bool:
        cfg = cfg or state_store.load_config()
        if cfg.get("postponedVersion") != version:
            return False
        until = self._parse_iso(cfg.get("postponedUntil"))
        if until is None:
            return False
        return datetime.now(timezone.utc) < until

    def _fetch_manifest_with_deadline(self, timeout: float = 25.0) -> Any:
        """Fetch the manifest with a HARD deadline.

        urllib's socket timeout does not bound DNS resolution on every
        platform, so a stuck resolver could otherwise leave the check hanging
        forever (and the UI on "Buscando actualizaciones…" indefinitely). The
        worker thread is daemon so it never blocks shutdown; the handler thread
        always returns within ``timeout`` seconds.
        """
        from concurrent.futures import ThreadPoolExecutor

        # NOTA: no usar el context manager — su __exit__ hace shutdown(wait=True)
        # y bloquearía esperando al hilo colgado. shutdown(wait=False) devuelve
        # al instante; el worker (daemon) queda abandonado sin bloquear nada.
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="maios-manifest")
        try:
            future = pool.submit(self.provider.fetch)
            try:
                return future.result(timeout=timeout)
            except Exception as exc:  # incluye futures.TimeoutError
                if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
                    raise TimeoutError(
                        f"El servidor de actualizaciones no respondió en {int(timeout)} s"
                    ) from exc
                raise
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _should_check(self, force: bool, cfg: dict[str, Any]) -> bool:
        if force:
            return True
        if not cfg.get("autoCheck", True):
            return False
        last = self._parse_iso(cfg.get("lastCheck"))
        if last is None:
            return True
        interval = float(cfg.get("checkIntervalHours", 4) or 4)
        return datetime.now(timezone.utc) >= last + timedelta(hours=interval)

    def _maybe_auto_download(self) -> None:
        cfg = state_store.load_config()
        if not cfg.get("autoDownload"):
            return
        st = state_store.load_state()
        if st.get("state") != UpdateState.AVAILABLE.value:
            return
        if self._download_thread and self._download_thread.is_alive():
            return

        def _run():
            try:
                self.download_update()
            except Exception as exc:
                log.warning("Background auto-download failed: %s", exc)

        self._download_thread = threading.Thread(target=_run, daemon=True, name="maios-auto-download")
        self._download_thread.start()

    def _emit(self, event: str, data: Optional[dict] = None) -> None:
        self.on_event(event, data or {})
        log.info("update.%s %s", event, json.dumps(data or {}, default=str)[:200])

    def _set(self, state: UpdateState, **kwargs: Any) -> dict[str, Any]:
        current = UpdateState(state_store.load_state().get("state", UpdateState.IDLE.value))
        try:
            transition(current, state)
        except ValueError:
            log.warning("Forced state %s from %s", state.value, current.value)
        if state not in (UpdateState.FAILED, UpdateState.OFFLINE):
            kwargs.setdefault("error", None)
        data = state_store.set_state(state, **kwargs)
        self._emit(f"update.{state.value}", data)
        return data

    def get_status(self) -> dict[str, Any]:
        from ..updater import current_version

        st = state_store.load_state()
        cfg = state_store.load_config()
        manifest_url = self.provider.refresh_url()
        return {
            **st,
            "installedVersion": current_version(),
            "channel": cfg.get("channel", "stable"),
            "lastCheck": cfg.get("lastCheck"),
            "manifestUrl": manifest_url,
            "history": state_store.get_history()[:5],
            "download": {
                "percent": st.get("progress"),
                "bytesReceived": st.get("downloadedBytes", 0),
                "totalBytes": st.get("totalBytes", 0),
            },
            "config": {
                k: cfg[k]
                for k in (
                    "channel", "autoCheck", "autoDownload", "manifestUrl",
                    "checkIntervalHours", "postponeHours",
                    "postponedVersion", "postponedUntil",
                )
                if k in cfg
            },
            "postponed": self._is_postponed(st.get("targetVersion") or "", cfg),
        }

    def check_for_updates(self, force: bool = False) -> dict[str, Any]:
        from ..updater import current_version

        installed = current_version()
        cfg = state_store.load_config()
        if not self._should_check(force, cfg):
            st = state_store.load_state()
            result = {
                **st,
                "installedVersion": installed,
                "updateAvailable": st.get("state") == UpdateState.AVAILABLE.value,
                "skippedCheck": True,
                "message": "Comprobación omitida — intervalo no alcanzado",
            }
            return result

        self.provider.refresh_url()
        self._set(UpdateState.CHECKING, targetVersion=None, message="Buscando actualizaciones…")
        try:
            manifest = self._fetch_manifest_with_deadline()
            cfg["lastCheck"] = datetime.now(timezone.utc).isoformat()

            # A manual check (force=True) is an explicit user request: it must
            # override any previous postponement so "Buscar actualizaciones"
            # always surfaces an available update instead of silently deferring.
            if force and cfg.get("postponedVersion") == manifest.version:
                cfg["postponedVersion"] = None
                cfg["postponedUntil"] = None

            state_store.save_config(cfg)

            if self._is_postponed(manifest.version, cfg):
                result = self._set(
                    UpdateState.UP_TO_DATE,
                    targetVersion=None,
                    manifest=asdict(manifest),
                    manifestSource=self.provider.manifest_url,
                    message=f"Actualización pospuesta hasta {cfg.get('postponedUntil', '')}",
                )
                result["updateAvailable"] = False
                result["postponed"] = True
                result["installedVersion"] = installed
                result["latestVersion"] = manifest.version
                result["releaseNotes"] = manifest.release_notes
                self._emit("update.postponed", result)
                return result

            # Product guard: the update channel is per-product. A manifest for a
            # DIFFERENT product (e.g. legacy MAIOS manifests) must never be
            # installed over VANOVA, and vice versa.
            own_product = (self._product_name() or "").strip().lower()
            manifest_product = (manifest.product or "").strip().lower()
            if own_product and manifest_product and manifest_product != own_product:
                log.info("Manifest product %s != installed product %s — ignoring", manifest.product, own_product)
                available = False
            else:
                available = self.provider.is_update_available(installed, manifest)
            if available:
                result = self._set(
                    UpdateState.AVAILABLE,
                    targetVersion=manifest.version,
                    manifest=asdict(manifest),
                    manifestSource=self.provider.manifest_url,
                    message=f"VANOVA {manifest.version} disponible",
                )
                self._maybe_auto_download()
            else:
                result = self._set(
                    UpdateState.UP_TO_DATE,
                    targetVersion=None,
                    manifest=asdict(manifest),
                    message="VANOVA está actualizado.",
                )
            result["updateAvailable"] = available
            result["installedVersion"] = installed
            result["latestVersion"] = manifest.version
            result["mandatory"] = manifest.mandatory
            result["releaseNotes"] = manifest.release_notes
            self._emit("update.available" if available else "update.up_to_date", result)
            return result
        except Exception as exc:
            log.warning("Update check failed: %s", exc)
            result = self._set(
                UpdateState.OFFLINE,
                error=str(exc),
                message="No se pudo comprobar actualizaciones",
            )
            result["offline"] = True
            result["installedVersion"] = installed
            self._emit("update.failed", result)
            return result

    def postpone_update(self, version: str = "", hours: Optional[float] = None) -> dict[str, Any]:
        cfg = state_store.load_config()
        st = state_store.load_state()
        target = version or st.get("targetVersion") or ""
        if not target:
            manifest_data = st.get("manifest") or {}
            target = manifest_data.get("version", "")
        if not target:
            return {"ok": False, "error": "No hay actualización para posponer"}

        postpone_hours = float(hours if hours is not None else cfg.get("postponeHours", 24) or 24)
        until = datetime.now(timezone.utc) + timedelta(hours=postpone_hours)
        cfg["postponedVersion"] = target
        cfg["postponedUntil"] = until.isoformat()
        state_store.save_config(cfg)

        current = UpdateState(st.get("state", UpdateState.IDLE.value))
        if current == UpdateState.AVAILABLE:
            self._set(
                UpdateState.UP_TO_DATE,
                targetVersion=None,
                message=f"Actualización pospuesta {int(postpone_hours)} h",
            )

        result = {
            "ok": True,
            "postponedVersion": target,
            "postponedUntil": cfg["postponedUntil"],
            "hours": postpone_hours,
        }
        self._emit("update.postponed", result)
        return result

    def download_update(self) -> dict[str, Any]:
        st = state_store.load_state()
        manifest_data = st.get("manifest")
        if not manifest_data:
            return self._fail("No update available to download")

        # Guarda de concurrencia: si ya hay una descarga en curso, no duplicar
        # (dos hilos escribiendo el mismo .partial la corromperian).
        if self._download_thread is not None and self._download_thread.is_alive():
            return self._set(
                UpdateState.DOWNLOADING,
                progress=st.get("progress", 0),
                message="Descarga en curso…",
            )

        self._cancel_requested = False
        self._set(UpdateState.DOWNLOADING, progress=0, message="Downloading update…")
        # La descarga corre en segundo plano: devolvemos al instante para que
        # la UI pueda hacer poll de progreso sin bloquear la peticion HTTP.
        self._download_thread = threading.Thread(
            target=self._download_worker, daemon=True, name="maios-update-download"
        )
        self._download_thread.start()
        return self._set(UpdateState.DOWNLOADING, progress=0, message="Downloading update…")

    def _download_worker(self) -> None:
        try:
            st = state_store.load_state()
            manifest_data = st.get("manifest")
            if not manifest_data:
                self._fail("No update available to download")
                return
            manifest = UpdateManifest.from_dict(manifest_data)
            dest = self.downloader.package_path(manifest.version)

            def progress(done: int, total: int):
                pct = int((done / total) * 100) if total else 0
                state_store.set_state(
                    UpdateState.DOWNLOADING,
                    progress=pct,
                    downloadedBytes=done,
                    totalBytes=total,
                    message="Downloading update…",
                )
                self._emit("update.progress", {"percent": pct, "downloaded": done, "total": total})

            url = manifest.download_url
            # Allow local file URLs for testing
            if url.startswith("local:"):
                src = self._resolve_local_path(url, st)
                shutil.copy2(src, dest)
                done = dest.stat().st_size
                progress(done, done)
            elif url.startswith("file://"):
                from .manifest_provider import UpdateManifestProvider
                src = UpdateManifestProvider._path_from_file_url(url)
                shutil.copy2(src, dest)
                done = dest.stat().st_size
                progress(done, done)
            else:
                self.downloader.download(url, dest, manifest.size, progress)

            if self._cancel_requested:
                self.downloader.cleanup_version(manifest.version)
                self._set(UpdateState.CANCELLED, message="Download cancelled")
                return

            self._set(UpdateState.DOWNLOADED, packagePath=str(dest), progress=100)
            self.verify_package()
        except Exception as exc:
            self._fail(f"Download failed: {exc}")
        finally:
            self._download_thread = None

    def verify_package(self) -> dict[str, Any]:
        st = state_store.load_state()
        path = Path(st.get("packagePath") or "")
        manifest = UpdateManifest.from_dict(st.get("manifest", {}))
        if not path.exists():
            return self._fail("Package not found")

        self._set(UpdateState.VERIFYING, message="Verifying package…")
        digest = self.downloader.sha256(path)
        if digest.lower() != manifest.sha256.lower():
            path.unlink(missing_ok=True)
            return self._fail(
                "Update verification failed. The downloaded package does not match the expected checksum."
            )

        # Signature verification placeholder
        if manifest.signature:
            log.info("Signature present — verification not yet implemented")

        # Pre-install validation
        issues = self._pre_install_checks(path, manifest)
        if issues:
            return self._fail("; ".join(issues))

        return self._set(UpdateState.READY_TO_INSTALL, message="Ready to install")

    def install_update(self) -> dict[str, Any]:
        from ..updater import current_version

        st = state_store.load_state()
        manifest = UpdateManifest.from_dict(st.get("manifest", {}))
        if not manifest.version:
            return self._fail("No update available to install")

        path = Path(st.get("packagePath") or "")
        expected = self.downloader.package_path(manifest.version)
        if not path.exists() or path.resolve() != expected.resolve():
            if expected.exists():
                path = expected
                state_store.set_state(UpdateState.READY_TO_INSTALL, packagePath=str(path))
            else:
                log.info("Package missing or stale — re-downloading %s", manifest.version)
                dl = self.download_update()
                if dl.get("state") in (UpdateState.FAILED.value, UpdateState.CANCELLED.value, UpdateState.OFFLINE.value):
                    return dl
                # La descarga corre en segundo plano: esperar a que termine.
                deadline = time.time() + 900
                while time.time() < deadline:
                    st = state_store.load_state()
                    cur = st.get("state")
                    if cur == UpdateState.READY_TO_INSTALL.value:
                        path = Path(st.get("packagePath") or "")
                        if path.exists():
                            break
                    if cur in (UpdateState.FAILED.value, UpdateState.CANCELLED.value, UpdateState.OFFLINE.value):
                        return {"state": cur, "message": st.get("message") or st.get("error") or "Download failed"}
                    time.sleep(1)
                else:
                    return self._fail("Timeout waiting for download")
                if not path.exists():
                    return self._fail("Installer package missing after download")

        installed = current_version()
        self._set(UpdateState.BACKING_UP, message="Preparando instalación…")
        # Local/file manifests are used by E2E tests and support tooling, but
        # they must have exactly the same data-safety guarantees as GitHub
        # updates. Never skip the complete user-data backup for a local build.
        backup = create_backup(installed)
        state_store.set_state(UpdateState.BACKING_UP, backupPath=str(backup))

        # Hermes compatibility check
        if manifest.required_hermes:
            log.info("Required Hermes: %s", manifest.required_hermes)

        self._set(UpdateState.INSTALLING, message="Preparing installation…")

        updater_script = self._updater_script()
        if not updater_script.exists():
            return self._fail("VANOVA Updater not found")

        # Write job file for external updater
        job = {
            "installer": str(path),
            "version": manifest.version,
            "previousVersion": installed,
            "backupPath": str(backup),
            "appExe": self._installed_exe(),
        }
        job_file = data_dir() / "updates" / "pending-install.json"
        job_file.parent.mkdir(parents=True, exist_ok=True)
        job_file.write_text(json.dumps(job, indent=2), encoding="utf-8")

        self._set(UpdateState.RESTARTING, message="Reiniciando para instalar…", postInstallPending=True)
        state_store.append_history({
            "version": manifest.version,
            "status": "installing",
            "from": installed,
        })

        # Runtime spawns the external updater (Electron quit is optional — updater closes VANOVA).
        try:
            self._spawn_updater(updater_script, job_file)
        except Exception as exc:
            log.exception("Failed to spawn external updater")
            return self._fail(f"No se pudo iniciar el instalador: {exc}")

        self._emit("update.installing", {"version": manifest.version, "jobFile": str(job_file)})
        return state_store.load_state()

    def cancel(self) -> dict[str, Any]:
        self._cancel_requested = True
        return self._set(UpdateState.CANCELLED, message="Cancelled")

    def complete_post_install(self, success: bool, message: Optional[str] = None) -> dict[str, Any]:
        st = state_store.load_state()
        target = st.get("targetVersion", "")
        if success:
            state_store.append_history({
                "version": target,
                "status": "installed",
            })
            self.downloader.cleanup_version(target)
            result = self._set(
                UpdateState.COMPLETED,
                message=message or f"Actualizado a {target}",
                postInstallPending=False,
                targetVersion=None,
                manifest=None,
                packagePath=None,
                error=None,
            )
            self._emit("update.completed", result)
            return result
        backup = Path(st.get("backupPath") or "")
        self._set(UpdateState.ROLLBACK, message="Revirtiendo…")
        restored = restore_backup(backup) if backup.exists() else False
        state_store.append_history({
            "version": target,
            "status": "failed — rolled back" if restored else "failed",
        })
        return self._set(
            UpdateState.FAILED,
            message=message or (
                "La actualización falló. VANOVA restauró la versión anterior."
                if restored else "La actualización falló. Vuelve a intentarlo desde Ajustes."
            ),
            postInstallPending=False,
            error=message or "Install verification failed",
        )

    def startup_recovery(self) -> dict[str, Any]:
        st = state_store.load_state()
        if st.get("postInstallPending"):
            from ..updater import current_version
            from .semver import gte

            target = (st.get("targetVersion") or "").strip()
            installed = current_version()
            version_ok = bool(target) and gte(installed, target)
            if version_ok:
                return self.complete_post_install(
                    True,
                    message=f"Actualizado a {installed}",
                )

            job_file = data_dir() / "updates" / "pending-install.json"
            package = Path(st.get("packagePath") or "")
            if job_file.exists() and package.exists():
                return self._set(
                    UpdateState.READY_TO_INSTALL,
                    message="Instalación interrumpida — pulsa Instalar de nuevo",
                    postInstallPending=False,
                    error=None,
                )

            return self.complete_post_install(
                False,
                message=(
                    f"La instalación no aplicó la versión {target} "
                    f"(sigue en {installed}). Vuelve a descargar e instalar."
                ),
            )
        sf = state_file()
        if st.get("state") in (
            UpdateState.INSTALLING.value,
            UpdateState.RESTARTING.value,
            UpdateState.VERIFYING_INSTALL.value,
        ):
            return self._set(
                UpdateState.FAILED,
                message="Actualizacion incompleta — vuelve a intentarlo desde Ajustes",
                postInstallPending=False,
            )
        # Estados transitorios huérfanos: si VANOVA se cerró mientras una
        # comprobación/descarga/verificación estaba en curso, ningún hilo sigue
        # vivo al arrancar. Mantenerlos dejaría la UI en "Buscando
        # actualizaciones…" / "Descargando…" para siempre (spinner infinito en
        # Buscar actualizaciones reportado por el usuario). Se restablecen a
        # IDLE para que el usuario pueda reintentar desde Ajustes.
        if st.get("state") in (
            UpdateState.CHECKING.value,
            UpdateState.DOWNLOADING.value,
            UpdateState.VERIFYING.value,
            UpdateState.DOWNLOADED.value,
            UpdateState.BACKING_UP.value,
        ):
            return self._set(
                UpdateState.IDLE,
                targetVersion=None,
                message="La comprobación anterior quedó interrumpida. Pulsa Buscar actualizaciones.",
                postInstallPending=False,
            )
        return st

    def _pre_install_checks(self, path: Path, manifest: UpdateManifest) -> list[str]:
        issues = []
        if shutil.disk_usage(path.parent).free < max(manifest.size * 2, 500_000_000):
            issues.append("Insufficient disk space")
        return issues

    def _fail(self, message: str) -> dict[str, Any]:
        ui_message = message
        lower = message.lower()
        if "verification failed" in lower or "checksum" in lower:
            ui_message = "La verificación del paquete falló. Vuelve a descargar la actualización."
        elif "insufficient disk" in lower:
            ui_message = "Espacio en disco insuficiente para instalar la actualización."
        elif "not found" in lower and "package" in lower:
            ui_message = "No se encontró el instalador descargado. Pulsa Descargar de nuevo."
        elif "updater not found" in lower:
            ui_message = "No se encontró el script de actualización (vanova-updater.ps1)."
        result = self._set(UpdateState.FAILED, error=message, message=ui_message)
        self._emit("update.failed", result)
        return result

    def _updater_script(self) -> Path:
        import os
        resources = os.getenv("MAIOS_RESOURCES") or os.getenv("MAIOS_APP_ROOT", "")
        candidates = [
            Path(resources) / "desktop" / "updater" / "vanova-updater.ps1" if resources else None,
            app_root() / "desktop" / "updater" / "vanova-updater.ps1",
            Path(__file__).resolve().parent.parent.parent / "updater" / "vanova-updater.ps1",
        ]
        for c in candidates:
            if c and c.exists():
                return c
        return candidates[1]

    def _product_name(self) -> str:
        try:
            data = json.loads((app_root() / "version.json").read_text(encoding="utf-8-sig"))
            return str(data.get("productName") or "VANOVA")
        except Exception:  # noqa: BLE001
            return "VANOVA"

    def _installed_exe(self) -> str:
        env_exe = os.getenv("MAIOS_EXE") or os.getenv("MAIOS_APP_EXE")
        if env_exe and Path(env_exe).exists():
            return str(Path(env_exe).resolve())
        local = os.getenv("LOCALAPPDATA", "")
        default = Path(local) / "Programs" / "VANOVA" / "VANOVA.exe"
        if default.exists():
            return str(default)
        pf = os.getenv("ProgramFiles", "C:\\Program Files")
        alt = Path(pf) / "VANOVA" / "VANOVA.exe"
        if alt.exists():
            return str(alt)
        return str(default)

    def _resolve_local_path(self, url: str, state: Optional[dict[str, Any]] = None) -> Path:
        rel = url.replace("local:", "", 1).lstrip("/\\")
        candidates: list[Path] = [app_root() / rel]

        manifest_source = (state or {}).get("manifestSource") or self.provider.manifest_url
        if manifest_source.startswith("file://"):
            manifest_dir = UpdateManifestProvider._path_from_file_url(manifest_source).parent
            candidates.append(manifest_dir / Path(rel).name)
            candidates.append(manifest_dir.parent / rel)
        elif manifest_source.startswith("local:"):
            manifest_path = app_root() / manifest_source.replace("local:", "", 1).lstrip("/\\")
            candidates.append(manifest_path.parent / Path(rel).name)

        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate.resolve()) if candidate.exists() else str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists():
                return candidate.resolve()

        tried = ", ".join(str(c) for c in candidates)
        raise FileNotFoundError(f"Local package not found for {url} (tried: {tried})")

    def _spawn_updater(self, updater_script: Path, job_file: Path) -> None:
        logs = data_dir() / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        spawn_log = logs / "updater-spawn.log"
        updates_dir = data_dir() / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        launcher = updates_dir / "run-updater.cmd"

        if os.name == "nt":
            windir = os.environ.get("WINDIR", r"C:\Windows")
            ps_exe = Path(windir) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            if not ps_exe.exists():
                ps_exe = Path("powershell.exe")
            # Spawn PowerShell DIRECTLY with CREATE_NO_WINDOW — never via
            # `cmd /c start /MIN` (that flashes a console window on the client).
            cmd_line = (
                f'echo %DATE% %TIME% spawn>> "{spawn_log}"\r\n'
                f'"{ps_exe}" -NoProfile -NonInteractive -STA -ExecutionPolicy Bypass '
                f'-File "{updater_script}" -JobFile "{job_file}"\r\n'
                f'echo %DATE% %TIME% exit=%%ERRORLEVEL%%>> "{spawn_log}"\r\n'
            )
            launcher.write_text("@echo off\r\n" + cmd_line, encoding="utf-8")
            # NOTE: DETACHED_PROCESS (0x8) BREAKS the spawn — powershell.exe starts
            # but never executes the script (update never runs, UI stuck on
            # "Instalando actualización"). Only CREATE_NEW_PROCESS_GROUP |
            # CREATE_NO_WINDOW, which are enough to avoid any console flash.
            new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(
                [str(ps_exe), "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass",
                 "-File", str(updater_script), "-JobFile", str(job_file)],
                creationflags=new_group | no_window,
                close_fds=True,
                cwd=str(updater_script.parent),
            )
        else:
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy", "Bypass",
                    "-File", str(updater_script),
                    "-JobFile", str(job_file),
                ],
                start_new_session=True,
                close_fds=True,
            )
        log.info("Spawned external updater via launcher: %s", job_file)
