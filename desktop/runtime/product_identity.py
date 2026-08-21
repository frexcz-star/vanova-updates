"""VANOVA Product Identity + Cost Verification (FASE 11).

Capa canónica que separa DOS problemas que antes estaban mezclados:

1. IDENTIDAD (multi-fuente, FASE 13 P5): ¿la línea de venta de CUALQUIER
   fuente (Shopify, WooCommerce, PrestaShop, CSV/Excel) corresponde a QUÉ
   producto del catálogo? Matching por orden de fiabilidad:
     SKU exacto → barcode/EAN/GTIN → variant ID ↔ externalId → mapping manual
     persistido → nombre SOLO como propuesta (nunca match automático).
   Los IDs específicos de cada fuente viven solo aquí y en el connector.
   Sin match fiable: matched=False, matchReason="no_identity_match".

2. COSTE: ¿el catálogo tiene un COSTE REAL de adquisición? Regla absoluta:
   coste == PVD sin evidencia NO es coste real (costStatus=missing). Solo se
   calcula margen si costStatus ∈ {verified, imported} y hay identidad.

Nunca se estima un coste, nunca se asigna un margen sin evidencia, y nunca se
modifica el SKU original de la fuente ni el producto canónico (la relación es
de identidad, no una copia de datos).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import business_model, config_store

# costStatus / costSource permitidos (documentados)
COST_STATUSES = ("verified", "imported", "estimated", "missing")
COST_SOURCES = ("supplier", "erp", "facturascripts", "manual", "imported_file", "unknown")
MATCH_METHODS = ("sku", "barcode", "variant_id", "manual", "name_suggestion")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# COSTE — separación coste real vs PVD
# ---------------------------------------------------------------------------


def resolve_cost(product: dict[str, Any], global_margin_pct: float | None = None) -> dict[str, Any]:
    """Devuelve el coste REAL de un producto del catálogo, nunca el PVD
    disfrazado de coste. Regla: si no existe evidencia de coste de adquisición
    (coste == precio de venta), costStatus=missing y cost=None.

    - `cost` explícito con costSource verificado → verified
    - `cost` explícito sin fuente → imported (evidencia en el dato)
    - netPrice ≠ rrp (hay margen real en el dato) → imported
    - netPrice == rrp (sin evidencia) → missing (NUNCA se usa como coste)
    - Si no hay coste real pero el usuario DECLARÓ un margen global (su propio
      margen de negocio), se ESTIMA un coste `= rrp × (1 − margen/100)` y se
      marca `estimated` (nunca verified/imported real). Honesto: deriva de un
      dato declarado por el usuario, nunca inventado por el sistema.
    """
    sale = _f(product.get("rrp"))
    explicit = _f(product.get("cost"))
    source = str(product.get("costSource") or "").strip().lower() or "unknown"
    net = _f(product.get("netPrice"))

    # FASE B (B5): un SKU duplicado es ambiguo — su coste NO se usa hasta
    # que el usuario lo revise (UNKNOWN ≠ coste verificado).
    if str(product.get("qualityReason") or "") == "duplicate_sku":
        return {
            "cost": None,
            "costStatus": "missing",
            "costSource": "unknown",
            "salePrice": sale,
            "reason": "sku_duplicado_requiere_revision",
        }

    if explicit is not None:
        verified = source in ("supplier", "erp", "facturascripts", "manual")
        return {
            "cost": explicit,
            "costStatus": "verified" if verified else "imported",
            "costSource": source if source != "unknown" else "unknown",
            "salePrice": sale,
        }
    if net is None:
        # Margen global declarado: estimar coste si hay precio de venta.
        if global_margin_pct is not None and sale is not None and sale > 0:
            est_cost = round(sale * (1 - global_margin_pct / 100.0), 2)
            if est_cost > 0:
                return {
                    "cost": est_cost,
                    "costStatus": "estimated",
                    "costSource": "global_margin",
                    "salePrice": sale,
                    "reason": "coste_estimado_con_margen_global_declarado",
                }
        return {"cost": None, "costStatus": "missing", "costSource": "unknown", "salePrice": sale}
    if sale is not None and abs(net - sale) < 0.001:
        # coste == PVD sin evidencia de adquisición → NO es coste real.
        # Con margen global declarado, estimar a partir del PVD.
        if global_margin_pct is not None and sale > 0:
            est_cost = round(sale * (1 - global_margin_pct / 100.0), 2)
            if est_cost > 0:
                return {
                    "cost": est_cost,
                    "costStatus": "estimated",
                    "costSource": "global_margin",
                    "salePrice": sale,
                    "reason": "coste_estimado_con_margen_global_declarado",
                }
        return {
            "cost": None,
            "costStatus": "missing",
            "costSource": "unknown",
            "salePrice": sale,
            "reason": "coste_igual_a_PVD_sin_evidencia",
        }
    return {
        "cost": net,
        "costStatus": "imported",
        "costSource": source if source != "unknown" else "imported_file",
        "salePrice": sale,
    }


def cost_available(product: dict[str, Any], global_margin_pct: float | None = None) -> bool:
    return resolve_cost(product, global_margin_pct).get("costStatus") in ("verified", "imported", "estimated")


# ---------------------------------------------------------------------------
# IDENTIDAD — matching canónico producto ↔ catálogo
# ---------------------------------------------------------------------------


def load_mappings() -> list[dict[str, Any]]:
    data = config_store.load()
    mappings = data.get("productMappings") or []
    return [m for m in mappings if isinstance(m, dict)] if isinstance(mappings, list) else []


def _sku_of(mapping: dict[str, Any]) -> str:
    """FASE 13 (P5): clave de identidad multi-fuente. Un mapping puede venir
    de Shopify (shopifySku), de WooCommerce/PrestaShop (sourceSku) o de
    cualquier fuente futura; todos se resuelven igual."""
    return str(mapping.get("sourceSku") or mapping.get("shopifySku") or "").strip()


def _variant_id_of(mapping: dict[str, Any]) -> str:
    return str(mapping.get("sourceVariantId") or mapping.get("shopifyVariantId") or "").strip()


def save_mappings(mappings: list[dict[str, Any]]) -> None:
    config_store.save({"productMappings": mappings})


def add_mapping(
    *,
    source_sku: str | None = None,
    shopify_sku: str | None = None,  # compatibilidad FASE 12
    source: str = "manual",
    variant_id: str | None = None,
    barcode: str | None = None,
    canonical_product_id: str,
    match_method: str = "manual",
    confidence: float = 1.0,
) -> dict[str, Any]:
    """Persiste un mapping manual verificado (identidad, no copia de datos).

    FASE 13 (P5): la clave es GENÉRICA (`source_sku`) — puede ser el SKU de
    venta de Shopify, WooCommerce, PrestaShop o un CSV. `shopify_sku` se
    acepta como alias de compatibilidad. El `source` queda registrado para
    trazabilidad."""
    sku = (source_sku or shopify_sku or "").strip()
    canonical_product_id = (canonical_product_id or "").strip()
    if not sku or not canonical_product_id:
        return {"ok": False, "error": "sourceSku y canonicalProductId son obligatorios"}
    if match_method not in MATCH_METHODS:
        return {"ok": False, "error": f"matchMethod inválido: {match_method}"}
    # BUG-023 FIX: RMW atómico bajo un solo lock (lost-update). Antes:
    # load_mappings() → modificar → save_mappings() sin config_store.update().
    now = _now()
    entry = {
        "sourceSku": sku,
        "source": (source or "unknown").strip()[:40],
        "sourceVariantId": (variant_id or "").strip() or None,
        "barcode": (barcode or "").strip() or None,
        "canonicalProductId": canonical_product_id,
        "matchMethod": match_method,
        "confidence": float(confidence),
        "verified": True,
        "createdAt": now,
        "updatedAt": now,
        # Aliases de compatibilidad (mappings creados antes de FASE 13)
        "shopifySku": sku,
        "shopifyVariantId": (variant_id or "").strip() or None,
    }

    was_updated = False

    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        nonlocal was_updated
        mappings = cfg.get("productMappings") or []
        if not isinstance(mappings, list):
            mappings = []
        mappings = [m for m in mappings if isinstance(m, dict)]
        # Idempotente: un mapping existente para la misma clave de fuente se
        # actualiza (cualquier fuente, no solo Shopify).
        for m in mappings:
            if _sku_of(m) == sku:
                m.update(entry)
                m["updatedAt"] = now
                cfg["productMappings"] = mappings
                was_updated = True
                return cfg
        mappings.append(entry)
        cfg["productMappings"] = mappings
        return cfg

    config_store.update(_mutate)
    return {"ok": True, "mapping": entry, "updated": was_updated}


def remove_mapping(source_sku: str, shopify_sku: str | None = None) -> dict[str, Any]:
    sku = (source_sku or shopify_sku or "").strip()
    # BUG-023 FIX: RMW atómico bajo un solo lock.
    removed = False

    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        nonlocal removed
        mappings = cfg.get("productMappings") or []
        if not isinstance(mappings, list):
            mappings = []
        mappings = [m for m in mappings if isinstance(m, dict)]
        before = len(mappings)
        mappings = [m for m in mappings if _sku_of(m) != sku]
        removed = len(mappings) != before
        cfg["productMappings"] = mappings
        return cfg

    config_store.update(_mutate)
    if not removed:
        return {"ok": False, "error": "Mapping no encontrado"}
    return {"ok": True, "removed": True}


# ---------------------------------------------------------------------------
# SKUs IGNORADOS — FASE 12 (P2): "Ignorar" nunca crea un mapping falso ni
# vincula; simplemente excluye el SKU de venta de la reconciliación (revisable).
# ---------------------------------------------------------------------------


def load_ignored() -> list[str]:
    data = config_store.load()
    ignored = data.get("productIgnoredSkus") or []
    return [str(x).strip() for x in ignored if str(x or "").strip()] if isinstance(ignored, list) else []


def _save_ignored(ignored: list[str]) -> None:
    config_store.save({"productIgnoredSkus": ignored})


def ignore_sku(source_sku: str, shopify_sku: str | None = None) -> dict[str, Any]:
    sku = (source_sku or shopify_sku or "").strip()
    if not sku:
        return {"ok": False, "error": "sourceSku obligatorio"}
    # BUG-023 FIX: RMW atómico bajo un solo lock.
    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        ignored = cfg.get("productIgnoredSkus") or []
        if not isinstance(ignored, list):
            ignored = []
        ignored = [str(x).strip() for x in ignored if str(x or "").strip()]
        if sku not in ignored:
            ignored.append(sku)
        cfg["productIgnoredSkus"] = ignored
        return cfg

    config_store.update(_mutate)
    return {"ok": True, "ignored": True}


def unignore_sku(source_sku: str, shopify_sku: str | None = None) -> dict[str, Any]:
    sku = (source_sku or shopify_sku or "").strip()
    # BUG-023 FIX: RMW atómico bajo un solo lock.
    unignored = False

    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        nonlocal unignored
        ignored = cfg.get("productIgnoredSkus") or []
        if not isinstance(ignored, list):
            ignored = []
        ignored = [str(x).strip() for x in ignored if str(x or "").strip()]
        before = len(ignored)
        ignored = [x for x in ignored if x != sku]
        unignored = len(ignored) != before
        cfg["productIgnoredSkus"] = ignored
        return cfg

    config_store.update(_mutate)
    if not unignored:
        return {"ok": False, "error": "SKU no estaba ignorado"}
    return {"ok": True, "unignored": True}


def _barcode_candidates(product: dict[str, Any]) -> list[str]:
    out = []
    for key in ("barcode", "ean", "gtin", "upc"):
        val = str(product.get(key) or "").strip()
        if val:
            out.append(val.lower())
    return out


# FASE 15: índice de catálogo precomputado. Antes cada llamada a
# resolve_identity recorría el catálogo completo por línea de venta
# (O(líneas × catálogo)); las coberturas reconstruían los mismos índices
# 3–4 veces por petición. Con un único índice por catálogo, el matching pasa
# a O(líneas + catálogo). La firma pública de resolve_identity no cambia.
def build_catalog_index(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    """Índices de búsqueda del catálogo: sku (lower), barcode, variant/external
    id y nombre normalizado. Se construye UNA vez por lote de líneas."""
    by_sku: dict[str, dict[str, Any]] = {}
    by_barcode: dict[str, dict[str, Any]] = {}
    by_variant: dict[str, dict[str, Any]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for p in catalog:
        if not isinstance(p, dict):
            continue
        sku = str(p.get("sku") or "").strip().lower()
        if sku:
            by_sku.setdefault(sku, p)
        for cand in _barcode_candidates(p):
            by_barcode.setdefault(cand, p)
        ext = str(
            p.get("externalId") or p.get("shopifyVariantId") or p.get("sourceVariantId") or p.get("source_variant_id") or ""
        ).strip()
        if ext:
            by_variant.setdefault(ext, p)
        pname = str(p.get("name") or "").strip().lower()
        if pname:
            by_name.setdefault(pname, []).append(p)
    return {"by_sku": by_sku, "by_barcode": by_barcode, "by_variant": by_variant, "by_name": by_name}


def resolve_identity(
    line_item: dict[str, Any],
    catalog: list[dict[str, Any]],
    mappings: list[dict[str, Any]] | None = None,
    catalog_index: dict[str, Any] | None = None,
    ignored: list[str] | None = None,
) -> dict[str, Any]:
    """Resuelve la identidad canónica de una línea de venta. Orden de
    fiabilidad: SKU → barcode → variant ID → mapping manual → nombre (solo
    propuesta, nunca match automático). Sin match fiable → matched=False.

    FASE 15: `catalog_index` (build_catalog_index) e `ignored` son opcionales
    y evitan reconstruir índices / releer la config por línea en lotes."""
    if mappings is None:
        mappings = load_mappings()
    sku = str(line_item.get("sku") or "").strip()
    # FASE 13 (P5): claves genéricas de identidad por fuente. Shopify usa
    # variant_id; WooCommerce usará variation_id/product_id; PrestaShop otras.
    variant_id = str(line_item.get("variant_id") or line_item.get("source_variant_id") or "").strip()
    barcode = str(line_item.get("barcode") or "").strip().lower()
    title = str(line_item.get("title") or "").strip()

    # FASE 12 (P2): SKU ignorado → nunca se vincula ni se sugiere (revisable).
    if ignored is None:
        try:
            ignored = load_ignored()
        except Exception:  # noqa: BLE001
            ignored = []
    if sku and sku in ignored:
        return {
            "matched": False,
            "canonicalProductId": None,
            "suggestedProductId": None,
            "matchMethod": None,
            "confidence": 0.0,
            "verified": False,
            "source": "ignored",
            "matchReason": "sku_ignorado",
        }

    if catalog_index is None:
        catalog_index = build_catalog_index(catalog)
    by_sku = catalog_index["by_sku"]
    by_barcode = catalog_index["by_barcode"]
    by_variant = catalog_index["by_variant"]
    by_name = catalog_index["by_name"]
    manual_by_sku = {_sku_of(m): m for m in mappings if m.get("verified")}

    # 1) Mapping manual verificado (más fiable que cualquier match automático)
    manual = manual_by_sku.get(sku)
    if manual and manual.get("canonicalProductId"):
        return {
            "matched": True,
            "canonicalProductId": manual["canonicalProductId"],
            "matchMethod": "manual",
            "confidence": float(manual.get("confidence") or 1.0),
            "verified": True,
            "source": "manual_mapping",
        }
    # 2) SKU exacto
    if sku and sku.lower() in by_sku:
        p = by_sku[sku.lower()]
        return {
            "matched": True,
            "canonicalProductId": str(p.get("sku") or p.get("id")),
            "matchMethod": "sku",
            "confidence": 1.0,
            "verified": True,
            "source": "catalog_sku",
        }
    # 3) Barcode/EAN/GTIN exacto
    if barcode:
        p = by_barcode.get(barcode)
        if p:
            return {
                "matched": True,
                "canonicalProductId": str(p.get("sku") or p.get("id")),
                "matchMethod": "barcode",
                "confidence": 1.0,
                "verified": True,
                "source": "catalog_barcode",
            }
    # 4) Variant ID ↔ externalId/sourceVariantId registrado en el catálogo.
    #    La línea de Shopify trae el variant_id en `sku` (la API de pedidos no
    #    expone el SKU del variante), así que probamos ambos campos. WooCommerce
    #    usará sourceVariantId; PrestaShop externalId. Todos genéricos.
    for v in (variant_id, sku):
        if v and v in by_variant:
            p = by_variant[v]
            return {
                "matched": True,
                "canonicalProductId": str(p.get("sku") or p.get("id")),
                "matchMethod": "variant_id",
                "confidence": 1.0,
                "verified": True,
                "source": "catalog_external_id",
            }
    # 5) Nombre → SOLO propuesta (nunca match automático como verdad)
    suggestion = None
    if title:
        norm_title = title.strip().lower()
        best_score = 0.0
        # coincidencia exacta de nombre primero (O(1))
        exact = by_name.get(norm_title)
        if exact:
            suggestion = exact[0]
            best_score = 1.0
        else:
            # coincidencia de subcadena simple — SOLO propuesta, confianza baja
            for pname, plist in by_name.items():
                if norm_title in pname or pname in norm_title:
                    score = min(len(norm_title), len(pname)) / max(len(norm_title), len(pname), 1)
                    if score > best_score:
                        best_score = score
                        suggestion = plist[0]
        if suggestion and best_score >= 0.6:
            return {
                "matched": False,
                "canonicalProductId": None,
                "suggestedProductId": str(suggestion.get("sku") or suggestion.get("id")),
                "matchMethod": "name_suggestion",
                "confidence": round(best_score, 2),
                "verified": False,
                "source": "name_suggestion",
                "matchReason": "solo_propuesta_requiere_confirmacion",
            }
    return {
        "matched": False,
        "canonicalProductId": None,
        "matchMethod": None,
        "confidence": 0.0,
        "verified": False,
        "source": "none",
        "matchReason": "no_identity_match",
    }


# ---------------------------------------------------------------------------
# RECONCILIACIÓN — resumen y desglose
# ---------------------------------------------------------------------------


def build_reconciliation(
    products: list[dict[str, Any]],
    sales: list[dict[str, Any]],
    mappings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Responde: cuántos productos Shopify tienen match, por qué método,
    cuántos requieren revisión y qué catálogo nunca aparece."""
    if mappings is None:
        mappings = load_mappings()
    catalog = [p for p in products if isinstance(p, dict)]
    catalog_index = build_catalog_index(catalog)
    ignored = load_ignored()
    shopify_lines: list[dict[str, Any]] = []
    for s in sales:
        if not isinstance(s, dict):
            continue
        for li in s.get("line_items") or []:
            if isinstance(li, dict):
                shopify_lines.append(li)

    seen_skus: dict[str, dict[str, Any]] = {}
    for li in shopify_lines:
        sku = str(li.get("sku") or "").strip()
        if not sku or sku in seen_skus:
            continue
        ident = resolve_identity(li, catalog, mappings, catalog_index=catalog_index, ignored=ignored)
        status = "MATCHED" if ident.get("matched") else ("IGNORED" if ident.get("matchReason") == "sku_ignorado" else ("REVIEW" if ident.get("matchMethod") == "name_suggestion" else "UNMATCHED"))
        seen_skus[sku] = {
            # Claves genéricas (FASE 13 P5) + alias de compatibilidad UI.
            "sourceSku": sku,
            "sourceVariantId": str(li.get("variant_id") or "").strip() or None,
            "shopifySku": sku,
            "shopifyVariantId": str(li.get("variant_id") or "").strip() or None,
            "title": str(li.get("title") or "")[:120],
            "canonicalProductId": ident.get("canonicalProductId"),
            "suggestedProductId": ident.get("suggestedProductId"),
            "matchMethod": ident.get("matchMethod"),
            "confidence": ident.get("confidence"),
            "status": status,
            "reason": ident.get("matchReason") or ("manual" if ident.get("matchMethod") == "manual" else ident.get("matchMethod") or "no_identity_match"),
        }

    items = sorted(seen_skus.values(), key=lambda r: (r["status"] != "MATCHED", r["sourceSku"]))
    matched = sum(1 for i in items if i["status"] == "MATCHED")
    review = sum(1 for i in items if i["status"] == "REVIEW")
    unmatched = sum(1 for i in items if i["status"] == "UNMATCHED")
    ignored = sum(1 for i in items if i["status"] == "IGNORED")
    total = len(items)

    catalog_skus = {str(p.get("sku") or "").strip() for p in catalog if str(p.get("sku") or "").strip()}
    matched_canonical = {i["canonicalProductId"] for i in items if i["canonicalProductId"]}
    catalog_never = sorted(sku for sku in catalog_skus if sku not in matched_canonical)

    by_method: dict[str, int] = {}
    for i in items:
        m = i["matchMethod"] or "none"
        by_method[m] = by_method.get(m, 0) + 1

    return {
        "ok": True,
        "summary": {
            "sourceSkuCount": total,
            "shopifySkuCount": total,  # alias UI
            "catalogProducts": len(catalog),
            "matched": matched,
            "unmatched": unmatched,
            "manualReview": review,
            "ignored": ignored,
            "coveragePct": round(matched / total * 100, 1) if total else 0.0,
            "byMethod": by_method,
            "catalogProductsNeverMatched": len(catalog_never),
        },
        "items": items,
        "catalogNeverMatched": catalog_never[:100],
    }


