"""File relevance scoring — separate business files from personal/system noise.

The scanner must be selective: it is better to import ONE clearly business file
than 1000 files where only two belong to the company. Scoring is conservative:

  - Folders with clearly non-business names are pruned (never descended into).
  - Files with personal/life markers (recipes, photos, courses, house bills...)
    are dropped immediately.
  - Strong business names (invoice, order, customer, catalog...) are confident
    on their own.
  - Weak signals become *candidates* that surface in an approval flow, so a
    human decides instead of silently polluting the data lake.
"""
from __future__ import annotations

import re
from typing import Any

# Folders we never descend into (system, media, games, dev, cache).
FOLDER_IGNORE = frozenset(
    {
        "appdata", "cache", "node_modules", "windows", "program files", "program files (x86)",
        "programdata", "perf logs", "recovery", "system volume information", "$recycle.bin",
        ".git", ".vscode", ".idea", "venv", ".venv", "site-packages", "__pycache__",
        "temp", "tmp", "thumbs", "steam", "steamapps", "epic games", "battlenet",
        "música", "music", "videos", "video", "pictures", "fotos", "foto", "imágenes",
        "imagenes", "imagen", "images", "grabaciones", "juegos", "games", "screenshots",
        "capturas", "wallpapers", "fondos", "diseño", "diseños", "plantillas", "templates",
        "descargas viejas", "old", "backup", "backups", "copia de seguridad", "copias",
        "instaladores", "installers", "portables", "programas", "software", "utilidades",
        "descargas", "downloads", "onedrive", "one drive", "googledrive", "dropbox",
    }
)

# Folder names that strongly suggest business content.
FOLDER_STRONG = frozenset(
    {
        "empresa", "negocio", "business", "trabajo", "work", "oficina", "office",
        "clientes", "customers", "proveedores", "suppliers", "ventas", "sales",
        "pedidos", "orders", "facturas", "invoices", "facturación", "billing",
        "contabilidad", "accounting", "finanzas", "finance", "bancos", "banco",
        "contable", "crm", "erp", "sap", "logística", "logistica", "logistics",
        "almacén", "almacen", "warehouse", "stock", "inventario", "inventory",
        "productos", "products", "catálogo", "catalogo", "catalog", "precios",
        "pricing", "tarifas", "rates", "marketing", "campañas", "campaigns",
        "informes", "reportes", "reports", "reporting", "exportaciones", "importaciones",
        "rrhh", "recursos humanos", "nóminas", "nominas", "payroll", "impuestos",
        "taxes", "fiscal", "auditoría", "auditoria", "audit", "proyectos", "projects",
        "presupuestos", "budgets", "albaranes", "albaranes de entrega", "envíos", "envios",
        "shipping", "hermes", "maios", "datos", "data", "analytics", "kpi", "dashboards",
        "cuentas", "accounts", "gastos", "expenses", "cobros", "pagos", "payments",
        "compras", "purchases", "licencias", "licenses", "suscripciones", "subscriptions",
        "comercial", "producción", "produccion", "operaciones", "compras y ventas",
        "exportar", "importar", "informes de ventas", "informe de ventas",
    }
)

# Folder names with a weaker business signal (candidate-level).
FOLDER_WEAK = frozenset(
    {
        "documentos", "documents", "archivos", "files", "docs", "miscelánea", "miscelanea",
        "otros", "administración", "administracion", "gestion", "gestión", "planillas",
        "planillas de calculo", "hojas de calculo", "excels", "tablas", "registros",
        "notas", "apuntes de trabajo", "reuniones", "meetings", "agenda", "calendario",
    }
)

# Strong filename signals — a file with one of these is very likely business.
FILE_STRONG = frozenset(
    {
        "factura", "invoice", "facturas", "pedido", "pedidos", "order", "orders",
        "venta", "ventas", "sale", "sales", "cliente", "clientes", "customer",
        "customers", "proveedor", "proveedores", "supplier", "suppliers",
        "catálogo", "catalogo", "catalog", "producto", "productos", "product",
        "products", "precio", "precios", "price", "pricing", "tarifa", "tarifas",
        "sku", "stock", "inventario", "inventory", "nómina", "nomina", "nóminas",
        "nominas", "payroll", "contabilidad", "accounting", "balance", "bancos",
        "banco", "bank", "extracto", "statement", "presupuesto", "presupuestos",
        "budget", "budgets", "albarán", "albaran", "albaranes", "delivery note",
        "impuesto", "impuestos", "tax", "taxes", "iva", "crm", "listado", "listados",
        "contrato", "contract", "licencia", "licencias", "license", "licenses",
        "inventario de stock", "pedido de compra", "orden de compra", "purchase order",
        "nota de entrega", "guía de remisión", "guia de remision", "reporte de ventas",
        "informe de ventas", "balance general", "cuenta de resultados", "profit",
        "ganancias", "margen", "margin", "rentabilidad", "inversion", "inversión",
        "patrimonio", "proveedores", "remesa", "remesas", "anticipo", "facturación",
        "facturacion", "albaranes de cliente", "gastos de empresa",
    }
)

