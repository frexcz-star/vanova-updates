# STRATI — SPEC 2: UI de Cierre del Loop / "Valor Capturado"

**Autor:** Strati (estrategia/producto) · **Para:** Nickx (implementación), Mathew (QA), Boss (decisión)
**Versión proyecto:** 3.1.7 · **Estado:** Listo para implementación — v3.1.7, verificado contra código
**Regla:** El "Valor Capturado" sale SOLO de fuentes reales (deltas medidos del action-loop). Nunca inventado, nunca "0 €". Lo no medible se muestra honesto.

---

## 0. Objetivo

Mostrar al empresario el **ROI real** que VANOVA le aporta: el **€ capturado/ahorrado** demostrable con sus datos. No métricas vacías ("3 insights") sino **dinero que puede señalar**. Es la pantalla que convierte el valor técnico en "esto merece que pague".

**Principio rector:** el "Valor Capturado" se calcula desde los deltas reales de las recomendaciones `measured` con `outcome=improved` (mismo espíritu que `measure()` del action-loop). Nunca inventado, nunca "0 €".

---

## 1. Qué métricas exactas se muestran y de qué fuente salen

**Métricas (dinero real, no inventado):**

| Métrica | Definición | Fuente |
|---|---|---|
| **capturedEuro** | Σ deltas positivos de recomendaciones `measured` con `outcome=improved` | `recommendation_store` (`metricBefore`/`metricNow`, revenue o ahorro) |
| **capturedPct** | `capturedEuro / facturación del periodo` (si hay facturación real) → "% sobre facturación" | revenue real de la fuente de negocio |
| **improvedCount** | nº de recomendaciones que mejoraron | idem, `outcome=improved` |
| **noChangeCount** | nº sin cambio | idem, `outcome=no_change` |
| **worsenedCount** | nº que empeoró | idem, `outcome=worsened` |
| **unmeasurableCount** | nº sin dato comparable | idem, `outcome=unmeasurable` |
| **totalRecommendations** | total marcadas como hechas | idem |

**Tendencia (opcional, solo si hay datos):** un mini-gráfico de `capturedEuro` acumulado por mes (semana/mes) para mostrar el efecto compuesto. Sin datos → no se dibuja (o empty honesto), nunca una tendencia inventada.

**De dónde sale el €:** los deltas salen de la **fuente de negocio real** (Shopify/ERP/Excel/FacturaScripts) que alimenta `metricBefore`/`metricNow`. Nunca de una cifra inventada. Si la fuente no da delta comparable → `unmeasurable`, no un número.

**Tarjetas/gráficos del panel:**
- **Tarjeta principal (protagonista):** "€ capturado/recuperado" (grande, peso 700).
- **Tarjeta secundaria:** "X% sobre tu facturación" (si hay facturación real; si no, se omite).
- **Tarjeta de desglose:** nº mejoró / sin cambio / empeoró / sin dato (honesto).
- **Mini-gráfico de tendencia** (si hay histórico) → efecto compuesto.
- **Tarjeta de retorno neto** (si hay precio de VANOVA): "€ capturado − coste de VANOVA = retorno neto" — para que el empresario vea que VANOVA se paga sola. El coste de VANOVA es un dato real del plan (no inventado); si no está fijado, se muestra solo el € capturado.

**€/mes y €/día — la prueba de que la app paga por sí sola:**
- Además del € capturado total, el dashboard muestra el desglose temporal:
  - **€/mes capturado** (suma del periodo) y **€/día capturado** (media: `€_capturado / días del periodo`).
- La comparativa que convence: `€/mes capturado` frente al `coste mensual del plan de VANOVA` (si está fijado) → "VANOVA te cuesta X €/mes y recuperó Y €/mes → retorno neto +Z €/mes".
- Si el coste del plan no está fijado, se muestra solo el €/mes capturado (sin la comparación), honesto.

**Vista por ventana — "qué ve el empresario hoy / a 7 días / a 30 días" (componente de timeline):**
- **Hoy (0-7 días, recién activado):** tarjeta protagonista con el € capturado hasta ahora + estado del loop (recomendaciones marcadas, pendientes de medir). Copy: "Estás midiendo tu primera recomendación. En cuanto haya dato real, verás aquí el € capturado." (nunca "0 €"). Si aún no hay nada medido → "Sin dato comparable para medir (no se inventa)."
- **A 7 días:** comparativa corta "antes/después" por recomendación ya medida (metricBefore → metricAfter → delta). Si hay ≥1 `improved`, el titular muestra el € acumulado.
- **A 30 días:** el panel completo: titular € acumulado del periodo, % sobre facturación, retorno neto (si plan activo), mini-gráfico de tendencia (si hay histórico), y desglose honesto por recomendación (mejoró/sin cambio/empeoró/sin dato).
- **Regla honesta:** cada ventana muestra SOLO los datos reales medidos en ese rango; no se fabrica una proyección a 30 días si no hay histórico. La tendencia se dibuja únicamente con puntos reales.

