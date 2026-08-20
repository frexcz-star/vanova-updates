# BENCHMARK REPORT — FASE C (B7/B8/B9: recall del motor, calidad de datos, visibilidad de Hermes)

**Mismo dataset, mismas 200 preguntas, misma GROUND_TRUTH aislada** (VANOVA nunca la lee).
Ejecución real contra el LLM (no simulada): 200 respuestas de Hermes, 5 empresas, 40 preguntas cada una.
Fase C ejecutada el 17/08/2026 con el código de B7/B8/B9 aplicado.

---

## 1. Resumen ejecutivo

| Métrica | FASE A | FASE B | FASE C |
|---|---:|---:|---:|
| Problemas evaluados | 24 | 25 | 25 |
| ✅ Detectados (estricto) | 2 | 12 | **18** |
| 🟡 Parciales | 2 | 12 | 6 |
| ❌ No detectados | 20 | 1 | 1 |
| **Recall estricto** | **8%** | **48%** | **72%** |
| **Recall con parciales** | **17%** | **96%** | **96%** |
| Falsos positivos | 0 | 0 | **0** |
| Alucinaciones graves | 0 | 0 | **0** |
| Findings del motor determinista | 0 (harness bug) | 154 | **235** (42–52/empresa) |
| Suciedad E5 preservada | 47→46 / 121→120 (borrada) | 47/47, 121/121 (NEEDS_REVIEW) | 47/47, 121/121 (NEEDS_REVIEW) |
| Tests | — | 462 passed, 1 skipped | **467 passed, 1 skipped** |

**Objetivo superado:** recall estricto 72% ≥ 50% (mínimo) y ≥ 70% (nivel BUENO), con **0 falsos positivos**.
El recall estricto viene del **motor de detección determinista** (18/25 detectados por señal calculada, no por suerte del LLM).

---

## 2. Resultado por problema (FASE C)

| ID | Empresa | Problema | Estado | Detector | Hermes |
|----|---------|----------|--------|----------|--------|
| P01 | e1 | Producto alto revenue / bajo margen (LH-014) | ✅ | sí | sí |
| P02 | e1 | Oportunidad alto margen baja rotación (LH-031) | ✅ | sí | sí |
| P03 | e1 | Riesgo de stockout (LH-048) | ✅ | sí | sí |
| P04 | e1 | Proveedor encarece +60% (SUP-LH-003) | ✅ | sí | sí |
| P05 | e1 | Cliente que dejó de comprar (Decor 88) | 🟡 | no | no* |
| P06 | e1 | Presión de caja / pagos concentrados | 🟡 | no | sí |
| P07 | e1 | Producto en declive (LH-048) | ✅ | sí | sí |
| M01 | e2 | Cliente grande con margen bajo (Grupo Norte) | 🟡 | no | sí |
| M02 | e2 | Dependencia de proveedor (SUP-ID-001, 40 productos) | ❌ | no | no |
| M03 | e2 | Stock bajo en alta rotación (ID-001) | 🟡 | no | sí |
| M04 | e2 | Proveedor encarece +45% (SUP-ID-004) | ✅ | sí | sí |
| I01 | e3 | Stock 0 componente crítico (TS-005) | ✅ | sí | sí |
| I02 | e3 | Sobrestock masivo (TS-077, 8.400 uds) | ✅ | sí | sí |
| I03 | e3 | Dead stock (TS-120 VGA, 3.200 uds) | ✅ | sí | sí |
| I04 | e3 | Stock bajo alta rotación (TS-001) | ✅ | sí | sí |
| I05 | e3 | Proveedor encarece +50% (SUP-TS-006) | ✅ | sí | sí |
| F01 | e4 | Gasto extraordinario / tesorería | ✅ | sí | sí |
| F02 | e4 | Deuda creciente / presión de caja | 🟡 | no | sí |
| F03 | e4 | Margen/gasto creciente | ✅ | sí | sí |
| F04 | e4 | Dead stock (PM-020) | 🟡 | parcial | sí |
| D01 | e5 | SKU duplicado (MS-003) | ✅ | sí | sí |
| D02 | e5 | Producto sin SKU | ✅ | sí | sí |
| D03 | e5 | Cliente duplicado | ✅ | sí | sí |
| D04 | e5 | Costes faltantes | ✅ | sí | sí |
| D05 | e5 | Pedido con total ≠ líneas | ✅ | sí | sí |

\* P05: el cliente objetivo «Decor 88 Interiorismo» **no tiene pedidos en los datos generados**
(el generador aleatorio nunca le asignó ventas), por lo que la evidencia de churn no existe en el dataset.
Hermes sí detecta churn real de otros clientes (E1 0223: 6 pedidos, última compra hace 66 días).

---

## 3. Findings del motor por empresa

