# STRATI — Plan de Pruebas "En la piel del empresario"

**Autor:** Strati (estrategia/producto)
**Para:** Boss (decisión) · Nickx (ejecución) · Mathew (QA)
**Versión proyecto:** 3.0.8 · **Estado:** Propuesta — para que Nickx/Mathew lo ejecuten después
**Regla:** Documento de plan. NO es código; NO modifica el proyecto; no da órdenes directas.

---

## 0. Objetivo

Validar que VANOVA DE VERDAD ayuda a un empresario a **VENDER más**, no solo a "ver datos".
La forma: hacer **pruebas poniéndonos en la piel del empresario de tienda online (Shopify)**
con datos reales, midiendo si el € se traduce en venta.

**Prueba de fuego del producto:** una oportunidad de VANOVA (cross-sell, reactivación, AOV)
→ si el empresario la aplica → ¿aumenta el ticket / la venta? → ¿cómo se mide con datos
reales? → ¿se ve el resultado en la UI?

---

## 2. Escenarios de uso reales (empresario de tienda online Shopify)

### 2.1 Perfil del "empresario ficticio"
- Dueño de tienda online (Shopify), sin equipo técnico, con datos reales: productos, pedidos,
  clientes, catálogo (quizá con coste por SKU cargado).
- Necesita: (1) saber qué está pasando, (2) qué hacer hoy, (3) cuánto puede ganar, (4) si lo
  que hizo funcionó.
- Confía si: ve € con evidencia real, no humo; ve que VANOVA "le vigila" y le avisa.

### 2.2 Escenarios concretos (mínimo 5)
1. **Primera sesión (onboarding):** conecta Shopify → ve la 1ª oportunidad con € en <15 min.
2. **Decisión diaria:** abre el Home → "Qué hacer hoy" con 1–3 items y su €.
3. **Una oportunidad de cross-sell:** ve "A+B se compran juntos" → decide aplicarla (pack).
4. **Un riesgo:** ve "un producto concentra el 26% de tus ventas" → evalúa diversificar.
5. **Un cliente dormido:** ve "este cliente te compraba y lleva 45 días sin pedido" → decide
   reactivarlo.
6. **Cierre del loop:** marca "hecha" una oportunidad → el sistema mide si mejoró.

---

## 3. Pruebas de VALIDACIÓN DE VENTA (que VANOVA ayude a vender más)

Objetivo: demostrar que aplicar la recomendación aumenta la venta, NO solo ver datos.

### 3.1 Cross-sell → ¿aumenta el ticket?
- **Entrada:** oportunidad "A+B co-comprados con frecuencia" (motor ya emite).
- **Prueba:** el empresario crea un pack A+B (o aplica el cross-sell en la tienda).
- **Medida honesta:** tras el cambio, comparar **AOV (ticket medio)** y **% pedidos
  multi-producto** del periodo con el periodo anterior, sobre datos reales (igual que
  `measure()` del action-loop).
- **Éxito:** AOV sube y/o % multi-producto sube → VANOVA ayudó a vender más.
- **Criterio honesto:** si no hay datos comparables o no cambia, se reporta "sin cambio /
  no medible", NUNCA "funcionó" sin evidencia.

### 3.2 Reactivación de cliente dormido
- **Entregunta:** señal de cliente dormido (motor).
- **Prueba:** enviar reactivación (email/descuento) a ese cliente.
- **Medida:** ¿ese cliente vuelve a pedir? ¿ingresos recuperados de ese cliente?
- **Honestidad:** si no vuelve, es "no cambio"; solo se atribuye éxito si el cliente
  recuperado tiene datos reales.

### 3.3 Concentración / diversificación
- **Entregunta:** concentración de producto/cliente.
- **Prueba:** empujar los sustitutos con crecimiento (diversificar).
- **Medida:** ¿baja la dependencia (share del top producto) manteniendo ingreso? ¿los
  sustitutos ganan revenue?

