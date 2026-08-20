"""VANOVA Connector Layer — FASE 13 (P2/P3).

Contrato común para TODAS las fuentes de datos de VANOVA. El core de VANOVA
(analytics, profitability, detection_engine, Hermes, dashboard) NUNCA depende
de una fuente concreta: solo conoce `source_id` + capabilities.

Cada conector expone:

  * id / label            — identificador y nombre para la UI
  * capabilities()        — qué tipos de datos puede proporcionar
  * status()              — conectado/desconectado/error + última sync
  * sync_now()            — ejecutar sincronización (si aplica)
  * implemented           — True si el conector existe hoy; False = "próximamente"

Un conector SOLO implementa lo que su fuente puede dar (un conector de pedidos
no está obligado a exponer facturas si su API no las tiene).

El core usa `source_capabilities(source_id)` y `sources_with(capability)` para
decir "esta empresa no tiene facturas porque ninguna de sus fuentes las
proporciona" en vez de "FacturaScripts está desconectado".
"""
from __future__ import annotations

from typing import Any, Callable


# Capacidades normalizadas del modelo canónico de VANOVA.
CAP_PRODUCTS = "products"
CAP_ORDERS = "orders"
CAP_ORDER_LINES = "order_lines"
CAP_CUSTOMERS = "customers"
CAP_INVENTORY = "inventory"
CAP_INVOICES = "invoices"
CAP_INVOICE_LINES = "invoice_lines"
CAP_PAYMENTS = "payments"
CAP_SUPPLIERS = "suppliers"
CAP_COSTS = "costs"
CAP_FINANCE = "finance"
CAP_STOCK = "stock"

ALL_CAPABILITIES = (
    CAP_PRODUCTS, CAP_ORDERS, CAP_ORDER_LINES, CAP_CUSTOMERS, CAP_INVENTORY,
    CAP_INVOICES, CAP_INVOICE_LINES, CAP_PAYMENTS, CAP_SUPPLIERS, CAP_COSTS,
    CAP_FINANCE, CAP_STOCK,
)

# Labels amigables para la UI/Hermes.
CAPABILITY_LABELS: dict[str, str] = {
    CAP_PRODUCTS: "Productos",
    CAP_ORDERS: "Pedidos / ventas",
    CAP_ORDER_LINES: "Líneas de pedido",
    CAP_CUSTOMERS: "Clientes",
    CAP_INVENTORY: "Inventario",
    CAP_INVOICES: "Facturas",
    CAP_INVOICE_LINES: "Líneas de factura",
    CAP_PAYMENTS: "Pagos / cobros",
    CAP_SUPPLIERS: "Proveedores",
    CAP_COSTS: "Costes",
    CAP_FINANCE: "Finanzas",
    CAP_STOCK: "Stock",
}


class Connector:
    """Descriptor declarativo de una fuente de datos.

    Los conectores reales (shopify, facturascripts, fileimport) exponen
    funciones del módulo correspondiente; los conectores futuros
    (woocommerce, prestashop) se registran con implemented=False para que la
    UI muestre "Próximamente" sin simular que existen.
    """

    def __init__(
        self,
        *,
        id: str,
        label: str,
        capabilities: dict[str, bool] | Callable[[], dict[str, bool]],
        implemented: bool = True,
        description: str = "",
        status: Callable[[], dict[str, Any]] | None = None,
        sync_now: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.id = id
        self.label = label
        self.description = description
        self.implemented = implemented
        self._capabilities = capabilities
        self._status = status
        self._sync = sync_now

    def capabilities(self) -> dict[str, bool]:
        """Capacidades DECLARADAS del tipo de conector (lo que puede dar cuando
        está conectado). Estáticas por conector: Shopify nunca da facturas;
        FacturaScripts sí. No depende del estado actual de conexión."""
        caps = self._capabilities() if callable(self._capabilities) else dict(self._capabilities or {})
        # Solo capacidades conocidas; el resto se ignora (no inventa).
        return {k: bool(v) for k, v in caps.items() if k in ALL_CAPABILITIES}

    def effective_capabilities(self) -> dict[str, bool]:
        """Capacidades EFECTIVAS: declaradas Y con la fuente conectada.
        Es lo que el negocio tiene AHORA MISMO."""
        caps = self.capabilities()
        st = self.status()
        connected = bool(st.get("connected", False) or st.get("configured", False) or st.get("ok", False))
        if not connected:
            return {k: False for k in caps}
        return caps

    def status(self) -> dict[str, Any]:
        if not self._status:
            return {"source": self.id, "implemented": self.implemented}
        try:
            st = self._status() or {}
            if not isinstance(st, dict):
                st = {}
            return {"source": self.id, "implemented": self.implemented, **st}
        except Exception:  # noqa: BLE001 — el estado nunca rompe el core
            return {"source": self.id, "implemented": self.implemented, "status": "unknown"}

    def sync_now(self) -> dict[str, Any]:
        if not self._sync:
            return {"ok": False, "error": f"El conector {self.id} no implementa sync manual"}
        return self._sync()


# ---------------------------------------------------------------------------
# Registro global de fuentes
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Connector] = {}


