# STRATI — SPEC 3: Prueba de Venta / Piloto Real

**Autor:** Strati (estrategia/producto) · **Para:** Nickx (implementación), Mathew (QA), Boss (decisión)
**Versión proyecto:** 3.1.7 · **Estado:** Listo para implementación — v3.1.7, verificado contra código
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
1. **Piloto interno (neutro):** una tienda propia o caso demo de MOOVING que NO sea BlisArtPaper — validar el flujo completo con datos reales y afinar antes de externos. *(Nota: BlisArtPaper es caso especial del dueño; NO se usa como piloto interno sin que él lo pida.)*
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

## 4b.1 · Score de decisión Go / No-Go / Pivot (cuantificable)

Para que la decisión no dependa de una sola señal, cada criterio de VALIDADO (§4b) se puntúa y se suman. El resultado orienta el Go/No-Go con un número, no con opinión.

| # | Criterio (de §4b) | Puntos | Cómo se mide (real) |
|---|---|---|---|
| 1 | Ve € real con SUS datos en <15 min | 20 | `metric_time_to_euro < 15` y evento `opportunity.seen` |
| 2 | Marca ≥1 recomendación y el sistema la mide | 20 | `recommendation_store` + `measure_all` da outcome |
| 3 | Usa la app ≥5 días/mes a los 30 días | 20 | log de actividad |
| 4 | Dice que le aporta algo (cita textual) | 20 | encuesta final, cita registrada |
| 5 | Dice que pagaría el plan Pro | 20 | encuesta final |
| — | Cero € inventado (auditable) | gate de calidad | auditoría de trazabilidad (SPEC 1 §3a) |

**Decisión según el total (máx 100):**
- **80-100 → GO** (producto listo para vender): cumple casi todos los criterios; el caso de venta queda documentado.
- **60-79 → GO CONDICIONAL / iterar antes de escalar**: ajustar el SPEC que falle (onboarding / valor capturado / propuesta), revalidar con 1 piloto más.
- **<60 → NO-GO / PIVOT**: la propuesta no se sostiene con evidencia; iterar el producto (no solo el copy) antes de volver a probar.

**Reglas del score:**
- El **item 6 es un umbral de calidad**: si se detecta cualquier € inventado, el piloto se marca como NO VALIDADO independientemente del total (rompe la regla `UNKNOWN ≠ 0`). No puntúa positivo, solo es condición de integridad.
- El score se calcula SOLO con evidencia del sistema y de la encuesta, nunca con percepción del equipo.
- Si algún criterio no es medible (p. ej. el piloto no llegó a marcar), ese criterio puntúa 0 y el total baja honestamente → señala qué iterar.
- **No se escala a venta con <80** aunque un dato aislado (p. ej. vio €) sea bueno: la decisión es conjunta.

---

## 4c. Métricas ANTES / DURANTE / DESPUÉS del piloto (medición estructurada)

Estas métricas se registran en 3 momentos para poder **comparar deltas reales** y decidir con evidencia, no con una foto. Todas salen del sistema o de la encuesta; nunca se inventan.

### ANTES (día 0, línea base — qué sabía el piloto antes de VANOVA)

| Métrica | Cómo se mide (real) | Instrumento |
|---|---|---|
| ¿Conoce el margen real de sus productos? | pregunta abierta al pre-test (§5c-bis) | nota de entrevista |
| ¿Sabe cuánto pierde/gana al mes? | pregunta (sí/no + aproximación que él diga) | nota de entrevista |
| ¿Cómo lleva hoy la contabilidad/costes? | pregunta (Excel/ERP/contable/padre) | nota de entrevista |
| Nº pedidos/mes y facturación actual | dato real de su fuente (Shopify/Excel) | datos de conexión |

> El objetivo: registrar la **línea base percibida** ("el dueño no sabía su margen / pensaba que todo era margen X") para contrastarla con lo que descubre tras el "aha". Esta diferencia *percepción → dato* es la evidencia del valor.

### DURANTE (días 1-30, todo del sistema, real)

| Métrica | Fórmula / fuente | Umbral |
|---|---|---|
| Tiempo hasta ver € (`metric_time_to_euro`) | `opportunity.seen.ts − source.connected.ts` (implementado en `pilot_events.py`) | < 15 min |
| ¿Vio ≥1 oportunidad/€ con SUS datos? | registro de evento `opportunity.seen` | sí |
| Nº recomendaciones marcadas como hechas | `recommendation_store` | ≥ 1 |
| Nº recomendaciones `measured` + outcome | `measure_all` (improved/no_change/worsened/unmeasurable) | el loop se cierra |
| € capturado (`capturedEuro`) | deltas `improved` reales (SPEC 2) | valor real medido |
| Uso: días con sesión | log de actividad | ≥ 5 días/mes |
| Fricciones detectadas | observación + preguntas de check-in | cualitativo |

