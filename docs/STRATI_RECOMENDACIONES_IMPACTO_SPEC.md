# STRATI — SPEC: UI "Recomendaciones seguidas / Impacto" (ROI visible)

**Autor:** Strati (estrategia/producto)
**Para:** Nickx (dev) · QA (Mathew)
**Versión proyecto:** 3.0.8 · **Estado:** Propuesta aprobada por Boss — implementación pendiente
**Regla:** Documento de especificación. NO es código; no modifica el proyecto.

---

## 0. Resumen ejecutivo (por qué esto retiene y hace pagable)

El action-loop del ROI **ya existe en el backend**: `desktop/runtime/recommendation_store.py`
implementa `record_finding` → `set_status` (open→done) → `measure()` automático (→ outcome
`improved / no_change / worsened / unmeasurable`), con `metricBefore`/`metricNow` y
`measuredAt`. Está expuesto en API: `GET /api/recommendations` (listar) y
`POST /api/recommendations/status` (cambiar estado + re-medir). Y ya hay una sección en
`web/dashboard.html` que lista recomendaciones pendientes y cerradas.

**El gap es de PRODUCTO, no de motor:** el empresario **no ve el ROI** en €. Ve que marcó
"Realizada", pero no una pantalla que le diga *"estas 3 recomendaciones que seguiste te
sumaron ≈ X € de margen/revenue"*. Ese es exactamente el argumento de venta que falta.

Este spec describe la **pantalla "Recomendaciones seguidas / Impacto"** que consume ese
loop y lo convierte en valor visible. Cierra la cadena: **detectar → seguir recomendación →
ver impacto en € → retención**. Es la pieza P0 nº2; conecta con el SPEC del Detector
(`docs/STRATI_DETECTOR_OPORTUNIDADES_SPEC.md`): el Detector produce oportunidades; esta
pantalla demuestra qué se ganó al seguirlas.

---

## 2. Qué muestra (datos, estados)

### 2.1 Los 3 estados visibles (mapa a los estados reales del store)

| Estado UX | Estado backend (`status`) | Qué ve el empresario |
|---|---|---|
| **Sin seguir / Nueva** | `open` | Recomendación pendiente. CTA "Marcar en curso" |
| **En curso** | `in_progress` | El empresario está actuando. CTA "Marcar realizada" |
| **Seguida / Realizada** | `done` | Marcada como hecha; auto-medición activada |
| **Con impacto** | `measured` | Outcome visible + delta € (o "no medible") |
| **Cerrada (descartada/resuelta)** | `not_done`, `resolved` | Sección colapsable (ya existe) |

> **Estado real ya presente:** `VALID_STATUSES` en `recommendation_store.py` define
> `open/in_progress/done/not_done/resolved`, y `measure()` transiciona `done → measured`
> fijando `outcome`. La UI debe mostrarlos con copy ES (no crudo): "Nueva / En curso /
> Realizada / No realizada / Resuelta / Con impacto".

### 2.2 Campos que consume la pantalla (del record real del store)
| Campo backend | Uso en UI |
|---|---|
| `id` | identidad (para `POST /api/recommendations/status`) |
| `title` | título de la recomendación |
| `recommendedAction` | acción sugerida |
| `findingType` | icono/tipo (cross_sell, product_concentration, aov_…, low_revenue_high_margin…) |
| `status` | estado (ver tabla) |
| `outcome` | `improved/no_change/worsened/unmeasurable/None` |
| `metricBefore`, `metricNow` | para calcular delta € cuando hay revenue comparable |
| `measuredAt` | cuándo se midió |
| `createdAt` | cuándo se creó la recomendación |
| `dismissedAt`/`resolvedAt` | sección cerrada |

### 2.3 Tarjeta de recomendación (layout)
1. **Estado pill** (arriba izq): "Nueva" / "En curso" / "Con impacto" / "Cerrada".
2. **Título** + acción recomendada (texto, ES).
3. **Resultado medido (cuando aplica):** badge `mejoró / sin cambio / empeoró / no medible`.
4. **ROI en € (cuando calculable):** "≈ +X € en revenue respecto a cuando la creaste".
5. **CTAs por estado:**
   - `open` → "En curso" / "Realizada"
   - `in_progress` → "Marcar realizada"
   - `done`/`measured` → "Ver detalle"
   - `not_done`/`resolved` → (sección cerrada, ver historial)

---

## 3. Copy ES (corporate, sin emojis de color)

### Encabezado de sección
- Título: **"Recomendaciones seguidas"**
- Subtítulo: "Lo que te sugerimos y el impacto de lo que ya hiciste. El resultado se
  mide sobre los datos reales, no con promesas."

### Estados (badges)
| Backend | Copy ES |
|---|---|
| `open` | **Nueva** |
| `in_progress` | **En curso** |
| `done` | **Realizada** |
| `measured` + `outcome=improved` | **Resultado: mejoró** |
| `measured` + `outcome=no_change` | **Resultado: sin cambio** |
| `measured` + `outcome=worsened` | **Resultado: empeoró** |
| `measured` + `outcome=unmeasurable` | **Sin dato comparable** |
| `not_done` | **No realizada** |
| `resolved` | **Resuelta** |

