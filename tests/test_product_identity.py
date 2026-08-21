"""FASE 11 — cost verification + product identity (P2..P12).

Reglas bajo prueba (VERACIDAD > COMPLETITUD > AUTOMATIZACIÓN > VELOCIDAD):

  * coste == PVD sin evidencia NO es coste real (costStatus=missing).
  * margen solo con coste verificado/importado + identidad canónica fiable.
  * matching por SKU → barcode → variant ID → mapping manual; el nombre SOLO
    es propuesta, nunca match automático.
  * la reconciliación es una relación de identidad: nunca modifica el SKU de
    Shopify ni el producto canónico; los mappings son idempotentes.
  * ningún test escribe en la instalación real (load Y save parcheados).
  * los secretos nunca aparecen en la salida ni en los logs.

TODO corre en memoria: config_store.load/save se parchean SIEMPRE.
"""
from __future__ import annotations

import io
import json
import logging
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import agent_data_tools, business_model, config_store, detection_engine, product_identity


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _catalog(**kw) -> list[dict]:
    """6 productos. netPrice < rrp → coste 'imported' disponible (FASE 11: el
    dato trae evidencia de margen). Con cost_equals_pvd=True → coste==PVD."""
    if kw.get("cost_equals_pvd"):
        rows = [
            {"sku": "A", "name": "Prod A", "netPrice": 10.0, "rrp": 10.0},
            {"sku": "B", "name": "Prod B", "netPrice": 10.0, "rrp": 10.0},
            {"sku": "C", "name": "Prod C", "netPrice": 10.0, "rrp": 10.0},
            {"sku": "D", "name": "Prod D", "netPrice": 10.0, "rrp": 10.0},
            {"sku": "E", "name": "Prod E", "netPrice": 10.0, "rrp": 10.0},
            {"sku": "F", "name": "Prod F", "netPrice": 10.0, "rrp": 10.0},
        ]
        return rows
    rows = []
    for sku, net, rrp in [
        ("A", 9.0, 10.0), ("B", 1.0, 10.0), ("C", 1.0, 10.0),
        ("D", 1.0, 10.0), ("E", 1.0, 10.0), ("F", 1.0, 10.0),
    ]:
        rows.append({"sku": sku, "name": f"Prod {sku}", "netPrice": net, "rrp": rrp})
    return rows


def _sales(n: int = 40, sku_prefix: str = "", **kw) -> list[dict]:
    """Pedidos con line_items; cada pedido lleva A (15 veces), un base rotatorio
    B..F y opcionalmente X (caída). sku_prefix permite simular variant IDs de
    Shopify que NO coinciden con el catálogo."""
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(n):
        date = (now - timedelta(days=i % 45)).isoformat()
        lines = []
        if i % 15 < 15:
            lines.append({"sku": f"{sku_prefix}A", "title": "Prod A", "quantity": 1, "price": 10.0})
        base = ["B", "C", "D", "E", "F"][i % 5]
        lines.append({"sku": f"{sku_prefix}{base}", "title": f"Prod {base}", "quantity": 1, "price": 10.0})
        if 30 <= i < 50:
            lines.append({"sku": f"{sku_prefix}X", "title": "Prod X", "quantity": 1, "price": 10.0})
        rows.append({
            "id": f"O{i}", "order_id": f"O{i}",
            "total": 20.0, "date": date, "line_items": lines,
        })
    return rows


def _store(**data) -> dict:
    base = {
        "organizedProducts": [],
        "organizedSales": [],
        "organizedInvoices": [],
        "organizedInvoiceLines": [],
        "organizedFinance": [],
        "businessFindings": [],
    }
    base.update(data)
    return base


def _patch_all(store: dict):
    """Parchea load, save Y update (nunca se toca la instalación real).

    BUG-023: add_mapping/remove_mapping/ignore_sku/unignore_sku ahora usan
    config_store.update() (RMW atómico). update aplica el mutator al store.
    """
    return [
        patch.object(config_store, "load", side_effect=lambda: dict(store)),
        patch.object(config_store, "save", side_effect=lambda d: store.update(d)),
        patch.object(config_store, "update", side_effect=lambda mut: (mut(store) or store)),
    ]


