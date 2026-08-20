"""DATA MIGRATION & DATA INTEGRITY PROTOCOL (FASE 14 — gobernanza de datos).

Una actualización de VANOVA NUNCA asume "si los datos ya estaban, son correctos".
Este módulo implementa:

- dataSchemaVersion explícito (ruta de migración por versión de esquema).
- Estados de calidad: VERIFIED / IMPORTED / LEGACY / NEEDS_REVIEW / INVALID / UNKNOWN.
- Procedencia (provenance): de dónde salió cada entidad y cuándo fue validada.
- validate_data_integrity(): auditoría reutilizable, READ-ONLY por defecto.
- run_migration_protocol(): flujo de actualización (backup → auditar → marcar
  legacy → revalidar → reporte). Idempotente y NO destructivo.
- evaluate_sync_guard(): alerta/bloqueo cuando una sync reduciría drásticamente
  cobertura (regresión H23).
- data_health(): resumen "Salud de los datos" para el dashboard.
- factory_reset(): restablecimiento explícito con backup previo.

Regla absoluta: VERACIDAD > COMPLETITUD. Si un dato no puede verificarse, se
marca y se explica — nunca se trata como verificado, nunca se inventa, nunca se
borra.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("maios.data_governance")

# --------------------------------------------------------------------------
# Versión de esquema de datos
# --------------------------------------------------------------------------
DATA_SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# Estados de calidad
# --------------------------------------------------------------------------
QUALITY_VERIFIED = "verified"
QUALITY_IMPORTED = "imported"
QUALITY_LEGACY = "legacy"
QUALITY_NEEDS_REVIEW = "needs_review"
QUALITY_INVALID = "invalid"
QUALITY_UNKNOWN = "unknown"

QUALITY_STATES = (
    QUALITY_VERIFIED,
    QUALITY_IMPORTED,
    QUALITY_LEGACY,
    QUALITY_NEEDS_REVIEW,
    QUALITY_INVALID,
    QUALITY_UNKNOWN,
)

QUALITY_LABELS = {
    QUALITY_VERIFIED: "Verificado",
    QUALITY_IMPORTED: "Importado",
    QUALITY_LEGACY: "Legado",
    QUALITY_NEEDS_REVIEW: "Requiere revisión",
    QUALITY_INVALID: "Inválido",
    QUALITY_UNKNOWN: "Desconocido",
}

# Fuentes que cuentan como evidencia de verificación contra un origen externo.
_VERIFIED_SOURCES = {"shopify", "facturascripts", "facturascript", "erp"}
# Fuentes de importación (correctas pero sin verificación externa posterior).
_IMPORTED_SOURCES = {"excel", "local", "csv", "imported", "file", "manual_import"}

# --------------------------------------------------------------------------
# Field ownership (P7): qué campos pertenecen a cada fuente. Una sync solo
# actualiza los campos de SU fuente; nunca reemplaza enriquecimientos locales.
# --------------------------------------------------------------------------
FIELD_OWNERSHIP: dict[str, dict[str, tuple[str, ...]]] = {
    "shopify": {
        "product": (
            "name", "sku", "barcode", "rrp", "sellingPrice", "variantId",
            "variant_id", "externalId", "stock", "inventoryQty", "tags",
            "productType", "vendor", "imageUrl",
        ),
        "order": (
            "id", "order_id", "date", "total", "subtotal", "customer",
            "customerEmail", "status", "line_items", "financialStatus",
        ),
        "line": ("sku", "variantId", "variant_id", "quantity", "price", "title"),
    },
    "facturascripts": {
        "invoice": ("id", "number", "date", "dueDate", "total", "paid", "status",
                    "customerId", "supplierId"),
        "payment": ("id", "type", "amount", "date", "account"),
        "supplier": ("id", "name", "nif", "email"),
    },
    "vanova": {
        # Enriquecimiento local: VANOVA es el único dueño. Una sync NUNCA los
        # pisa (regresión H23).
        "product": (
            "cost", "costSource", "costStatus", "sourceReference", "costUpdatedAt",
            "qualityStatus", "legacyFromVersion", "lastValidatedAt",
            "identityMappingId", "category", "classification", "notes", "tags_local",
        ),
        "order": ("qualityStatus", "legacyFromVersion", "lastValidatedAt", "notes"),
        "line": ("identityMappingId", "qualityStatus", "canonicalProductId"),
    },
}

_OWNER_OF: dict[str, set[str]] = {}
for _owner, _entities in FIELD_OWNERSHIP.items():
    for _fields in _entities.values():
        _OWNER_OF.setdefault(_owner, set()).update(_fields)

# --------------------------------------------------------------------------
# Estado generado por VANOVA que se reconstruye desde los archivos/integraciones.
# "Limpiar y volver a importar" borra SOLO esto (nunca archivos del PC, nunca
# la identidad de la empresa, nunca la configuración de la instalación).
# --------------------------------------------------------------------------
BUSINESS_STATE_KEYS = frozenset(
    {
        # Datos de negocio importados/organizados (se reconstruyen en el escaneo)
        "organizedProducts",
        "organizedSales",
        "organizedCustomers",
        "organizedSuppliers",
        "organizedInvoices",
        "organizedInvoiceLines",
        "organizedFinance",
        "financialReconciliation",
        "facturascriptSync",
        "shopifySync",
        "dataNormalizationVersion",
        "fileOrganization",
        # Derivados del análisis: se regeneran al re-analizar
        "businessFindings",
        "detectionRunAt",
        "insights",
        "recommendations",
        "importantItems",
        "companyModel",
        "hermesActivity",
        "fileCandidates",
        "dashboardSnapshot",
        "lastScan",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _quality_field(entity: dict[str, Any]) -> str | None:
    """Estado explícito si la entidad ya lo declara (calidad persistida)."""
    q = _clean_text(entity.get("qualityStatus"))
    if q in QUALITY_STATES:
        return q
    return None


def _provenance_of(entity: dict[str, Any]) -> dict[str, Any]:
    p = entity.get("dataProvenance")
    return p if isinstance(p, dict) else {}


# --------------------------------------------------------------------------
# Inferencia de calidad por tipo de entidad
# --------------------------------------------------------------------------
def infer_product_quality(p: dict[str, Any]) -> tuple[str, str]:
    """Estado de calidad de un producto + motivo (nunca inventa)."""
    explicit = _quality_field(p)
    if explicit:
        return explicit, "estado explícito persistido"

    name = _clean_text(p.get("name"))
    sku = _clean_text(p.get("sku"))
    if not name and not sku:
        return QUALITY_INVALID, "producto sin nombre ni SKU"

    rrp = _as_float(p.get("rrp"))
    net = _as_float(p.get("netPrice"))
    cost = _as_float(p.get("cost"))
    if (rrp is not None and rrp < 0) or (net is not None and net < 0) or (cost is not None and cost < 0):
        return QUALITY_INVALID, "valor imposible (precio o coste negativo)"

    src = _clean_text(p.get("source")).lower()
    cost_status = _clean_text(p.get("costStatus")).lower()
    cost_source = _clean_text(p.get("costSource"))

    # Contradicción: dice verified pero falta el coste o la fuente.
    if cost_status == "verified" and (cost is None or not cost_source):
        return QUALITY_NEEDS_REVIEW, "costStatus=verified sin coste o sin costSource"

    # PVD == coste sin evidencia → nunca coste real (regla FASE 11).
    if (
        cost_status in ("", "missing")
        and net is not None and rrp is not None
        and abs(net - rrp) < 1e-9
        and not cost_source
    ):
        return QUALITY_NEEDS_REVIEW, "coste == PVD sin evidencia de coste real"

    # Evidencia de verificación: fuente externa conectada o coste verificado.
    if src in _VERIFIED_SOURCES or (cost_status == "verified" and cost_source):
        return QUALITY_VERIFIED, "verificado contra fuente externa o coste con procedencia"

    if src in _IMPORTED_SOURCES or cost_source or p.get("dataProvenance"):
        return QUALITY_IMPORTED, "importado correctamente, sin verificación externa"

    if not src and not p.get("dataProvenance") and not cost_status:
        return QUALITY_LEGACY, "heredado de versión anterior sin evidencia de validación"

    return QUALITY_UNKNOWN, "sin información suficiente para determinar el estado"


def infer_order_quality(o: dict[str, Any]) -> tuple[str, str]:
    explicit = _quality_field(o)
    if explicit:
        return explicit, "estado explícito persistido"

    oid = _clean_text(o.get("id") or o.get("order_id") or o.get("order"))
    if not oid:
        return QUALITY_INVALID, "pedido sin identificador"

    total = _as_float(o.get("total"))
    if total is not None and total < 0:
        return QUALITY_INVALID, "total negativo"

    src = _clean_text(o.get("source")).lower()

    lines = o.get("line_items")
    if isinstance(lines, list) and lines:
        line_total = sum(
            _as_float(li.get("price")) * int(li.get("quantity") or 1)
            for li in lines if isinstance(li, dict)
        )
        # Umbral relativo: gastos de envío/descuentos normales no son una
        # inconsistencia; solo se marca si la desviación es material (>15%).
        if total is not None and line_total and not o.get("subtotal"):
            deviation = abs(line_total - total)
            if deviation > max(5.0, 0.15 * total):
                return QUALITY_NEEDS_REVIEW, "total del pedido no cuadra con sus líneas"

    date = _clean_text(o.get("date"))
    if src in _VERIFIED_SOURCES:
        if not date:
            return QUALITY_NEEDS_REVIEW, "pedido verificado de fuente externa sin fecha"
        return QUALITY_VERIFIED, "verificado contra fuente externa"

    if src in _IMPORTED_SOURCES or o.get("dataProvenance"):
        if not date:
            return QUALITY_NEEDS_REVIEW, "pedido importado sin fecha"
        return QUALITY_IMPORTED, "importado correctamente, sin verificación externa"

    if not src and not o.get("dataProvenance"):
        return QUALITY_LEGACY, "heredado de versión anterior sin evidencia de validación"

    return QUALITY_UNKNOWN, "sin información suficiente para determinar el estado"


def infer_line_quality(li: dict[str, Any]) -> tuple[str, str]:
    explicit = _quality_field(li)
    if explicit:
        return explicit, "estado explícito persistido"

    sku = _clean_text(li.get("sku") or li.get("product") or li.get("variant_id"))
    if not sku:
        return QUALITY_NEEDS_REVIEW, "línea sin SKU (no se puede enlazar con el catálogo)"

    qty = li.get("quantity")
    if qty is not None and _as_float(qty) is not None and _as_float(qty) <= 0:
        return QUALITY_INVALID, "cantidad no positiva"

    if li.get("canonicalProductId") or li.get("identityMappingId"):
        return QUALITY_VERIFIED, "identidad de producto resuelta"

    return QUALITY_NEEDS_REVIEW, "SKU presente pero sin match de identidad"


def infer_customer_quality(c: dict[str, Any]) -> tuple[str, str]:
    explicit = _quality_field(c)
    if explicit:
        return explicit, "estado explícito persistido"

    cid = _clean_text(c.get("id") or c.get("customer_id"))
    email = _clean_text(c.get("email"))
    name = _clean_text(c.get("name"))
    if not cid and not email and not name:
        return QUALITY_INVALID, "cliente sin identificación"
    if email and "@" not in email:
        return QUALITY_NEEDS_REVIEW, "email con formato inválido"

    src = _clean_text(c.get("source")).lower()
    if src in _VERIFIED_SOURCES or (cid and email):
        return QUALITY_VERIFIED, "identificado con fuente externa o email"
    if src in _IMPORTED_SOURCES or c.get("dataProvenance") or cid:
        return QUALITY_IMPORTED, "importado correctamente"
    if not src and not c.get("dataProvenance"):
        return QUALITY_LEGACY, "heredado de versión anterior sin evidencia de validación"
    return QUALITY_UNKNOWN, "sin información suficiente"


def _count_entity_lines(
    lines: list[dict[str, Any]],
    products: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> dict[str, Any]:
    """Conteo de calidad de líneas usando la identidad canónica resuelta.

    La identidad de una línea (SKU → producto del catálogo) se resuelve en la
    capa product_identity; una línea con SKU que existe en el catálogo es
    VERIFIED, una sin SKU o sin match es NEEDS_REVIEW.
    """
    try:
        from . import product_identity

        sales_for_coverage = orders or [{"line_items": lines}]
        ic = product_identity.identity_coverage(sales_for_coverage, products)
    except Exception:  # noqa: BLE001
        ic = {}

    matched = int(ic.get("matchedLines") or 0)
    unmatched = int(ic.get("unmatchedLines") or 0)
    counts = _empty_counts()
    counts["verified"] = matched
    counts["needs_review"] = unmatched
    counts["total"] = len(lines)

    issues: list[dict[str, Any]] = []
    for li in lines:
        if not isinstance(li, dict):
            continue
        sku = _clean_text(li.get("sku") or li.get("product") or li.get("variant_id"))
        if not sku:
            issues.append({
                "entity": "line",
                "id": sku or _clean_text(li.get("title"))[:60],
                "state": QUALITY_NEEDS_REVIEW,
                "reason": "línea sin SKU (no se puede enlazar con el catálogo)",
            })
    return {"counts": counts, "issues": issues}


def _classify_entity(entity: dict[str, Any], kind: str) -> tuple[str, str]:
    if kind == "product":
        return infer_product_quality(entity)
    if kind == "order":
        return infer_order_quality(entity)
    if kind == "line":
        return infer_line_quality(entity)
    if kind == "customer":
        return infer_customer_quality(entity)
    return QUALITY_UNKNOWN, "tipo de entidad no soportado por la auditoría"


# --------------------------------------------------------------------------
# Auditoría de integridad (READ-ONLY por defecto)
# --------------------------------------------------------------------------
def _empty_counts() -> dict[str, int]:
    return {s: 0 for s in QUALITY_STATES}


def _count_entities(entities: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    counts = _empty_counts()
    issues: list[dict[str, Any]] = []
    for e in entities:
        if not isinstance(e, dict):
            continue
        state, reason = _classify_entity(e, kind)
        counts[state] += 1
        if state in (QUALITY_NEEDS_REVIEW, QUALITY_INVALID, QUALITY_LEGACY, QUALITY_UNKNOWN):
            issues.append({
                "entity": kind,
                "id": _clean_text(e.get("id") or e.get("order_id") or e.get("sku") or e.get("name"))[:60],
                "state": state,
                "reason": reason,
            })
    counts["total"] = len(entities)
    return {"counts": counts, "issues": issues}


def _duplicate_check(entities: list[dict[str, Any]], kind: str, key_fn) -> list[dict[str, Any]]:
    """Detecta identidades duplicadas (mismo SKU/id/email en dos entidades)."""
    seen: dict[str, list[str]] = {}
    for e in entities:
        if not isinstance(e, dict):
            continue
        key = key_fn(e)
        if not key:
            continue
        eid = _clean_text(e.get("id") or e.get("order_id") or e.get("sku") or e.get("name"))[:60]
        seen.setdefault(key.lower(), []).append(eid)
    out: list[dict[str, Any]] = []
    for key, ids in seen.items():
        if len(set(ids)) > 1:
            out.append({
                "entity": kind,
                "duplicateKey": key,
                "ids": ids[:5],
                "state": QUALITY_NEEDS_REVIEW,
                "reason": "identidad duplicada en varias entidades",
            })
    return out


def _load_entities() -> dict[str, list[dict[str, Any]]]:
    from . import config_store

    data = config_store.load()
    products = [p for p in (data.get("organizedProducts") or []) if isinstance(p, dict)]
    sales = [s for s in (data.get("organizedSales") or []) if isinstance(s, dict)]
    # B-02: las filas rechazadas por validación se conservan en
    # organizedSalesReview — cuentan como needs_review en Data Health.
    review = [r for r in (data.get("organizedSalesReview") or []) if isinstance(r, dict)]
    customers = [c for c in (data.get("organizedCustomers") or []) if isinstance(c, dict)]
    invoices = [i for i in (data.get("organizedInvoices") or []) if isinstance(i, dict)]
    finance = [f for f in (data.get("organizedFinance") or []) if isinstance(f, dict)]

    lines: list[dict[str, Any]] = []
    for s in sales:
        li = s.get("line_items")
        if isinstance(li, list):
            lines.extend(x for x in li if isinstance(x, dict))
    return {
        "products": products,
        "orders": sales + review,
        "orderLines": lines,
        "customers": customers,
        "invoices": invoices,
        "finance": finance,
    }


def validate_data_integrity(
    *,
    entities: dict[str, list[dict[str, Any]]] | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    """Auditoría reutilizable de integridad de datos.

    READ-ONLY por defecto: no modifica entidades. ``persist=True`` guarda el
    informe y el timestamp de última validación en dataGovernance.
    """
    if entities is None:
        entities = _load_entities()

    report: dict[str, Any] = {
        "ok": True,
        "generatedAt": _now(),
        "schemaVersion": DATA_SCHEMA_VERSION,
        "byEntity": {},
        "issues": [],
        "summary": _empty_counts(),
    }

    totals = _empty_counts()
    total_entities = 0
    for kind in ("products", "orders", "orderLines", "customers", "invoices", "finance"):
        rows = entities.get(kind) or []
        total_entities += len(rows)
        if not rows:
            report["byEntity"][kind] = {"counts": {**_empty_counts(), "total": 0}, "issues": []}
            continue
        if kind == "orderLines":
            # Las líneas NO guardan su identidad resuelta; se usa el conteo
            # canónico de identidad (product_identity.identity_coverage) para
            # no marcar como "sin match" líneas que SÍ tienen identidad.
            block = _count_entity_lines(rows, entities.get("products") or [], entities.get("orders") or [])
        else:
            block = _count_entities(rows, "product" if kind == "products" else "order" if kind == "orders"
                                    else "customer" if kind == "customers" else "order")
        for s in QUALITY_STATES:
            totals[s] += block["counts"][s]
        report["byEntity"][kind] = block
        report["issues"].extend(block["issues"])

    # Duplicados (solo donde tiene sentido: productos por SKU, clientes por email).
    if entities.get("products"):
        report["issues"].extend(_duplicate_check(
            entities["products"], "product", lambda e: _clean_text(e.get("sku"))))
    if entities.get("customers"):
        report["issues"].extend(_duplicate_check(
            entities["customers"], "customer", lambda e: _clean_text(e.get("email") or e.get("name"))))

    report["summary"] = totals
    report["summary"]["total"] = total_entities
    report["needsReviewCount"] = totals[QUALITY_NEEDS_REVIEW] + totals[QUALITY_LEGACY] + totals[QUALITY_UNKNOWN]
    report["invalidCount"] = totals[QUALITY_INVALID]
    report["legacyCount"] = totals[QUALITY_LEGACY]
    report["verifiedCount"] = totals[QUALITY_VERIFIED]

    if totals[QUALITY_INVALID]:
        report["status"] = "FAIL"
        report["ok"] = False
    elif totals[QUALITY_NEEDS_REVIEW] or totals[QUALITY_LEGACY] or totals[QUALITY_UNKNOWN]:
        report["status"] = "REVIEW"
    else:
        report["status"] = "PASS"

    if persist:
        try:
            from . import config_store

            data = config_store.load()
            gov = data.get("dataGovernance") or {}
            config_store.save({"dataGovernance": {
                **gov,
                "dataSchemaVersion": gov.get("dataSchemaVersion") or DATA_SCHEMA_VERSION,
                "lastIntegrityCheck": report["generatedAt"],
                "lastDataValidation": report["generatedAt"],
                "lastIntegrityStatus": report["status"],
                "lastIntegritySummary": {
                    "total": total_entities,
                    "verified": totals[QUALITY_VERIFIED],
                    "imported": totals[QUALITY_IMPORTED],
                    "legacy": totals[QUALITY_LEGACY],
                    "needs_review": totals[QUALITY_NEEDS_REVIEW],
                    "invalid": totals[QUALITY_INVALID],
                    "unknown": totals[QUALITY_UNKNOWN],
                },
            }})
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo persistir el informe de integridad: %s", exc)

    return report


# --------------------------------------------------------------------------
# Marcado de datos heredados (LEGACY / NEEDS_REVIEW) — NO destructivo
# --------------------------------------------------------------------------
def mark_legacy_unverified(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Marca entidades heredadas sin evidencia de validación como LEGACY y las
    que presentan contradicciones como NEEDS_REVIEW.

    Reglas:
    - NUNCA toca entidades con evidencia (source, costStatus, provenance).
    - NUNCA borra nada.
    - Solo escribe qualityStatus / legacyFromVersion / lastValidatedAt.
    - Idempotente: re-ejecutar no cambia entidades ya marcadas.
    """
    from . import config_store

    if data is None:
        data = config_store.load()

    gov = data.get("dataGovernance") or {}
    created_by = gov.get("dataCreatedByVersion") or data.get("version") or "unknown"

    marked = {"products": 0, "orders": 0, "customers": 0, "needs_review": 0}
    changed = False

    def _apply(entity: dict[str, Any], kind: str) -> None:
        nonlocal changed
        if not isinstance(entity, dict):
            return
        if entity.get("qualityStatus"):
            return  # ya clasificado — idempotente
        state, _reason = _classify_entity(entity, kind)
        if state in (QUALITY_LEGACY, QUALITY_NEEDS_REVIEW, QUALITY_UNKNOWN):
            entity["qualityStatus"] = state
            entity["lastValidatedAt"] = _now()
            if state == QUALITY_LEGACY:
                entity["legacyFromVersion"] = created_by
            entity.setdefault("dataProvenance", {})["markedLegacy"] = True
            key = "needs_review" if state != QUALITY_LEGACY else (
                "products" if kind == "product" else "orders" if kind == "order" else "customers")
            marked[key] = marked.get(key, 0) + 1
            changed = True

    for p in data.get("organizedProducts") or []:
        _apply(p, "product")
        marked["products"] = marked.get("products") or 0
    for o in data.get("organizedSales") or []:
        _apply(o, "order")
    for c in data.get("organizedCustomers") or []:
        _apply(c, "customer")

    if changed:
        config_store.save(data)

    return {
        "markedLegacy": marked,
        "dataCreatedByVersion": created_by,
        "applied": changed,
        "note": "Nunca se borran datos; solo se marcan y se explica el motivo.",
    }


