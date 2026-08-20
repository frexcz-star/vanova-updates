# MEGA UPDATE VANOVA — AUDITORÍA (FASE 1)

**Fecha:** 17/08/2026 · **Base:** benchmark congelado A/B/C (ver `BENCHMARK_FROZEN.md`).

Esta auditoría precede a cualquier implementación. No se ha tocado código de
negocio todavía; solo se ha leído y medido el estado actual.

---

## C) Problemas actuales (evidencia, no opinión)

### C1. Motor de detección — cobertura y consistencia
- **6 parciales del benchmark (P05, P06, M01, M03, F02, F04):** análisis uno a uno:
  - **P05** (churn Decor 88): el cliente objetivo **no tiene pedidos en el dataset**
    (0 órdenes). Hermes SÍ detecta churn real de otros clientes (E1 0223: 6 pedidos,
    3.054 €, 66 días; E1 0067: 5 pedidos, 99 días). El detector funciona; la evidencia
    deliberada no existe en los datos → no es un fallo del detector.
  - **P06/F02** (presión de caja): pagos próximos = 5,7% de los cobros; la deuda no crece
    en Q3. No hay presión de caja real en los datos congelados.
  - **M01** (Grupo Norte bajo margen): margen real 37% (los descuentos aleatorios del
    generador no crearon el problema). Detector `customer_low_margin` **ya corregido**
    (dead code eliminado en B7), pero sin evidencia no emite.
  - **M03** (ID-001 stockout): 34 días de stock (umbral 14). La "alta demanda" no está
    reflejada en las ventas → no hay riesgo medible.
  - **F04** (PM-020 dead stock): el motor lo clasifica como **overstock** (2.059 días de
    cobertura, 6.895 €) — clasificación CORRECTA según los datos. El ground truth decía
    "dead stock" pero la velocidad (0,107 uds/día) no es ≈0.
  - **Conclusión honesta:** 5/6 parciales son **limitaciones del dataset congelado**, no
    del motor. No se pueden convertir en detecciones sin fabricar evidencia (prohibido).
- **M02** (dependencia proveedor): la relación proveedor→producto no sobrevive la
  importación (`productos.csv` sin columna proveedor; el canónico no conserva el vínculo).
  **Limitación actual de trazabilidad de datos.** Ver C4.

### C2. Trazabilidad proveedor → producto → SKU (ROTTA)
- `generate.py` crea 40 productos de SUP-ID-001 en memoria, pero **ningún archivo que
  VANOVA lee** lleva el vínculo: `productos.csv` no tiene columna `proveedor`, y el
  `canonical-connector.json` solo lleva suppliers/invoices/lines/finance (sin productos).
- Las líneas de factura SÍ tienen `sku` y `invoiceId`, y la factura tiene `supplierId`:
  **existe una ruta indirecta** (línea → factura → proveedor) para reconstruir
  "proveedor suministra SKU". M02 exige 40 productos de un proveedor: verificable por
  nº de SKUs distintos en sus líneas de compra.
- **Impacto:** sin esto, la dependencia por nº de SKUs (M02) y el "impacto en margen por
  proveedor" son imposibles. Es la pieza de arquitectura de datos más valiosa.

### C3. Accionabilidad — impacto económico
- Los findings tienen `estimatedImpact` con `kind: calculated|estimated` y
  `inventoryValue`/`marginPotential` en algunos casos, pero **no es sistemático**:
  - stockout: no cuantifica la venta perdida (revenue 30d × días de riesgo);
  - churn: no cuantifica el revenue anual del cliente en riesgo;
  - supplier cost increase: no calcula el € extra anual por la subida;
  - expenses growing: no calcula el € extra mensual;
  - high_revenue_low_margin: solo "subir 5 puntos" — sin impacto € anual.
- **El empresario necesita "cuánto dinero gano/ahorro si actúo".** Falta la fórmula por
  tipo de finding.

### C4. Datos duplicados en señales
- `business_signals.product_signals` y `detection_engine._product_metrics` calculan cosas
  parecidas por caminos distintos (señales vs métricas internas). No hay inconsistencia
  grave (B7 alineó las ventanas), pero hay **cálculo duplicado** (coste por SKU resuelto
  dos veces; buckets de 30/60/90d por dos rutas).
- `render_business_brief` re-llama `list_findings()` cuando se le pasa `None`; el caller
  ya lo tiene. Duplicación menor de I/O.

### C5. Hermes — contexto y latencia
- **Latencia:** media 38,9 s / p50 34 s / p90 66 s (200 respuestas). El contexto construye
  ~0,5–1 s; el 95%+ es la llamada LLM cloud. El contexto se cachea 10 s (TTL) y las
  coberturas se precalculan (P1/P6 de FASE HERMES ya aplicadas).
- **Contexto NO selectivo:** Hermes recibe el brief completo (30 productos + brief de
  negocio) para TODA pregunta. Una pregunta de clientes no necesita los 30 productos.
  Selección por dominio de la pregunta reduciría tokens y ruido.