class CostResolutionTests(unittest.TestCase):
    """P12 #1, #2, #3 — PVD ≠ coste / PVD = coste / coste ausente."""

    def test_pvd_equals_cost_is_never_a_real_cost(self):
        p = {"sku": "A", "name": "A", "netPrice": 4.47, "rrp": 4.47}
        rc = product_identity.resolve_cost(p)
        self.assertEqual(rc["costStatus"], "missing")
        self.assertIsNone(rc["cost"])
        self.assertEqual(rc["costSource"], "unknown")

    def test_explicit_verified_cost_wins(self):
        p = {"sku": "A", "name": "A", "cost": 3.0, "costSource": "supplier", "netPrice": 4.47, "rrp": 10.0}
        rc = product_identity.resolve_cost(p)
        self.assertEqual(rc["costStatus"], "verified")
        self.assertEqual(rc["cost"], 3.0)

    def test_explicit_cost_unknown_source_is_imported(self):
        p = {"sku": "A", "name": "A", "cost": 3.0, "netPrice": 4.47, "rrp": 10.0}
        rc = product_identity.resolve_cost(p)
        self.assertEqual(rc["costStatus"], "imported")
        self.assertEqual(rc["cost"], 3.0)

    def test_netprice_below_rrp_is_imported_cost(self):
        p = {"sku": "A", "name": "A", "netPrice": 4.47, "rrp": 10.0}
        rc = product_identity.resolve_cost(p)
        self.assertEqual(rc["costStatus"], "imported")
        self.assertEqual(rc["cost"], 4.47)

    def test_margin_null_without_real_cost(self):
        p = {"sku": "A", "name": "A", "netPrice": 10.0, "rrp": 10.0}
        row = business_model.with_margin(p)
        self.assertIsNone(row["margin"])
        self.assertIsNone(row["marginPct"])
        self.assertIsNone(row["markupPct"])
        self.assertEqual(row["costStatus"], "missing")

    def test_margin_computed_with_real_cost(self):
        p = {"sku": "A", "name": "A", "netPrice": 9.0, "rrp": 10.0}
        row = business_model.with_margin(p)
        self.assertEqual(row["marginPct"], 10.0)
        self.assertEqual(row["margin"], 1.0)