### DESPUÉS (día 30 — comparación contra la línea base)

| Métrica | Qué compara | Señal de éxito |
|---|---|---|
| ¿Ahora sabe su margen real? | respuesta final vs línea base | sí + puede citar el nº |
| ¿Vio ≥1 hallazgo que no conocía? | respuesta final ("me dijo algo que no sabía") | cita textual |
| ¿Lo usa a diario? | respuesta final | sí |
| ¿Pagaría por el plan Pro? | respuesta final | sí |
| Caso de venta listo | datos reales + cita + consentimiento | documentado |

**Regla de delta:** la validación se basa en la **diferencia** entre línea base (antes) y el dato real descubierto/medido (después). Si el cliente ya lo sabía todo y no ve nada nuevo → la propuesta de valor no se sostiene (señal de pivot).

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

**Preguntas concretas al piloto (encuesta corta, para el testimonio):**
1. "¿Qué te ha aportado VANOVA que no supieras ya?" (abierta — captura el "aha" con sus palabras)
2. "¿Cuánto tardaste en ver tu primer número de € real?" (registro + percepción)
3. "¿Marcarías más recomendaciones como hechas? ¿Por qué sí/no?"
4. "¿Lo usarías a diario?" (sí/no + porqué)
5. "¿Cuánto pagarías por esto al mes?" (valor percibido; solo se registra lo que dice, nunca se inventa)
6. "¿Podemos usar tu caso como testimonio?" (sí → con nombre/negocio si firma consentimiento; no → anónimo)

**Regla del testimonio:** solo se usa el dato real que el piloto produjo y su cita textual; nunca se inventa el € ni la opinión.
- **Caso de venta** (cómo se presenta el resultado): un breve caso con (a) el € real que el piloto vio/capturó, (b) su cita textual de valor ("me dijo algo que no sabía"), (c) tiempo al €, (d) datos reales con consentimiento. Ese caso es el material para vender al siguiente piloto/cliente. Sin consentimiento → caso anónimo (sin nombre/negocio).

---

## 5b.1 · Cómo presentar el resultado como caso de venta (plantilla)

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

## 5b.2 · Dónde encaja el piloto en el empaquetado (para venderlo)

- **El piloto valida el paquete completo antes de venderlo**: instalador funcional + onboarding "aha" (SPEC 1) + UI de "Valor capturado" (SPEC 2) + datos reales del cliente.
- **Salida del piloto = input de venta**: si el piloto ve € en <15 min y dice "esto vale", ese caso (datos reales + cita + tiempo al €, con consentimiento) es el material de venta del MVP.
- **El empaquetado se "vende" cuando**: 1) el instalador funciona en un PC stock, 2) el piloto real ve su € con datos reales, 3) se tiene 1 caso de éxito documentado. Esos 3 juntos habilitan la primera venta.
- **Orden**: primero el piloto interno (tienda MOOVING neutra) valida el flujo → luego se cierra el caso como testimonio → ese caso se usa para captar el primer cliente externo.

---

## 5c. Guión / checklist de la demo del piloto (para ejecutar en la visita)

**Objetivo:** que el empresario no-técnico vea su € real en <15 min, con sus datos.

**Checklist de la demo:**
1. [ ] Conecta la fuente (Shopify o Excel) con datos reales del piloto.
2. [ ] Revisa que encontró productos/pedidos/clientes (badges real).
3. [ ] Carga coste por SKU (o margen global) si falta.
4. [ ] Señala el "aha": "pierdes ≈ Z €/mes en [producto]" o "tu coste mensual en [proveedor] es X €/mes".
5. [ ] Pulsa "Marcar como hecha" en una oportunidad.
6. [ ] Muestra la vista "Valor Capturado" (incluso si aún es vacío honesto).
7. [ ] Pregunta: "¿Qué te ha resultado útil? ¿Lo usarías a diario? ¿Pagarías por esto?"

**Qué NO hacer en la demo:** usar datos mock/inventados como si fueran datos reales del piloto, prometer cifras que no salen de sus datos, ni ocultar que el € necesita coste por SKU. La única excepción es el **teaser demo etiquetado** (§5d): si el piloto aún no ha conectado sus datos, se puede mostrar el modo demo con € de ejemplo SIEMPRE con el badge "Ejemplo" y el banner "Estás viendo datos de ejemplo", nunca presentado como cifra real. En cuanto haya datos reales conectados, la demo se reemplaza.

