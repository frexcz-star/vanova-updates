# INFORME PRE-BETA — GO / NO-GO

**Fecha:** 2026-08-17 · **Estado:** auditoría final de flujos críticos completada

---

## 1. QUÉ SE AUDITÓ

| Flujo | Resultado |
|---|---|
| Primer arranque (instalación nueva, sin datos) | ✅ Honesto: health UNKNOWN, moneyAtRisk None, 0 findings, "datos" ya no dice GOOD |
| Escaneo / importación | ✅ 461 productos / 414 costes / 99 ventas, idempotente (2× idéntico) |
| Detección | ✅ 6 findings con evidencia real, firmas estables entre runs |
| Dashboard | ✅ Health Scores + semáforos + Brief + "Qué hacer hoy" + findings agrupados |
| Health Score | ✅ GOOD/WARNING/CRITICAL/UNKNOWN correctos; UNKNOWN ≠ GOOD sin datos |
| Brief Ejecutivo | ✅ Basado en motor; moneyAtRisk None (no 0 €) cuando no cuantificable |
| "Qué hacer hoy" | ✅ Ranking por impacto € × confianza × severidad del motor |
| Findings | ✅ 6/6 con qué ocurre + evidencia + impacto + acción + qué falta |
| Preguntas a Hermes | ✅ HECHO/INFERENCIA/NO DISPONIBLE, sin leaks, cifras reales (4 preguntas probadas) |
| Actualización / refresco de datos | ✅ `/api/business/analyze` + polling 30 s; re-import sin duplicados |

---

## 2. BUGS REALES ENCONTRADOS Y CORREGIDOS (4)

### B1. "Dinero en riesgo" se mostraba como **0 €** cuando no era cuantificable — BUG (UNKNOWN ≠ 0)
- **Dónde:** `web/dashboard.html` (`executiveBriefHTML`) — `moneyAtRisk` null se renderizaba como "0 €" en verde (éxito).
- **Corrección:** cuando es `null`/`undefined` muestra **"—"** en gris con el texto "no cuantificable con los datos actuales (UNKNOWN, no 0)". Lo mismo para `opportunityPotential`.
- **Verificado:** render con payload real → PASS (no aparece "0 €").

### B2. Nota de identidad de producto invertida — BUG de wording
- **Dónde:** `detection_engine.data_quality()` — decía "el {cov}% del revenue no tiene correspondencia" cuando `cov` es el % CON match. Con 75,2 % de match habría dicho "el 75,2 % no tiene correspondencia" (falso).
- **Corrección:** ahora dice "el {100 − cov}% del revenue no tiene correspondencia fiable (solo el {cov}% tiene match)".
- **Verificado:** "el 100.0% del revenue no tiene correspondencia fiable (solo el 0.0% tiene match)" en datos sin líneas.

### B3. Las dos bases de cobertura de coste no se diferenciaban en UI — UX
- **Dónde:** el dashboard solo mostraba la cobertura por revenue; la de Nº de productos no aparecía como % (solo conteo).
- **Corrección:** `cost_coverage()` expone `productsCoveragePct` + `productsTotal`; el dashboard muestra dos métricas etiquetadas:
  - **"Coste (por producto): 89,8 % (414 de 461 productos con coste real)"**
  - **"Coste (por revenue): 41,6 % del revenue con coste verificado"**
- Hermes también las distingue: "41.6% del revenue (1254.74€ de 3016.43€; 89.8% de los productos tienen coste — bases distintas)".

### B4. Dimensión "Calidad de datos" decía GOOD sin datos — BUG (UNKNOWN ≠ GOOD)
- **Dónde:** `health_scores()` — `datos` era GOOD incluso en instalación vacía.
- **Corrección:** GOOD solo si hay entidades reales que auditar (ordersTotal+productsTotal > 0); si no, UNKNOWN.
- **Verificado:** instalación nueva → todos los semáforos UNKNOWN; con datos → estados correctos.

---

## 3. CORRECCIONES PREVIAS REVALIDADAS (FASE VALIDACIÓN REAL)

- `moneyAtRisk` del motor: `None` (no 0) sin impacto cuantificado — confirmado.
- Priorización de `inconsistent_order_total` por magnitud de desvío — confirmado.
- Observación de findings con matiz "envío/impuestos/descuentos" — confirmado.

---

## 4. REGRESIÓN COMPLETA

