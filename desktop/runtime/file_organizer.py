"""Hermes file organizer — classify imported/scanned files and route to Products/Sales."""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config_store, file_relevance, task_queue
from .logger import get_logger

log = get_logger("maios.organizer", "file-organizer")

PRODUCT_NAME_HINTS = (
    "product", "products", "catalog", "catalogo", "catálogo", "precio", "precios",
    "price", "sku", "inventory", "inventario", "stock", "articulo", "artículo",
    "tarifa", "lista", "item", "items",
)
SALES_NAME_HINTS = (
    "venta", "ventas", "sales", "sale", "order", "orders", "pedido", "pedidos",
    "invoice", "factura", "facturas", "customer", "cliente", "clientes", "revenue",
    "ingreso", "ingresos", "pipeline", "crm",
)
PRODUCT_HEADER_HINTS = (
    "sku", "product", "producto", "precio", "price", "net", "rrp", "pvp",
    "articulo", "artículo", "ean", "barcode",
)
SALES_HEADER_HINTS = (
    "order", "pedido", "sale", "venta", "invoice", "factura", "total", "amount",
    "importe", "customer", "cliente", "fecha", "date",
)
CUSTOMER_NAME_HINTS = (
    "customer", "customer_name", "client", "client_name", "cliente", "nombre_cliente",
    "buyer", "buyer_name", "comprador", "nombre", "full_name", "fullname",
)
CUSTOMER_HEADER_HINTS = (
    "customer", "cliente", "customer_name", "client", "nombre", "email", "correo",
    "phone", "telefono", "teléfono", "nif", "cif", "vat", "province", "provincia",
    "country", "pais", "país", "activity", "actividad",
)
NORMALIZATION_VERSION = 7
# Storage must not silently drop valid rows. This is a protective upper bound
# for a single imported file, not the UI/agent response limit.
# Cap de seguridad anti-memoria para un solo archivo. Nunca es silencioso:
# cuando un archivo excede el cap, organize_files lo reporta en el resumen
# (truncatedRows/truncatedFiles) para que la UI avise al usuario.
MAX_IMPORT_ROWS = 100_000
# Límite de FILAS devueltas por get_sales para la UI. El summary sigue
# cubriendo el dataset completo; esto solo acota el payload de la tabla
# (la UI renderiza ~100 filas; 10k filas eran ~3 MB de JSON → latencia alta).
_SALES_ROWS_LIMIT = 2_000


def organization_status() -> dict[str, Any]:
    data = config_store.load()
    org = data.get("fileOrganization") or {}
    products = [p for p in (data.get("organizedProducts") or []) if not _is_legacy_entity(p)]
    sales = [s for s in (data.get("organizedSales") or []) if not _is_legacy_entity(s)]
    customers = [c for c in (data.get("organizedCustomers") or []) if not _is_legacy_entity(c)]
    return {
        "status": org.get("status", "idle"),
        "lastRun": org.get("completedAt"),
        "message": org.get("message", ""),
        "counts": {
            "products": len(products),
            "sales": len(sales),
            "files": org.get("fileCount", 0),
            "productFiles": org.get("productFiles", 0),
            "salesFiles": org.get("salesFiles", 0),
            "customerFiles": org.get("customerFiles", 0),
            "customers": len(customers),
        },
        "hermesTaskId": org.get("hermesTaskId"),
    }


def get_products() -> dict[str, Any]:
    _ensure_normalized_data()
    products = config_store.load().get("organizedProducts") or []
    if not isinstance(products, list):
        products = []
    products = [p for p in products if _is_product_entity(p) and not _is_legacy_entity(p)]
    # BUG real (Nico): el catálogo debe mostrar productos ÚNICOS (colapsar
    # duplicados marcados 'needs_review' por SKU/nombre), no las filas brutas
    # (p.ej. 4000 filas vs 400 SKU reales). Los duplicados marcados se conservan
    # en organizedProducts para la vista de revisión 'Vincula tus productos'.
    unique: dict[str, dict[str, Any]] = {}
    for p in products:
        sku = str(p.get("sku") or "").strip().lower()
        key = sku or ("name:" + str(p.get("name") or "").strip().lower())
        if not key.strip("name:"):
            continue
        if key not in unique:
            unique[key] = p
    products = list(unique.values())
    return {"products": products, "count": len(products), "source": "local"}


def _is_product_entity(item: Any) -> bool:
    """Reject integration error strings masquerading as product rows."""
    if not isinstance(item, dict):
        return False
    name = str(item.get("name") or "").strip()
    if not name:
        return False
    lower = name.lower()
    if any(
        marker in lower
        for marker in (
            "faltan permisos de shopify",
            "shopify conectado pero faltan",
            "no se pudieron descargar datos de shopify",
        )
    ):
        return False
    return True


def add_product(entry: dict[str, Any]) -> dict[str, Any]:
    """Append a manually entered product to the local catalog.

    BUG-012 FIX: usa config_store.update() (RMW atómico bajo un solo lock).
    Antes hacía load() → añadir → save() sin serializar el ciclo completo;
    con ThreadingHTTPServer (/api/products/add) dos POST concurrentes podían
    hacer lost-update (el producto añadido primero se perdía).
    """
    name = (entry.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "El nombre del producto es obligatorio"}
    sku = (entry.get("sku") or "").strip()
    net = _parse_optional_float(entry.get("netPrice"))
    rrp = _parse_optional_float(entry.get("rrp"))
    product = {
        "name": name,
        "sku": sku,
        "netPrice": net,
        "rrp": rrp,
        "source": "manual",
    }
    products: list[dict[str, Any]] = []

    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        nonlocal products
        raw = cfg.get("organizedProducts") or []
        items = list(raw) if isinstance(raw, list) else []
        products = _dedupe_products(items + [product])
        cfg["organizedProducts"] = products
        return cfg

    config_store.update(_mutate)
    sync_dashboard_overview(products=products)
    return {"ok": True, "product": product, "count": len(products), "products": products}


def get_sales() -> dict[str, Any]:
    """Ventas para la UI: el RESUMEN se calcula sobre el dataset COMPLETO, pero
    la lista de filas se limita a _SALES_ROWS_LIMIT (la UI solo renderiza ~100).
    Con 100k+ filas, devolver todo serializaba varios MB y el GET acababa en
    timeout — sin perdida de información: totalCount informa del dataset real."""
    _ensure_normalized_data()
    data = config_store.load()
    return get_sales_with_data(data)


def get_customers() -> dict[str, Any]:
    """Return normalized customer records, never arbitrary source columns."""
    _ensure_normalized_data()
    data = config_store.load()
    explicit = data.get("organizedCustomers") or []
    if not isinstance(explicit, list):
        explicit = []
    by_key: dict[str, dict[str, Any]] = {}
    for customer in explicit:
        if isinstance(customer, dict) and not _is_legacy_entity(customer):
            _merge_customer_row(by_key, customer)
    sales_counted: set[str] = set()
    for sale in data.get("organizedSales") or []:
        if isinstance(sale, dict) and not _is_legacy_entity(sale):
            name = str(sale.get("customer") or "").strip()
            if not name or name == "—":
                continue
            customer_key = _merge_customer_row(by_key, {
                "name": name,
                "email": sale.get("customerEmail"),
                "phone": sale.get("customerPhone"),
                "taxId": sale.get("customerTaxId"),
                "province": sale.get("customerProvince"),
                "country": sale.get("customerCountry"),
                "activity": sale.get("customerActivity"),
                "orders": 0,
                "total": 0,
            })
            row = by_key[customer_key]
            if customer_key not in sales_counted:
                # Orders are the authoritative totals when available; do not
                # add them on top of a separate CRM/customer export.
                row["orders"] = 0
                row["total"] = 0
                sales_counted.add(customer_key)
            row["orders"] = int(row.get("orders") or 0) + 1
            row["total"] = round(float(row.get("total") or 0) + float(sale.get("total") or 0), 2)
    rows = list(by_key.values())
    rows.sort(key=lambda row: float(row.get("total") or 0), reverse=True)
    return {"customers": rows, "count": len(rows), "source": "local"}