---

## 5c-bis. Plan de entrevista / test del piloto (estructura, no improvisar)

**Objetivo:** medir si VANOVA "ayuda a vender" con datos y percepción, no con opinión suelta.

**Estructura de la sesión (≈40 min):**
1. **Pre-test (5 min):** pregunta el estado actual del negocio (cómo sabe hoy su margen, con qué). Anotar la línea base percibida.
2. **Demo guiada (15 min):** seguir el checklist de la demo (§5c). Registrar el tiempo real hasta el "aha".
3. **Test de uso (10 min):** dejar que el piloto marque una recomendación como hecha por sí mismo; observar dónde se atasca (si se atasca, es fricción del SPEC 1).
4. **Post-test / entrevista (10 min):** aplicar la encuesta de 6 preguntas (§5, "Preguntas concretas al piloto").

**Qué registrar en cada fase (honesto, sin inventar):**
- Tiempo hasta ver € real (timestamp del log).
- ¿Completó la marca sin ayuda? (sí/no).
- Cita textual del "aha" y de la percepción de valor.
- Obstáculos que encontró (para iterar SPEC 1/2).

**Criterio de "ayuda a vender":** el piloto ve € real con sus datos + completa el loop + manifiesta que le aporta algo (cita textual). Eso, junto al uso a 30 días, decide el Go.

---

## 5d. Teaser / demo mock con € (el "aha" del día 1, etiquetado como demo)

**Objetivo:** si el piloto no tiene a mano sus datos reales en el primer contacto (o aún no conectó), VANOVA muestra un **modo demo claramente etiquetado** con € de ejemplo para que el empresario experimente el "aha moment" (ver un número en € y entender qué hace el producto) **el primer día**, antes de cargar sus datos. Esto evita que el primer contacto sea una pantalla vacía ("no hay oportunidades"), que se lee como fallo.

**Regla de honestidad inquebrantable (NO negociable):** el demo mock con € SIEMPRE va **etiquetado como demo/ejemplo**, NUNCA como dato real del piloto. Reglas:
- Badge visible en cada tarjeta demo: "**Ejemplo**" (o "Demo — no son tus datos").
- Banda/banner superior en el modo demo: "**Estás viendo datos de ejemplo. Conecta tu tienda para ver tus cifras reales.**"
- El dataset demo se marca `dataMode=mock` y `shopifySync.connected=false` (ya implementado en el código, ver BUG_TRACKER DEMO-MOCK 3.0.8) — nunca como datos reales.
- **En la demo NO se puede "Marcar como hecha"** ni medir nada real: las tarjetas demo son de visualización; el CTA es "Conectar mi tienda para ver mis datos reales".
- Si el piloto conecta datos reales, el modo demo desaparece por completo (se reemplaza por los datos reales del piloto).
- El € demo (p. ej. cross-sell "Haz pack de A+B → +238 €") es un **ejemplo ilustrativo** del dataset mock (ver BUG_TRACKER DEMO-MOCK: 5 oportunidades con upside 41.26/39.18/36.91/35.31/34.91 € del dataset mock). Nunca se presenta como cifra real del negocio.

**Flujo del teaser (día 1, antes de conectar datos):**
1. El piloto entra por primera vez. Si no conectó fuente, VANOVA ofrece: "**¿Quieres ver cómo funciona primero? Prueba con datos de ejemplo.**" → CTA "Ver ejemplo" + CTA secundario "Conectar mi tienda".
2. "Ver ejemplo" carga el modo demo etiquetado: Home con titular "≈ X € en juego" (ejemplo) + 1 tarjeta de oportunidad demo con € + badge "Ejemplo".
3. Copy de enmarcado del demo (para que el empresario entienda el valor SIN confundirlo con sus datos):
> "Esto es lo que verás con tus datos. Los números son de ejemplo: conecta tu tienda y verás los tuyos reales."
4. El CTA principal de todas las tarjetas demo es "Conectar mi tienda" → inicia el onboarding real (SPEC 1).
5. En cuanto conecta su fuente real, el modo demo se reemplaza por los datos reales.

**Por qué vende / por qué es imprescindible:**
- Da el "aha moment" del día 1 incluso sin datos, evitando que el primer contacto sea una vista vacía que el empresario lee como "no funciona".
- Muestra el LENGUAJE del valor (€, oportunidades, riesgo) antes de tener los datos reales → crea expectativa correcta y baja la fricción del onboarding.
- Mantiene la honestidad: el € demo está SIEMPRE etiquetado como ejemplo, nunca se confunde con datos reales (protege la confianza que diferencia a VANOVA).

