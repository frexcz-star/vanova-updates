# STRATI — Checklist de Importación de Datos Reales de MOOVING (para Pablo)

**Autor:** Strati (estrategia/producto) · **Para:** Pablo (fuente de datos) + Nickx (ingest) + Mathew (QA) + Boss (decisión)
**Fecha:** 2026-08-22 · **Regla inquebrantable:** datos reales de MOOVING, NUNCA mock como real. Si un dato falta, se deja vacío honesto, no se inventa.

---

## Objetivo

Que el export de datos de MOOVING que entregue Pablo cargue en VANOVA **sin fricción** y desbloquee el **€ real del aha** en la demo del cliente: ventas → margen → upside en €. Esto cierra el bloqueo confirmado (0/414 productos con coste en el catálogo).

---

## 1. Checklist de importación — QUÉ pedirle a Pablo (2 archivos)

### Archivo A — Catálogo de productos con coste por SKU (Obligatorio)

| Columna | Ejemplo | Obligatorio | Formato |
|---|---|---|---|
| `sku` | `2112100208` | Sí | texto; debe coincidir con el SKU del catálogo ya cargado (414 productos) |
| `ean` | `7799133019074` | No (si falta, se usa el `sku`) | texto, 13 dígitos |
| `name` | `MAW Mania - Narrow Page Flags...` | No (ya lo tiene el catálogo) | texto |
| `netPrice` | `2,15` | Sí | número, separador coma ES o punto |
| `cost_price` | `1,10` | **SÍ — es la que desbloquea el €** | número con decimales |
| `rrp` | `3,50` | No (si falta, se usa netPrice) | número |
| `stock` | `120` | Opcional | entero |

> **La columna `cost_price` es la crítica.** Sin ella, el margen (`netPrice − cost_price`) y el upside en € no se pueden calcular. Formato idéntico al CSV `synthetic-data/NOVA-HOME-TECH-productos.csv` que ya usa el repo.

### Archivo B — Ventas / pedidos (últimos 6-12 meses)

| Columna | Ejemplo | Obligatorio | Formato |
|---|---|---|---|
| `fecha` | `2026-03-14` | Sí | fecha ISO (YYYY-MM-DD) |
| `cliente` | `Papeleria Central` | Sí | texto |
| `sku_producto` | `MO2100208` | Sí | coincide con el catálogo (case-insensitive) |
| `cantidad` | `4` | Sí | entero |
| `total` | `8,60` | Sí | número, € sin IVA (o con IVA — se indica) |
| `coste_linea` | `4,40` | Opcional | si no viene, se cruza con el coste del catálogo |

### Archivo B — Ventas / margen mensual AGREGADO (para el dashboard `overview`)

Este bloque alimenta **directamente** `overview.revenue` y `overview.grossMargin` del snapshot `dashboard` — es la pieza que hace aparecer el € del aha en el dashboard (hoy `revenue=null, grossMargin=null` en vivo). Si Pablo no quiere dar el detalle línea a línea, basta con este resumen mensual:

| Columna | Ejemplo | Obligatorio | Formato |
|---|---|---|---|
| `mes` | `2026-03` | Sí | YYYY-MM |
| `revenue_ventas` | `8.420,00` | Sí | número, € (sin IVA o con — se indica) |
| `margen_bruto` | `3.100,00` | Sí | número, € = revenue − coste real (o `%` si prefiere: `31`) |
| `pedidos` | `85` | No (opcional) | entero |
| `clientes` | `37` | No (opcional) | entero |

> **Por qué importa:** el `/api/dashboard` solo muestra € reales si el snapshot `dashboard` tiene `overview.revenue/grossMargin` poblados desde una fuente real (nunca mock). Este bloque mensual es lo que desbloquea el `dataMode=real` con € en el dashboard. Sin él, el aha queda vacío aunque el catálogo tenga coste.

---

## 2. Formato de archivo

- **Excel (.xlsx)** o **CSV UTF-8** (delimitador `;` o `,`), primera fila = cabecera.
- Máximo 10.000 filas (límite seguro para un catálogo de papelería).
- Si Pablo exporta desde su ERP/FacturaScripts, buscar: `articulos` → `referencia`, `nombre`, `preciocoste`, `precioventa` (BUG-033). Si exporta desde Excel de Carrefour, añadir la columna `cost_price`.

---

## 3. Quién hace qué (cadena del dato)

| Paso | Quién | Qué |
|---|---|---|
| 1 | **Pablo** | Exporta el catálogo con `cost_price` + las ventas de 6-12 meses en Excel/CSV |
| 2 | **Nickx** | Amplía `ingest_catalog.py` para leer `cost_price` por SKU (hoy solo lee `sku/ean/name/netPrice/rrp`) |
| 3 | **Nickx** | Regenera el snapshot `products` a `cloud/maios_cloud.db` con `costStatus=verified` (nunca mock) |
| 4 | **Nickx** | Importa las ventas como fuente real "MOOVING PAPER" (no mock) |
| 5 | **Mathew** | Verifica: `/api/products` con >0% `costStatus=verified`, `/api/dashboard` `dataMode=real` con overview y € |
| 6 | **Boss** | Veredicto de cierre: demo aprobada solo con login + dataMode real + >0% coste verificado |

---

## 4. Criterio de cierre (no negociable)

**La demo está aprobada SOLO cuando:**
1. El login demo entra con las credenciales definitivas.
2. `/api/dashboard` responde `dataMode=real` con `overview` y €.
3. `>0%` de los productos tienen `costStatus=verified`.

Sin esos tres, no hay pitch. El € del aha sale de **coste real por SKU**, nunca de mock.

---

*Checklist generada por Strati. Lista para dar a Pablo y despachar a Nickx para el ingest.*