# Weaker filename signals — candidate-level unless content confirms.
FILE_WEAK = frozenset(
    {
        "informe", "report", "informes", "reportes", "datos", "data", "export",
        "import", "list", "lista", "listado", "analisis", "análisis", "analysis",
        "proyecto", "proyectos", "project", "campaña", "campañas", "campaign",
        "marketing", "gastos", "expenses", "compras", "purchases", "pagos", "payments",
        "cobros", "ingresos", "revenue", "resumen", "summary", "registro", "registros",
        "planilla", "planillas", "excel", "tabla", "tablas", "hoja", "hojas", "csv",
        "detalle", "detalles", "historial", "log", "logs", "bitácora", "bitacora",
        "movimientos", "transacciones", "transactions", "extracto bancario",
        "presupuesto familiar", "cuadre", "conciliación", "conciliacion", "reconciliación",
        "estadística", "estadisticas", "stats", "indicadores", "kpis", "seguimiento",
        "tracking", "cronograma", "planning", "agenda", "reunión", "reunion", "meeting",
        "cliente potencial", "lead", "leads", "oportunidad", "oportunidades", "quote",
        "cotización", "cotizacion", "estimación", "estimacion", "forecast", "predicción",
        "prediccion", "previsión", "prevision", "demanda", "abastecimiento", "reposición",
        "reposicion", "despacho", "despachos", "entrega", "entregas", "rutas", "rutas de reparto",
    }
)

# Personal/life markers — a file with any of these is dropped immediately.
NEGATIVE_HINTS = frozenset(
    {
        "casa", "hogar", "personal", "privado", "privada", "familia", "familiar",
        "receta", "recetas", "cocina", "comida", "menú", "menu", "viaje", "viajes",
        "vacaciones", "cumpleaños", "cumpleanos", "boda", "fiesta", "invitación",
        "invitacion", "apuntes", "curso", "cursos", "clase", "clases", "universidad",
        "instituto", "colegio", "tarea", "deberes", "juego", "juegos", "foto", "fotos",
        "fotografía", "fotografia", "imagen", "imágenes", "imagenes", "música", "musica",
        "película", "pelicula", "serie", "series", "libro", "libros", "novela", "novelas",
        "rutina", "ejercicio", "gimnasio", "salud", "médico", "medico", "doctor",
        "dieta", "peso", "calorías", "calorias", "entrenamiento", "yoga", "meditación",
        "meditacion", "diario", "diario personal", "cartas", "carta personal", "amigos",
        "amistades", "horóscopo", "horoscopo", "química", "quimica", "física", "fisica",
        "matemáticas", "matematicas", "examen", "exámenes", "trabajo de clase", "tesis",
        "tfgs", "tfms", "freelance personal", "mascota", "mascotas", "perro", "gato",
        "hobby", "aficiones", "manualidades", "dibujos", "pinturas", "canciones",
    }
)

# Header/content signals — a file containing several of these is business data.
# Application artifacts must never enter the business data lake. This is
# deliberately path/name based: old MAIOS/VANOVA config and web bundles can
# contain words such as "sales", "customers" and "revenue" while being
# application state, not company data.
LEGACY_APP_FILENAMES = frozenset({
    "maios.json",
    "maios-config.json",
    "vanova.json",
    "dashboard.html",
    "index.html",
    "data-services.js",
})
LEGACY_APP_MARKERS = (
    "/maios/config/",
    "\\maios\\config\\",
    "/maios/web/",
    "\\maios\\web\\",
    "/maios/desktop/",
    "\\maios\\desktop\\",
    "/maios/release/",
    "\\maios\\release\\",
    "/maios-final-suite/",
    "\\maios-final-suite\\",
    "/maios-full-suite/",
    "\\maios-full-suite\\",
    "/release/build-tmp/",
    "\\release\\build-tmp\\",
    "/release/build-",
    "\\release\\build-",
)