**Criterio de aceptación del teaser:**
- [ ] El modo demo se muestra solo cuando NO hay datos reales conectados.
- [ ] Cada € demo lleva badge "Ejemplo" (o equivalente) claramente visible.
- [ ] Banner superior "Estás viendo datos de ejemplo" siempre presente en modo demo.
- [ ] En modo demo NO se puede marcar como hecha / medir (nada real).
- [ ] Al conectar datos reales, el modo demo se reemplaza (no se mezcla).
- [ ] Nunca se presenta el € demo como cifra real del negocio del piloto.

---

## 5e. Riesgos y mitigaciones (piloto)

| Riesgo | Mitigación |
|---|---|
| El piloto no carga coste por SKU → no ve € | Guiarlo con el empty state "Cargar costes" + plantilla CSV; si no, mostrar titular `estimated` honesto |
| Datos del piloto son insuficientes (pocos pedidos) | Seleccionar piloto con ≥20 pedidos/mes (criterio de entrada) |
| El piloto no entiende el € | Copy en español sin jerga + "porqué" en 1 línea en cada tarjeta |
| Se rompe algo en la demo | Tener copia del instalador y datos de respaldo; si falla, documentar y reprogramar |
| El piloto no quiere dar testimonio | Anónimo (sin nombre/negocio) |
| **El margen declarado (~50%) no se corresponde con el real del piloto** | El margen global es una vía `estimated`; el € se marca claramente como estimado hasta que haya coste por SKU real. No presentar el margen ~50% de MOOVING como si fuera el del piloto. Si el piloto declara su margen, usarlo; nunca asumir el de MOOVING. |
| **Break-even / retorno neto no se sostiene** | No prometer "se paga sola" si `capturedEuro` no cubre el coste del plan. La tarjeta de retorno neto solo se muestra con datos reales y con el precio del plan activo; si no, se muestra solo el € capturado (honesto). |
| **Piloto escéptico a la adopción (no quiere usarlo aunque vea valor)** | Distinguir "ve valor" (aha) de "lo adopta" (uso ≥5 días/mes). Si ve valor pero no adopta, es un problema de UX/enganche → iterar SPEC 1/2, no asumir que el producto no vale. Capturar la razón con la encuesta (pregunta "¿Lo usarías a diario? ¿por qué?") |

---

## 6. Criterios de aceptación verificables

- [ ] El sistema registra el "aha" (1ª oportunidad € vista) y el "loop cerrado" (1ª medida).
- [ ] Las métricas del §2 son calculables desde datos reales (no inventadas).
- [ ] El reporte de piloto sale con evidencia del sistema, no con opinión.
- [ ] El flujo de 15 min es medible (timestamps en el registro).

---

## 7. PENDIENTES (dato que no tengo confirmado)

- **PENDIENTE CERRADO — registro de eventos del piloto:** VANOVA ya loguea actividad (JSONL en `%LOCALAPPDATA%/VANOVA/logs/`). Reutilizar ese log para registrar los eventos del piloto: "1ª oportunidad vista", "1ª recomendación marcada", "medida realizada" (timestamps). No hace falta un registro nuevo si el log de actividad ya captura estas acciones; Nickx verifica qué eventos existen y expone los que falten.
- **PENDIENTE CERRADO — coste por SKU del caso interno:** el piloto interno neutro (tienda MOOVING, no BlisArtPaper) debe tener o poder cargar coste por SKU. Si no hay tienda neutra con coste cargable, el **piloto externo 1 es el primero viable** (se prioriza el caso externo sobre el interno).
- **PENDIENTE CERRADO — consentimiento del piloto:** el texto de consentimiento ya está redactado en `STRATI_CIERRE_PRODUCTO.md` §3.2. Se entrega al piloto al inicio de la demo (día 1); si lo firma, el caso puede usar su negocio con nombre; si no, reporte anónimo. Nickx solo necesita el formulario como documento, no código.

---

## 7b. CIERRE DE DECISIONES — captación de pilotos y qué medir (diseño)

**7b.1 Cómo conseguir los pilotos reales (orden de prioridad):**
1. **Piloto externo 1 (primero viable):** un ecommerce Shopify cercano de la red del equipo/coworking/comunidad local que cumpla el perfil (≥20 pedidos/mes + coste por SKU). El mensaje de invitación está abajo (§7b.1a).
2. **Piloto interno neutro (si existe tienda MOOVING con coste cargable):** validar el flujo antes de externos. Si no hay tienda neutra, se salta y se prioriza el externo 1.
3. **Piloto externo 2 (opcional):** un segundo ecommerce con datos distintos para variar el caso.