# --------------------------------------------------------------------------
# Protocolo de migración (UPDATE → BACKUP → MIGRATE → AUDIT → REPORT)
# --------------------------------------------------------------------------
def _app_version() -> str:
    try:
        from . import updater

        return updater.current_version()
    except Exception:  # noqa: BLE001
        return ""


def run_migration_protocol(*, force: bool = False) -> dict[str, Any]:
    """Protocolo formal que se ejecuta al arrancar tras un cambio de versión.

    Flujo: BACKUP → detectar versión → auditar → marcar legacy → revalidar →
    reporte → registro. Idempotente: con esquema al día y sin cambios de
    versión pendientes no vuelve a migrar.
    """
    from . import backup_service, config_store

    data = config_store.load()
    gov = data.get("dataGovernance") or {}
    current_schema = int(gov.get("dataSchemaVersion") or 0)
    app_version = _app_version()
    recorded_version = _clean_text(data.get("version")) or "unknown"

    is_fresh = not data.get("setupComplete") and not (data.get("organizedProducts") or data.get("organizedSales"))

    if is_fresh:
        config_store.save({"dataGovernance": {
            **gov,
            "dataSchemaVersion": DATA_SCHEMA_VERSION,
            "dataMigrationVersion": app_version,
            "dataCreatedByVersion": app_version,
            "migrationStatus": "fresh_install",
            "lastMigrationAt": _now(),
        }})
        return {
            "status": "fresh_install",
            "message": "Instalación nueva — protocolo de migración omitido.",
            "schemaVersion": DATA_SCHEMA_VERSION,
        }

    # La migración la decide la VERSIÓN DE ESQUEMA, no la versión de la app:
    # una app nueva con el mismo esquema no necesita re-migrar (idempotente).
    if current_schema >= DATA_SCHEMA_VERSION and not force:
        # Asegurado de marcado: entidades SIN estado de calidad (p. ej. perdido
        # por syncs de versiones anteriores que pisaban campos de gobernanza) se
        # vuelven a clasificar. Idempotente y NO destructivo.
        try:
            ensure = mark_legacy_unverified()
        except Exception as exc:  # noqa: BLE001
            log.warning("Asegurado de marcado de calidad falló: %s", exc)
            ensure = {}
        return {
            "status": "up_to_date",
            "message": "Esquema de datos al día — sin migración necesaria.",
            "schemaVersion": current_schema,
            "marked": ensure.get("markedLegacy"),
        }

    # UPDATE PATH
    protocol: dict[str, Any] = {
        "status": "migrated",
        "fromSchemaVersion": current_schema or 0,
        "toSchemaVersion": DATA_SCHEMA_VERSION,
        "fromVersion": recorded_version,
        "toVersion": app_version,
        "migratedAt": _now(),
        "steps": {},
    }

    # 1) BACKUP — si falla, NO se modifica NINGÚN dato (regla: backup fallido →
    # abortar; no migrar, no marcar, no guardar). Se registra el error y se
    # reintenta en el siguiente arranque.
    backup_ok = False
    try:
        backup = backup_service.run_backup(reason="pre-migration")
        backup_ok = bool(backup.get("ok"))
        protocol["steps"]["backup"] = {
            "ok": True,
            "path": str(backup.get("path") or backup.get("backupPath") or ""),
        }
    except Exception as exc:  # noqa: BLE001
        protocol["steps"]["backup"] = {"ok": False, "error": str(exc)}
        log.warning("Backup pre-migración falló: %s", exc)

    if not backup_ok:
        protocol["status"] = "backup_failed"
        protocol["integrity"] = "NOT_RUN"
        protocol["blockedReason"] = "El backup previo a la migración falló — ningún dato fue modificado."
        log.error("Migración abortada: el backup pre-migración falló. Ningún dato modificado.")
        return protocol

    # 2) AUDITAR antes
    try:
        before = validate_data_integrity()
        protocol["steps"]["auditBefore"] = {"ok": True, "summary": before["summary"]}
    except Exception as exc:  # noqa: BLE001
        protocol["steps"]["auditBefore"] = {"ok": False, "error": str(exc)}
        before = None

    # 3) MARCAR LEGACY (datos heredados no verificables)
    try:
        mark_result = mark_legacy_unverified(data)
        protocol["steps"]["markLegacy"] = mark_result
    except Exception as exc:  # noqa: BLE001
        protocol["steps"]["markLegacy"] = {"ok": False, "error": str(exc)}
        mark_result = None

    # 4) AUDITAR después
    try:
        after = validate_data_integrity()
        protocol["steps"]["auditAfter"] = {"ok": True, "summary": after["summary"], "status": after["status"]}
    except Exception as exc:  # noqa: BLE001
        protocol["steps"]["auditAfter"] = {"ok": False, "error": str(exc)}
        after = None

    integrity = after.get("status") if after else "UNKNOWN"
    protocol["integrity"] = integrity
    protocol["legacyMarked"] = (mark_result or {}).get("markedLegacy")
    protocol["summary"] = (after or before or {}).get("summary")

    # 5) REGISTRAR gobernanza
    config_store.save({"dataGovernance": {
        **gov,
        "dataSchemaVersion": DATA_SCHEMA_VERSION,
        "dataMigrationVersion": app_version,
        "dataCreatedByVersion": gov.get("dataCreatedByVersion") or recorded_version,
        "lastMigrationAt": protocol["migratedAt"],
        "migrationStatus": "migrated",
        "lastIntegrityCheck": (after or {}).get("generatedAt"),
        "lastIntegrityStatus": integrity,
        "lastMigrationReport": protocol,
    }})

    return protocol