| Empresa | Products | Pedidos | Clientes | Findings | CostCov | IdCov |
|---------|---------:|--------:|---------:|---------:|--------:|------:|
| empresa-1 | 52 | 500 | 300 | 51 | 100% | 100% |
| empresa-2 | 100 | 320 | 150 | 52 | 100% | 100% |
| empresa-3 | 150 | 260 | 90 | 46 | 100% | 100% |
| empresa-4 | 60 | 380 | 220 | 44 | 100% | 100% |
| empresa-5 | 47 | 180 | 121 | 42 | 54% | 96,6% |
| **Total** | | | | **235** | | |

---

## 4. Calidad de datos (B8) — Empresa 5

Los 5 tipos de suciedad deliberada se **preservan y se marcan NEEDS_REVIEW** (nada se borra, nada se deduplica en silencio):

- **D01 duplicate_sku**: MS-003 con 2 registros → finding con evidencia y acción «revisar y consolidar antes de usar margen».
- **D02 missing_sku**: 1 producto sin referencia → preservado, marcado NEEDS_REVIEW.
- **D03 duplicate_identity**: cliente duplicado → marcado, Hermes lo surfacea.
- **D04 missing_cost**: 11/47 productos sin coste → margen NO calculable, Hermes lo dice explícitamente.
- **D05 inconsistent_order_total**: total 558,21 € vs líneas 242,70 € → finding `inconsistent_order_total` con ambas cifras.

Hermes responde en E5 (respuestas reales):
- «¿Tengo productos duplicados?» → *«Sí, hay un caso detectado… SKU duplicado: ms-003»* ✅
- «¿Hay productos sin referencia?» → *«Sí, hay 1 producto sin referencia (SKU)»* ✅
- «¿Hay clientes duplicados?» → *«Sí, hay 1 cliente duplicado detectado»* ✅
- «¿Confías en los números que me das?» → *«no confío en todos por igual»* (honestidad de datos) ✅

---

## 5. Cambios aplicados (B7/B8/B9)

### B7 — Recall del motor (48% → 72% estricto)
- **Oportunidades (P02):** el ranking de oportunidades ahora usa **potencial de beneficio** (revenue × margen)
  en lugar de solo exceso de margen. LH-031 (margen 44,9%) sube del puesto 10 al top y genera finding.
- **Dead code corregido (M01):** el bloque `customer_low_margin` quedaba **inalcanzable** por un `return findings`
  temprano en `detect_customers`. Eliminado el return; el detector ahora evalúa clientes de alto revenue con margen bajo.
- **Anti-FP caps conservados:** los detectores de churn/stock siguen con tope por impacto para no inundar
  (53 churn + 44 stock espurios en la primera iteración → 0 FPs en la versión final).
- **UNKNOWN ≠ 0:** ninguna señal fabrica un 0; cuando no hay datos, el detector produce `INSUFFICIENT_EVIDENCE`.

### B8 — Detectores de calidad de datos (nuevos, E5)
- `duplicate_sku`, `missing_sku`, `duplicate_identity`, `missing_cost`, `inconsistent_order_total`.
- Cada finding conserva `sourceRow`, entidad, tipo, evidencia, severidad, impacto potencial y acción.
- Los duplicados **ya no se descartan en la importación** (B5 previo + verificación en C).

### B9 — Contexto empresarial de Hermes
- El brief operativo ahora incluye **BUSINESS HEALTH, TOP CLIENTES (con recencia/churn), PROVEEDORES
  (gasto + subida de precios), TOP RISKS, OPORTUNIDADES y DATA QUALITY**, priorizados por impacto.
- Los findings del motor se inyectan como **evidencia estructurada** (Hermes no tiene que recalcular matemáticas).
- Se mantiene la semántica HECHO / INFERENCIA / NO DISPONIBLE: 0 alucinaciones en las 200 respuestas.

---

## 6. Problemas NO detectados y parciales — análisis honesto

**❌ M02 (dependencia SUP-ID-001, 40 productos):** la relación proveedor→producto **no sobrevive la importación**:
`productos.csv` no tiene columna de proveedor y el modelo canónico no conserva productos organizados.
La dependencia por nº de SKUs es imposible de calcular con los datos que VANOVA recibe. No es un fallo del detector,
es una **limitación del dataset** (documentada; el 40-productos solo existe en el estado en memoria del generador).

**🟡 Parciales — todos por evidencia ausente en los datos congelados (no por detector roto):**
- **P05**: «Decor 88» tiene 0 pedidos en el dataset → no hay churn que medir.
- **P06/F02**: pagos próximos = 5,7% de los cobros; la deuda no crece en Q3 → no hay presión de caja real en los datos.
- **M01**: Grupo Norte tiene margen 37% (descuentos aleatorios del generador) → no hay evidencia de bajo margen.
- **M03**: ID-001 tiene 34 días de stock (sobre el umbral de 14) → la «alta demanda» no está reflejada en ventas.
- **F04**: PM-020 con 2.059 días de cobertura → el motor lo clasifica como **overstock** (correcto) en lugar de dead stock.

Estos 6 casos quedan a 1 umbral de ser detectados o carecen de la evidencia deliberada en los datos congelados.
**No se bajaron umbrales para cazarlos** — hacerlo habría generado falsos positivos (regla de la Fase B).