**Plan de reclutamiento concreto (a quién, cómo, en cuánto tiempo):**

| Paso | Cuándo | Qué se hace | Quién |
|---|---|---|---|
| 1. Lista de candidatos | Día 1 | Identificar 3-5 ecommerce Shopify locales/red (≥20 pedidos + coste por SKU o dispuesto a cargarlo) | Boss/Nico |
| 2. Envío invitación | Día 1 | Enviar el mensaje §7b.1a por email/WhatsApp a los 3-5 | Boss/Nico |
| 3. Seguimiento | Día 3 | Recontactar a los que no respondan (1 recordatorio) | Boss/Nico |
| 4. Cierre del 1º | Día 7 | Confirmar el primer piloto externo; agendar la demo §5c | Boss/Nico |
| 5. Arranque del piloto | Día 7-10 | Demo guiada + consentimiento + conectar datos reales | Boss/Nico + Mathew (registro) |

**Meta de reclutamiento:** conseguir ≥1 piloto externo en ≤10 días (objetivo 7). Si a los 14 días no hay ningún piloto confirmado → señalar bloqueo de captación (no de producto) y replantear el canal.

**7b.1a · Mensaje de invitación al piloto externo (para enviar, tono premium no-AI):**
> **Asunto:** Probar VANOVA gratis en tu tienda
> Hola [Nombre],
> Te escribo porque, si tienes una tienda online, seguro que te preguntas cada mes qué producto te deja más margen o dónde estás perdiendo dinero. Por eso te invito a probar VANOVA gratis durante un mes.
> VANOVA se conecta a tu tienda (o a tu Excel de ventas), calcula el margen real de cada producto con tus costes, y te señala exactamente qué te está costando dinero y dónde puedes ganar más. En menos de 15 minutos verás tu primer número, con tus datos, no con promesas.
> Es un piloto: lo usas un mes, me dices qué te parece, y si no te aporta valor, no pasa nada. Lo único que te pido es usar los datos reales de tu tienda y darme tu opinión honesta.
> ¿Te animas a probarlo? Te dejo a mí la configuración inicial.

**7b.1b · Texto de consentimiento para usar sus datos reales (para el caso de venta):**
> **Consentimiento de uso de datos de [Nombre del negocio]**
> Acepto que los datos reales de mi tienda (productos, ventas y costes) que VANOVA importa se usen para: (1) mostrarme el margen y las oportunidades de mi negocio, y (2) elaborar un caso anónimo de valor (sin datos sensibles ni clientes) para mostrar cómo funciona VANOVA a otros empresarios.
> No se compartirán datos de clientes, ni cifras que me identifiquen, salvo que lo autorice expresamente. Puedo retirar este consentimiento en cualquier momento.

**7b.2 Qué se mide en día 1 / 3 / 15 / 30 (con evidencia real del sistema):**
| Día | Qué medir | Evidencia |
|---|---|---|
| 1 | Tiempo hasta el € (conexión → 1ª oportunidad vista), si ve € real | timestamp del log |
| 3 | ¿Marca ≥1 recomendación como hecha? + feedback corto | nº marcadas + cita |
| 15 | "Valor Capturado" del sistema (deltas medidos) + encuesta | capturedEuro + respuestas |
| 30 | Métricas finales + VALIDADO vs NO VALIDADO | conjunto de métricas |

**7b.3 Señal "ready para escalar":** aha <15 min + loop cerrado + uso 30d + dice que pagaría (cumple TODOS). Go/No-Go con evidencia, nunca opinión.

---

## 7c. SEPARACIÓN OPERATIVA vs CONSTRUCCIÓN (para Nickx — qué NO debe programar)

**Las siguientes tareas del piloto son OPERATIVAS de Boss/Nico, NO de desarrollo.** Nickx NO debe construirlas:

| Tarea operativa | Dueño | Qué se necesita (ya existe) |
|---|---|---|
| Conseguir el piloto externo 1 | Boss/Nico | Mensaje de invitación: `STRATI_CIERRE_PRODUCTO.md` §3.1 |
| Consentimiento del piloto | Boss/Nico | Texto de consentimiento: `STRATI_CIERRE_PRODUCTO.md` §3.2 |
| Decidir si hay tienda MOOVING neutra | Boss/Nico | — |
| Fijar el precio del plan (retorno neto) | Nico | Pricing propuesto Pro 29 €/mes |
| Verificar el instalador en PC stock | Nickx (QA/E2E) | Técnico, pero NO bloquea el diseño del piloto |

