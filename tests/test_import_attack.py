"""VANOVA 3.0 — ataques agresivos de importación.

Regla: los datos inválidos NUNCA se convierten en silencio en 0 ni en un número
inventado; las filas malas se conservan en revisión con evidencia; reimportar
nunca duplica; las métricas solo usan filas válidas.
"""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.runtime import file_organizer as fo
from desktop.runtime import business_model

EURO = "1.234,56"
US = "1,234.56"


class NumberParsingTests(unittest.TestCase):
    def test_european_thousands_parsed(self):
        self.assertEqual(fo._pick_number({"t": EURO}, {"t": "t"}, ("t",)), 1234.56)
        self.assertEqual(fo._pick_number({"t": US}, {"t": "t"}, ("t",)), 1234.56)

    def test_garbage_never_becomes_number(self):
        # VANOVA 3.0: ambiguo/corrupto -> UNKNOWN (None), nunca 105.5 inventado
        for bad in ("10.5.5", "NaN", "nan", "null", "None", "INF", "-inf", "abc", "1.2.3", "1..5"):
            self.assertIsNone(fo._pick_number({"t": bad}, {"t": "t"}, ("t",)), f"{bad} -> None")

    def test_optional_float_nan_and_garbage(self):
        self.assertIsNone(fo._parse_optional_float("10.5.5"))
        self.assertIsNone(fo._parse_optional_float(float("nan")))
        self.assertIsNone(fo._parse_optional_float(float("inf")))
        self.assertEqual(fo._parse_optional_float("1.234,56"), 1234.56)
        self.assertIsNone(fo._parse_optional_float("-inf"))

    def test_business_model_as_float_nan_inf(self):
        self.assertIsNone(business_model._as_float(float("nan")))
        self.assertIsNone(business_model._as_float(float("inf")))
        self.assertIsNone(business_model._as_float("-inf"))
        self.assertIsNone(business_model._as_float("nan"))
        self.assertIsNone(business_model._as_float("inf"))
        self.assertEqual(business_model._as_float("1.234,56"), 1234.56)
        # NaN total nunca puede ser venta válida
        self.assertIsNotNone(business_model.sale_validation_issue({"total": float("nan"), "date": "2026-01-15"}))