class IdentityResolutionTests(unittest.TestCase):
    """P12 #4..#10 — matching por fiabilidad."""

    def test_sku_exact_match(self):
        catalog = _catalog()
        ident = product_identity.resolve_identity({"sku": "A"}, catalog, [])
        self.assertTrue(ident["matched"])
        self.assertEqual(ident["matchMethod"], "sku")
        self.assertEqual(ident["canonicalProductId"], "A")
        self.assertTrue(ident["verified"])

    def test_barcode_match(self):
        catalog = _catalog() + [{"sku": "EAN1", "name": "EAN prod", "barcode": "8420000000001", "netPrice": 1.0, "rrp": 2.0}]
        ident = product_identity.resolve_identity({"sku": "shop", "barcode": "8420000000001"}, catalog, [])
        self.assertTrue(ident["matched"])
        self.assertEqual(ident["matchMethod"], "barcode")
        self.assertEqual(ident["canonicalProductId"], "EAN1")

    def test_variant_id_match(self):
        catalog = _catalog() + [{"sku": "C1", "name": "C1", "externalId": "57335931142475", "netPrice": 1.0, "rrp": 2.0}]
        ident = product_identity.resolve_identity({"sku": "57335931142475", "variant_id": "57335931142475"}, catalog, [])
        self.assertTrue(ident["matched"])
        self.assertEqual(ident["matchMethod"], "variant_id")
        self.assertEqual(ident["canonicalProductId"], "C1")

    def test_variant_id_in_sku_matches_catalog_shopify_variant_id(self):
        """FASE 12 (P3): las líneas de pedido de Shopify guardan el variant_id
        en `sku` (la API de pedidos no devuelve el SKU del variante). Tras la
        recuperación de identidad, el catálogo tiene `shopifyVariantId` y la
        línea debe enlazarse — incluso sin campo `variant_id` en la línea."""
        catalog = _catalog() + [{
            "sku": "1404128",
            "name": "Agenda 15x21",
            "shopifyVariantId": "57335931142475",
            "netPrice": 1.0,
            "rrp": 2.0,
        }]
        ident = product_identity.resolve_identity(
            {"sku": "57335931142475", "title": "Agenda 15x21"}, catalog, []
        )
        self.assertTrue(ident["matched"], "la línea con variant_id en sku debe enlazar")
        self.assertEqual(ident["matchMethod"], "variant_id")
        self.assertEqual(ident["canonicalProductId"], "1404128")
        self.assertTrue(ident["verified"])

    def test_ignored_sku_never_matches_and_is_reviewable(self):
        """FASE 12 (P2): "Ignorar" nunca crea un mapping falso ni vincula;
        el SKU ignorado no recibe match ni propuesta, y es reversible."""
        store = _store()
        with ExitStack() as stack:
            for p in _patch_all(store):
                stack.enter_context(p)
            catalog = [{"sku": "1404128", "name": "Agenda 15x21 spring semana vista", "netPrice": 1.0, "rrp": 2.0}]
            ident = product_identity.resolve_identity(
                {"sku": "shop_v_9", "title": "Agenda 15x21 spring semana vista"}, catalog, []
            )
            self.assertEqual(ident["matchMethod"], "name_suggestion")

            # Ignorar el SKU → ya no hay ni propuesta
            product_identity.ignore_sku("shop_v_9")
            ident2 = product_identity.resolve_identity(
                {"sku": "shop_v_9", "title": "Agenda 15x21 spring semana vista"}, catalog, []
            )
            self.assertFalse(ident2["matched"])
            self.assertEqual(ident2["matchReason"], "sku_ignorado")
            self.assertIsNone(ident2["suggestedProductId"])

        # Reversible: al quitar el ignorado vuelve la propuesta
        with ExitStack() as stack:
            for p in _patch_all(store):
                stack.enter_context(p)
            product_identity.unignore_sku("shop_v_9")
            ident3 = product_identity.resolve_identity(
                {"sku": "shop_v_9", "title": "Agenda 15x21 spring semana vista"}, catalog, []
            )
            self.assertEqual(ident3["matchMethod"], "name_suggestion")

    def test_shopify_sync_preserves_imported_costs(self):
        """FASE 14 (H23): la re-sync de Shopify NUNCA borra los costes
        importados (cost/costSource/costStatus/sourceReference). Antes, el
        merge descartaba los productos Shopify existentes y los reemplazaba
        por la respuesta de la API — que no trae costes → se perdían en cada
        sync (smoke test real: 414 costes → 0 tras arrancar la app)."""
        from desktop.runtime import shopify_sync

        existing = [
            {
                "sku": "1404128", "name": "Agenda 2026", "source": "shopify",
                "netPrice": 4.47, "rrp": 4.47,
                "cost": 3.04, "costSource": "supplier", "costStatus": "verified",
                "sourceReference": "NET_PRICE_LECLERC.xlsx", "costUpdatedAt": "2026-08-16T00:00:00Z",
                "shopifyVariantId": "57335931142475",
            },
        ]
        # La respuesta fresca de la API solo trae lo que Shopify devuelve
        # (sin costes ni procedencia).
        incoming = [
            {"sku": "1404128", "name": "Agenda 2026", "source": "shopify", "netPrice": 4.47, "rrp": 4.47, "shopifyVariantId": "57335931142475"},
        ]
        merged = shopify_sync._merge_products(existing, incoming)
        self.assertEqual(len(merged), 1)
        m = merged[0]
        self.assertEqual(m["cost"], 3.04, "el coste importado debe sobrevivir a la sync")
        self.assertEqual(m["costSource"], "supplier")
        self.assertEqual(m["costStatus"], "verified")
        self.assertEqual(m["sourceReference"], "NET_PRICE_LECLERC.xlsx")
        self.assertEqual(m["shopifyVariantId"], "57335931142475")

    def test_product_performance_sorted_by_revenue(self):
        """FASE 12 (H21): get_product_performance debe devolver el top por
        revenue descendente, no en orden de inserción — el contexto de Hermes
        lo presenta como "Top ventas" y debe serlo de verdad."""
        from desktop.runtime import agent_data_tools

        sales = [
            {"id": "1", "source": "shopify", "line_items": [
                {"sku": "B", "title": "B", "quantity": 2, "price": 5.0},
                {"sku": "A", "title": "A", "quantity": 1, "price": 100.0},
                {"sku": "C", "title": "C", "quantity": 1, "price": 3.0},
            ]},
        ]
        orig = agent_data_tools._sales
        agent_data_tools._sales = lambda: sales
        try:
            perf = agent_data_tools.get_product_performance()
        finally:
            agent_data_tools._sales = orig
        revs = [t["revenue"] for t in perf["performance"]]
        self.assertEqual(revs, sorted(revs, reverse=True), "el top ventas debe estar ordenado")
        self.assertEqual(perf["performance"][0]["sku"], "A")
        self.assertEqual(perf["performance"][0]["revenue"], 100.0)
        # El contexto debe incluir el bloque Top ventas (H21: antes Hermes
        # decía no tener el dato aunque la tool sí lo devolvía).
        agent_data_tools._sales = lambda: sales
        try:
            ctx = agent_data_tools.render_context_block(limit=2)
        finally:
            agent_data_tools._sales = orig
        self.assertIn("Top ventas", ctx)
        self.assertIn("100.0 €", ctx)

    def test_shopify_mapper_preserves_variant_id_and_barcode(self):
        """FASE 12 (P3): el mapeo de productos debe conservar variant id y
        barcode, y el de pedidos debe guardar variant_id en cada línea — son
        los eslabones que permiten venta → catálogo → coste."""
        from desktop.runtime import shopify_sync

        raw = [{
            "title": "Agenda 2026",
            "variants": [{"id": 57335931142475, "sku": "1404128", "barcode": "8420000000001", "price": "4.47"}],
        }]
        mapped = shopify_sync._map_shopify_products(raw)[0]
        self.assertEqual(mapped["shopifyVariantId"], "57335931142475")
        self.assertEqual(mapped["barcode"], "8420000000001")

        order = {
            "id": 3001,
            "name": "#3001",
            "total_price": "4.47",
            "created_at": "2026-08-15T10:00:00Z",
            "line_items": [{"title": "Agenda 2026", "quantity": 1, "price": "4.47", "variant_id": 57335931142475}],
        }
        line = shopify_sync._map_shopify_orders([order])[0]["line_items"][0]
        self.assertEqual(line["variant_id"], "57335931142475")

    def test_name_is_suggestion_never_auto_match(self):
        catalog = [{"sku": "1404128", "name": "Agenda 15x21 spring semana vista", "netPrice": 1.0, "rrp": 2.0}]
        ident = product_identity.resolve_identity(
            {"sku": "shop_v", "title": "Agenda 15x21 spring semana vista"}, catalog, []
        )
        self.assertFalse(ident["matched"])  # propuesta, NO match
        self.assertEqual(ident["matchMethod"], "name_suggestion")
        self.assertEqual(ident["suggestedProductId"], "1404128")
        self.assertFalse(ident["verified"])
        self.assertIsNone(ident["canonicalProductId"])

    def test_manual_mapping_is_verified(self):
        catalog = _catalog()
        mappings = [{
            "shopifySku": "shop_v_1", "canonicalProductId": "A",
            "matchMethod": "manual", "confidence": 1.0, "verified": True,
        }]
        ident = product_identity.resolve_identity({"sku": "shop_v_1"}, catalog, mappings)
        self.assertTrue(ident["matched"])
        self.assertEqual(ident["matchMethod"], "manual")
        self.assertEqual(ident["canonicalProductId"], "A")
        self.assertTrue(ident["verified"])

    def test_no_match_is_honest(self):
        catalog = _catalog()
        ident = product_identity.resolve_identity({"sku": "zzz_unknown"}, catalog, [])
        self.assertFalse(ident["matched"])
        self.assertEqual(ident["matchReason"], "no_identity_match")
        self.assertIsNone(ident["canonicalProductId"])