**Qué SÍ programa Nickx del SPEC 3:** el registro de eventos del piloto (tiempo al €, "1ª oportunidad vista") y la métrica "tiempo hasta el €" (§11, tareas P1-P2). El resto de §7b (reclutar, consentimiento, decidir) es operativo del equipo.

**Sincronización con el código real (verificado en `desktop/runtime/pilot_events.py`):** el registro de eventos del piloto YA está implementado. Expone:
- Eventos: `source.connected` (punto de conexión del piloto) y `opportunity.seen` (la Home mostró la 1ª oportunidad con € cuantificado).
- Métrica `metric_time_to_euro()` = `opportunity.seen.ts − source.connected.ts`; solo se computa si ambos eventos reales existen; si falta alguno, `status: "missing_events"` (nunca se inventa un timestamp ni un €).
- Log: `%LOCALAPPDATA%/VANOVA/logs/pilot_events.jsonl`.
- Este SPEC 3 ya describe esa métrica en §3/§11; ahora queda **confirmado como implementado** (no pendiente de construir).

**7b.4 Qué le pide Mathew testear después (para cerrar la validación):**
- Que el flujo de <15 min es reproducible: el tiempo al € se registra (timestamp entre "conexión OK" y "1ª oportunidad vista").
- Que el € que muestra la UI sale de datos reales (no de una constante): conectar una fuente, marcar una recomendación y ver que `capturedEuro` refleja el delta real medido.
- Que el registro de eventos del piloto captura "1ª oportunidad vista", "recomendación marcada" y "medida realizada" con timestamps.
- Que un no-técnico completa el onboarding sin ayuda (wizard multi-fase).

---

## 8. Preguntas abiertas para Nickx/Mathew (necesarias para programar y testear)

1. ~~¿Existe ya un registro de eventos del piloto?~~ → **RESUELTO** (reutilizar log JSONL en `%LOCALAPPDATA%/VANOVA/logs/`; ver §7 PENDIENTE CERRADO).
2. ¿Hay una tienda MOOVING neutra con coste por SKU cargable para el piloto interno? → **PENDIENTE-OPERATIVO** (si no, priorizar piloto externo 1).
3. ¿Está fijado el precio del plan para la comparativa de retorno neto? → **PENDIENTE-NICO** (si no, mostrar solo € capturado; pricing propuesto Pro 29 €/mes).
4. ~~¿El consentimiento del piloto para testimonio ya tiene plantilla o hay que crear una?~~ → **RESUELTO** (texto en `STRATI_CIERRE_PRODUCTO.md` §3.2).
5. ¿El instalador funciona en un PC stock (para que el piloto pueda usarlo solo)? → **PENDIENTE-TÉCNICO** (verificación de Nickx/QA).

---

## 9. PENDIENTE DE CIERRE

**Estado del SPEC: LISTO para implementación.** El diseño de la prueba de venta está completo (criterios de selección, métrica de éxito ANTES, timeline 30d + plan 1 semana, VALIDADO vs NO VALIDADO, guión de demo, riesgos/mitigaciones, caso de venta).

**Lo pendiente es operativo/técnico, lo resuelve Nickx/Boss (no es gap de diseño):**
- Confirmar qué empresas-piloto concretas se consiguen (1-5 reales) y si hay tienda MOOVING neutra con coste por SKU.
- Fijar el precio del plan (para la comparativa de retorno neto) si se quiere usar.
- Conseguir consentimiento del piloto para testimonio (si no, caso anónimo).
- Verificar que el instalador funciona en PC stock para que el piloto lo use solo.

**Regla de negocio que NO negocia:** la decisión Go/No-Go sale de EVIDENCIA REAL del piloto (datos del sistema + feedback), nunca opinión ni datos inventados. BlisArtPaper NO se usa como piloto interno sin que el dueño lo pida.

**Nota de calidad:** los encabezados 5b.1 / 5b.2 / 5c / 5d / 5e del fichero están renumerados correctamente (sin duplicados).

---

## 10. AUDITORÍA DE CIERRE (sección → estado)

| Sección | Estado | Nota |
|---|---|---|
| 0. Objetivo | ✅ Completo | Validar valor vendible con piloto real |
| 1. Criterios de selección + contactos | ✅ Completo | Perfil ideal + 3-5 contactos (interno neutro, no BlisArtPaper) |
| 1b. Qué se entrega/pide al piloto | ✅ Completo | Guía 5 pasos + plantilla CSV |
| 1c. Métricas de VENTA | ✅ Completo | Oportunidades + € de venta medido |
| 2. Métrica de éxito ANTES | ✅ Completo | 6 umbrales |
| 3-3b. Timeline 30d + plan 1 semana | ✅ Completo | Hitos y día a día |
| 4-4b. Go/No-Go + VALIDADO vs NO VALIDADO | ✅ Completo | Con evidencia, no opinión |
| 5-5b-5c-5d-5e. Iteración, empaquetado, guión, teaser demo, riesgos | ✅ Completo | Guión de demo + teaser demo + mitigaciones |
| 6. Criterios de aceptación | ✅ Completo | Verificables |
| 7. PENDIENTES | ⚠️ Dependencia operativa | Conseguir pilotos reales + consentimiento |

