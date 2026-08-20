"""FASE 9 — Backfill de line_items de Shopify.

El backfill recupera las líneas de pedidos guardados por sync anteriores a la
feature de line_items (e.g. los 99 pedidos del backup del usuario). Debe ser
idempotente, no duplicar pedidos ni líneas, no borrar datos válidos y registrar
errores individualmente sin tocar el resto.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import shopify_sync

URL = "https://demo.myshopify.com"
TOKEN = "shpat_test_token"


def _sale(order_id: str, with_lines: bool = False) -> dict:
    sale = {
        "id": order_id,
        "customer": "Cliente Test",
        "total": 53.22,
        "date": "2026-08-15",
        "status": "paid",
        "source": "shopify",
        "sourceFile": "Shopify",
    }
    if with_lines:
        sale["line_items"] = [{"sku": "SKU-A", "title": "Agenda", "quantity": 1, "price": 10.0}]
    return sale


def _shopify_order(order_id: str) -> dict:
    return {
        "orders": [{
            "id": 1001,
            "name": order_id,
            "total_price": "53.22",
            "created_at": "2026-08-15T10:00:00Z",
            "line_items": [
                {"title": "Agenda 2026", "quantity": 2, "price": "4.47", "variant": {"sku": "SKU-AGENDA"}},
                {"title": "Bolígrafo", "quantity": 3, "price": "1.25", "variant": {"sku": "SKU-BOLI"}},
            ],
        }]
    }


class ShopifyBackfillTests(unittest.TestCase):
    def _store(self, sales, saved=None):
        saved = saved if saved is not None else {}
        store = {"organizedSales": sales, "shopifySync": {"status": "ok"}}
        store.update(saved)
        return store

    def test_backfills_missing_lines_and_preserves_fields(self):
        sales = [_sale("#1001"), _sale("#1002", with_lines=True)]
        store = self._store(sales)
        with patch.object(shopify_sync.integrations_store, "get_shopify_credentials", return_value={"url": URL, "token": TOKEN}), \
             patch.object(shopify_sync.config_store, "load", return_value=dict(store)), \
             patch.object(shopify_sync.config_store, "save", side_effect=lambda d: store.update(d)), \
             patch.object(shopify_sync, "_shopify_get", return_value=_shopify_order("#1001")):
            res = shopify_sync.backfill_line_items()

        self.assertTrue(res["ok"])
        self.assertEqual(res["updated"], 1)
        self.assertEqual(res["failed"], 0)
        # Pedido sin líneas recuperadas
        s1 = next(s for s in store["organizedSales"] if s["id"] == "#1001")
        self.assertEqual(len(s1["line_items"]), 2)
        self.assertEqual(s1["line_items"][0]["sku"], "SKU-AGENDA")
        self.assertEqual(s1["line_items"][0]["quantity"], 2)
        self.assertEqual(s1["line_items"][0]["price"], 4.47)
        # Campos originales conservados (nunca se reemplaza el pedido entero)
        self.assertEqual(s1["customer"], "Cliente Test")
        self.assertEqual(s1["total"], 53.22)
        self.assertEqual(s1["date"], "2026-08-15")
        self.assertEqual(s1["status"], "paid")
        # Pedido que ya tenía líneas: intacto
        s2 = next(s for s in store["organizedSales"] if s["id"] == "#1002")
        self.assertEqual(s2["line_items"], [{"sku": "SKU-A", "title": "Agenda", "quantity": 1, "price": 10.0}])

    def test_idempotent_second_run_does_nothing(self):
        sales = [_sale("#1001")]
        store = self._store(sales)
        calls = {"n": 0}
        with patch.object(shopify_sync.integrations_store, "get_shopify_credentials", return_value={"url": URL, "token": TOKEN}), \
             patch.object(shopify_sync.config_store, "load", side_effect=lambda: dict(store)), \
             patch.object(shopify_sync.config_store, "save", side_effect=lambda d: store.update(d)), \
             patch.object(shopify_sync, "_shopify_get", side_effect=lambda *a, **k: calls.update(n=calls["n"] + 1) or _shopify_order("#1001")):
            r1 = shopify_sync.backfill_line_items()
            r2 = shopify_sync.backfill_line_items()

        self.assertEqual(r1["updated"], 1)
        self.assertEqual(r2["candidates"], 0)  # segunda pasada: nada que hacer
        self.assertEqual(r2["updated"], 0)
        self.assertEqual(calls["n"], 1)  # solo se llamó a la API una vez
        # No se duplican pedidos ni líneas
        self.assertEqual(len(store["organizedSales"]), 1)
        self.assertEqual(len(store["organizedSales"][0]["line_items"]), 2)

    def test_individual_failure_never_touches_other_orders(self):
        sales = [_sale("#A"), _sale("#B"), _sale("#C")]
        store = self._store(sales)

        def fake_get(base_url, token, path):
            # Shopify URL-encodea el nombre del pedido: "#B" → "%23B"
            if "%23B" in path:
                raise RuntimeError("Shopify HTTP 429: rate limited")
            if "%23C" in path:
                return {"orders": []}  # pedido no encontrado
            return _shopify_order("#A")

        with patch.object(shopify_sync.integrations_store, "get_shopify_credentials", return_value={"url": URL, "token": TOKEN}), \
             patch.object(shopify_sync.config_store, "load", return_value=dict(store)), \
             patch.object(shopify_sync.config_store, "save", side_effect=lambda d: store.update(d)), \
             patch.object(shopify_sync, "_shopify_get", side_effect=fake_get):
            res = shopify_sync.backfill_line_items()

        self.assertEqual(res["updated"], 1)   # solo #A
        self.assertEqual(res["failed"], 2)    # #B (429) y #C (no encontrado)
        self.assertEqual(len(res["errors"]), 2)
        err_ids = {e["id"] for e in res["errors"]}
        self.assertEqual(err_ids, {"#B", "#C"})
        self.assertIn("429", next(e["error"] for e in res["errors"] if e["id"] == "#B"))
        # #B y #C conservan su estado previo SIN líneas (no se borró nada)
        sB = next(s for s in store["organizedSales"] if s["id"] == "#B")
        sC = next(s for s in store["organizedSales"] if s["id"] == "#C")
        self.assertNotIn("line_items", sB)
        self.assertNotIn("line_items", sC)
        # Los 3 pedidos siguen existiendo
        self.assertEqual(len(store["organizedSales"]), 3)

    def test_not_connected_returns_error_and_touches_nothing(self):
        sales = [_sale("#1001")]
        store = self._store(sales)
        with patch.object(shopify_sync.integrations_store, "get_shopify_credentials", return_value={}), \
             patch.object(shopify_sync.config_store, "load", return_value=dict(store)), \
             patch.object(shopify_sync.config_store, "save", side_effect=lambda d: store.update(d)):
            res = shopify_sync.backfill_line_items()
        self.assertFalse(res["ok"])
        self.assertNotIn("line_items", store["organizedSales"][0])

    def test_sync_skipped_when_already_running(self):
        """FASE 9 hardening: el loop de fondo y una llamada manual nunca
        sincronizan a la vez — la segunda se omite sin tocar datos."""
        store = self._store([_sale("#1001")])
        fetched = {"n": 0}
        with patch.object(shopify_sync, "_sync_running", True), \
             patch.object(shopify_sync.integrations_store, "sync_shopify_from_hermes_if_needed", side_effect=lambda: fetched.update(n=fetched["n"] + 1)), \
             patch.object(shopify_sync.config_store, "load", return_value=dict(store)), \
             patch.object(shopify_sync.config_store, "save", side_effect=lambda d: store.update(d)):
            res = shopify_sync._run_sync()
        self.assertFalse(res["ok"])
        self.assertTrue(res.get("skipped"))
        self.assertEqual(fetched["n"], 0)  # no se tocó nada
        self.assertNotIn("line_items", store["organizedSales"][0])

    def test_sync_runs_once_after_guard_released(self):
        """La guarda se libera en `finally`: una sync fallida no deja el
        sistema bloqueado para siempre."""
        store = self._store([])
        calls = {"n": 0}
        with patch.object(shopify_sync, "_shopify_get_all", side_effect=lambda *a, **k: calls.update(n=calls["n"] + 1) or ({"products": [], "orders": []} if False else [])):
            with patch.object(shopify_sync.integrations_store, "get_shopify_credentials", return_value={"url": URL, "token": TOKEN}), \
                 patch.object(shopify_sync.config_store, "load", side_effect=lambda: dict(store)), \
                 patch.object(shopify_sync.config_store, "save", side_effect=lambda d: store.update(d)):
                shopify_sync._run_sync()
                r2 = shopify_sync._run_sync()
        self.assertFalse(shopify_sync._sync_running)  # guarda liberada
        # 2 fetchs por sync (products + orders) × 2 syncs = 4: la segunda sync
        # sí se ejecutó porque la guarda se liberó en `finally`.
        self.assertEqual(calls["n"], 4)

    def test_recovered_line_resolves_cost_and_margin(self):
        """Cadena pedido → línea → SKU → coste → margen tras el backfill."""
        sales = [_sale("#1001")]
        store = self._store(sales)
        store["organizedProducts"] = [{"sku": "SKU-AGENDA", "netPrice": 3.0, "name": "Agenda"}]
        with patch.object(shopify_sync.integrations_store, "get_shopify_credentials", return_value={"url": URL, "token": TOKEN}), \
             patch.object(shopify_sync.config_store, "load", side_effect=lambda: dict(store)), \
             patch.object(shopify_sync.config_store, "save", side_effect=lambda d: store.update(d)), \
             patch.object(shopify_sync, "_shopify_get", return_value=_shopify_order("#1001")):
            shopify_sync.backfill_line_items()

        from desktop.runtime import business_model
        pm = business_model.profitability(store)
        rows = {r["sku"]: r for r in pm.get("products", [])}
        row = rows["SKU-AGENDA"]
        self.assertEqual(row["units"], 2.0)
        self.assertEqual(row["revenue"], 8.94)
        self.assertEqual(row["margin"], 2.94)   # 8.94 - 2*3.0
        self.assertEqual(row["marginPct"], round(2.94 / 8.94 * 100, 1))
        self.assertEqual(row["markupPct"], round(2.94 / 6.0 * 100, 1))


if __name__ == "__main__":
    unittest.main()
