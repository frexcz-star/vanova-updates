# STRATI — SPEC 3: Prueba de Venta / Piloto Real

**Autor:** Strati (estrategia/producto) · **Para:** Nickx (implementación), Mathew (QA), Boss (decisión)
**Versión proyecto:** 3.1.1 · **Estado:** Listo para implementación
**Regla:** La decisión se toma con **evidencia real** del piloto (métricas del sistema + feedback), nunca con opinión ni cifras inventadas.

---

## 0. Objetivo

Validar con un **piloto real** que VANOVA aporta valor vendible: que un empresario **ve € con SUS datos**, lo usa a diario y quiere seguir/pagar. Es la prueba de fuego antes de escalar a venta.

---

## 1. Criterios de selección del piloto

**Perfil ideal (todos deben cumplirse):**

| Criterio | Ideal | Evitar |
|---|---|---|
| Sector | PYME ecommerce con tienda online (Shopify) | negocio sin datos de ventas cargables |
| Datos | ≥20 pedidos/mes + **coste por SKU** (o dispuesto a cargarlo) | sin coste y sin querer cargarlo (el € no saldrá) |
| Decisor | El **dueño** (quien decide pagar) usa la app | solo un empleado sin poder de compra |
| Actitud | Dispuesto a dar feedback y a ser caso de referencia | no quiere feedback |

**Contactos concretos (3-5 empresas reales):**
1. **Piloto interno:** la tienda del equipo (BlisPaper) — validar el flujo completo con datos reales y afinar antes de externos.
2. **Piloto externo 1:** ecommerce Shopify cercano (red del equipo / coworking / comunidad local) que cumpla el perfil.
3. **Piloto externo 2 (opcional):** un segundo ecommerce con datos distintos (p. ej. otro sector de papelería o un producto no estacional) para variar el caso.
4-5. **Reserva:** 2 candidatos de cola si alguno no arranca o no carga coste.

**Mínimo viable:** 1 piloto interno + 1 externo son suficientes para el Go/No-Go inicial. 3-5 dan más señal pero con el tiempo limitado (~1 mes) priorizar 1 interno + 1-2 externos.

---

## 1b. Qué se les entrega en onboarding y qué se les pide

**Se entrega (a cada piloto):**
- Acceso a VANOVA (instalación o build) + credenciales de su cuenta.
- Guía corta de 5 pasos: "Conecta tu tienda → carga costes → ve tu € → marca una recomendación".
- Plantilla CSV de costes por SKU (si la usan).
- Acceso al equipo (contacto directo para dudas).

**Se les pide:**
- Cargar ventas reales + coste por SKU (datos reales, no fake).
- Usar VANOVA al menos 5 días en el primer mes.
- Marcar ≥1 recomendación como hecha y ver el resultado.
- Dar feedback en 3 checkpoints (3d / 15d / 30d).
- (Con consentimiento) permitir usar el caso como testimonio.

---

## 1c. Métricas de valor que prueban que VANOVA ayuda a VENDER (no solo de coste)

Además del € capturado/ahorrado (reducción de coste), el piloto debe evidenciar valor de VENTA:
- **Nº de oportunidades de crecimiento detectadas** con € real (cross-sell, reactivación, AOV) en sus datos.
- **Recomendaciones de venta marcadas como hechas** (el piloto actúa sobre una oportunidad de ingresos).
- **Resultado medido** de esas recomendaciones (`improved` → el € de venta incremental real).
- **Percepción:** "VANOVA me propuso una venta que no había visto" (cita, feedback).

Estas métricas prueban que VANOVA no solo reduce coste, sino que ayuda a **capturar ingresos**.

---

## 2. Métrica de éxito definida ANTES (qué cuenta como "aporta valor")

El piloto es un **ÉXITO** si cumple TODOS estos (métricas medibles con datos reales del sistema, no opinión):

| Métrica | Umbral de éxito |
|---|---|
| **Activación / aha** | Ve ≥1 oportunidad o valor con € real en <15 min (registrado) |
| **Cierre del loop** | Marca ≥1 recomendación como hecha y el sistema mide el resultado (`improved/no_change/worsened/unmeasurable`) |
| **Uso a los 30 días** | Abre VANOVA ≥5 días/mes tras el primer mes |
| **Percepción de valor** | Dice, con sus palabras, "me dijo algo que no sabía / me ahorra tiempo" (encuesta corta) |
| **Disposición a pagar** | Dice que pagaría el plan Pro (aunque no pague aún en la fase piloto) |
| **Cero € inventado** | Ningún dato mostrado fue inventado (auditable) |

**Señales de FALLO (para matar o pivotar):**
- No llega a ver € con sus datos en <15 min (por no cargar coste o bug).
- No usa la app tras el primer mes.
- No identifica ningún hallazgo útil para su negocio.

---

## 3. Timeline del piloto (duración, hitos, checkpoint)

**Duración:** 30 días.

| Hito | Tiempo | Qué se evalúa |
|---|---|---|
| **Arranque** | Día 1 | Alta + conexión + ver € en <15 min (SPEC 1). Registro del "aha". |
| **Check-in 1** | Día 3 | Feedback corto: "¿Viste algo útil? ¿Qué te confundió?" + uso inicial. |
| **Check-in 2** | Día 15 | Encuesta de 5 preguntas + "Valor Capturado" del sistema (deltas medidos). |
| **Fin** | Día 30 | Métricas finales (§2) + decisión Go/No-Go/Pivot. |

**Checkpoint intermedio (Día 7):** si el piloto no vio € (no cargó coste o bug), es señal de BLOQUEO → corregir el SPEC 1 antes de seguir.

---

## 3b. Plan de validación de 1 semana (día a día)

