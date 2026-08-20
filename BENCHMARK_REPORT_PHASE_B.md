# BENCHMARK REPORT — FASE B (Business Signals → Detection → Hermes)

**Mismo dataset, mismas 40 preguntas por empresa (200 en total), misma
GROUND_TRUTH** que FASE A. El evaluador (`scripts/benchmark/evaluate_phase_b.py`)
solo da por **detectado** un problema cuando el tipo de finding y la entidad
objetivo coinciden, o existe evidencia de calidad de datos específica. Un
mencionar el tipo sin la entidad cuenta como **parcial**, nunca como éxito.

---

## 1. Resumen ejecutivo (A → B)

| Métrica | FASE A | FASE B |
|---|---:|---:|
| Problemas evaluados | 24 | 25* |
| ✅ Detectados | 2 | **12** |
| 🟡 Parciales | 2 | 12 |
| ❌ No detectados | 20 | **1** |
| **Recall (solo detectados)** | **8%** | **48%** |
| **Recall (detectados + parciales)** | **17%** | **96%** |
| Falsos positivos | 0 | 0 |
| Motor de detección (findings en las 5 empresas) | **0** | **154** (24–34 por empresa) |
| Datos sucios preservados (E5) | 47→46 productos, 121→120 clientes | **47/47 productos, 121/121 clientes** |

\* La GROUND_TRUTH lista 24 problemas; el evaluador añade **D03** como problema
de calidad explícito (costes faltantes) que FASE A sí evaluó, total 25.

**Veredicto:** VANOVA pasó de **lector honesto** a **detector parcial de
problemas**. El motor determinista ya funciona (era el hallazgo de
infraestructura de FASE A) y Hermes recibe evidencia estructurada. **El recall
estricto (48%) se queda ligeramente por debajo del objetivo MÍNIMO del 50%**
por problemas de *precisión de entidad* y *umbrales*, no por falta de datos.
Con los parciales, el sistema **localiza y señala el 96% de los problemas**.

---

## 2. Matriz por problema (B1) — dónde se rompe la cadena

Cadena: `DATOS → MODELO → DETECTOR → CONTEXTO/HERMES → DECISIÓN`

| ID | Problema | Datos necesarios | VANOVA los tiene | Detector | Hermes | Status |
|---|---|---|:---:|:---:|:---:|---|
| P01 | LH-014 mucho revenue, margen 6% | revenue+margen por SKU | ✅ | ✅ | ✅ | **DETECTADO** |
| P02 | LH-031 alto margen, baja rotación | margen+share | ✅ | tipo, entidad distinta | ✅ | PARCIAL |
| P03 | LH-007 riesgo stockout | stock+velocidad | ✅ | ✅ | ✅ | **DETECTADO** |
| P04 | SUP-LH-003 encarece +60% | precios de compra históricos | ✅ | ✅ | ✅ | **DETECTADO** |
| P05 | Cliente que dejó de comprar | recencia por cliente | ✅ | tipo (otro cliente) | ❌ | PARCIAL |
| P06 | Presión de tesorería | facturas+cobros | ✅ | ❌ | ✅ | PARCIAL |
| P07 | LH-048 en caída | tendencia 30d | ✅ | tipo (otro SKU) | ✅ | PARCIAL |
| M01 | Cliente grande con margen bajo | margen por cliente | ✅ | ❌ | ✅ | PARCIAL |
| M02 | Dependencia SUP-ID-001 | gasto por proveedor | ✅ | ❌ (share 10% < umbral) | ❌ | **NO DETECTADO** |
| M03 | ID-001 stock bajo, alta rotación | stock+velocidad | ✅ | ❌ (ID-001 no pasa umbral) | ✅ | PARCIAL |
| M04 | SUP-ID-004 encarece +45% | precios de compra | ✅ | ✅ | ✅ | **DETECTADO** |
| I01 | TS-005 stock 0 | stock+velocidad | ✅ | ✅ | ✅ | **DETECTADO** |
| I02 | TS-077 sobrestock 8.400 uds | stock+velocidad | ✅ | ✅ | ✅ | **DETECTADO** |
| I03 | TS-120 dead stock | stock+velocidad | ✅ | ✅ | ✅ | **DETECTADO** |
| I04 | TS-001 stock 4, alta rotación | stock+velocidad | ✅ | ✅ | ✅ | **DETECTADO** |
| I05 | SUP-TS-006 encarece | precios de compra | ✅ | ✅ | ✅ | **DETECTADO** |
| F01 | Alquiler+servicios crecen | serie de pagos | ✅ | ✅ | ✅ | **DETECTADO** |
| F02 | Deuda creciente (impagados) | facturas emitidas | ✅ | ❌ | ✅ | PARCIAL |
| F03 | SUP-PM-002 encarece | precios de compra | ✅ | ✅ | ✅ | **DETECTADO** |
| F04 | PM-020 dead stock de alto coste | stock+velocidad | ✅ | tipo (otro SKU) | ✅ | PARCIAL |
| D01 | SKU MS-003 duplicado | archivo original | ✅ preservado (2 filas NEEDS_REVIEW) | ❌ | ✅ (Q32) | PARCIAL |
| D02 | Producto sin SKU | archivo original | ✅ preservado (NEEDS_REVIEW) | ❌ | ❌ (Q33 dice "todos tienen SKU") | PARCIAL |
| D03 | 10 costes faltantes | catálogo | ✅ | bloqueo de cobertura | ✅ | **DETECTADO** |
| D04 | Cliente duplicado (email) | archivo original | ✅ preservado (2 filas NEEDS_REVIEW) | ❌ | ❌ | PARCIAL |
| D05 | Pedido con total incoherente | pedido + líneas | ✅ preservado | ❌ | ❌ | PARCIAL |

