"""FASE 14 — DATA MIGRATION & DATA INTEGRITY PROTOCOL tests.

Incluye la fixture de una instalación ANTIGUA con datos deliberadamente
incorrectos/sin procedencia y verifica: detección, no-verificación, marcado
LEGACY/NEEDS_REVIEW, revalidación, conservación, idempotencia y no-destrucción.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from desktop.runtime import data_governance as dg
from desktop.runtime import product_identity


def legacy_fixture() -> dict:
    """Instalación antigua (schema 0) con datos mal identificados.

    - Producto sin source ni costStatus ni provenance → LEGACY.
    - Producto con coste == PVD sin evidencia → NEEDS_REVIEW (no coste real).
    - Producto verificado con costSource → VERIFIED.
    - Pedido sin source ni provenance → LEGACY.
    - Pedido Shopify con fecha → VERIFIED.
    - Pedido con total que no cuadra con líneas → NEEDS_REVIEW.
    - Línea sin SKU → NEEDS_REVIEW.
    """
    return {
        "version": "1.4.2",
        "setupComplete": True,
        "dataGovernance": {"dataSchemaVersion": 0},
        "organizedProducts": [
            {"name": "Artículo viejo sin metadatos", "sku": "OLD-1"},  # LEGACY
            {"name": "Coste falso", "sku": "PVD-1", "netPrice": 10.0, "rrp": 10.0,
             "costStatus": "missing", "source": "excel"},  # NEEDS_REVIEW (coste==PVD)
            {"name": "Bien verificado", "sku": "OK-1", "netPrice": 5.0, "rrp": 10.0,
             "cost": 5.0, "costSource": "supplier", "costStatus": "verified",
             "source": "excel"},  # VERIFIED
            {"name": "Sincronizado", "sku": "SH-1", "rrp": 15.0, "source": "shopify"},  # VERIFIED
            {"sku": "", "name": ""},  # INVALID
        ],
        "organizedSales": [
            {"id": "ORD-LEGACY"},  # LEGACY
            {"id": "ORD-SHOPIFY", "source": "shopify", "date": "2026-07-01", "total": 20.0},  # VERIFIED
            {"id": "ORD-MISMATCH", "source": "shopify", "date": "2026-07-02", "total": 10.0,
             "line_items": [{"sku": "X", "quantity": 1, "price": 100.0}]},  # NEEDS_REVIEW
        ],
        "organizedCustomers": [
            {"name": "Cliente antiguo"},  # LEGACY (sin id ni email ni source)
        ],
        "organizedInvoices": [],
        "organizedFinance": [],
    }


class QualityStateTests(unittest.TestCase):
    """P3 — semántica de estados de calidad."""

    def test_unknown_never_zero(self):
        # UNKNOWN ≠ 0: un estado vacío no debe confundirse con un cero.
        counts = dg._empty_counts()
        self.assertEqual(counts["unknown"], 0)
        self.assertNotIn(None, (dg.QUALITY_STATES))
        # El resumen de salud nunca convierte unknown en verified
        self.assertNotEqual(dg.QUALITY_UNKNOWN, dg.QUALITY_VERIFIED)

    def test_legacy_not_verified_by_existence(self):
        p = {"name": "viejo", "sku": "A"}
        state, _ = dg.infer_product_quality(p)
        self.assertEqual(state, dg.QUALITY_LEGACY)  # existir NO verifica

    def test_pvd_equals_cost_not_verified(self):
        p = {"name": "P", "sku": "B", "netPrice": 10.0, "rrp": 10.0, "source": "excel"}
        state, reason = dg.infer_product_quality(p)
        self.assertEqual(state, dg.QUALITY_NEEDS_REVIEW)
        self.assertIn("PVD", reason)

    def test_verified_cost_wins(self):
        p = {"name": "P", "sku": "C", "cost": 4.0, "costSource": "supplier",
             "costStatus": "verified", "source": "excel"}
        state, _ = dg.infer_product_quality(p)
        self.assertEqual(state, dg.QUALITY_VERIFIED)

    def test_shopify_source_verified(self):
        p = {"name": "P", "sku": "D", "source": "shopify"}
        state, _ = dg.infer_product_quality(p)
        self.assertEqual(state, dg.QUALITY_VERIFIED)

    def test_imported_without_external_check(self):
        p = {"name": "P", "sku": "E", "source": "excel", "netPrice": 4.0, "rrp": 8.0}
        state, _ = dg.infer_product_quality(p)
        self.assertEqual(state, dg.QUALITY_IMPORTED)

    def test_invalid_negative_price(self):
        p = {"name": "P", "sku": "F", "rrp": -5.0}
        state, _ = dg.infer_product_quality(p)
        self.assertEqual(state, dg.QUALITY_INVALID)

    def test_contradiction_verified_without_cost(self):
        p = {"name": "P", "sku": "G", "costStatus": "verified", "cost": None,
             "costSource": "", "source": "shopify"}
        state, _ = dg.infer_product_quality(p)
        self.assertEqual(state, dg.QUALITY_NEEDS_REVIEW)

    def test_explicit_quality_persisted(self):
        p = {"name": "P", "sku": "H", "qualityStatus": "needs_review"}
        state, _ = dg.infer_product_quality(p)
        self.assertEqual(state, dg.QUALITY_NEEDS_REVIEW)


class IntegrityAuditTests(unittest.TestCase):
    """P5/P15 — auditoría reutilizable, READ-ONLY por defecto."""

    def test_audit_legacy_fixture_states(self):
        r = dg.validate_data_integrity(entities=dg._load_entities() if False else {
            "products": legacy_fixture()["organizedProducts"],
            "orders": legacy_fixture()["organizedSales"],
            "orderLines": [],
            "customers": legacy_fixture()["organizedCustomers"],
            "invoices": [],
            "finance": [],
        })
        by = r["byEntity"]
        # 4 productos: OLD-1 legacy, PVD-1 needs_review, OK-1 verified,
        # SH-1 verified, vacío invalid → 2 verified, 1 legacy, 1 needs_review, 1 invalid
        self.assertEqual(by["products"]["counts"]["verified"], 2)
        self.assertEqual(by["products"]["counts"]["legacy"], 1)
        self.assertEqual(by["products"]["counts"]["needs_review"], 1)
        self.assertEqual(by["products"]["counts"]["invalid"], 1)
        # pedidos: ORD-LEGACY legacy, ORD-SHOPIFY verified, ORD-MISMATCH needs_review
        self.assertEqual(by["orders"]["counts"]["legacy"], 1)
        self.assertEqual(by["orders"]["counts"]["verified"], 1)
        self.assertEqual(by["orders"]["counts"]["needs_review"], 1)
        self.assertEqual(r["status"], "FAIL")  # hay inválidos

    def test_audit_readonly_by_default(self):
        fixture = legacy_fixture()
        with patch("desktop.runtime.config_store.load", return_value=fixture), \
             patch("desktop.runtime.config_store.save") as mock_save:
            dg.validate_data_integrity()
        mock_save.assert_not_called()  # READ-ONLY por defecto

    def test_audit_persist_writes_governance(self):
        fixture = legacy_fixture()
        with patch("desktop.runtime.config_store.load", return_value=fixture), \
             patch("desktop.runtime.config_store.save") as mock_save:
            dg.validate_data_integrity(persist=True)
        mock_save.assert_called_once()
        args = mock_save.call_args[0][0]
        gov = args["dataGovernance"]
        self.assertEqual(gov["lastIntegrityStatus"], "FAIL")
        self.assertIsNotNone(gov["lastIntegrityCheck"])

    def test_secrets_never_in_report(self):
        # Los informes no exponen credenciales ni tokens (solo ids/motivos).
        r = dg.validate_data_integrity(entities={
            "products": [{"name": "P", "sku": "S1", "rrp": 1.0, "source": "shopify"}],
            "orders": [], "orderLines": [], "customers": [], "invoices": [], "finance": [],
        })
        blob = json.dumps(r)
        for secret in ("shpat_", "ghp_", "Token", "apiKey", "password"):
            self.assertNotIn(secret.lower(), blob.lower())


class MigrationProtocolTests(unittest.TestCase):
    """P4/P8/P10/P11 — protocolo de actualización NO destructivo."""

    _OK_BACKUP = {"ok": True, "path": "/tmp/bk"}

    def _run_protocol(self, fixture):
        with patch("desktop.runtime.config_store.load", return_value=fixture), \
             patch("desktop.runtime.config_store.save", side_effect=lambda data: fixture.update(data)), \
             patch("desktop.runtime.backup_service.run_backup", return_value=self._OK_BACKUP):
            return dg.run_migration_protocol(), fixture

    def test_update_detects_and_migrates(self):
        fixture = legacy_fixture()
        result, data = self._run_protocol(fixture)
        self.assertEqual(result["status"], "migrated")
        self.assertEqual(result["fromSchemaVersion"], 0)
        self.assertEqual(result["toSchemaVersion"], dg.DATA_SCHEMA_VERSION)
        self.assertTrue(result["steps"]["backup"]["ok"])
        # Los datos NO se borran
        self.assertEqual(len(data["organizedProducts"]), 5)
        self.assertEqual(len(data["organizedSales"]), 3)
        # El producto legacy queda marcado LEGACY, nunca borrado ni "verificado"
        old = next(p for p in data["organizedProducts"] if p["sku"] == "OLD-1")
        self.assertEqual(old["qualityStatus"], "legacy")
        self.assertEqual(old["legacyFromVersion"], "1.4.2")
        # El verificado NO se degrada
        ok = next(p for p in data["organizedProducts"] if p["sku"] == "OK-1")
        self.assertNotEqual(ok.get("qualityStatus"), "legacy")
        # El pedido legacy marcado
        old_order = next(o for o in data["organizedSales"] if o["id"] == "ORD-LEGACY")
        self.assertEqual(old_order["qualityStatus"], "legacy")
        # Se registra la gobernanza
        gov = data["dataGovernance"]
        self.assertEqual(gov["dataSchemaVersion"], dg.DATA_SCHEMA_VERSION)
        self.assertEqual(gov["migrationStatus"], "migrated")
        self.assertIsNotNone(gov["lastIntegrityCheck"])

    def test_migration_idempotent(self):
        fixture = legacy_fixture()
        result1, data1 = self._run_protocol(fixture)
        # Segunda ejecución: esquema al día y misma versión → up_to_date, sin cambios
        result2, data2 = self._run_protocol(fixture)
        self.assertEqual(result2["status"], "up_to_date")
        # Entidades sin calidad marcada tras la primera pasada siguen sin cambios
        # (idempotencia: no se vuelven a marcar)
        self.assertEqual(len(data2["organizedProducts"]), len(data1["organizedProducts"]))

    def test_up_to_date_still_ensures_marking(self):
        # Si el esquema está al día pero alguna entidad perdió su calidad (p.
        # ej. una sync de una versión antigua que pisaba campos de gobernanza),
        # el protocolo la vuelve a clasificar al arrancar (idempotente).
        fixture = legacy_fixture()
        fixture["dataGovernance"] = {"dataSchemaVersion": dg.DATA_SCHEMA_VERSION}
        with patch("desktop.runtime.config_store.load", return_value=fixture), \
             patch("desktop.runtime.config_store.save", side_effect=lambda data: fixture.update(data)), \
             patch("desktop.runtime.backup_service.run_backup", return_value=self._OK_BACKUP):
            result = dg.run_migration_protocol()
        self.assertEqual(result["status"], "up_to_date")
        # El producto legacy vuelve a quedar marcado
        old = next(p for p in fixture["organizedProducts"] if p["sku"] == "OLD-1")
        self.assertEqual(old["qualityStatus"], "legacy")

    def test_fresh_install_skips_migration(self):
        fresh = {"version": "2.0.24", "setupComplete": False,
                 "organizedProducts": [], "organizedSales": [],
                 "dataGovernance": {"dataSchemaVersion": 0}}
        result, data = self._run_protocol(fresh)
        self.assertEqual(result["status"], "fresh_install")
        self.assertEqual(data["dataGovernance"]["migrationStatus"], "fresh_install")

    def test_failed_migration_preserves_data(self):
        # Backup fallido → ABORTA la migración: no marca, no guarda, no borra.
        # (Antes continuaba marcando; la auditoría pre-release lo corrigió: sin
        # backup no se modifica NINGÚN dato.)
        fixture = legacy_fixture()
        with patch("desktop.runtime.config_store.load", return_value=fixture), \
             patch("desktop.runtime.config_store.save", side_effect=lambda data: fixture.update(data)), \
             patch("desktop.runtime.backup_service.run_backup", side_effect=RuntimeError("disk full")):
            result = dg.run_migration_protocol()
        self.assertFalse(result["steps"]["backup"]["ok"])
        self.assertEqual(result["status"], "backup_failed")
        self.assertIn("ningún dato fue modificado", result["blockedReason"].lower())
        # Ninguna entidad fue marcada ni modificada
        self.assertEqual(len(fixture["organizedProducts"]), 5)
        self.assertEqual(len(fixture["organizedSales"]), 3)
        for p in fixture["organizedProducts"]:
            self.assertNotIn("qualityStatus", p)
        for o in fixture["organizedSales"]:
            self.assertNotIn("qualityStatus", o)
        # La gobernanza no se registró como migrada
        self.assertNotEqual(fixture["dataGovernance"].get("migrationStatus"), "migrated")


class SyncGuardTests(unittest.TestCase):
    """P16/P18 — regresión H23: una sync nunca destruye costes ni cobertura."""

    def _product(self, sku, cost=None, source="shopify"):
        p = {"name": sku, "sku": sku, "source": source, "rrp": 10.0}
        if cost is not None:
            p.update({"cost": cost, "costSource": "supplier", "costStatus": "verified"})
        return p

    def test_sync_removing_all_costs_is_blocked(self):
        # Escenario H23 directo: si el resultado del merge (aun sin pasar por
        # _merge_products) dejaría el cost coverage en 0 con costes verificados
        # existentes, el guard lo BLOQUEA. Defensa en profundidad: aunque una
        # futura ruta de merge no preserve los enriquecimientos, la sync no
        # puede destruir la cobertura.
        before_products = [self._product(f"S{i}", cost=5.0, source="excel") for i in range(5)]
        sales = [{"id": f"O{i}", "source": "shopify", "date": "2026-07-01",
                  "total": 10.0, "line_items": [{"sku": f"S{i}", "quantity": 1, "price": 10.0}]}
                 for i in range(5)]
        after_products = [self._product(f"S{i}", source="excel") for i in range(5)]  # sin coste

        guard = dg.evaluate_sync_guard(before_products, sales, after_products, sales)
        self.assertTrue(guard["blocked"])
        self.assertTrue(any("eliminaría" in a or "reduciría" in a for a in guard["alerts"]))

    def test_merge_preserves_local_costs(self):
        # La capa de merge ya conserva los enriquecimientos locales (H23 fix).
        from desktop.runtime import shopify_sync
        existing = [self._product("S1", cost=3.5)]
        incoming = [self._product("S1")]  # sin coste desde la API
        merged = shopify_sync._merge_products(existing, incoming)
        self.assertEqual(merged[0]["cost"], 3.5)
        self.assertEqual(merged[0]["costStatus"], "verified")
        self.assertEqual(merged[0]["costSource"], "supplier")

    def test_merge_preserves_governance_fields_on_products_and_orders(self):
        # FASE 14: qualityStatus/legacyFromVersion son propiedad de VANOVA y
        # deben sobrevivir a la re-sincronización (productos Y pedidos).
        from desktop.runtime import shopify_sync
        existing_p = [{"name": "S1", "sku": "S1", "source": "shopify",
                       "qualityStatus": "needs_review", "legacyFromVersion": "1.4.2",
                       "cost": 3.5, "costStatus": "verified", "costSource": "supplier"}]
        incoming_p = [{"name": "S1", "sku": "S1", "source": "shopify", "rrp": 10.0}]
        merged_p = shopify_sync._merge_products(existing_p, incoming_p)
        self.assertEqual(merged_p[0]["qualityStatus"], "needs_review")
        self.assertEqual(merged_p[0]["legacyFromVersion"], "1.4.2")
        self.assertEqual(merged_p[0]["cost"], 3.5)  # enriquecimiento local intacto

        existing_o = [{"id": "O1", "source": "shopify", "date": "2026-07-01",
                       "total": 20.0, "qualityStatus": "needs_review"}]
        incoming_o = [{"id": "O1", "source": "shopify", "date": "2026-07-05", "total": 22.0}]
        merged_o = shopify_sync._merge_sales(existing_o, incoming_o)
        self.assertEqual(merged_o[0]["qualityStatus"], "needs_review")  # gobernanza conservada
        self.assertEqual(merged_o[0]["total"], 22.0)  # el dato fresco de la API gana
        self.assertEqual(merged_o[0]["date"], "2026-07-05")

    def test_normal_sync_not_blocked(self):
        existing_products = [self._product(f"S{i}", cost=5.0) for i in range(5)]
        existing_sales = [{"id": f"O{i}", "source": "shopify", "date": "2026-07-01",
                           "total": 10.0, "line_items": [{"sku": f"S{i}", "quantity": 1, "price": 10.0}]}
                          for i in range(5)]
        guard = dg.evaluate_sync_guard(existing_products, existing_sales, existing_products, existing_sales)
        self.assertFalse(guard["blocked"])


class OrganizerMergeGovernanceTests(unittest.TestCase):
    """Auditoría pre-release: file_organizer reemplazaba entidades completas y
    destruía enriquecimiento local (cost, gobernanza, mappings) en el merge de
    archivos + conectores. Ahora el merge es field-aware."""

    def test_file_organizer_product_merge_preserves_enrichment(self):
        from desktop.runtime import file_organizer as fo
        existing = [{"name": "S1", "sku": "S1", "source": "excel", "netPrice": 3.5, "rrp": 10.0,
                     "cost": 3.5, "costSource": "supplier", "costStatus": "verified",
                     "qualityStatus": "needs_review", "legacyFromVersion": "1.4.2"}]
        incoming = [{"name": "S1", "sku": "S1", "source": "shopify", "rrp": 11.0}]
        merged = fo._merge_products(existing, incoming)
        self.assertEqual(len(merged), 1)
        row = merged[0]
        # El conector gana en sus campos (precio)…
        self.assertEqual(row["rrp"], 11.0)
        self.assertEqual(row["source"], "shopify")
        # …pero el enriquecimiento local y la gobernanza sobreviven
        self.assertEqual(row["cost"], 3.5)
        self.assertEqual(row["costStatus"], "verified")
        self.assertEqual(row["costSource"], "supplier")
        self.assertEqual(row["qualityStatus"], "needs_review")
        self.assertEqual(row["legacyFromVersion"], "1.4.2")

    def test_file_organizer_sales_merge_preserves_governance(self):
        from desktop.runtime import file_organizer as fo
        existing = [{"id": "O1", "source": "excel", "date": "2026-07-01", "total": 20.0,
                     "qualityStatus": "needs_review", "legacyFromVersion": "1.4.2"}]
        incoming = [{"id": "O1", "source": "shopify", "date": "2026-07-05", "total": 22.0}]
        merged = fo._merge_sales(existing, incoming)
        self.assertEqual(len(merged), 1)
        row = merged[0]
        self.assertEqual(row["total"], 22.0)  # el dato fresco gana
        self.assertEqual(row["qualityStatus"], "needs_review")  # gobernanza conservada
        self.assertEqual(row["legacyFromVersion"], "1.4.2")

    def test_file_organizer_merge_never_drops_existing_without_key(self):
        # Regresión: un re-escaneo sin la fila no borra la fila existente con la
        # misma clave; solo los datos frescos que SÍ existen reemplazan.
        from desktop.runtime import file_organizer as fo
        existing = [{"name": "K1", "sku": "K1", "source": "excel", "rrp": 10.0}]
        incoming = []  # el archivo ya no se puede extraer
        merged = fo._merge_products(existing, incoming)
        self.assertEqual(len(merged), 1)

    def test_review_counts_light_helper(self):
        fixture = legacy_fixture()
        # Tras marcar, el conteo ligero refleja los estados persistidos
        with patch("desktop.runtime.config_store.load", return_value=fixture), \
             patch("desktop.runtime.config_store.save", side_effect=lambda data: fixture.update(data)), \
             patch("desktop.runtime.backup_service.run_backup", return_value={"ok": True, "path": "/tmp/bk"}):
            dg.run_migration_protocol()
        counts = dg._review_counts(fixture)
        self.assertGreaterEqual(counts["legacy"], 1)      # OLD-1 / ORD-LEGACY / cliente
        self.assertGreaterEqual(counts["needs_review"], 1)  # PVD-1 / ORD-MISMATCH
        self.assertEqual(counts["invalid"], 1)            # producto vacío
        self.assertEqual(counts["total"], counts["legacy"] + counts["needs_review"] + counts["invalid"])


class FactoryResetTests(unittest.TestCase):
    """P14 — reset explícito con backup, nunca automático tras un update."""

    def test_requires_confirmation(self):
        result = dg.factory_reset(confirmed=False)
        self.assertFalse(result["ok"])
        self.assertIn("Confirmación", result["error"])

    def test_confirmed_reset_backs_up_and_clears(self):
        fixture = legacy_fixture()
        with patch("desktop.runtime.config_store.load", return_value=fixture), \
             patch("desktop.runtime.config_store.reset_to_defaults",
                   side_effect=lambda: fixture.update({"organizedProducts": [], "organizedSales": []}) or fixture), \
             patch("desktop.runtime.backup_service.run_backup", return_value={"path": "/tmp/bk"}), \
             patch("desktop.runtime.integrations_store.disconnect", return_value={"ok": True}), \
             patch("desktop.runtime.paths.data_dir", return_value=_tmp_data_dir()):
            result = dg.factory_reset(confirmed=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["backupPath"], "/tmp/bk")
        self.assertEqual(fixture["organizedProducts"], [])

    def test_confirmed_reset_aborts_when_backup_fails(self):
        # Backup fallido → NUNCA se borra nada: el reset aborta antes de tocar
        # los datos (la desconexión de integraciones no debe ejecutarse).
        fixture = legacy_fixture()
        disconnected = []
        with patch("desktop.runtime.config_store.load", return_value=fixture), \
             patch("desktop.runtime.config_store.reset_to_defaults", side_effect=AssertionError("no debe llamarse")), \
             patch("desktop.runtime.backup_service.run_backup",
                   side_effect=RuntimeError("backup failed")), \
             patch("desktop.runtime.integrations_store.disconnect",
                   side_effect=lambda iid: disconnected.append(iid) or {"ok": True}), \
             patch("desktop.runtime.paths.data_dir", return_value=_tmp_data_dir()):
            result = dg.factory_reset(confirmed=True)
        self.assertFalse(result["ok"])
        self.assertIn("backup", result["error"].lower())
        self.assertEqual(fixture["organizedProducts"], legacy_fixture()["organizedProducts"])
        self.assertEqual(disconnected, [])  # ni siquiera se intentó desconectar

    def test_factory_reset_is_complete_and_returns_to_setup(self):
        # FASE reset completo: TODOS los datos generados por VANOVA desaparecen
        # (negocio, findings, insights, recomendaciones, memoria), las bases de
        # decisión se eliminan y setupComplete vuelve a False.
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.mkdtemp(prefix="vanova-reset-"))
        (tmp / "approvals.db").write_text("x")
        (tmp / "tasks.db").write_text("x")
        (tmp / "approvals.db-wal").write_text("x")
        (tmp / "tasks.db-shm").write_text("x")
        # Un archivo físico del usuario NO debe tocarse jamás.
        user_file = tmp / "datos-empresa.csv"
        user_file.write_text("sku,precio\nA,1")

        fresh = {
            "version": "3.0.0",
            "setupComplete": False,
            "organizedProducts": [],
            "organizedSales": [],
            "businessFindings": [],
            "insights": [],
            "recommendations": [],
            "companyModel": None,
            "dataGovernance": {},
        }
        with patch("desktop.runtime.config_store.reset_to_defaults", return_value=fresh), \
             patch("desktop.runtime.backup_service.run_backup", return_value={"path": "/tmp/bk"}), \
             patch("desktop.runtime.integrations_store.disconnect", return_value={"ok": True}), \
             patch("desktop.runtime.paths.data_dir", return_value=tmp):
            result = dg.factory_reset(confirmed=True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["setupComplete"])
        self.assertEqual(sorted(result["removedDatabases"]),
                         sorted(["approvals.db", "approvals.db-wal", "tasks.db", "tasks.db-shm"]))
        self.assertFalse((tmp / "approvals.db").exists())
        self.assertFalse((tmp / "tasks.db").exists())
        self.assertTrue(user_file.exists())  # los archivos del PC jamás se borran
        self.assertEqual(user_file.read_text(), "sku,precio\nA,1")


class ClearBusinessDataTests(unittest.TestCase):
    """Escaneo → «Limpiar y volver a importar»: solo el estado empresarial."""

    def test_requires_confirmation(self):
        result = dg.clear_business_data(confirmed=False)
        self.assertFalse(result["ok"])
        self.assertIn("Confirmación", result["error"])

    def test_clears_business_state_keeps_installation(self):
        fixture = legacy_fixture()
        fixture["setupComplete"] = True
        fixture["scanFolders"] = ["C:/Empresa"]
        fixture["companyProfile"] = {"name": "Mi Empresa"}
        fixture["insights"] = [{"id": "i1"}]
        fixture["recommendations"] = [{"id": "r1"}]
        fixture["businessFindings"] = [{"id": "f1"}]
        fixture["companyModel"] = {"memory": "x"}

        def fake_remove_keys(keys):
            for k in keys:
                fixture.pop(k, None)
            return fixture

        with patch("desktop.runtime.config_store.load", return_value=fixture), \
             patch("desktop.runtime.config_store.remove_keys", side_effect=fake_remove_keys), \
             patch("desktop.runtime.config_store.save", side_effect=lambda d: fixture.update(d)), \
             patch("desktop.runtime.backup_service.run_backup", return_value={"path": "/tmp/bk"}):
            result = dg.clear_business_data(confirmed=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["setupComplete"])
        # Estado empresarial y derivados eliminados…
        for k in ("organizedProducts", "organizedSales", "businessFindings",
                  "insights", "recommendations", "companyModel", "importantItems"):
            self.assertNotIn(k, fixture, k)
        # …pero la instalación/identidad sobreviven
        self.assertTrue(fixture["setupComplete"])
        self.assertEqual(fixture["scanFolders"], ["C:/Empresa"])
        self.assertEqual(fixture["companyProfile"], {"name": "Mi Empresa"})
        # No se deja estado huérfano persistido
        self.assertNotIn("dataCleanReimport", fixture)
        self.assertNotIn("dataCleanReimportAt", fixture)

    def test_aborts_when_backup_fails(self):
        fixture = legacy_fixture()
        with patch("desktop.runtime.config_store.load", return_value=fixture), \
             patch("desktop.runtime.config_store.remove_keys", side_effect=AssertionError("no debe llamarse")), \
             patch("desktop.runtime.backup_service.run_backup", side_effect=RuntimeError("backup failed")):
            result = dg.clear_business_data(confirmed=True)
        self.assertFalse(result["ok"])
        self.assertIn("backup", result["error"].lower())
        self.assertEqual(fixture.get("organizedProducts"), legacy_fixture()["organizedProducts"])


def _tmp_data_dir():
    import tempfile
    from pathlib import Path

    return Path(tempfile.mkdtemp(prefix="vanova-reset-tmp-"))


if __name__ == "__main__":
    unittest.main()
