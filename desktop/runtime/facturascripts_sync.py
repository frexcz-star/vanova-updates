"""FacturaScripts deep integration — FASE 4.

Pipeline: extracción → validación → normalización → deduplicación/idempotencia
→ modelo financiero VANOVA → tools de Hermes.

Robustez (requisito FASE 4):
  * retries con backoff y timeout por petición;
  * manejo de rate-limit (HTTP 429) y errores 5xx con reintento;
  * extracción defensiva del payload (lista, ``data``, ``items``, ``results``);
  * un error de FacturaScripts NUNCA se convierte en una entidad financiera
    (los payloads de error se rechazan en la frontera del modelo);
  * protección contra datos parciales: si un recurso falla, se conservan los
    datos ya sincronizados de ese recurso (no se borran, no se contaminan);
  * estado de sincronización persistente (última sync, counts, errores por
    recurso) accesible por API y por Hermes.

Contrato real de la API (verificado contra la documentación oficial):
  * URL base de la API:  {instalación}/api/3
  * Autenticación:       header ``Token: <api_key>`` (no X-API-KEY)
  * Recursos:            clientes, proveedores, facturascli, facturasprov,
                         cobros, pagos, articulos, ...
  * Paginación:          ?limit=N&offset=N
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from . import business_model, config_store, integrations_store
from .logger import get_logger

log = get_logger("maios.facturascript", "facturascript-sync")

FS_API_BASE = "/api/3"
FS_TIMEOUT = 30.0


def normalize_fs_base_url(url: str) -> str:
    """Normalize the FacturaScripts installation URL to its bare origin+path.

    Users legitimately paste either ``https://host`` (the form hint) or
    ``https://host/api/3`` (the API URL from the official docs). Both must
    work: we strip any trailing ``/api/3`` or ``/api`` segment so the rest of
    the pipeline can append ``/api/3`` exactly once.
    """
    base = str(url or "").strip().rstrip("/")
    if not base:
        return ""
    if not base.lower().startswith(("http://", "https://")):
        base = "https://" + base
    lowered = base.lower()
    for suffix in ("/api/3", "/api/v3", "/api"):
        if lowered.endswith(suffix):
            base = base[: -len(suffix)].rstrip("/")
            break
    return base


FS_PROBE_PATHS = ("/api/3", "/api/3/")
FS_RETRIES = 3
FS_BACKOFF = (1.0, 2.0, 4.0)
FS_PAGE_SIZE = 200
FS_INTERVAL_SECONDS = 900  # background refresh every 15 min

# Resource -> how to interpret its rows
_RESOURCES: dict[str, dict[str, str]] = {
    "clientes": {"kind": "customer"},
    "proveedores": {"kind": "supplier"},
    "facturascli": {"kind": "invoice", "invoiceType": "issued"},
    "facturasprov": {"kind": "invoice", "invoiceType": "received"},
    "lineascli": {"kind": "line", "invoiceType": "issued"},
    "lineasprov": {"kind": "line", "invoiceType": "received"},
    "cobros": {"kind": "cash", "cashType": "collection"},
    "pagos": {"kind": "cash", "cashType": "payment"},
}

_sync_lock = threading.Lock()
_sync_running = False


# ---------------------------------------------------------------------------
# Estado de sincronización
# ---------------------------------------------------------------------------


def sync_status() -> dict[str, Any]:
    data = config_store.load()
    state = data.get("facturascriptSync")
    if not isinstance(state, dict):
        state = {}
    configured = bool(integrations_store.get_config("facturascript").get("base_url"))
    defaults = {
        "configured": configured,
        "ok": False,
        "status": "not_configured",
        "lastSync": None,
        "counts": {},
        "resourceErrors": {},
        "error": None,
        "userMessage": None,
        "dataMode": None,
        "intervalSeconds": FS_INTERVAL_SECONDS,
    }
    merged = {**defaults, **state}
    if configured and not merged.get("lastSync") and merged.get("status") == "not_configured":
        merged["status"] = "idle"
    return merged


def _save_state(**updates: Any) -> dict[str, Any]:
    current = sync_status()
    current.update(updates)
    config_store.save({"facturascriptSync": current})
    return current


# ---------------------------------------------------------------------------
# Extracción (HTTP con retries / timeouts / rate-limit)
# ---------------------------------------------------------------------------


def _num(value: Any) -> float | None:
    return business_model._as_float(value)  # noqa: SLF001 — shared canonical parser


def _request(client: httpx.Client, url: str, token: str, params: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    headers = {"Token": token, "Accept": "application/json"}
    last_error: str | None = None
    for attempt in range(FS_RETRIES):
        try:
            r = client.get(url, params=params, headers=headers)
        except httpx.ConnectError as exc:
            last_error = f"no se pudo conectar: {exc}"
        except httpx.TimeoutException:
            last_error = "timeout"
        except Exception as exc:  # noqa: BLE001
            last_error = f"error HTTP: {exc}"
        else:
            if r.status_code == 200:
                try:
                    return r.json(), None
                except ValueError:
                    return None, "respuesta no JSON"
            if r.status_code in (429,) or r.status_code >= 500:
                last_error = f"HTTP {r.status_code} (reintentable)"
            elif r.status_code in (401, 403):
                return None, f"autenticación rechazada (HTTP {r.status_code})"
            else:
                return None, f"HTTP {r.status_code}"
        if attempt < FS_RETRIES - 1:
            time.sleep(FS_BACKOFF[min(attempt, len(FS_BACKOFF) - 1)])
    return None, last_error or "sin respuesta"


def _extract_rows(payload: Any) -> list[dict[str, Any]] | None:
    """Defensive payload parsing. Returns None when the payload is an error or
    has no usable data — never a list of garbage."""
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if not isinstance(payload, dict):
        return None
    status = str(payload.get("status") or "").lower()
    if status in ("error", "fail", "failure"):
        return None
    for key in ("data", "items", "results", "records", "rows"):
        value = payload.get(key)
        if isinstance(value, list):
            return [p for p in value if isinstance(p, dict)]
    return None


def _fetch_rows(client: httpx.Client, base: str, token: str, resource: str) -> tuple[list[dict[str, Any]], str | None]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        url = f"{base}{FS_API_BASE}/{resource}"
        payload, error = _request(client, url, token, {"limit": FS_PAGE_SIZE, "offset": offset})
        if payload is None:
            return rows, error
        batch = _extract_rows(payload)
        if batch is None:
            return rows, "respuesta sin datos válidos"
        rows.extend(batch)
        if len(batch) < FS_PAGE_SIZE:
            break
        offset += FS_PAGE_SIZE
    return rows, None


# ---------------------------------------------------------------------------
# Normalización al modelo canónico (siempre pasa por business_model)
# ---------------------------------------------------------------------------


def _normalize_invoice(raw: dict[str, Any], invoice_type: str) -> dict[str, Any]:
    return {
        "id": str(raw.get("idfactura") or raw.get("id") or raw.get("codigo") or "").strip(),
        "code": str(raw.get("codigo") or raw.get("numero") or "").strip(),
        "type": invoice_type,
        "counterpartyId": str(raw.get("codcliente") or raw.get("codproveedor") or "").strip(),
        "counterparty": str(
            raw.get("nombrecliente") or raw.get("nombreproveedor") or raw.get("razonsocial") or ""
        ).strip(),
        "date": str(raw.get("fecha") or "").strip() or None,
        "net": _num(raw.get("neto")),
        "tax": _num(raw.get("totaliva")),
        "total": _num(raw.get("total")),
        "paid": bool(raw.get("pagada")) if raw.get("pagada") is not None else None,
        "dueDate": str(raw.get("vencimiento") or "").strip() or None,
        "currency": str(raw.get("coddivisa") or "EUR").strip() or "EUR",
    }


def _normalize_cash(raw: dict[str, Any], cash_type: str) -> dict[str, Any]:
    return {
        "id": str(raw.get("idcobro") or raw.get("idpago") or raw.get("id") or "").strip(),
        "type": cash_type,
        "date": str(raw.get("fecha") or "").strip() or None,
        "amount": _num(raw.get("importe") or raw.get("total")),
        "counterpartyId": str(raw.get("codcliente") or raw.get("codproveedor") or "").strip(),
        "counterparty": str(
            raw.get("nombrecliente") or raw.get("nombreproveedor") or raw.get("cliente") or raw.get("proveedor") or ""
        ).strip(),
        "invoiceCode": str(raw.get("codigo") or "").strip() or None,
    }


def _normalize_line(raw: dict[str, Any], invoice_type: str) -> dict[str, Any]:
    """Línea de factura → modelo canónico. id con prefijo de tipo para que las
    secuencias de lineascli y lineasprov no colisionen al fusionar."""
    return {
        "id": f"{invoice_type}:{str(raw.get('idlinea') or raw.get('id') or '').strip()}",
        "invoiceId": str(raw.get("idfactura") or "").strip(),
        "invoiceType": invoice_type,
        "sku": str(raw.get("referencia") or raw.get("codigo") or "").strip(),
        "description": str(raw.get("descripcion") or "").strip(),
        "quantity": _num(raw.get("cantidad")) or 0,
        "unitPrice": _num(raw.get("pvpunitario") or raw.get("precio")),
        "discountPct": _num(raw.get("dtopor")),
        "taxPct": _num(raw.get("iva")),
        "lineTotal": _num(raw.get("pvptotal") or raw.get("total") or raw.get("importe")),
    }


def _normalize_partner(raw: dict[str, Any], kind: str) -> dict[str, Any]:
    return {
        "name": str(raw.get("nombre") or raw.get("razonsocial") or "").strip(),
        "email": str(raw.get("email") or "").strip(),
        "taxId": str(raw.get("cifnif") or raw.get("nif") or "").strip(),
        "phone": str(raw.get("telefono1") or "").strip(),
        "city": str(raw.get("ciudad") or "").strip(),
        "province": str(raw.get("provincia") or "").strip(),
        "country": str(raw.get("pais") or "").strip(),
        "code": str(raw.get("codcliente") or raw.get("codproveedor") or raw.get("codigo") or "").strip(),
        "partnerType": kind,
    }


# ---------------------------------------------------------------------------
# Tesorería (cálculo etiquetado sobre datos reales)
# ---------------------------------------------------------------------------


def _due_within(due_date: str | None, days: int) -> bool:
    if not due_date:
        return False
    try:
        due = datetime.fromisoformat(str(due_date)[:10]).date()
    except (ValueError, TypeError):
        return False
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=days)
    return today <= due <= horizon


def treasury_summary() -> dict[str, Any]:
    """Tesorería con categorías SIEMPRE separadas (regla P3):

      * REAL        → cobros y pagos procedentes de FacturaScripts.
      * CALCULADO   → derivados sobre datos reales (pendientes, vencimientos,
                      movimiento neto de caja).
      * NO DISPONIBLE → saldo bancario: VANOVA no tiene integración bancaria.

    Las categorías nunca se mezclan: cada métrica lleva su etiqueta."""
    data = config_store.load()
    invoices = data.get("organizedInvoices") or []
    finance = data.get("organizedFinance") or []
    if not isinstance(invoices, list):
        invoices = []
    if not isinstance(finance, list):
        finance = []
    collections = [f for f in finance if isinstance(f, dict) and f.get("type") == "collection"]
    payments = [f for f in finance if isinstance(f, dict) and f.get("type") == "payment"]
    if not collections and not payments:
        return {"available": False, "dataSource": "facturascript"}
    col_total = round(sum(c.get("amount", 0) for c in collections if isinstance(c.get("amount"), (int, float))), 2)
    pay_total = round(sum(p.get("amount", 0) for p in payments if isinstance(p.get("amount"), (int, float))), 2)
    issued = [i for i in invoices if isinstance(i, dict) and i.get("type") == "issued"]
    received = [i for i in invoices if isinstance(i, dict) and i.get("type") == "received"]
    pending_col = [i for i in issued if not i.get("paid")]
    pending_pay = [i for i in received if not i.get("paid")]
    pending_col_total = round(sum(i.get("total", 0) for i in pending_col if isinstance(i.get("total"), (int, float))), 2)
    pending_pay_total = round(sum(i.get("total", 0) for i in pending_pay if isinstance(i.get("total"), (int, float))), 2)
    upcoming = [i for i in pending_col if _due_within(i.get("dueDate"), 30)]
    upcoming_total = round(sum(i.get("total", 0) for i in upcoming if isinstance(i.get("total"), (int, float))), 2)
    return {
        "available": True,
        "dataSource": "facturascript",
        "metrics": {
            # REAL — proceden directamente de FacturaScripts
            "collections": {"value": col_total, "count": len(collections), "category": "real", "source": "facturascript"},
            "payments": {"value": pay_total, "count": len(payments), "category": "real", "source": "facturascript"},
            # CALCULADO — derivados sobre datos reales
            "netCashMovement": {
                "value": round(col_total - pay_total, 2),
                "category": "calculated",
                "definition": "cobros - pagos (movimiento neto de caja, NO saldo bancario)",
            },
            "pendingCollections": {
                "value": pending_col_total, "count": len(pending_col), "category": "calculated",
                "definition": "facturas emitidas no pagadas",
            },
            "pendingPayments": {
                "value": pending_pay_total, "count": len(pending_pay), "category": "calculated",
                "definition": "facturas recibidas no pagadas",
            },
            "upcomingDue": {
                "value": upcoming_total, "count": len(upcoming), "category": "calculated",
                "horizonDays": 30, "definition": "vencimientos de cobro en los próximos 30 días",
            },
            # NO DISPONIBLE — explícito, nunca se mezcla con las demás
            "bankBalance": {
                "value": None, "category": "not_available",
                "reason": "Saldo bancario real no disponible: VANOVA no tiene integración bancaria.",
            },
        },
    }


# ---------------------------------------------------------------------------
# Persistencia idempotente (dedupe por id + fusión de clientes)
# ---------------------------------------------------------------------------


def _persist(kind: str, rows: list[dict[str, Any]], source: str) -> None:
    """Validate + stamp + MERGE into the stored dataset (idempotent by id).

    Merging (not replacing) is what makes partial-data protection real: when
    one resource fails, the rows already synced from it survive the next sync.
    Never stores an invalid row."""
    data = config_store.load()
    valid: list[dict[str, Any]] = []
    for raw in rows:
        if kind == "invoice":
            ok, _ = business_model.validate_invoice(raw)
        elif kind == "line":
            ok, _ = business_model.validate_invoice_line(raw)
        elif kind == "cash":
            ok, _ = business_model.validate_cash_row(raw)
        else:
            ok, _ = business_model.validate_customer(raw)
        if ok:
            valid.append(business_model.stamp(raw, source))
    if kind == "invoice":
        existing = data.get("organizedInvoices") or []
        # Dedupe con tipo incluido: idfactura es una secuencia independiente por
        # tabla (facturascli.idfactura=1 y facturasprov.idfactura=1 colisionan).
        merged = business_model.dedupe(
            list(existing) + valid, lambda r: f"{r.get('type')}:{str(r.get('id') or r.get('code') or '').lower()}"
        )
        config_store.save({"organizedInvoices": merged})
    elif kind == "line":
        existing = data.get("organizedInvoiceLines") or []
        merged = business_model.dedupe(list(existing) + valid, lambda r: str(r.get("id") or "").lower())
        config_store.save({"organizedInvoiceLines": merged})
    elif kind == "cash":
        existing = data.get("organizedFinance") or []
        merged = business_model.dedupe(list(existing) + valid, lambda r: str(r.get("id") or "").lower())
        config_store.save({"organizedFinance": merged})
    elif kind == "supplier":
        existing = data.get("organizedSuppliers") or []
        merged = business_model.dedupe(list(existing) + valid, lambda r: str(r.get("taxId") or r.get("email") or r.get("name") or "").lower())
        config_store.save({"organizedSuppliers": merged})
    else:  # customer
        _merge_customers(valid)


def _merge_customers(incoming: list[dict[str, Any]]) -> None:
    data = config_store.load()
    existing = data.get("organizedCustomers") or []
    if not isinstance(existing, list):
        existing = []
    by_key: dict[str, dict[str, Any]] = {}
    for c in existing:
        if isinstance(c, dict):
            key = str(c.get("email") or c.get("taxId") or c.get("name") or "").strip().lower()
            if key:
                by_key[key] = c
    added = 0
    for c in incoming:
        key = str(c.get("email") or c.get("taxId") or c.get("name") or "").strip().lower()
        if not key:
            continue
        if key in by_key:
            continue  # keep the existing record — never clobber with a partial one
        by_key[key] = c
        added += 1
    config_store.save({"organizedCustomers": list(by_key.values())})
    log.info("FacturaScript: %d clientes nuevos fusionados (total %d)", added, len(by_key))


# ---------------------------------------------------------------------------
# Sync completo
# ---------------------------------------------------------------------------


def sync_now() -> dict[str, Any]:
    """Run the full FacturaScripts pipeline. NEVER raises: returns a structured
    result so the UI and Hermes always get a clear message."""
    global _sync_running
    with _sync_lock:
        if _sync_running:
            return {"ok": True, "started": False, "message": "Sync de FacturaScripts ya en curso"}
        _sync_running = True
    try:
        cfg = integrations_store.get_config("facturascript")
        base_url = normalize_fs_base_url(str(cfg.get("base_url") or ""))
        api_key = str(cfg.get("api_key") or "").strip()
        if not base_url:
            _save_state(status="not_configured", ok=False, error=None, userMessage="FacturaScripts no está configurado")
            return {"ok": False, "error": "FacturaScripts no está configurado", "status": "not_configured"}
        if not api_key:
            _save_state(status="not_configured", ok=False, error="Falta la API key", userMessage="Falta la API key de FacturaScripts")
            return {"ok": False, "error": "Falta la API key de FacturaScripts", "status": "not_configured"}

        _save_state(status="syncing", ok=False, error=None)
        try:
            client = httpx.Client(timeout=FS_TIMEOUT, follow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            _save_state(status="error", ok=False, error=str(exc), userMessage="No se pudo crear el cliente HTTP")
            return {"ok": False, "error": str(exc), "status": "error"}

        resource_errors: dict[str, str] = {}
        counts: dict[str, int] = {}
        fetched: dict[str, list[dict[str, Any]]] = {}
        try:
            probe, probe_error = None, None
            for path in FS_PROBE_PATHS:
                probe, probe_error = _request(client, f"{base_url}{path}", api_key, {})
                if probe is not None:
                    break
            if probe is None:
                _save_state(
                    status="error", ok=False, error=probe_error or "API de FacturaScripts no responde",
                    userMessage="No se pudo conectar con la API de FacturaScripts (comprueba URL y API key)",
                )
                return {"ok": False, "error": probe_error or "API no responde", "status": "error"}

            for resource, meta in _RESOURCES.items():
                rows, error = _fetch_rows(client, base_url, api_key, resource)
                if error:
                    resource_errors[resource] = error
                    log.warning("FacturaScript: recurso %s falló: %s", resource, error)
                    continue
                fetched[resource] = rows
                counts[resource] = len(rows)
        finally:
            client.close()

        if not fetched:
            _save_state(
                status="error", ok=False, error="todos los recursos fallaron",
                resourceErrors=resource_errors,
                userMessage="FacturaScripts respondió pero todos los recursos fallaron — no se tocó ningún dato",
            )
            return {"ok": False, "error": "todos los recursos fallaron", "status": "error"}

        # Normalize + persist each successfully fetched resource. Failed ones
        # keep their previously stored data (partial-data protection).
        for resource, meta in _RESOURCES.items():
            rows = fetched.get(resource)
            if rows is None:
                continue
            kind = meta["kind"]
            normalized: list[dict[str, Any]] = []
            for raw in rows:
                if kind == "invoice":
                    normalized.append(_normalize_invoice(raw, meta["invoiceType"]))
                elif kind == "line":
                    normalized.append(_normalize_line(raw, meta["invoiceType"]))
                elif kind == "cash":
                    normalized.append(_normalize_cash(raw, meta["cashType"]))
                else:
                    normalized.append(_normalize_partner(raw, kind))
            _persist(kind, normalized, source="facturascript")

        invoice_count = len(fetched.get("facturascli", [])) + len(fetched.get("facturasprov", []))
        line_count = len(fetched.get("lineascli", [])) + len(fetched.get("lineasprov", []))
        status = "partial" if resource_errors else "ok"
        state = _save_state(
            status=status,
            ok=not resource_errors,
            lastSync=datetime.now(timezone.utc).isoformat(),
            counts={
                "invoices": invoice_count,
                "issued": len(fetched.get("facturascli", [])),
                "received": len(fetched.get("facturasprov", [])),
                "lines": line_count,
                "collections": len(fetched.get("cobros", [])),
                "payments": len(fetched.get("pagos", [])),
                "customers": len(fetched.get("clientes", [])),
                "suppliers": len(fetched.get("proveedores", [])),
            },
            resourceErrors=resource_errors,
            error=None,
            userMessage=None,
            dataMode="real",
        )
        log.info(
            "FacturaScript sync: %d facturas, %d líneas, %d cobros, %d pagos (%s)",
            invoice_count, line_count, counts.get("cobros", 0), counts.get("pagos", 0), status,
        )
        # P2 — reconciliación financiera tras cada sync: registra discrepancias,
        # nunca corrige el dato en silencio.
        try:
            report = business_model.financial_reconciliation()
            config_store.save({"financialReconciliation": report})
            for item in report.get("items") or []:
                if item.get("severity") in ("high", "medium"):
                    log.warning("Reconciliación [%s]: %s", item.get("scope"), item.get("detail"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Reconciliación financiera no disponible: %s", exc)
        return {"ok": True, "status": status, "counts": state["counts"], "resourceErrors": resource_errors}
    except Exception as exc:  # noqa: BLE001 — the pipeline must never crash the runtime
        log.error("FacturaScript sync failed: %s", exc)
        _save_state(status="error", ok=False, error=str(exc), userMessage="Error inesperado sincronizando FacturaScripts")
        return {"ok": False, "error": str(exc), "status": "error"}
    finally:
        with _sync_lock:
            _sync_running = False


# ---------------------------------------------------------------------------
# Background sync (mirror de shopify_sync)
# ---------------------------------------------------------------------------

_background_thread: threading.Thread | None = None
_background_stop = threading.Event()


def start_background_sync() -> None:
    global _background_thread
    if _background_thread and _background_thread.is_alive():
        return
    _background_stop.clear()

    def loop() -> None:
        while not _background_stop.is_set():
            try:
                cfg = integrations_store.get_config("facturascript")
                if cfg.get("base_url") and cfg.get("api_key"):
                    sync_now()
            except Exception as exc:  # noqa: BLE001
                log.warning("FacturaScript background sync tick: %s", exc)
            _background_stop.wait(FS_INTERVAL_SECONDS)

    _background_thread = threading.Thread(target=loop, name="maios-facturascript-sync", daemon=True)
    _background_thread.start()


def stop_background_sync() -> None:
    _background_stop.set()


def ensure_background_sync() -> None:
    start_background_sync()
