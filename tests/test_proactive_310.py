"""VANOVA 3.0.1 — PROACTIVE LAYER regression tests.

Covers:
* command_center snapshot exposes canonical period revenue (today/week/month/
  quarter/year/total) — UNKNOWN ≠ 0 (empty/not-yet-synced periods are None,
  never 0 €);
* company_model is refreshed after every organize (import) → persisted as
  in-memory business memory;
* /api/company/model is a protected sensitive-read endpoint (requires token);
* total == sum of months for the canonical engine (same validity gate).
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import business_model, command_center, runtime_security


def _mk_sales(*rows):
    return [
        {"id": f"S{i}", "total": total, "date": date}
        for i, (total, date) in enumerate(rows)
    ]


class CommandCenterRevenueTests(unittest.TestCase):
    def _snapshot(self, sales, insights=None):
        with patch("desktop.runtime.command_center.task_queue.list_tasks", return_value=[]):
            with patch("desktop.runtime.command_center.task_queue.get_queue_status", return_value={"queued": 0}):
                with patch("desktop.runtime.command_center.agent_architect.list_agents", return_value=[]):
                    with patch("desktop.runtime.command_center.approval_store.list_approvals", return_value=[]):
                        with patch(
                            "desktop.runtime.command_center.config_store.load",
                            return_value={
                                "lastScan": {"dataMode": "ready"},
                                "organizedSales": sales,
                            },
                        ):
                            with patch(
                                "desktop.runtime.insight_store.list_insights",
                                return_value=insights or [],
                            ):
                                return command_center.get_home_snapshot(force=True)

    def test_snapshot_exposes_revenue_periods(self):
        now = datetime.now(timezone.utc)
        month_key = now.strftime("%Y-%m")
        snap = self._snapshot(
            _mk_sales(
                (100.0, now.strftime("%Y-%m-%d")),
                (50.0, f"{month_key}-02"),
                (45.5, f"{month_key}-10"),
            )
        )
        periods = snap.get("revenuePeriods")
        self.assertIsInstance(periods, dict)
        for key in ("today", "week", "month", "quarter", "year", "total"):
            self.assertIn(key, periods)
        # Canonical engine: total == sum of the two valid month rows.
        self.assertEqual(periods["total"]["revenue"], 195.5)
        self.assertEqual(periods["total"]["orders"], 3)
        self.assertEqual(periods["month"]["revenue"], 195.5)
        self.assertEqual(periods["month"]["orders"], 3)

    def test_empty_sales_unknown_not_zero(self):
        snap = self._snapshot([])
        periods = snap.get("revenuePeriods") or {}
        total = periods.get("total") or {}
        # UNKNOWN ≠ 0: sin datos, revenue es None, jamás 0 €.
        self.assertIsNone(total.get("revenue"))
        self.assertIsNone(periods.get("month", {}).get("revenue"))
        self.assertFalse(periods.get("month", {}).get("comparable"))

    def test_previous_period_missing_is_not_invented(self):
        now = datetime.now(timezone.utc)
        month_key = now.strftime("%Y-%m")
        snap = self._snapshot(_mk_sales((80.0, f"{month_key}-05")))
        month = snap["revenuePeriods"]["month"]
        self.assertEqual(month["revenue"], 80.0)
        # Previous month has no rows → no fabricated % change.
        self.assertFalse(month["comparable"])
        self.assertIsNone(month["changePct"])

    def test_invalid_rows_excluded_from_revenue(self):
        now = datetime.now(timezone.utc)
        month_key = now.strftime("%Y-%m")
        snap = self._snapshot(
            _mk_sales(
                (100.0, f"{month_key}-01"),
                (-50.0, f"{month_key}-02"),  # negativo → inválida
                (0.0, "not-a-date"),  # fecha imposible → inválida
            )
        )
        total = snap["revenuePeriods"]["total"]
        self.assertEqual(total["revenue"], 100.0)
        self.assertEqual(total["orders"], 1)

    def test_proactive_insights_in_snapshot(self):
        snap = self._snapshot(
            [],
            insights=[
                {
                    "id": "ins-1",
                    "agentId": "pricing",
                    "agentName": "Pricing AI",
                    "kind": "opportunity",
                    "title": "Oportunidad de pricing",
                    "summary": "El producto X podría soportar una subida.",
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "status": "new",
                    "meta": {"impactEuro": 250.0},
                }
            ],
        )
        ins = snap.get("proactiveInsights") or []
        self.assertEqual(len(ins), 1)
        self.assertEqual(ins[0]["title"], "Oportunidad de pricing")
        self.assertEqual(ins[0]["impactEuro"], 250.0)


class CompanyModelWiringTests(unittest.TestCase):
    def test_refresh_persists_company_model(self):
        from desktop.runtime import company_model

        now = datetime.now(timezone.utc)
        month_key = now.strftime("%Y-%m")
        cfg = {
            "companyName": "Pruebas SL",
            "organizedSales": _mk_sales((120.0, f"{month_key}-03")),
            "organizedProducts": [{"sku": "P1", "name": "Producto 1", "rrp": 10.0}],
        }
        saved = {}

        def _fake_save(patch_dict):
            saved.update(patch_dict)

        with patch("desktop.runtime.config_store.load", return_value=cfg):
            with patch("desktop.runtime.config_store.save", side_effect=_fake_save):
                model = company_model.refresh(now=now)

        self.assertEqual(model["summary"]["revenue"], 120.0)
        self.assertIn("revenuePeriods", model)
        self.assertIn("dataAvailability", model)
        self.assertIn("dataMissing", model)
        self.assertTrue(saved.get("companyModel"))
        self.assertEqual(saved["companyModel"]["summary"]["revenue"], 120.0)

    def test_organize_refreshes_company_model(self):
        from desktop.runtime import file_organizer

        with patch.object(file_organizer.config_store, "load", return_value={}):
            with patch.object(file_organizer.config_store, "save") as mock_save:
                with patch.object(file_organizer, "sync_dashboard_overview") as mock_sync:
                    with patch("desktop.runtime.data_version.stamp_import") as mock_stamp:
                        with patch("desktop.runtime.detection_engine.run_detection",
                                   return_value={"findings": [], "counts": {"problems": 0}}):
                            result = file_organizer.organize_files([], trigger_hermes=False)

        self.assertTrue(result.get("ok"))
        # Guard: la importación nunca debe romper por la memoria.
        mock_save.assert_called()


class CompanyModelEndpointTests(unittest.TestCase):
    def test_endpoint_is_protected_read(self):
        self.assertIn("/api/company/model", runtime_security.SENSITIVE_READ_PATHS)


class CompanyModelLineItemsTests(unittest.TestCase):
    """VANOVA PROACTIVA — el modelo de empresa debe leer line_items (datos
    reales de tienda: el SKU vive solo en las líneas, no en la fila)."""

    def test_product_aggregation_from_line_items(self):
        from desktop.runtime import company_model

        sales = [
            {
                "id": "#1",
                "total": 40.0,
                "date": "2026-07-15",
                "customer": "Cliente A",
                "line_items": [
                    {"sku": "SKU-1", "price": 10.0, "quantity": 2},
                    {"sku": "SKU-2", "price": 20.0, "quantity": 1},
                ],
            },
            {
                "id": "#2",
                "total": 15.0,
                "date": "2026-07-16",
                "customer": "Cliente B",
                "line_items": [
                    {"sku": "SKU-1", "price": 5.0, "quantity": 1},
                ],
            },
        ]
        data = {
            "organizedSales": sales,
            "organizedProducts": [
                {"sku": "SKU-1", "name": "A", "rrp": 10.0, "cost": 5.0},
                {"sku": "SKU-2", "name": "B", "rrp": 20.0, "cost": 10.0},
            ],
            "businessFindings": [],
        }
        model = company_model.build_company_model(data)
        self.assertEqual(model["whatSells"]["productBasis"], "sales-with-sku")
        top = {t["sku"]: t for t in model["whatSells"]["topProducts"]}
        # SKU-1: 10*2 + 5*1 = 25 ; SKU-2: 20*1 = 20
        self.assertAlmostEqual(top["sku-1"]["revenue"], 25.0)
        self.assertAlmostEqual(top["sku-2"]["revenue"], 20.0)
        self.assertEqual(top["sku-1"]["orders"], 2)
        self.assertEqual(model["summary"]["customers"], 2)
        # Concentración por producto calculada desde líneas (no None)
        self.assertIsNotNone(model["concentration"]["products"]["topShare"])
        self.assertEqual(model["concentration"]["products"]["productsWithSales"], 2)
        # Sin SKU en fila NI en líneas → basis catalog-only, no inventa
        flat = [{"id": "#3", "total": 10.0, "date": "2026-07-17", "customer": "C"}]
        m2 = company_model.build_company_model({
            "organizedSales": flat,
            "organizedProducts": [{"sku": "X", "name": "X", "rrp": 5.0}],
            "businessFindings": [],
        })
        self.assertEqual(m2["whatSells"]["productBasis"], "catalog-only")
        self.assertEqual(m2["whatSells"]["topProducts"], [])

    def test_data_missing_not_claiming_missing_sku_when_line_items_have_sku(self):
        from desktop.runtime import company_model

        sales = [{
            "id": "#1",
            "total": 12.0,
            "date": "2026-07-15",
            "line_items": [{"sku": "SKU-A", "price": 12.0, "quantity": 1}],
        }]
        model = company_model.build_company_model({
            "organizedSales": sales,
            "organizedProducts": [{"sku": "SKU-A", "name": "A", "rrp": 12.0, "cost": 6.0}],
            "businessFindings": [],
        })
        self.assertFalse(any("no traen SKU" in m for m in model["dataMissing"]))


class FindingsToInsightsTests(unittest.TestCase):
    """VANOVA PROACTIVA — puente detection_engine → insights de usuario."""

    def _cfg(self):
        return {
            "organizedSales": [
                {"id": "#1", "total": 30.0, "date": "2026-07-15"},
                {"id": "#2", "total": 10.0, "date": "2026-07-16"},
                {"id": "#3", "total": 20.0, "date": "2026-07-17"},
            ],
            "organizedProducts": [
                {"sku": "SKU-1", "name": "A", "rrp": 10.0, "cost": 5.0},
                {"sku": "SKU-2", "name": "B", "rrp": 20.0, "cost": 10.0},
                {"sku": "SKU-3", "name": "C", "rrp": 5.0},
            ],
            "organizedCustomers": [],
            "organizedInvoices": [],
            "organizedSuppliers": [],
            "businessFindings": [],
            "insights": [],
        }

    def test_findings_become_insights_with_evidence(self):
        from desktop.runtime import detection_engine, insight_store

        with patch("desktop.runtime.insight_store.config_store.load", return_value=self._cfg()):
            with patch("desktop.runtime.insight_store.config_store.save") as mock_save:
                res = detection_engine.run_detection(self._cfg(), persist=False)
                result = insight_store.sync_from_findings(res["findings"])
        self.assertGreater(result["created"], 0)
        # El insight lleva evidencia y acción (no texto genérico)
        saved_meta = None
        for call in mock_save.call_args_list:
            payload = call.args[0] if call.args else call.kwargs.get("data", {})
            if isinstance(payload, dict) and payload.get("insights"):
                for item in payload["insights"]:
                    if item.get("kind") == "finding":
                        saved_meta = item.get("meta") or {}
                        self.assertTrue(item.get("summary"))
                        self.assertTrue(saved_meta.get("evidence"))
                        self.assertTrue(saved_meta.get("recommendedAction"))
                        break
        self.assertIsNotNone(saved_meta)
        self.assertEqual(saved_meta.get("source"), "detection_engine")

    def test_insights_dedup_by_finding_signature(self):
        from desktop.runtime import detection_engine, insight_store

        cfg = self._cfg()
        captured = {}

        def fake_save(data):
            if isinstance(data, dict) and data.get("insights") is not None:
                captured["insights"] = data["insights"]

        def fake_load():
            return {
                **cfg,
                "insights": captured.get("insights", cfg.get("insights", [])),
            }

        with patch("desktop.runtime.insight_store.config_store.load", side_effect=fake_load):
            with patch("desktop.runtime.insight_store.config_store.save", side_effect=fake_save):
                res = detection_engine.run_detection(cfg, persist=False)
                result1 = insight_store.sync_from_findings(res["findings"])
        self.assertGreater(result1["created"], 0)
        self.assertGreater(len(captured.get("insights") or []), 0)

        # Segundo análisis con los mismos datos → 0 creados (dedup por firma)
        with patch("desktop.runtime.insight_store.config_store.load", side_effect=fake_load):
            with patch("desktop.runtime.insight_store.config_store.save", side_effect=fake_save):
                res2 = detection_engine.run_detection(cfg, persist=False)
                result2 = insight_store.sync_from_findings(res2["findings"])
        self.assertEqual(result2["created"], 0)
        self.assertGreaterEqual(result2["updated"], 1)

    def test_insight_lifecycle_resolved_and_reactivated(self):
        from desktop.runtime import detection_engine, insight_store

        cfg = self._cfg()
        res = detection_engine.run_detection(cfg, persist=False)
        sigs = {f.get("type"): f.get("signature") for f in res["findings"]}
        self.assertIn("missing_cost", sigs)
        missing_sig = sigs["missing_cost"]

        captured = {}

        def fake_save(data):
            if isinstance(data, dict) and data.get("insights") is not None:
                captured["insights"] = data["insights"]

        def fake_load():
            return {
                **cfg,
                "insights": captured.get("insights", cfg.get("insights", [])),
            }

        # 1) sync completo → insight new
        with patch("desktop.runtime.insight_store.config_store.load", side_effect=fake_load):
            with patch("desktop.runtime.insight_store.config_store.save", side_effect=fake_save):
                insight_store.sync_from_findings(res["findings"])
        st = [i for i in captured["insights"] if (i.get("meta") or {}).get("findingSignature") == missing_sig]
        self.assertTrue(st and st[0]["status"] in ("new",))

        # 2) el finding desaparece → insight resolved
        without = [f for f in res["findings"] if f.get("type") != "missing_cost"]
        with patch("desktop.runtime.insight_store.config_store.load", side_effect=fake_load):
            with patch("desktop.runtime.insight_store.config_store.save", side_effect=fake_save):
                insight_store.sync_from_findings(without)
        st = [i for i in captured["insights"] if (i.get("meta") or {}).get("findingSignature") == missing_sig]
        self.assertTrue(st and st[0]["status"] == "resolved")

        # 3) reaparece → vuelve a new (nueva evidencia)
        with patch("desktop.runtime.insight_store.config_store.load", side_effect=fake_load):
            with patch("desktop.runtime.insight_store.config_store.save", side_effect=fake_save):
                insight_store.sync_from_findings(res["findings"])
        st = [i for i in captured["insights"] if (i.get("meta") or {}).get("findingSignature") == missing_sig]
        self.assertTrue(st and st[0]["status"] == "new")

    def test_no_findings_no_insights(self):
        from desktop.runtime import insight_store

        with patch("desktop.runtime.insight_store.config_store.load", return_value=self._cfg()):
            with patch("desktop.runtime.insight_store.config_store.save") as mock_save:
                result = insight_store.sync_from_findings([])
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["active"], 0)
        self.assertFalse(any(
            (call.args[0] if call.args else {}).get("insights")
            for call in mock_save.call_args_list
        ))


class OrganizeRunsProactiveAnalysisTests(unittest.TestCase):
    def test_organize_runs_detection_and_syncs_insights(self):
        from desktop.runtime import file_organizer

        with patch.object(file_organizer.config_store, "load", return_value={}):
            with patch.object(file_organizer.config_store, "save"):
                with patch.object(file_organizer, "sync_dashboard_overview"):
                    with patch("desktop.runtime.data_version.stamp_import"):
                        with patch("desktop.runtime.company_model.refresh"):
                            with patch("desktop.runtime.detection_engine.run_detection",
                                       return_value={
                                           "findings": [{"id": "f1", "signature": "s1", "type": "missing_cost",
                                                         "category": "problem", "status": "new",
                                                         "title": "Productos sin coste", "observation": "x",
                                                         "evidence": ["e"], "recommendedAction": "a"}],
                                           "counts": {"problems": 1},
                                       }):
                                with patch("desktop.runtime.insight_store.sync_from_findings") as mock_sync:
                                    result = file_organizer.organize_files([], trigger_hermes=False)
        self.assertTrue(result.get("ok"))
        mock_sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