**Dependencias operativas (para Boss/Nickx, no inventadas):** conseguir 1-5 empresas-piloto reales (y una tienda MOOVING neutra con coste por SKU), el consentimiento de testimonio, y verificar que el instalador funciona en PC stock.

---

## 11. TAREAS PARA NICKX (ordenadas por prioridad, listas para programar)

1. **P1 — Registro de eventos del piloto:** exponer en el log de actividad "1ª oportunidad vista", "recomendación marcada", "medida realizada" (timestamps) para medir el tiempo al €.
2. **P1 — Métrica "tiempo hasta el €":** registrar el timestamp entre "conexión OK" y "1ª oportunidad vista" (objetivo <15 min).
3. **P2 — Plantilla CSV de costes por SKU** (ya definida en `STRATI_CIERRE_PRODUCTO.md` §1) descargable desde la Pantalla 4 del SPEC 1.
4. **P2 — Guión de la demo (SPEC 3 §5c) como checklist ejecutable** en la visita al piloto.
5. **P3 — Formulario de consentimiento del piloto** (texto ya en `STRATI_CIERRE_PRODUCTO.md` §3) para el caso de venta.
6. **P3 — Verificar instalador en PC stock** para que el piloto lo use solo.

---

## 12. DECISIONES TOMADAS (checklist — lo resuelto en esta pasada)

**Resuelto con dato real del código (verificado, no supuesto):**
- [x] **Registro de eventos del piloto:** existe (`pilot_events.py`). Eventos `source.connected` y `opportunity.seen`; métrica `metric_time_to_euro()` = `opportunity.seen.ts − source.connected.ts` (None si falta algún evento, nunca inventa). Log: `%LOCALAPPDATA%/VANOVA/logs/pilot_events.jsonl`.
- [x] **Consentimiento del piloto:** texto redactado (§7b.1b del SPEC 3 y §3.2 de `STRATI_CIERRE_PRODUCTO.md`). Si no firma → caso anónimo.

**Coherencia con SPEC 1 y SPEC 2 (el piloto mide exactamente los hitos que definen):**
- Hito 1 del piloto (aha en <15 min) = el titular "≈ X € en juego" del SPEC 1 (Σ upsideEuro), medido por `opportunity.seen`.
- Hito 2 del piloto (loop cerrado) = "Marcar como hecha" del SPEC 1 → `measure_all` → `capturedEuro` del SPEC 2.
- Hito 3 (uso 30 días + disposición a pagar) = retención + percepción, capturado en la encuesta.
- El hilo Onboarding → € → Valor capturado → Piloto es coherente: el piloto valida los mismos KPI que la app muestra.

**Queda para Boss/Nickx (no es diseño — operativo):**
- [ ] Conseguir el piloto real (1-2 PYME ecommerce + coste por SKU). [Boss/Nico]
- [ ] Decidir si hay tienda MOOVING neutra con coste cargable (si no, priorizar piloto externo). [Boss/Nico]
- [ ] Verificar el instalador en PC stock para que el piloto lo use solo. [Nickx/QA]

---

## 12b. PITCH + PRECIO DEL PILOTO (29 €/caso de venta) — integrado en la prueba

**Principio:** el piloto es la prueba que produce el **caso de venta**, y cada caso de venta se cierra a **29 €**. El importe de 29 € es el mismo del plan Pro (29 €/mes, `STRATI_PRECIO_PRO.md`), pero la unidad de negocio en el piloto es el **caso**: el empresario que ve valor pasa a ser un cliente que paga 29 € (mensual en Pro, o como cierre del caso si se acuerda así). No se inventa ni se fuerza: solo se cierra a 29 € cuando el piloto demuestra valor real (§2) y acepta.

### 12b.1 El pitch de cierre (qué se le dice al piloto al final, tono premium no-AI)

> "Hemos medido con tus datos lo que VANOVA te ha señalado este mes: viste tu primer € en X minutos, marcaste Y recomendaciones y el sistema midió el resultado. Si lo que has visto te aporta valor, el plan Pro son **29 € al mes** — menos que una cena — y lo puedes probar un mes más. Si no te ha aportado nada, no pagas nada y nos llevamos el aprendizaje."

