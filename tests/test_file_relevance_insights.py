"""Tests for selective file relevance, insight store, and candidate approval."""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.runtime import business_scanner, file_relevance, insight_actions, insight_store
from desktop.runtime.file_inventory import decide_candidate, list_candidates
from desktop.runtime.task_queue import _record_routine_insight


class FileRelevanceTests(unittest.TestCase):
    def test_strong_business_names_are_confident(self):
        for name in ("factura_2026_001.pdf", "ventas_q1_2026.csv", "catalogo_precios.xlsx",
                     "pedidos_enero.csv", "datos_clientes.xlsx", "listado_productos.csv"):
            score = file_relevance.score_file(name)
            self.assertGreaterEqual(score, 3, f"{name} -> {score}")
            record = {"name": name, "folderScore": 0, "fileScore": score, "contentScore": 0}
            self.assertEqual(file_relevance.classify_scan_record(record), "confident", name)

    def test_personal_files_are_dropped(self):
        for name in ("recetas_cocina.xlsx", "gastos_casa.xlsx", "fotos_vacaciones.xlsx",
                     "apuntes_universidad.docx", "rutina_gimnasio.csv", "horoscopo.pdf"):
            self.assertLess(file_relevance.score_file(name), 0, name)

    def test_weak_names_are_candidates_unless_content_confirms(self):
        name = "informe_q1.xlsx"
        self.assertEqual(file_relevance.score_file(name), 1)  # informe (weak)
        # Weak name alone, no business content -> skip (precision over recall).
        skip = {"name": name, "folderScore": 0, "fileScore": 1, "contentScore": 0}
        self.assertEqual(file_relevance.classify_scan_record(skip), "skip")
        # Weak name + a content signal -> candidate (ask the owner).
        cand = {"name": name, "folderScore": 0, "fileScore": 1, "contentScore": 1}
        self.assertEqual(file_relevance.classify_scan_record(cand), "candidate")
        # Weak name + strong business content -> confident.
        conf = {"name": name, "folderScore": 0, "fileScore": 1, "contentScore": 3}
        self.assertEqual(file_relevance.classify_scan_record(conf), "confident")

    def test_folder_pruning(self):
        for folder in ("Música", "Videos", "juegos", "AppData", "node_modules", "imágenes"):
            self.assertLess(file_relevance.score_folder(folder), 0, folder)
        self.assertGreater(file_relevance.score_folder("Facturas"), 0)
        self.assertGreater(file_relevance.score_folder("Clientes 2026"), 0)

    def test_content_scoring(self):
        business = "sku,producto,precio,cantidad,fecha\nA1,Libreta,5.50,100,2026-01-01\nA2,Boligrafo,1.20,250,2026-01-02\n"
        self.assertGreaterEqual(file_relevance.score_content(business), 3)
        personal = "ingredientes, cantidad\nharina, 500\ngramos, 200\n"
        self.assertLess(file_relevance.score_content(personal), 3)


class InsightStoreTests(unittest.TestCase):
    def test_record_and_list(self):
        stored: dict = {}
        with patch("desktop.runtime.config_store.load", return_value=stored), patch(
            "desktop.runtime.config_store.save", side_effect=lambda data: stored.update(data)
        ):
            insight_store.record("marketing-agent", "Marketing Agent", title="Informe", summary="Hallazgos")
            insight_store.record("sales-agent", "Sales Copilot", title="Informe", summary="Ventas ok")
            items = insight_store.list_insights()
            self.assertEqual(len(items), 2)
            self.assertEqual(insight_store.count_by_agent().get("marketing-agent"), 1)
            latest = insight_store.latest_for_agent("marketing-agent")
            self.assertEqual(latest["summary"], "Hallazgos")

    def test_routine_completion_records_insight(self):
        task = {"id": "t1", "agentId": "marketing-agent", "type": "scheduled", "status": "completed"}
        stored: dict = {}
        with patch("desktop.runtime.config_store.load", return_value=stored), patch(
            "desktop.runtime.config_store.save", side_effect=lambda data: stored.update(data)
        ), patch("desktop.runtime.task_queue._load_agent", return_value={"name": "Marketing Agent"}):
            _record_routine_insight(task, "Resultado de la rutina")
            self.assertIn("insights", stored)
            self.assertEqual(stored["insights"][0]["summary"], "Resultado de la rutina")
            # Manual tasks must NOT become insights
            manual = {"id": "t2", "agentId": "marketing-agent", "type": "manual", "status": "completed"}
            _record_routine_insight(manual, "Resultado manual")
            self.assertEqual(len(stored["insights"]), 1)

    def test_actioned_routine_keeps_identity_and_stays_hidden(self):
        stored: dict = {}
        with patch("desktop.runtime.config_store.load", return_value=stored), patch(
            "desktop.runtime.config_store.save", side_effect=lambda data: stored.update(data)
        ), patch.object(insight_actions, "load_all", return_value={}):
            first = insight_store.record(
                "sales-agent", "Sales Agent", title="Informe de rutina", summary="Primero",
                meta={"routineKey": "scheduled:sales-agent"},
            )
            action = {first["id"]: "dismissed"}
            with patch.object(insight_actions, "load_all", return_value=action):
                second = insight_store.record(
                    "sales-agent", "Sales Agent", title="Informe de rutina", summary="Segundo",
                    meta={"routineKey": "scheduled:sales-agent"},
                )
                self.assertEqual(second["id"], first["id"])
                self.assertEqual(insight_store.list_insights(), [])