def register(connector: Connector) -> None:
    _REGISTRY[connector.id] = connector


def source(id: str) -> Connector | None:
    return _REGISTRY.get(id)


def list_sources(*, implemented_only: bool = False) -> list[Connector]:
    out = list(_REGISTRY.values())
    if implemented_only:
        out = [c for c in out if c.implemented]
    return out


def source_capabilities(source_id: str) -> dict[str, bool]:
    conn = _REGISTRY.get(source_id)
    return conn.capabilities() if conn else {}


def sources_with(capability: str) -> list[str]:
    """Fuentes CONECTADAS y con la capacidad EFECTIVA dada. No cuenta fuentes
    que la empresa no usa (desconectadas) ni fuentes futuras."""
    out: list[str] = []
    for conn in _REGISTRY.values():
        if not conn.implemented:
            continue
        if not conn.effective_capabilities().get(capability):
            continue
        out.append(conn.id)
    return out


def any_source_provides(capability: str) -> bool:
    return bool(sources_with(capability))


def aggregate_capabilities() -> dict[str, bool]:
    """Capacidad agregada EFECTIVA del negocio: true si ALGUNA fuente
    conectada la da ahora mismo."""
    merged: dict[str, bool] = {}
    for cap in ALL_CAPABILITIES:
        merged[cap] = any_source_provides(cap)
    return merged


def missing_capability_reason(capability: str) -> str:
    """Explica POR QUÉ no está disponible una capacidad, distinguiendo:
      * ninguna fuente la ofrece (tipo) → "ninguna fuente conectada la da"
      * la ofrece pero está desconectada → nombre de la fuente."""
    declared = [c.id for c in _REGISTRY.values() if c.implemented and c.capabilities().get(capability)]
    if not declared:
        return f"ninguna de las fuentes soportadas proporciona {CAPABILITY_LABELS.get(capability, capability).lower()}"
    connected_ids = sources_with(capability)
    if connected_ids:
        return f"proporcionada por: {', '.join(connected_ids)}"
    labels = [(_REGISTRY[d].label if d in _REGISTRY else d) for d in declared]
    return (
        f"{', '.join(labels)} puede proporcionarlo pero está desconectado"
        if len(declared) == 1
        else f"pueden proporcionarlo {', '.join(labels)} pero están desconectados"
    )


def source_summaries() -> list[dict[str, Any]]:
    """Resumen de todas las fuentes para la UI («Fuentes de datos») y Hermes."""
    out: list[dict[str, Any]] = []
    for conn in list_sources():
        st = conn.status()
        caps = conn.capabilities()
        eff = conn.effective_capabilities()
        out.append({
            "source": conn.id,
            "label": conn.label,
            "description": conn.description,
            "implemented": conn.implemented,
            "status": st.get("status", "unknown"),
            "connected": bool(st.get("connected", False) or st.get("configured", False) or st.get("ok", False)),
            "lastSync": st.get("lastSync"),
            "lastError": st.get("lastError") or st.get("error"),
            "capabilities": caps,
            "capabilityLabels": [CAPABILITY_LABELS[k] for k, v in caps.items() if v],
            "effectiveCapabilities": eff,
        })
    return out


