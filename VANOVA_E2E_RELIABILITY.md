# VANOVA_E2E_RELIABILITY — Fiabilidad de extremo a extremo

Fecha: 2026-08-19 · Proyecto: 3.0.0 · Benchmark congelado intacto (72% / 96% / 0 FP) · Producción byte-idéntica (SHA c43ed3a13e35)

---

## 1. Qué se ha probado con datos reales

**Ciclo completo, ejecutado en sandbox aislado con los datos reales de la empresa tester (461 productos / 100 ventas):**

```
DETECCIÓN (0.1 s) → RECOMENDACIÓN (missing_cost: 47 productos sin coste) →
marcada REALIZADA → auto-medición (⚪ NO MEDIBLE: sin métrica por SKU — honesto) →
ACCIÓN REAL: plantilla → aplicar 47 costes (preview 47/47 → apply con backup) →
RE-ANÁLISIS → la condición desaparece (missing_cost ya no se detecta) →
RECOMENDACIÓN RESUELTA («la condición detectada ya no está presente en los datos»)
```

Tiempos reales: detección 0.097-0.100 s · contexto Hermes frío ~4 s (cálido ~0 s) · sync FacturaScripts 0.8-19 s (retries) · importación de costes instantánea.

## 2. FacturaScripts — estado honesto

- **Validado contra servidor HTTP REAL** (nuevo `tests/test_facturascripts_real_http.py`, 4/4): un servidor local que implementa la API `/api/3` de FacturaScripts (no mocks del transporte). Se probó sobre HTTP real: probe `/api/3`, autenticación por Token, fetch + paginación de los 8 recursos, normalización al modelo canónico (proveedores, facturas emitidas/recibidas, líneas, cobros/pagos), persistencia con dedupe y detección posterior.
- **Casos de fallo reales cubiertos**: token inválido → error estructurado de autenticación; respuesta HTML → NUNCA se cuenta como conexión válida; servidor inalcanzable → error estructurado (nunca excepción).
- **PENDIENTE (explícito)**: el servidor REAL del cliente no está disponible en este entorno (sin URL ni API key). El conector está validado contra un servidor FS-compatible; la validación end-to-end con la instancia del cliente sigue abierta y es el único bloqueo honesto que queda para declarar FacturaScripts «validado».

## 3. Medición automática de recomendaciones

- **`measure_all()`**: el análisis recurrente (cada 6 h), `/api/business/analyze` y el post-import de costes re-miden automáticamente las recomendaciones `done`/`measured` (evolución en el tiempo) con los datos canónicos actuales. `resolved` nunca se re-mide (ciclo cerrado).
- **`sync_resolutions()`**: cuando la condición que originó una recomendación ya NO se detecta, pasa a `resolved` con motivo honesto — sin atribuir causalidad.
- **Bug real encontrado y corregido**: `run_detection` conserva findings históricos con `lastSeenAt` viejo; al pasar la lista *merged* a insights/recomendaciones, las condiciones desaparecidas NUNCA se resolvían. Solución: `run_detection` ahora expone `freshSignatures` (detectadas en esta ejecución) y `sync_from_findings`/`sync_resolutions` reciben las firmas frescas. Verificado en el E2E: tras importar los 47 costes, `missing_cost` sale de `freshSignatures` y la recomendación se resuelve.
- **UNKNOWN ≠ 0**: la recomendación de costes marcada como realizada quedó `NO MEDIBLE` (no hay métrica por SKU comparable), no un resultado inventado. `measure()` distingue mejoró/empeoró/sin cambio/no medible.

## 4. Hermes como agente operativo

- El contexto operacional ahora incluye **ACCIONES DISPONIBLES** (plantilla de costes, segmento de reactivación, aplicar costes) con la instrucción explícita: proponer el siguiente paso concreto con impacto esperado, mostrar exactamente qué va a cambiar, **pedir confirmación antes de ejecutar nada externo**, registrar qué hizo y anunciar que el resultado se medirá en el próximo análisis.
- **Acción ejecutable real conectada a la UI**: en la vista Recomendaciones, una recomendación de costes tiene el botón **«Aplicar costes»** que abre un drawer con la plantilla editable → `previsualizar` (plan sin escribir: coincidencias/nuevos/cambios/ambiguos) → `confirmar` (backup automático + audit trail) → aplicar → **re-análisis automático → medición/resolución**. Es el cierre real del ciclo decisión → acción → resultado; nada se ejecuta sin confirmación.
- El backend `/api/costs/import` y `/api/business/analyze` cierran el ciclo también fuera de la UI (el mismo flujo queda operativo por API).

## 5. Feature desconectada encontrada y arreglada

`DataServices.previewCostsImport`/`importCosts` existían en el cliente API pero **no tenían ninguna UI** (nadie las llamaba). Se conectaron al flujo «Aplicar costes» de la vista de recomendaciones. Verificado por smoke test de render (nodo) con y sin recomendaciones.

## 6. Tests

- **636 passed, 1 skipped, 0 fallos** (antes: 632). Nuevos: `tests/test_facturascripts_real_http.py` (4, servidor HTTP real) + cobertura del lifecycle extendida en los existentes.
- **Producción byte-idéntica** tras la suite. Benchmark congelado intacto. Sin release.

## 7. Qué sigue sin estar validado / no demostrado

| Item | Estado |
|---|---|
| FacturaScripts con el servidor REAL del cliente | ⚠️ PENDIENTE (necesita URL + API key) |
| Medición en el tiempo (semana/mes) | ✅ Mecánica implementada (re-medición automática); el resultado real de «mejoró/empeoró» requiere datos que evolucionen en el tiempo — no se puede demostrar con un snapshot |
| Acciones externas más allá de costes (precios, emails) | ❌ No operativo por diseño (requiere permisos + confirmación; solo se preparan) |
| Atribución de causalidad | ✅ Nunca se hace: `resolved` solo dice que la condición ya no está presente |

## 8. Bugs reales encontrados en esta fase

1. **Lifecycle bloqueado por findings stale** (insights y recomendaciones nunca se resolvían) → `freshSignatures` + `sync_resolutions`.
2. **Cost-import sin UI** (feature muerta) → drawer «Aplicar costes» conectado.
3. **`measure()` dejaba la recomendación en `done` con outcome en la rama no-medible** → comportamiento coherente (Realizada + ⚪ No medible), documentado.

## 9. Veredicto

La cadena **detectar → recomendar → confirmar → actuar → re-analizar → medir → resolver** está cerrada y demostrada con datos reales para la vía de costes (la única acción ejecutable segura con datos disponibles). FacturaScripts está validado contra servidor HTTP real y falla de forma estructurada; queda pendiente únicamente la validación con la instancia real del cliente. **Recomendación: proceder a la beta con la empresa tester; antes de una beta más amplia, validar FacturaScripts con el servidor real del cliente.**