def legacy_app_artifact(entry: dict[str, Any] | str) -> str | None:
    """Return a reason when *entry* is an old app artifact, otherwise None."""
    if isinstance(entry, dict):
        name = str(entry.get("name") or "")
        path = str(entry.get("path") or "")
        source = str(entry.get("source") or "")
    else:
        name = str(entry)
        path = str(entry)
        source = ""
    lower_name = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
    lower_path = path.replace("\\", "/").lower()
    lower_source = source.lower()
    if lower_name in LEGACY_APP_FILENAMES:
        return "archivo interno de VANOVA/MAIOS"
    if any(marker in lower_path for marker in LEGACY_APP_MARKERS):
        return "ruta interna de una copia histórica de VANOVA/MAIOS"
    if lower_source in {"maios", "vanova", "legacy_dashboard", "app_internal"}:
        return "origen interno de VANOVA/MAIOS"
    return None


CONTENT_BUSINESS = frozenset(
    {
        "sku", "producto", "product", "precio", "price", "net", "rrp", "pvp", "ean",
        "barcode", "cliente", "customer", "venta", "sale", "pedido", "order", "invoice",
        "factura", "total", "amount", "importe", "fecha", "date", "nif", "cif", "vat",
        "proveedor", "supplier", "cantidad", "quantity", "qty", "unidades", "units",
        "ref", "referencia", "reference", "descripcion", "description", "estado",
        "status", "iva", "tax", "pago", "payment", "direccion", "address", "telefono",
        "phone", "email", "categoria", "category", "beneficio", "profit", "margen",
        "margin", "revenue", "ingreso", "ingresos", "valor", "value", "stock",
        "inventory", "empleado", "employee", "sueldo", "salary", "pedidos", "orders",
        "clientes", "customers", "albaran", "albarán", "delivery", "shipping",
        "remesa", "iban", "cuenta", "account", "subtotal", "descuento", "discount",
        "unidad", "unit", "kg", "litro", "litros", "caja", "cajas", "paquete", "palet",
    }
)

_NUMBER_TOKENS_RE = re.compile(r"(?<![A-Za-z])[0-9]+(?:[.,][0-9]+)?")
_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")


def _count_hits(text: str, hints: frozenset[str]) -> int:
    lower = text.lower()
    return sum(1 for h in hints if h in lower)


def score_folder(name: str) -> int:
    """Return a folder relevance score. Negative => prune this subtree."""
    n = (name or "").lower()
    if any(ig in n for ig in FOLDER_IGNORE):
        return -2
    strong = min(2, _count_hits(n, FOLDER_STRONG))
    weak = min(2, _count_hits(n, FOLDER_WEAK))
    return strong * 2 + weak


def score_file(name: str) -> int:
    """Return a file relevance score from its name. Negative => drop."""
    n = (name or "").lower()
    if any(h in n for h in NEGATIVE_HINTS):
        return -3
    strong = min(2, _count_hits(n, FILE_STRONG)) * 3
    weak = min(2, _count_hits(n, FILE_WEAK))
    return strong + weak


def score_content(text: str) -> int:
    """Return a content relevance score (0..4) from a text snippet."""
    if not text:
        return 0
    lower = text.lower()[:20000]
    hits = min(3, _count_hits(lower, CONTENT_BUSINESS))
    # Numeric density: real business tables have many numbers and/or dates.
    numbers = len(_NUMBER_TOKENS_RE.findall(lower[:8000]))
    density = 1 if numbers >= 4 or _DATE_RE.search(lower) else 0
    return min(4, hits + density)


def classify_scan_record(entry: dict[str, Any]) -> str:
    if legacy_app_artifact(entry):
        return "skip"
    """Return 'confident' | 'candidate' | 'skip' for a scanned file record."""
    name = entry.get("name") or entry.get("path") or ""
    folder_score = int(entry.get("folderScore") or 0)
    file_score = int(entry.get("fileScore") or 0)
    content_score = int(entry.get("contentScore") or 0)
    total = folder_score + file_score + content_score
    if file_score >= 3 or total >= 4:
        return "confident"
    if total >= 2:
        return "candidate"
    return "skip"
