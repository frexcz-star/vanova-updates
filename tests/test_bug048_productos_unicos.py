"""BUG real (Nico, producción): el catálogo mostraba ~4000 productos cuando el
catálogo real tiene 400. Root cause: el importador marca duplicados como
'needs_review' (duplicate_sku) pero los MANTIENE todos en organizedProducts;
get_products() contaba las FILAS BRUTAS (4000) en vez de los SKU únicos (400).

Fix: file_organizer.get_products() y agent_data_tools get_products/availability
colapsan por SKU/nombre (devuelven productos ÚNICOS), conservando los duplicados
marcados en organizedProducts para la vista de revisión 'Vincula tus productos'.

Falla con el código anterior (get_products devolvía count=4000 con duplicados).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ProductCatalogUniqueTests(unittest.TestCase):
    """El catálogo de productos debe ser ÚNICO por SKU/nombre, no filas brutas."""

    def _fake_organized(self):
        # 400 SKU únicos, cada uno duplicado 10x (4000 filas brutas)
        products = []
        for i in range(400):
            row = {
                "sku": f"SKU-{i:03d}",
                "name": f"Producto {i}",
                "netPrice": 10.0,
                "rrp": 12.0,
            }
            for _ in range(5):
                dup = dict(row, qualityStatus="needs_review", qualityReason="duplicate_sku")
                products.append(dup)
            products.append(row)  # la fila "buena" original
        return products

    def test_get_products_devuelve_unicos(self):
        from desktop.runtime import file_organizer

        fake = {"organizedProducts": self._fake_organized()}
        with patch.object(file_organizer, "config_store") as cs:
            cs.load.return_value = fake
            with patch.object(file_organizer, "_ensure_normalized_data", lambda: None):
                res = file_organizer.get_products()
        # 400 SKU únicos, no 2400 filas brutas (400 x 6)
        self.assertEqual(res["count"], 400, f"el catálogo debe tener 400 únicos, no {res['count']}")
        self.assertEqual(len(res["products"]), 400)

    def test_agent_data_tools_get_products_devuelve_unicos(self):
        from desktop.runtime import agent_data_tools

        with patch.object(agent_data_tools, "_products", return_value=self._fake_organized()):
            res = agent_data_tools.get_products()
        self.assertEqual(res["count"], 400, f"get_products debe contar 400 únicos, no {res['count']}")

    def test_agent_data_tools_availability_cuenta_unicos(self):
        from desktop.runtime import agent_data_tools

        with patch.object(agent_data_tools, "_products", return_value=self._fake_organized()):
            with patch.object(agent_data_tools, "_sales", return_value=[]):
                with patch.object(agent_data_tools, "_customers", return_value=[]):
                    with patch.object(agent_data_tools, "_files", return_value=[]):
                        res = agent_data_tools.availability()
        self.assertEqual(res["products"]["count"], 400, f"availability debe contar 400 únicos, no {res['products']['count']}")


if __name__ == "__main__":
    unittest.main()
