# STRATI — CHECKLIST TÉCNICO CONSOLIDADO PARA NICKX

**Autor:** Strati (estrategia/producto) · **Para:** Nickx (implementación) · **Revisa:** Mathew (QA), Boss (decisión)
**Fecha:** 2026-08-23 · **Base:** SPECs 1/2/3 (STRATI_ESPEC_FLUJO_COSTES / VALOR_CAPTURADO / PILOTO) · **Regla:** € solo de fuentes reales, nunca "0 €" inventado.

Este checklist cruza las tareas P1/P2 de los 3 SPECs en **orden de implementación**, con dependencias y criterios de aceptación por tarea. Nickx puede seguirlo sin releer los 3 docs; cada tarea referencia la sección del SPEC de origen.

---

## FASE A — ONBOARDING "AHA" (SPEC 1) → el € en <15 min

| # | Tarea | SPEC § | Depende de | Criterio de aceptación |
|---|---|---|---|---|
| A1 | Conexión Shopify por token manual + manejo de scopes (pantalla "Ver permisos") | 1 §7b.1 | — (ya implementado, verificar) | Conectar tienda real → estado conectado o error claro de scopes; nunca spinner infinito |
| A2 | Wizard P0-P6 + state-machine (§1f) | 1 §1f | A1 | Alta → conectar → coste/margen → Home; transiciones por caso (calculated/estimated/Más tarde) |
| A3 | Empty states por pantalla + copy ES | 1 §2 | A2 | Cada pantalla sin datos guía con CTA; nunca "0 €" |
| A4 | Botón "Declarar mi margen" (globalMarginPct) | 1 §4 | A2 | Al pulsar, titular "≈ X € en juego" `estimated` + cross-sell € ESTIMADO |
| A5 | Alta manual de coste "una línea a la vez" (Pantalla 4b) | 1 §4b | A2 | Con 1 solo coste, el € se actualiza en el Home |
| A6 | Plantilla CSV de costes (`prepare_cost_template`) | 1 §7b.2 | A2 (existe) | Descarga plantilla `sku;coste;precio_venta;unidades_mes`; import cruza por SKU |
| A7 | Test de aceptación del aha | 1 §15 | A2-A6 | `t_aha ≤ 15 min` con datos reales; titular + ≥1 € visible sin scroll |

**Salida Fase A:** un empresario no-técnico ve su € real en <15 min.

---

## FASE B — VALOR CAPTURADO / CIERRE DEL LOOP (SPEC 2)

| # | Tarea | SPEC § | Depende de | Criterio de aceptación |
|---|---|---|---|---|
| B1 | Endpoint `GET /api/recommendations/impact` | 2 §4b | A7 | Devuelve `{capturedEuro, improved, noChange, worsened, unmeasurable, total}`; HTTP 200 (ya implementado, verificar) |
| B2 | Tarjeta protagonista "€ capturado" (peso 700, formato ES) | 2 §1/§3 | B1 | Muestra `capturedEuro` = Σ deltas `improved` de `measure_all`; nunca "0 €" |
| B3 | Desglose honesto: mejoró/sin cambio/empeoró/sin dato | 2 §3 | B1 | no_change/worsened/unmeasurable NO suman; se muestran con etiqueta honesta |
| B4 | Vista por ventana hoy/7d/30d | 2 §1 | B2-B3 | Cada ventana muestra SOLO datos reales medidos; sin proyección inventada |
| B5 | Retorno neto (si plan activo) | 2 §1b | B2 + precio Pro [Nico] | "VANOVA te cuesta X y recuperó Y → retorno neto +Z"; si no hay plan, solo € capturado |
| B6 | Cierre del loop "lo ve, reconoce, comparte" + CTA caso de venta | 2 §1b | B2 + consentimiento [SPEC 3] | Ve € → reconoce con delta → comparte (solo con dato real + consentimiento) |

**Salida Fase B:** el empresario ve el ROI real y entiende por qué paga.

---

## FASE C — PILOTO REAL (SPEC 3)

| # | Tarea | SPEC § | Depende de | Criterio de aceptación |
|---|---|---|---|---|
| C1 | Registro de eventos del piloto (`pilot_events.py`: source.connected, opportunity.seen) | 3 §12 | A7 | `metric_time_to_euro()` computa solo si ambos eventos reales existen; None si falta |
| C2 | Métrica "tiempo hasta el €" (objetivo <15 min) | 3 §11 | C1 | Registra timestamp conexión→1ª oportunidad vista |
| C3 | Demo/teaser etiquetado (modo demo con badge "Ejemplo", NO se puede marcar/medir) | 3 §5d | A2 | En demo: badge "Ejemplo" + banner; CTA "Conectar mi tienda"; marcar/medir bloqueado |
| C4 | Empty state de la vista Oportunidades | 1 §2 | A7 | "No hay oportunidades con evidencia mínima hoy" + enlace a conectar/cargar costes |
| C5 | Guión de la demo como checklist ejecutable | 3 §5c | — (documento) | Checklist paso a paso para la visita al piloto |
| C6 | Formulario de consentimiento del piloto | 3 §7b.1b | — (documento) | Texto de consentimiento; si no firma → caso anónimo |

**Salida Fase C:** el piloto real ve su € en <15 min, se registra la evidencia, y se decide Go/No-Go.

---

## DEPENDENCIAS CRÍTICAS (fuera de Nickx)

| Dependencia | Dueño | Afecta a |
|---|---|---|
| Precio del plan Pro (29 €/mes) | Nico | B5 (retorno neto) |
| Conseguir piloto real | Boss/Nico | C (todo el piloto) |
| Instalador en PC stock | Nickx/QA | C (que el piloto lo use solo) |

**Orden de ejecución recomendado:** A (1-7) → B (1-6) → C (1-6). No empezar B sin terminar A (el € del aha alimenta el valor capturado); no empezar C sin B (el piloto mide los hitos de A y B).

---

*Checklist generado por Strati. Solo diseño; no ejecutó nada. Listo para que Nickx implemente y Mathew valide.*