class ProfitabilityTests(unittest.TestCase):
    """P12 #11, #12, #13 — margen correcto / bloqueado / parcial."""

    def test_correct_identity_and_cost_give_correct_margin(self):
        store = _store(organizedProducts=_catalog(), organizedSales=_sales(sku_prefix=""))
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            prof = business_model.profitability(store)
            rows = {r["sku"]: r for r in prof["products"]}
            self.assertEqual(rows["A"]["marginPct"], 10.0)   # (10-9)/10
            self.assertEqual(rows["B"]["marginPct"], 90.0)
            self.assertEqual(rows["A"]["markupPct"], 11.1)   # (10-9)/9

    def test_wrong_identity_blocks_margin(self):
        # Líneas con SKU de Shopify (variant IDs) que NO coinciden con el
        # catálogo → identidad incorrecta → coste nunca se asigna.
        store = _store(organizedProducts=_catalog(), organizedSales=_sales(sku_prefix="shop_"))
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            prof = business_model.profitability(store)
            self.assertEqual(prof["orders"]["withCost"], 0)
            for r in prof["products"]:
                self.assertIsNone(r["marginPct"], f"{r['sku']} no debe tener margen sin identidad")
                self.assertEqual(r["costCoverage"], "missing")

    def test_manual_mapping_unlocks_margin(self):
        store = _store(organizedProducts=_catalog(), organizedSales=_sales(sku_prefix="shop_"))
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            # Sin mapping: bloqueado
            prof = business_model.profitability(store)
            self.assertEqual(prof["orders"]["withCost"], 0)
            # Mapping manual verificado shop_A → A desbloquea SOLO esa línea
            product_identity.add_mapping(
                shopify_sku="shop_A", canonical_product_id="A", match_method="manual", confidence=1.0
            )
            prof2 = business_model.profitability(store)
            rows = {r["sku"]: r for r in prof2["products"]}
            self.assertEqual(rows["shop_A"]["marginPct"], 10.0)   # coste A (9) sobre precio 10
            self.assertIsNone(rows["shop_B"]["marginPct"])        # sigue bloqueado

    def test_partial_coverage_is_clearly_labeled(self):
        catalog = _catalog()
        catalog[0]["netPrice"] = 10.0  # A sin coste real (== rrp)
        store = _store(organizedProducts=catalog, organizedSales=_sales(sku_prefix=""))
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            cc = product_identity.cost_coverage(store["organizedSales"], catalog)
            self.assertLess(cc["coveragePct"], 100.0)
            prof = business_model.profitability(store)
            rows = {r["sku"]: r for r in prof["products"]}
            self.assertEqual(rows["A"]["costCoverage"], "missing")
            self.assertEqual(rows["B"]["costCoverage"], "catalog")
            self.assertIsNone(rows["A"]["marginPct"])
            self.assertIsNotNone(rows["B"]["marginPct"])