### ROI € (regla honesta)
- Si hay delta revenue comparable (metricBefore/Now ambos con revenue): muestro
  `"+X € vs el momento en que la marcaste"`.
- Si no hay métrica comparable → **"Sin dato comparable para medir el impacto"** — NUNCA
  un 0 € ni una cifra inventada (`UNKNOWN ≠ 0`).

### Empty state honesto
"VANOVA recomienda, tú decides. Marca 'Realizada' una recomendación y verás aquí el
impacto medido con tus datos reales. Aún no hay recomendaciones seguidas."

### CTA de recuperación
- Enlace "Ver oportunidades pendientes" → conecta con la vista del Detector
  (SPEC de Oportunidades), cerrando el bucle en la UI.

---

## 4. Requisitos para dev

### 4.1 Estado "seguida" — dónde se guarda
Ya está persistido por `recommendation_store` en el config (`config_store`), con estados y
timestamps (`doneAt`, `measuredAt`, `dismissedAt`, `resolvedAt`). **No hay que crear una
nueva tabla**: la pantalla lee `list_recommendations()` vía `GET /api/recommendations` y
cambia estado vía `POST /api/recommendations/status` (que auto-mide al marcar done).

### 4.2 Cómo medir el impacto
- `measure()`/`measure_all()` ya releen la métrica canónica de la entidad y clasifican
  `outcome`. Reutilizar tal cual; **no duplicar lógica de medición**.
- Para el **delta € en UI**, calcular en frontend (o pequeño helper): si
  `metricBefore.revenue` y `metricNow.revenue` son ambos > 0 → `delta = metricNow.revenue -
  metricBefore.revenue`; mostrarlo con signo y formato EUR es-ES. Si no → "sin dato comparable".

### 4.3 Archivos candidatos (referencia; Nickx decide)
- `web/dashboard.html` + `web/data-services.js` — nueva vista/pestaña "Recomendaciones
  seguidas" (o bloque en Insights). Ya hay sección de recomendaciones cerradas; integrar.
- `web/dist/*` — sincronizar build (patrón BUG-003).
- Backend **sin cambios funcionales** salvo que Nickx detecte un gap de datos; el loop ya
  existe y está testeado.

### 4.4 Decisiones que DEBE tomar Nickx (confirmar con Boss)
- ¿Pestaña propia "Seguimiento" en nav, o bloque dentro de Insights? (prefiero pestaña
  propia, accesible desde Home, para dar protagonismo al ROI.)
- ¿Endpoint dedicado de "resumen de impacto total" (`GET /api/recommendations/impact`) para
  mostrar un **total en €** ("≈ X € capturados hasta ahora")? Prefiero sí: es el gran titular
  de retención. Puede sumar `metricNow.revenue - metricBefore.revenue` de las `measured`
  con `outcome=improved`.
- Frecuencia de refresco/automedida (ya hay `measure_all()` en el flujo de análisis).

---

## 5. Cómo se probaría (QA — Mathew)

### 5.1 Automático (acumulativo)
- `tests/test_recommendations_impact_ui.py` (o ampliar los existentes de
  `recommendation_store`):
  - `set_status(rec,"done")` → status `measured` + `outcome` en {improved/no_change/worsened/unmeasurable} (ya cubierto, mantener).
  - Delta €: helper de cálculo devuelve número cuando hay revenue comparable; `None`/no
    comparable cuando falta (nunca 0 €).
  - Endpoint `/api/recommendations/status` con `done` devuelve el record re-medido (regresión).
  - `GET /api/recommendations/impact` (si se implementa): total con solo `improved`, sin FP.
- Suite completa en verde (671+ tests acumulativos).

### 5.2 Manual (Mathew, checklist UX)
1. Marcar una recomendación como "Realizada" → pasa a "Con impacto" y muestra outcome.
2. Con datos sin revenue comparable → "Sin dato comparable", nunca 0 €.
3. Dos recomendaciones mejoradas → el total del resumen suma correctamente.
4. Copy en ES, sin emojis de color, responsive (incluye móvil).

---

## 6. Conexión con el Detector de Oportunidades (bucle de valor)

```
Detector (P0 nº1)            →  Recomendaciones seguidas (P0 nº2)
  cruza señales con €           lee list_recommendations() + outcome
  emite opportunity/cross-sell  muestra "mejoró / no cambió / empeoró"
                                 + delta € real o "sin comparable"
```
- El Detector **crea** la oportunidad (recomendación); esta vista **la cierra con ROI**.
- El **total capturado** es el titular comercial: "X € en valor medido gracias a VANOVA".
- Solo cuando este loop se ve en UI se puede cobrar por "oportunidades + seguimiento"
  (niveles de pricing): el diagnóstico es teaser, el ROI demostrado es la suscripción.

---

*Documento de especificación generado por Strati. No modifica el proyecto. Aprobado por
Boss (2026-08-20); pendiente de review/decision de Nickx.*