# --------------------------------------------------------------------------
# Data Health (dashboard)
# --------------------------------------------------------------------------
def data_health() -> dict[str, Any]:
    """Resumen "Salud de los datos" para el dashboard. Todo viene del backend,
    nunca inventado."""
    from . import config_store

    data = config_store.load()
    gov = data.get("dataGovernance") or {}
    report = validate_data_integrity()

    per_entity: dict[str, dict[str, Any]] = {}
    for kind, block in report["byEntity"].items():
        per_entity[kind] = block["counts"]

    return {
        "ok": True,
        "generatedAt": report["generatedAt"],
        "lastValidation": gov.get("lastIntegrityCheck"),
        "lastMigration": gov.get("dataMigrationVersion"),
        "schemaVersion": int(gov.get("dataSchemaVersion") or report["schemaVersion"]),
        "migrationStatus": gov.get("migrationStatus", "never_run"),
        "status": report["status"],
        "entities": per_entity,
        "totals": report["summary"],
        "needsReviewCount": report["needsReviewCount"],
        "invalidCount": report["invalidCount"],
        "legacyCount": report["legacyCount"],
        "verifiedCount": report["verifiedCount"],
        "issues": report["issues"][:50],
        "issueCount": len(report["issues"]),
    }


def _review_counts(data: dict[str, Any] | None = None) -> dict[str, int]:
    """Conteo LIGERO de entidades en estado de revisión (usa el qualityStatus
    persistido; no ejecuta la auditoría completa). Pensado para el contexto de
    Hermes: barato y canónico."""
    from . import config_store

    if data is None:
        data = config_store.load()
    counts = {"needs_review": 0, "legacy": 0, "invalid": 0}
    kinds = (("organizedProducts", "product"), ("organizedSales", "order"), ("organizedCustomers", "customer"))
    for key, kind in kinds:
        for e in data.get(key) or []:
            if not isinstance(e, dict):
                continue
            q = _clean_text(e.get("qualityStatus"))
            if not q or q not in QUALITY_STATES:
                # Sin estado persistido (p. ej. entidad INVALID nunca marcada):
                # se clasifica para que el conteo sea canónico, no solo persistido.
                q, _reason = _classify_entity(e, kind)
            if q == QUALITY_INVALID:
                counts["invalid"] += 1
            elif q in (QUALITY_NEEDS_REVIEW, QUALITY_UNKNOWN):
                counts["needs_review"] += 1
            elif q == QUALITY_LEGACY:
                counts["legacy"] += 1
    # B-02: las filas de venta rechazadas por validación (fechas/totales
    # imposibles) viven en organizedSalesReview con evidencia — cuentan como
    # needs_review para que Data Health y Hermes las vean.
    for e in data.get("organizedSalesReview") or []:
        if isinstance(e, dict) and _clean_text(e.get("qualityStatus")) in QUALITY_STATES:
            counts["needs_review"] += 1
    counts["total"] = counts["needs_review"] + counts["legacy"] + counts["invalid"]
    return counts