def organize_files(files: list[dict[str, Any]] | None = None, *, trigger_hermes: bool = True) -> dict[str, Any]:
    """Classify files, extract tabular data, persist for Products/Sales views."""
    data = config_store.load()
    if files is None:
        files = data.get("scanFiles") or []
    if not isinstance(files, list):
        files = []

    config_store.save({
        "fileOrganization": {
            "status": "running",
            "startedAt": _now(),
            "message": "Hermes organizando archivos…",
        }
    })

    product_files: list[dict[str, Any]] = []
    sales_files: list[dict[str, Any]] = []
    customer_files: list[dict[str, Any]] = []
    other_files: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    sales: list[dict[str, Any]] = []
    customers: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    review_sales: list[dict[str, Any]] = []
    # VANOVA 3.0: filas descartadas por el cap de seguridad por archivo
    # (MAX_IMPORT_ROWS). NUNCA silencioso: se reportan en el resumen para que
    # la UI avise al usuario de que el archivo se importó parcialmente.
    truncated_rows: dict[str, int] = {}
    # B-02: las filas de venta inválidas de importaciones ANTERIORES (guardadas
    # antes de la validación) también deben migrar al store de revisión. Se
    # recolectan aquí durante el merge final y NUNCA entran en organizedSales.
    migrated_review_sales: list[dict[str, Any]] = []

    tagged_files: list[dict[str, Any]] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        record = dict(entry)
        legacy_reason = file_relevance.legacy_app_artifact(record)
        if legacy_reason:
            exclusions.append({
                "path": record.get("path") or record.get("name") or "",
                "name": record.get("name") or "",
                "reason": legacy_reason,
                "excludedAt": _now(),
            })
            continue
        category = classify_file(record)
        record["category"] = category
        tagged_files.append(record)
        if category == "products":
            product_files.append(record)
            products.extend(_extract_products(record, truncated_rows))
        elif category == "sales":
            sales_files.append(record)
            extracted = _extract_sales(record, truncated_rows)
            for _row in extracted:
                if _row.get("_saleIssue"):
                    review_sales.append(_row)
                else:
                    sales.append(_row)
        elif category == "customers":
            customer_files.append(record)
            customers.extend(_extract_customers(record, truncated_rows))
        else:
            other_files.append(record)

    # Treat the persisted normalized datasets as the source of truth. A startup
    # scan can legitimately return zero rows when a previously imported file is
    # offline, moved, permission-protected, or only represented by a preview.
    # Never replace good rows with that empty/partial result. New extraction wins
    # for the same key; existing rows survive when extraction cannot reproduce
    # them. Only proven legacy app artifacts are excluded.
    products = _dedupe_products(products)
    sales = _dedupe_sales(sales)
    customers = _dedupe_customers(customers)

    # B-02 (auditoría comercial): las filas de venta inválidas NUNCA se borran
    # ni se deduplican en silencio. Se conservan en organizedSalesReview con
    # evidencia (sourceRow, sourceFile, motivo) para Data Health, y quedan
    # FUERA de organizedSales — así revenue/resumen/detección no se contaminan.
    review_sales = _dedupe_review_sales(review_sales)

    existing = config_store.load()
    existing_review = existing.get("organizedSalesReview") or []
    if not isinstance(existing_review, list):
        existing_review = []
    review_sales = _dedupe_review_sales(existing_review + review_sales)
    existing_products = [
        p for p in (existing.get("organizedProducts") or [])
        if _is_preservable_product(p)
    ]
    existing_sales = [
        s for s in (existing.get("organizedSales") or [])
        if _is_preservable_sale(s)
    ]
    existing_customers = [
        c for c in (existing.get("organizedCustomers") or [])
        if _is_preservable_customer(c)
    ]
    # FASE 13 (P11): las filas procedentes de UN CONECTOR sincronizado (Shopify,
    # FacturaScripts, WooCommerce, PrestaShop… cualquier fuente del registro)
    # son autoritativas sobre la extracción de archivos en el organize: no se
    # pisan con datos de ficheros. Sin hardcodear una fuente concreta.
    synced_products = [p for p in existing_products if _is_connector_source(p)]
    synced_sales = [s for s in existing_sales if _is_connector_source(s)]
    synced_customers = [c for c in existing_customers if _is_connector_source(c)]
    products = _merge_products(existing_products + products, synced_products)
    sales = _merge_sales(existing_sales + sales, synced_sales)
    customers = _merge_customers(existing_customers + customers, synced_customers)
    # B-02: particionar el resultado FINAL — cualquier fila que no supere la
    # validación canónica (incluidas las ya guardadas por versiones anteriores
    # antes de que existiera la validación) se mueve a organizedSalesReview con
    # evidencia y queda FUERA de las métricas. La validación es la misma que usa
    # business_model.revenue/sales_summary (UNKNOWN nunca cuenta como 0).
    partitioned_sales: list[dict[str, Any]] = []
    for _row in sales:
        issue = _sale_row_issue(_row)
        if issue:
            _row.setdefault("_saleIssue", issue)
            _row["qualityStatus"] = "needs_review"
            _row["qualityReason"] = issue
            migrated_review_sales.append(_row)
        else:
            partitioned_sales.append(_row)
    sales = partitioned_sales
    review_sales = _dedupe_review_sales(review_sales + migrated_review_sales)
    preserved_counts = {
        "products": len(existing_products),
        "sales": len(existing_sales),
        "customers": len(existing_customers),
    }

    hermes_task = None
    if trigger_hermes:
        hermes_task = task_queue.enqueue(
            "hermes",
            "organize_files",
            {
                "productFiles": len(product_files),
                "salesFiles": len(sales_files),
                "customerFiles": len(customer_files),
                "otherFiles": len(other_files),
            },
        )

    org_result = {
        "status": "ok",
        "completedAt": _now(),
        "message": (
            f"Organizados {len(product_files)} productos, {len(sales_files)} ventas y "
            f"{len(customer_files)} archivos de clientes "
            f"({len(products)} filas producto, {len(sales)} filas venta, {len(customers)} clientes)."
        ),
        "fileCount": len(tagged_files),
        "excludedFileCount": len(exclusions),
        "productFiles": len(product_files),
        "salesFiles": len(sales_files),
        "customerFiles": len(customer_files),
        "hermesTaskId": hermes_task.get("id") if hermes_task else None,
        "preservedExisting": preserved_counts,
        "reviewSales": len(review_sales),
        "rejectedSales": len(review_sales),
        "truncatedRows": sum(truncated_rows.values()),
        "truncatedFiles": truncated_rows,
        "importSummary": {
            "productsImported": len(products),
            "salesImported": len(sales),
            "customersImported": len(customers),
            "salesRejected": len(review_sales),
            "truncatedRows": sum(truncated_rows.values()),
            "truncatedFiles": dict(truncated_rows),
            "preserved": preserved_counts,
        },
        "dataLossGuard": True,
    }

    previous_exclusions = existing.get("scanExclusions") or []
    if not isinstance(previous_exclusions, list):
        previous_exclusions = []
    by_excluded_path = {str(e.get("path") or "").lower(): e for e in previous_exclusions if isinstance(e, dict)}
    for exclusion in exclusions:
        by_excluded_path[str(exclusion.get("path") or "").lower()] = exclusion

    config_store.save({
        "scanFiles": tagged_files,
        # Do not truncate persisted business data. UI/API consumers may page or
        # limit their own responses, but the local source of truth must be lossless.
        "organizedProducts": products,
        "organizedSales": sales,
        "organizedCustomers": customers,
        "organizedSalesReview": review_sales,
        "scanExclusions": list(by_excluded_path.values())[-500:],
        "dataNormalizationVersion": NORMALIZATION_VERSION,
        "fileOrganization": org_result,
    })
    # Post-update data validation: record the app version that wrote this
    # dataset so a later update can offer a safe re-import (never a wipe).
    try:
        from . import data_version

        data_version.stamp_import(
            source="files",
            counts={
                "products": len(products),
                "sales": len(sales),
                "customers": len(customers),
                "salesRejected": len(review_sales),
                "productFiles": len(product_files),
                "salesFiles": len(sales_files),
                "customerFiles": len(customer_files),
                "preservedExisting": preserved_counts,
                "newProducts": max(0, len(products) - preserved_counts.get("products", 0)),
                "newSales": max(0, len(sales) - preserved_counts.get("sales", 0)),
                "newCustomers": max(0, len(customers) - preserved_counts.get("customers", 0)),
            },
        )
    except Exception:  # noqa: BLE001 — never block the import on stamping
        log.warning("Could not stamp data version after organize", exc_info=True)

    sync_dashboard_overview(products, sales)

    # VANOVA PROACTIVA — tras cada importación/sincronización importante:
    # 1) se reconstruye la memoria empresarial (qué vende, cómo vende, qué falta);
    # 2) se ejecuta el motor de detección determinista sobre los datos REALES
    #    recién importados (no espera a que el usuario pulse «Analizar»);
    # 3) los findings activos se convierten en insights de usuario con evidencia
    #    y acción, deduplicados por firma (el mismo hallazgo no genera spam).
    # IMPORTANTE (aislamiento): TODO el análisis usa el config en memoria que
    # acaba de construir ESTE organize — nunca relee/reescribe el config de
    # otra instalación. Los tests que llaman organize_files con un store
    # parcheado capturan businessFindings/insights/companyModel ahí mismo.
    try:
        from . import company_model, detection_engine, insight_store

        model = company_model.build_company_model(data)
        data["companyModel"] = model
        config_store.save({"companyModel": model})
    except Exception:  # noqa: BLE001 — la memoria nunca debe romper la importación
        log.warning("Could not refresh company model after organize", exc_info=True)

    try:
        from . import prioritization

        result = detection_engine.run_detection(data, persist=False)
        if isinstance(result, dict) and result.get("findings"):
            data["businessFindings"] = result["findings"]
            data["detectionRunAt"] = result.get("ranAt")
            insight_store.sync_from_findings(result["findings"], data=data, active_signatures=result.get("freshSignatures"))
            # Prioridades reales del motor (score económico, determinista).
            top = prioritization.build_priorities(result["findings"])
            prioritization.persist(top, data=data)
            # FASE 8 — memoria de recomendaciones (dedup por firma): registrar
            # los hallazgos con prioridad para poder medir su evolución.
            try:
                from . import recommendation_store

                for p in top[:5]:
                    fnd = next((x for x in result["findings"] if x.get("id") == p.get("findingId")), None)
                    if fnd:
                        recommendation_store.record_finding(fnd, data=data)
                recommendation_store.sync_resolutions(result["findings"], active_signatures=result.get("freshSignatures"), data=data)
            except Exception:  # noqa: BLE001
                pass
            config_store.save({
                "businessFindings": result["findings"],
                "detectionRunAt": result.get("ranAt"),
                "insights": data.get("insights") or [],
                "priorities": data.get("priorities") or [],
                "recommendations": data.get("recommendations") or [],
            })
        log.info(
            "Proactive analysis after organize: %s",
            str((result or {}).get("counts") or {}),
        )
    except Exception:  # noqa: BLE001 — el análisis nunca debe romper la importación
        log.warning("Could not run proactive detection after organize", exc_info=True)

    log.info(
        "File organization complete: %d product files, %d sales files, %d customer files, %d exclusions",
        len(product_files),
        len(sales_files),
        len(customer_files),
        len(exclusions),
    )
    return {
        "ok": True,
        "organization": org_result,
        "products": len(products),
        "sales": len(sales),
        "customers": len(customers),
        "salesReview": len(review_sales),
    }


