"""VANOVA Desktop Runtime launcher — started by Electron main process."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Ensure runtime package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from desktop.runtime.api_server import start_server
from desktop.runtime.logger import get_logger
from desktop.runtime import updater, install_secrets

log = get_logger("maios.launcher", "launcher")


def _startup_tasks():
    import threading
    import time

    # Persisted chat records outlive the runtime, but their worker threads do
    # not. Recover them before the UI starts polling so an interrupted Hermes
    # request cannot make the whole runtime appear unavailable.
    try:
        from desktop.runtime import hermes_chat

        recovered = hermes_chat.recover_orphaned_requests(max_age_seconds=0.0)
        if recovered:
            log.warning("Recovered %d interrupted Hermes request(s) at startup", recovered)
    except Exception as exc:
        log.warning("Hermes request recovery unavailable: %s", exc)

    def hermes_warm():
        time.sleep(0.8)
        try:
            from desktop.runtime import hermes_chat, hermes_service

            hermes_service.ensure_ollama_launch()
            hermes_service.start_warm_pool()
            hermes_chat.warm_chat()
            log.info("Hermes pre-warm complete")
        except Exception as exc:
            log.warning("Hermes pre-warm unavailable: %s", exc)

    threading.Thread(target=hermes_warm, name="maios-hermes-prewarm", daemon=True).start()

    def organize_startup():
        time.sleep(5)
        try:
            from desktop.runtime import config_store, file_organizer

            data = config_store.load()
            files = data.get("scanFiles") or []
            org = data.get("fileOrganization") or {}
            if files and org.get("status") != "running":
                file_organizer.organize_files(trigger_hermes=False)
                log.info("Startup file organization complete (%d files)", len(files))
        except Exception as exc:
            log.warning("Startup organize skipped: %s", exc)

    threading.Thread(target=organize_startup, name="maios-organize-startup", daemon=True).start()

    def run():
        time.sleep(3)
        try:
            result = updater.startup_recovery()
            log.info("Update startup recovery: %s", result.get("state"))
        except Exception as exc:
            log.warning("Update startup recovery failed: %s", exc)

    threading.Thread(target=run, daemon=True).start()

    def governance_startup():
        # FASE 14 — DATA MIGRATION & INTEGRITY PROTOCOL: al arrancar se detecta
        # si la versión del esquema de datos es anterior a la actual y, en ese
        # caso, se ejecuta el protocolo (backup → auditar → marcar legacy →
        # revalidar → reporte). Nunca borra datos; marca y explica.
        time.sleep(6)
        try:
            from desktop.runtime import data_governance

            result = data_governance.run_migration_protocol()
            log.info(
                "Data governance: %s (schema %s → %s, status %s)",
                result.get("status"),
                result.get("fromSchemaVersion", "?"),
                result.get("toSchemaVersion", "?"),
                result.get("integrity", "n/a"),
            )
        except Exception as exc:
            log.warning("Data governance startup failed: %s", exc)

    threading.Thread(target=governance_startup, name="maios-governance-startup", daemon=True).start()

    def shopify_loop():
        time.sleep(4)
        try:
            from desktop.runtime import integrations_store, shopify_sync

            bridge = integrations_store.sync_shopify_from_hermes_if_needed()
            if bridge and bridge.get("imported"):
                log.info("Shopify credentials bridged from Hermes .env")
            shopify_sync.start_background_sync()
        except Exception as exc:
            log.warning("Shopify background sync unavailable: %s", exc)

    threading.Thread(target=shopify_loop, daemon=True).start()

    def facturascript_loop():
        time.sleep(6)
        try:
            from desktop.runtime import facturascripts_sync

            facturascripts_sync.start_background_sync()
        except Exception as exc:
            log.warning("FacturaScript background sync unavailable: %s", exc)

    threading.Thread(target=facturascript_loop, name="maios-facturascript-sync-start", daemon=True).start()

    def gmail_skill_loop():
        time.sleep(4)
        try:
            from desktop.runtime import gmail_skill_bridge

            result = gmail_skill_bridge.sync_from_integrations_store()
            if result.get("ok"):
                log.info("Gmail skill provisioned at startup: %s", result.get("detail"))
            elif result.get("error"):
                log.info("Gmail skill not provisioned at startup: %s", result.get("error"))
        except Exception as exc:
            log.warning("Gmail skill startup sync unavailable: %s", exc)

    threading.Thread(target=gmail_skill_loop, daemon=True).start()

    def services_bootstrap():
        time.sleep(2)
        try:
            from desktop.runtime import process_manager

            result = process_manager.ensure_services()
            log.info("Services bootstrap: cloud=%s connector=%s", result.get("cloud"), result.get("connector"))
        except Exception as exc:
            log.warning("Services bootstrap unavailable: %s", exc)

    threading.Thread(target=services_bootstrap, name="maios-services-bootstrap", daemon=True).start()

    def start_cloud_supervisor():
        """BUG-063: launch an EXTERNAL, DETACHED supervisor for the cloud.

        The in-process watchdog (health_watchdog below) dies with the runtime.
        If the runtime also dies, nothing relaunches the cloud. Spawn a separate
        detached process that survives the runtime's death and independently
        watches cloud (:8000) + runtime (:8765), relaunching whichever is down.
        """
        try:
            from desktop.runtime import cloud_supervisor
            from desktop.runtime.paths import python_executable

            py = str(python_executable())
            script = Path(cloud_supervisor.__file__)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent.parent)
            subprocess.Popen(
                [py, str(script)],
                cwd=str(Path(__file__).resolve().parent.parent.parent),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                if os.name == "nt" else 0,
            )
            log.info("Cloud supervisor spawned (detached)")
        except Exception as exc:
            log.warning("Cloud supervisor spawn failed: %s", exc)

    threading.Thread(target=start_cloud_supervisor, name="maios-cloud-supervisor", daemon=True).start()

    def health_watchdog():
        time.sleep(10)
        while True:
            try:
                from desktop.runtime import health_monitor, shopify_sync

                health_monitor.watchdog_tick()
                shopify_sync.ensure_background_sync()
            except Exception as exc:
                log.debug("Health watchdog tick: %s", exc)
            time.sleep(15)

    threading.Thread(target=health_watchdog, name="maios-health-watchdog", daemon=True).start()

    def backup_startup():
        # Snapshot user data before the delayed startup organizer can migrate
        # or classify anything. This is the last line of defense if a future
        # migration is buggy.
        time.sleep(2)
        try:
            from desktop.runtime import backup_service

            backup_service.maybe_startup_backup()
        except Exception as exc:
            log.warning("Startup backup unavailable: %s", exc)

    threading.Thread(target=backup_startup, name="maios-backup-startup", daemon=True).start()


def main():
    log.info("VANOVA Desktop Runtime starting")
    install_secrets.ensure_install_secrets()
    try:
        server = start_server()
    except RuntimeError as exc:
        log.error("Failed to start runtime API: %s", exc)
        sys.exit(1)
    _startup_tasks()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Runtime shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