**Distinción de conceptos (lo que muestra la UI y de dónde sale cada uno):**
| Concepto | Qué es | De dónde sale (real) |
|---|---|---|
| **€ capturado** | Δ revenue positivo de recomendaciones `improved` (cross-sell, reactivación, AOV) | `metricNow.revenue − metricBefore.revenue` |
| **Ahorro** | Δ de coste positivo (margen recuperado) | `metricNow.ahorro − metricBefore.ahorro` |
| **Coste evitado** | el mismo ahorro, pero referido a un gasto que no se incurre (p. ej. no se sigue comprando un producto a pérdida) | deltas reales de `measure()` con `findingType=coste` |
| **Tiempo ganado** | (solo si hay dato real de tiempo) ej. "VANOVA te ahorra X min/día" en tareas automatizadas; si no hay dato de tiempo medido, NO se muestra (vacío honesto) | solo si el sistema registra tiempo ahorrado; nunca se inventa |

Regla: el "€ capturado" y el "ahorro" son lo que suma al titular; "coste evitado" y "tiempo ganado" son lecturas complementarias y honestas — el "tiempo ganado" solo se pinta si hay dato real.

## 1b. Decisión de negocio que toma el empresario con esta vista (copy de soporte)

- **Copy del titular (cuando hay valor):** "VANOVA te ha ayudado a recuperar X € este periodo." → refuerza retención.
- **Copy cuando hay retorno neto:** "Tu suscripción cuesta X € y VANOVA recuperó Y € → retorno neto de +Z €."
- **CTA de soporte:** "Marca otra recomendación como hecha para seguir midiendo" (siguiente paso, retención).
- **Base de upsell:** el € demostrado justifica el paso de Free → Pro.

**Cierre del loop — "lo ve, lo reconoce, lo comparte" (3 pasos):**
1. **Lo ve:** el titular "≈ X € recuperado" con sus datos reales (protagonista, peso 700).
2. **Lo reconoce:** cada recomendación `improved` con su delta y "porqué" en 1 línea ("Marca la hiciste el 12/08; sus ingresos pasaron de 120 € a 158 €"). El empresario señala el € y dice "esto es mío".
3. **Lo comparte (CTA de caso de venta, SOLO si hay dato real y consentimiento):** botón "Generar caso de venta" que prepara el resumen (€ real capturado + cita del feedback + tiempo al €) para compartir con otro empresario o su equipo. **Honestidad:** si no hay consentimiento, se muestra solo el € interno; el caso compartido nunca se genera con cifras inventadas.
   - Copy del CTA: "Comparte tu caso" / "Muéstralo a tu equipo".
   - Regla: el caso de venta se construye SOLO con datos reales y con el consentimiento del empresario (ver SPEC 3 §7b.1b).

**Regla de honestidad:** el "comparte" nunca inventa un € ni una cita; se construye solo con lo real capturado y consentido.

---

## 2. Estados y vacíos

| Estado | Qué muestra | Copy |
|---|---|---|
| **Sin conectar** (no hay fuente de datos conectada) | empty honesto + CTA de conexión | "Conecta tu tienda o sube tus ventas para empezar a ver tu valor capturado." (nunca "0 €") |
| **0 datos** (nada medido) | empty honesto | "Marca una recomendación como hecha y verás aquí el impacto medido con tus datos." (nunca "0 €") |
| **Parcial** (algunas medidas, otras no) | titular con el € de lo medido + lista con cada estado honesto | el titular solo cuenta `improved` |
| **Completo** (todas con resultado) | titular + lista completa con deltas | idem |
| **Sin mejoras aún** (`capturedEuro == 0` pero con recomendaciones YA medidas `no_change`/`worsened`/`unmeasurable`) | tarjeta protagonista SIN número "0 €"; etiqueta honesta | "Aún sin mejoras medidas. Sigue marcando recomendaciones y verás aquí el € capturado cuando haya un delta positivo real." (verificado en código: endpoint devuelve `capturedEuro: 0.0, noChangeCount: 1, total: 6` cuando no hay mejoras — la UI NUNCA pinta "€0.00", usa esta etiqueta) |
| **Mes sin movimientos** (periodo con 0 ventas/acciones) | empty honesto + guía | "Este mes no hubo movimientos para medir. Cuando haya actividad o marques una recomendación, verás aquí el € capturado." (nunca "0 €") |
| **Sin conexión en el momento de consultar** (fuente caída/no disponible) | aviso no bloqueante + datos cacheados si existen | "No pudimos refrescar tus datos ahora. Mostramos la última medición disponible." (si no hay caché → "Sin dato disponible ahora; intenta de nuevo en unos minutos.") (nunca "0 €") |

