"""Shopify sync pagination tests (Hallazgo #4 regression).

The previous implementation requested `?limit=50` without following Shopify's
`Link` header cursor, silently truncating any catalog larger than one page
(e.g. a store with 462 products was stored as 50). These tests pin the fix.
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import shopify_sync

URL = "https://demo.myshopify.com"
TOKEN = "shpat_test_token"


class _FakeResp:
    def __init__(self, body: dict, link: str = ""):
        self._body = body
        self._link = link

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self._body).encode("utf-8")

    @property
    def headers(self):
        return {"Link": self._link}


class ShopifySyncPaginationTests(unittest.TestCase):
    def test_single_page_returns_all_items(self):
        payload = {"products": [{"id": i} for i in range(3)]}
        with patch("desktop.runtime.shopify_sync.urlopen", return_value=_FakeResp(payload)):
            items = shopify_sync._shopify_get_all(URL, TOKEN, "/admin/api/2024-01/products.json")
        self.assertEqual(len(items), 3)

    def test_follows_cursor_until_last_page(self):
        """Regression: a 2-page catalog (462 products @ 250/page) must not truncate."""
        pages = {
            "next_cursor_2": {
                "body": {"products": [{"id": 300 + i} for i in range(200)]},
                "link": "",
            }
        }

        def fake_urlopen(req, timeout=25):
            q = req.full_url
            if "page_info=" not in q:
                body = {"products": [{"id": i} for i in range(250)]}
                return _FakeResp(body, '<https://x/next?page_info=next_cursor_2>; rel="next"')
            # Second page
            return _FakeResp(pages["next_cursor_2"]["body"], "")

        with patch("desktop.runtime.shopify_sync.urlopen", side_effect=fake_urlopen):
            items = shopify_sync._shopify_get_all(URL, TOKEN, "/admin/api/2024-01/products.json", limit=250)

        self.assertEqual(len(items), 450)
        self.assertEqual(items[0]["id"], 0)
        self.assertEqual(items[-1]["id"], 499)

    def test_does_not_truncate_at_50(self):
        """The original bug: limit=50 with >50 products dropped everything after page 1."""
        payload = {"products": [{"id": i} for i in range(120)]}
        # Old code called _shopify_get with limit=50 and got 50 items back.
        # New code uses _shopify_get_all with limit=250, so a single response
        # of 120 items must be preserved in full.
        with patch("desktop.runtime.shopify_sync.urlopen", return_value=_FakeResp(payload)):
            items = shopify_sync._shopify_get_all(URL, TOKEN, "/admin/api/2024-01/products.json", limit=250)
        self.assertEqual(len(items), 120)

    def test_stops_on_empty_page(self):
        payload = {"products": []}
        with patch("desktop.runtime.shopify_sync.urlopen", return_value=_FakeResp(payload)):
            items = shopify_sync._shopify_get_all(URL, TOKEN, "/admin/api/2024-01/orders.json?status=any")
        self.assertEqual(items, [])

    def test_maps_orders_and_products_fields(self):
        order = {
            "id": 1001,
            "name": "#1001",
            "total_price": "53.22",
            "customer": {"first_name": "Maria", "last_name": "Pilar"},
            "created_at": "2026-08-15T10:00:00Z",
        }
        mapped = shopify_sync._map_shopify_orders([order])
        self.assertEqual(mapped[0]["id"], "#1001")
        self.assertEqual(mapped[0]["customer"], "Maria Pilar")
        self.assertEqual(mapped[0]["total"], 53.22)
        self.assertEqual(mapped[0]["date"], "2026-08-15")
        self.assertEqual(mapped[0]["line_items"], [])

        product = {"title": "Agenda 2026", "variants": [{"sku": "SKU-1", "price": "4.47"}]}
        mapped = shopify_sync._map_shopify_products([product])
        self.assertEqual(mapped[0]["sku"], "SKU-1")
        self.assertEqual(mapped[0]["netPrice"], 4.47)
        self.assertEqual(mapped[0]["source"], "shopify")

    def test_maps_orders_keeps_line_items_with_sku_and_qty(self):
        """Regression (Sales Analyst top sellers): the sync must keep each
        order's line items (SKU + quantity + unit price) so agents can compute
        units/revenue per product instead of only order-level totals."""
        order = {
            "id": 2001,
            "name": "#2001",
            "total_price": "53.22",
            "created_at": "2026-08-15T10:00:00Z",
            "line_items": [
                {
                    "title": "Agenda 2026",
                    "quantity": 2,
                    "price": "4.47",
                    "variant": {"sku": "SKU-AGENDA"},
                },
                {
                    "title": "Bolígrafo BIC",
                    "quantity": 3,
                    "price": "1.25",
                    "variant": {"sku": "SKU-BOLI"},
                },
            ],
        }
        mapped = shopify_sync._map_shopify_orders([order])
        lines = mapped[0]["line_items"]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["sku"], "SKU-AGENDA")
        self.assertEqual(lines[0]["title"], "Agenda 2026")
        self.assertEqual(lines[0]["quantity"], 2)
        self.assertEqual(lines[0]["price"], 4.47)
        self.assertEqual(lines[1]["sku"], "SKU-BOLI")

    def test_maps_orders_line_item_without_variant_sku_falls_back(self):
        """Line items without a variant SKU must fall back to ids — never crash."""
        order = {
            "id": 3001,
            "name": "#3001",
            "total_price": "10.00",
            "created_at": "2026-08-15T10:00:00Z",
            "line_items": [{"title": "Sin SKU", "quantity": 1, "price": "10.00", "variant_id": 777}],
        }
        mapped = shopify_sync._map_shopify_orders([order])
        self.assertEqual(mapped[0]["line_items"][0]["sku"], "777")
        self.assertEqual(mapped[0]["line_items"][0]["quantity"], 1)


if __name__ == "__main__":
    unittest.main()