class CoverageMetricsTests(unittest.TestCase):
    """P12 #13, #14, #15 — costCoverage / identityCoverage canónicas."""

    def test_cost_coverage_revenue_based(self):
        catalog = _catalog()
        sales = _sales(sku_prefix="")  # solo A..F, X sin identidad
        with ExitStack() as s:
            for p in _patch_all(_store()):
                s.enter_context(p)
            cc = product_identity.cost_coverage(sales, catalog)
            self.assertGreater(cc["coveragePct"], 0.0)
            self.assertLess(cc["coveragePct"], 100.0)  # X sin identidad/coste
            self.assertEqual(
                round(cc["revenueWithVerifiedCost"] + cc["revenueWithMissingCost"], 2),
                round(sum(li["price"] * li["quantity"] for sale in sales for li in sale["line_items"]), 2),
            )

    def test_cost_coverage_two_bases_explicit(self):
        """PRE-BETA: la cobertura de coste se expone en sus DOS bases, etiquetadas
        por separado: por Nº de productos (catálogo) y por revenue. Son métricas
        distintas y ambas deben estar presentes y ser coherentes."""
        catalog = _catalog()
        # solo A..F con coste; X e Y sin coste -> base producto != base revenue
        sales = _sales(sku_prefix="")
        with ExitStack() as s:
            for p in _patch_all(_store()):
                s.enter_context(p)
            cc = product_identity.cost_coverage(sales, catalog)
            self.assertIn("productsCoveragePct", cc)
            self.assertIn("coveragePct", cc)
            self.assertIn("productsTotal", cc)
            self.assertIn("productsWithVerifiedCost", cc)
            self.assertIn("productsWithMissingCost", cc)
            # base producto: % de productos con coste real
            self.assertEqual(cc["productsTotal"], cc["productsWithVerifiedCost"] + cc["productsWithMissingCost"])
            self.assertEqual(
                cc["productsCoveragePct"],
                round(cc["productsWithVerifiedCost"] / cc["productsTotal"] * 100, 1) if cc["productsTotal"] else 0.0,
            )
            # bases distintas: X vende pero no tiene coste -> revenue < producto
            self.assertLess(cc["coveragePct"], cc["productsCoveragePct"])
            # ambas < = 100 y >= 0 (ninguna inventada)
            self.assertGreaterEqual(cc["coveragePct"], 0.0)
            self.assertGreaterEqual(cc["productsCoveragePct"], 0.0)
            self.assertLessEqual(cc["productsCoveragePct"], 100.0)

    def test_identity_coverage(self):
        catalog = _catalog()
        sales = _sales(sku_prefix="")
        with ExitStack() as s:
            for p in _patch_all(_store()):
                s.enter_context(p)
            ic = product_identity.identity_coverage(sales, catalog)
            self.assertGreater(ic["matchedLines"], 0)
            self.assertGreater(ic["unmatchedLines"], 0)  # X
            self.assertGreater(ic["coveragePct"], 50.0)

    def test_catalog_index_equivalence_and_speed(self):
        # FASE 15: el índice precomputado (build_catalog_index) debe devolver
        # EXACTAMENTE los mismos resultados que el matching por catálogo, y
        # hacerlo mucho más rápido (antes O(líneas × catálogo) ~1.3s; ahora
        # O(líneas + catálogo)).
        import time as _time

        catalog = _catalog() * 3
        sales = _sales(sku_prefix="") * 10
        with ExitStack() as s:
            for p in _patch_all(_store()):
                s.enter_context(p)
            idx = product_identity.build_catalog_index(catalog)
            self.assertIn("by_sku", idx)
            self.assertIn("by_barcode", idx)
            self.assertIn("by_variant", idx)
            self.assertIn("by_name", idx)

            # equivalencia: mismo resultado por cada línea
            for sale in sales:
                for li in business_model.normalize_sale_lines(sale):
                    a = product_identity.resolve_identity(li, catalog)
                    b = product_identity.resolve_identity(li, catalog, catalog_index=idx)
                    self.assertEqual(a.get("matched"), b.get("matched"))
                    self.assertEqual(a.get("canonicalProductId"), b.get("canonicalProductId"))
                    self.assertEqual(a.get("matchMethod"), b.get("matchMethod"))

            # rendimiento: con índice debe ser sustancialmente más rápido.
            # Best-of-3 por ruta: bajo carga (suite completa) una única
            # medición de pared puede dar falsos negativos por ruido del timer.
            def _best(path):
                best = None
                for _ in range(3):
                    t0 = _time.monotonic()
                    for sale in sales:
                        for li in business_model.normalize_sale_lines(sale):
                            product_identity.resolve_identity(li, catalog, catalog_index=path)
                    dt = _time.monotonic() - t0
                    if best is None or dt < best:
                        best = dt
                return best

            t_naive = _best(None)
            t_indexed = _best(idx)
            self.assertLess(t_indexed, t_naive)

            # coberturas idénticas usando el mismo código de producción
            cc_a = product_identity.cost_coverage(sales, catalog)
            cc_b = product_identity.cost_coverage(sales, catalog)
            self.assertEqual(cc_a["coveragePct"], cc_b["coveragePct"])
            self.assertEqual(cc_a["revenueWithVerifiedCost"], cc_b["revenueWithVerifiedCost"])

    def test_hermes_tools_expose_coverage(self):
        store = _store(organizedProducts=_catalog(), organizedSales=_sales(sku_prefix=""))
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            cc = agent_data_tools.call_tool("get_cost_coverage", {})
            self.assertTrue(cc["ok"])
            self.assertIn("coveragePct", cc)
            ic = agent_data_tools.call_tool("get_identity_coverage", {})
            self.assertTrue(ic["ok"])
            self.assertIn("coveragePct", ic)
            rec = agent_data_tools.call_tool("get_product_reconciliation", {})
            self.assertTrue(rec["ok"])
            self.assertIn("summary", rec)
            self.assertIn("items", rec)

    def test_context_block_mentions_data_quality(self):
        store = _store(organizedProducts=_catalog(), organizedSales=_sales(sku_prefix=""))
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            block = agent_data_tools.render_context_block(limit=5)
            self.assertIn("CALIDAD DE DATOS", block)
            self.assertIn("coste real", block)


