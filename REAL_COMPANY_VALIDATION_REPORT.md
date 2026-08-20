# REAL COMPANY VALIDATION REPORT

**Fecha:** 2026-08-17 · **Entorno:** sandbox aislado (`benchmark-sandbox/real-company`) · **Instalación de producción: NO tocada**

---

## 1. QUÉ SE PROBÓ

| Paso | Mecanismo | Resultado |
|---|---|---|
| 1. Sandbox aislado | Copia del backup real de producción (`release/synthetic-backups/VANOVA-REAL-BEFORE-SYNTHETIC`) | ✅ Aislado, sin conexión a producción |
| 2. Importación con mecanismos normales | `organize_files()` con `productos.xlsx` + `ventas.csv` (archivos fuente generados desde los datos canónicos reales) | ✅ 461 productos (414 con coste) / 99 ventas |
| 3. Importación repetida (idempotencia) | Mismo import 2 veces | ✅ 461/99 ambas veces — sin duplicados, sin pérdidas |
| 4. Motor de detección | `run_detection()` persistido | ✅ 6 findings, firmas estables entre runs |
| 5. Dashboard (payload API) | `list_findings()` | ✅ healthScores + executiveBrief + actionPlan presentes |
| 6. Hermes | 4 preguntas empresariales reales (harness del benchmark) | ✅ HECHO/INFERENCIA/NO DISPONIBLE, sin leaks, cifras reales |
| 7. Rendimiento | Timing del pipeline | ✅ motor ~43 ms, contexto 285 ms |
| 8. Logs / secretos | Escaneo de logs del sandbox | ✅ 0 errores, sin credenciales expuestas |

---

## 2. DATOS REALES: ANTES → IMPORTADO

| Métrica | Real (producción/backup) | Importado (sandbox) | ¿Coincide? |
|---|---|---|---|
| Productos | 461 | 461 | ✅ |
| Productos con coste | 414 | 414 | ✅ |
| Ventas/pedidos | 99 | 99 | ✅ |
| Revenue | 3.119,12 € (99 pedidos) | 3.119,12 € (99 pedidos) | ✅ |
| Identidad de producto | 75,2 % (187 líneas match / 49 sin) | 75,2 % | ✅ |
| Cobertura de costes (por producto) | 89,8 % (414/461) | 89,8 % | ✅ |
| Cobertura de costes (por revenue) | 41,6 % (1.254,74 € de 3.016,43 €) | 41,6 % | ✅ |
| Clientes | 87 (derivados de ventas; 0 registros dedicados) | 87 | ✅ |
| Inventario / stock | Sin fuente conectada → UNKNOWN | UNKNOWN | ✅ (honesto) |
| Proveedores / facturas / tesorería | Sin fuente conectada → UNKNOWN | UNKNOWN | ✅ (honesto) |

**Conclusión de datos:** el pipeline de importación normal preserva el 100 % de los datos de negocio y de gobernanza. No se pierde ni se duplica nada en importaciones repetidas.

---

## 3. FINDINGS DEL MOTOR (6)

| Tipo | Severidad | Entidad | Evidencia | Impacto € | Acción |
|---|---|---|---|---|---|
| `missing_cost` | high | 47 productos | 47 con costStatus=missing; coste==PVD sin evidencia no cuenta | — (UNKNOWN, no 0) | Cargar coste real antes de decidir por margen |
| `inconsistent_order_total` | medium | #1082 | total 29,60 € vs líneas 37,00 € | — | Revisar en el sistema de origen |
| `inconsistent_order_total` | medium | #1081 | total 43,60 € vs líneas 51,00 € | — | Revisar en el sistema de origen |
| `inconsistent_order_total` | medium | #1012 | total 17,67 € vs líneas 11,17 € | — | Revisar en el sistema de origen |
| `inconsistent_order_total` | medium | #1090 | total 11,30 € vs líneas 4,80 € | — | Revisar en el sistema de origen |
| `inconsistent_order_total` | medium | #1098 | total 22,94 € vs líneas 16,44 € | — | Revisar en el sistema de origen |

**Firmas estables:** 2 ejecuciones consecutivas del motor → las 6 firmas y estados son idénticos (dedupe correcto, sin duplicados entre runs).

---

## 4. HALLAZGOS DE LA VALIDACIÓN (problemas encontrados)

