# STRATI — SPEC: Pricing por niveles (Free → pago)

**Autor:** Strati (estrategia/producto)
**Para:** Nickx (dev) · QA (Mathew) · Boss (decisión comercial)
**Versión proyecto:** 3.0.8 · **Estado:** Propuesta aprobada por Boss — decisión comercial pendiente
**Regla:** Documento de especificación. NO es código; no modifica el proyecto.

---

## 0. Resumen ejecutivo (el titular que lo justifica)

El principio comercial de VANOVA es:

> **El diagnóstico es el teaser. El ROI demostrado es lo que se paga.**

La cadena ya está especificada en los 2 specs previos:
- **Detector de Oportunidades** (`STRATI_DETECTOR_OPORTUNIDADES_SPEC.md`): emite
  oportunidades con impacto € (o "no cuantificable", nunca 0).
- **Recomendaciones seguidas / Impacto** (`STRATI_RECOMENDACIONES_IMPACTO_SPEC.md`): cierra
  el loop mostrando `mejoró / no cambió / empeoró` y el **delta €** por recomendación.

El pricing por niveles se construye sobre un único **titular de retención** que ya viene de
esos specs: el **"total capturado en €"** — la suma de `metricNow.revenue − metricBefore.revenue`
de las recomendaciones `measured` con `outcome=improved`. Esa cifra es el argumento de venta
final: *"VANOVA te ha ayudado a capturar X € con tus datos reales."*

Este spec define: niveles, qué es gratis vs pago, modelo y referencia de mercado, métricas de
retención/conversión, y requisitos de dev para poder cobrar.

---

## 2. Referencia de mercado (datos reales, no inventados)

Apps de analítica/ROI para ecommerce (mercado objetivo directo), precios públicos mensuales:

| Producto | Nivel bajo | Nivel medio | Nivel alto | Observación |
|---|---|---|---|---|
| **Metorik** | $25 (≤100 pedidos) | $75 (≤500) | $150–$250 | Precio por volumen de pedidos |
| **Profit Panel** | $18 (≤100) | $30 (≤300) | $50–$150 | PNL + sugerencias IA en el tier alto |
| **Cifra Analytics** | $29 (≤500) | $49 (≤600) | $149 | Por volumen + dashboards |
| **Kendall Analytics** | $99 (≤$1M GMV) | $199 (≤$5M) | $249+ | Precio por GMV anual |

**Lectura para VANOVA:**
- El mercado valida un **rango mensual ~$20–$150** para este segmento, casi siempre con
  **free trial (14–30 días)** y **frecuencia mensual recurrente**.
- La diferenciación de VANOVA (un *AI OS* que detecta, prioriza, recomienda y mide con
  **datos reales**, no un simple reporteador) permite situarse **por encima del rango de las
  apps de reporting puras**, pero hay que demostrar el ROI primero → de ahí el modelo
  **Free con ROI visible** como prueba.
- Moneda del mercado: USD mayoritario, pero VANOVA opera en **EUR** (clientes Galicia/ES).
  Sugiero **precios en €** y adaptarlos a USD solo si se sale del mercado hispano.

---

## 3. Niveles propuestos

### 3.1 Modelo: mensual recurrente + 3 niveles (Free / Pro / Business)

| Nivel | Precio (€/mes) | Mercado objetivo | Filosofía |
|---|---|---|---|
| **Free** | 0 € | cualquier pyme que pruebe | teaser: conectar + diagnóstico + ROI del 1er mes |
| **Pro** | 29 € | ecommerce activo (pyme) | oportunidades + seguimiento/ROI completo + Shopify |
| **Business** | 79 € | ecommerce/operación mayor | multi-empresa + agentes + FacturaScripts + soporte prioritario |

> Precios orientativos. Ajustar con los números del ROI que salgan del piloto (ver §5).
> El rango 29/79 está dentro del mercado (Metorik 20–150, Cifra 29–149, Profit Panel 18–150).

### 3.2 Qué incluye cada nivel