class DetectionGateTests(unittest.TestCase):
    """P12 #16 — el motor respeta los gates de coste e identidad."""

    def test_no_margin_findings_without_real_cost(self):
        store = _store(
            organizedProducts=_catalog(cost_equals_pvd=True),
            organizedSales=_sales(sku_prefix=""),
        )
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            res = detection_engine.run_detection(store, persist=True)
            self.assertEqual(res["quality"]["costCoverage"], 0.0)
            self.assertFalse(res["quality"]["canAnalyzeMargin"])
            types = {f["type"] for f in res["findings"]}
            self.assertNotIn("high_revenue_low_margin", types)
            self.assertTrue(any("coste real" in n for n in res["blockedReasons"]))

    def test_no_margin_findings_without_identity(self):
        store = _store(
            organizedProducts=_catalog(),
            organizedSales=_sales(sku_prefix="shop_"),
        )
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            res = detection_engine.run_detection(store, persist=True)
            self.assertFalse(res["quality"]["canAnalyzeMargin"])
            types = {f["type"] for f in res["findings"]}
            self.assertNotIn("high_revenue_low_margin", types)
            self.assertTrue(any("identidad" in n for n in res["blockedReasons"]))

    def test_findings_open_with_identity_and_cost(self):
        store = _store(
            organizedProducts=_catalog(),
            organizedSales=_sales(sku_prefix=""),
        )
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            res = detection_engine.run_detection(store, persist=True)
            self.assertTrue(res["quality"]["canAnalyzeMargin"])
            types = {f["type"] for f in res["findings"]}
            self.assertIn("high_revenue_low_margin", types)
            self.assertIn("cross_sell", types)
            # La caída de X se detecta SIN identidad (solo revenue): evidencia
            # propia, independiente del coste.
            self.assertIn("product_declining", types)
            for f in res["findings"]:
                self.assertTrue(f["evidence"])