# ---------------------------------------------------------------------------
# COBERTURAS — coste e identidad sobre el negocio (revenue real)
# ---------------------------------------------------------------------------


def identity_coverage(
    sales: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    mappings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Qué parte del REVENUE tiene identidad de producto fiable."""
    if mappings is None:
        mappings = load_mappings()
    catalog_index = build_catalog_index(catalog)
    ignored = load_ignored()
    matched_lines = 0
    unmatched_lines = 0
    matched_rev = 0.0
    unmatched_rev = 0.0
    matched_units = 0.0
    total_units = 0.0
    for s in sales:
        if not isinstance(s, dict):
            continue
        # FASE 13 (P8): filas planas de CSV/Excel se normalizan igual que
        # las líneas de cualquier tienda/ERP.
        for li in business_model.normalize_sale_lines(s):
            qty = _f(li.get("quantity")) or 1.0
            price = _f(li.get("price"))
            amount = (price or 0.0) * qty
            total_units += qty
            ident = resolve_identity(li, catalog, mappings, catalog_index=catalog_index, ignored=ignored)
            if ident.get("matched"):
                matched_lines += 1
                matched_rev += amount
                matched_units += qty
            else:
                unmatched_lines += 1
                unmatched_rev += amount
    total_rev = matched_rev + unmatched_rev
    return {
        "matchedLines": matched_lines,
        "unmatchedLines": unmatched_lines,
        "matchedRevenue": round(matched_rev, 2),
        "unmatchedRevenue": round(unmatched_rev, 2),
        "coveragePct": round(matched_rev / total_rev * 100, 1) if total_rev else 0.0,
        "coverageUnitsPct": round(matched_units / total_units * 100, 1) if total_units else 0.0,
    }


def cost_coverage(
    sales: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    mappings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Qué parte del REVENUE tiene coste VERIFICADO (identidad + coste real)."""
    if mappings is None:
        mappings = load_mappings()
    catalog_index = build_catalog_index(catalog)
    ignored = load_ignored()
    products_with_cost = 0
    products_without = 0
    # FASE 15: cost_by_sku precomputado — evita el bucle interno
    # O(catálogo) que se ejecutaba por cada línea de venta.
    cost_by_sku: dict[str, bool] = {}
    for p in catalog:
        if not isinstance(p, dict):
            continue
        sku = str(p.get("sku") or "").strip()
        if sku:
            cost_by_sku[sku] = cost_available(p)
        if cost_available(p):
            products_with_cost += 1
        else:
            products_without += 1
    rev_with = 0.0
    rev_without = 0.0
    sales_with = 0
    sales_without = 0
    for s in sales:
        if not isinstance(s, dict):
            continue
        for li in business_model.normalize_sale_lines(s):
            qty = _f(li.get("quantity")) or 1.0
            price = _f(li.get("price"))
            amount = (price or 0.0) * qty
            ident = resolve_identity(li, catalog, mappings, catalog_index=catalog_index, ignored=ignored)
            has_cost = bool(ident.get("matched") and cost_by_sku.get(str(ident.get("canonicalProductId") or "")))
            if has_cost:
                rev_with += amount
                sales_with += 1
            else:
                rev_without += amount
                sales_without += 1
    total_rev = rev_with + rev_without
    return {
        "productsWithVerifiedCost": products_with_cost,
        "productsWithMissingCost": products_without,
        "productsTotal": products_with_cost + products_without,
        # PRE-BETA: las dos bases de cobertura son métricas distintas y se
        # exponen por separado: por Nº de productos (catálogo) y por REVENUE.
        "productsCoveragePct": round(products_with_cost / (products_with_cost + products_without) * 100, 1) if (products_with_cost + products_without) else 0.0,
        "salesWithVerifiedCost": sales_with,
        "salesWithMissingCost": sales_without,
        "revenueWithVerifiedCost": round(rev_with, 2),
        "revenueWithMissingCost": round(rev_without, 2),
        "coveragePct": round(rev_with / total_rev * 100, 1) if total_rev else 0.0,
    }