class SelectiveScanTests(unittest.TestCase):
    def test_scan_only_keeps_business_files(self):
        """The exact client bug: files with no company info must not be imported."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Documents"
            (root / "Facturas 2026").mkdir(parents=True)
            (root / "Música").mkdir(parents=True)
            (root / "Fotos").mkdir(parents=True)
            (root / "Facturas 2026").joinpath("factura_001.pdf").write_text("pdf", encoding="utf-8")
            (root / "Facturas 2026").joinpath("ventas_q1.csv").write_text(
                "order,customer,total,date\nO1,Acme,99.5,2026-01-01\n", encoding="utf-8"
            )
            (root / "Música").joinpath("canciones.csv").write_text("song,artist\nX,Y\n", encoding="utf-8")
            (root / "Fotos").joinpath("album_fotos.xlsx").write_bytes(b"not-really-xlsx")
            (root / "gastos_casa.csv").write_text("total,fecha\n10,2026-01-01\n", encoding="utf-8")
            (root / "recetas_cocina.csv").write_text("ingrediente,cantidad\nharina,500\n", encoding="utf-8")
            (root / "informe_sin_contenido.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
            (root / "listado_clientes.csv").write_text(
                "cliente,nif,telefono,email\nAcme,B123,555,acme@x.com\n", encoding="utf-8"
            )

            stored: dict = {}
            with patch.object(business_scanner, "scan_dirs", lambda: [root]), patch.object(
                business_scanner, "MAX_SCAN_SECONDS", 10
            ), patch.object(business_scanner, "config_store") as mock_store:
                mock_store.load.return_value = stored
                mock_store.save.side_effect = lambda data: stored.update(data)
                found = business_scanner._scan_files(time.monotonic())
                candidates = stored.get("fileCandidates") or []

            paths = {str(p.get("path")) for p in found}
            self.assertIn("factura_001.pdf", " ".join(paths))  # invoice -> confident
            self.assertTrue(any("ventas_q1.csv" in p for p in paths))
            self.assertTrue(any("listado_clientes.csv" in p for p in paths))
            # Personal / non-business files must NOT be imported.
            self.assertFalse(any("canciones" in p for p in paths), paths)
            self.assertFalse(any("gastos_casa" in p for p in paths), paths)
            self.assertFalse(any("recetas_cocina" in p for p in paths), paths)
            self.assertFalse(any("album_fotos" in p for p in paths), paths)
            self.assertTrue(
                any("informe_sin_contenido" in (c.get("name") or "") for c in candidates),
                candidates,
            )


class CandidateApprovalTests(unittest.TestCase):
    def test_decide_approve_imports_and_reject_drops(self):
        cand = {"path": "C:/datos/informe_q1.csv", "name": "informe_q1.csv", "ext": "csv",
                "size": 100, "status": "pending", "folderScore": 0, "fileScore": 1, "contentScore": 0}
        stored: dict = {"fileCandidates": [dict(cand)], "scanFiles": []}

        def _save(data):
            stored.update(data)

        with patch("desktop.runtime.config_store.load", return_value=stored), patch(
            "desktop.runtime.config_store.save", side_effect=_save
        ), patch("desktop.runtime.file_inventory._organize_after_import") as mock_org:
            self.assertEqual(list_candidates()["count"], 1)
            r = decide_candidate(cand["path"], approve=True)
            self.assertTrue(r["ok"])
            self.assertEqual(stored["fileCandidates"][0]["status"], "approved")
            self.assertEqual(stored["scanFiles"][0]["source"], "approved")
            mock_org.assert_called_once()
            # Approved candidates no longer show as pending
            self.assertEqual(list_candidates()["count"], 0)

        cand2 = {"path": "C:/datos/otro.csv", "name": "otro.csv", "ext": "csv", "size": 50,
                 "status": "pending", "folderScore": 0, "fileScore": 1, "contentScore": 0}
        stored2: dict = {"fileCandidates": [dict(cand2)], "scanFiles": []}
        with patch("desktop.runtime.config_store.load", return_value=stored2), patch(
            "desktop.runtime.config_store.save", side_effect=lambda data: stored2.update(data)
        ):
            r2 = decide_candidate(cand2["path"], approve=False)
            self.assertTrue(r2["ok"])
            self.assertEqual(stored2["fileCandidates"][0]["status"], "rejected")
            self.assertEqual(stored2["scanFiles"], [])


if __name__ == "__main__":
    unittest.main()