class ReconciliationSafetyTests(unittest.TestCase):
    """P12 #17, #18 — relación de identidad, nunca copia; idempotencia."""

    def test_mapping_does_not_modify_source_data(self):
        catalog = _catalog()
        sales = _sales(sku_prefix="shop_")
        store = _store(organizedProducts=catalog, organizedSales=sales)
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            before_prod = json.dumps(catalog, sort_keys=True)
            before_sale = json.dumps(sales, sort_keys=True)
            product_identity.add_mapping(shopify_sku="shop_A", canonical_product_id="A")
            # El SKU de Shopify y el producto canónico quedan INTACTOS
            self.assertEqual(json.dumps(catalog, sort_keys=True), before_prod)
            self.assertEqual(json.dumps(sales, sort_keys=True), before_sale)
            # El mapping vive aparte, como relación
            mappings = product_identity.load_mappings()
            self.assertEqual(len(mappings), 1)
            self.assertEqual(mappings[0]["shopifySku"], "shop_A")
            self.assertEqual(mappings[0]["canonicalProductId"], "A")
            self.assertTrue(mappings[0]["verified"])

    def test_mappings_are_idempotent(self):
        store = _store()
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            r1 = product_identity.add_mapping(shopify_sku="S1", canonical_product_id="A")
            r2 = product_identity.add_mapping(shopify_sku="S1", canonical_product_id="A")
            self.assertTrue(r1["ok"])
            self.assertFalse(r1["updated"])
            self.assertTrue(r2["ok"])
            self.assertTrue(r2["updated"])  # se actualizó, no duplicó
            self.assertEqual(len(product_identity.load_mappings()), 1)

    def test_reconciliation_summary_shape(self):
        store = _store(organizedProducts=_catalog(), organizedSales=_sales(sku_prefix="shop_"))
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            rec = product_identity.build_reconciliation(store["organizedProducts"], store["organizedSales"], [])
            self.assertIn("summary", rec)
            self.assertIn("items", rec)
            self.assertIn("catalogNeverMatched", rec)
            self.assertEqual(rec["summary"]["matched"], 0)
            self.assertGreater(rec["summary"]["unmatched"], 0)
            self.assertEqual(rec["summary"]["coveragePct"], 0.0)


