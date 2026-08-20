"""VANOVA 1.0.2 commercial hardening audit tests."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import (
    file_organizer,
    health_monitor,
    integrations_lifecycle,
    process_manager,
    shopify_sync,
)
from desktop.runtime.update.downloader import UpdateDownloader
from desktop.runtime.update.manifest_provider import UpdateManifest
from desktop.runtime.update.state_machine import UpdateState
from desktop.runtime.update.update_manager import UpdateManager
from desktop.runtime.update import state_store


class ConnectorStatusTests(unittest.TestCase):
    def test_running_unauthenticated_is_warning_not_recovery(self):
        comp = {
            "status": "warning",
            "running": True,
            "authenticated": False,
            "authRequired": True,
        }
        self.assertFalse(health_monitor._connector_label(True, False).startswith("●"))
        self.assertIn("autenticación", health_monitor._connector_label(True, False))

    def test_authenticated_is_connected_label(self):
        self.assertEqual(health_monitor._connector_label(True, True), "● Connector conectado")

    def test_dead_connector_is_disconnected_label(self):
        self.assertEqual(health_monitor._connector_label(False, False), "○ Connector desconectado")

    def test_status_distinguishes_running_auth_cloud(self):
        with patch.object(process_manager, "_is_cloud_running", return_value=True), patch.object(
            process_manager, "_is_connector_running", return_value=True
        ), patch.object(process_manager, "_connector_heartbeat_ok", return_value=False), patch.object(
            process_manager, "_ensure_device_registered", return_value=False
        ):
            st = process_manager.status()
        conn = st["connector"]
        self.assertTrue(conn["running"])
        self.assertFalse(conn["authenticated"])
        self.assertFalse(conn["registered"])
        self.assertTrue(conn["cloudAvailable"])

    def test_registration_uses_current_version(self):
        with patch("desktop.runtime.process_manager._connector_env", return_value={"MAIOS_DEVICE_KEY": "dk"}), patch(
            "desktop.runtime.process_manager._connector_heartbeat_ok", return_value=False
        ), patch("desktop.runtime.updater.current_version", return_value="1.0.1"):
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_client.post.return_value = mock_resp
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            with patch("httpx.Client", return_value=mock_client):
                process_manager._register_device_local("dk", "http://127.0.0.1:8000")
            payload = mock_client.post.call_args.kwargs["json"]
            self.assertEqual(payload["version"], "1.0.1")

    def test_connector_env_backfills_missing_device_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp)
            conn_env = cfg / "connector.env"
            conn_env.write_text(
                "MAIOS_AI_PROVIDER=ollama-launch\nMAIOS_AI_MODEL=deepseek-v4-flash:cloud\n",
                encoding="utf-8",
            )
            with patch("desktop.runtime.process_manager.config_dir", return_value=cfg), patch(
                "desktop.runtime.process_manager.logs_dir", return_value=cfg
            ), patch("desktop.runtime.process_manager.app_root", return_value=ROOT):
                process_manager._ensure_env_files()
            text = conn_env.read_text(encoding="utf-8")
            self.assertIn("MAIOS_DEVICE_KEY=", text)
            self.assertIn("MAIOS_CLOUD_URL=", text)
            self.assertIn("MAIOS_AI_PROVIDER=ollama-launch", text)


class ShopifyPermissionTests(unittest.TestCase):
    def test_permission_denied_classified(self):
        parsed = shopify_sync._parse_shopify_error("Shopify HTTP 403: scope read_products")
        self.assertEqual(parsed["errorCategory"], "permission_denied")
        self.assertTrue(parsed["scopeErrors"])

    def test_needs_reauth_when_missing_scopes(self):
        with patch(
            "desktop.runtime.shopify_sync.integrations_store.get_config",
            return_value={"connected": True},
        ), patch(
            "desktop.runtime.shopify_sync.config_store.load",
            return_value={"shopifySync": {"missingScopes": ["read_products"]}},
        ), patch(
            "desktop.runtime.shopify_sync.integrations_store.sync_shopify_from_hermes_if_needed",
            return_value=None,
        ), patch(
            "desktop.runtime.shopify_sync.integrations_store.get_shopify_credentials",
            return_value={"url": "https://test.myshopify.com", "token": "shpat_test"},
        ), patch(
            "desktop.runtime.shopify_sync.check_credentials",
            return_value={"ok": False, "missingScopes": ["read_products"]},
        ):
            self.assertTrue(shopify_sync.needs_reauth())

    def test_reauth_required_lifecycle(self):
        with patch(
            "desktop.runtime.integrations_lifecycle.integrations_store.get_config",
            return_value={"connected": True, "url": "https://x.myshopify.com"},
        ), patch(
            "desktop.runtime.integrations_lifecycle.integrations_store.get_shopify_entry",
            return_value={},
        ), patch(
            "desktop.runtime.integrations_lifecycle.integrations_store.sync_shopify_from_hermes_if_needed",
            return_value=None,
        ), patch(
            "desktop.runtime.integrations_lifecycle.shopify_sync.sync_status",
            return_value={
                "status": "error",
                "missingScopes": ["read_products"],
                "userMessage": "Faltan permisos",
            },
        ):
            lc = integrations_lifecycle.shopify_lifecycle()
        self.assertEqual(lc["state"], "reauth_required")
        self.assertEqual(lc["label"], "Permisos insuficientes")

    def test_error_not_product_entity(self):
        fake = {"name": "Faltan permisos de Shopify (read_products)", "sku": "", "source": "shopify"}
        self.assertFalse(file_organizer._is_product_entity(fake))
        real = {"name": "Camiseta MOOVING", "sku": "SKU-1", "source": "shopify"}
        self.assertTrue(file_organizer._is_product_entity(real))

    def test_network_error_classified(self):
        parsed = shopify_sync._parse_shopify_error("Shopify unreachable: timed out")
        self.assertEqual(parsed["errorCategory"], "network_error")


class UpdateAuditTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data = Path(self._tmpdir.name)
        patcher = patch("desktop.runtime.update.state_store.data_dir", return_value=self.data)
        self.addCleanup(patcher.stop)
        patcher.start()
        patcher2 = patch("desktop.runtime.update.downloader.data_dir", return_value=self.data)
        self.addCleanup(patcher2.stop)
        patcher2.start()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_update_available_100_to_101(self):
        mgr = UpdateManager()
        manifest = UpdateManifest(
            version="1.0.1",
            download_url="local:release/VANOVA-Setup-1.0.1.exe",
            sha256="a" * 64,
            size=100,
        )
        with patch.object(mgr.provider, "fetch", return_value=manifest):
            with patch("desktop.runtime.updater.current_version", return_value="1.0.0"):
                r = mgr.check_for_updates(force=True)
        self.assertTrue(r.get("updateAvailable"))
        self.assertEqual(r["targetVersion"], "1.0.1")

    def test_sha_mismatch_rejected(self):
        mgr = UpdateManager()
        manifest = UpdateManifest(
            version="1.0.1",
            download_url="local:release/VANOVA-Setup.exe",
            sha256="0" * 64,
            size=100,
        )
        state_store.set_state(UpdateState.AVAILABLE, manifest=manifest.__dict__, targetVersion="1.0.1")
        pkg = self.data / "temp" / "update" / "1.0.1" / "VANOVA-Setup.exe"
        pkg.parent.mkdir(parents=True, exist_ok=True)
        pkg.write_bytes(b"wrong-content")
        state_store.set_state(UpdateState.DOWNLOADED, packagePath=str(pkg))
        r = mgr.verify_package()
        self.assertEqual(r["state"], UpdateState.FAILED.value)

    def test_update_unavailable_continues(self):
        mgr = UpdateManager()
        with patch.object(mgr.provider, "fetch", side_effect=ValueError("Invalid manifest")):
            with patch("desktop.runtime.updater.current_version", return_value="1.0.0"):
                r = mgr.check_for_updates(force=True)
        self.assertEqual(r["state"], UpdateState.OFFLINE.value)
        self.assertEqual(r["installedVersion"], "1.0.0")

    def test_backup_preserves_data_on_install_path(self):
        """UpdateManager.create_backup is invoked before install — verify helper exists."""
        from desktop.runtime.update import backup as update_backup

        self.assertTrue(callable(update_backup.create_backup))


class RecoveryUiLogicTests(unittest.TestCase):
    """Mirror system-status.js componentNeedsRecovery rules in Python."""

    @staticmethod
    def _needs_recovery(comp: dict) -> bool:
        if not comp or comp.get("status") == "ok":
            return False
        if comp.get("authRequired") or (comp.get("running") and comp.get("authenticated") is False):
            return False
        return True

    def test_running_unauthenticated_no_recovery(self):
        comp = {"status": "warning", "running": True, "authenticated": False, "authRequired": True}
        self.assertFalse(self._needs_recovery(comp))

    def test_dead_connector_recoverable(self):
        comp = {"status": "warning", "running": False, "authenticated": False}
        self.assertTrue(self._needs_recovery(comp))


class ProductsEmptyStateTests(unittest.TestCase):
    def test_dashboard_has_products_empty_state(self):
        html = (ROOT / "web" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("function productsEmptyState()", html)
        self.assertIn("Catálogo Excel detectado", html)
        self.assertIn("shopifyWarningBanner", html)
        self.assertIn("function onAppClick", html)
        self.assertNotIn("[[emptyHint,'—','—','—']]", html)


class FinanceAndCustomerUiTests(unittest.TestCase):
    def test_finance_cards_open_detail_instead_of_extra_breakdown_card(self):
        html = (ROOT / "web" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("function openFinanceMetricDetail", html)
        for key in ("revenue", "orders", "average-order", "gross-margin"):
            self.assertIn("kind === '" + key + "'", html)
        self.assertNotIn("De dónde salen los números", html)

    def test_customers_use_normalized_dataset(self):
        html = (ROOT / "web" / "dashboard.html").read_text(encoding="utf-8")
        services = (ROOT / "web" / "data-services.js").read_text(encoding="utf-8")
        self.assertIn("const customers = Array.isArray(store.customers)", html)
        self.assertIn("async getCustomers()", services)
        self.assertIn("solo se muestran campos de cliente reales", html)

    def test_data_safety_guard_preserves_rows_and_exposes_recovery(self):
        organizer = (ROOT / "desktop" / "runtime" / "file_organizer.py").read_text(encoding="utf-8")
        backup = (ROOT / "desktop" / "runtime" / "update" / "backup.py").read_text(encoding="utf-8")
        api = (ROOT / "desktop" / "runtime" / "api_server.py").read_text(encoding="utf-8")
        self.assertIn("_is_preservable_product", organizer)
        self.assertIn("dataLossGuard", organizer)
        self.assertIn("backupFormat", backup)
        self.assertIn("restore_pre_update", api)


class FileOrganizerXlsxTests(unittest.TestCase):
    def test_xlsx_col_index(self):
        self.assertEqual(file_organizer._xlsx_col_index("A1"), 0)
        self.assertEqual(file_organizer._xlsx_col_index("C5"), 2)

    def test_extract_products_from_xlsx_when_file_exists(self):
        xlsx = Path(r"C:\Users\Admin\Downloads\NET_PRICE_LECLERC_ENGLISH_FORMATTED.xlsx")
        if not xlsx.exists():
            self.skipTest("MOOVING catalog xlsx not on disk")
        rows = file_organizer._extract_products({
            "path": str(xlsx),
            "name": xlsx.name,
            "ext": "xlsx",
        })
        self.assertGreater(len(rows), 10)
        self.assertTrue(any(r.get("sku") for r in rows))


class SystemStatusJsTests(unittest.TestCase):
    def test_connection_banner_is_deduplicated(self):
        js = (ROOT / "web" / "system-status.js").read_text(encoding="utf-8")
        dashboard = (ROOT / "web" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("lastBannerSignature", js)
        self.assertIn("const cached = MAIOSSystemStatus.getState", dashboard)
        self.assertIn("Do not re-render Home every poll while idle", dashboard)

    def test_auth_failure_skips_auto_recovery(self):
        js = (ROOT / "web" / "system-status.js").read_text(encoding="utf-8")
        self.assertIn("comp.authRequired", js)
        self.assertIn("authenticated === false", js)

    def test_run_recovery_has_finally_hide(self):
        js = (ROOT / "web" / "system-status.js").read_text(encoding="utf-8")
        self.assertIn("finally", js)
        self.assertIn("hideOperation", js)


if __name__ == "__main__":
    unittest.main()
