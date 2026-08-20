# VANOVA QA AUDIT — Auditoría QA de producto (E2E con datos reales)

Fecha: 2026-08-19 · Entorno: sandbox aislados (`/tmp/qa*`, `LOCALAPPDATA` propio) + producción leída sin modificar.
Método: ejecutar cada flujo crítico E2E con datos reales/representativos, NO dar por bueno un flujo porque los tests pasen.

---

## 1. Flujos auditados y resultado

| # | Flujo | Resultado | Evidencia |
|---|-------|-----------|-----------|
| 1 | Import E2E: import → modelo → detección → insights → prioridades → recomendaciones → medición | ✅ PASS | Cadena completa en sandbox con datos reales (fase previa + esta auditoría): 6 findings, 11 insights dedup, 3 prioridades, contexto Hermes con cifras coincidentes |
| 2 | Revenue periodos Todo/Mes/Trimestre/Año coherentes | ✅ PASS | 50 ventas = 1.625 € cuadran con el desglose; `salesSummary` se calcula al vuelo, no hay resumen vacío |
| 3 | Finanzas (invoices/treasury/reconciliation) | ✅ PASS | Shape real verificado contra la vista frontend; cifras coherentes |
| 4 | Re-import idempotente | ✅ PASS | 1ª import: 50 ventas / 20 productos · 2ª import: idéntico (preserved 50/20) · `IDEMPOTENT: True` |
| 5 | Persistencia tras reinicio | ✅ PASS | Recarga de config tras "cerrar/abrir" mantiene 50 ventas / 20 productos |
| 6 | Scanner de archivos | ✅ PASS | Detecta ventas.csv + productos.csv, descarta notas.txt, estado running → idle/done sin error |
| 7 | Factory reset | ✅ PASS | Backup + limpieza correctos (verificado en fase anterior de esta auditoría) |
| 8 | Notificaciones / badge canónico | ✅ PASS | `updateBellBadge` solo cuenta findings `kind=finding` status `new` posteriores a `notifSeenAt` + aprobaciones pendientes; abrir el centro marca leído y persiste en `uiPrefs` |
| 9 | Hermes casual vs empresarial | ✅ PASS | Casual: 0 ms (sin operational context). Empresarial: 3,4 s frío / 0 ms cálido (caché 10 s) |
| 10 | Anti-leak de Hermes | ✅ PASS | Sanitizador elimina bloques `[Contexto VANOVA`, `BUSINESS HEALTH`, etc. y conserva la respuesta real (verificado con parámetros reales del caller) |
| 11 | Recomendaciones seguidas | ✅ PASS | `record_finding` dedup estable por firma (re-registro → mismo ID, count=1); `set_status(done)` auto-mide → `outcome: unmeasurable` (UNKNOWN honesto, nunca 0) |
| 12 | Action center (preparar acciones) | ✅ PASS | Solo lectura + audit trail; `prepare("costs")` devuelve plantilla o `ok:false` sin datos — nunca inventa |

---

## 2. Hallazgos

### 2.1 Bugs reales encontrados y corregidos en esta auditoría

No se encontró ningún bug que rompa un flujo crítico. Un artefacto del harness de pruebas (no del producto) causó dos falsos positivos iniciales, descartados:

1. **`_extract_sales` devolvía 0 filas** → la causa era pasar `ext=".csv"` (con punto) en mi harness; el caller real pasa `"csv"`. Con el parámetro correcto extrae 50/50. **No es bug.**
2. **`_strip_prompt_leak` parecía borrar la respuesta** → mi test pasaba `action_hint=""`; el caller real pasa el hint + contexto + mensaje reales, y con esos parámetros el sanitizador conserva la respuesta y corta solo el leak (verificado: CASE1/CASE2/EDGE1/EDGE3). **No es bug.**
3. **`revenue`/`importSummary` KeyError** → el shape real de `organize_files` es `{ok, organization, products, sales, customers, salesReview}`; `importSummary` vive dentro de `organization`. **No es bug**, solo lectura incorrecta del harness.

### 2.2 Observaciones (no bloqueantes)

| ID | Severidad | Área | Observación |
|----|-----------|------|-------------|
| QA-01 | 🟡 Mejora | Rendimiento | El build frío del contexto empresarial de Hermes tarda ~3,4 s: dominado por `health_monitor.check_all` (3,3 s) y `agent_architect.list_agents` (1,8 s), sondas con timeout cuando los servicios no corren. Con caché (TTL 10 s) la siguiente pregunta es 0 ms. En producción con servicios activos es más rápido. No es un bloqueo. |
| QA-02 | 🔵 Limitación | Rendimiento | El coste frío es inherente a sondear servicios reales (timeout de red). Una pregunta casual NO paga ese coste (0 ms). |

---

## 3. Verificaciones de integridad

- **Suite completa**: 636 passed, 1 skipped, 0 fallos (86,9 s).
- **Producción intacta**: 461 productos / 100 ventas / dataVersion 3.0.0 (leída sin escribir).
- **Benchmark congelado intacto**: GROUND_TRUTH.md md5 `01be6228…` (coincide con el hash congelado).
- **Sin release publicada** · **sin cambios en benchmark/GROUND_TRUTH/resultados históricos**.

---

## 4. Veredicto

### 🟢 LISTO PARA BETA (con reservas menores de rendimiento)

**Por qué:**
- Todos los flujos críticos de producto pasan E2E con datos reales: importación idempotente, persistencia, análisis proactivo, priorización, insights, recomendaciones con medición honesta, acciones preparadas con audit trail, notificaciones sin spam, scanner, reset, Hermes con contexto estructurado y anti-leak verificado.
- **UNKNOWN ≠ 0** confirmado en toda la cadena: `outcome: unmeasurable`, impacto "no cuantificable", findings sin evidencia no se emiten.
- No hay bugs conocidos que bloqueen a una empresa real.

**Reservas (no bloqueantes):**
- QA-01: primera pregunta empresarial a Hermes puede tardar ~3,4 s extra en frío (sondas). No afecta a casual.
- FacturaScripts sigue pendiente de validación contra el servidor real del cliente (declarado NO VALIDADO E2E hasta entonces).

**Acción recomendada antes de beta ampliada:** considerar cachear `health_monitor.check_all` con TTL más largo (p. ej. 15–30 s) para reducir el coste frío, sin cambiar comportamiento.

---

## 5. Qué se probó esta fase (E2E real, no mocks)

1. Import de CSV reales (ventas + productos) → conteos correctos.
2. Re-import del mismo archivo → 0 duplicados.
3. Recarga tras reinicio → datos persistentes.
4. Scanner con carpeta configurada → detecta/discarta correctamente.
5. Recomendación: registrar → dedup → marcar realizada → auto-medición honesta.
6. Action center: preparar plantilla de costes (solo lectura).
7. Hermes: casual 0 ms / empresarial 3,4 s frío / 0 ms cálido; anti-leak conserva respuesta.
8. Badge de notificaciones: solo findings nuevos + aprobaciones.
9. Finanzas: cifras coherentes con el motor.
10. Reset: backup + limpieza.