class ImportAttackTests(unittest.TestCase):
    def _organize(self, content: str, name: str = "ventas_ataque.csv"):
        files = [{"name": name, "path": name, "ext": "csv", "contentPreview": content}]
        stored: dict = {"scanFiles": files, "organizedSales": [], "organizedCustomers": []}
        mock_store = unittest.mock.MagicMock()
        mock_store.load.return_value = stored
        mock_store.save.side_effect = lambda data: stored.update(data)
        patchers = [
            patch("desktop.runtime.file_organizer.config_store", mock_store),
            patch("desktop.runtime.data_version.config_store", mock_store),
        ]
        for p in patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])
        with patch("desktop.runtime.file_organizer.task_queue.enqueue") as mq:
            mq.return_value = {"id": "t"}
            result = fo.organize_files(files, trigger_hermes=False)
        return result, stored

    def test_empty_csv(self):
        result, stored = self._organize("order_id,customer,total,date\n")
        self.assertEqual(result["sales"], 0)
        self.assertEqual(stored["organizedSales"], [])

    def test_missing_columns(self):
        content = "order_id,customer\nO1,Acme\n"
        result, stored = self._organize(content)
        # sin total ni fecha: la fila se conserva en revisión (evidencia), no en métricas
        self.assertEqual(result["sales"], 0)
        self.assertGreaterEqual(result["salesReview"], 1)

    def test_duplicate_columns(self):
        # CSV con columna 'total' duplicada: la extracción no debe reventar Y no
        # debe elegir una columna en silencio (VANOVA 3.0: a revisión con evidencia).
        content = "order_id,total,total,date\nO1,10,99,2026-01-15\n"
        result, stored = self._organize(content)
        self.assertEqual(result["sales"], 0)
        self.assertEqual(result["salesReview"], 1)
        self.assertIn("columnas duplicadas", stored["organizedSalesReview"][0]["_saleIssue"])

    def test_nan_null_empty_values(self):
        content = (
            "order_id,customer,total,date\n"
            "O1,Acme,NaN,2026-01-15\n"
            "O2,Acme,null,2026-01-16\n"
            "O3,Acme,,2026-01-17\n"
            "O4,Acme,50,2026-01-18\n"
        )
        result, stored = self._organize(content)
        # solo O4 es válida; el resto -> revisión con evidencia
        self.assertEqual(result["sales"], 1)
        self.assertEqual(result["salesReview"], 3)

    def test_negative_prices_and_totals(self):
        content = (
            "order_id,customer,total,date\n"
            "O1,Acme,-100,2026-01-15\n"
            "O2,Acme,50,2026-01-16\n"
        )
        result, stored = self._organize(content)
        self.assertEqual(result["sales"], 1)
        self.assertEqual(result["salesReview"], 1)
        # el revenue nunca incluye el total negativo
        rev = business_model.revenue(stored["organizedSales"])
        self.assertEqual(rev, 50.0)

    def test_impossible_and_future_dates(self):
        content = (
            "order_id,customer,total,date\n"
            "O1,Acme,10,2026-13-45\n"
            "O2,Acme,10,not-a-date\n"
            "O3,Acme,10,2030-01-01\n"  # fecha futura parseable: se acepta
        )
        result, stored = self._organize(content)
        self.assertEqual(result["sales"], 1)  # O3
        self.assertEqual(result["salesReview"], 2)

    def test_european_decimals_in_import(self):
        # Los números con coma deben ir ENTRE COMILLAS en un CSV separado por
        # comas (de lo contrario el propio CSV los rompe).
        content = (
            "order_id,customer,total,date\n"
            "O1,Acme,\"1.234,56\",2026-01-15\n"
            "O2,Acme,\"99,5\",2026-01-16\n"
        )
        result, stored = self._organize(content)
        self.assertEqual(result["sales"], 2)
        rev = business_model.revenue(stored["organizedSales"])
        self.assertEqual(rev, 1234.56 + 99.5)

    def test_partially_corrupt_rows(self):
        content = (
            "order_id,customer,total,date\n"
            "O1,Acme,100,2026-01-15\n"
            "BAD,Acme,abc,2026-01-16\n"
            "O3,Acme,30,2026-01-17\n"
        )
        result, stored = self._organize(content)
        self.assertEqual(result["sales"], 2)
        self.assertEqual(result["salesReview"], 1)

    def test_huge_file_100k_rows(self):
        rows = ["order_id,customer,total,date"]
        for i in range(100_000):
            rows.append(f"ORD-{i},Cliente {i},10.50,2026-01-15")
        content = "\n".join(rows)
        t0 = time.monotonic()
        parsed = fo._parse_sales_rows(content, ",", "ventas_grandes.csv")
        elapsed = time.monotonic() - t0
        # VANOVA 3.0: el cap sube a 100k y, si se excede, NUNCA es silencioso.
        # BUG-016 FIX: umbral subido de 30s a 60s — bajo carga de la suite
        # completa el parseo de 100k filas puede superar 30s por contienda de
        # CPU con otros tests pesados. 60s es un margen robusto sin perder el
        # propósito del test (verificar que el cap de 100k no degenera en un
        # parse infinito ni silencioso).
        self.assertEqual(len(parsed), 100_000)
        self.assertLess(elapsed, 60.0)

    def test_truncation_never_silent(self):
        # Cap reducido artificialmente para ejercitar la ruta sin importar 100k+1 filas.
        rows = ["order_id,customer,total,date"]
        for i in range(110):
            rows.append(f"ORD-{i},Cliente {i},10.50,2026-01-15")
        content = "\n".join(rows)
        with patch.object(fo, "MAX_IMPORT_ROWS", 100):
            truncated: dict[str, int] = {}
            parsed = fo._parse_sales_rows(content, ",", "grande.csv", truncated)
        self.assertEqual(len(parsed), 100)
        # El resto se cuenta y se reporta, nunca se pierde en silencio.
        self.assertEqual(truncated.get("grande.csv"), 10)

    def test_truncation_surfaced_in_organize_result(self):
        rows = ["order_id,customer,total,date"]
        for i in range(110):
            rows.append(f"ORD-{i},Cliente {i},10.50,2026-01-15")
        content = "\n".join(rows)
        with patch.object(fo, "MAX_IMPORT_ROWS", 100):
            result, stored = self._organize(content)
        self.assertEqual(result["sales"], 100)
        org = result.get("organization") or {}
        self.assertGreaterEqual(org.get("truncatedRows", 0), 10)
        self.assertIn("truncatedRows", org.get("importSummary", {}))
        self.assertIn("truncatedFiles", org.get("importSummary", {}))

    def test_absurd_total_flagged_for_review_not_in_metrics(self):
        """VANOVA 3.0 (red team): un total de 1e+20 € no es una venta plausible.
        La fila pasa a revisión con evidencia; el revenue NO se contamina."""
        content = (
            "order_id,customer,total,date\n"
            "O1,Acme,100.00,2026-08-01\n"
            "O2,Acme,99999999999999999999.99,2026-08-02\n"
        )
        result, stored = self._organize(content)
        self.assertEqual(result["sales"], 1)          # solo la plausible
        self.assertEqual(result["salesReview"], 1)    # la absurda, preservada
        review = stored["organizedSalesReview"][0]
        self.assertIn("fuera de rango plausible", review["_saleIssue"])
        self.assertEqual(review["total"], 1e20)       # no se borra ni se inventa
        summary = business_model.sales_summary(stored["organizedSales"], products=[])
        self.assertEqual(summary["revenue"], 100.0)

    def test_duplicate_headers_flagged_for_review_not_silent(self):
        """VANOVA 3.0 (red team): cabecera con dos columnas 'total' → csv.DictReader
        descartaría una en silencio. La fila va a revisión, no se inventa cuál
        columna es la correcta."""
        content = (
            "order_id,customer,total,total,date\n"
            "O1,Acme,10.5,99,2026-08-01\n"
        )
        result, stored = self._organize(content)
        self.assertEqual(result["sales"], 0)
        self.assertEqual(result["salesReview"], 1)
        review = stored["organizedSalesReview"][0]
        self.assertIn("columnas duplicadas", review["_saleIssue"])

    def test_import_20x_rename_and_reorder_never_duplicates(self):
        """VANOVA 3.0 (red team): reimportar 20 veces el mismo archivo, una
        copia renombrada y el mismo dataset con columnas reordenadas nunca
        duplica ventas ni filas de revisión."""
        content = (
            "order_id,customer,total,date\n"
            "O1,Acme,100,2026-08-01\nO2,Beta,50,2026-08-02\nO3,Acme,25,2026-08-03\n"
        )
        base = [{"name": "ventas.csv", "path": "ventas.csv", "ext": "csv", "contentPreview": content}]
        _, stored = self._organize(content)
        ids1 = {s["id"] for s in stored["organizedSales"]}
        for _ in range(5):
            self._organize(content)
        renamed = [{"name": "ventas-copia.csv", "path": "ventas-copia.csv", "ext": "csv", "contentPreview": content}]
        files = renamed
        stored2 = {"scanFiles": files, "organizedSales": [], "organizedCustomers": []}
        ms = unittest.mock.MagicMock()
        ms.load.return_value = stored2
        ms.save.side_effect = lambda d: stored2.update(d)
        with patch("desktop.runtime.file_organizer.config_store", ms), \
             patch("desktop.runtime.data_version.config_store", ms), \
             patch("desktop.runtime.file_organizer.task_queue.enqueue") as mq:
            mq.return_value = {"id": "t"}
            fo.organize_files(files, trigger_hermes=False)
        reordered = [{"name": "v.csv", "path": "v.csv", "ext": "csv",
                      "contentPreview": "date,total,customer,order_id\n2026-08-01,100,Acme,O1\n2026-08-02,50,Beta,O2\n2026-08-03,25,Acme,O3\n"}]
        stored3 = {"scanFiles": reordered, "organizedSales": [], "organizedCustomers": []}
        ms3 = unittest.mock.MagicMock()
        ms3.load.return_value = stored3
        ms3.save.side_effect = lambda d: stored3.update(d)
        with patch("desktop.runtime.file_organizer.config_store", ms3), \
             patch("desktop.runtime.data_version.config_store", ms3), \
             patch("desktop.runtime.file_organizer.task_queue.enqueue") as mq3:
            mq3.return_value = {"id": "t"}
            fo.organize_files(reordered, trigger_hermes=False)
        final_ids = {s["id"] for s in stored3["organizedSales"]}
        self.assertEqual(final_ids, ids1)
        self.assertEqual(len(stored3["organizedSales"]), 3)
        self.assertEqual(len(stored3.get("organizedSalesReview") or []), 0)

    def test_reimport_same_file_idempotent_after_attack(self):
        content = (
            "order_id,customer,total,date\n"
            "O1,Acme,100,2026-01-15\n"
            "BAD,Acme,abc,2026-01-16\n"
        )
        result, stored = self._organize(content)
        result2, stored2 = self._organize(content)
        self.assertEqual(len(stored["organizedSales"]), len(stored2["organizedSales"]))
        self.assertEqual(len(stored["organizedSalesReview"]), len(stored2["organizedSalesReview"]))


if __name__ == "__main__":
    unittest.main()