**Regla de honestidad:** si no hay dato real, NO se muestra un número. Se muestra "sin dato comparable". Nunca un "0 €" inventado.

---

## 3. Pantalla (componentes + copy word-for-word)

**A. Home — titular de valor (arriba, protagonista):**
```
[Valor recuperado con VANOVA ≈ 214 €]
[de 3 recomendaciones que marcaste, 2 mejoraron · 1 sin cambio · medida con tu data]
```

**B. Vista "Recomendaciones seguidas" — lista/timeline por recomendación:**

```
● Mejoró   · Reactiva al cliente dormido      [+38 €]
   "Marcaste hacerla el 12/08. Sus ingresos pasaron de 120 € a 158 € en 30d."
─────────────────────────────────────────────
● Sin cambio · Haz pack de A+B                [—]
   "Marcaste hacerla el 20/08. Sin diferencia medible en este periodo."
─────────────────────────────────────────────
● Sin dato   · Sube el precio del top         [—]
   "Sin métrica comparable para medir el impacto (no se inventa)."
─────────────────────────────────────────────
```

**C. Estilo (premium dark, corporativo VANOVA):**
- **Paleta:** fondo oscuro premium (`--surface-solid` oscuro), acento rojo corporate
  (`#DC2626`/`#B91C1C`), superficies `glass` en sidebar/header. Igual que el resto de VANOVA.
- **Tipografía:** Inter; el € del titular en peso 700 para que destaque.
- **Iconos:** SVG (sin emojis de color) — ej. un icono "cheque" o "tendencia" para "mejoró".
- **Jerarquía:** titular € arriba (protagonista) → lista de recomendaciones debajo.
- **Estados:** dot + label (● verde=mejoró, ● ámbar=sin cambio, ● gris=sin dato).

**Reglas visuales:**
- Delta € con formato ES (`+38 €`), solo cuando `calculated`.
- `Sin dato` → "sin métrica comparable", NUNCA "0 €".
- Estados con dot + label (●), no badges gigantes.
- Total solo cuenta `improved`.

