"""Continuous Shopify sync — periodic pull of products and orders."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import config_store, integrations_store
from .logger import get_logger

log = get_logger("maios.shopify", "shopify-sync")

SYNC_INTERVAL_SECONDS = 180
API_VERSION = "2024-01"
REQUIRED_SCOPES = ("read_products", "read_orders")
ERROR_CATEGORIES = frozenset(
    {"permission_denied", "authentication_failed", "network_error", "rate_limited", "server_error"}
)
_sync_lock = threading.Lock()
_sync_thread: threading.Thread | None = None
_sync_running = False
_stop_event = threading.Event()

# --- Dev Dashboard client-credentials support (Shopify 2025+) ---------------
# Shopify deprecó los "custom apps" del admin y los tokens Admin API `shpat_`
# ahora se obtienen desde el Dev Dashboard. En el Dev Dashboard el usuario ve:
#   - Client ID (identifica la app)
#   - Client Secret (empieza por `shpss_`)  ← NO es un Admin API token usable
# El Client Secret `shpss_` NO vale como cabecera `X-Shopify-Access-Token`
# (devuelve 401). Hay que intercambiarlo por un access_token real vía el
# client credentials grant (POST /admin/oauth/access_token). El access_token
# dura 24h; se cachea y se refresca. Fuente: docs de Shopify (Dev Dashboard).
_CC_CACHE: dict[str, tuple[str, float]] = {}  # key -> (token, expira)
_CC_CACHE_TTL = 23 * 3600  # 23h (el token dura 24h)


def _is_client_secret(value: str) -> bool:
    v = (value or "").strip().lower()
    # Solo `shpss_` es Client Secret (Dev Dashboard) → requiere intercambio.
    # `shpat_`/`shpua_`/`shpca_` son tokens de Admin válidos → uso directo.
    return v.startswith("shpss_")


def resolve_admin_token(url: str, token: str) -> str:
    """Devuelve un token usable como `X-Shopify-Access-Token`.

    - `shpat_*` / `shpua_*` → se usan tal cual (Admin API token).
    - `shp_*` (Client Secret del Dev Dashboard) → se intercambia por un
      access_token real vía client credentials grant (cached 24h).
    Necesita el client_id de la app: se lee de integrations_store. Si falta,
    lanza RuntimeError con un mensaje claro (no inventa).
    """
    t = (token or "").strip()
    if not _is_client_secret(t):
        return t  # shpat_/shpua_ directo
    cache_key = f"{url}|{t}"
    cached = _CC_CACHE_TTL and _CC_CACHE.get(cache_key)
    if cached and cached[1] > time.time():
        return cached[0]
    from . import integrations_store
    entry = integrations_store.get_shopify_entry()
    client_id = str(entry.get("api_key") or entry.get("client_id") or "").strip()
    if not client_id:
        raise RuntimeError(
            "Este es un Client Secret del Dev Dashboard (empieza por `sh_`). "
            "Necesito también el Client ID de tu app Shopify para canjearlo por "
            "un access token. Pégalos juntos o usa un token Admin (`shpat_…`)."
        )
    access = _exchange_client_credentials(url, client_id, t)
    if not access:
        raise RuntimeError(
            "No pude canjear el Client Secret por un access token de Shopify "
            "(credenciales inválidas o app no instalada en esta tienda)."
        )
    _CC_CACHE[cache_key] = (access, time.time() + _CC_CACHE_TTL)
    return access


def _exchange_client_credentials(url: str, client_id: str, client_secret: str) -> str | None:
    """POST /admin/oauth/access_token con grant_type=client_credentials."""
    from urllib.parse import urlencode
    import urllib.request

    base = (url or "").rstrip("/")
    token_url = base + "/admin/oauth/access_token"
    payload = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")
    req = Request(
        token_url,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return str(data.get("access_token") or "").strip() or None
    except (HTTPError, URLError, ValueError) as exc:
        log.warning("Shopify client_credentials exchange failed: %s", exc)
        return None


def sync_status() -> dict[str, Any]:
    st = config_store.load().get("shopifySync") or {}
    cfg = integrations_store.get_config("shopify")
    return {
        "connected": cfg.get("connected", False),
        "url": cfg.get("url", ""),
        "lastSync": st.get("lastSync"),
        "lastError": st.get("lastError"),
        "userMessage": st.get("userMessage"),
        "status": st.get("status", "idle"),
        "errorCategory": st.get("errorCategory"),
        "intervalSeconds": SYNC_INTERVAL_SECONDS,
        "counts": st.get("counts") or {},
        "scopeErrors": st.get("scopeErrors") or [],
        "missingScopes": st.get("missingScopes") or [],
        "partial": bool(st.get("partial")),
    }


def needs_reauth() -> bool:
    """True when Shopify is connected but lacks scopes or permission — skip background sync."""
    cfg = integrations_store.get_config("shopify")
    if not cfg.get("connected"):
        bridge = integrations_store.sync_shopify_from_hermes_if_needed()
        if bridge and bridge.get("imported"):
            cfg = integrations_store.get_config("shopify")
        if not cfg.get("connected"):
            return False
    st = config_store.load().get("shopifySync") or {}
    if st.get("errorCategory") == "permission_denied" or st.get("missingScopes"):
        bridge = integrations_store.sync_shopify_from_hermes_if_needed()
        if bridge and bridge.get("ok"):
            return False
        st = config_store.load().get("shopifySync") or {}
    if st.get("errorCategory") == "permission_denied" or st.get("missingScopes"):
        creds = integrations_store.get_shopify_credentials()
        if creds.get("url") and creds.get("token"):
            live = check_credentials(creds["url"], creds["token"])
            if live.get("ok"):
                integrations_store.clear_stale_shopify_sync_errors()
                return False
    st = config_store.load().get("shopifySync") or {}
    if st.get("errorCategory") == "permission_denied":
        return True
    if st.get("missingScopes"):
        return True
    return False


def sync_now() -> dict[str, Any]:
    return _run_sync()


def check_credentials(url: str, token: str) -> dict[str, Any]:
    """Validate Shopify token and report granted/missing scopes."""
    url = (url or "").rstrip("/")
    token = (token or "").strip()
    if not url or not token:
        return {"ok": False, "error": "URL y token de Shopify son obligatorios"}

    try:
        payload = _shopify_get(url, token, f"/admin/oauth/access_scopes.json")
        granted = {
            (row.get("handle") or "").strip()
            for row in (payload.get("access_scopes") or [])
            if isinstance(row, dict)
        }
        missing = [scope for scope in REQUIRED_SCOPES if scope not in granted]
        return {
            "ok": not missing,
            "grantedScopes": sorted(granted),
            "missingScopes": missing,
            "userMessage": _scope_user_message(missing) if missing else None,
        }
    except Exception as exc:
        parsed = _parse_shopify_error(str(exc))
        return {
            "ok": False,
            "error": parsed["technical"],
            "userMessage": parsed["userMessage"],
            "scopeErrors": parsed["scopeErrors"],
        }


def start_background_sync() -> None:
    global _sync_thread
    with _sync_lock:
        if _sync_thread and _sync_thread.is_alive():
            return
        _stop_event.clear()
        _sync_thread = threading.Thread(target=_loop, name="maios-shopify-sync", daemon=True)
        _sync_thread.start()
        log.info("Shopify background sync started (every %ds)", SYNC_INTERVAL_SECONDS)


def stop_background_sync() -> None:
    _stop_event.set()


def ensure_background_sync() -> None:
    """Restart poll thread if it died (e.g. after runtime attach/restart)."""
    global _sync_thread
    with _sync_lock:
        alive = _sync_thread is not None and _sync_thread.is_alive()
    if not alive:
        start_background_sync()


def _loop() -> None:
    time.sleep(5)
    while not _stop_event.is_set():
        cfg = integrations_store.get_config("shopify")
        if cfg.get("connected") and not needs_reauth():
            try:
                _run_sync()
            except Exception as exc:
                log.warning("Shopify sync loop error: %s", exc)
        elif cfg.get("connected") and needs_reauth():
            log.debug("Shopify background sync skipped — reauth required")
        if _stop_event.wait(SYNC_INTERVAL_SECONDS):
            break


def _run_sync() -> dict[str, Any]:
    """Ejecuta la sync con guarda de reentrada: el loop de fondo y una llamada
    manual (API) nunca sincronizan a la vez (FASE 9 hardening)."""
    global _sync_running
    with _sync_lock:
        if _sync_running:
            log.info("Shopify sync omitida — ya hay una en curso")
            return {"ok": False, "error": "Sincronización de Shopify ya en curso", "skipped": True}
        _sync_running = True
    try:
        return _run_sync_inner()
    finally:
        with _sync_lock:
            _sync_running = False


def _run_sync_inner() -> dict[str, Any]:
    integrations_store.sync_shopify_from_hermes_if_needed()
    creds = integrations_store.get_shopify_credentials()
    if not creds.get("url") or not creds.get("token"):
        return {"ok": False, "error": "Shopify no conectado"}

    url = creds["url"]
    token = creds["token"]

    config_store.save({
        "shopifySync": {
            "status": "syncing",
            "startedAt": _now(),
            "message": "Descargando productos y pedidos de Shopify…",
        }
    })

    from . import hermes_activity

    hermes_activity.log_step("Conectando con Shopify…", step="shopify_start", source="shopify")

    scope_check = check_credentials(url, token)
    missing_scopes = list(scope_check.get("missingScopes") or [])
    scope_errors = list(scope_check.get("scopeErrors") or [])

    products: list[dict[str, Any]] = []
    sales: list[dict[str, Any]] = []
    fetch_errors: list[str] = []

    if "read_products" not in missing_scopes:
        try:
            hermes_activity.log_step("Descargando productos de Shopify…", step="shopify_products", source="shopify")
            # Paginate: fetch ALL products (default limit=50 previously truncated
            # the catalog to the first page — stores with >50 products lost data).
            products = _map_shopify_products(
                _shopify_get_all(url, token, f"/admin/api/{API_VERSION}/products.json", limit=250)
            )
        except Exception as exc:
            parsed = _parse_shopify_error(str(exc))
            fetch_errors.append(parsed["technical"])
            scope_errors.extend(parsed["scopeErrors"])
            hermes_activity.log_step(f"Shopify: {parsed['userMessage']}", step="shopify_error", source="shopify")
    else:
        msg = _scope_user_message(["read_products"])
        fetch_errors.append(msg)
        scope_errors.append("read_products")
        hermes_activity.log_step(f"Shopify: {msg}", step="shopify_error", source="shopify")

    if "read_orders" not in missing_scopes:
        try:
            hermes_activity.log_step("Descargando pedidos de Shopify…", step="shopify_orders", source="shopify")
            sales = _map_shopify_orders(
                _shopify_get_all(url, token, f"/admin/api/{API_VERSION}/orders.json?status=any", limit=250)
            )
        except Exception as exc:
            parsed = _parse_shopify_error(str(exc))
            fetch_errors.append(parsed["technical"])
            scope_errors.extend(parsed["scopeErrors"])
            hermes_activity.log_step(f"Shopify: {parsed['userMessage']}", step="shopify_error", source="shopify")
    else:
        msg = _scope_user_message(["read_orders"])
        fetch_errors.append(msg)
        scope_errors.append("read_orders")
        hermes_activity.log_step(f"Shopify: {msg}", step="shopify_error", source="shopify")

    scope_errors = sorted(set(scope_errors))
    missing_scopes = sorted(set(missing_scopes + scope_errors))

    if not products and not sales:
        user_message = _scope_user_message(missing_scopes) if missing_scopes else (
            fetch_errors[0] if fetch_errors else "No se pudieron descargar datos de Shopify."
        )
        technical = fetch_errors[0] if fetch_errors else user_message
        error_category = "permission_denied" if missing_scopes else _classify_error(technical)
        log.warning("Shopify sync failed: %s", technical)
        config_store.save({
            "shopifySync": {
                "status": "error",
                "lastSync": config_store.load().get("shopifySync", {}).get("lastSync"),
                "lastError": technical,
                "userMessage": user_message,
                "errorCategory": error_category,
                "scopeErrors": scope_errors,
                "missingScopes": missing_scopes,
                "partial": False,
            }
        })
        return {
            "ok": False,
            "error": technical,
            "userMessage": user_message,
            "errorCategory": error_category,
            "scopeErrors": scope_errors,
        }

    existing_products = config_store.load().get("organizedProducts") or []
    existing_sales = config_store.load().get("organizedSales") or []
    if not isinstance(existing_products, list):
        existing_products = []
    if not isinstance(existing_sales, list):
        existing_sales = []

    merged_products = _merge_products(existing_products, products)
    merged_sales = _merge_sales(existing_sales, sales)

    # FASE 14 (P16): una sync NUNCA puede destruir cobertura o datos. Se
    # compara ANTES vs DESPUÉS del merge; si el resultado eliminaría costes
    # verificados, cobertura de identidad o volumen sin justificación, el
    # merge se rechaza y se conserva el estado anterior (regresión H23).
    from . import data_governance

    sync_guard = data_governance.evaluate_sync_guard(
        existing_products, existing_sales, merged_products, merged_sales
    )
    merge_blocked = bool(sync_guard.get("blocked"))
    merge_alerts = list(sync_guard.get("alerts") or [])
    if merge_blocked:
        log.warning("Shopify sync GUARD: %s", " | ".join(merge_alerts))
        # Se conserva el estado anterior (sin aplicar el merge destructivo).
        merged_products = existing_products
        merged_sales = existing_sales

    from . import file_organizer

    partial = bool(fetch_errors or missing_scopes)
    if partial:
        user_message = _scope_user_message(missing_scopes) if missing_scopes else fetch_errors[0]
        status = "partial"
        message = (
            f"Sincronización parcial: {len(products)} productos, {len(sales)} pedidos. "
            f"{user_message}"
        )
    else:
        user_message = None
        status = "ok"
        message = f"Sincronizados {len(products)} productos y {len(sales)} pedidos."

    sync_result = {
        "status": status,
        "lastSync": _now(),
        "lastError": fetch_errors[0] if fetch_errors else None,
        "userMessage": user_message,
        "message": message,
        "errorCategory": "permission_denied" if missing_scopes else (
            _classify_error(fetch_errors[0]) if fetch_errors else None
        ),
        "counts": {
            "products": len(merged_products),
            "orders": len(merged_sales),
        },
        "scopeErrors": scope_errors,
        "missingScopes": missing_scopes,
        "partial": partial,
        "guardBlocked": merge_blocked,
        "guardAlerts": merge_alerts,
        "guard": sync_guard,
    }

    # Shopify sync is additive/authoritative for Shopify keys, but must never
    # truncate local Excel/manual rows that were already persisted.
    config_store.save({
        "organizedProducts": merged_products,
        "organizedSales": merged_sales,
        "shopifySync": sync_result,
    })
    file_organizer.sync_dashboard_overview(merged_products, merged_sales)

    # FASE 9: backfill automático — si quedan pedidos sin line_items (datos
    # migrados de sync anteriores), se recuperan sin re-descargar el catálogo.
    if status == "ok" and any(
        isinstance(s, dict) and s.get("source") == "shopify" and not s.get("line_items")
        for s in merged_sales
    ):
        try:
            backfill_line_items()
        except Exception as exc:  # noqa: BLE001 — el backfill nunca rompe la sync
            log.warning("Shopify backfill automático falló: %s", exc)

    hermes_activity.log_step(message, step="shopify_done", source="shopify")
    log.info("Shopify sync %s: %d products, %d orders", status, len(products), len(sales))
    return {"ok": True, **sync_result}


def backfill_line_items() -> dict[str, Any]:
    """Backfill real: recupera `line_items` de Shopify para los pedidos ya
    guardados sin líneas (sync de versiones anteriores a la feature).

    Idempotente: los pedidos que ya tienen line_items no se tocan; ejecutar
    varias veces no duplica pedidos ni líneas. Cada pedido se actualiza en su
    sitio conservando id/customer/total/date/status. Los errores se registran
    individualmente y NUNCA se borran datos válidos: un pedido que falla
    conserva exactamente su estado previo."""
    from urllib.parse import quote

    creds = integrations_store.get_shopify_credentials()
    if not creds.get("url") or not creds.get("token"):
        return {"ok": False, "error": "Shopify no conectado"}
    url = creds["url"].rstrip("/")
    token = creds["token"]

    data = config_store.load()
    sales = data.get("organizedSales") or []
    if not isinstance(sales, list):
        sales = []

    candidates = [
        s for s in sales
        if isinstance(s, dict) and s.get("source") == "shopify" and not s.get("line_items")
    ]
    if not candidates:
        return {"ok": True, "candidates": 0, "updated": 0, "skipped": 0, "failed": 0, "linesRecovered": 0, "message": "No hay pedidos de Shopify sin line_items."}

    updated = 0
    skipped = 0
    failed = 0
    lines_recovered = 0
    errors: list[dict[str, Any]] = []

    for sale in candidates:
        order_name = str(sale.get("id") or "")
        if not order_name:
            skipped += 1
            continue
        try:
            path = f"/admin/api/{API_VERSION}/orders.json?status=any&name={quote(order_name, safe='')}&limit=1"
            payload = _shopify_get(url, token, path)
            orders = payload.get("orders") or []
            if not orders:
                failed += 1
                errors.append({"id": order_name, "error": "Pedido no encontrado en Shopify"})
                continue
            mapped = _map_shopify_orders([orders[0]])
            lines = (mapped[0] or {}).get("line_items") or []
            sale["line_items"] = lines  # conserva id/customer/total/date/status
            updated += 1
            lines_recovered += len(lines)
        except Exception as exc:  # noqa: BLE001 — un fallo NUNCA toca el pedido
            failed += 1
            errors.append({"id": order_name, "error": str(exc)[:200]})
        time.sleep(0.25)  # respeta rate limits de Shopify en backfills largos

    prev_sync = data.get("shopifySync") or {}
    if isinstance(prev_sync, dict):
        prev_sync = dict(prev_sync)
    else:
        prev_sync = {}
    prev_sync["backfill"] = {
        "ranAt": _now(),
        "candidates": len(candidates),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "linesRecovered": lines_recovered,
        "errors": errors[:50],
    }
    # BUG-034 FIX (raíz): RMW atómico bajo config_store.update(). Antes este
    # backfill (fetch de red con sleep 0.25s, puede durar minutos) acumulaba
    # `sales` en memoria y al final hacía config_store.save({"organizedSales":
    # sales}) SOBRESCRIBIENDO la lista completa — si otro escritor (cost_importer,
    # facturascripts_sync, un sync de Shopify simultáneo) persistía
    # organizedSales/organizedProducts durante el fetch, su cambio se perdía
    # (lost-update, mismo patrón que BUG-006/015/019/021/027). Ahora el backfill
    # solo captura los pedidos ACTUALIZADOS (con line_items) y los aplica con
    # update() sobre la lista vigente, sin pisar escrituras concurrentes.
    updated_by_id = {str(s.get("id") or ""): s for s in sales if s.get("line_items")}

    def _mutate(cfg):
        current = cfg.get("organizedSales") or []
        if not isinstance(current, list):
            current = []
        # Re-aplicar solo los pedidos actualizados sobre la lista vigente.
        for s in current:
            if not isinstance(s, dict):
                continue
            repl = updated_by_id.get(str(s.get("id") or ""))
            if repl is not None:
                # conserva la versión más reciente (la del backfill con líneas)
                # pero preserva cualquier campo que otro escritor haya tocado
                merged = dict(repl)
                for k, v in s.items():
                    if k not in ("line_items",) and v is not None and merged.get(k) is None:
                        merged[k] = v
                current[current.index(s)] = merged
        cfg["organizedSales"] = current
        cfg["shopifySync"] = prev_sync
        return cfg

    config_store.update(_mutate)
    log.info("Shopify backfill: %d/%d actualizados (%d líneas), %d fallidos", updated, len(candidates), lines_recovered, failed)
    return {
        "ok": True,
        "candidates": len(candidates),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "linesRecovered": lines_recovered,
        "errors": errors[:50],
        "message": f"Backfill: {updated} pedidos actualizados ({lines_recovered} líneas), {skipped} omitidos, {failed} fallidos.",
    }


def recover_variant_identity() -> dict[str, Any]:
    """FASE 12 (P3/P5): recupera la identidad de variante (variant id +
    barcode) de Shopify y la persiste en el catálogo local.

    Por qué existe: las líneas de pedido de Shopify solo traen `variant_id`
    (no el SKU del variante), mientras que el catálogo guarda el SKU del
    proveedor. El enlace línea → catálogo → coste requiere el variant_id en
    el catálogo. Esta función descarga los productos (solo lectura) y
    completa `shopifyVariantId`/`barcode` en los productos que faltan.

    Garantías: idempotente, NO toca sku/name/netPrice/rrp, solo AÑADE campos
    de identidad, y un fallo de red NO escribe nada (se persiste solo al
    final, con los productos completados en memoria)."""
    creds = integrations_store.get_shopify_credentials()
    if not creds.get("url") or not creds.get("token"):
        return {"ok": False, "error": "Shopify no conectado"}
    url = creds["url"].rstrip("/")
    token = creds["token"]

    data = config_store.load()
    products = data.get("organizedProducts") or []
    if not isinstance(products, list):
        products = []

    # variant_sku → {variantId, barcode} para todos los variantes de todos los
    # productos (un producto puede tener varios variantes).
    raw_products = _shopify_get_all(url, token, f"/admin/api/{API_VERSION}/products.json", limit=250)
    by_variant_sku: dict[str, dict[str, str]] = {}
    for p in raw_products:
        for variant in p.get("variants") or []:
            v_sku = str(variant.get("sku") or "").strip()
            if not v_sku:
                continue
            by_variant_sku[v_sku] = {
                "variantId": str(variant.get("id") or ""),
                "barcode": str(variant.get("barcode") or "").strip(),
            }

    updated = 0
    already = 0
    for product in products:
        if not isinstance(product, dict):
            continue
        p_sku = str(product.get("sku") or "").strip()
        if not p_sku or product.get("shopifyVariantId"):
            already += 1
            continue
        info = by_variant_sku.get(p_sku)
        if not info or not info["variantId"]:
            continue
        product["shopifyVariantId"] = info["variantId"]
        if info["barcode"] and not product.get("barcode"):
            product["barcode"] = info["barcode"]
        updated += 1

    # BUG-034 FIX (raíz): RMW atómico bajo config_store.update(). Antes esta
    # función persistía con config_store.save({"organizedProducts": products})
    # SOBRESCRIBIENDO la lista completa tras un fetch de red largo — si otro
    # escritor (cost_importer, facturascripts_sync, un sync de Shopify)
    # persistía organizedProducts durante el fetch, su cambio se perdía
    # (lost-update). Ahora solo se capturan los productos ACTUALIZADOS y se
    # aplican con update() sobre la lista vigente.
    enriched = {str(p.get("sku") or ""): p for p in products if p.get("shopifyVariantId")}

    def _mutate(cfg):
        current = cfg.get("organizedProducts") or []
        if not isinstance(current, list):
            current = []
        for p in current:
            if not isinstance(p, dict):
                continue
            repl = enriched.get(str(p.get("sku") or ""))
            if repl is not None:
                # preserva campos que otro escritor haya tocado; solo AÑADE
                # shopifyVariantId/barcode (nunca pisa sku/name/cost/rrp)
                for k, v in repl.items():
                    if k in ("shopifyVariantId", "barcode") and not p.get(k):
                        p[k] = v
        cfg["organizedProducts"] = current
        return cfg

    config_store.update(_mutate)
    from . import file_organizer

    file_organizer.sync_dashboard_overview(config_store.load().get("organizedProducts") or [], config_store.load().get("organizedSales") or [])
    return {
        "ok": True,
        "productsProcessed": len(products),
        "updated": updated,
        "alreadyHad": already,
        "message": f"Identidad recuperada: {updated} productos enlazados por variant id, {already} ya lo tenían.",
    }


def _shopify_get(base_url: str, token: str, path: str) -> dict[str, Any]:
    req = Request(
        base_url + path,
        headers={
            "X-Shopify-Access-Token": resolve_admin_token(base_url, token),
            "Accept": "application/json",
            "User-Agent": "VANOVA-Desktop/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"Shopify HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Shopify unreachable: {exc.reason}") from exc


def _shopify_get_all(base_url: str, token: str, path: str, limit: int = 250) -> list[dict[str, Any]]:
    """Fetch ALL items from a paginated Shopify REST endpoint.

    Shopify paginates with a `Link` response header whose `rel="next"` URL
    carries a `page_info` cursor. The previous implementation requested only
    the first page (limit=50), silently truncating catalogs with more rows —
    e.g. a store with 462 products was shown as 50. This follows the cursor
    until the last page (defensive cap of 50 pages / 12 500 rows).
    """
    from urllib.parse import quote

    items: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(50):
        url = f"{base_url}{path}"
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}limit={int(limit)}"
        if cursor:
            url = f"{url}&page_info={quote(cursor, safe='')}"
        req = Request(
            url,
            headers={
                "X-Shopify-Access-Token": resolve_admin_token(base_url, token),
                "Accept": "application/json",
                "User-Agent": "VANOVA-Desktop/1.0",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=25) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                link = resp.headers.get("Link") or ""
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")[:300]
            raise RuntimeError(f"Shopify HTTP {exc.code}: {raw}") from exc
        except URLError as exc:
            raise RuntimeError(f"Shopify unreachable: {exc.reason}") from exc

        page_items: list[dict[str, Any]] = []
        for key, value in body.items():
            if isinstance(value, list):
                page_items = value
                break
        if not page_items:
            break
        items.extend(page_items)

        # Next page cursor from the Link header (rel="next").
        next_cursor: str | None = None
        for part in link.split(","):
            if 'rel="next"' in part:
                match = re.search(r"page_info=([^&>]+)", part)
                if match:
                    next_cursor = match.group(1)
                break
        if not next_cursor:
            break
        cursor = next_cursor
    return items


def _parse_shopify_error(message: str) -> dict[str, Any]:
    lower = message.lower()
    scope_errors: list[str] = []
    for scope in REQUIRED_SCOPES:
        if scope.replace("_", " ") in lower or scope in lower:
            scope_errors.append(scope)
    if "merchant approval" in lower or "requires" in lower and "scope" in lower:
        match = re.search(r"read_[a-z_]+", lower)
        if match and match.group(0) not in scope_errors:
            scope_errors.append(match.group(0))
    user_message = _scope_user_message(scope_errors) if scope_errors else message
    category = "permission_denied" if scope_errors else _classify_error(message)
    return {
        "technical": message,
        "userMessage": user_message,
        "scopeErrors": scope_errors,
        "errorCategory": category,
    }


def _classify_error(message: str) -> str:
    lower = (message or "").lower()
    if "401" in lower or "unauthorized" in lower or "invalid api key" in lower:
        return "authentication_failed"
    if "403" in lower or "permission" in lower or "scope" in lower or "approval" in lower:
        return "permission_denied"
    if "429" in lower or "rate limit" in lower or "too many" in lower:
        return "rate_limited"
    if re.search(r"\b5\d{2}\b", lower) or "server error" in lower:
        return "server_error"
    if "unreachable" in lower or "timed out" in lower or "timeout" in lower or "network" in lower:
        return "network_error"
    return "server_error"


def _scope_user_message(missing: list[str]) -> str:
    scopes = ", ".join(missing) if missing else "read_products, read_orders"
    return (
        f"Faltan permisos de Shopify ({scopes}). "
        "En el admin de Shopify → Configuración → Apps → tu app → "
        "aprobar los permisos y volver a pegar el token en VANOVA."
    )


def _map_shopify_products(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in items:
        variant = (p.get("variants") or [{}])[0]
        price = variant.get("price")
        out.append({
            "name": p.get("title") or "—",
            "sku": variant.get("sku") or str(variant.get("id") or ""),
            "netPrice": float(price) if price else None,
            "rrp": float(price) if price else None,
            # FASE 12: conservar la identidad del variante (variant ID + barcode)
            # para que las líneas de pedido (que solo traen variant_id) puedan
            # enlazarse con el catálogo y, desde ahí, con el coste real.
            "shopifyVariantId": str(variant.get("id") or ""),
            "barcode": str(variant.get("barcode") or "").strip() or None,
            "sourceFile": "Shopify",
            "source": "shopify",
        })
    return out


def _map_shopify_orders(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for o in items:
        total = o.get("total_price")
        customer = o.get("customer") or {}
        customer_name = " ".join(
            part for part in (customer.get("first_name"), customer.get("last_name")) if part
        ).strip()
        # Shopify returns `line_items` inside each order. Previously we dropped
        # them, so the agents could only see order-level totals — making it
        # impossible to compute sales per product (top sellers, units, etc.).
        line_items: list[dict[str, Any]] = []
        for li in o.get("line_items") or []:
            variant = li.get("variant") or {}
            sku = (variant.get("sku") or "").strip()
            variant_id = str(li.get("variant_id") or "")
            if not sku:
                # La API de pedidos no devuelve el SKU del variante; la línea
                # se identifica por variant_id. Lo guardamos en `sku` (como
                # antes) Y en `variant_id` para que la capa de identidad pueda
                # resolverlo contra el catálogo (FASE 12).
                sku = variant_id or str(li.get("product_id") or "")
            qty = li.get("quantity")
            price = li.get("price")
            line_items.append({
                "sku": sku,
                "variant_id": variant_id or None,
                "title": li.get("title") or "—",
                "quantity": int(qty) if qty else 1,
                "price": float(price) if price else None,
            })
        out.append({
            "id": str(o.get("name") or o.get("id") or ""),
            "customer": customer_name or (o.get("email") or "—"),
            "total": float(total) if total else None,
            "date": (o.get("created_at") or "—")[:10],
            "status": o.get("financial_status") or o.get("fulfillment_status") or "—",
            "line_items": line_items,
            "sourceFile": "Shopify",
            "source": "shopify",
        })
    return out


# Campos de ENRIQUECIMIENTO LOCAL que la API de Shopify NO devuelve y que
# nunca deben perderse al re-sincronizar: costes importados (cost_importer),
# procedencia, marcas de tiempo y ESTADO DE CALIDAD (FASE 14 gobernanza). El
# sync actualiza precio/identidad desde la API pero PRESERVA estos campos si el
# producto ya existe (FASE 14, H23 + gobernanza: qualityStatus/legacyFromVersion
# son propiedad de VANOVA y NUNCA se pierden en un sync).
_LOCAL_ENRICHMENT_FIELDS = (
    "cost", "costSource", "costStatus", "sourceReference", "costUpdatedAt",
    "qualityStatus", "legacyFromVersion", "lastValidatedAt", "dataProvenance",
)


def _merge_products(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    # Índice de TODOS los existentes (incluidos los de Shopify, que luego se
    # reemplazan por la API) para conservar el enriquecimiento local al fusionar.
    all_existing: dict[str, dict[str, Any]] = {}
    for item in existing:
        key = (item.get("sku") or item.get("name") or "").lower()
        if not key:
            continue
        all_existing[key] = item
        if item.get("source") == "shopify":
            continue  # los de Shopify se reemplazan por la respuesta fresca
        by_key[key] = item
    for item in incoming:
        key = (item.get("sku") or item.get("name") or "").lower()
        if key:
            existing_item = all_existing.get(key)
            if existing_item and isinstance(existing_item, dict):
                # FASE 14 (H23): conservar el enriquecimiento local (costes,
                # procedencia) que la API no conoce — nunca se pierde al sync.
                for field in _LOCAL_ENRICHMENT_FIELDS:
                    if existing_item.get(field) is not None and item.get(field) is None:
                        item[field] = existing_item[field]
            by_key[key] = item
    return list(by_key.values())


# Campos de gobernanza/calidad (propiedad de VANOVA) que una sync NUNCA puede
# pisar en los pedidos (FASE 14): el pedido fresco de la API no los trae y el
# marcado needs_review/legacy debe sobrevivir a la re-sincronización.
_ORDER_ENRICHMENT_FIELDS = (
    "qualityStatus", "legacyFromVersion", "lastValidatedAt", "dataProvenance", "notes",
)


def _merge_sales(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    all_existing: dict[str, dict[str, Any]] = {}
    by_key: dict[str, dict[str, Any]] = {}
    for item in existing:
        key = str(item.get("id") or "")
        if not key:
            continue
        all_existing[key] = item
        if item.get("source") == "shopify":
            continue  # los de Shopify se reemplazan por la respuesta fresca
        by_key[key] = item
    for item in incoming:
        key = str(item.get("id") or "")
        if not key:
            continue
        existing_item = all_existing.get(key)
        if existing_item and isinstance(existing_item, dict):
            for field in _ORDER_ENRICHMENT_FIELDS:
                if existing_item.get(field) is not None and item.get(field) is None:
                    item[field] = existing_item[field]
        by_key[key] = item
    return list(by_key.values())


def _orders_summary(sales: list[dict[str, Any]]) -> dict[str, Any]:
    totals = [s.get("total") for s in sales if isinstance(s.get("total"), (int, float))]
    customers = {str(s.get("customer")) for s in sales if s.get("customer")}
    return {
        "orders": len(sales),
        "revenue": sum(totals) if totals else None,
        "customers": len(customers) if customers else None,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
