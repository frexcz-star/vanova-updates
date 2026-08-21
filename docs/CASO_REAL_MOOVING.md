# CASO REAL — MOOVING PAPER

**Fecha:** 2026-08-20
**Estado:** Datos reales de MOOVING PAPER NO disponibles en el sistema — documento honesto de diagnóstico, sin inventar nada.

---

## 1. Qué datos reales de MOOVING existen hoy

Tras un barrido completo del sistema, **no hay datos reales de negocio de MOOVING PAPER** en el entorno:

- **No hay** archivos de ventas, pedidos, clientes, productos, facturas o márgenes de MOOVING (ningún `.xlsx`, `.csv`, `.xls` etiquetado como MOOVING).
- El `Cuestionario Mooving Paper.odt` existe pero **está sin responder** (template vacío).
- El prototipo `maios-mooving-prototype/` contiene specs de diseño/backend, no datos.
- El config actual del runtime tiene cargada la **demo mock** (`dataMode=mock`, 766 ventas sintéticas de `mock_dataset.json`) — NO son datos de MOOVING.
- Los datasets de `benchmark-data/` y `benchmark-sandbox/real-company/` son **sintéticos de prueba**, no de MOOVING.

**Conclusión honesta:** no hay datos reales de MOOVING para que el Detector de Oportunidades los analice.

---

## 2. Por qué no hay oportunidades reales (honestidad)

Con los datos disponibles (demo mock o benchmarks sintéticos), VANOVA no puede demostrar oportunidades reales de MOOVING porque:

1. **No hay datos reales** → cualquier € mostrado sería inventado o de otra empresa. Eso viola la regla de honestidad (`UNKNOWN ≠ 0`).
2. El detalle está en el BUG_TRACKER: con datos reales de tiendas pequeñas (p.ej. BlisArtPaper, 101 pedidos, sin costes) el motor **no fabrica oportunidades** — respeta los umbrales de evidencia.

---

## 3. Qué necesita el padre (Pablo) para que VANOVA genere valor real

Para que VANOVA analice MOOVING de verdad y le muestre al padre oportunidades en €, hace falta que Pablo aporte **datos reales mínimos**:

| Dato | Formato | Por qué es necesario |
|---|---|---|
| **Ventas / pedidos** (últimos 6-12 meses) | Excel/CSV: fecha, cliente, producto, cantidad, total | Base para cross-sell, AOV, concentración de cliente |
| **Catálogo de productos** | Excel/CSV: sku, nombre, precio venta | Identifica productos y su peso en revenue |
| **Costes por producto** | Columna "coste" en el catálogo | Desbloquea el **€ de margen** (upside real) — sin coste no se cuantifica |
| **Clientes** (opcional pero valioso) | Excel/CSV: nombre, historial | Detección de clientes dormidos/reactivables |

> Con solo **ventas + catálogo + costes por SKU**, VANOVA ya puede detectar: cross-selling (€), concentración de producto/cliente (riesgo en €), ticket medio a la baja (gap en €), productos de alto margen infra-promocionados.

---

## 4. Estado de la fuente en VANOVA
- La fuente que está conectada hoy es **BlisArtPaper** (Shopify, del usuario) — no MOOVING.
- El config tiene la **demo mock** cargada (etiquetada como tal, nunca presentada como real).
- Para conectar MOOVING real: importar los archivos de ventas/productos/costes del padre como nueva fuente, y re-ejecutar el detector.

---

## 5. Próximo paso propuesto
1. Pablo exporta sus datos (ventas + catálogo + costes) en Excel/CSV.
2. Se importan en VANOVA como fuente "MOOVING PAPER" (no como mock).
3. El detector genera las oportunidades reales en € y este documento se actualiza con los resultados reales.

_Generado sin inventar datos. Si no hay datos de MOOVING, se dice con claridad y se propone qué se necesita._