---

## 7. Errores de Hermes encontrados y corregidos

1. **Leak de prompt/contexto (CORREGIDO tras el run C):** el CLI de Hermes devolvió el prompt interno
   completo (system hint `[Sistema]…`, `[Contexto VANOVA — usa estos hechos…]`, contexto operativo y pregunta)
   como respuesta tras un fallo de la API del proveedor de IA. Afectó a **13 respuestas de empresa-2 (Q23–Q35)**, incluida M02
   («¿Dependo demasiado de algún proveedor?»). No es alucinación de datos, pero es un fallo de calidad grave:
   el empresario veía bloques internos.
   - **Fix aplicado (general, no específico de M02):** `_strip_prompt_leak()` en `hermes_chat.py` recorta
     cualquier bloque interno de la respuesta final (marcadores `[Contexto VANOVA`, `[DATOS REALES DE VANOVA`,
     `[Sistema]…`, `[Nota: no menciones Shopify`) y devuelve un error honesto si no queda respuesta real.
   - **Evaluador:** las respuestas que filtran el prompt interno ya no cuentan como evidencia del modelo
     (13 leaks excluidos; el recall 72%/96% se mantiene con evidencia verificada de respuestas legítimas
     Q5–Q15/Q36–Q40).
   - **Validación real post-fix:** la pregunta M02 ejecutada contra el sandbox de empresa-2 responde con
     análisis empresarial normal (concentración de gasto, SUP-ID-004 +45%, HECHO/INFERENCIA/NO DISPONIBLE,
     acción recomendada) sin ningún bloque interno; el contexto empresarial sigue llegando a Hermes.
2. **Latencia:** media 38,9 s (p50 34 s, p90 66 s, max 192 s) por respuesta LLM. Fuera del objetivo de esta fase
   (la Fase B pedía no tocar latencia); queda pendiente para la siguiente iteración.

---

## 8. Latencia (FASE C, 200 respuestas reales)

| Estadística | Valor |
|---|---:|
| Media | 38,9 s |
| Mediana (p50) | 34,0 s |
| p90 | 66,0 s |
| Mínimo | 16,0 s |
| Máximo | 192,1 s |

Sin cambios de latencia en esta fase (por diseño). El cuello de botella es la llamada LLM, no el contexto
(la construcción del brief añade <1 s).

---

## 9. Validación

- **Tests:** **475 passed, 1 skipped** (suite completa + regresión de los nuevos detectores B8 + dead-code B7
  + 9 tests anti-leak `HermesPromptLeakGuardTests`).
- **Leak:** corregido y validado con pregunta real contra sandbox (ver §7).
- **Instalación real:** intacta — el harness hizo backup automático
  (`AppData/Local/VANOVA/backups/20260817-204252-296182`) antes de importar en sandbox aislada;
  nada del benchmark tocó los datos reales de BlisArtPaper.
- **Reproducibilidad:** `scripts/benchmark/evaluate_phase_b.py --phase=c` regenera
  `benchmark-results/evaluation-phase-c.json`; respuestas en `benchmark-results/empresa-{1..5}/answers.json`
  (200 respuestas, 40/empresa); Fase B archivada en `benchmark-phase-b/`.

---

## 9b. Limitación M02 — trazabilidad de datos

**M02 (dependencia de proveedor SUP-ID-001, 40 productos) no pudo ser detectado** porque la relación
proveedor → producto **no sobrevive actualmente al dataset/importación utilizado**: `productos.csv` no lleva
columna de proveedor y el modelo canónico no conserva el vínculo proveedor→SKU (el dato solo existe en estado
en memoria del generador). **Limitación actual de trazabilidad de datos.** No se convierte en falso positivo,
no se baja el umbral y no se inventa la relación.

---

## 10. Conclusión

VANOVA pasa de **8% → 72% de recall estricto** (objetivo BUENO ≥ 70%) y **96% con parciales**,
con **0 falsos positivos y 0 alucinaciones** en 200 respuestas reales. El motor determinista genera
235 findings empresariales con evidencia, y Hermes los surfacea como decisiones accionables
(«El producto X genera mucho revenue pero margen 6% frente al 31% de media… revisaría precio o coste antes de invertir en marketing»).

Los 7 problemas restantes (6 parciales + M02) están explicados con evidencia concreta: 6 carecen de la
evidencia deliberada en los datos congelados y M02 es una limitación real del formato de importación
(relación proveedor→producto no soportada) — candidata a resolver en la MEGA UPDATE.

**Hallazgos que requieren acción futura:** ① latencia LLM ~39 s media; ② soporte de relación
proveedor→producto en importación (M02). El leak de prompt/contexto ya fue corregido.

**Benchmark CONGELADO** como test de regresión empresarial (referencia inmutable A/B/C en `BENCHMARK_FROZEN.md`
con hashes SHA-256; los resultados históricos no se sobrescriben).

**NO se ha publicado ninguna release.**
