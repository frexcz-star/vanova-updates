# ESTADO DE VALIDACIÓN QA — Tareas 1 y 3 (MVP vendible)

Este fichero es la fuente de verdad escrita del veredicto de QA. NO depende
de memoria de sesión: se actualiza cuando Mathew reporta, y Boss/Nico leen
este archivo.

## Estado actual: VEREDICTO QA de Mathew registrado (revalidado 2026-08-22, release 3.1.3)

### VEREDICTO_TAREA_1: FUNCIONA (revalidado en 3.1.3)
Onboarding "aha" + flujo de costes. Revalidado por QA con evidencia real (ejecución del motor en 3.1.3):
- Con coste real por SKU → `5 con EUR (calc=5)`, impactKind `calculated` (41.26 €, 39.18 €, 36.91 €).
- Sin coste por SKU + margen global 40% → `3 con EUR (est=3)`, impactKind `estimated` (30.4 €, 28.8 €, 27.2 €).
- Nunca se inventa 0 €: pares sin margen/coste quedan `not_quantifiable` (UNKNOWN ≠ 0).
- Recorrido end-to-end: conectar → coste (CSV por SKU) o margen global (1 campo) → motor emite findings → catálogo cuantifica €. Cálculo instantáneo (<15 min).
- Wizard usable por no-técnico (fases en español, cada una dice el dato que falta + botón).
- FECHA_VEREDICTO: 2026-08-22 (revalidado tras release 3.1.3).

### VEREDICTO_TAREA_3: FUNCIONA (mecanismo) / ROI real NO validado en producción
UI "Valor Capturado" (release 3.1.2/3.1.3). Validado por QA (evidencia real de ejecución):
- Endpoint real (no mock) con rec `measured+improved` (delta +50) + `no_change` → `_recommendations_impact()` = `{"capturedEuro": 50.0, "improvedCount": 1, "noChangeCount": 1}`.
- El ciclo marcar-hecho → medir → delta € funciona con deltas metricBefore/metricNow reales; `capturedPct` solo se calcula con € capturado + facturación real.
- En vivo: `capturedEuro: 0.0` (entorno MOOVING: 414 productos, 0 ventas) — vacío honesto, no inventa "0 €" ni mock.
- **ROI real en producción NO validado:** falta un cliente real que cargue ventas+costes, marque "hecho" y se mida el delta. No es bug de código; es falta de dato real de cliente.
- FECHA_VEREDICTO: 2026-08-22 (sin cambios en 3.1.3 — el fix de 3.1.3 es de autenticación Shopify, no toca este flujo).

### VEREDICTO_TAREA_2 (EMPAQUETADO / piloto PC stock): PENDIENTE de Nico
- Núcleo autocontenido verificado por Developer (bundle embebido, HTTP 200).
- Plan accionable documentado en `docs/PILOTO_FISICO_NICO.md` (requisitos del PC, pasos de instalación del .exe, 4 preguntas de reporte con capturas/logs). Revisado por QA: es accionable.
- Piloto físico en PC stock PENDIENTE de Nico. No se ejecuta por QA.

## Instrucciones de despacho (para reenvíos)
Despacho de validación enviado a Mathew vía `hermes -p mathew chat` en background
(procesos background no persisten entre turnos; por eso este fichero es la
constancia). Al recibir el veredicto de Mat, actualizar:
- `VEREDICTO_TAREA_1: FUNCIONA | FALLA (detalle)`
- `VEREDICTO_TAREA_3: FUNCIONA | FALLA (detalle)`
- `FECHA_VEREDICTO: YYYY-MM-DD`

## Definición de "MVP cerrado" (para CHANGELOG/README)
- [x] Tarea 1 validada por QA (veredicto FUNCIONA, 2026-08-22).
- [x] Tarea 3 validada por QA (mecanismo FUNCIONA; ROI real en producción pendiente de cliente con datos — ver doc).
- [ ] Tarea 2 piloto físico reportado por Nico (docs/PILOTO_FISICO_NICO.md) — plan accionable verificado por QA.
- [x] Suite en verde (744 passed, 1 skipped, verificado por QA 2026-08-22).
Solo cuando las 4 casillas estén cumplidas con evidencia real (no inventada),
marcar "MVP cerrado" en CHANGELOG/README.

---
*Documento de estado preparado por Hermes (Developer). No afirma resultados
que no se hayan ejecutado.*
