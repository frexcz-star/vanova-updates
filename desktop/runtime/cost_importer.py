"""VANOVA Cost Importer — FASE 12 (P6).

Importador SEGURO de costes reales de adquisición. Reglas:

  * BACKUP → PREVIEW → CONFIRM → IMPORT → INTEGRITY (el preview nunca escribe).
  * Solo AÑADE campos de coste al catálogo (cost, costSource, costStatus,
    sourceReference, updatedAt) — NUNCA toca sku/name/netPrice/rrp originales.
  * Matching por fiabilidad: SKU directo → barcode/EAN → nombre SOLO propuesta
    (nunca match automático por nombre).
  * Si un coste ya existe y el nuevo difiere → se registra como "changed" y se
    requiere confirmación (no se sobrescribe silenciosamente).
  * Cada coste importado conserva procedencia (costSource + sourceReference).

Flujo: cost_importer.preview(rows) → usuario revisa → cost_importer.apply(rows).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import config_store

COST_SOURCES = ("supplier", "erp", "facturascripts", "manual", "imported_file", "unknown")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normaliza filas {sku, ean, name, cost, rrp?, sourceReference?}."""
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sku = str(r.get("sku") or "").strip()
        ean = str(r.get("ean") or r.get("barcode") or "").strip()
        name = str(r.get("name") or "").strip()
        cost = _f(r.get("cost") if r.get("cost") is not None else r.get("netPrice"))
        if cost is None or cost < 0:
            continue
        if not (sku or ean or name):
            continue
        out.append({
            "sku": sku,
            "ean": ean,
            "name": name,
            "cost": cost,
            "rrp": _f(r.get("rrp")),
            "sourceReference": str(r.get("sourceReference") or r.get("source") or "cost_import")[:160],
        })
    return out


def _catalog_index(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    by_sku: dict[str, dict[str, Any]] = {}
    by_ean: dict[str, dict[str, Any]] = {}
    by_norm_name: dict[str, list[dict[str, Any]]] = {}
    import re
    import unicodedata

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "")
        s = "".join(c for c in s if not unicodedata.combining(c)).lower()
        return re.sub(r"[^a-z0-9]+", " ", s).strip()

    for p in catalog:
        if not isinstance(p, dict):
            continue
        sku = str(p.get("sku") or "").strip()
        if sku:
            by_sku[sku.lower()] = p
        for key in ("barcode", "ean", "ean13"):
            e = str(p.get(key) or "").strip()
            if e:
                by_ean[e] = p
        n = norm(p.get("name"))
        if n:
            by_norm_name.setdefault(n, []).append(p)
    return {"by_sku": by_sku, "by_ean": by_ean, "by_norm_name": by_norm_name, "norm": norm}