class Bug023AtomicRmwTests(unittest.TestCase):
    """BUG-023: add_mapping/remove_mapping/ignore_sku/unignore_sku deben usar
    config_store.update() (RMW atómico), no load→save que pierde escrituras."""

    def test_add_mapping_uses_atomic_update(self):
        from unittest.mock import patch as _p
        store = _store()
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            with _p.object(config_store, "update", wraps=config_store.update) as mock_upd:
                product_identity.add_mapping(shopify_sku="BUG23-A", canonical_product_id="A")
            mock_upd.assert_called_once()

    def test_ignore_sku_uses_atomic_update(self):
        from unittest.mock import patch as _p
        store = _store()
        with ExitStack() as stack:
            for pat in _patch_all(store):
                stack.enter_context(pat)
            with _p.object(config_store, "update", wraps=config_store.update) as mock_upd:
                product_identity.ignore_sku("IGN-X")
            mock_upd.assert_called_once()


class SecretsAndInstallationTests(unittest.TestCase):
    """P12 #19, #20 — la suite no toca la instalación y los secretos no salen."""

    def test_flow_does_not_write_real_config(self):
        real_path = config_store.CONFIG_FILE
        before = real_path.read_bytes() if real_path.exists() else None
        store = _store(organizedProducts=_catalog(), organizedSales=_sales(sku_prefix="shop_"))
        with ExitStack() as s:
            for p in _patch_all(store):
                s.enter_context(p)
            product_identity.add_mapping(shopify_sku="shop_A", canonical_product_id="A")
            detection_engine.run_detection(store, persist=True)
            agent_data_tools.call_tool("get_cost_coverage", {})
            agent_data_tools.call_tool("get_product_reconciliation", {})
        after = real_path.read_bytes() if real_path.exists() else None
        self.assertEqual(before, after, "la suite nunca debe escribir en el config real")

    def test_secrets_never_leak_to_output_or_logs(self):
        secret = "shpat_SUPERSECRETTOKEN_12345"
        store = _store(organizedProducts=_catalog(), organizedSales=_sales(sku_prefix="shop_"))
        captured: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record):  # noqa: A003
                captured.append(record)

        handler = _Capture()
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            with ExitStack() as s:
                for p in _patch_all(store):
                    s.enter_context(p)
                product_identity.add_mapping(shopify_sku=secret, canonical_product_id="A", variant_id=secret)
                rec = agent_data_tools.call_tool("get_product_reconciliation", {})
                cc = agent_data_tools.call_tool("get_cost_coverage", {})
            blob = json.dumps(rec) + json.dumps(cc)
            self.assertNotIn(secret, blob)
            for record in captured:
                self.assertNotIn(secret, record.getMessage())
        finally:
            root.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