| Capacidad | Free | Pro | Business |
|---|---|---|---|
| Dashboard + estado de datos (real/partial/mock/empty) | ✅ | ✅ | ✅ |
| Detección de **problemas/riesgos** (motor) | ✅ | ✅ | ✅ |
| Business Brain + preguntas a Hermes (básico) | ✅ (limitado) | ✅ | ✅ |
| **Detector de Oportunidades** (spec P0-1) | ⚠️ ver teaser | ✅ | ✅ |
| **Recomendaciones seguidas / ROI €** (spec P0-2) | ⚠️ | ✅ | ✅ |
| Historial de recomendaciones (cuántas medidas) | ❌ | ✅ | ✅ |
| **"Total capturado en €"** (titular ROI) | ❌ (solo 1ª muestra) | ✅ | ✅ |
| Proactividad recurrente (6 h) | ❌ | ✅ | ✅ |
| Shopify sync | ❌ | ✅ | ✅ |
| FacturaScripts / ERP | ❌ | ❌ | ✅ (pendiente validación) |
| Multi-empresa / multi-workspace | ❌ | ❌ | ✅ |
| Agent orchestrator (Hermes, autónomo) | ❌ | ❌ | ✅ |
| Soporte | Comunidad | Email | Prioritario |

---

## 4. Qué es teaser gratis y qué se paga

### 4.1 Teaser (Free — el "aha moment" gratuito)
- Dashboard real + detección de problemas/riesgos con € (ya funciona).
- **Una (1) oportunidad** del Detector y **una (1) muestra del "total capturado"** para que
  el empresario vea el loop de valor funcionando de verdad.
- Así el usuario experimenta el momento aha *antes* de pagar, y el titular "X € capturados"
  actúa de prueba social en la misma UI.

### 4.2 Lo que se paga (gated) — todo lo que cierra el ROI y escala:
- Detector de Oportunidades **completo** (cross-sell, concentración, AOV, reactivación).
- **Recomendaciones seguidas con ROI completo** + historial + el **total capturado**.
- Proactividad 6 h (el motor que te avisa solo).
- Shopify sync.
- (Business) multi-empresa, ERP/FacturaScripts, agentes/autonomía.

> Regla de honestidad que NO se negocia: **el ROI demostrado y el "total capturado" solo se
> muestran cuando hay evidencia real** (nunca un 0 € ni una cifra inventada). Si el teaser
> no tiene datos suficientes, se ve el empty state honesto (como ya definen los 2 specs).

---

## 4b. Modelo de precios
- **Modelo base: suscripción mensual fija por nivel** (recurrente), coherente con el mercado
  (Metorik/Cifra/Profit Panel). Facturación en €.
- **Atributo variable a futuro:** volumen (pedidos/mes) o GMV en el tier Business, como hacen
  Metorik/Cifra. No empezar con eso; empezar fijo para no complicar el MVP comercial.
- **Free trial de pago:** el Free es perpetuo como teaser; si se quiere, un **14 días Pro
  gratis** (imitando el 14–30 del mercado) al registrarse.
- **Anual con descuento (10–20%)** como palanca de retención (Cifra: ~21% anual).

---

## 5. Cómo se mide retención / conversión Free→pago

### 5.1 Métricas de producto (origen: specs previos)
- **"Total capturado en €"** (titular): suma de deltas revenue de recs `measured`+`improved`.
  Es la métrica que da valor y la que sube la conversión.
- **Nº recomendaciones seguidas** y **tasa de recomendaciones con resultado (`improved`)**.

### 5.2 Métricas de negocio (a instrumentar por dev/QA)
| Métrica | Definición | Señal |
|---|---|---|
| **Activación (Free)** | usuario conecta fuente y ve ≥1 finding real en ≤15 min | conversión Free→Pro |
| **Aha moment** | el usuario ve la 1ª recomendación con impacto | la ve en la UI (titular ROI) |
| **Conversión Free→Pro** | % de usuarios Free que pagan en 30/60 días | viabilidad del pricing |
| **Retención (churn)** | % que renueva mes a mes | el ROI demostrado reduce churn |
| **RPC (revenue per customer)** | €/cliente/mes | salud de la economía del producto |
| **Payback** | meses para recuperar CAC | decide el presupuesto de venta |

