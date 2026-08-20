"""Tests for config_store setup state."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import config_store


class ConfigStoreSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.config_file = base / "config" / "maios.json"
        self.flag_file = base / ".setup_complete"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        self.config_patcher = patch.object(config_store, "CONFIG_FILE", self.config_file)
        self.flag_patcher = patch.object(config_store, "SETUP_FLAG", self.flag_file)
        self.config_patcher.start()
        self.flag_patcher.start()

    def tearDown(self):
        self.config_patcher.stop()
        self.flag_patcher.stop()
        self.tmp.cleanup()

    def test_setup_complete_from_json_only(self):
        self.config_file.write_text(json.dumps({"setupComplete": True}), encoding="utf-8")
        self.assertTrue(config_store.is_setup_complete())

    def test_reset_setup_clears_json_and_legacy_flag(self):
        self.config_file.write_text(json.dumps({"setupComplete": True}), encoding="utf-8")
        self.flag_file.write_text("", encoding="utf-8")
        config_store.reset_setup()
        data = json.loads(self.config_file.read_text(encoding="utf-8"))
        self.assertFalse(data.get("setupComplete"))
        self.assertFalse(self.flag_file.exists())
        self.assertFalse(config_store.is_setup_complete())

    def test_manual_false_not_overridden_by_missing_flag(self):
        self.config_file.write_text(json.dumps({"setupComplete": False}), encoding="utf-8")
        self.assertFalse(config_store.is_setup_complete())

    def test_atomic_save_roundtrip(self):
        config_store.save({"setupComplete": True, "companyProfile": {"name": "Test Co"}})
        loaded = config_store.load()
        self.assertTrue(loaded.get("setupComplete"))
        self.assertEqual(loaded.get("companyProfile", {}).get("name"), "Test Co")

    def test_save_skips_unchanged_payload(self):
        config_store.save({"setupComplete": True, "companyProfile": {"name": "Test Co"}})
        before = self.config_file.read_text(encoding="utf-8")
        with patch.object(config_store.log, "info") as mock_log:
            config_store.save({"setupComplete": True, "companyProfile": {"name": "Test Co"}})
            saved_calls = [str(c) for c in mock_log.call_args_list if "Configuration saved" in str(c)]
            self.assertEqual(saved_calls, [])
        after = self.config_file.read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_corrupt_config_never_clobbered_silently(self):
        """FASE 9 hardening: un maios.json corrupto se resguarda ANTES de
        guardar (nunca se pierde el archivo dañado para diagnóstico)."""
        self.config_file.write_text("{esto-no-es-json", encoding="utf-8")
        loaded = config_store.load()
        self.assertTrue(config_store._config_corrupt)
        self.assertFalse(loaded.get("setupComplete"))  # defaults, sin crash

        config_store.save({"setupComplete": True})

        # El archivo corrupto se movió a un resguardo con timestamp
        corrupt_backups = list(self.config_file.parent.glob("maios.corrupt-*.json"))
        self.assertEqual(len(corrupt_backups), 1)
        self.assertIn("esto-no-es-json", corrupt_backups[0].read_text(encoding="utf-8"))
        # El config nuevo es válido y contiene el dato guardado
        self.assertTrue(config_store.is_setup_complete())
        self.assertFalse(config_store._config_corrupt)

    def test_corrupt_config_load_is_recoverable(self):
        """Tras resguardar el corrupto, el sistema sigue funcionando con defaults
        y la siguiente carga ya no lo marca como corrupto."""
        self.config_file.write_text("{", encoding="utf-8")
        config_store.load()
        config_store.save({"companyProfile": {"name": "Recovered"}})
        self.assertFalse(config_store._config_corrupt)
        self.assertEqual(config_store.load().get("companyProfile", {}).get("name"), "Recovered")

    # ------------------------------------------------------------------
    # remove_keys / reset_to_defaults — escritura COMPLETA (no merge):
    # clave de la limpieza «limpiar y volver a importar» y del factory reset.
    # ------------------------------------------------------------------

    def test_remove_keys_truly_deletes_from_disk(self):
        # save() MERGEA: hacer pop sobre el dict cargado no borra nada en disco.
        # remove_keys debe reescribir el archivo SIN las claves indicadas.
        config_store.save({
            "setupComplete": True,
            "organizedProducts": [{"sku": "A"}],
            "businessFindings": [{"id": "f1"}],
            "insights": [{"id": "i1"}],
            "customUserKey": {"x": 1},
        })
        config_store.remove_keys(["organizedProducts", "businessFindings", "insights"])
        on_disk = json.loads(self.config_file.read_text(encoding="utf-8"))
        self.assertNotIn("organizedProducts", on_disk)
        self.assertNotIn("businessFindings", on_disk)
        self.assertNotIn("insights", on_disk)
        # Lo que no se pidió eliminar sobrevive
        self.assertTrue(on_disk.get("setupComplete"))
        self.assertEqual(on_disk.get("customUserKey"), {"x": 1})

    def test_remove_keys_does_not_merge_defaults_back_into_disk(self):
        config_store.save({"setupComplete": True, "organizedProducts": [{"sku": "A"}]})
        config_store.remove_keys(["organizedProducts"])
        on_disk = json.loads(self.config_file.read_text(encoding="utf-8"))
        self.assertNotIn("organizedProducts", on_disk)
        # load() sigue siendo seguro (los defaults se aplican solo en memoria)
        self.assertEqual(config_store.load().get("organizedProducts"), [])

    def test_reset_to_defaults_replaces_everything(self):
        config_store.save({
            "setupComplete": True,
            "companyProfile": {"name": "Mi Empresa"},
            "organizedProducts": [{"sku": "A"}],
            "businessFindings": [{"id": "f1"}],
            "insights": [{"id": "i1"}],
            "recommendations": [{"id": "r1"}],
            "companyModel": {"memory": "x"},
            "importantItems": [{"id": "im1"}],
            "scanFolders": ["C:/X"],
            "aiProviders": {"hermes": {"key": "k"}},
            "customUserKey": {"x": 1},
        })
        fresh = config_store.reset_to_defaults()
        on_disk = json.loads(self.config_file.read_text(encoding="utf-8"))
        # Claves que NO existen en los defaults desaparecen del archivo
        for k in ("businessFindings", "insights", "recommendations", "companyModel",
                  "importantItems", "scanFolders", "customUserKey"):
            self.assertNotIn(k, on_disk, k)
        # Claves de defaults quedan vacías (el CONTENIDO del usuario se perdió)
        self.assertEqual(on_disk.get("companyProfile"), {})
        self.assertEqual(on_disk.get("aiProviders"), {})
        self.assertEqual(on_disk.get("organizedProducts"), [])
        self.assertFalse(fresh.get("setupComplete"))
        # Estado de primera instalación
        self.assertEqual(config_store.load().get("organizedProducts"), [])
        self.assertEqual(config_store.load().get("setupComplete"), False)
        self.assertEqual(config_store.load().get("companyProfile"), {})

    def test_reset_to_defaults_keeps_system_version(self):
        config_store.save({"setupComplete": True, "customUserKey": 1})
        fresh = config_store.reset_to_defaults()
        self.assertTrue(fresh.get("version"))  # lee version.json, no se pierde
        on_disk = json.loads(self.config_file.read_text(encoding="utf-8"))
        self.assertNotIn("customUserKey", on_disk)


if __name__ == "__main__":
    unittest.main()