| Verificación | Resultado |
|---|---|
| Suite completa de tests | **505 passed, 1 skipped** (+3 tests nuevos: cobertura doble base, nota identidad, datos UNKNOWN) |
| Benchmark congelado (FASE C) | **72 % estricto / 96 % con parciales / 0 FP** — SHA-256 intacto (`73e88ef1…`) |
| Instalación real de producción | Intacta: 461 productos / 100 ventas (solo lectura) |
| Importación idempotente | 2× → 461/414/99 idéntico, sin duplicados |
| Hermes sin prompt leaks | Tests anti-leak: 29 passed (contexto + operativo) |
| benchmark-data / GROUND_TRUTH / preguntas / resultados históricos | Sin tocar |

---

## 5. FLUJOS VERIFICADOS CON EL PAYLOAD REAL

- **Health Scores (empresa real):** ventas GOOD, margen CRITICAL, inventario UNKNOWN, clientes UNKNOWN, proveedores UNKNOWN, finanzas WARNING, datos CRITICAL — correcto.
- **Findings:** 6/6 con observación + evidencia + impacto + acción + qué falta.
- **Brief:** dinero en riesgo "—" (no 0 €), mayor problema = missing_cost (47 productos).
- **Hermes (4 preguntas):** cifras verificadas contra el motor (99 pedidos, 3.119,12 €, 41,6 %, 75,2 %, 62 entidades a revisión).
- **Instalación nueva:** semáforos UNKNOWN, sin findings inventados.

---

## 6. PROBLEMAS RESTANTES (no bloqueantes)

| Problema | Tipo | Acción recomendada |
|---|---|---|
| Importación CSV sin columnas de líneas → identidad/revenue 0 % | LIMITACIÓN DE DATOS | El tester debe importar con líneas (Shopify/FacturaScripts los incluyen); VANOVA lo declara honestamente |
| M02 (dependencia proveedor→SKU) no detectable | LIMITACIÓN DE DATOS | Trazabilidad proveedor→producto no sobrevive al import actual; documentado |
| 6 parciales del benchmark | LIMITACIÓN DE DATOS CONGELADOS | Evidencia ausente en datasets congelados; no se fuerza |
| Latencia LLM ~14–20 s | RENDIMIENTO | Modelo cloud; no bloqueante para beta controlada |
| Import con `ext` faltante → 0 filas | COMPORTAMIENTO ESPERADO | El escaneo real (`file_inventory`) siempre setea `ext`; solo afecta llamadas API manuales |

---

## 7. VEREDICTO

### 🟢 GO — LISTO PARA ENTREGAR AL TESTER (beta controlada)

**Razones:**
1. Los 4 bugs reales encontrados en esta auditoría están **corregidos y verificados con tests**.
2. Regresión completa en verde: 505 tests, benchmark congelado intacto (72 %/96 %/0 FP), instalación real intacta, import idempotente, sin leaks.
3. Los flujos críticos del tester funcionan de extremo a extremo con datos reales: importación → detección → dashboard → Hermes.
4. El sistema es honesto donde faltan datos: UNKNOWN nunca se muestra como 0 ni como GOOD.

**Condiciones para el tester (recomendadas):**
- Importar datos con **líneas de pedido** (productos, ventas con líneas, clientes) — no solo cabeceras.
- Conectar al menos una fuente con tesorería/facturas (FacturaScripts) para validar finanzas.
- Documentar cualquier hallazgo en el mismo formato de clasificación usado aquí (BUG / LIMITACIÓN / UX / etc.).

**No se ha publicado ninguna release.** Los cambios quedan en el working tree para tu revisión.

---

## 8. ARCHIVOS MODIFICADOS

- `desktop/runtime/detection_engine.py` — nota identidad invertida (B2), datos UNKNOWN sin entidades (B4), tests asociados
- `desktop/runtime/product_identity.py` — `productsCoveragePct` / `productsTotal` (B3)
- `desktop/runtime/agent_data_tools.py` — contexto Hermes con las dos bases + redondeo de € (B3)
- `desktop/runtime/hermes_chat.py` — DATA COVERAGE con bases diferenciadas (B3)
- `web/dashboard.html` (+ `index.html`, `dist/dashboard.html`) — "—" para UNKNOWN (B1), dos métricas de coste etiquetadas (B3)
- `tests/test_detection_engine.py`, `tests/test_product_identity.py` — +3 tests de regresión
- `scripts/_validation_export_source.py`, `scripts/_validation_import_source.py`, `scripts/_validation_hermes.py` — harness de validación (dev, aislado)