# --------------------------------------------------------------------------
# Guard post-sync (P16): una sync nunca puede destruir cobertura (H23)
# --------------------------------------------------------------------------
def evaluate_sync_guard(
    existing_products: list[dict[str, Any]],
    existing_sales: list[dict[str, Any]],
    merged_products: list[dict[str, Any]],
    merged_sales: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compara cobertura y volumen ANTES vs DESPUÉS del merge.

    Si la sync reduciría drásticamente cobertura de coste/identidad o el número
    de productos/pedidos sin justificación, devuelve blocked=True. La sync debe
    entonces NO aplicar el merge (regla H23: 414 costes → 0 costes).
    """
    from . import product_identity

    def _metrics(products, sales) -> dict[str, Any]:
        cc = product_identity.cost_coverage(sales, products)
        ic = product_identity.identity_coverage(sales, products)
        return {
            "products": len(products),
            "orders": len(sales),
            "costCoveragePct": cc.get("coveragePct") or 0.0,
            "identityCoveragePct": ic.get("coveragePct") or 0.0,
            "verifiedCosts": cc.get("productsWithVerifiedCost") or 0,
        }

    before = _metrics(existing_products, existing_sales)
    after = _metrics(merged_products, merged_sales)

    alerts: list[str] = []
    blocked = False

    # Caída drástica de cobertura de costes (>30 puntos porcentuales o >50% relativa)
    if before["costCoveragePct"] >= 30 and after["costCoveragePct"] < before["costCoveragePct"] - 30:
        alerts.append(
            f"La sincronización reduciría la cobertura de costes del {before['costCoveragePct']:.1f}% "
            f"al {after['costCoveragePct']:.1f}% — sin cambios aplicados."
        )
        blocked = True
    elif before["costCoveragePct"] > 0 and after["costCoveragePct"] == 0 and before["verifiedCosts"] > 0 and after["verifiedCosts"] == 0:
        alerts.append(
            "La sincronización eliminaría TODOS los costes verificados (H23) — sin cambios aplicados."
        )
        blocked = True

    # Caída drástica de identidad
    if before["identityCoveragePct"] >= 30 and after["identityCoveragePct"] < before["identityCoveragePct"] - 30:
        alerts.append(
            f"La sincronización reduciría la cobertura de identidad del {before['identityCoveragePct']:.1f}% "
            f"al {after['identityCoveragePct']:.1f}% — sin cambios aplicados."
        )
        blocked = True

    # Pérdida masiva de volumen sin justificación (sync parcial vacía)
    if before["products"] > 0 and after["products"] < before["products"] * 0.5:
        alerts.append(
            f"La sincronización reduciría el catálogo de {before['products']} a {after['products']} productos — "
            "posible sync parcial; sin cambios aplicados."
        )
        blocked = True

    return {
        "blocked": blocked,
        "alerts": alerts,
        "before": before,
        "after": after,
    }


# --------------------------------------------------------------------------
# Factory reset (P14) — operación explícita, con backup y confirmación
# --------------------------------------------------------------------------
def clear_business_data(*, confirmed: bool = False) -> dict[str, Any]:
    """Limpia SOLO el estado empresarial generado por VANOVA (para re-importar).

    Usado por «Escaneo → Limpiar y volver a importar»: borra los datos de
    negocio importados y sus derivados (findings, insights, recomendaciones,
    memoria) para reconstruirlos desde los archivos encontrados. NUNCA toca:
    - archivos físicos del PC;
    - la identidad de la empresa (companyProfile);
    - la configuración de la instalación (setupComplete, scanFolders,
      aiProviders, hermes, uiPrefs).

    Antes de borrar nada crea un backup; si el backup falla, aborta.
    """
    if not confirmed:
        return {
            "ok": False,
            "error": "Confirmación requerida. Esto eliminará los datos empresariales importados.",
        }

    from . import backup_service, config_store

    try:
        backup = backup_service.run_backup(reason="scan-clean-reimport")
    except Exception as exc:  # noqa: BLE001
        log.error("Limpieza abortada: el backup previo falló. Ningún dato fue borrado: %s", exc)
        return {
            "ok": False,
            "error": "El backup previo falló — ningún dato fue borrado.",
            "backupError": str(exc),
        }

    cfg = config_store.remove_keys(sorted(BUSINESS_STATE_KEYS))
    # El escaneo que sigue re-poblará el inventario y el análisis (organize_files)
    # regenerará los derivados automáticamente. No dejamos flags de estado
    # huérfanos en el config (limpieza de estado persistido).
    return {
        "ok": True,
        "message": "Datos empresariales limpiados. El escaneo reconstruirá los datos desde los archivos.",
        "backupPath": str(backup.get("path") or backup.get("backupPath") or ""),
        "cleared": sorted(BUSINESS_STATE_KEYS),
        "setupComplete": bool(cfg.get("setupComplete")),
    }


def factory_reset(*, confirmed: bool = False) -> dict[str, Any]:
    """Restablecimiento COMPLETO (factory reset) de la instalación.

    Deja VANOVA exactamente como una instalación inicial: configuración,
    datos empresariales importados, findings, insights, recomendaciones,
    memoria/modelo de empresa, historial y conexiones locales vuelven a su
    estado de fábrica y el Setup vuelve a aparecer.

    NO es consecuencia de una actualización: exige confirmación explícita.
    Antes de borrar nada crea un backup automático; si el backup falla, aborta
    sin tocar ningún dato. Los archivos originales del PC NUNCA se borran.
    """
    if not confirmed:
        return {
            "ok": False,
            "error": "Confirmación requerida. Esto eliminará TODOS los datos de VANOVA y volverás al Setup.",
        }

    from . import backup_service, config_store, integrations_store
    from .paths import data_dir

    # Backups fallido → NUNCA se borra nada (abortar antes de tocar datos).
    try:
        backup = backup_service.run_backup(reason="factory-reset")
    except Exception as exc:  # noqa: BLE001
        log.error("Factory reset abortado: el backup previo falló. Ningún dato fue borrado: %s", exc)
        return {
            "ok": False,
            "error": "El backup previo al restablecimiento falló — ningún dato fue borrado.",
            "backupError": str(exc),
        }

    # 1) Configuración → estado de primera instalación (reescritura completa:
    #    desaparecen datos de negocio, findings, insights, recomendaciones,
    #    memoria, historial, integraciones, preferencias).
    config_store.reset_to_defaults()

    # 2) Bases de datos locales de decisión/estado (aprobaciones y tareas).
    #    Con reintento corto: en Windows un handle residual (antivirus, WAL)
    #    puede bloquear el borrado de forma transitoria.
    import time as _time

    removed_db: list[str] = []
    for db_name in ("approvals.db", "tasks.db"):
        for suffix in ("", "-wal", "-shm"):
            f = data_dir() / (db_name + suffix)
            if not f.exists():
                continue
            for _attempt in range(4):
                try:
                    f.unlink()
                    removed_db.append(f.name)
                    break
                except OSError as exc:
                    if _attempt >= 3:
                        log.warning("Factory reset: no se pudo eliminar %s: %s", f, exc)
                    else:
                        _time.sleep(0.15 * (_attempt + 1))

    # 3) Desconectar integraciones de negocio (sus credenciales viven en
    #    config; la limpieza de arriba ya las borró — este paso asegura que
    #    el store queda coherente). Los secretos del sistema (install_secrets)
    #    se conservan: sin ellos el runtime no podría autenticarse.
    for integration_id in ("shopify", "facturascripts"):
        try:
            integrations_store.disconnect(integration_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("Factory reset: no se pudo desconectar %s: %s", integration_id, exc)

    return {
        "ok": True,
        "message": "VANOVA restablecida por completo. Volverás al Setup inicial.",
        "backupPath": str(backup.get("path") or backup.get("backupPath") or ""),
        "removedDatabases": removed_db,
        "setupComplete": False,
    }
