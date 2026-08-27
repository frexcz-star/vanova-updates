# STRATI — Cierre de gaps de producto (no técnicos)

**Autor:** Strati (estrategia/producto) · **Para:** Boss (decisión) → Nickx (implementación), Mathew (QA)
**Versión proyecto:** 3.1.1 · **Estado:** Propuesta de producto — para decisión de Boss
**Regla:** Solo diseño/propuesta. Nada de código. Datos honestos, nunca inventados.

---

## 1. Tabla de gaps de producto REALMENTE abiertos (no dependencias técnicas)

| SPEC | Gap de producto abierto | Propuesta concreta | Estado |
|---|---|---|---|
| **SPEC 1 (Flujo costes + aha)** | Ninguno de diseño. El flujo, el aha, empty states, copy ES, margen global vs coste por SKU, y el framing por cliente/hora están definidos | — | **CERRADO** |
| **SPEC 2 (Valor Capturado)** | Contradicción de ubicación de "Recomendaciones seguidas" (PENDIENTE ABIERTO vs CERRADO) | Eliminado el "PENDIENTE ABIERTO" obsoleto; decisión única: pestaña propia "Recomendaciones" | **CERRADO** (fix aplicado) |
| **SPEC 3 (Piloto)** | El plan del piloto y la métrica de éxito están definidos; falta lo operativo (conseguir piloto), que NO es gap de diseño sino de ejecución — lo ataca el punto 2 | — | **CERRADO de diseño**; la ejecución del piloto es operativa (Boss/Nico), no de producto |

**Conclusión honesta:** NO queda ningún gap de producto/diseño abierto en mi competencia. Los 3 SPECs están a nivel "LISTO para implementación". Lo que queda es (a) confirmación técnica de Nickx y (b) conseguir el piloto real (operativo, punto 2).

---

## 2. Vía real MÁS CORTA para conseguir 1 piloto + arranque día 1 + señal "ready"

**La vía más corta (en este orden, la primera que responda gana):**
1. **Contacto directo de Nico/red** (máx 2-3 emails/candidatos): un ecommerce Shopify cercano que Nico conozca (amistad, coworking, comunidad local). Mensaje de invitación ya redactado en `STRATI_CIERRE_PRODUCTO.md` §3.1. Responsable: Boss/Nico. Fecha objetivo: esta semana.
2. **Community/forum local** (papelería/ecommerce): post/mensaje ofreciendo "probar gratis durante un mes un sistema que te dice cuánto pierdes en margen". Responsable: Boss. Fecha: esta semana.
3. **Caso interno si hay tienda MOOVING neutra** con coste cargable (si existe; si no, se salta). Responsable: Nickx confirma si existe. Fecha: 1-2 días.

**Guion de arranque día 1 (no teoría, pasos):**
- Día 1 mañana: enviar invitación (`STRATI_CIERRE_PRODUCTO.md` §3.1) + acceso + guía de 5 pasos.
- Día 1 tarde: acompañar la conexión (Shopify/Excel) + coste por SKU; registrar el timestamp "conexión OK → 1ª oportunidad vista".
- Día 1 fin: si ve € real en <15 min → "aha" registrado. Si no → fricción, ajustar SPEC 1 (no a ciegas).

**Señal EXACTA que confirma "ready para escalar" (todas deben cumplirse):**
1. El piloto ve ≥1 oportunidad/€ real con SUS datos en <15 min (registrado en el log).
2. Marca ≥1 recomendación como hecha y el sistema mide el resultado (improved/no_change/worsened/unmeasurable).
3. Usa la app ≥5 días/mes a los 30 días.
4. Dice (con sus palabras) que le aportó algo o que pagaría.

Si cumplen TODAS → **ready para escalar**. Si falla la 1 o la 2 → **bloquear** y corregir SPEC 1/2 antes de seguir (no escalar a ciegas).

---

## 3. Coherencia entre los 3 SPECs (verificación)

**Cadena completa y coherente:**
- **SPEC 1** produce el "aha" (Home: titular "≈ X € en juego" + oportunidad cuantificada) y el botón "Marcar como hecha" (P6).
- **SPEC 2** recibe esa marca: `recommendation_store` la mide (`measure_all`) y el panel "Valor Capturado" muestra `capturedEuro` (Σ deltas improved). Cierre del loop: ve coste → ve valor → marca → mide → muestra € → repite.
- **SPEC 3** mide el piloto con las métricas del SPEC 1 (tiempo al €, "aha") y del SPEC 2 (capturedEuro medido) → decide Go/No-Go.

**Incoherencia detectada y corregida (SPEC 2):** la ubicación de "Recomendaciones seguidas" estaba como abierta y cerrada a la vez. Resuelto: única decisión = pestaña propia "Recomendaciones".

**Ninguna otra incoherencia entre los 3.** Los números/flujos conectan sin contradicción.

---

*Documento de cierre de gaps de producto, generado por Strati. Solo propuesta; no ejecuté nada.*