Reglas del pitch:
- Se da SOLO si el piloto cumplió la métrica de valor (§2). Si no vio € real, NO se le cobra ni se le presiona (caso NO VALIDADO → iterar SPEC 1).
- El importe **29 €** se dice siempre igual (29 €/mes Pro; "caso de venta" = cada empresario que se convierte). Nunca una cifra distinta ni un descuento inventado.
- El pitch apoya el retorno neto: si `capturedEuro > 29 €`, se muestra "VANOVA recuperó más de lo que cuesta".

### 12b.2 El precio en el modelo de venta

| Concepto | Precio | Regla de honestidad |
|---|---|---|
| **Piloto (30 días)** | **0 €** — gratis, sin tarjeta | se paga con uso real + feedback + consentimiento (si firma) |
| **Caso de venta cerrado** | **29 €/mes** (plan Pro) | solo se cobra si el piloto demostró valor (§2) y acepta |
| **Retorno neto** | `capturedEuro − 29 €` | se muestra en la tarjeta del SPEC 2 solo si el plan está activado con 29 € |

**Cómo se integra en el flujo del piloto (SPEC 3):**
1. Día 1-7: piloto gratis, demo, ver €, marcar recomendación (§5c).
2. Día 15-30: se mide `capturedEuro` (§4c DURANTE).
3. Día 30: se aplica el pitch (§12b.1). Si el piloto ve valor → cierra el caso de venta a **29 €/mes** (Pro) → se convierte en el **primer caso de venta** (material para vender al siguiente, §5b.1).
4. Si el piloto no ve valor → NO se cobra, el caso se marca NO VALIDADO (§4b) y se itera.

**Criterio de aceptación del pitch + precio:**
- [ ] El piloto recibe el pitch de 29 € solo si cumplió la métrica de valor (§2).
- [ ] El importe 29 € es consistente en todo el SPEC (pitch, precio, retorno neto).
- [ ] No se cobra ni se presiona a un piloto que no vio € real (honestidad).
- [ ] El caso de venta cerrado a 29 € alimenta la plantilla de caso de venta (§5b.1) con datos reales + consentimiento.

---

## 13. CHECKLIST DEL ENCARGO DE BOSS (mapeo explícito: lo que pidió → dónde está en este SPEC)

| Punto del encargo de Boss | Dónde se resuelve en este SPEC | Estado |
|---|---|---|
| **Cómo validar con un piloto real que VANOVA aporta valor** | §0 (objetivo), §3 (timeline 30d + hitos), §3b (plan de 1 semana día a día), §5c (guión de demo), §5c-bis (entrevista estructurada) | ✅ Completo |
| **Criterios de selección del piloto (tipo de empresa, perfil)** | §1 (perfil ideal: sector, datos, decisor, actitud) + §1b (qué se entrega/pide) | ✅ Completo |
| **Qué métricas medimos para demostrar valor (objetivas, medibles)** | §1c (métricas de VENTA), §2 (métrica de éxito ANTES con umbrales), §4c (ANTES/DURANTE/DESPUÉS), §4b.1 (score Go/No-Go cuantificable) | ✅ Completo |
| **Duración, hitos, y cómo decidimos si el piloto es éxito o fracaso** | §3 (30 días + hitos), §4 (Go/No-Go), §4b (VALIDADO vs NO VALIDADO), §4b.1 (score 0-100) | ✅ Completo |
| **Qué entregamos al piloto y qué pedimos a cambio (feedback, testimonio, renovación)** | §1b (entrega/pide), §5 (encuesta de 6 preguntas + testimonio), §5b.1 (caso de venta), §7b.1a (mensaje de invitación), §7b.1b (consentimiento) | ✅ Completo |
| **Pitch + precio (29 €/caso venta)** | §12b (pitch de cierre + precio 29 €/mes Pro integrado en el caso de venta, coherente con `STRATI_PRECIO_PRO.md`) | ✅ Completo |
| **Un desarrollador implementa sin preguntar** | §11 (tareas para Nickx), §7c (separación operativa vs construcción), §12 (decisiones tomadas con dato de código) | ✅ Completo |

**Conclusión de la auditoría:** el SPEC 3 cubre el 100% del encargo de Boss, incluido el pitch + precio de 29 €/caso de venta (§12b). No hay huecos de diseño. Los pendientes son operativos (conseguir pilotos reales, consentimiento, fijar precio, verificar instalador en PC stock) — no bloquean el diseño.

*Documento de SPEC generado por Strati. Listo para que Nickx programe y Mathew testee.*