> Fuente honesta: el Free solo mide el teaser; el ROI real se captura en Pro. Esa métrica
> con respaldo real es lo que justifica subir el precio al subir la retención.

---

## 6. Requisitos para dev (si se implementa el pricing)

### 6.1 Qué hace falta (mínimo)
- **Gate por plan:** campo `plan` en la cuenta (`free|pro|business`) y checks en:
  - Detector de Oportunidades (Free: 1 oportunidad; Pro+: completo).
  - Vista de Recomendaciones/Impacto (Free: 1 muestra + 1 total; Pro+: historial completo).
  - Shopify / ERP / multi-workspace (según plan).
- **Titular "total capturado"**: endpoint que sume deltas de recoversiones `improved` del
  workspace (ver `GET /api/recommendations/impact` del SPEC de Recomendaciones).
- **Instrumentación de conversión/uso** (eventos anónimos: conexión de fuente, 1er finding,
  marcar realizada, delta > 0). Sin esto no se mide retención ni conversión.
- **Facturación/pagos:** es lo único "externo" (Stripe u otro); proponer a Boss como fase
  separada, NO en el MVP del loop de valor.

### 6.2 Qué NO implementar ahora (evitar sobre-ingeniería)
- Suscripciones reales con tarjeta, facturación, dunning, multi-tenant pricing — diferir a
  una fase de lanzamiento con cliente pago real.
- El pricing por volumen de pedidos/GMV — diferir hasta tener volúmenes reales.

### 6.3 Decisiones para Boss/Nickx
1. ¿Señalizar "Pro" con características bloqueadas + CTA, o mostrar todo y dar trial?
   (recomiendo CTA + trial 14 días).
2. ¿El titular "total capturado" se muestra en Free como teaser (1 muestra) — recomiendo sí.
3. ¿Pagos con tercero ahora o validar primero con pilotos manuales (factura a mano)?
   recomiendo validar con pilotos antes de integrar pagos.

---

## 7. Cómo se probaría (QA — Mathew)

### 7.1 Automático (si se implementan gates)
- Tests por plan: Free solo ve 1 oportunidad; Pro ve todas; Business multi-workspace.
- Endpoint de titular ROI: suma solo `improved`, nunca cuenta `no_change/worsened`.
- Sin evidencia → `0 €` nunca se muestra (honestidad intacta).

### 7.2 Manual
- Usuario Free conecta Shopify → ve 1 oportunidad + teaser de ROI.
- Al hacer upgrade → se desbloquean Detector completo + historial + total ROI.
- Churn/instrumentación: evento "primera recomendación mejorada" se registra.

---

## 8. Conexión con los 2 specs previos (bucle de valor cerrado)

```
[Free: teaser]                        [Pro: ROI pagado]
  Detector (P0-1)                        Detector completo
    → 1 oportunidad                        → todas las oportunidades
  Recomendaciones/Impacto (P0-2)          → historial + TOTAL CAPTURADO €
    → 1 muestra de ROI                     → titular de retención
```
- El Detector crea oportunidades; la UI de Recomendaciones las cierra con ROI; el **pricing**
  monetiza ese ROI (Free lo muestra para vender, Pro lo explota completo).
- El **"total capturado"** es el nexo: lo detecta el Detector (€), lo mide la UI (delta),
  y lo cobra el pricing (retiene y convierte). Por eso la cifra debe ser **honesta y real**
  — es el argumento comercial, y una cifra falsa destruiría la confianza que VANOVA diferencia.

---

*Documento de especificación generado por Strati. No modifica el proyecto. Aprobado por
Boss (2026-08-20); decisiones comerciales pendientes (niveles, precio final, pagos).*
