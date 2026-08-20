"""Tests for Hermes file organizer."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.runtime.file_organizer import (
    _parse_customer_rows,
    _parse_product_dict_rows,
    _parse_sales_dict_rows,
    classify_file,
    get_sales,
    organize_files,
)


class FileOrganizerTests(unittest.TestCase):
    def _mock_store(self, initial: dict):
        """Parchea config_store TANTO en file_organizer como en data_version.

        organize_files llama a data_version.stamp_import, que usa su propia
        referencia a config_store — sin este segundo patch los tests escribirían
        en el config REAL de producción."""
        store: dict = dict(initial)
        mock_store = unittest.mock.MagicMock()
        mock_store.load.return_value = store
        mock_store.save.side_effect = lambda data: store.update(data)
        patchers = [
            patch("desktop.runtime.file_organizer.config_store", mock_store),
            patch("desktop.runtime.data_version.config_store", mock_store),
        ]
        for p in patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])
        return store
    def test_classify_by_filename(self):
        self.assertEqual(classify_file({"name": "catalogo_precios.csv", "ext": "csv"}), "products")
        self.assertEqual(classify_file({"name": "ventas_2026.csv", "ext": "csv"}), "sales")

    def test_organize_persists_products(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "productos.csv"
            csv_path.write_text("sku,producto,precio\nA1,Test,10.5\n", encoding="utf-8")
            files = [{
                "name": csv_path.name,
                "path": str(csv_path),
                "ext": "csv",
                "size": csv_path.stat().st_size,
            }]
            stored = self._mock_store({"scanFiles": files})
            with patch("desktop.runtime.file_organizer.task_queue.enqueue") as mock_enqueue:
                mock_enqueue.return_value = {"id": "task-1"}
                result = organize_files(files, trigger_hermes=True)
            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["products"], 1)
            self.assertEqual(stored["scanFiles"][0]["category"], "products")


    def test_truncated_preview_never_truncates_import(self):
        """FASE 16 H24 regression: la UI manda contentPreview truncado a 64KB.
        Si el archivo existe en disco, la extracción DEBE leer el archivo
        completo — un CSV de ventas >64KB no puede importarse de forma parcial."""
        from desktop.runtime import file_organizer as fo

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "ventas_grandes.csv"
            rows = ["order_id,customer_name,customer_email,sku,quantity,total,date,status"]
            for i in range(3000):
                rows.append(f"ORD-{i:05d},Cliente {i},c{i}@demo.test,NH-0001,1,10.50,2026-08-01,paid")
            full = "\n".join(rows)
            csv_path.write_text(full, encoding="utf-8")
            preview = full[:65536]  # truncado como hace la UI (text.slice(0,65536))
            entry = {
                "name": csv_path.name,
                "path": str(csv_path),
                "ext": "csv",
                "size": csv_path.stat().st_size,
                "contentPreview": preview,
            }
            sales = fo._extract_sales(entry)
            self.assertEqual(len(sales), 3000, "el preview truncado no puede limitar la extracción")


    def test_customer_export_has_explicit_customer_schema(self):
        content = "cliente,nif,email,provincia,pais,actividad\nAcme SL,B123,ops@acme.test,Sevilla,ES,Comercio\n"
        self.assertEqual(
            classify_file({"name": "clientes.csv", "ext": "csv", "contentPreview": content}),
            "customers",
        )

    def test_sales_mapping_never_uses_province_as_customer(self):
        rows = _parse_sales_dict_rows([
            {
                "pedido": "P-1",
                "provincia": "Sevilla",
                "pais": "ES",
                "actividad": "Comercio",
                "cliente": "Acme SL",
                "total": "120,50",
                "fecha": "2026-08-01",
            }
        ], "ventas.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["customer"], "Acme SL")
        self.assertEqual(rows[0]["customerProvince"], "Sevilla")
        self.assertEqual(rows[0]["customerCountry"], "ES")
        self.assertEqual(rows[0]["customerActivity"], "Comercio")
        self.assertNotEqual(rows[0]["customer"], rows[0]["customerProvince"])

    def test_semicolon_customer_export_and_tax_id_do_not_become_name(self):
        content = "cliente;nif;pais;provincia;actividad\n;B123;ES;Madrid;Retail\n"
        rows = _parse_customer_rows(content, ";", "clientes.csv")
        self.assertEqual(rows[0]["name"], "Cliente sin nombre")
        self.assertEqual(rows[0]["taxId"], "B123")
        self.assertEqual(rows[0]["country"], "ES")

    def test_product_generic_price_is_sale_price_not_cost(self):
        rows = _parse_product_dict_rows([
            {"sku": "A1", "producto": "Producto", "precio": "10,50"}
        ], "catalogo.csv")
        self.assertEqual(rows[0]["rrp"], 10.5)
        self.assertIsNone(rows[0]["netPrice"])

    def test_legacy_dashboard_config_is_not_a_business_file(self):
        entry = {
            "name": "maios.json",
            "path": r"C:\Users\Admin\Documents\Codex\MAIOS\config\maios.json",
            "ext": "json",
            "contentPreview": '{"organizedSales": [{"customer": "not a company export"}]}'
        }
        self.assertEqual(classify_file(entry), "other")

    def test_organize_excludes_legacy_files(self):
        files = [{
            "name": "maios.json",
            "path": r"C:\old\MAIOS\config\maios.json",
            "ext": "json",
            "contentPreview": '{"organizedSales": [{"customer": "old"}]}'
        }]
        stored = self._mock_store({"scanFiles": files})
        result = organize_files(files, trigger_hermes=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["sales"], 0)
        self.assertEqual(stored["scanFiles"], [])
        self.assertEqual(len(stored["scanExclusions"]), 1)

    def test_organize_from_content_preview(self):
        files = [{
            "name": "ventas_import.csv",
            "path": "ventas_import.csv",
            "ext": "csv",
            "size": 100,
            "contentPreview": "order,customer,total,date\nO1,Acme,99.5,2026-01-01\n",
        }]
        stored = self._mock_store({"scanFiles": files})
        with patch("desktop.runtime.file_organizer.task_queue.enqueue") as mock_enqueue:
            mock_enqueue.return_value = {"id": "task-2"}
            result = organize_files(files, trigger_hermes=False)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["sales"], 1)
        self.assertEqual(stored["scanFiles"][0]["category"], "sales")

    def test_rescan_preserves_imported_catalog_when_source_is_unavailable(self):
        """Startup organization must not erase normalized rows when the file is offline."""
        files = [{
            "name": "catalogo_precios.xlsx",
            "path": r"C:\\cliente\\catalogo_precios.xlsx",
            "ext": "xlsx",
        }]
        previous = {
            "scanFiles": files,
            "organizedProducts": [
                {"name": "Producto válido", "sku": "SKU-1", "rrp": 12.5, "source": "excel", "sourceFile": "catalogo_precios.xlsx"}
            ],
            "organizedSales": [],
            "organizedCustomers": [],
        }
        previous = self._mock_store(previous)
        result = organize_files(files, trigger_hermes=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["products"], 1)
        self.assertEqual(previous["organizedProducts"][0]["sku"], "SKU-1")
        self.assertEqual(result["organization"]["preservedExisting"]["products"], 1)
        self.assertTrue(result["organization"]["dataLossGuard"])

    def test_organize_does_not_truncate_persisted_business_rows(self):
        """A rescan with no readable files keeps every already accepted row."""
        previous = {
            "scanFiles": [],
            "organizedProducts": [
                {"name": f"Producto {i}", "sku": f"SKU-{i}", "source": "excel"}
                for i in range(501)
            ],
            "organizedSales": [],
            "organizedCustomers": [],
        }
        previous = self._mock_store(previous)
        result = organize_files([], trigger_hermes=False)
        self.assertTrue(result["ok"])
        self.assertEqual(len(previous["organizedProducts"]), 501)

    def test_invalid_sales_go_to_review_not_metrics(self):
        """B-02 (auditoría comercial): filas con fecha imposible / total
        negativo se conservan en organizedSalesReview con evidencia y NO entran
        en organizedSales (las métricas no se contaminan)."""
        files = [{
            "name": "ventas_mixtas.csv",
            "path": "ventas_mixtas.csv",
            "ext": "csv",
            "contentPreview": (
                "order_id,customer,total,date\n"
                "O1,Acme,100,2026-01-15\n"
                "O2,Acme,95,2026-01-20\n"
                "O3,Acme,100,2026-02-01\n"
                "BAD1,Acme,100,2026-13-45\n"
                "BAD2,Acme,-100,2026-01-10\n"
            ),
        }]
        stored = self._mock_store({"scanFiles": files, "organizedSales": [], "organizedCustomers": []})
        with patch("desktop.runtime.file_organizer.task_queue.enqueue") as mock_enqueue:
            mock_enqueue.return_value = {"id": "task-x"}
            result = organize_files(files, trigger_hermes=False)
        self.assertEqual(result["sales"], 3)
        self.assertEqual(result["salesReview"], 2)
        self.assertEqual(len(stored["organizedSalesReview"]), 2)
        self.assertEqual(len(stored["organizedSales"]), 3)
        for row in stored["organizedSalesReview"]:
            self.assertEqual(row["qualityStatus"], "needs_review")
            self.assertIn("_saleIssue", row)
            self.assertIn(row["sourceFile"], ("ventas_mixtas.csv",))

    def test_reimport_invalid_sales_idempotent(self):
        """B-02: reimportar el mismo archivo no duplica ni las ventas válidas
        ni las filas en revisión (idempotencia conservada)."""
        files = [{
            "name": "ventas_mixtas.csv",
            "path": "ventas_mixtas.csv",
            "ext": "csv",
            "contentPreview": (
                "order_id,customer,total,date\n"
                "O1,Acme,100,2026-01-15\n"
                "BAD1,Acme,100,2026-13-45\n"
            ),
        }]
        stored = self._mock_store({"scanFiles": files, "organizedSales": [], "organizedCustomers": []})
        with patch("desktop.runtime.file_organizer.task_queue.enqueue") as mock_enqueue:
            mock_enqueue.return_value = {"id": "t1"}
            organize_files(files, trigger_hermes=False)
            organize_files(files, trigger_hermes=False)
        self.assertEqual(len(stored["organizedSales"]), 1)
        self.assertEqual(len(stored["organizedSalesReview"]), 1)

    def test_non_numeric_quantity_preserved_as_unknown(self):
        """B-02: una cantidad no numérica NO descarta la fila ni la convierte en
        0 — la cantidad queda UNKNOWN (None) y la fila se conserva."""
        rows = _parse_sales_dict_rows([
            {"order_id": "Q1", "total": "50", "date": "2026-01-15", "quantity": "abc"},
            {"order_id": "Q2", "total": "50", "date": "2026-01-16", "quantity": ""},
        ], "ventas.csv")
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertIsNone(row.get("quantity"))  # UNKNOWN, nunca 0
            self.assertNotIn("_saleIssue", row)     # total/fecha válidos → no inválida

    def test_existing_invalid_sales_migrated_to_review(self):
        """B-02: filas inválidas guardadas por una versión ANTERIOR (sin
        validación) se migran a organizedSalesReview al reorganizar — nunca
        contaminan el revenue posterior."""
        files = [{
            "name": "ventas_ok.csv",
            "path": "ventas_ok.csv",
            "ext": "csv",
            "contentPreview": "order_id,customer,total,date\nO1,Acme,50,2026-01-15\n",
        }]
        stored = self._mock_store({
            "scanFiles": files,
            "organizedSales": [
                {"id": "OLD-BAD", "customer": "Acme", "total": -100, "date": "2026-13-45", "source": "excel", "sourceFile": "ventas_ok.csv", "sourceRow": 3},
            ],
            "organizedCustomers": [],
        })
        with patch("desktop.runtime.file_organizer.task_queue.enqueue") as mock_enqueue:
            mock_enqueue.return_value = {"id": "t2"}
            result = organize_files(files, trigger_hermes=False)
        self.assertEqual(result["sales"], 1)  # solo la nueva válida
        self.assertEqual(result["salesReview"], 1)  # la antigua inválida migrada
        self.assertEqual(len(stored["organizedSales"]), 1)
        self.assertEqual(len(stored["organizedSalesReview"]), 1)

    def test_conflicting_product_rows_are_preserved_for_data_health(self):
        """B5: duplicate SKU and missing SKU are evidence, never discarded rows."""
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "productos_sucios.csv"
            csv_path.write_text(
                "product_name,sku,cost_price,sale_price,stock\n"
                "Producto A,DUP-1,4,10,5\n"
                "Producto B,DUP-1,7,12,8\n"
                "Artículo sin referencia,,3,9,2\n",
                encoding="utf-8",
            )
            files = [{"name": csv_path.name, "path": str(csv_path), "ext": "csv", "size": csv_path.stat().st_size}]
            stored = self._mock_store({"scanFiles": files, "organizedProducts": [], "organizedSales": [], "organizedCustomers": []})
            result = organize_files(files, trigger_hermes=False)
            products = stored["organizedProducts"]
            self.assertTrue(result["ok"])
            self.assertEqual(len(products), 3)
            duplicate_rows = [p for p in products if p.get("sku") == "DUP-1"]
            self.assertEqual(len(duplicate_rows), 2)
            self.assertTrue(all(p.get("qualityStatus") == "needs_review" for p in duplicate_rows))
            missing = next(p for p in products if not p.get("sku"))
            self.assertEqual(missing.get("qualityStatus"), "needs_review")
            self.assertEqual(missing.get("qualityReason"), "missing_sku")

    def test_conflicting_customer_rows_are_preserved_for_data_health(self):
        """B5: duplicate customer identity keeps both source records."""
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "clientes_sucios.csv"
            csv_path.write_text(
                "customer_id,name,email\n"
                "C-1,Cliente A,dup@example.test\n"
                "C-2,Cliente B,dup@example.test\n"
                "C-3,Cliente C,ok@example.test\n",
                encoding="utf-8",
            )
            files = [{"name": csv_path.name, "path": str(csv_path), "ext": "csv", "size": csv_path.stat().st_size}]
            stored = self._mock_store({"scanFiles": files, "organizedProducts": [], "organizedSales": [], "organizedCustomers": []})
            result = organize_files(files, trigger_hermes=False)
            customers = stored["organizedCustomers"]
            self.assertTrue(result["ok"])
            self.assertEqual(len(customers), 3)
            duplicate_rows = [c for c in customers if c.get("email") == "dup@example.test"]
            self.assertEqual(len(duplicate_rows), 2)
            self.assertTrue(all(c.get("qualityStatus") == "needs_review" for c in duplicate_rows))

    def test_get_sales_limits_rows_but_keeps_full_summary(self):
        """VANOVA 3.0 (red team/perf): /api/sales limita la lista de filas
        (payload) pero el resumen y totalCount cubren el dataset COMPLETO —
        nunca se pierde información ni se muestra un contador truncado."""
        sales = [
            {"id": f"ORD-{i}", "customer": f"C{i % 10}", "total": 10.0, "date": "2026-08-01"}
            for i in range(5000)
        ]
        stored = {"organizedSales": sales, "organizedProducts": [], "dataNormalizationVersion": 999}
        with patch("desktop.runtime.file_organizer.config_store") as ms:
            ms.load.return_value = stored
            result = get_sales()
        self.assertEqual(len(result["sales"]), 2000)          # payload limitado
        self.assertEqual(result["totalCount"], 5000)         # dataset completo
        self.assertEqual(result["summary"]["revenue"], 50000.0)
        self.assertEqual(result["summary"]["orders"], 5000)


if __name__ == "__main__":
    unittest.main()
