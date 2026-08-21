# STRATI — Estrategia de Diseño de VANOVA

**Autor:** Strati (estrategia/producto)
**Para:** Boss (decisión) · Nickx (aplicación posible) · Mathew (QA)
**Versión proyecto:** 3.0.8 · **Estado:** Propuesta — pendiente de decisión del usuario
**Regla:** Documento de estrategia. NO es código; NO modifica el proyecto; no da órdenes a Nickx.

---

## 0. Principio rector

VANOVA debe verse y sentirse como **el analista de confianza de la empresa**: serio,
moderno, claro y, sobre todo, que **ponga el € y la decisión por delante**. Un empresario
no compra "una IA" — compra *"algo que vigila mis números y me dice qué y cuánto"*.
El diseño debe hacer que eso se sienta en los primeros 10 segundos.

Tres palabras que definen la identidad: **CONFIANZA · CLARIDAD · VALOR (€)**.

---

## 1. Identidad visual

### 1.1 Qué transmite VANOVA (atributos de marca)
| Atributo | Traducción visual |
|---|---|
| **Confianza** | rojo corporate estable, superficies limpias, datos etiquetados como reales |
| **Datos / rigor** | cifras claras, notación de € consistente, evidencia visible, sin "humo" |
| **€ / valor** | el dinero es PROTAGONISTA visual (mayor peso tipográfico) |
| **Inteligencia** | orden, jerarquía, sugestión de "algo me vigila y razona", no caos de tarjetas |

### 1.2 Paleta (evolución, no ruptura)
- **Mantener la identidad corporate red** (preferencia de marca): `#DC2626` / `#B91C1C` como
  acento único, SIN degradados orbes ni purple (anti-patrón del audit).
- **Superficies:** pasar a un fondo claro y limpio (`--surface-solid` casi blanco / crema
  muy suave), con el rojo solo como acento de foco. La marca roja se mantiene en CTA y
  estado principal; el fondo respira.
- **Semántica:** un solo verde para "ganancia/mejoró", un ámbar para "atención", un gris
  para "neutro". Nada de colores aleatorios por tarjeta.
- **Regla de honestidad:** el rojo = acción/CTA; nunca se usa rojo para un dato que no
  es real. Los badges `real / mock / empty` mantienen colores distintos y explícitos.

### 1.3 Tipografía
- Mantener **Inter** (limpieza, legibilidad). Aumentar el peso del **número €** (600–700)
  para que el dinero destaque.
- Jerarquía: título de página 30px/600; sección 18px/600; tarjeta 16px/600; cuerpo 14px;
  metadatos 12px (eliminar el exceso de MAYÚSCULAS micro).
- Mono (Geist Mono) solo para IDs/timestamps internos, nunca para cifras de negocio.

### 1.4 Tono de la interfaz (copy)
- Lenguaje de empresario, no de ingeniero: "Lo que debes mirar hoy", "Cuánto te estás
  dejando", "Oportunidad de +X €". Nunca "findings", "priorities", "upside", "UNKNOWN≠0".
- Tono: directo, útil, honesto. Cero exclamaciones falsas.

---

## 2. Jerarquía visual por pantalla (el € y el valor como protagonistas)

### 2.1 Home / Command Center — 4–6 bloques, el € arriba
**Protagonista (arriba, inconfundible):**
1. **Titular de valor:** "≈ X € capturados / en juego este mes" — número grande, rojo
   (CTA) o verde según mejore. Es el primer dato que se lee.