- **Leak:** corregido y protegido (FASE C) — `_strip_prompt_leak` + 9 tests.

### C6. UI/Dashboard
- El dashboard YA tiene: tarjetas de métricas, `dataQualityHTML`, `dataHealthHTML`,
  `businessFindingsHTML` (problemas/oportunidades/positivos con evidencia, impacto,
  acción y botones Reconocer/Resolver/Preguntar a Hermes), prioridades de IA y columna
  lateral (estado, timeline, acciones rápidas).
- **Faltan / pueden mejorar:**
  1. **"¿Qué debería hacer hoy?"** — no hay un bloque ejecutivo que priorice las 3–5
     acciones con mayor impacto €. Es el valor nº1 para un empresario.
  2. **Impacto económico visible en las tarjetas de métricas** (solo cifras, sin
     semáforo de "bueno/malo").
  3. Concentración: los findings se listan todos; falta colapso por tipo con top-N.
  4. Estados ambiguos: cuando el motor no puede analizar (muestra/coste), no se muestra
     claramente por qué (los `blockedReasons` existen pero no se exponen).

### C7. Rendimiento
- Sin perfilado formal en esta auditoría; puntos de riesgo detectados por lectura:
  - `compute_signals` recalcula por request del motor (ok, el motor se ejecuta por
    análisis, no por pregunta de Hermes);
  - `render_context_block` + `render_business_brief` leen findings persistidos una vez
    por build de contexto (con caché 10 s → bien);
  - dashboard hace polling de `getBusinessFindings` — barato (lectura de config);
  - imports de CSV → `file_organizer` (no perfilado aquí; ficheros de 100–500 filas).
- **Conclusión:** no hay cuello de botella determinista crítico; el coste real es el LLM.

---

## A) Lista priorizada de mejoras

| # | Mejora | Área | Impacto | Esfuerzo |
|---|--------|------|---------|----------|
| A1 | Trazabilidad proveedor→producto→SKU (línea→factura→proveedor) | Datos/Señales | ALTO (M02 + margen por proveedor) | M |
| A2 | Impacto económico cuantificado por finding (fórmulas por tipo) | Motor/Accionabilidad | ALTO | M |
| A3 | Bloque UI "Qué hacer hoy" (top 3–5 acciones por impacto €) | UI | ALTO | M |
| A4 | Ranking de oportunidades: potencial € × confianza × urgencia | Motor | ALTO | B |
| A5 | Señal de velocidad de venta proyectada + días de ruptura exactos | Motor | MEDIO | B |
| A6 | Contexto Hermes selectivo por dominio de la pregunta | Hermes | MEDIO | M |
| A7 | Exponer `blockedReasons` en UI (por qué no hay análisis) | UI | MEDIO | B |
| A8 | Colapsar findings por tipo con top-N en UI | UI | MEDIO | B |
| A9 | Eliminar cálculo duplicado señales vs métricas internas | Perf | MEDIO | M |
| A10 | Semáforo bueno/malo en tarjetas de métricas | UI | BAJO | B |
| A11 | Reordenar brief de Hermes por impacto (no por orden de hallazgo) | Hermes | BAJO | B |

## B) Arquitectura propuesta (objetivo)

```
DATOS CANÓNICOS (config_store)
   │
   ├─ business_model (normalización/validación, fuente única)
   │
   ├─ business_signals (SEÑALES: producto/cliente/proveedor/finanzas + trazabilidad)
   │     • producto: revenue, margen €/%, velocidad, días de stock, valor inventario
   │     • cliente: revenue, pedidos, ticket, tendencia, recencia/churn, margen
   │     • proveedor: gasto, tendencia, dependencia (por gasto Y por nº SKUs), precios
   │     • finanzas: revenue, gastos, pendientes, caja, evolución mensual
   │     • IMPACTO €: cada señal lleva la fórmula de impacto económico
   │
   ├─ detection_engine (DETECTORES → FINDINGS con evidencia + impacto € + acción)
   │     • reglas deterministas, umbrales documentados, anti-FP caps
   │     • ranking: score = impacto € × confianza × urgencia
   │
   ├─ agent_data_tools (CONTEXTO Hermes: brief compacto, seleccionado por dominio)
   │
   ├─ web/dashboard.html (UI: Qué hacer hoy → Riesgos → Oportunidades → Data Quality)
   │
   └─ Hermes (interpretación/conversación; NUNCA sustituye al motor)
```

**Principios:** ① determinista primero, LLM después; ② UNKNOWN ≠ 0; ③ evidencia y
fórmula de impacto en cada finding; ④ anti-FP por cap; ⑤ benchmark congelado como
regresión; ⑥ ninguna mejora hardcodea entidades del benchmark.

## D) Impacto esperado de cada mejora