def classify_file(entry: dict[str, Any]) -> str:
    """Return products | sales | customers | other using schema-aware signals."""
    if file_relevance.legacy_app_artifact(entry):
        return "other"
    name = (entry.get("name") or entry.get("path") or "").lower()
    path = entry.get("path") or ""
    ext = (entry.get("ext") or "").lower().lstrip(".")

    product_score = sum(1 for hint in PRODUCT_NAME_HINTS if hint in name)
    sales_score = sum(1 for hint in SALES_NAME_HINTS if hint in name)
    customer_score = sum(1 for hint in CUSTOMER_NAME_HINTS if hint in name)

    content = entry.get("contentPreview") or _read_snippet(path, ext)
    if not content and ext in {"xlsx", "xls", "ods"} and path:
        try:
            header_rows = _read_spreadsheet_dict_rows(Path(path), ext, max_rows=2)
            if header_rows:
                content = ",".join(str(key) for key in header_rows[0].keys())
        except Exception:
            content = ""
    if content:
        lower = content.lower()
        product_score += sum(1 for hint in PRODUCT_HEADER_HINTS if hint in lower)
        sales_score += sum(1 for hint in SALES_HEADER_HINTS if hint in lower)
        customer_score += sum(1 for hint in CUSTOMER_HEADER_HINTS if hint in lower)

    # A customer export is recognized only when it has an identity signal. A
    # file containing province/country/activity alone must not become customers.
    customer_identity = any(token in (content or "").lower() for token in (
        "customer", "cliente", "client", "nombre", "name", "email", "correo", "nif", "cif", "vat"
    ))
    if customer_score > sales_score and customer_score >= product_score and customer_identity:
        return "customers"
    if product_score > sales_score and product_score > customer_score and product_score > 0:
        return "products"
    if sales_score >= customer_score and sales_score > product_score and sales_score > 0:
        return "sales"
    if ext in {"xlsx", "xls", "csv", "ods", "tsv"} and product_score == sales_score == customer_score == 0:
        # Neutral tabular files remain products only as a conservative fallback;
        # they still need a valid product schema before rows are created.
        return "products"
    return "other"


def _detect_delimiter(text: str, default: str = ",") -> str:
    """Detect common CSV export separators without guessing from data rows."""
    first = next((line for line in (text or "").splitlines() if line.strip()), "")
    if not first:
        return default
    candidates = [(",", first.count(",")), (";", first.count(";")), ("\\t", first.count("\\t")), ("|", first.count("|"))]
    delimiter, count = max(candidates, key=lambda item: item[1])
    return delimiter if count > 0 else default


def _read_snippet(path: str, ext: str, max_bytes: int = 8192) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ""
    try:
        if ext in {"csv", "txt", "tsv"}:
            return p.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
        if ext == "json":
            raw = p.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
            try:
                return json.dumps(json.loads(raw), ensure_ascii=False)[:max_bytes]
            except json.JSONDecodeError:
                return raw
    except OSError:
        return ""
    return ""


def _extract_products(entry: dict[str, Any], truncated: dict[str, int] | None = None) -> list[dict[str, Any]]:
    path = entry.get("path") or ""
    ext = (entry.get("ext") or "").lower().lstrip(".")
    source_name = entry.get("name") or Path(path).name or "import"
    p = Path(path)
    if ext in {"xlsx", "xls", "ods"}:
        if not p.exists():
            return []
        dict_rows = _read_spreadsheet_dict_rows(p, ext)
        return _parse_product_dict_rows(dict_rows, source_name, truncated)
    if ext == "json":
        return _parse_product_dict_rows(_read_json_dict_rows(p, entry.get("contentPreview")), source_name, truncated)
    if ext not in {"csv", "tsv", "txt"}:
        return []
    delimiter = "\t" if ext == "tsv" else ","
    # H24 (FASE 16): igual que en ventas — el contentPreview de la UI está
    # truncado a 64KB; si el archivo existe en disco se lee SIEMPRE completo.
    if not p.exists():
        preview = entry.get("contentPreview") or ""
        if not preview:
            return []
        return _parse_product_rows(preview, _detect_delimiter(preview, delimiter), source_name, truncated)
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        log.debug("Product read failed for %s: %s", path, exc)
        return []
    return _parse_product_rows(text, _detect_delimiter(text, delimiter), source_name, truncated)


def _parse_product_rows(text: str, delimiter: str, source_name: str, truncated: dict[str, int] | None = None) -> list[dict[str, Any]]:
    try:
        import io

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            return []
        dict_rows: list[dict[str, Any]] = []
        for i, row in enumerate(reader):
            if i < MAX_IMPORT_ROWS:
                dict_rows.append(dict(row))
            elif truncated is not None:
                truncated[source_name] = truncated.get(source_name, 0) + 1
        return _parse_product_dict_rows(dict_rows, source_name, truncated)
    except csv.Error as exc:
        log.debug("Product parse failed for %s: %s", source_name, exc)
        return []