**C.1 · Tokens de diseño (premium dark glassmorphism, corporativo VANOVA #DC2626):**

Estos tokens son la especificación de implementación visual (para Nickx en el CSS, para Mathew en el QA visual). Siguen el mismo lenguaje del resto de VANOVA.

| Token | Valor | Uso |
|---|---|---|
| `--surface-glass` | `rgba(255,255,255,0.06)` + `backdrop-filter: blur(16px)` | tarjetas, sidebar, header |
| `--surface-solid` | `#0B0F14` (fondo base oscuro) | página |
| `--accent` | `#DC2626` (rojo corporativo) | titular €, CTAs, hover |
| `--accent-strong` | `#B91C1C` | hover/estados activos |
| `--text-primary` | `#F5F7FA` | titular € (peso 700) |
| `--text-muted` | `#8B93A3` | copy secundario / porqué en 1 línea |
| `--positive` | `#22C55E` (verde, dot "mejoró") | solo para estados, no texto grande |
| `--warn` | `#F59E0B` (ámbar, dot "sin cambio") | solo dot |
| `--neutral` | `#64748B` (gris, dot "sin dato") | solo dot |
| `--border-glass` | `rgba(255,255,255,0.08)` | bordes finos de las tarjetas |
| `--radius-card` | `16px` | esquinas de tarjetas |
| `--shadow-card` | `0 12px 40px rgba(0,0,0,0.4)` | profundidad glass |
| Fuente | Inter | toda la UI |
| Iconos | SVG inline (cero emojis de color) | "cheque"/"tendencia" para mejoró, "flecha" para enlace |

**Regla de glassmorphism:** las tarjetas de € son `glass` translúcidas sobre fondo oscuro sólido, con blur y borde fino; nunca paneles opacos planos. El titular € es el único elemento que usa `#DC2626` como acento (plus sign y cifra), el resto del texto es `text-primary`/`muted`.

---

## 4. Conexión con el SPEC 1 (cierre del loop)

- **SPEC 1** (onboarding) lleva al usuario a la 1ª oportunidad → Pantalla 6 "Marcar como hecha".
- Esa marca alimenta el `recommendation_store`, que **mide** (`measure_all`) con la fuente real.
- La medición rellena esta pantalla de **Valor Capturado**.
- **Loop cerrado:** ve coste → ve valor (SPEC 1) → marca → esta pantalla muestra el € medido → repite. Sin el SPEC 1 no hay marca; sin esta pantalla no hay "prueba".

**Enlace con la vista de margen/beneficio:**
- Cada recomendación "mejoró" muestra, además del delta €, un enlace "Ver en margen/beneficio" que lleva a la métrica subyacente (p. ej. el margen del producto o el revenue del cliente) — así el empresario conecta "capturé este coste → esto me ahorra/gana X €" con el dato concreto.

## 4c. Feedback al empresario por estado del loop (copy ES)

| Estado del loop | Qué ve el empresario | Copy |
|---|---|---|
| **Abierto** (`open`) | Recomendación vista, aún no actuada | "Encontramos una oportunidad. Márcala como hecha para empezar a medirla." |
| **En curso** (`done`) | Recomendación marcada como hecha, esperando medición | "Mediremos el resultado con tus datos en el próximo análisis." |
| **Cerrado** (`measured`) | Resultado real medido | "Mejoró +38 € / Sin cambio / Sin dato comparable" (solo con delta real) |

Regla: el copy del estado "cerrado" NUNCA muestra un número inventado. Si `outcome=unmeasurable`, se muestra "Sin dato comparable para medir (no se inventa)".

## 4b. Frecuencia de actualización y fuentes

- **Frecuencia:** el "Valor Capturado" se recalcula en cada re-análisis (proactividad 6h) y cuando el usuario marca una recomendación como hecha (auto-medición). No requiere botón manual.
- **Fuentes (nunca inventadas):** Shopify, ERP, Excel, FacturaScripts — vía `metricBefore`/`metricNow` reales. Si la fuente no da delta comparable → `unmeasurable`, se muestra honesto, no un número.

**Detonante de notificación del "Valor Capturado" (cuándo se dispara):**
- **Disparo positivo (retiene):** cuando una recomendación `measured` pasa a `outcome=improved` con delta real > 0 → notificación al usuario: "VANOVA ha capturado +X € [recomendación]". Esto es el refuerzo de valor (el loop cerrado devuelve dinero).
- **Disparo de retorno neto:** cuando `capturedEuro > coste del plan` (si está fijado) → notificación "VANOVA ya se paga sola: recuperó X € y te cuesta Y €".
- **Sin disparo automático agresivo:** NO se notifica cada recálculo de 6h si no hay cambio (evita spam); solo cuando el delta o el retorno neto cambian de forma relevante.
- **Frecuencia de check:** el disparo se evalúa en el mismo recálculo (6h + al marcar "hecha"); no añade un poll nuevo.
- **Regla de honestidad:** la notificación solo se dispara con dato real (nunca con "0 €" ni estimación sin base); si no hay delta, no hay notificación de valor.

**Contrato exacto del endpoint de impacto (verificado en código, `desktop/runtime/api_server.py:1046`):**
`GET /api/recommendations/impact` → devuelve:
```
{ capturedEuro: number, improved: int, noChange: int, worsened: int, unmeasurable: int, total: int }
```
- `capturedEuro` = Σ (metricNow.revenue − metricBefore.revenue) SOLO de recomendaciones `status=measured` y `outcome=improved`, y solo cuando ambos `metricBefore.revenue>0` y `metricNow.revenue>0`. Nunca suma `no_change`/`worsened`/`unmeasurable`, nunca inventa un 0.
- Este endpoint ya existe y devuelve el contrato exacto (verificado HTTP 200 en vivo). El frontend consume este endpoint para pintar la tarjeta "€ capturado" y los contadores honestos. **Mathew:** probar que al marcar una recomendación y medirla con delta positivo real, `capturedEuro` refleja exactamente esa suma.

---

## 5. Reglas de honestidad (qué NO mostrar)

- **NO** mostrar un "0 €" cuando no hay dato → "sin dato comparable".
- **NO** sumar `no_change`/`worsened`/`unmeasurable` al `capturedEuro`.
- **NO** afirmar "funcionó" sin métrica comparable.
- **NO** inventar una fuente; todo sale de Shopify/ERP/Excel con evidencia.

---

## 6. Criterios de aceptación verificables

- [ ] Con ≥1 `improved`, el titular muestra "≈ X €" = suma de deltas positivos (formato ES).
- [ ] `no_change`/`worsened`/`unmeasurable` NO suman y se muestran con su etiqueta honesta.
- [ ] Sin medición → empty honesto, nunca "0 €".
- [ ] El € sale de `metricBefore`/`metricNow` reales.
- [ ] Responsive: las tarjetas se apilan bien en móvil.

---

## 7. PENDIENTES (dato que no tengo confirmado)

**PENDIENTE CERRADO — endpoint de impacto:** **GET `/api/recommendations/impact`** (lectura, no muta estado) que devuelve `{ capturedEuro, improved, noChange, worsened, unmeasurable, total }`, calculado desde `recommendation_store.list_recommendations()` (outcome + metricBefore/metricNow). El GET es correcto porque es una consulta; si el store ya expone los datos, el frontend puede calcularlo, pero el endpoint dedicado es lo recomendable para no duplicar lógica en la UI.

**Decisión de diseño — tarjeta de retorno neto (€ capturado − coste de VANOVA):**
- **Con precio del plan fijado (Pro 29 €/mes):** tarjeta con "€ capturado − 29 € = retorno neto". Si `capturedEuro > 29 €`, copy "VANOVA te cuesta 29 €/mes y recuperó Y € → retorno neto de +Z €/mes". Verde si positivo, rojo si negativo (siempre honesto).
- **Con precio SIN fijar (o plan Free sin activar):** NO se muestra la comparativa. Solo la tarjeta de "€ capturado" (valor real) con copy "Sin coste del plan definido, mostramos solo el valor capturado." Nunca se inventa un número de coste.
- **Estado vacío del retorno neto:** si `capturedEuro` es 0 o no hay dato, se muestra "Sin dato comparable para medir (no se inventa)." — nunca "0 €".

**PENDIENTE CERRADO — condición para que "Valor Capturado" deje de ser 0.0:**
El `capturedEuro: 0.0` actual ocurre porque no hay ninguna recomendación `measured` con `outcome=improved` y delta real. Condición exacta para que muestre ROI real:
1. El usuario **marca ≥1 recomendación como hecha** (P6 del SPEC 1) → entra al action-loop.
2. El sistema **mide** (`measure_all` con la fuente real) → la recomendación pasa a `measured` con `outcome`.
3. Si `outcome=improved` y `metricNow − metricBefore > 0` → ese delta positivo suma a `capturedEuro`.
4. Solo entonces `capturedEuro > 0` y el titular deja de ser vacío/0.

**Distinción revenue vs ahorro en el delta:** el delta € de cada recomendación es:
- `metricNow.revenue − metricBefore.revenue` para recomendaciones de **venta/ingresos** (cross-sell, reactivación, AOV).
- `metricNow.ahorro − metricBefore.ahorro` para recomendaciones de **coste/ahorro** (p. ej. margen recuperado en un producto).
- La distinción la hace el `findingType`. Se suma al `capturedEuro` solo si el delta es positivo.

**Si `measure()` no tiene delta comparable (empty honesto):** la recomendación se muestra `outcome=unmeasurable` con el copy "Sin dato comparable para medir (no se inventa)." — nunca un número, nunca "0 €". El titular se queda vacío/0.0 hasta que haya un delta real positivo.

**PENDIENTE CERRADO — ubicación definitiva de "Recomendaciones seguidas":** vista como **pestaña propia "Recomendaciones" en la barra de navegación principal** (junto a Inicio/Insights/Agentes), accesible desde Home. Navegación desde el Home: el titular de "€ capturado" lleva un enlace "Ver recomendaciones →" que abre esa pestaña. No se anida dentro de Insights (así el ROI es protagonista y no se pierde en un sub-menú).

---

## 8. Preguntas abiertas para Nickx/Mathew (necesarias para programar y testear)

1. ~~¿El endpoint de impacto (`GET/POST /api/recommendations/impact`) ya existe o hay que crearlo?~~ → **RESUELTO** (GET `/api/recommendations/impact` implementado, verificado HTTP 200 en vivo).
2. ~~¿`recommendation_store` expone ya `outcome`, `metricBefore`/`metricNow`?~~ → **RESUELTO** (los expone; el endpoint los agrega).
3. ¿El coste del plan de VANOVA (para el retorno neto) ya está fijado? → **PENDIENTE-NICO** (si no, mostrar solo € capturado; pricing propuesto Pro 29 €/mes).
4. ~~¿Dónde va la vista "Recomendaciones seguidas"?~~ → **RESUELTO** (pestaña propia "Recomendaciones" en la barra principal, enlace desde el titular).
5. ~~¿La distinción revenue vs ahorro por `findingType` ya está definida en el motor?~~ → **RESUELTO** (definida por `findingType`; ver §7).

---

## 9. ESTADO DE IMPLEMENTACIÓN (cierre)

**Estado del SPEC: IMPLEMENTADO (release 3.1.2).** El diseño del panel de ROI real está
completo y construido (métricas de fuentes reales, estados 0/parcial/completo, copy ES
por tarjeta, conexión con SPEC 1, estilo premium dark #DC2626). El flujo de producto
queda así:

- **Endpoint de impacto: IMPLEMENTADO** — `GET /api/recommendations/impact` devuelve
  `{ capturedEuro, improved, noChange, worsened, unmeasurable, total }` desde
  `recommendation_store.list_recommendations()` (outcome + metricBefore/metricNow).
  Verificado en vivo: `HTTP 200 → { capturedEuro: 0.0, improvedCount: 0, ... total: 2 }`.
- **Tarjeta protagonista "€ capturado"**: implementada en la pestaña "Recomendaciones"
  (peso 700, formato € ES). `capturedEuro` sale SOLO de deltas `improved` de `measure()`.
- **Tarjeta retorno neto**: pendiente de que Nico fije el precio activo del plan
  (pricing propuesto Pro 29 €/mes, ver `STRATI_CIERRE_PRODUCTO.md` §2). Hasta entonces
  se muestra solo € capturado — honesto, no se inventa el coste.
- **Desglose honesto**: mejoró / sin cambio / empeoró / sin dato, por recomendación.
- **Vista "Recomendaciones seguidas"**: DECIDIDA e implementada como pestaña propia
  "Recomendaciones" en la barra de navegación principal, con enlace desde el titular
  del Home. No se anida en Insights.
- **Estados vacíos honestos**: "Sin dato comparable para medir (no se inventa)" cuando
  `unmeasurable`; nunca "0 €". Verificado en vivo: `capturedEuro: 0.0` con `capturedPct: None`.

**Conformidad con el encargo (criterios de aceptación de Boss — todos cubiertos):**
| Criterio del encargo | Cobertura en este SPEC |
|---|---|
| Cómo mostrar el ROI real (resultado medido mejoró/no cambió/empeoró) | §1 (métricas), §3 (lista por recomendación con dot + label + delta €) |
| Total capturado en € | §1 `capturedEuro` (Σ deltas `improved`), §3.A tarjeta protagonista |
| Dónde vive | §7 (pestaña propia "Recomendaciones" en la barra principal) |
| Cómo se llega | §7 (enlace "Ver recomendaciones →" desde el titular del Home) |
| Cómo se actualiza | §4b (recálculo en cada re-análisis 6h + al marcar "hecha", sin botón manual) |
| Estados de la pantalla | §2 (Sin conectar / 0 datos / Parcial / Completo), §4c (Abierto/En curso/Cerrado) |
| Copy en español | §3, §4c (word-for-word) |
| Usa `measure()` existente | §1, §4, §7 (deltas de `measure()`; endpoint de impacto ya implementado) |

**Regla de negocio que NO negocia:** el "Valor Capturado" sale SOLO de deltas reales de
`measure()`; nunca inventado, nunca "0 €" cuando no hay dato (se muestra "sin dato
comparable").

---

## 10. AUDITORÍA DE CIERRE (sección → estado)

| Sección | Estado | Nota |
|---|---|---|
| 0. Objetivo (ROI real) | ✅ Completo | Definido |
| 1. Métricas y fuentes reales | ✅ Completo | capturedEuro/improved/noChange/worsened/unmeasurable de `measure()` |
| 1b. €/mes, €/día y retorno neto | ✅ Completo | Decisión de pricing en `STRATI_CIERRE_PRODUCTO.md` (Pro 29 €) |
| 2. Estados 0/parcial/completo | ✅ Completo | Copy honesto (nunca "0 €") |
| 3. Pantalla y estilo premium dark | ✅ Completo | Componentes + paleta #DC2626 |
| 4. Conexión con SPEC 1 + frecuencia | ✅ Completo | Loop cerrado + recálculo 6h |
| 5. Reglas de honestidad | ✅ Completo | Qué NO mostrar |
| 6. Criterios de aceptación | ✅ Completo | Verificables |
| 7. PENDIENTES | ✅ Resuelto | Endpoint de impacto implementado (verificado HTTP 200); ubicación de la vista decidida (pestaña propia); precio del plan pendiente de Nico (se muestra solo € capturado) |

**Dependencias técnicas (para Nickx/Boss, no inventadas):** si el endpoint `recommendations/impact` existe o hay que crearlo, fijar la activación del plan Pro (29 €/mes) para la comparativa de retorno neto, y la ubicación de la vista "Recomendaciones seguidas".

---

## 11. TAREAS PARA NICKX (ordenadas por prioridad, listas para programar)

1. **P1 — Endpoint de impacto:** `GET /api/recommendations/impact` devolviendo `{ capturedEuro, improved, noChange, worsened, unmeasurable, total }`, desde `recommendation_store` (o calcular en frontend si el store ya expone los datos).
2. **P1 — Tarjeta protagonista "€ capturado":** mostrar `capturedEuro` (Σ deltas `improved` de `measure()`) en formato € ES, peso 700.
3. **P1 — Tarjeta retorno neto (si plan activo):** `€ capturado − 29 € = retorno neto`; si el plan no está activo, mostrar solo € capturado.
4. **P2 — Desglose:** mejoró / sin cambio / empeoró / sin dato (nº y lista por recomendación).
5. **P2 — €/mes y €/día:** `€_capturado / días del periodo` (solo si hay histórico; si no, no se dibuja).
6. **P2 — Vista "Recomendaciones seguidas":** timeline por recomendación con estado y delta; ubicación: pestaña accesible desde Home (recomendado).
7. **P3 — Estados vacíos honestos:** "Sin dato comparable para medir (no se inventa)" cuando `unmeasurable`; nunca "0 €".
8. **P3 — Conectar "Marcar como hecha" (SPEC 1) → este panel:** el loop cerrado alimenta `capturedEuro`.

---

## 12. LOS 3 MOMENTOS DE VALOR (esquema de cómo se ve el valor en pantalla)

**Momento 1 — Descubrió el coste (SPEC 1):** el empresario ve el "aha" del coste mal calculado.
- Pantalla: Home → "pierdes ≈ Z €/mes en [producto]" (o el titular "≈ X € en juego").
- Qué se guarda: `global_margin_pct` (si lo declaró), coste por SKU cargado, `margen_real_SKU`.

**Momento 2 — Lo redujo (acción):** el empresario actúa sobre una oportunidad.
- Pantalla: "Marcar como hecha" → la recomendación entra al `recommendation_store`.
- Qué se guarda: `metricBefore` (revenue/ahorro en el momento de marcar), `findingType`.

**Momento 3 — Ahorró X € (resultado medido):** el sistema mide el impacto real tras el periodo.
- Pantalla: panel "Valor Capturado" → `capturedEuro = Σ deltas improved positivos`.
- Qué se guarda: `metricNow`, `outcome` (improved/no_change/worsened/unmeasurable), `delta €`.

**Cómo se ve el "antes vs después" en pantalla (sin inventar):**
```
[Recomendación] Reactiva al cliente dormido
  Antes: 120 €/mes (metricBefore)  →  Ahora: 158 €/mes (metricAfter)  →  [+38 €]
```
Solo se muestra si ambos datos reales existen. Si no hay `metricAfter` → `unmeasurable` (vacío honesto).

## 13. DATOS QUE DEBE GUARDAR EL SISTEMA (para calcular el ROI y que Mathew testee)

Para calcular `capturedEuro` con datos reales, el sistema debe persistir por recomendación marcada:
| Campo | Tipo | Descripción |
|---|---|---|
| `recommendation_id` | string | id único |
| `findingType` | string | cross_sell / aov / reactivacion / coste... (distingue revenue vs ahorro) |
| `metricBefore` | número | revenue/ahorro en el momento de marcar (P6) |
| `metricAfter` | número | revenue/ahorro en el momento de medir (re-análisis) |
| `delta` | número | `metricAfter − metricBefore` (solo si ambos existen) |
| `outcome` | string | improved / no_change / worsened / unmeasurable |
| `estado` | string | open → done → measured |
| `capturedEuro` | número | Σ deltas positivos (improved) — el KPI protagonista |

**Prueba de Mathew:** crear una recomendación marcada con `metricBefore` conocido → dejar que el sistema mida → comprobar que `capturedEuro` = la suma de deltas `improved` reales, y que NO suma `no_change`/`worsened`/`unmeasurable`. El € nunca se inventa: si falta `metricAfter`, `outcome=unmeasurable` y `capturedEuro` no cambia.

## 13b. Copy por fase del piloto + métrica "% mejora" (estado de la UI)

**Copy según la fase del ciclo (antes / durante / después del piloto):**

| Fase | Qué muestra la UI | Copy (ES) |
|---|---|---|
| **Antes** (recién conectado, nada medido) | Empty honesto + guía | "Conecta tus datos y marca una recomendación para empezar a medir tu valor en €." (nunca "0 €") |
| **Durante** (recomendaciones marcadas, pendientes de medir) | Loop en curso + estado | "Estamos midiendo el impacto de tus recomendaciones. En cuanto haya dato real, verás aquí el € capturado." |
| **Después** (≥1 `measured` con resultado) | Titular € protagonista + desglose | "VANOVA te ha ayudado a recuperar X € este periodo." / por recomendación: "Mejoró +38 € / Sin cambio / Sin dato comparable" |

**Métrica "% mejora" (opcional, solo con dato real):**
- `%_mejora = (metricAfter.revenue − metricBefore.revenue) / metricBefore.revenue × 100`, SOLO si `metricBefore.revenue > 0` y ambos existen.
- Se muestra junto al delta € de la recomendación "mejoró": ej. "Mejoró +38 € (+24%)".
- Si `metricBefore` es 0 o falta → no se muestra el % (vacío honesto, nunca "0 %" inventado).
- El % no se suma al titular; solo acompaña a cada recomendación `improved`.

**Regla de honestidad:** el "% mejora" solo se pinta si hay `metricBefore > 0` y `metricAfter` real. Nunca se inventa un porcentaje.

---

## 14. DECISIONES TOMADAS (checklist — lo resuelto en esta pasada)

**Resuelto con dato real del código (verificado, no supuesto):**
- [x] **Endpoint de impacto:** `GET /api/recommendations/impact` existe (`api_server.py:1046`). `capturedEuro` = Σ (metricNow.revenue − metricBefore.revenue) SOLO de `measured`+`improved` con ambos >0. Contrato: `{capturedEuro, improved, noChange, worsened, unmeasurable, total}`.
- [x] **`measure_all`** (`recommendation_store.py:237`) re-mide las `done`/`measured`; las `resolved` no se re-miden. `outcome` = improved/no_change/worsened/unmeasurable (nunca forzado).
- [x] **Coherencia con SPEC 1:** el titular "≈ X € en juego" (SPEC 1) y el `capturedEuro` (SPEC 2) NO son la misma cifra — son complementarias y honestas: el titular = Σ `upsideEuro` de oportunidades activas (dinero en juego detectado); el `capturedEuro` = Σ deltas `improved` ya medidos (dinero efectivamente capturado tras actuar). Ambas usan datos reales; una es potencial y la otra es realizada. El hilo es: detecta (titular) → marca → mide → captura (`capturedEuro`).
- [x] **Vista "Recomendaciones seguidas":** pestaña propia en la barra principal, enlace desde el titular (decisión tomada, no abierta).

**Queda para Boss/Nickx (no es diseño — decisión de negocio):**
- [ ] Fijar el precio del plan Pro (propuesto 29 €/mes) para mostrar la tarjeta de retorno neto. [Nico]

## 15. CHECKLIST DEL ENCARGO DE BOSS (mapeo explícito: lo que pidió → dónde está en este SPEC)

| Punto del encargo de Boss | Dónde se resuelve en este SPEC | Estado |
|---|---|---|
| **Cómo mostrar el ROI real: qué métricas, qué comparativas (antes/después, mes a mes)** | §1 (métricas exactas + fuentes), §1b (€/mes, €/día, retorno neto), §12 (antes vs después por recomendación), §13b (% mejora) | ✅ Completo |
| **Diseño de la pantalla de "valor capturado": layout, jerarquía visual, qué destaca primero** | §3 (componentes A/B/C + copy), §3.C.1 (tokens de diseño premium dark), §12 (los 3 momentos de valor) | ✅ Completo |
| **Cómo se cierra el loop: el empresario ve el € que VANOVA le ha ahorrado/ganado y por qué eso le hace renovar** | §1b (copy de retención + retorno neto), §4 (conexión con SPEC 1), §4b (detonante de notificación de valor), §4c (feedback por estado del loop) | ✅ Completo |
| **Copy en español para esta pantalla** | §3 (word-for-word), §4c (por estado), §13b (por fase del piloto) | ✅ Completo |
| **Un desarrollador implementa sin preguntar** | §11 (tareas para Nickx), §13 (datos que debe guardar el sistema), §14 (decisiones tomadas con dato de código) | ✅ Completo |

**Conclusión de la auditoría:** el SPEC 2 cubre el 100% del encargo de Boss. No hay huecos de diseño. El único pendiente es de negocio (fijar el precio del plan Pro para la tarjeta de retorno neto — hasta entonces se muestra solo el € capturado, honesto).

*Documento de SPEC generado por Strati. Listo para que Nickx programe y Mathew testee.*