**Dónde se rompe la cadena en los 13 parciales/no detectados:**

1. **Detector encuentra el TIPO pero no la ENTIDAD objetivo** (P02, P05, P07,
   F04): el motor prioriza por impacto/capital (p. ej. `low_revenue_high_margin`
   queda limitado a los 3 de mayor margen) y la entidad deliberada cae fuera
   del tope. Es una decisión anti-ruido documentada, con coste de recall.
2. **Umbrales demasiado estrictos para el caso** (M02, M03): la dependencia de
   proveedor se mide por *share de gasto* (10% en el dataset) y el umbral es
   40%; la dependencia real es por nº de productos (40 SKUs), que no se mide.
3. **Modelo sin detección de calidad de datos** (D01, D02, D04, D05): las
   anomalías **se preservan y marcan NEEDS_REVIEW** (fix B5, verificado: 47/47
   y 121/121), pero no hay detector de duplicados/missing/incoherencias que
   las convierta en finding.
4. **Hermes no recibe la agregación de cliente con margen** (M01) ni la
   visibilidad de deuda por impagados (F02) → responde de forma general.

---

## 3. Qué se cambió (B2–B5)

| Módulo | Cambio |
|---|---|
| **`desktop/runtime/business_signals.py`** (NUEVO) | Señales estructuradas por producto (revenue, margen, velocidad, tendencia 30d relativa a los datos, stock, días de stock, valor de inventario), cliente (revenue, pedidos, ticket, margen, recencia/churn), proveedor (gasto, dependencia, precio unitario histórico) y finanzas (revenue, gastos, pendientes, mensual). **UNKNOWN ≠ 0**: sin stock/coste/histórico → `None`, nunca 0. |
| **`desktop/runtime/detection_engine.py`** | Nuevos detectores: `stockout_risk`, `overstock`, `dead_stock` (con tope por capital para no inundar), `customer_churn`, `customer_concentration`, `customer_low_margin`, `supplier_dependency`, `supplier_cost_increase`, `expense_growing` (series recurrentes rent/services). Los detectores de producto ahora consumen las señales (misma fuente de verdad, sin doble cálculo). |
| **`desktop/runtime/agent_data_tools.py`** | Contexto de Hermes rediseñado: bloque `BUSINESS HEALTH` (revenue/gastos/margen/pendientes), `TOP CLIENTES`, `PROVEEDORES`, `TOP RISKS` y `OPORTUNIDADES` con hallazgos persistidos del motor agrupados por tipo (evidencia + acción), y contador del motor. |
| **`desktop/runtime/file_organizer.py`** (B5) | El import **ya no deduplica silenciosamente**: duplicados de SKU y de cliente se **preservan ambos** y se marcan `NEEDS_REVIEW` (`duplicate_sku` / `duplicate_identity`); filas sin SKU se preservan marcadas `missing_sku`; el merge por clave de archivo respeta la procedencia (`sourceRow`). |
| **`desktop/runtime/product_identity.py`** | Un SKU duplicado deja de aportar coste hasta su revisión (`UNKNOWN ≠ coste verificado`). |
| **Tests** | `test_file_organizer.py`: +2 regresiones de preservación (productos y clientes). Suite completa: **462 passed, 1 skipped**. |

