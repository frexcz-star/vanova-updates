# MEGA UPDATE VANOVA — INFORME FINAL (FASE 1 + FASE 2)

**Fecha:** 17/08/2026 · **Base:** benchmark congelado (ver `BENCHMARK_FROZEN.md`)
· **Regla:** veracidad > completitud. Ningún cambio tocó `benchmark-data/`,
`benchmark-secret/GROUND_TRUTH.md`, las preguntas ni los resultados históricos.

---

## 1. Resumen ejecutivo

La MEGA UPDATE convierte VANOVA de "motor que detecta hechos" en un producto
que **prioriza por valor económico**: cada hallazgo lleva impacto € (calculado o
estimado, nunca inventado), el motor genera un semáforo de salud por dimensión,
un brief ejecutivo ("dinero en riesgo / mayor problema / mayor oportunidad /
qué falta") y un plan de acción "Qué hacer hoy" — todo determinista, con
evidencia, y servido a Hermes y a la UI por el MISMO cálculo (el LLM interpreta,
no inventa).

**Benchmark congelado intacto:** 72% recall estricto / 96% con parciales / 0 FP
(verificado tras cada cambio). Sin regresiones: **499 tests passed, 1 skipped**.

---

## 2. Comparativa A → B → C → MEGA UPDATE

| Métrica | FASE A | FASE B | FASE C | **MEGA UPDATE** |
|---|---:|---:|---:|---:|
| Recall estricto | 8% | 48% | 72% | **72%** (sin tocar umbrales; capacidad nueva para futuras empresas) |
| Recall con parciales | 17% | 96% | 96% | **96%** |
| Falsos positivos | 0 | 0 | 0 | **0** |
| Hallucinaciones graves | 0 | 0 | 0 | **0** (leak de prompt corregido y protegido en FASE C; intacto) |
| Findings del motor | 0 | 154 | 235 | **42–52 por empresa** (misma cobertura + nuevas señales de impacto) |
| Tests | — | 462+1sk | 475+1sk | **499 passed, 1 skipped** |
| Hallazgos con impacto € | 0 | parcial | parcial | **sistemático** (stockout, churn, proveedor, margen, gastos) |
| Semáforo de salud | — | — | — | **SÍ** (7 dimensiones + overall, UNKNOWN≠0) |
| Brief ejecutivo | — | — | — | **SÍ** (riesgo €, mayor problema/oportunidad, qué falta) |
| "Qué hacer hoy" | — | — | — | **SÍ** (top 5 por impacto € × confianza) |
| Contexto selectivo Hermes | — | — | — | **SÍ** (customer/supplier/finance omiten filas de producto; −28% tokens) |
| Cálculos duplicados | varios | varios | varios | **eliminados** (helpers reutilizan datos; código muerto retirado) |

---

## 3. Cambios implementados en la MEGA UPDATE

### FASE 1 (motor / señales / impacto)
- **A1 — Trazabilidad proveedor→producto→SKU** (`business_signals.supplier_sku_signals`):
  reconstruye la relación proveedor→SKU desde línea de factura → factura recibida →
  proveedor (los datos que SÍ existen). Detector de dependencia por **nº de SKUs**
  (≥5 SKUs y ≥40% del catálogo de compra), sin duplicar con la dependencia por
  gasto. UNKNOWN≠0: sin vínculo → INSUFFICIENT_EVIDENCE (M02 sigue siendo una
  limitación del dataset, no del detector).
- **A2 — Impacto económico cuantificado** por finding:
  - stockout: venta perdida = revenue 30d × fracción de días sin cobertura;
  - churn: revenue histórico del cliente en riesgo;
  - supplier cost increase: coste extra = (último precio − primer precio) ×
    unidades compradas — sin unidades → solo %, **nunca un € inventado**;
  - high_revenue_low_margin: potencial de recuperar la mitad del gap de margen;
  - expenses: incremento mensual recurrente.
  Todo etiquetado `calculated` (aritmética sobre datos reales) o `estimated`.
- **A4 — Ranking por valor económico**: el cap anti-ruido de "alto margen poco
  revenue" ordena por **revenue × margen** (un producto con 1.600 € al 45% no
  queda oculto tras cola larga con revenue casi nulo — el caso LH-031 de FASE C).
  Firmas estables por entidad + ventana (dedupe entre días).

### FASE 2 (UI / semáforo / brief / eficiencia)
- **A3 — "Qué hacer hoy"** (`detection_engine.action_plan`): prioriza hallazgos
  activos por impacto € × confianza × severidad; sin importe → orden por
  severidad (UNKNOWN≠0). Bloque UI top-5 con importe visible.
- **A8 — Findings agrupados y priorizados**: por categoría (problema /
  oportunidad / positivo), **ordenados por impacto €**, con badge de € en el
  resumen, severidad, evidencia, acción y expansor "+N más" (sin lista
  interminable).
- **A10 — Semáforo de salud empresarial** (`health_scores`): 7 dimensiones
  (ventas, margen, inventario, clientes, proveedores, finanzas, calidad de
  datos) con estados GOOD / WARNING / CRITICAL / UNKNOWN. UNKNOWN≠0: sin datos
  suficientes se muestra SIN DATOS, nunca BIEN. El agregado es el PEOR estado.
- **A11 — Brief ejecutivo** (`executive_brief`): salud general, dinero en
  riesgo (suma de impactos de problemas activos), mayor problema, mayor
  oportunidad, plan de acción y qué información falta (`missingInfo`). Se
  inyecta en el contexto de Hermes (bloque SALUD GENERAL) y se muestra en el
  dashboard (Resumen ejecutivo).