**Objetivo:** en 7 días tener la señal de si VANOVA aporta valor a UN piloto (instalar + conectar + ver € + marcar + medir).

| Día | Acción | Qué recoger | Qué validar |
|---|---|---|---|
| 1 | Reclutar/confirmar el piloto; entregar acceso y guía de 5 pasos | contacto, perfil, fuentes de datos | que el piloto puede instalar/conectar |
| 2 | El piloto conecta ventas + coste por SKU | tiempo hasta ver €, fricciones | el "aha" en <15 min (SPEC 1) |
| 3 | El piloto marca ≥1 recomendación como hecha | nº marcadas, qué recomendación | que el loop se cierra (medición) |
| 4 | Revisar "Valor Capturado" con datos reales | € capturado/medido (delta) | que el ROI se ve (SPEC 2) |
| 5 | Feedback 1: ¿qué viste útil / qué te confundió? | cita textual, fricciones | percepción de valor |
| 6 | Seguimiento de uso + ¿lo usarías a diario? | frecuencia, disposición | retención / pago |
| 7 | Mini-decisión Go/No-Go (1 semana) | evidencia §1b | si merece seguir a 30d o pivot |

**Datos que se recogen cada día (del sistema, reales):** conexión OK, tiempo al €, nº recomendaciones marcadas, resultados medidos, uso (sesiones), y feedback textual del piloto.

---

## 4. Cómo medir si el flujo de 15 min funcionó (señal = ready para escalar)

- **Flujo 15 min OK:** el sistema registra que el piloto vio una oportunidad con € y la marcó como hecha. Esa es la señal técnica de "funcionó".
- **Ready para escalar a venta:** piloto cumple la métrica de éxito (§2) = aha + loop cerrado + uso 30 días + dice que pagaría. Con eso, pasar a venta/más pilotos.
- **No ready:** ajustar SPEC 1 (onboarding) o SPEC 2 (Valor Capturado) antes de escalar, según dónde falle.

---

## 4b. Definición de VALIDADO vs NO VALIDADO (qué cuenta)

**VALIDADO (aporta valor vendible):** el piloto cumple TODOS estos:
- Ve ≥1 oportunidad/€ real con SUS datos en <15 min (registrado).
- Marca ≥1 recomendación como hecha y el sistema mide el resultado (sin que falle).
- Usa la app ≥5 días/mes a los 30 días.
- Dice (con sus palabras) que le aportó algo o que pagaría.

**NO VALIDADO (hay que iterar):** si falla CUALQUIERA de estos:
- No ve € en <15 min (no cargó coste o bug) → **BLOQUEO**: corregir SPEC 1 antes de seguir.
- Ve € pero no lo usa a los 30 días → **PIVOT**: revisar propuesta de valor/onboarding.
- Ve € y lo usa pero no quiere pagar → **REVISAR PRECIO**.

**Regla:** decidir con el conjunto de métricas, no con un dato aislado.

---

## 5. Plan de aprendizaje e iteración (feedback → SPEC 1 y 2)

**Cómo se itera:**
- Cada fricción del piloto en el flujo de 15 min → ajustar el **SPEC 1** (onboarding/costes).
- Si el € medido no se ve claro → ajustar el **SPEC 2** (Valor Capturado).
- Si el piloto ve valor pero no usa → revisar propuesta de valor / onboarding.
- Si ve valor y quiere pagar → ese testimonio/caso real es el material de venta para el siguiente.

**Entregables del piloto (para Boss):**
- Reporte: "el piloto vio X € de oportunidad real y marcó Y recomendaciones; resultado medido Z".
- Fricciones de onboarding (tiempo al €).
- Decisión Go / No-Go / Pivot con la evidencia.
- **Caso de venta** (cómo se presenta el resultado): un breve caso con (a) el € real que el piloto vio/capturó, (b) su cita textual de valor ("me dijo algo que no sabía"), (c) tiempo al €, (d) datos reales con consentimiento. Ese caso es el material para vender al siguiente piloto/cliente. Sin consentimiento → caso anónimo (sin nombre/negocio).

---

## 5b. Cómo presentar el resultado como caso de venta (plantilla)

```
CASO VANOVA — [sector / negocio]
- Datos conectados: Shopify/Excel + coste por SKU (real).
- Tiempo hasta ver el €: X min (objetivo <15).
- Lo que VANOVA detectó: [1-2 hallazgos con € real].
- Resultado medido: [mejoró +X € / sin cambio / ...] (delta real).
- En palabras del cliente: "[cita real, español]".
- (Opcional, con consentimiento) Nombre/tienda.
```
**Regla:** el caso solo usa datos reales registrados; nunca se inventa el € ni la cita.

---

## 6. Criterios de aceptación verificables

- [ ] El sistema registra el "aha" (1ª oportunidad € vista) y el "loop cerrado" (1ª medida).
- [ ] Las métricas del §2 son calculables desde datos reales (no inventadas).
- [ ] El reporte de piloto sale con evidencia del sistema, no con opinión.
- [ ] El flujo de 15 min es medible (timestamps en el registro).

---

## 7. PENDIENTES (dato que no tengo confirmado)

- [PENDIENTE: registro de eventos del piloto — ¿existe ya en el log de actividad?]. Si VANOVA loguea actividad, reutilizarlo ("1ª oportunidad vista", "1ª recomendación marcada", "medida realizada").
- [PENDIENTE: coste por SKU del caso interno (BlisArtPaper) — ¿está cargado o se puede cargar?]. Si no, el piloto externo es el primero viable.
- [PENDIENTE: consentimiento del piloto para usar su caso como testimonio]. Sin consentimiento, reporte anónimo (sin nombre/negocio).

---

*Documento de SPEC generado por Strati. Listo para que Nickx programe y Mathew testee.*
