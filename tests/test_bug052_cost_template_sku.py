"""BUG real (Nico, audit.jsonl): la plantilla de costes ('cost_template') incluía
productos SIN SKU (sku="") — p.ej. `skus: ["SKU-2", ""]`. Un producto sin SKU no
tiene identidad para vincular el coste al importar la plantilla → fila inútil/rota.

Fix: prepare_cost_template excluye los productos sin SKU de la plantilla de costes.
Falla con el código anterior (incluía el producto con sku="").
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class CostTemplateExcludesNoSkuTests(unittest.TestCase):
    """La plantilla de costes NO debe incluir productos sin SKU."""

    def test_plantilla_costes_excluye_productos_sin_sku(self):
        from desktop.runtime import action_center

        products = [
            {"sku": "SKU-1", "name": "Con SKU", "cost": None},       # sin coste, con SKU -> debe ir
            {"sku": "SKU-2", "name": "Con SKU 2", "cost": None},     # sin coste, con SKU -> debe ir
            {"name": "Sin SKU", "cost": None},                        # sin SKU -> NO debe ir
            {"sku": "", "name": "SKU vacio", "cost": None},           # SKU vacio -> NO debe ir
        ]
        data = {"organizedProducts": products}

        # mock product_identity.resolve_cost para que devuelva costStatus="missing" en todos
        fake_identity = type("Fake", (), {
            "resolve_cost": lambda p: {"costStatus": "missing", "cost": None}
        })

        with patch("desktop.runtime.product_identity.resolve_cost", side_effect=fake_identity.resolve_cost):
            res = action_center.prepare_cost_template(data)

        skus = [r["sku"] for r in res.get("rows", [])]
        # Solo SKU-1 y SKU-2 (los que tienen SKU); NO el sin-SKU ni el vacío
        self.assertIn("SKU-1", skus)
        self.assertIn("SKU-2", skus)
        self.assertNotIn("", [r["sku"] for r in res["rows"]], "no debe incluir productos sin SKU")
        self.assertEqual(len(skus), 2, f"debe haber 2 productos con SKU, hay {len(skus)}")


if __name__ == "__main__":
    unittest.main()