def _parse_product_dict_rows(dict_rows: list[dict[str, Any]], source_name: str, truncated: dict[str, int] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not dict_rows:
        return rows
    sample = dict_rows[0]
    fields = {(_norm(str(h))): str(h) for h in sample.keys() if h}
    for i, row in enumerate(dict_rows):
        if i >= MAX_IMPORT_ROWS:
            if truncated is not None:
                truncated[source_name] = truncated.get(source_name, 0) + (len(dict_rows) - i)
            break
        str_row = {str(k): str(v) if v is not None else "" for k, v in row.items()}
        name = _pick(str_row, fields, (
            "product_name", "productname", "product", "producto", "nombre_producto", "articulo", "artículo",
            "item_name", "title", "name", "description",
        ))
        sku = _pick(str_row, fields, (
            "sku", "product_sku", "code", "codigo", "código", "ean", "barcode", "ref", "reference",
        ))
        # Generic "price/precio" is a sale price. Cost is only accepted from
        # explicit cost/net/purchase columns, avoiding silent margin corruption.
        net = _pick_number(str_row, fields, (
            "cost_price", "costprice", "purchase_price", "buy_price", "wholesale_price",
            "precio_coste", "precio_compra", "coste", "cost", "net_price_ex_works", "netpriceexworks", "ex_works", "net_price", "netprice", "net",
        ))
        rrp = _pick_number(str_row, fields, (
            "sale_price", "selling_price", "retail_price", "public_price", "precio_venta",
            "precio_publico", "precio_público", "rrp", "pvp", "retail", "msrp", "price", "precio",
        ))
        stock = _pick_number(str_row, fields, ("stock", "stock_qty", "stock_quantity", "inventory", "inventario"))
        if not name and not sku:
            continue
        item = {
            "name": name or sku or f"Producto {i + 1}",
            "sku": sku or "",
            "netPrice": net,
            "rrp": rrp,
            "stock": stock,
            "sourceFile": source_name,
            "sourceRow": i + 2,  # header is row 1; preserves raw-row provenance
            "source": "excel",
        }
        # A missing SKU is evidence to review, not a reason to discard the row.
        if not sku:
            _mark_quality(item, "missing_sku")
        rows.append(item)
    return rows


def _extract_sales(entry: dict[str, Any], truncated: dict[str, int] | None = None) -> list[dict[str, Any]]:
    path = entry.get("path") or ""
    ext = (entry.get("ext") or "").lower().lstrip(".")
    source_name = entry.get("name") or Path(path).name or "import"
    p = Path(path)
    if ext in {"xlsx", "xls", "ods"}:
        if not p.exists():
            return []
        dict_rows = _read_spreadsheet_dict_rows(p, ext)
        return _parse_sales_dict_rows(dict_rows, source_name, truncated)
    if ext == "json":
        return _parse_sales_dict_rows(_read_json_dict_rows(p, entry.get("contentPreview")), source_name, truncated)
    if ext not in {"csv", "tsv", "txt"}:
        return []
    delimiter = "\t" if ext == "tsv" else ","
    # H24 (FASE 16): el contentPreview que llega de la UI está TRUNCADO a
    # 64KB. Usarlo como fuente de verdad hacía que los CSV de ventas >64KB se
    # importaran de forma parcial y silenciosa (datos incompletos en el modelo
    # canónico). El preview solo debe servir para clasificar el tipo de archivo;
    # la extracción SIEMPRE lee el archivo completo del disco cuando existe.
    if not p.exists():
        preview = entry.get("contentPreview") or ""
        if not preview:
            return []
        delimiter = _detect_delimiter(preview, delimiter)
        return _parse_sales_rows(preview, delimiter, source_name, truncated)
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        log.debug("Sales read failed for %s: %s", path, exc)
        return []
    return _parse_sales_rows(text, _detect_delimiter(text, delimiter), source_name, truncated)


def _duplicate_headers(fieldnames: list[str] | None) -> list[str]:
    """Columnas repetidas en la cabecera (p.ej. dos columnas 'total'). Un CSV
    así es ambiguo: csv.DictReader se queda con la última y descarta la primera
    en silencio (pérdida de datos). Lo detectamos para marcar las filas como
    needs_review en lugar de inventar cuál columna es la buena."""
    seen: dict[str, int] = {}
    dupes: list[str] = []
    for h in fieldnames or []:
        key = str(h or "").strip()
        if not key:
            continue
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            dupes.append(key)
    return dupes


def _parse_sales_rows(text: str, delimiter: str, source_name: str, truncated: dict[str, int] | None = None) -> list[dict[str, Any]]:
    try:
        import io

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            return []
        dupes = _duplicate_headers(reader.fieldnames)
        dict_rows: list[dict[str, Any]] = []
        for i, row in enumerate(reader):
            if i < MAX_IMPORT_ROWS:
                dict_rows.append(dict(row))
            elif truncated is not None:
                truncated[source_name] = truncated.get(source_name, 0) + 1
        return _parse_sales_dict_rows(dict_rows, source_name, truncated, duplicate_headers=dupes)
    except csv.Error as exc:
        log.debug("Sales parse failed for %s: %s", source_name, exc)
        return []


def _parse_sales_dict_rows(dict_rows: list[dict[str, Any]], source_name: str, truncated: dict[str, int] | None = None, duplicate_headers: list[str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not dict_rows:
        return rows
    sample = dict_rows[0]
    fields = {(_norm(str(h))): str(h) for h in sample.keys() if h}
    for i, row in enumerate(dict_rows):
        if i >= MAX_IMPORT_ROWS:
            if truncated is not None:
                truncated[source_name] = truncated.get(source_name, 0) + (len(dict_rows) - i)
            break
        str_row = {str(k): str(v) if v is not None else "" for k, v in row.items()}
        order_id = _pick(str_row, fields, (
            "order_id", "order_number", "order_no", "pedido_id", "numero_pedido", "número_pedido",
            "invoice_id", "invoice_number", "factura_id", "factura_numero", "reference", "id",
        ))
        customer = _pick(str_row, fields, (
            "customer_name", "customername", "client_name", "clientname", "nombre_cliente",
            "cliente", "customer", "buyer_name", "buyername", "comprador", "full_name", "fullname", "name",
        ))
        customer_email = _pick(str_row, fields, ("customer_email", "client_email", "email", "correo", "correo_electronico"))
        customer_phone = _pick(str_row, fields, ("customer_phone", "client_phone", "phone", "telefono", "teléfono", "mobile"))
        customer_tax_id = _pick(str_row, fields, ("customer_tax_id", "customer_vat", "nif", "cif", "vat", "vat_number", "tax_id"))
        customer_province = _pick(str_row, fields, ("customer_province", "province", "provincia", "state_province"))
        customer_country = _pick(str_row, fields, ("customer_country", "country", "pais", "país", "country_code"))
        customer_activity = _pick(str_row, fields, ("customer_activity", "activity", "actividad", "business_activity"))
        total = _pick_number(str_row, fields, (
            "order_total", "total_order", "grand_total", "total", "amount", "importe", "revenue", "sale_amount",
        ))
        date = _pick(str_row, fields, ("order_date", "created_at", "created", "date", "fecha"))
        status = _pick(str_row, fields, ("financial_status", "fulfillment_status", "status", "estado", "state")) or "—"
        sku = _pick(str_row, fields, ("product_sku", "sku", "item_code", "product_code"))
        product_name = _pick(str_row, fields, ("product_name", "productname", "producto", "item_name"))
        quantity = _pick_number(str_row, fields, ("quantity", "qty", "cantidad", "unidades", "units"))
        if not order_id and total is None and not customer and not customer_email and not customer_tax_id:
            continue
        row = {
            "id": order_id or f"S-{i + 1}",
            "customer": customer or customer_email or "Cliente sin nombre",
            "customerEmail": customer_email or "",
            "customerPhone": customer_phone or "",
            "customerTaxId": customer_tax_id or "",
            "customerProvince": customer_province or "",
            "customerCountry": customer_country or "",
            "customerActivity": customer_activity or "",
            "sku": sku or "",
            "productName": product_name or "",
            "quantity": quantity,
            "total": total,
            "date": date or "—",
            "status": status,
            "sourceFile": source_name,
            "source": "excel",
        }
        # B-02 (auditoría comercial): valida la fila ANTES de que entre en las
        # métricas. Una fila inválida no se descarta ni se deduplica en silencio:
        # se marca con _saleIssue + qualityStatus=needs_review y se conserva en
        # organizedSalesReview para Data Health. El resto del pipeline (revenue,
        # summary, detección) solo consume filas válidas.
        issue = _sale_row_issue(row)
        if not issue and duplicate_headers:
            # VANOVA 3.0 (red team): cabecera con columnas repetidas → el CSV es
            # ambiguo (csv.DictReader descarta silenciosamente la primera de las
            # columnas duplicadas). No inventamos cuál es la buena: a revisión.
            issue = "columnas duplicadas en la cabecera: " + ", ".join(duplicate_headers)
        if issue:
            row["_saleIssue"] = issue
            row["qualityStatus"] = "needs_review"
            row["qualityReason"] = issue
        rows.append(row)
    return rows


def _sale_row_issue(row: dict[str, Any]) -> str | None:
    """Razón por la que una fila de venta NO es financieramente válida, o None.
    Mismo criterio canónico que business_model.sale_validation_issue + chequeo de
    cantidad: fecha parseable, importe numérico >= 0, cantidad numérica."""
    try:
        from . import business_model

        issue = business_model.sale_validation_issue(row)
        if issue:
            return issue
    except Exception:  # noqa: BLE001 — nunca bloquea el import por la validación
        pass
    qty = row.get("quantity")
    if qty is not None:
        try:
            float(str(qty).replace(",", "."))
        except (TypeError, ValueError):
            return "cantidad no numérica"
    return None


def _extract_customers(entry: dict[str, Any], truncated: dict[str, int] | None = None) -> list[dict[str, Any]]:
    path = entry.get("path") or ""
    ext = (entry.get("ext") or "").lower().lstrip(".")
    source_name = entry.get("name") or Path(path).name or "import"
    p = Path(path)
    if ext in {"xlsx", "xls", "ods"}:
        if not p.exists():
            return []
        return _parse_customer_dict_rows(_read_spreadsheet_dict_rows(p, ext), source_name, truncated)
    if ext == "json":
        return _parse_customer_dict_rows(_read_json_dict_rows(p, entry.get("contentPreview")), source_name, truncated)
    if ext not in {"csv", "tsv", "txt"}:
        return []
    delimiter = "\t" if ext == "tsv" else ","
    # H24 (FASE 16): igual que en productos/ventas — si el archivo existe en
    # disco se lee SIEMPRE completo (el contentPreview de la UI está truncado).
    if not p.exists():
        preview = entry.get("contentPreview") or ""
        return _parse_customer_rows(preview, _detect_delimiter(preview, delimiter), source_name, truncated) if preview else []
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        log.debug("Customer read failed for %s: %s", path, exc)
        return []
    return _parse_customer_rows(text, _detect_delimiter(text, delimiter), source_name, truncated) if text else []


def _parse_customer_rows(text: str, delimiter: str, source_name: str, truncated: dict[str, int] | None = None) -> list[dict[str, Any]]:
    try:
        import io

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            return []
        dict_rows: list[dict[str, Any]] = []
        for i, row in enumerate(reader):
            if i < MAX_IMPORT_ROWS:
                dict_rows.append(dict(row))
            elif truncated is not None:
                truncated[source_name] = truncated.get(source_name, 0) + 1
        return _parse_customer_dict_rows(dict_rows, source_name, truncated)
    except csv.Error as exc:
        log.debug("Customer parse failed for %s: %s", source_name, exc)
        return []


def _parse_customer_dict_rows(dict_rows: list[dict[str, Any]], source_name: str, truncated: dict[str, int] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not dict_rows:
        return rows
    fields = {_norm(str(h)): str(h) for h in dict_rows[0].keys() if h}
    if truncated is not None and len(dict_rows) > MAX_IMPORT_ROWS:
        truncated[source_name] = truncated.get(source_name, 0) + (len(dict_rows) - MAX_IMPORT_ROWS)
    for i, row in enumerate(dict_rows[:MAX_IMPORT_ROWS]):
        str_row = {str(k): str(v).strip() if v is not None else "" for k, v in row.items()}
        name = _pick(str_row, fields, (
            "customer_name", "customername", "client_name", "clientname", "nombre_cliente",
            "cliente", "customer", "buyer_name", "buyername", "comprador", "full_name", "fullname", "name",
        ))
        email = _pick(str_row, fields, ("email", "correo", "correo_electronico", "customer_email", "client_email"))
        tax_id = _pick(str_row, fields, ("nif", "cif", "vat", "vat_number", "tax_id", "customer_tax_id"))
        if not name:
            name = email or "Cliente sin nombre"
        # Province/country/activity/tax ID are attributes, never the identity fallback.
        if not name:
            continue
        rows.append({
            "id": _pick(str_row, fields, ("customer_id", "client_id", "id_cliente", "id")) or email or tax_id or name,
            "name": name,
            "email": email,
            "phone": _pick(str_row, fields, ("phone", "telefono", "teléfono", "mobile", "customer_phone")),
            "taxId": tax_id,
            "address": _pick(str_row, fields, ("address", "direccion", "dirección", "customer_address")),
            "province": _pick(str_row, fields, ("province", "provincia", "customer_province", "state_province")),
            "country": _pick(str_row, fields, ("country", "pais", "país", "country_code", "customer_country")),
            "activity": _pick(str_row, fields, ("activity", "actividad", "business_activity", "customer_activity")),
            "orders": _pick_number(str_row, fields, ("orders", "pedidos", "order_count")) or 0,
            "total": _pick_number(str_row, fields, ("total_spent", "spend", "gasto_total", "lifetime_value", "total")) or 0,
            "sourceFile": source_name,
            "sourceRow": i + 2,
            "source": "excel",
        })
    return rows


def _read_json_dict_rows(path: Path, preview: str | None = None, *, max_rows: int = MAX_IMPORT_ROWS) -> list[dict[str, Any]]:
    """Read structured JSON rows; internal app config is filtered before this."""
    raw = preview or ""
    if not raw and path.exists():
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [row for row in payload[:max_rows] if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "data", "items", "products", "sales", "orders", "customers", "clients"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value[:max_rows] if isinstance(row, dict)]
        if all(not isinstance(value, (dict, list)) for value in payload.values()):
            return [payload]
    return []


def _read_spreadsheet_dict_rows(path: Path, ext: str, *, max_rows: int = MAX_IMPORT_ROWS + 1) -> list[dict[str, Any]]:
    """Read Excel/ODS rows as dicts using stdlib (xlsx) or openpyxl when available."""
    matrix: list[list[str]] = []
    if ext == "xlsx":
        matrix = _read_xlsx_matrix(path, max_rows=max_rows)
    elif ext in {"xls", "ods"}:
        try:
            import openpyxl  # type: ignore

            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            ws = wb.active
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= max_rows:
                    break
                matrix.append(["" if c is None else str(c).strip() for c in row])
            wb.close()
        except Exception as exc:
            log.debug("Spreadsheet read failed for %s: %s", path, exc)
            return []
    if not matrix:
        return []
    return _matrix_to_dict_rows(matrix, max_rows=max_rows - 1)


def _read_xlsx_matrix(path: Path, *, max_rows: int = MAX_IMPORT_ROWS + 1) -> list[list[str]]:
    import xml.etree.ElementTree as ET
    import zipfile

    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with zipfile.ZipFile(path, "r") as zf:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in root.findall(".//m:si", ns):
                    texts = [t.text or "" for t in si.findall(".//m:t", ns)]
                    shared.append("".join(texts))
            sheet_name = next(
                (n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")),
                None,
            )
            if not sheet_name:
                return []
            sheet = ET.fromstring(zf.read(sheet_name))
            rows_map: dict[int, dict[int, str]] = {}
            max_col = 0
            for row_el in sheet.findall(".//m:sheetData/m:row", ns):
                r_idx = int(row_el.get("r", "0") or "0") - 1
                if r_idx < 0:
                    continue
                row_cells: dict[int, str] = {}
                for cell in row_el.findall("m:c", ns):
                    ref = cell.get("r") or ""
                    c_idx = _xlsx_col_index(ref) if ref else len(row_cells)
                    row_cells[c_idx] = _xlsx_cell_value(cell, ns, shared)
                    max_col = max(max_col, c_idx)
                if row_cells:
                    rows_map[r_idx] = row_cells
            if not rows_map:
                return []
            return [
                [rows_map[r_idx].get(c, "") for c in range(max_col + 1)]
                for r_idx in sorted(rows_map.keys())[:max_rows]
            ]
    except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        log.debug("XLSX read failed for %s: %s", path, exc)
        return []


def _xlsx_col_index(cell_ref: str) -> int:
    col = "".join(ch for ch in cell_ref if ch.isalpha())
    idx = 0
    for ch in col:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return max(idx - 1, 0)


def _xlsx_cell_value(cell: Any, ns: dict[str, str], shared: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        is_el = cell.find("m:is", ns)
        if is_el is not None:
            texts = [t.text or "" for t in is_el.findall(".//m:t", ns)]
            return "".join(texts).strip()
        return ""
    v_el = cell.find("m:v", ns)
    if v_el is None or v_el.text is None:
        return ""
    if cell_type == "s":
        try:
            return str(shared[int(v_el.text)]).strip()
        except (IndexError, ValueError, TypeError):
            return str(v_el.text).strip()
    return str(v_el.text).strip()


def _matrix_to_dict_rows(matrix: list[list[str]], *, max_rows: int = MAX_IMPORT_ROWS) -> list[dict[str, Any]]:
    header_idx = 0
    best_score = -1
    hints = tuple(_norm(h) for h in PRODUCT_HEADER_HINTS + SALES_HEADER_HINTS + CUSTOMER_HEADER_HINTS)
    for i, row in enumerate(matrix[:25]):
        score = sum(
            1 for c in row
            if c and any(h in _norm(str(c)) for h in hints)
        )
        if score > best_score:
            best_score = score
            header_idx = i
    headers = [str(h or "").strip() for h in matrix[header_idx]]
    if not any(headers):
        return []
    out: list[dict[str, Any]] = []
    for row in matrix[header_idx + 1:header_idx + 1 + max_rows]:
        if not any(str(c or "").strip() for c in row):
            continue
        item: dict[str, Any] = {}
        for i, header in enumerate(headers):
            if header:
                item[header] = str(row[i] if i < len(row) else "").strip()
        out.append(item)
    return out


def _pick(row: dict[str, str], fields: dict[str, str], keys: tuple[str, ...]) -> str:
    """Pick a column by explicit aliases; never guess from unrelated columns.

    Exact normalized aliases win. A narrow suffix match supports common export
    headers such as ``order_id`` without allowing ``name`` to match ``filename``
    or ``customer`` to match ``customer_email``.
    """
    aliases = [_norm(key) for key in keys if _norm(key)]
    for alias in aliases:
        header = fields.get(alias)
        if header and str(row.get(header) or "").strip():
            return str(row[header]).strip()

    safe_suffixes = {"id", "name", "number", "no", "num", "date", "price", "amount", "value", "qty", "quantity", "code", "sku"}
    for alias in aliases:
        if len(alias) < 4:
            continue
        for norm_h, orig_h in fields.items():
            if not str(row.get(orig_h) or "").strip() or not norm_h.startswith(alias):
                continue
            suffix = norm_h[len(alias):]
            if suffix in safe_suffixes:
                return str(row[orig_h]).strip()
    return ""


def _parse_optional_float(value: Any) -> float | None:
    """VANOVA 3.0 (auditoría): mismo criterio anti-invención que _pick_number —
    un valor ambiguo ("10.5.5") devuelve None (UNKNOWN), nunca un número
    adivinado; el formato europeo de miles ("1.234,56") sí se soporta."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        if result != result or result in (float("inf"), float("-inf")):
            return None
        return result
    normalized = str(value).replace(",", ".")
    if normalized.count(".") > 1:
        parts = normalized.split(".")
        last = parts[-1]
        int_parts = parts[:-1]
        middle = int_parts[1:]
        if not (1 <= len(last) <= 2
                and int_parts and 1 <= len(int_parts[0]) <= 3
                and all(p and len(p) == 3 and p.isdigit() for p in middle)
                and all(p.isdigit() for p in int_parts)):
            return None
        normalized = int_parts[0] + "".join(middle) + "." + last
    cleaned = re.sub(r"[^\d.\-]", "", normalized)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _pick_number(row: dict[str, str], fields: dict[str, str], keys: tuple[str, ...]) -> float | None:
    raw = _pick(row, fields, keys)
    if not raw:
        return None
    # VANOVA 3.0 (auditoría): los no-numéricos NUNCA se convierten en silencio
    # a un número inventado. Se soporta el formato europeo de miles 1.234,56
    # (-> 1234.56) y 1,234.56, pero una cadena con puntos ambiguos ("10.5.5")
    # devuelve None (UNKNOWN) en vez de adivinar 105.5.
    normalized = raw.replace(",", ".")
    if normalized.count(".") > 1:
        parts = normalized.split(".")
        last = parts[-1]
        int_parts = parts[:-1]
        # Formato europeo válido: decimales de 1-2 dígitos; el primer grupo
        # entero puede tener 1-3 dígitos y los siguientes exactamente 3
        # (1.234,56 -> 1234.56). Cualquier otra forma (10.5.5) es corrupta:
        # se declara UNKNOWN.
        middle = int_parts[1:]
        if not (1 <= len(last) <= 2
                and int_parts and 1 <= len(int_parts[0]) <= 3
                and all(p and len(p) == 3 and p.isdigit() for p in middle)
                and all(p.isdigit() for p in int_parts)):
            return None
        normalized = int_parts[0] + "".join(middle) + "." + last
    cleaned = re.sub(r"[^\d.\-]", "", normalized)
    try:
        return float(cleaned)
    except ValueError:
        return None


from functools import lru_cache


@lru_cache(maxsize=2048)
def _norm(value: str) -> str:
    """VANOVA 3.0 (performance): cache puro — la misma cabecera/alias se
    normaliza miles de veces por import (un CSV de 100k filas repite los
    mismos nombres de columna en cada fila).

    Accent-insensitive enough for Spanish/Portuguese exports while retaining
    deterministic aliases (``país`` and ``pais`` both normalize to ``pas``;
    both are listed where needed)."""
    value = (value or "").lower()
    replacements = str.maketrans("áéíóúüñ", "aeiouun")
    return re.sub(r"[^a-z0-9]", "", value.translate(replacements))


def _is_legacy_entity(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    origin = item.get("sourceFile") or item.get("path") or item.get("name") or ""
    return bool(file_relevance.legacy_app_artifact({
        "name": item.get("name") or item.get("sourceFile") or "",
        "path": origin,
        "source": item.get("source") or "",
    }))


def _is_preservable_product(item: Any) -> bool:
    """Return whether an existing product is safe to retain across rescans."""
    if not _is_product_entity(item) or _is_legacy_entity(item):
        return False
    return bool(str(item.get("sku") or item.get("name") or "").strip())


def _is_preservable_sale(item: Any) -> bool:
    """Return whether an existing order/ sale has enough identity to retain."""
    if not isinstance(item, dict) or _is_legacy_entity(item):
        return False
    if str(item.get("source") or "").lower() in {"error", "system"}:
        return False
    return bool(
        str(item.get("id") or item.get("orderId") or "").strip()
        or str(item.get("customer") or "").strip()
        or str(item.get("sku") or item.get("productName") or "").strip()
    )


def _is_preservable_customer(item: Any) -> bool:
    """Return whether an existing customer has a real identity field."""
    if not isinstance(item, dict) or _is_legacy_entity(item):
        return False
    if str(item.get("source") or "").lower() in {"error", "system"}:
        return False
    return bool(
        str(item.get("name") or "").strip()
        or str(item.get("email") or "").strip()
        or str(item.get("taxId") or "").strip()
        or str(item.get("id") or "").strip()
    )


_normalization_in_progress = False
# Cache de la verificación de normalización por mtime del config: con 100k
# filas, escanear organizedSales en CADA request era ~5s en /api/sales.
_norm_check_cache: tuple[str, float, bool] | None = None


def _needs_normalization_repair(data: dict[str, Any]) -> bool:
    """Detect stale rows even when an earlier build marked migration complete."""
    files = data.get("scanFiles") or []
    if any(isinstance(f, dict) and file_relevance.legacy_app_artifact(f) for f in files):
        return True
    known_sources = {
        str(value).replace("\\", "/").lower()
        for f in files if isinstance(f, dict)
        for value in (f.get("name"), f.get("path")) if value
    }
    for key in ("organizedProducts", "organizedSales", "organizedCustomers"):
        for row in data.get(key) or []:
            if not isinstance(row, dict) or _is_legacy_entity(row):
                return True
            if row.get("source") in ("excel", "file", "import"):
                origin = str(row.get("sourceFile") or row.get("path") or "").replace("\\", "/").lower()
                if not origin or (known_sources and not any(origin == source or origin.endswith("/" + source.rsplit("/", 1)[-1]) for source in known_sources)):
                    return True
    return False


def _ensure_normalized_data() -> None:
    """One-time migration: rebuild local rows with the strict schema mapper."""
    global _normalization_in_progress, _norm_check_cache
    if _normalization_in_progress:
        return
    # Si el config no ha cambiado desde la última verificación, no re-escanear
    # las 100k filas (era el cuello de botella de /api/sales).
    try:
        from . import config_store as _cs

        stat = _cs.CONFIG_FILE.stat()
        key = (str(_cs.CONFIG_FILE), stat.st_mtime_ns, stat.st_size)
        if _norm_check_cache is not None and _norm_check_cache[0] == key[0] and _norm_check_cache[1] == key[1] and _norm_check_cache[2] is False:
            return
    except OSError:
        key = None
    data = config_store.load()
    try:
        if int(data.get("dataNormalizationVersion") or 0) >= NORMALIZATION_VERSION and not _needs_normalization_repair(data):
            if key is not None:
                _norm_check_cache = (key[0], key[1], False)
            return
    except (TypeError, ValueError):
        pass
    if key is not None:
        _norm_check_cache = (key[0], key[1], True)
    _normalization_in_progress = True
    try:
        repair = _needs_normalization_repair(data)
        files = data.get("scanFiles") or []
        if isinstance(files, list) and files and not repair:
            organize_files(files, trigger_hermes=False)
        elif repair:
            # Reparación real pendiente: filtra SOLO entidades legacy probadas.
            config_store.save({
                "organizedProducts": [p for p in (data.get("organizedProducts") or []) if not _is_legacy_entity(p)],
                "organizedSales": [s for s in (data.get("organizedSales") or []) if not _is_legacy_entity(s)],
                "organizedCustomers": [c for c in (data.get("organizedCustomers") or []) if not _is_legacy_entity(c)],
                "dataNormalizationVersion": NORMALIZATION_VERSION,
            })
        else:
            # H20: sin archivos y sin reparación pendiente, NUNCA se reescriben
            # organized* completos derivados del load (un load parcial o
            # parcheado no debe persistir datos). Solo se avanza la versión.
            config_store.save({"dataNormalizationVersion": NORMALIZATION_VERSION})
    except Exception as exc:
        log.warning("Data normalization migration failed: %s", exc)
    finally:
        _normalization_in_progress = False


def _customer_identity(row: dict[str, Any]) -> str:
    # Prefer stable business identities shared by exports and orders. Numeric
    # source IDs are last because Shopify/ERP/customer exports often use
    # different ID namespaces for the same email/name.
    for key in ("taxId", "email", "name", "id"):
        value = str(row.get(key) or "").strip().lower()
        if value:
            return _norm(value)
    return ""


def _merge_customer_row(by_key: dict[str, dict[str, Any]], row: dict[str, Any]) -> str:
    key = _customer_identity(row)
    if not key:
        key = "customer-" + str(len(by_key) + 1)
    current = by_key.get(key)
    if current is None:
        current = {
            "id": row.get("id") or key,
            "name": row.get("name") or "",
            "email": row.get("email") or "",
            "phone": row.get("phone") or "",
            "taxId": row.get("taxId") or "",
            "address": row.get("address") or "",
            "province": row.get("province") or "",
            "country": row.get("country") or "",
            "activity": row.get("activity") or "",
            "orders": int(row.get("orders") or 0),
            "total": round(float(row.get("total") or 0), 2),
            "sourceFile": row.get("sourceFile") or "",
            "source": row.get("source") or "excel",
        }
        by_key[key] = current
    else:
        # FASE B (B5): dos registros comparten identidad (email/NIF/nombre) —
        # se conserva el merge pero se marca NEEDS_REVIEW (duplicate_identity)
        # para que Data Health lo muestre en vez de fundirlo en silencio.
        _mark_quality(current, "duplicate_identity", key)
        for field in ("name", "email", "phone", "taxId", "address", "province", "country", "activity", "sourceFile"):
            if not current.get(field) and row.get(field):
                current[field] = row[field]
        # FASE 13 (P11): una fuente CONECTORA (Shopify, FS, WooCommerce…) gana
        # sobre una fuente de archivo al deduplicar clientes — sin hardcodear.
        if _is_connector_source(row) and not _is_connector_source(current):
            current["source"] = row.get("source")
    return key


def _customer_record_key(item: dict[str, Any]) -> str:
    return _customer_identity(item)


def _customer_stable_key(item: dict[str, Any]) -> str:
    source_file = str(item.get("sourceFile") or "").strip().lower()
    source_row = str(item.get("sourceRow") or "").strip()
    if source_file and source_row:
        return f"file:{source_file}:{source_row}"
    identifier = str(item.get("id") or "").strip().lower()
    return f"id:{identifier}" if identifier else ""


def _customer_fingerprint(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("id"), item.get("name"), item.get("email"), item.get("taxId"),
        item.get("phone"), item.get("sourceFile"), item.get("sourceRow"),
    )


def _merge_customer_records(override: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if value not in (None, ""):
            merged[key] = value
    # Governance is local ownership and must survive a re-import.
    for field in ("qualityStatus", "qualityReason", "duplicateKey", "legacyFromVersion", "lastValidatedAt", "dataProvenance"):
        if base.get(field) and not merged.get(field):
            merged[field] = base[field]
    return merged


def _dedupe_customers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve conflicting customer rows instead of merging them away.

    Rows with the same stable source id/row are the same record on a rescan and
    are merged. Different records sharing an email/NIF/name are all retained
    and marked ``duplicate_identity`` so Data Health can explain the conflict.
    """
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or _is_legacy_entity(item):
            continue
        key = _customer_record_key(item)
        matches = [i for i, current in enumerate(out) if key and _customer_record_key(current) == key]
        same_index = None
        stable = _customer_stable_key(item)
        for i in matches:
            current = out[i]
            current_stable = _customer_stable_key(current)
            if stable and current_stable and stable == current_stable:
                same_index = i
                break
            if _customer_fingerprint(current) == _customer_fingerprint(item):
                same_index = i
                break
            # A connected source is authoritative for the same customer key,
            # but it must not collapse two conflicting file records.
            if _is_connector_source(current) or _is_connector_source(item):
                if len(matches) == 1:
                    same_index = i
                    break
        if same_index is not None:
            out[same_index] = _merge_customer_records(item, out[same_index])
            continue
        if matches:
            for i in matches:
                _mark_quality(out[i], "duplicate_identity", key)
            _mark_quality(item, "duplicate_identity", key)
        out.append(item)
    return out


def _merge_customers(file_items: list[dict[str, Any]], integration_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _dedupe_customers(file_items + integration_items)


def _dedupe_products(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve duplicate product rows and mark them NEEDS_REVIEW.

    The old implementation kept both rows here but ``_merge_products`` later
    collapsed them by SKU. This helper now guarantees the quality marker is on
    every conflicting raw row; the field-aware merge below also keeps both.
    """
    seen: dict[str, list[dict[str, Any]]] = {}
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("sku") or "").strip().lower()
        key = sku or ("name:" + str(item.get("name") or "").strip().lower())
        if not key.strip("name:"):
            continue
        prior = seen.setdefault(key, [])
        if prior:
            _mark_quality(item, "duplicate_sku" if sku else "duplicate_identity", key)
            for existing in prior:
                _mark_quality(existing, "duplicate_sku" if sku else "duplicate_identity", key)
        prior.append(item)
        out.append(item)
    return out


def _mark_quality(item: dict[str, Any], reason: str, duplicate_key: str = "") -> None:
    """Marca una entidad como NEEDS_REVIEW sin destruir sus datos."""
    item["qualityStatus"] = "needs_review"
    item["qualityReason"] = reason
    if duplicate_key:
        item["duplicateKey"] = duplicate_key


def _dedupe_sales(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = f"{item.get('id','')}|{item.get('date','')}|{item.get('total','')}".lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _dedupe_review_sales(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplica filas de venta marcadas para revisión conservando la evidencia.

    Misma clave que _dedupe_sales: la misma fila reimportada no debe duplicarse
    en organizedSalesReview. El primer registro (con _saleIssue/motivo) gana y
    la fuente/evidencia se conserva."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = f"{item.get('id','')}|{item.get('date','')}|{item.get('total','')}".lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def sync_dashboard_overview(
    products: list[dict[str, Any]] | None = None,
    sales: list[dict[str, Any]] | None = None,
) -> None:
    """Push organized revenue/orders into Command Center snapshot."""
    data = config_store.load()
    if products is None:
        products = data.get("organizedProducts") or []
    if sales is None:
        sales = data.get("organizedSales") or []
    if not isinstance(products, list):
        products = []
    if not isinstance(sales, list):
        sales = []

    summary = _sales_summary(sales)
    snapshot = data.get("dashboardSnapshot") or {}
    if not isinstance(snapshot, dict):
        snapshot = {}

    overview = dict(snapshot.get("overview") or {})
    # Replace stale snapshot values, including an explicit empty state. Old
    # MAIOS dashboard snapshots must not survive a clean re-normalization.
    overview["orders"] = summary.get("orders", 0)
    overview["revenue"] = summary.get("revenue")
    overview["grossMargin"] = summary.get("grossMarginPct")
    customer_rows = data.get("organizedCustomers") or []
    customers = {
        str(c.get("email") or c.get("taxId") or c.get("name") or "").strip().lower()
        for c in customer_rows
        if isinstance(c, dict) and not _is_legacy_entity(c)
        and (c.get("email") or c.get("taxId") or c.get("name"))
    }
    if not customers:
        customers = {
            str(s.get("customer")).strip().lower()
            for s in sales
            if isinstance(s, dict) and s.get("customer") and s.get("customer") != "—"
        }
    overview["customers"] = len(customers)
    overview["productsOrganized"] = len(products)
    overview["filesScanned"] = len(data.get("scanFiles") or [])

    snapshot["overview"] = overview
    snapshot["fetchedAt"] = _now()
    if summary.get("revenue") is not None or summary.get("orders"):
        snapshot["dataMode"] = "real"

    config_store.save({"dashboardSnapshot": snapshot})
    log.info(
        "Dashboard metrics synced: %d orders, revenue=%s, %d products",
        summary.get("orders") or 0,
        summary.get("revenue"),
        len(products),
    )
    # FASE 3: non-blocking integrity check — log any drift between the snapshot
    # and the raw model so a future bug surfaces instead of silently showing
    # wrong numbers as if they were current.
    try:
        from . import business_model

        report = business_model.integrity_report()
        for issue in report.get("issues") or []:
            log.warning("Integridad de datos [%s]: %s", issue.get("dataset"), issue.get("detail"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Integrity check skipped: %s", exc)


def _is_connector_source(item: dict[str, Any]) -> bool:
    """FASE 13 (P11): ¿la fila viene de un conector sincronizado (no de
    archivos)? Consulta el registro de conectores: cualquier fuente registrada
    e implementada cuenta, no solo Shopify."""
    source = str(item.get("source") or "").strip()
    if not source or source == "local":
        return False
    try:
        from . import connector_base

        conn = connector_base.source(source)
        return bool(conn and conn.implemented)
    except Exception:  # noqa: BLE001 — nunca rompe el organize
        return source != "local"


# FASE 14 (auditoría final pre-release): campos de ENRIQUECIMIENTO LOCAL y
# GOBERNANZA propiedad de VANOVA que un merge (conector O re-extracción de
# archivos) NUNCA puede destruir al reemplazar una entidad con la misma clave.
# El override gana en los campos de SU fuente; estos campos sobreviven siempre
# salvo que el override los traiga explícitamente.
_PRODUCT_ENRICHMENT_FIELDS = (
    "cost", "costSource", "costStatus", "sourceReference", "costUpdatedAt",
    "qualityStatus", "legacyFromVersion", "lastValidatedAt", "dataProvenance",
    "identityMappingId", "canonicalProductId", "category", "classification",
    "notes", "tags_local",
)
_ORDER_ENRICHMENT_FIELDS = (
    "qualityStatus", "legacyFromVersion", "lastValidatedAt", "dataProvenance",
    "identityMappingId", "notes",
)


def _merge_with_enrichment(
    override: dict[str, Any],
    base: dict[str, Any],
    enrichment_fields: tuple[str, ...],
) -> dict[str, Any]:
    """Merge field-aware: ``override`` gana en los campos que trae; los campos de
    enriquecimiento local de ``base`` se conservan cuando el override no los
    define (o los trae vacíos). Nunca se reemplaza una entidad completa por un
    payload externo que no conoce el enriquecimiento local."""
    merged = dict(override)
    for field in enrichment_fields:
        base_value = base.get(field)
        if base_value is None or base_value == "":
            continue
        override_value = merged.get(field)
        if override_value is None or override_value == "":
            merged[field] = base_value
    return merged


def _product_record_key(item: dict[str, Any]) -> str:
    sku = str(item.get("sku") or "").strip().lower()
    return "sku:" + sku if sku else "name:" + str(item.get("name") or "").strip().lower()


def _product_stable_key(item: dict[str, Any]) -> str:
    source_file = str(item.get("sourceFile") or "").strip().lower()
    source_row = str(item.get("sourceRow") or "").strip()
    if source_file and source_row:
        return f"file:{source_file}:{source_row}"
    identifier = str(item.get("id") or item.get("externalId") or "").strip().lower()
    return f"id:{identifier}" if identifier else ""


def _product_fingerprint(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("sku"), item.get("name"), item.get("netPrice"), item.get("rrp"),
        item.get("stock"), item.get("sourceFile"), item.get("sourceRow"),
    )


def _merge_products(file_items: list[dict[str, Any]], integration_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Field-aware merge that does not erase conflicting raw product rows.

    Same source row (or same connector identity) is a refresh and is merged.
    Two different file rows with one SKU are evidence of a duplicate and both
    remain in the canonical store with ``qualityStatus=needs_review``.
    """
    out: list[dict[str, Any]] = []
    for item in [*file_items, *integration_items]:
        if not isinstance(item, dict):
            continue
        key = _product_record_key(item)
        if not key.strip("sku:name"):
            continue
        matches = [i for i, current in enumerate(out) if _product_record_key(current) == key]
        same_index = None
        stable = _product_stable_key(item)
        for i in matches:
            current = out[i]
            current_stable = _product_stable_key(current)
            if stable and current_stable and stable == current_stable:
                same_index = i
                break
            if _product_fingerprint(current) == _product_fingerprint(item):
                same_index = i
                break
            # A connector and a file can describe the same canonical product;
            # merge that pair. Conflicting file rows are never collapsed.
            if _is_connector_source(current) or _is_connector_source(item):
                if len(matches) == 1:
                    same_index = i
                    break
        if same_index is not None:
            out[same_index] = _merge_with_enrichment(item, out[same_index], _PRODUCT_ENRICHMENT_FIELDS)
            continue
        if matches:
            sku = str(item.get("sku") or "").strip().lower()
            reason = "duplicate_sku" if sku else "duplicate_identity"
            for i in matches:
                _mark_quality(out[i], reason, key)
            _mark_quality(item, reason, key)
        out.append(item)
    return out


def _merge_sales(file_items: list[dict[str, Any]], integration_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for item in file_items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or item.get("orderId") or "").strip()
        if key:
            base = by_key.get(key)
            by_key[key] = _merge_with_enrichment(item, base, _ORDER_ENRICHMENT_FIELDS) if isinstance(base, dict) else item
    for item in integration_items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or item.get("orderId") or "").strip()
        if key:
            base = by_key.get(key)
            by_key[key] = _merge_with_enrichment(item, base, _ORDER_ENRICHMENT_FIELDS) if isinstance(base, dict) else item
    return list(by_key.values())


def _sales_summary(sales: list[dict[str, Any]]) -> dict[str, Any]:
    # FASE 3: canonical summary — same numbers the dashboard and Hermes use.
    from . import business_model

    products = config_store.load().get("organizedProducts") or []
    valid_products = [
        p for p in products
        if isinstance(p, dict) and not _is_legacy_entity(p)
    ]
    return business_model.sales_summary(sales, products=valid_products)


def get_sales_with_data(data: dict[str, Any]) -> dict[str, Any]:
    """Variante de get_sales que reutiliza el config ya cargado por el caller
    (evita el 3er load + la reparación por request)."""
    sales = data.get("organizedSales") or []
    if not isinstance(sales, list):
        sales = []
    sales = [s for s in sales if isinstance(s, dict) and not _is_legacy_entity(s)]
    summary = business_model_sales_summary(sales, data)
    limited = sales[:_SALES_ROWS_LIMIT]
    return {"sales": limited, "count": len(sales), "totalCount": len(sales), "summary": summary, "source": "local"}


def business_model_sales_summary(sales: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any]:
    """sales_summary del modelo canónico usando productos ya cargados."""
    from . import business_model

    products = data.get("organizedProducts") or []
    valid_products = [
        p for p in products
        if isinstance(p, dict) and not _is_legacy_entity(p)
    ]
    return business_model.sales_summary(sales, products=valid_products)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