---

## 4. Flujo de prueba end-to-end (simulación completa)

**Simular que un empresario usa VANOVA de principio a fin:**
1. **Conecta datos** → Shopify o Excel (real).
2. **Ve €** → Home con titular "≈ X € en juego" + 1ª oportunidad con €.
3. **Actúa** → marca una oportunidad como "hecha" / aplica el pack / reactiva el cliente.
4. **Ve resultado** → la UI de "Recomendaciones/Impacto" muestra `mejoró / sin cambio /
   empeoró` con delta € (cuando esté implementada).
5. **Decide** → si el resultado se ve con evidencia, decide seguir usando y pagar.

**Nota:** los pasos 3–4 dependen de la UI de Recomendaciones/Impacto (spec P0-2, pendiente de
implementar). Hasta entonces, la simulación verifica el backend y el plan de UI.

---

## 5. Qué mejorarías al verlo desde esa perspectiva (gaps detectados)

1. **Lenguaje técnico:** "findings", "priorities", "upside", "UNKNOWN≠0" NO dicen nada a un
   empresario. Cambiar a "oportunidad / riesgo / hoy / €".
2. **Falta de "me vigila" percibida:** la proactividad 6h existe pero no llega como aviso fácil
   de entender en el Home → el empresario no siente que le cuidan.
3. **Sin UI de cierre del loop:** no ve "lo marqué → mejoró". Sin la pantalla de
   Recomendaciones/Impacto, no demuestra que ayuda a vender (es la prueba central).
4. **Sin carga de coste:** el cross-sell/upstide necesita margen; si no hay coste, no cuantifica.
   Guiar al empresario a cargar costes por SKU.
5. **Empty states honestos:** "no data" → debe ser "Conecta Shopify para ver tu 1ª
   oportunidad".
6. **Verificar build instalada** (lección BUG-017): la feature que se promete debe servir la
   build instalada, no solo el repo.

---

## 6. Checklist "¿LE AYUDA A VENDER?" (criterios concretos y honestos)

- [ ] En <15 min el empresario ve ≥1 cifra de € real (oportunidad o riesgo) con evidencia.
- [ ] El empresario entiende QUÉ hacer y POR QUÉ (lenguaje de negocio, no técnico).
- [ ] Puede marcar una recomendación como "hecha".
- [ ] El sistema mide el resultado y muestra `mejoró / sin cambio / empeoró` con delta €
      (cuando aplique) — honesto, nunca "0 €" inventado.
- [ ] Si aplica un cross-sell/pack: hay un camino medible a ticket/AOV (o se reporta no-medible).
- [ ] El titular "Total capturado ≈ X €" es visible y honesto.
- [ ] La build instalada sirve las features que se prometen (no desync).
- [ ] Cero € inventado (UNKNOWN≠0 respetado en toda la UI).

**Definición de "ayuda a vender" (honesta):** VANOVA ayuda a vender si el empresario puede
ver y actuar sobre oportunidades de € reales, y el sistema mide el efecto de forma honesta
(mejora o no) sobre datos reales — no porque "diga" que vende más.

---

## 7. Ejecución (para Nickx/Mathew después)

1. Cargar un dataset real (ej. Shopify de BlisPaper o un ecommerce con costes) en un entorno
   de prueba aislado.
2. Recorrer el flujo end-to-end (§4) y registrar resultados.
3. Para cada escenario (§2), aplicar la prueba de venta (§3) y medir.
4. Marcar cada item del checklist (§6) ✅/❌ con evidencia.
5. Reportar gaps a Boss; NO tocar código (esto es validación).

---

## 7b. Nota de control (regla del usuario)
Documento de plan — solo propuesta. No modifica el proyecto ni da órdenes directas a
Nickx/Mathew; es la base para que ellos ejecuten las pruebas. El usuario decide.

---

*Documento generado por Strati. No modifica el proyecto.*
