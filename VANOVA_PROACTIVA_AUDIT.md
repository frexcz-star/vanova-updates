# VANOVA PROACTIVA — Auditoría y Corrección (Producto Real)

Fecha: 2026-08-19 · Sin release · Benchmark congelado intacto · Producción intacta

## 1. Metodología

No fue una pasada de tests: inspección del código real, reproducción con los
datos reales de producción (461 productos / 100 ventas, importados desde
Shopify), ejecución del flujo completo y corrección de lo que estaba roto.

## 2. Bugs reales encontrados

### BUG 1 — `company_model` no leía `line_items` (datos de tienda real)
- **Causa**: `_product_aggregates` y `_trend` solo miraban `sale.sku` /
  `sale.product_sku` a nivel de pedido. Los datos reales de Shopify traen el
  SKU **únicamente dentro de `line_items`** (116 SKUs distintos en 100 pedidos).
- **Efecto**: el modelo de empresa decía `productBasis: "catalog-only"`,
  `topProducts: 0`, `growing: 0`, `declining: 0`, `concentration.products`
  vacío, `summary.customers: 0` (los 88 clientes reales de las ventas no se
  contaban). El "modelo de la empresa" era inútil con la forma de datos real.
- **Fix**: `_line_sku_total()` + uso de `business_model.normalize_sale_lines()`
  en agregación y tendencias; `summary.customers` usa la concentración real por
  cliente de las ventas; `dataMissing` ya no afirma falsamente "ventas sin SKU".
- **Test**: `CompanyModelLineItemsTests` (3 casos).

### BUG 2 — El análisis NO se ejecutaba tras la importación
- **Causa**: `organize_files()` refrescaba el modelo de empresa pero **no
  ejecutaba el detection engine**. En producción: `businessFindings: 0` con
  `detectionRunAt` anterior a la última importación. El usuario tenía que
  pulsar manualmente "Actualizar análisis".
- **Efecto**: VANOVA no era proactiva: importar datos no producía hallazgos ni
  insights. El Home mostraba "Sin hallazgos activos" con datos reales.
- **Fix**: `organize_files()` ejecuta ahora modelo + detección + sincronización
  de insights tras cada importación (con `data` en memoria, ver BUG 4). El
  endpoint `POST /api/business/analyze` también sincroniza insights.
- **Test**: `OrganizeRunsProactiveAnalysisTests` + `test_organize_refreshes_company_model`.

### BUG 3 — No existía puente findings → insights de usuario
- **Causa**: `insight_store` solo recibía "informes de rutina" de agentes
  (texto genérico). Los hallazgos del motor determinista (con evidencia) nunca
  llegaban al feed de insights ni al badge.
- **Efecto**: el usuario solo veía "Informe de rutina: X Agent", no hallazgos
  de negocio con evidencia.
- **Fix**: nueva `insight_store.sync_from_findings()` — cada finding activo se
  convierte en un insight `kind="finding"` con: título, observación, evidencia,
  acción recomendada, severidad, categoría, impacto €, confianza, entidad.
  Dedup por firma (el mismo hallazgo nunca genera copias), lifecycle
  `new → resolved → new` (reaparece con nueva evidencia), y `createdAt` estable
  para no reactivar el badge en cada reanálisis.
- **Test**: `FindingsToInsightsTests` (5 casos).

### BUG 4 — Aislamiento de la suite de tests (escrituras en producción)
- **Causa**: durante el desarrollo, `organize_files` con `run_detection()`
  persistente releía el config real (LOCALAPPDATA) en vez del store de tests.
- **Efecto**: la suite podía escribir `businessFindings`/`insights`/
  `companyModel` en el config de producción. Detectado y corregido durante esta
  auditoría (producción restaurada byte a byte y verificada tras la suite).
- **Fix**: el análisis post-import usa el dict `data` en memoria del propio
  organize y persiste vía su `config_store` (el que los tests parchean);
  `sync_from_findings(..., data=...)` acepta store inyectado.
- **Verificación**: snapshot de producción antes/después de la suite completa →
  idéntico.

## 3. Flujo E2E real ejecutado (datos de producción, sandbox aislado)

