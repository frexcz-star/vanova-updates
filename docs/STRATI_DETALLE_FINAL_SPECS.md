# STRATI — DETALLE FINAL DE LOS 3 SPECS (base congelada para Nickx)

**Autor:** Strati (estrategia/producto) · **Para:** Boss (decisión) → Nickx (implementación), Mathew (QA)
**Versión proyecto:** 3.1.1 · **Fecha:** 2026-08-22 · **Estado:** Base congelada para Nickx
**Regla:** Verificación honesta; el € sale SOLO de fuentes reales (Shopify/ERP/Excel/FacturaScripts); nunca inventado, nunca "0 €".

---

## Tabla de detalle final por SPEC

### SPEC 1 — FLUJO DE COSTES + ONBOARDING "AHA"

| Sección | Estado | Qué hay |
|---|---|---|
| Flujo pantalla a pantalla (P0-P6) | ✅ LISTO | Wizard multi-fase, copy ES literal, wireframes (líneas 57-221) |
| Empty states | ✅ LISTO | Copy ES + CTA por vacío (§2, líneas 225-235) |
| € en <15 min + aha | ✅ LISTO | Fórmula real + titular "≈ X € en juego" (líneas 174-214) |
| Umbrales obligatorio/opcional | ✅ LISTO | §12 (líneas 420-433) |
| Bloqueos del aha | ✅ LISTO | §14 (líneas 450-461) |
| Criterios de aceptación | ✅ LISTO | §5 (líneas 305-311) |

**¿Algo que Nickx no pueda resolver hoy SOLO con el diseño?** No. Las dependencias técnicas que antes estaban "delegadas" ya están **resueltas en la release 3.1.3** (según el developer): método Shopify (Dev Dashboard, shpss_ → token real), plantilla CSV de costes (existe), mapa FacturaScripts (implementado), y el botón "Declarar mi margen" ya en el Home. No queda ninguna dependencia técnica pendiente de diseño.

### SPEC 2 — UI CIERRE DEL LOOP / "VALOR CAPTURADO"

| Sección | Estado | Detalle |
|---|---|---|
| Métricas exactas + fuente | ✅ LISTO | capturedEuro/improved/no_change/worsened/unmeasurable de `measure()` |
| Honestidad (nunca "0 €") | ✅ LISTO | Regla explícita §5 |
| Los 3 momentos de valor | ✅ LISTO | §12: descubrió coste → lo redujo → ahorró € |
| Estados/vacíos + "Sin conectar" | ✅ LISTO | §2 incluye "Sin conectar" (línea 61) |
| Endpoint de impacto | ✅ LISTO | GET `/api/recommendations/impact` (implementado, verificado HTTP 200) |

**¿Queda algún caso/empty sin definir?** No. Todos los estados y empty states están definidos; no sumar `no_change`/`worsened`/`unmeasurable` al `capturedEuro` está explícito.

### SPEC 3 — PRUEBA DE VENTA / PILOTO REAL

| Sección | Estado | Detalle |
|---|---|---|
| Criterios de selección | ✅ LISTO | ecommerce + coste por SKU + dueño (§1) |
| Qué se entrega/pide | ✅ LISTO | Guía 5 pasos + plantilla CSV (§1b) |
| Sesión de test | ✅ LISTO | pre→demo→test→post, ~40 min (§5c-bis) |
| Métricas de valor de VENTA | ✅ LISTO | §1c: oportunidades + € de venta medido |
| Señal "ready para escalar" | ✅ LISTO | aha <15 + loop + uso 30d + paga (§4/§7b.3) |
| Separación operativa vs construcción | ✅ LISTO | §7c: captación (Boss/Nico) NO se programa |

**¿Fase operativa de captación separada de lo construible?** Sí, en §7c. Nickx solo programa el registro de eventos y la métrica "tiempo hasta el €"; reclutar/consentimiento/precio es operativo de Boss/Nico.

---

## Conclusión (3 líneas)

1. **Los 3 SPECs están LISTOS para que Nickx programe** — todos los puntos de diseño, copy, empty states, umbrales, bloqueos y criterios están definidos y verificados en disco.
2. **Los únicos pendientes son técnicos delegados** (método Shopify, plantilla CSV, mapa de FacturaScripts, activar plan 29 €) y **operativos** (conseguir el piloto real) — NO son gaps de diseño.
3. **La base queda congelada**: Nickx puede programar sin tomar decisiones de producto; no hace falta más iteración de ideas.

---

*Documento de detalle final generado por Strati. Solo lectura/diseño; no ejecuté nada.*