def preview(rows: list[dict[str, Any]], catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """PREVIEW — nunca escribe. Devuelve el plan exacto de importación."""
    if catalog is None:
        catalog = config_store.load().get("organizedProducts") or []
    parsed = parse_rows(rows)
    idx = _catalog_index(catalog)

    items: list[dict[str, Any]] = []
    matched = changed = new_cost = ambiguous = unmatched = 0
    for r in parsed:
        p = None
        method = None
        sku = r["sku"]
        ean = r["ean"]
        # 1) SKU directo
        if sku and sku.lower() in idx["by_sku"]:
            p = idx["by_sku"][sku.lower()]
            method = "sku"
        # 2) barcode/EAN
        elif ean and ean in idx["by_ean"]:
            p = idx["by_ean"][ean]
            method = "barcode"
        # 3) nombre → SOLO propuesta, nunca automático
        elif r["name"]:
            n = idx["norm"](r["name"])
            candidates = idx["by_norm_name"].get(n, [])
            if len(candidates) == 1:
                p = candidates[0]
                method = "name_suggestion"
            elif len(candidates) > 1:
                ambiguous += 1
        if p is None:
            unmatched += 1
            items.append({
                "row": r, "matched": False, "method": method or "none",
                "catalogSku": None, "catalogName": None,
                "currentCost": None, "currentCostStatus": None, "newCost": r["cost"],
                "action": "skip", "reason": "no_match",
            })
            continue
        current = _f(p.get("cost"))
        status = str(p.get("costStatus") or "missing")
        if current is None:
            new_cost += 1
            action = "add"
        elif abs(current - r["cost"]) < 0.001:
            matched += 1
            action = "keep"
        else:
            changed += 1
            action = "update"
        if action != "keep":
            matched += 1
        items.append({
            "row": r, "matched": True, "method": method,
            "catalogSku": str(p.get("sku") or ""),
            "catalogName": str(p.get("name") or ""),
            "currentCost": current, "currentCostStatus": status,
            "newCost": r["cost"], "action": action, "reason": None,
        })

    return {
        "ok": True,
        "counts": {
            "rows": len(parsed),
            "matched": matched,
            "changed": changed,
            "newCost": new_cost,
            "ambiguous": ambiguous,
            "unmatched": unmatched,
        },
        "items": items,
        "basis": (
            "matching por SKU directo → barcode/EAN → nombre SOLO propuesta; "
            "nunca se sobrescribe un coste sin 'update' explícito; los originales "
            "sku/name/netPrice/rrp no se tocan"
        ),
    }


def apply(
    rows: list[dict[str, Any]],
    *,
    catalog: list[dict[str, Any]] | None = None,
    cost_source: str = "supplier",
    persist: bool = True,
) -> dict[str, Any]:
    """CONFIRM → IMPORT. Aplica el plan del preview. Requiere backup previo
    (responsabilidad del llamador: /api/costs/import hace backup automático)."""
    if cost_source not in COST_SOURCES:
        return {"ok": False, "error": f"costSource inválido: {cost_source}"}
    if catalog is None:
        data = config_store.load()
        catalog = list(data.get("organizedProducts") or [])
    else:
        data = {"organizedProducts": catalog}

    plan = preview(rows, catalog)
    if not plan.get("ok"):
        return plan
    counts = plan["counts"]
    # Solo se aplican los que NO son 'keep' (no duplica trabajo) y no ambiguos.
    by_sku: dict[str, dict[str, Any]] = {}
    by_ean: dict[str, dict[str, Any]] = {}
    idx = _catalog_index(catalog)
    for p in catalog:
        sku = str(p.get("sku") or "").strip()
        if sku:
            by_sku[sku.lower()] = p
        for key in ("barcode", "ean", "ean13"):
            e = str(p.get(key) or "").strip()
            if e:
                by_ean[e] = p

    now = _now()

    # Aplicar los costes a los productos del catálogo.
    # BUG-037 (fix): RMW atómico. Antes se hacía load() → modificar `catalog`
    # (copia local) → save({"organizedProducts": catalog}) SOBRESCRIBIENDO la
    # lista completa. Si otro hilo (shopify sync, file_organizer, otro import)
    # añadía productos entre el load y el save, se perdían (lost-update, patrón
    # BUG-006/015/019/023/034). Ahora `config_store.update()` hace el RMW dentro
    # del _config_lock y re-aplica los costes al catálogo ACTUAL.
    def _apply_cost_to_product(p: dict[str, Any], r: dict[str, Any]) -> bool:
        sku = str(p.get("sku") or "").strip().lower()
        ean = str(p.get("barcode") or p.get("ean") or p.get("ean13") or "").strip()
        if r.get("sku") and sku == str(r["sku"]).strip().lower():
            return True
        if r.get("ean") and ean == str(r["ean"]).strip():
            return True
        return False

    if persist:
        try:
            applied = 0

            def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
                nonlocal applied
                catalog = list(cfg.get("organizedProducts") or [])
                for it in plan["items"]:
                    if not it["matched"] or it["action"] == "keep":
                        continue
                    r = it["row"]
                    for p in catalog:
                        if _apply_cost_to_product(p, r):
                            p["cost"] = r["cost"]
                            p["costSource"] = cost_source
                            p["costStatus"] = (
                                "verified"
                                if cost_source in ("supplier", "erp", "facturascripts", "manual")
                                else "imported"
                            )
                            p["sourceReference"] = r["sourceReference"]
                            p["costUpdatedAt"] = now
                            applied += 1
                            break
                cfg["organizedProducts"] = catalog
                return cfg

            config_store.update(_mutate)
        except Exception as exc:
            return {"ok": False, "error": f"Error al persistir: {exc}", "applied": applied}

    from . import business_model

    integrity = business_model.integrity_report({"organizedProducts": catalog})
    return {
        "ok": True,
        "applied": applied,
        "counts": counts,
        "integrity": {"ok": integrity.get("ok"), "issues": len(integrity.get("issues") or [])},
        "costSource": cost_source,
        "costStatus": "verified" if cost_source in ("supplier", "erp", "facturascripts", "manual") else "imported",
        "note": "Solo se añadieron campos de coste; sku/name/netPrice/rrp originales intactos.",
    }