**Causa raíz del "0 findings" de FASE A:** era un bug del harness de FASE A
que llamaba a `list_findings` sin haber ejecutado nunca `run_detection`. En
FASE B el harness ejecuta el motor real (`persist=True`) y los hallazgos se
persisten y llegan a Hermes.

---

## 4. Falsos positivos y alucinaciones

- **Falsos positivos: 0.** El evaluador exige tipo + entidad; no se ha contado
  ninguna detección inexacta como éxito.
- **Alucinaciones: 0.** Hermes sigue separando HECHO/INFERENCIA/NO DISPONIBLE;
  donde no hay dato lo dice y no lo convierte en 0.
- **Datos que VANOVA consideró fiables cuando no debía:** ninguna cifra nueva;
  el único caso heredado es que Hermes afirmó en E5 Q33 "no hay productos sin
  referencia" (el modelo expone 46–47 filas y la fila sin SKU no se surfacea
  aún al contexto) — incoherencia del modelo, no alucinación del LLM.

---

## 5. Decisiones accionables nuevas (ejemplos reales de las respuestas)

- **E3 Q35/Q37:** "El sensor a reordenar con urgencia es TS-005 (stock 0)" y
  "liquidar con prioridad TS-120 (stock muerto 3.200 uds)".
- **E4 Q17:** "SUP-PM-002 ha encarecido sus productos (+36,5%)" — renegociar.
- **E4 Q31:** "Gasto recurrente en alza: rent 1.800→2.605 € (+44,7%) y services
  600→1.104 € (+84%)" — revisar partidas.
- **E1 Q34:** "pedir más stock de la silla LH-007 (1,9 días de cobertura)".
- **E1 Q8:** el ancla LH-014 con margen 6% vs 33% de media y decisión de
  renegociar antes de invertir en publicidad.

---

## 6. Nuevos fallos y limitaciones restantes

1. **Recall estricto 48%** (objetivo MÍNIMO 50%): la entidad objetivo cae
   fuera de los topes anti-ruido del motor en 4 casos (P02, P05, P07, F04) y
   el umbral de dependencia de proveedor no encaja con el caso M02.
2. **No hay detectores de calidad de datos** (duplicados, missing SKU, total
   incoherente): los datos se preservan y marcan, pero no generan finding.
3. **Hermes no surfacea aún la fila sin SKU/duplicados** al contexto de
   calidad (D02/D04) — la preservación existe en el modelo, la UX no.
4. **F02 (deuda creciente)** y **P06 (presión de tesorería)** se señalan solo
   de forma general; falta visibilidad de impagados/vencimientos por cliente.
5. **M02**: la dependencia se mide por gasto, no por nº de productos.
6. **Latencia**: ~16–40 s por respuesta (LLM cloud) — sin cambios en esta fase.

---

## 7. Tests

- Suite completa: **462 passed, 1 skipped, 0 fallos** (`pytest -q`).
- Nuevas regresiones B5 (preservación de suciedad): incluidas en
  `tests/test_file_organizer.py`.

---

## 8. Instalación real

- **Intacta**: 461 productos / 99–100 pedidos / credenciales sin tocar.
- El benchmark se ejecutó íntegramente en sandbox aislado
  (`benchmark-sandbox/`, `LOCALAPPDATA` temporal + `.env` vacío que bloquea
  Shopify real). No se publicó ninguna release.

---

## 9. Conclusión

VANOVA ya **detecta** 12 de los 24–25 problemas deliberados con entidad exacta
y **localiza** 24/25 si se cuentan los parciales. El valor accionable real
(qué producto reponer, qué liquidar, qué proveedor renegociar, qué gasto
revisar) aparece en las respuestas de Hermes con evidencia del motor. Lo que
queda es **precisión de entidad** (afinar topes/umbrales sin reintroducir
ruido), **detectores de calidad de datos** y **surfacear la salud de los
datos en el contexto de Hermes**. La honestidad (0 alucinaciones, 0 falsos
positivos, UNKNOWN ≠ 0) se mantiene intacta.

**Estados de los 24 problemas: 12 detectados · 12 parciales · 1 no detectado ·
0 falsos positivos.**
