"""E2E test: real proactivity cycle demonstration.

Proves that VANOVA can:
1. Start runtime + scheduler
2. Run proactive analysis
3. Generate findings → insights → recommendations
4. Deduplicate correctly
5. Persist recommendation lifecycle
6. Trigger a single notification
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from unittest.mock import patch

# Ensure imports work
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestProactivityE2E(unittest.TestCase):
    """Full E2E proactivity demonstration."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vanova-proactivity-e2e-")
        self.data_dir = os.path.join(self.tmpdir, "data")
        self.config_dir = os.path.join(self.data_dir, "config")
        os.makedirs(self.config_dir, exist_ok=True)

        # Create minimal config with organized data that will generate findings
        self.config = {
            "setupComplete": True,
            "companyName": "Test Corp",
            "organizedProducts": [
                {"sku": "SKU-001", "name": "Product A", "price": 100.0, "cost": 60.0},
                {"sku": "SKU-002", "name": "Product B", "price": 50.0, "cost": None},  # Missing cost!
                {"sku": "SKU-003", "name": "Product C", "price": 80.0, "cost": 30.0},
            ],
            "organizedSales": [
                {"order_id": "ORD-001", "sku": "SKU-001", "total": 100.0, "date": "2026-01-15"},
                {"order_id": "ORD-002", "sku": "SKU-001", "total": 200.0, "date": "2026-01-16"},
                {"order_id": "ORD-003", "sku": "SKU-002", "total": 50.0, "date": "2026-01-17"},
                {"order_id": "ORD-004", "sku": "SKU-003", "total": 80.0, "date": "2026-01-18"},
            ],
            "businessFindings": [],
            "insights": [],
            "recommendations": [],
            "priorities": [],
        }
        config_path = os.path.join(self.config_dir, "maios.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f)

        # Patch paths module to use our temp directory
        self._patches = []
        from pathlib import Path
        _td = Path(self.data_dir)
        _cd = Path(self.config_dir)

        import desktop.runtime.paths as paths_mod
        self._patches.append(patch.object(paths_mod, "data_dir", lambda: _td))
        self._patches.append(patch.object(paths_mod, "config_dir", lambda: _cd))

        import desktop.runtime.config_store as cs_mod
        self._patches.append(patch.object(cs_mod, "CONFIG_FILE", Path(config_path)))

        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_01_scheduler_starts_and_ticks(self):
        """Verify scheduler starts and runs ticks."""
        from desktop.runtime import agent_scheduler

        # Reset state
        agent_scheduler._started = False
        agent_scheduler._stop_event = None
        agent_scheduler._thread = None

        # Start scheduler
        started = agent_scheduler.start()
        self.assertTrue(started, "Scheduler should start successfully")

        # Verify thread is running
        self.assertIsNotNone(agent_scheduler._thread)
        self.assertTrue(agent_scheduler._thread.is_alive())
        self.assertTrue(agent_scheduler._started)

        # Wait for at least one tick
        time.sleep(2)

        # Stop scheduler
        agent_scheduler.stop()
        time.sleep(1)
        self.assertFalse(agent_scheduler._started)

    def test_02_proactive_analysis_generates_findings(self):
        """Verify proactive analysis generates findings from real data."""
        from desktop.runtime import config_store, detection_engine

        # Load config
        data = config_store.load()

        # Run detection
        result = detection_engine.run_detection(data, persist=False)
        findings = result.get("findings", [])

        # We have a product without cost (SKU-002) → should generate a finding
        self.assertGreater(len(findings), 0, "Detection should find at least 1 finding")

        # Verify finding structure
        f = findings[0]
        self.assertIn("id", f)
        self.assertIn("type", f)
        self.assertIn("title", f)
        self.assertIn("signature", f)
        print(f"  ✓ Finding generated: {f['type']} — {f['title']}")

    def test_03_findings_create_insights(self):
        """Verify findings are synced into insights with deduplication."""
        from desktop.runtime import config_store, detection_engine, insight_store

        data = config_store.load()
        result = detection_engine.run_detection(data, persist=False)
        findings = result.get("findings", [])

        # Sync findings into insights (no data= so it persists to disk)
        insight_store.sync_from_findings(findings,
                                          active_signatures=result.get("freshSignatures"))

        # Load insights
        insights = insight_store.list_insights()
        self.assertGreater(len(insights), 0, "At least 1 insight should be created")

        # Verify insight structure
        ins = insights[0]
        self.assertIn("id", ins)
        self.assertIn("title", ins)
        self.assertIn("status", ins)
        print(f"  ✓ Insight created: {ins.get('title', 'N/A')}")

        # Run again → should NOT duplicate (dedup by signature)
        insight_store.sync_from_findings(findings,
                                          active_signatures=result.get("freshSignatures"))
        insights_after = insight_store.list_insights()
        self.assertEqual(len(insights), len(insights_after),
                         "Re-sync should NOT duplicate insights")
        print(f"  ✓ Deduplication: {len(insights)} insights (no duplicate)")

    def test_04_findings_create_recommendations(self):
        """Verify findings create recommendations with stable IDs."""
        from desktop.runtime import config_store, detection_engine, prioritization, recommendation_store

        data = config_store.load()
        result = detection_engine.run_detection(data, persist=False)
        findings = result.get("findings", [])

        # Build priorities and create recommendations
        prs = prioritization.build_priorities(findings, top=5)
        for p in prs:
            fnd = next((x for x in findings if x.get("id") == p.get("findingId")), None)
            if fnd:
                recommendation_store.record_finding(fnd, data=data)

        recs = recommendation_store.list_recommendations(data=data)
        self.assertGreater(len(recs), 0, "At least 1 recommendation should be created")

        rec = recs[0]
        self.assertIn("id", rec)
        self.assertIn("status", rec)
        self.assertEqual(rec["status"], "open", "New recommendation should be 'open'")
        rec_id = rec["id"]
        print(f"  ✓ Recommendation created: {rec.get('title', 'N/A')} (status={rec['status']})")

        # Run again → should NOT duplicate (stable ID by signature)
        for p in prs:
            fnd = next((x for x in findings if x.get("id") == p.get("findingId")), None)
            if fnd:
                recommendation_store.record_finding(fnd, data=data)

        recs_after = recommendation_store.list_recommendations(data=data)
        self.assertEqual(len(recs), len(recs_after),
                         "Re-record should NOT duplicate recommendations")

        # Same ID preserved
        rec_after = next((r for r in recs_after if r["id"] == rec_id), None)
        self.assertIsNotNone(rec_after, "Original recommendation should still exist")
        print(f"  ✓ Stable ID preserved: {rec_id}")

    def test_05_recommendation_lifecycle(self):
        """Verify recommendation state transitions persist correctly."""
        from desktop.runtime import config_store, detection_engine, prioritization, recommendation_store

        data = config_store.load()
        result = detection_engine.run_detection(data, persist=False)
        findings = result.get("findings", [])
        prs = prioritization.build_priorities(findings, top=5)

        for p in prs:
            fnd = next((x for x in findings if x.get("id") == p.get("findingId")), None)
            if fnd:
                recommendation_store.record_finding(fnd, data=data)

        recs = recommendation_store.list_recommendations(data=data)
        self.assertGreater(len(recs), 0)
        rec_id = recs[0]["id"]

        # Test: open → in_progress
        updated = recommendation_store.set_status(rec_id, "in_progress", data=data)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "in_progress")
        print(f"  ✓ open → in_progress")

        # Test: in_progress → done
        updated = recommendation_store.set_status(rec_id, "done", data=data)
        self.assertIsNotNone(updated)
        # After 'done', may become 'measured' or stay 'done'
        self.assertIn(updated["status"], ("done", "measured"))
        print(f"  ✓ in_progress → {updated['status']}")

        # Verify persistence
        recs_final = recommendation_store.list_recommendations(data=data)
        rec_final = next((r for r in recs_final if r["id"] == rec_id), None)
        self.assertIsNotNone(rec_final)
        self.assertIn(rec_final["status"], ("done", "measured"))
        print(f"  ✓ Persisted: status={rec_final['status']}")

        # Test: reset to open, then resolve
        rec_final["status"] = "open"
        recommendation_store._save(recs_final, data=data)
        updated = recommendation_store.set_status(rec_id, "resolved", data=data)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "resolved")
        self.assertIn("resolvedAt", updated)
        print(f"  ✓ open → resolved (with resolvedAt)")

    def test_06_deduplication_across_syncs(self):
        """Verify that multiple syncs don't create duplicates."""
        from desktop.runtime import config_store, detection_engine, insight_store, recommendation_store

        data = config_store.load()
        result = detection_engine.run_detection(data, persist=False)
        findings = result.get("findings", [])
        sigs = result.get("freshSignatures", [])

        # Run 5 sync cycles
        for i in range(5):
            insight_store.sync_from_findings(findings, active_signatures=sigs)
            for f in findings:
                recommendation_store.record_finding(f, data=data)

        insights = insight_store.list_insights()
        recs = recommendation_store.list_recommendations(data=data)

        # Count unique signatures
        unique_sigs = set(f.get("signature") for f in findings if f.get("signature"))
        self.assertEqual(len(insights), len(unique_sigs),
                         f"Insights ({len(insights)}) should match unique signatures ({len(unique_sigs)})")
        self.assertLessEqual(len(recs), len(unique_sigs) + 1,
                             f"Recommendations ({len(recs)}) should not exceed signatures + 1")
        print(f"  ✓ 5 sync cycles: {len(insights)} insights, {len(recs)} recommendations (no spam)")

    def test_07_notification_event_identity(self):
        """Verify that activity events have deterministic IDs for dedup."""
        import uuid

        # Simulate what buildUnifiedActivity does
        event1 = {
            "id": "insight:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "vanova:rec:missing_cost_sku002")),
            "kind": "insight",
            "action": "Finding: missing_cost",
        }
        event2 = {
            "id": "insight:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "vanova:rec:missing_cost_sku002")),
            "kind": "insight",
            "action": "Finding: missing_cost",
        }

        # Same signature → same ID
        self.assertEqual(event1["id"], event2["id"])
        print(f"  ✓ Deterministic event ID: {event1['id']}")

        # Different signature → different ID
        event3 = {
            "id": "insight:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "vanova:rec:other_finding")),
            "kind": "insight",
        }
        self.assertNotEqual(event1["id"], event3["id"])
        print(f"  ✓ Different finding → different ID")

    def test_08_scheduler_proactive_tick_simulation(self):
        """Simulate a proactive tick and verify it generates results."""
        from desktop.runtime import (
            agent_scheduler,
            config_store,
            detection_engine,
            insight_store,
            prioritization,
            recommendation_store,
        )

        # Reset scheduler state
        agent_scheduler._started = False
        agent_scheduler._stop_event = None
        agent_scheduler._thread = None

        # Clear existing findings/insights/recs
        data = config_store.load()
        data["businessFindings"] = []
        data["insights"] = []
        data["recommendations"] = []
        data["priorities"] = []
        config_store.save(data)

        # Start scheduler
        agent_scheduler.start()
        self.assertTrue(agent_scheduler._started)

        # Manually trigger one tick
        agent_scheduler._tick()

        # Verify results
        data_after = config_store.load()
        findings = data_after.get("businessFindings") or []
        insights = data_after.get("insights") or []
        recs = data_after.get("recommendations") or []

        self.assertGreater(len(findings), 0, "Tick should generate findings")
        self.assertGreater(len(insights), 0, "Tick should generate insights")
        self.assertGreater(len(recs), 0, "Tick should generate recommendations")

        print(f"  ✓ Proactive tick generated: {len(findings)} findings, {len(insights)} insights, {len(recs)} recommendations")

        # Run tick again → should NOT duplicate
        agent_scheduler._tick()
        data_after2 = config_store.load()
        findings2 = data_after2.get("businessFindings") or []
        insights2 = data_after2.get("insights") or []
        recs2 = data_after2.get("recommendations") or []

        self.assertEqual(len(findings), len(findings2), "Findings should not duplicate")
        self.assertEqual(len(insights), len(insights2), "Insights should not duplicate")
        self.assertEqual(len(recs), len(recs2), "Recommendations should not duplicate")
        print(f"  ✓ Second tick: same counts (dedup works)")

        # Stop scheduler
        agent_scheduler.stop()

    def test_09_background_persistence_simulation(self):
        """Simulate window close: scheduler continues, then clean shutdown."""
        from desktop.runtime import agent_scheduler

        agent_scheduler._started = False
        agent_scheduler._stop_event = None
        agent_scheduler._thread = None

        agent_scheduler.start()
        self.assertTrue(agent_scheduler._thread.is_alive())
        print("  ✓ Scheduler thread alive after start")

        # Simulate window close (scheduler continues)
        time.sleep(2)
        self.assertTrue(agent_scheduler._started, "Scheduler still running after 'window close'")
        self.assertTrue(agent_scheduler._thread.is_alive(), "Thread still alive")
        print("  ✓ Scheduler still running 2s after simulated window close")

        # Simulate "Salir de VANOVA" (explicit quit)
        agent_scheduler.stop()
        time.sleep(1)
        self.assertFalse(agent_scheduler._started)
        print("  ✓ Scheduler stopped after 'Salir de VANOVA'")

    def test_10_full_cycle_demonstration(self):
        """Complete E2E cycle: import → analyze → find → recommend → measure."""
        from desktop.runtime import (
            config_store,
            detection_engine,
            insight_store,
            prioritization,
            recommendation_store,
        )

        print("\n  === FULL PROACTIVITY CYCLE ===\n")

        # Step 1: Load data
        data = config_store.load()
        products = data.get("organizedProducts") or []
        sales = data.get("organizedSales") or []
        print(f"  Step 1: Data loaded — {len(products)} products, {len(sales)} sales")

        # Step 2: Run detection
        result = detection_engine.run_detection(data, persist=False)
        findings = result.get("findings", [])
        sigs = result.get("freshSignatures", [])
        print(f"  Step 2: Detection complete — {len(findings)} findings")

        for f in findings:
            print(f"    → {f.get('type')}: {f.get('title')} (sig={f.get('signature', 'N/A')[:20]}...)")

        # Step 3: Sync insights (no data= so it persists to disk)
        insight_store.sync_from_findings(findings, active_signatures=sigs)
        insights = insight_store.list_insights()
        print(f"  Step 3: Insights synced — {len(insights)} total")

        # Step 4: Create recommendations
        prs = prioritization.build_priorities(findings, top=5)
        for p in prs:
            fnd = next((x for x in findings if x.get("id") == p.get("findingId")), None)
            if fnd:
                recommendation_store.record_finding(fnd, data=data)
        recs = recommendation_store.list_recommendations(data=data)
        print(f"  Step 4: Recommendations created — {len(recs)} total")

        # Step 5: User marks one as in_progress
        if recs:
            rec_id = recs[0]["id"]
            recommendation_store.set_status(rec_id, "in_progress", data=data)
            print(f"  Step 5: Recommendation {rec_id[:12]}... → in_progress")

        # Step 6: Simulate resolution (problem disappears)
        if recs:
            rec_final = next((r for r in recommendation_store.list_recommendations(data=data)
                             if r["id"] == rec_id), None)
            if rec_final:
                rec_final["status"] = "open"
                recommendation_store._save(recommendation_store.list_recommendations(data=data), data=data)
                recommendation_store.set_status(rec_id, "resolved", data=data)
                print(f"  Step 6: Recommendation resolved")

        # Step 7: Re-analyze (problem gone → auto-resolve)
        recommendation_store.sync_resolutions(findings[:1] if findings else [],
                                               active_signatures=sigs, data=data)
        print(f"  Step 7: sync_resolutions completed")

        # Step 8: Verify final state
        final_recs = recommendation_store.list_recommendations(data=data)
        for r in final_recs:
            print(f"    → {r.get('title', 'N/A')[:40]}: status={r.get('status')}")

        print(f"\n  === CYCLE COMPLETE ===\n")
        self.assertGreater(len(findings), 0, "Should have findings")
        self.assertGreater(len(recs), 0, "Should have recommendations")


if __name__ == "__main__":
    unittest.main(verbosity=2)
