"""Tests for business scanner dashboard snapshot."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from desktop.runtime.business_scanner import (
    add_imported_file,
    build_dashboard_snapshot,
    list_imported_files,
    remove_imported_file,
)
from desktop.runtime.company_profile import CompanyProfile


class BusinessScannerTests(unittest.TestCase):
    def test_build_snapshot_uses_real_mode_with_files(self):
        profile = CompanyProfile(identity={"name": "Test Co", "slug": "test-co"})
        files = [{"path": "/a.csv", "name": "a.csv", "ext": "csv", "size": 100, "modified": "2026-01-01T00:00:00Z"}]
        integrations = [{"id": "files", "name": "Archivos", "status": "connected", "source": "local", "recordCount": 1, "dataMode": "real"}]
        snapshot = build_dashboard_snapshot(
            system={"hardware": {"diskFreeGb": 50, "ramGb": 16}},
            profile=profile,
            files=files,
            integrations=integrations,
            agents=[],
            recommendations=[{"name": "Marketing Agent", "reason": "Start here"}],
        )
        self.assertEqual(snapshot["dataMode"], "real")
        self.assertEqual(snapshot["overview"]["filesScanned"], 1)
        self.assertTrue(snapshot["priorities"])
        self.assertTrue(snapshot["setupProgress"]["scanComplete"])

    def test_build_snapshot_partial_without_files(self):
        profile = CompanyProfile()
        snapshot = build_dashboard_snapshot(
            system={"hardware": {"diskFreeGb": 10, "ramGb": 8}},
            profile=profile,
            files=[],
            integrations=[],
            agents=[],
            recommendations=[],
        )
        self.assertEqual(snapshot["dataMode"], "partial")

    def test_imported_files_roundtrip(self):
        stored = {"scanFiles": []}
        # BUG-017: add/remove_imported_file usan config_store.update() (RMW
        # atómico). El side_effect aplica el mutator al dict stored, igual que
        # haría update() real.
        with patch("desktop.runtime.config_store.load", return_value=stored), patch(
            "desktop.runtime.config_store.update", side_effect=lambda mutator: mutator(stored)
        ), patch("desktop.runtime.config_store.save", side_effect=lambda data: stored.update(data)), patch(
            "desktop.runtime.file_organizer.organize_files"
        ):
            added = add_imported_file({"name": "catalogo.xlsx", "ext": "xlsx", "size": 2048, "path": "catalogo.xlsx"})
            self.assertTrue(added["ok"])
            self.assertEqual(added["file"]["name"], "catalogo.xlsx")
            listing = list_imported_files()
            self.assertEqual(listing["count"], 1)
            removed = remove_imported_file("catalogo.xlsx")
            self.assertTrue(removed["ok"])
            self.assertEqual(list_imported_files()["count"], 0)

    def test_scan_results_do_not_clobber_synced_overview(self):
        """H2: a scan must only record metadata; the synced business overview
        (written by sync_dashboard_overview) is the single source of truth."""
        from desktop.runtime import business_scanner

        synced = {
            "overview": {"orders": 99, "revenue": 12345.0, "customers": 12, "productsOrganized": 461},
            "dataMode": "real",
            "fetchedAt": "2026-08-16T10:00:00Z",
        }
        scan_snapshot = {
            "dataMode": "scan",
            "overview": {"orders": 3, "revenue": 500.0, "filesScanned": 2, "integrationsDetected": 0},
        }
        stored: dict = {"dashboardSnapshot": dict(synced)}
        with patch("desktop.runtime.config_store.load", return_value=stored), patch(
            "desktop.runtime.config_store.save", side_effect=lambda data: stored.update(data)
        ):
            business_scanner.save_scan_results(scan_snapshot)
        snap = stored["dashboardSnapshot"]
        # Synced business metrics are preserved, not replaced by scan estimates
        self.assertEqual(snap["overview"]["orders"], 99)
        self.assertEqual(snap["overview"]["revenue"], 12345.0)
        self.assertEqual(snap["overview"]["customers"], 12)
        self.assertEqual(snap["dataMode"], "real")
        # Scan metadata is recorded
        self.assertEqual(snap["lastScan"]["fileCount"], 2)
        self.assertEqual(snap["lastScan"]["completedAt"], stored["lastScan"]["completedAt"])

    def test_scan_seeds_overview_when_none_exists(self):
        """H2: on a brand-new install (no sync yet) the scan may seed the
        overview so the dashboard is never empty."""
        from desktop.runtime import business_scanner

        scan_snapshot = {
            "dataMode": "real",
            "overview": {"orders": 0, "revenue": None, "filesScanned": 2, "integrationsDetected": 1},
        }
        stored: dict = {}
        with patch("desktop.runtime.config_store.load", return_value=stored), patch(
            "desktop.runtime.config_store.save", side_effect=lambda data: stored.update(data)
        ):
            business_scanner.save_scan_results(scan_snapshot)
        snap = stored["dashboardSnapshot"]
        self.assertEqual(snap["overview"]["filesScanned"], 2)
        self.assertEqual(snap["lastScan"]["fileCount"], 2)


if __name__ == "__main__":
    unittest.main()