- **A6 — Contexto de Hermes selectivo por dominio** (`_question_domain`):
  clasifica la pregunta (product/customer/supplier/finance/stock/general,
  conservador); customer/supplier/finance omiten las 30 filas de producto
  (−28% tokens en smoke real) pero conservan ventas, clientes, finanzas y el
  brief. Ambigua → contexto completo.
- **A7 — blockedReasons en UI**: cuando el motor no puede analizar, la UI
  muestra los motivos exactos (notas de `data_quality`) en vez de un vacío.
- **A9 — Eficiencia**:
  - `action_plan` / `health_scores` / `executive_brief` aceptan findings y
    quality ya cargados → **0 lecturas extra de config** por request
    (verificado con contador de llamadas);
  - eliminado `_product_metrics` (código muerto: duplicaba
    `business_signals.product_signals`, sin llamadores desde FASE B);
  - el brief de Hermes usa el `executiveBrief` del payload de `list_findings`
    (no recalcula `data_quality` ni rompe `precomputed_coverage`).

### Detector review (sin bajar umbrales)
- Dependencia por SKUs nueva con umbrales propios (≥5 SKUs, ≥40%);
- los 6 parciales de FASE C (P05/P06/M01/M03/F02/F04) **no** se forzaron: la
  evidencia no existe en los datos congelados (documentado en la auditoría);
- sin cambios de umbrales existentes → 0 FP, ranking determinista.

---

## 4. Tests

| Conjunto | Resultado |
|---|---|
| Suite completa | **499 passed, 1 skipped** |
| Anti-leak Hermes (FASE C) | 9 tests intactos |
| A1 trazabilidad proveedor→SKU | 4 tests (señal, umbral, no-duplicado, gasto) |
| A2 impacto € | 5 tests (stockout, churn, proveedor con/sin unidades) |
| A3/A4 ranking + action plan | 5 tests (valor>margen, cap, determinismo, resuelto excluido) |
| A10 salud | 2 tests (peor manda, UNKNOWN≠0, GOOD solo con datos) |
| A11 brief | 2 tests (evidencia, vacío honesto) + 1 en contexto Hermes |
| A6 contexto selectivo | 4 tests (clasificador + filas omitidas/conservadas) |
| A9 eficiencia | 1 test (0 loads extra con datos pre-cargados) |

Nuevos tests en FASE 2: **+6** (A10×2, A11×2+1, A9×1). Ninguno toca el
benchmark.

---

## 5. Verificación

- **Benchmark congelado**: evaluador `--phase=c` → 18 detected / 6 partial /
  1 not_detected (M02) · 72% estricto · 96% con parciales · 0 FP. **Sin cambio.**
- **Instalación real**: 461 productos, 100 ventas — intacta (ningún write).
- **Smoke por empresa** (5 sandboxes): 42–52 findings cada una; semáforo con
  CRITICAL/WARNING/UNKNOWN correctos (p. ej. proveedores UNKNOWN en empresa-5
  sin facturas; finanzas GOOD solo donde hay tesorería).
- **UI**: funciones nuevas renderizan con datos reales (verificado vía DOM):
  semáforo con estados, brief con importes, "Qué hacer hoy" con €, findings con
  € e IMPACTO CALCULADO. Copias `index.html`/`dist` sincronizadas.
- **Latencia**: sin regresión medible; los helpers nuevos no leen config
  extra; el coste dominante sigue siendo la llamada LLM (fuera de alcance).

---

## 6. Limitaciones conocidas (honestas)

1. **M02** — dependencia de proveedor por nº de SKUs: la relación
   proveedor→producto no sobrevive al dataset/importación (`productos.csv` sin
   columna proveedor). **Limitación de trazabilidad de datos**, no del motor.
   Documentada; sin falso positivo; sin bajar umbrales.
2. **6 parciales de FASE C** (P05/P06/M01/M03/F02/F04): la evidencia deliberada
   no existe en los datos congelados (0 pedidos de un cliente, pagos = 5,7% de
   cobros, margen 37%, 34 días de stock, deuda sin crecimiento en Q3). No se
   pueden convertir en detecciones sin fabricar evidencia (prohibido).
3. **Semáforo**: GOOD se asigna solo cuando el motor puede analizar esa
   dimensión; dimensiones sin fuente (p. ej. tesorería sin FacturaScripts)
   quedan UNKNOWN. Por diseño.
4. **Latencia LLM** (~39 s media): el contexto selectivo A6 reduce tokens pero
   el tiempo dominante es el modelo cloud. Sin cambios en esta fase.
5. **Login de UI en sandbox**: los sandboxes del benchmark no son instalaciones
   completas (no tienen setup), por lo que el preview visual completo requiere
   una instalación real; la validación de render se hizo inyectando datos.

---

## 7. Recomendación para beta empresarial

**VANOVA está preparada para una beta empresarial controlada** en cuanto a
inteligencia empresarial:
- recall 72% estricto / 96% con parciales / 0 FP / 0 alucinaciones — el motor
  es honesto y prioriza por valor €;
- semáforo, brief ejecutivo y "qué hacer hoy" responden directamente a "¿cómo
  está mi empresa, qué me afecta, cuánto y qué hago?";
- la trazabilidad proveedor→SKU y el impacto € abren el análisis de compras y
  margen por proveedor.

**Antes de beta amplia / release**, considerar (fuera del alcance de esta fase):
- importación de la relación proveedor→producto desde el fichero de origen
  (desbloquea M02 de forma general);
- reducir latencia LLM (selección de contexto ya aplicada; siguiente paso:
  ranking de tools o modelo más rápido);
- UX pulida de onboarding/setup (la fase de UI/UX global puede profundizar en
  los estados de primera configuración).

**No se ha publicado ninguna release.** `benchmark-data/`, GROUND_TRUTH y
resultados históricos permanecen intactos y congelados.