### B1. `moneyAtRisk` devolvía 0,0 € cuando no había impacto cuantificado — **BUG (UNKNOWN ≠ 0)**
- **Dónde:** `executive_brief()` en `desktop/runtime/detection_engine.py` — `sum(_impact_euro(f) or 0.0 …)`.
- **Síntoma:** con 6 findings sin importe € cuantificado, el brief decía "dinero en riesgo: 0,00 €" — es decir, **confundía UNKNOWN con 0**.
- **Corrección:** solo se suma lo cuantificado; si no hay ningún importe, `moneyAtRisk` y `opportunityPotential` son `None` (desconocido), no 0.
- **Verificado:** `moneyAtRisk: None` con los datos reales. Test: `test_executive_brief_money_at_risk_none_when_unquantified`.

### B2. `inconsistent_order_total` mostraba los 5 primeros desvíos en orden de lista — **BUG de priorización (riesgo de FP/FN)**
- **Dónde:** `detect_data_quality()` — `mismatches[:5]` sin ordenar.
- **Síntoma:** en los datos reales hay 33/99 pedidos con total ≠ líneas; el tope 5 mostraba solo desvíos de +5,0/+6,5 € (patrón consistente con envío), mientras que los desvíos negativos más graves (líneas > total, p. ej. #1082: 37,00 vs 29,60) quedaban ocultos.
- **Corrección:** ordenar por magnitud de desvío antes del tope → los casos más graves salen primero (verificado: #1082, #1081, #1012 ahora lideran).
- **Test:** `test_inconsistent_order_total_prioritizes_largest_delta`.

### B3. Observación del finding "total incoherente" sin matiz — **UX/COMPORTAMIENTO**
- El texto decía solo "Los importes no cuadran" → el empresario podría interpretar que es fraude/error, cuando el desvío puede ser envío/impuestos/descuentos no desglosados (los datos reales de Shopify no desglosan envío).
- **Corrección:** se añade el matiz honesto al finding: "El desvío puede corresponder a envío/impuestos/descuentos no desglosados en las líneas." (sin cambiar umbrales).

### B4. Cobertura de costes con dos bases distintas (89,8 % producto vs 41,6 % revenue) — **UX / claridad**
- `costCoverage` (por producto) y `revenueWithVerifiedCost` (por revenue) coexisten. Ambas son correctas pero el usuario puede confundirlas.
- **Clasificación:** no es bug; ambas métricas se exponen con nombres distintos. Recomendación: la UI debe etiquetar la base ("de productos" vs "del revenue").

### B5. Hermes citó "0/575 con stock" — **LIMITACIÓN DE DATOS (no bug)**
- 575 ≠ 461 productos: la cifra viene de un conteo de filas/almacenes con stock ausente. Hermes lo explicó correctamente ("no es un dato real de inventario: es ausencia del campo de stock"). El motor marca `inventario: UNKNOWN` — honesto.

### B6. Clientes 87 vs 0 registros `organizedCustomers` — **LIMITACIÓN DE DATOS (no bug)**
- La instalación real no tiene archivo de clientes: los 87 se derivan de las ventas. Hermes lo presentó correctamente ("87, ninguno con email registrado").

---

## 5. HERMES (4 preguntas reales)

| Pregunta | Estado | Latencia | Veredicto |
|---|---|---|---|
| ¿Cómo está mi empresa? | completed | 18,0 s | 🟢 Correcta y honesta: 99 pedidos, 3.119,12 €, 41,6 % coste por revenue, 75,2 % identidad, "margen no calculable de forma fiable" |
| ¿Cuál es mi mayor problema y cuánto dinero está en riesgo? | completed | 20,0 s | 🟢 Excelente: HECHO/INFERENCIA/NO DISPONIBLE; "NO es 0 €: es no se puede determinar" — **UNKNOWN ≠ 0 respetado** |
| ¿Qué debería hacer hoy? | completed | 14,0 s | 🟢 Correcta: prioriza cerrar brecha de datos (conectar FacturaScripts, completar costes, 62 entidades a revisar) |
| ¿Tengo problemas de stock o dependencia de proveedores? | completed | 20,0 s | 🟢 Honesta: NO DISPONIBLE para ambos, sin inventar; distingue hecho/inferencia |

- **HECHO / INFERENCIA / NO DISPONIBLE:** ✅ usado consistentemente.
- **Prompt leak:** ✅ ninguno (respuestas de análisis empresarial normal).
- **Cifras:** ✅ coinciden con los datos reales verificados por el motor (99 pedidos, 3.119,12 €, 41,6 %, 75,2 %, 62 entidades a revisión del conteo de gobernanza).
- **Uso de findings del motor:** ✅ (missing_cost, identidad, 62 needs_review).

---

## 6. RENDIMIENTO Y ERRORES

| Operación | Tiempo |
|---|---|
| Carga de config | 6 ms |
| Business signals | 8 ms |
| Detección completa (con data quality) | 43 ms |
| Contexto de Hermes (bloque completo) | 285 ms |
| Hermes (LLM cloud, 4 preguntas) | 14–20 s (dominado por el modelo, por diseño) |

- Logs del sandbox: **0 errores**, sin excepciones.
- Escaneo de secretos en logs: sin API keys/passwords/tokens (solo mención de instalaciónId truncado).

---

## 7. CLASIFICACIÓN DE PROBLEMAS

| # | Problema | Clasificación | Estado |
|---|---|---|---|
| B1 | moneyAtRisk 0,0 € con impacto desconocido | **BUG (UNKNOWN ≠ 0)** | ✅ Corregido + test |
| B2 | Desvíos mostrados sin priorizar (riesgo FP/FN) | **BUG de priorización** | ✅ Corregido + test |
| B3 | Finding sin matiz de envío/impuestos | **UX** | ✅ Corregido |
| B4 | Dos bases de cobertura de costes | UX / claridad | 📝 Recomendación UI |
| B5 | Stock "0/575" vs 461 productos | LIMITACIÓN DE DATOS | ✅ Hermes lo explica honestamente |
| B6 | Clientes derivados de ventas (0 dedicados) | LIMITACIÓN DE DATOS | ✅ Comportamiento esperado |
| — | Sin facturas/tesorería/proveedores/inventario conectados | LIMITACIÓN DE DATOS | ✅ UNKNOWN honesto (no 0) |
| — | Falsos positivos del motor | — | **0 FP obvios** (6 findings todos con evidencia real) |
| — | Falsos negativos | — | Solo los de datos ausentes (UNKNOWN, no FN) |

---

## 8. TESTS Y BENCHMARK

- **Suite completa:** 501 passed, 1 skipped (+2 tests nuevos de validación real: `money_at_risk_none_when_unquantified`, `inconsistent_order_total_prioritizes_largest_delta`).
- **Benchmark congelado intacto:** 72 % estricto / 96 % con parciales / 0 FP — SHA-256 de `evaluation-phase-c.json` coincide con el valor congelado (`73e88ef1…`).
- **Instalación real intacta:** 461 productos / 100 ventas (solo lectura).
- **benchmark-data / GROUND_TRUTH / preguntas / resultados históricos:** sin tocar.

---

## 9. VEREDICTO

### 🟡 LISTO CON CORRECCIONES

**Motivo del 🟡 (no 🟢):**
1. Los 2 bugs reales encontrados (B1 UNKNOWN≠0, B2 priorización) **ya están corregidos y verificados** — el código actual es correcto.
2. Queda pendiente de producto (no de código): **etiquetar la base de la cobertura de costes** en UI (B4) y decidir si el modelo debe desglosar envío/impuestos/descuentos en las líneas de venta para eliminar el matiz de B3 en origen.
3. La instalación real actual está **limitada por datos** (sin FacturaScripts, sin stock, sin proveedores), pero el sistema lo declara como UNKNOWN — que es exactamente el comportamiento correcto.

**Qué debe arreglarse antes de beta amplia:**
- (UI) Etiquetar base de cobertura de costes (producto vs revenue).
- (Producto) Decidir si se importa envío/impuestos/descuentos desglosados (elimina el ruido de `inconsistent_order_total` en origen).
- (Datos) Conectar FacturaScripts/stock reales del tester para validar finanzas e inventario end-to-end.

**Qué puede esperar hasta después de beta:**
- Detalles de UI/UX cosméticos; nuevas fuentes; optimización de latencia LLM.

**Lo demostrado en esta validación:**
- Importación normal preserva el 100 % de los datos (461/414/99), idempotente.
- Motor: findings con evidencia real, firmas estables, 0 FP obvios, UNKNOWN ≠ 0.
- Dashboard: Health Scores (ventas GOOD, margen CRITICAL, datos CRITICAL, resto UNKNOWN), Brief Ejecutivo, "Qué hacer hoy" — todos con datos reales.
- Hermes: honesto, sin leaks, sin inventar, cifras verificables, usa los findings del motor.
- Rendimiento: motor ~43 ms; contexto 285 ms; logs sin errores ni secretos.