def _load_registry() -> None:
    """Registra los conectores (import perezoso para evitar ciclos)."""
    if _REGISTRY:
        return

    from . import facturascripts_sync, integrations_store, shopify_sync

    # --- Shopify (implementado) ---
    # Capacidades DECLARADAS del tipo de conector: Shopify (ecommerce) da
    # productos/pedidos/líneas/clientes; NO da facturas ni pagos (no es ERP).
    # La conexión real se consulta por separado vía status().
    _SHOPIFY_CAPS = {
        CAP_PRODUCTS: True,
        CAP_ORDERS: True,
        CAP_ORDER_LINES: True,
        CAP_CUSTOMERS: True,
        CAP_INVENTORY: False,   # la API REST básica no expone stock fiable
        CAP_INVOICES: False,    # Shopify no es ERP: sin facturas ni pagos
        CAP_PAYMENTS: False,
        CAP_SUPPLIERS: False,
        CAP_COSTS: False,
        CAP_FINANCE: False,
        CAP_STOCK: False,
    }

    register(Connector(
        id="shopify",
        label="Shopify",
        description="Tienda online: productos, pedidos, líneas y clientes.",
        capabilities=dict(_SHOPIFY_CAPS),
        status=shopify_sync.sync_status,
        sync_now=shopify_sync.sync_now,
    ))

    # --- FacturaScripts (implementado) ---
    _FS_CAPS = {
        CAP_PRODUCTS: True,
        CAP_CUSTOMERS: True,
        CAP_SUPPLIERS: True,
        CAP_INVOICES: True,
        CAP_INVOICE_LINES: True,
        CAP_PAYMENTS: True,
        CAP_FINANCE: True,
        CAP_COSTS: True,
        CAP_ORDERS: False,      # depende de la instalación; no se asume
        CAP_INVENTORY: False,
        CAP_STOCK: False,
    }

    register(Connector(
        id="facturascript",
        label="FacturaScripts",
        description="ERP/contabilidad: facturas, líneas, cobros, pagos, proveedores y tesorería.",
        capabilities=dict(_FS_CAPS),
        status=facturascripts_sync.sync_status,
        sync_now=facturascripts_sync.sync_now,
    ))

    # --- Importación CSV/Excel (siempre disponible) ---
    def _file_caps() -> dict[str, bool]:
        return {
            CAP_PRODUCTS: True,
            CAP_ORDERS: True,
            CAP_ORDER_LINES: True,
            CAP_CUSTOMERS: True,
            CAP_INVENTORY: False,
            CAP_INVOICES: False,
            CAP_PAYMENTS: False,
            CAP_SUPPLIERS: False,
            CAP_COSTS: True,       # el importador de costes acepta filas de Excel/CSV
            CAP_FINANCE: False,
            CAP_STOCK: False,
        }

    register(Connector(
        id="fileimport",
        label="Importación CSV/Excel",
        description="Importa productos, ventas, costes y clientes desde archivos.",
        capabilities=_file_caps,
        status=lambda: {
            "source": "fileimport",
            "implemented": True,
            "status": "ok",
            "connected": True,
            "lastSync": None,
            "message": "Siempre disponible (importación manual de archivos).",
        },
    ))

    # --- Futuros (preparados, NO implementados → "Próximamente") ---
    for fut in (
        Connector(id="woocommerce", label="WooCommerce",
                  description="Tienda online WordPress: productos, pedidos, clientes e inventario.",
                  capabilities={CAP_PRODUCTS: True, CAP_ORDERS: True, CAP_ORDER_LINES: True,
                                CAP_CUSTOMERS: True, CAP_INVENTORY: True},
                  implemented=False),
        Connector(id="prestashop", label="PrestaShop",
                  description="Tienda online PrestaShop: productos, pedidos, clientes e inventario.",
                  capabilities={CAP_PRODUCTS: True, CAP_ORDERS: True, CAP_ORDER_LINES: True,
                                CAP_CUSTOMERS: True, CAP_INVENTORY: True},
                  implemented=False),
    ):
        register(fut)


_load_registry()
