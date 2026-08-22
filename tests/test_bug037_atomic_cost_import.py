"""BUG-037 — RMW atómico en apply() de cost_importer (lost-update).

Root cause: apply() hacía load() → modificar catalog (copia local) →
config_store.save({"organizedProducts": catalog}) SOBRESCRIBIENDO la lista
completa. Si otro hilo añadía productos entre el load y el save, se perdían
(patrón BUG-006/015/019/023/034).

Fix: usar config_store.update() que re-aplica los costes al catálogo ACTUAL
dentro del _config_lock, sin sobrescribir productos agregados por otros hilos.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import config_store
from desktop.runtime import cost_importer


def _product(sku, name="Prod", cost=None):
    return {"sku": sku, "name": name, "netPrice": 10.0, "rrp": 12.0, "cost": cost}


class Bug037CostImporterAtomicRmwTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self._config_patch = patch.object(config_store, "CONFIG_FILE", Path(tmp) / "maios.json")
        self._config_patch.start()
        self.addCleanup(self._config_patch.stop)
        # Reset estado (si el módulo cachea algo).
        if hasattr(config_store, "_DATA"):
            patch.object(config_store, "_DATA", None).start()
        # Config base con un producto sin coste.
        config_store.save({"organizedProducts": [_product("SKU-A")]})

    def test_apply_uses_update_not_save(self):
        """BUG-037: apply() persiste con config_store.update (atómico), no save()."""
        rows = [{"sku": "SKU-A", "cost": 5.0, "ean": "", "sourceReference": "t"}]
        with patch.object(config_store, "save", wraps=config_store.save) as mock_save, \
             patch.object(config_store, "update", wraps=config_store.update) as mock_update:
            res = cost_importer.apply(rows, cost_source="supplier", persist=True)
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(res.get("applied"), 1)
        mock_update.assert_called_once()
        # El catálogo persiste con el coste aplicado.
        prods = config_store.load().get("organizedProducts")
        self.assertEqual(prods[0]["cost"], 5.0)
        self.assertEqual(prods[0]["costStatus"], "verified")

    def test_no_lost_update_on_concurrent_product(self):
        """BUG-037: aplicar coste no pierde un producto añadido por otro hilo."""
        rows = [{"sku": "SKU-A", "cost": 5.0, "price": "", "sourceReference": "t"}]
        # Simular que, dentro del mutator, otro código añade un producto nuevo.
        real_update = config_store.update

        def _mutate_with_extra(mutator):
            def wrapped(cfg):
                result = mutator(cfg)
                if result is not None:
                    # otro hilo añade un producto DURANTE el RMW (mismo lock, no se pierde)
                    prods = list(result.get("organizedProducts") or [])
                    if not any(p.get("sku") == "SKU-NEW" for p in prods):
                        prods.append(_product("SKU-NEW", cost=3.0))
                        result["organizedProducts"] = prods
                return result
            return real_update(wrapped)

        with patch.object(config_store, "update", side_effect=_mutate_with_extra):
            res = cost_importer.apply(rows, cost_source="supplier", persist=True)
        self.assertTrue(res["ok"])
        prods = config_store.load().get("organizedProducts") or []
        skus = {p["sku"] for p in prods}
        # el coste de SKU-A se aplicó
        self.assertIn("SKU-A", skus)
        # y el producto añadido por "otro hilo" NO se pierde
        self.assertIn("SKU-NEW", skus)
        sku_a = next(p for p in prods if p["sku"] == "SKU-A")
        self.assertEqual(sku_a["cost"], 5.0)


if __name__ == "__main__":
    unittest.main()