| Mejora | Recall | FP | Accionabilidad | UX | Perf |
|--------|:------:|:--:|:--------------:|:--:|:----:|
| A1 trazabilidad proveedor | + (M02 si los datos lo permiten) | 0 | + | + | — |
| A2 impacto € por finding | 0 | 0 | **++** | ++ | — |
| A3 "Qué hacer hoy" | 0 | 0 | **++** | **++** | — |
| A4 ranking por valor | 0 | 0 | + | + | — |
| A5 días de ruptura exactos | +(M03 si hay evidencia) | 0 | + | + | — |
| A6 contexto selectivo | + (menos ruido) | 0 | + | + | + |
| A7 blockedReasons en UI | 0 | 0 | + | + | — |
| A8 colapso por tipo | 0 | 0 | 0 | + | + |
| A9 sin duplicación | 0 | 0 | 0 | 0 | + |
| A10 semáforo métricas | 0 | 0 | 0 | + | — |
| A11 brief por impacto | 0 | 0 | + | + | — |

## E) Clasificación

- **CRÍTICOS:** A1 (trazabilidad — desbloquea M02 y margen por proveedor), A2 (impacto €),
  A3 ("Qué hacer hoy").
- **IMPORTANTES:** A4 (ranking), A5 (días de ruptura), A6 (contexto selectivo), A7
  (blockedReasons en UI).
- **NICE-TO-HAVE:** A8, A9, A10, A11.

## F) Plan de implementación por fases

- **Fase 1 (esta):** auditoría + A1 + A2 + A4 (motor/señales/impacto).
- **Fase 2:** A3 + A7 + A8 (UI "Qué hacer hoy", blockedReasons, colapso por tipo).
- **Fase 3:** A5 + A6 (días de ruptura exactos, contexto selectivo por dominio).
- **Fase 4:** A9 + A10 + A11 (perf, semáforo, brief por impacto) + suite completa.
- **Cada fase:** tests + verificación del benchmark congelado (sin re-ejecutar las 200
  preguntas salvo aprobación).

## G) Estimación de tests necesarios

- A1: trazabilidad proveedor→SKU (línea→factura→proveedor), dependencia por nº de SKUs,
  sin vínculo → INSUFFICIENT_EVIDENCE. (~6 tests)
- A2: fórmula de impacto por tipo (stockout, churn, supplier increase, expenses, margin),
  kind calculated vs estimated, UNKNOWN≠0. (~8 tests)
- A4: ranking por score, empates, sin hardcode. (~4 tests)
- A3/A7/A8 (UI): smoke de render de los bloques nuevos. (~4 tests)
- A5: días de ruptura exactos, stock 0, sin velocidad. (~3 tests)
- A6: selección por dominio, pregunta de clientes no trae productos, pregunta genérica
  trae brief completo. (~4 tests)
- Regresión: los 475 existentes + anti-FP + leak. Total estimado **~504+**.

## H) Riesgos de introducir falsos positivos

- **A1:** reconstruir proveedor→SKU por líneas puede unir facturas sin fecha o con
  proveedor vacío → exigir ≥3 líneas/facturas y SKU no vacío; si el vínculo es débil,
  INSUFFICIENT_EVIDENCE. **Mitigación:** umbral de cobertura + cap de findings.
- **A2:** impacto € puede parecer "cierto" → etiquetar SIEMPRE `estimated` salvo
  aritmética directa (`calculated`); la fórmula usa revenue/coste reales.
- **A4:** score alto en cola larga → combinar con caps por tipo (ya existentes) y
  umbral mínimo de revenue/€.
- **A5:** proyección lineal puede sobre-estimar → días = stock/velocidad con velocidad
  mínima (evita división por ruido); no emitir con <2 ventas.
- **A6:** clasificación errónea de dominio → si la pregunta es ambigua, contexto completo
  (regla conservadora como la ruta casual).

## I) Impacto esperado global

- **Recall:** sin tocar los 6 parciales del dataset congelado (limitación de datos), pero
  A1+A5 añaden capacidad nueva para futuras empresas (M02/M03-type cuando exista
  evidencia). Objetivo honesto: mantener 72% estricto / 96% con parciales **sin FP**, y
  subir capacidad por dimensión.
- **UX:** "Qué hacer hoy" + impacto € + semáforo → el empresario entiende en segundos
  qué pasa y qué hacer.
- **Performance:** contexto selectivo + sin duplicación → menos tokens LLM y menos
  cálculo; el LLM sigue dominando la latencia (fuera de alcance de esta fase).

---

## DECISIÓN DE IMPLEMENTACIÓN (tras la auditoría)

**Empiezo por las de mayor valor: A2 (impacto económico por finding), A4 (ranking por
valor), A1 (trazabilidad proveedor→SKU por línea→factura→proveedor).** Cada una con
tests y sin tocar el benchmark congelado. El resto (UI, contexto selectivo) en fases
posteriores dentro de esta misma MEGA UPDATE.