2. **"Qué hacer hoy":** 1–3 tarjetas, cada una con su € y un verbo ("Sube el ticket con
   este pack", "Revisa el coste de X"). Acción > panel.
**Secundario (abajo):**
3. Métricas de salud (revenue, pedidos, margen) en una fila calma — sin 24px gigantes.
4. Actividad reciente (timeline de cambios) — transmite "me vigila".
**Ocultar / mover:** autonomía (duplica Settings), CEO banner (duplica nav), inventory a
secundario. Reducir los 12+ bloques actuales.

### 2.2 Tarjeta de oportunidad (el patrón que más vende)
- **€ arriba a la izquierda, en grande, con signo** ("+41 €") — protagonista absoluto.
- Título en frase de acción ("Haz pack de A+B").
- Línea de "por qué" en lenguaje de negocio (1 línea, no técnico).
- CTA único: "Aplicar / Marcar como hecha" (rojo).
- Si no hay €: "no cuantificable con los datos actuales" — NUNCA "0 €".

### 2.3 Insights / Recomendaciones
- Estado pill pequeño (● Mejoró / sin cambio / empeoró) + delta €.
- Historial como timeline (no tabla), con el total capturado arriba.

---

## 3. Experiencia de usuario (UX): entenderlo en 1 minuto

### 3.1 Onboarding "aha en 5 minutos"
1. Pregunta clave al entrar: "¿Qué datos tienes? (Shopify / Excel / ERP)" con 1 botón.
2. Conecta/importa → **muestra 1 oportunidad real con €** en < 5 min ("Has recuperado
   potencialmente ≈ X €").
3. Nunca vacío silencioso: si no hay datos, CTA única "Conectar fuente".

### 3.2 Lenguaje
- Sustituir toda la jerga técnica por términos de negocio (lista concreta en §6).
- Mensajes de estado en primera persona de la empresa: "VANOVA detectó esto…".

### 3.3 Empty states honestos (NO "no data")
- "Conecta tu tienda para empezar a ver oportunidades" + botón "Conectar Shopify".
- "No hay oportunidades con evidencia suficiente hoy. Carga costes por producto para ver
  más." — honesto, no un fallo.

---

## 4. Elementos que generan confianza

1. **Claridad del dato:** toda cifra con su fuente/periodo etiquetado ("pedidos reales,
   últimos 30d"). Si es mock, badge claro.
2. **Honestidad (regla sagrada):** nunca € inventado. `UNKNOWN ≠ 0`. Un "no medible" claro
   da MÁS confianza que un número inventado.
3. **Badges de dato:** `REAL / SAMPLE / EMPTY` visibles y consistentes (no camuflados).
4. **Audit trail / trazabilidad:** "esto lo detectó el 12/08" — el empresario ve el
   razonamiento, confía más.
5. **Cierre del loop:** "lo marcaste, el sistema lo midió: mejoró X €" — la prueba de que
   el € no es humo.

---

## 5. Responsive / móvil (empresario consulta desde el móvil)

- **Principio:** en móvil, un teléfono es para CONSULTAR y DECIDIR, no para operar.
- **Prioridad móvil:** el titular "Total capturado" + "Qué hacer hoy" primero; resto colapsado.
- **Breakpoints:** la actual se rompe en móvil (solape de pills). Diseñar nav abajo
  (bottom-nav con 5 items: Inicio, Oportunidades, Recomendaciones, Hermes, Más) + sidebar
  oculto en drawer.
- **Cifras legibles:** números grandes, pocos por pantalla, sin tablas densas en móvil
  (timeline en su lugar).
- **Notificaciones** (lo que la proactividad 6h detecta) como primer feed en móvil —
  el empresario decide desde el móvil.

---

## 5b. Recomendaciones concretas para el dashboard (accionables)

Prioridad de aplicación (estructural, sin cambiar identidad de color):

1. **P0 — Limpiar el Home:** reducir de 12+ a 4–6 bloques; el titular "Total €" arriba;
   mover autonomía/CEO out. (guía §2.1)
2. **P0 — Patrón "tarjeta de oportunidad"** (§2.2): € grande + acción única + "no medible"
   en lugar de "0 €". Reutilizarlo en Insights y Home.
3. **P0 — Badges de estado**: sustituir grandes pills por dot + label (● Mejoró).
4. **P1 — quitar anti-patrones:** orbs/gradient purple, glass en todas las tarjetas (glass
   solo en overlays), breathing glow en botones, hover lift en todo. (del audit §9)
5. **P1 — tipografía de cifras:** peso 600–700 en el €; eliminar mayúsculas micro-labels.
6. **P1 — empty states** con copy humano + CTA única.
7. **P2 — nav móvil** (bottom-nav 5 items) y resolver el solape de pills.
8. **P2 — sync build** `dashboard.html → index.html → web/dist/*` (patrón BUG-003) tras
   cualquier cambio.

---

## 6. Nota de control (regla del usuario)

Este documento es **solo propuesta de diseño**. No modifica el proyecto ni da órdenes a
Nickx. El usuario/Boss decide qué se aplica. La identidad de color (rojo corporate) se
mantiene por preferencia de marca; lo que se evoluciona es estructura, jerarquía y copy.

---

*Documento generado por Strati. No modifica el proyecto.*