```
DATOS REALES (461 productos, 100 ventas Shopify)
  → company_model.build_company_model   (0.00 s)
  → detection_engine.run_detection      (0.05 s)
  → insight_store.sync_from_findings    (0.00 s)
  → command_center / Home               (proactiveInsights + revenuePeriods)
  → badge de notificaciones             (6 hallazgos nuevos sin leer)
```

**Modelo de empresa (ahora real):** revenue 3.187,64 € · 100 pedidos ·
ticket medio 31,88 € · 461 productos · 88 clientes · top 10 productos por
revenue · concentración: el SKU 51758206910795 = 26,4 % de las ventas ·
productBasis `sales-with-sku`.

**Hallazgos del motor (evidencia real):**
- 47 productos sin coste verificable (HIGH) — evidencia: registro preservado,
  no borrado; acción: cargar coste real antes de usar el margen.
- 5 pedidos con total incoherente (#1082, #1081, #1012, #1090, #1098) —
  evidencia: "Total 22,94 € vs líneas 16,44 €"; acción: revisar en el origen.

**Insights generados (con evidencia y acción):** 6 nuevos, todos con
`summary` + `meta.evidence` + `meta.recommendedAction` — sin texto genérico.

**UNKNOWN ≠ 0 verificado:** sin finding → sin insight; sin datos → `None`,
nunca 0 €; `dataMissing` declara honestamente lo que falta (stock, facturas,
proveedores).

## 4. Cambios realizados

| Archivo | Cambio |
|---|---|
| `desktop/runtime/company_model.py` | Lee `line_items`; customers reales; dataMissing honesto |
| `desktop/runtime/insight_store.py` | `sync_from_findings()` (dedup + lifecycle + store inyectado); `record(refresh_created=)` |
| `desktop/runtime/file_organizer.py` | Análisis proactivo automático post-import, aislado |
| `desktop/runtime/api_server.py` | `/api/business/analyze` sincroniza insights |
| `web/dashboard.html` / `index.html` / `web/dist/*` | Insights de detección con evidencia en Home e Insights; badge solo con hallazgos nuevos (no rutinas) |
| `tests/test_proactive_310.py` | +7 tests (line_items, sync, dedup, lifecycle, sin-evidencia, organize) |

## 5. Tests

- **Suite completa**: 601 passed, 1 skipped, 31 subtests, 0 fallos.
- Nuevos: 7 (3 company_model + 5 insights + 1 organize → 15 en el archivo, 8 ya existían).
- Producción verificada idéntica antes/después de la suite.
- Benchmark congelado intacto (GROUND_TRUTH `c09d47ac…`).

## 6. Qué puede hacer ahora VANOVA de forma autónoma

- Tras importar datos, construye el modelo de empresa (qué vende, cómo vende,
  qué funciona, qué falta) automáticamente.
- Ejecuta el motor determinista y convierte los hallazgos con evidencia en
  insights de usuario con acción recomendada.
- Deduplica por firma: el mismo hallazgo nunca genera spam; si se resuelve se
  marca `resolved` y si reaparece vuelve a `new`.
- El Home muestra ingresos por periodo (motor canónico), hallazgos del motor y
  insights con evidencia; el badge solo refleja hallazgos nuevos reales.

## 7. Qué NO puede hacer todavía (honesto)

- **Oportunidades (cross-sell, pricing, crecimiento)**: en los datos reales el
  motor no encuentra ninguna con los umbrales actuales (evidencia insuficiente:
  29 pedidos multi-SKU, sin pares ≥ 15 %). Es UNKNOWN, no 0 — correcto.
- **FacturaScripts**: el conector está testeado con clientes falsos, pero no
  hay servidor real disponible en este entorno → NO VALIDADO end-to-end.
- **Latencia de Hermes**: el pipeline de fases existe; el tiempo real depende
  del proveedor configurado (medible con `timings`).
- **Stock/proveedores/tesorería**: los datos reales no los traen; el motor lo
  declara en `dataMissing` en vez de inventarlo.

## 8. Pendiente honesto

- Latencia de Hermes en equipo del cliente.
- FacturaScripts con servidor real.
- Explorar oportunidades con umbrales basados en señal (sin bajar thresholds a ciegas).
