# VALIDACIÓN — Sistema de Agentes de VANOVA (Mathew QA + Strati producto)

> Validación conjunta del sistema de agentes tras la creación de un agente de ventas.
> **Mathew (QA):** validación funcional/técnica. **Strati (estrategia/producto):** validación
> desde la piel del empresario-cliente (UX, nombres, coherencia con la propuesta de valor).
> Los hallazgos se pasan a Nickx para corregir. **Regla: solo propuestas, no se toca código.**

---

## SECCIÓN STRATI — Validación desde la piel del empresario-cliente

**Fecha:** 2026-08-21 · **Autor:** Strati (estrategia/producto)

### 1. Cómo se siente crear/ver/ejecutar un agente hoy (evidencia real)

Lo que existe en el código (revisado read-only):

- **Catálogo de agentes predefinidos (`business_analyst.py` → `AGENT_CATALOG`):** los 6 agentes
  están **en INGLÉS**, tanto nombres como descripciones y responsabilidades:
  - `Marketing Agent` — "Plans campaigns, monitors performance…"
  - `Sales Analyst` — "Analyzes sales trends…"
  - `Content Agent` — "Generates content ideas…"
  - `Inventory Agent` — "Monitors stock levels…"
  - `Customer Support Agent` — "Drafts responses…"
  - `CEO Copilot` — "Executive summary…"
- **Vista Agents (`dashboard.html`):** el botón y el modal SÍ están en español ("Crear agente",
  "Crea un agente de IA para tu negocio, sin escribir código"), con selector de rol en español
  (ventas / contabilidad / stock / marketing / soporte / CEO / general).
- **`shared/mock_data.py`:** los agentes mock también en inglés ("Trend Hunter", "Licensing
  Intelligence", "Product Designer AI", "Sales Copilot", "Forecast AI"…).

**Conclusión de coherencia:** hay una **mezcla de idiomas clara**: la *interfaz de creación*
está en español, pero el *catálogo de agentes* que se muestra al usuario está en inglés. Para
un empresario PYME no-técnico (público objetivo), los nombres/descripciones en inglés rompen la
confianza y la comprensión de qué hace cada agente. Es una fricción de adopción real.

### 2. Aportaciones / mejoras propuestas (UX, nombres, coherencia)

1. **Traducir el catálogo a español y en lenguaje de empresario** (no técnico, con verbo y €):
   - "Sales Analyst" → **"Analista de Ventas"** — "Detecta oportunidades y tendencias de venta"
   - "Marketing Agent" → **"Agente de Marketing"** — "Propone campañas y mide su rendimiento"
   - "Inventory Agent" → **"Agente de Stock"** — "Avisa de falta o exceso de inventario"
   - "Customer Support Agent" → **"Agente de Atención al Cliente"** — "Responde y clasifica incidencias"
   - "CEO Copilot" → **"Copiloto de Dirección"** — "Resumen ejecutivo y recomendaciones"
   - "Content Agent" → **"Agente de Contenidos"** — "Genera ideas de contenido y publicaciones"
2. **Alinear descripciones a la propuesta de valor**: cada tarjeta debe responder "¿qué
   gano/ahorro yo con esto?" en € y en verbo, no "plans campaigns / analyzes trends".
3. **Separar claramente el agente "de ventas" recién creado**: cuando el usuario crea un agente
   de ventas, la tarjeta debe mostrar beneficio ("te avisa de oportunidades de venta"), estado
   real, y qué datos lee — coherente con el resto del sistema (honestidad de datos).
4. **Consistencia idioma**: si la UI es en español, TODO el sistema de agentes debe ir en
   español (nombres, descripciones, estados, "en curso / terminado / fallado"). Los estados
   internos tipo `running/failed` que se cuelan al usuario deben localizarse.
5. **Claridad de acción**: en la vista de agente, el usuario debe ver claro: qué hace ahora,
   qué recomendó, y el botón para ejecutar — con estado honesto (real vs. demo).

### 3. Coherencia con la propuesta de valor
- El sistema de agentes refuerza la propuesta ("alguien vigila tus números y te dice qué y
  cuánto") si el nombre de cada agente le habla al empresario de su negocio (ventas, stock,
  marketing) — no de tecnología. El inglés actual lo aleja de ese mensaje.
- La creación sin código es correcta y el valor de la propuesta. Falta que el *catálogo* que
  se ofrece hable el idioma del usuario y explique el beneficio.

### 4. Recomendación de paso a Nickx
- **P0:** localizar el `AGENT_CATALOG` (y mock) a español con lenguaje de beneficio.
- **P1:** alinear descripciones con "qué gano / qué ahorro" y estado de datos honesto.
- **P2:** vista de agente con "qué está haciendo ahora" y "último resultado" claro.

---

> *Sección aportada por Strati. Validación desde la piel del empresario-cliente. Pendiente de
> validación técnica/QA por Mathew y de decisión del usuario para pasar a Nickx.*

---

## SECCIÓN MATHEW — Validación funcional/técnica (QA)

**Fecha:** 2026-08-21 · **Autor:** Mathew (QA)

### 1. Estado de la suite
`pytest tests/` → **726 passed, 1 skipped, 0 fallos** (114.48s). La suite completa está en verde. No hay fallos técnicos de regresión en esta área.

### 2. Verificación del agente de ventas creado (datos reales del config)
Inspeccioné `C:\Users\Admin\AppData\Local\VANOVA\config\maios.json` (el config real de la instalación):
- El agente que el usuario creó/activó aparece con `id="sales-analyst"`, `name="Sales Analyst"` — **en inglés**.
- **`role=None`** y **`hermesBot=None`** en el config.
- Permisos: `["read_orders", "read_products"]`.

**Confirmado (QA):** el nombre/descripción en inglés proviene de un **agente predefinido** del catálogo (`business_analyst.py` → `AGENT_CATALOG`), no de un dato mal introducido por el usuario. Coincide con el hallazgo de Strati.

### 3. Puntos de QA a resolver (técnicos, para Nickx)

1. **`role=None`** — El agente `sales-analyst` del catálogo no tiene campo `role` poblado. En `agent_architect.create_custom_agent` el role se traduce a permisos, pero los agentes **predefinidos** del catálogo no lo llevan. Verificar si `role` debe derivarse para todos (afecta a permisos y a la lógica de sincronización con el bot de Hermes).

2. **`hermesBot=None`** — La Fase B exige que un agente creado se sincronice a un **bot persistente de Hermes** (`agent_hermes_bot.sync_agent_to_bot`). El agente de ventas en el config **no tiene `hermesBot`** seteado. Confirmar si la sincronización del bot se ejecutó (o falló silenciosamente, ya que `create_custom_agent` hace `except Exception: log.warning(...)` y no bloquea). **Si el bot no se sincroniza, el agente no actúa como bot de Hermes aunque la UI lo presente como tal — gap funcional potencial.**

3. **Localización del catálogo (consolidado con Strati)**: los 6 agentes predefinidos están en inglés. Además del impacto de UX que describe Strati, es un **defecto de coherencia de producto**: la UI de creación está en español pero el catálogo que se ofrece no. **P0.**

4. **`shared/mock_data.py`** también tiene agentes en inglés ("Trend Hunter", "Sales Copilot", "Forecast AI"…). Si el entorno mock se sirve al usuario, introduce inglés adicional.

### 4. Recomendación de paso a Nickx (QA)

- **P0:** localizar `AGENT_CATALOG` (business_analyst.py) + `shared/mock_data.py` a español, con lenguaje de beneficio (consolidado con Strati).
- **P1:** investigar por qué `sales-analyst` tiene `role=None` y `hermesBot=None` — asegurar que la sincronización al bot persistente de Hermes (Fase B) ocurre o se reporta honestamente si falla.
- **P1:** si la UI dice "agente como bot de Hermes", el config debe reflejarlo (campo `hermesBot` poblado) o mostrar un estado honesto "bot no disponible".
- **P2:** estados internos del agente (`running/failed/...`) localizados en la UI.

---

## SECCIÓN STRATI (BARRIDO COMPLETO) — Problemas de UX/usabilidad desde la piel del empresario

**Fecha:** 2026-08-21 · **Autor:** Strati (estrategia/producto) · **Alcance:** barrido completo de UX/usabilidad (no solo agentes)

### Barrido de hallazgos (evidencia read-only, en `web/dashboard.html` y `shared/mock_data.py`)

| # | Severidad | Hallazgo | Evidencia (archivo:línea) | Impacto en el empresario |
|---|-----------|----------|---------------------------|--------------------------|
| U1 | P0 | **Saludo en inglés**: "Good morning/afternoon/evening" | dashboard.html:1939 | El empresario ve la app en inglés al entrar → "no es para mí" |
| U2 | P0 | **Estado "Offline" en inglés** (Hermes tile) | dashboard.html:2401 | Texto mezclado con UI en español |
| U3 | P0 | **Nombres de agentes en inglés** en el JS del dashboard (Trend Hunter, Sales Copilot, Forecast AI…) | dashboard.html:1470-1492, dashboard.html AGENTS | El catálogo que ve el usuario está en inglés (consolidado con Mathew) |
| U4 | P0 | **Estados crudos en inglés** en labels de tareas/agentes: "Offline", "Unknown" | dashboard.html:1496, 2567, 2588 | Estados técnicos visibles al usuario |
| U5 | P1 | **Saludo no localizado ni por hora ni idioma** — hay hora pero solo inglesa | dashboard.html:1939 | Falta personalización en español |
| U6 | P1 | **Copy técnico "insight(s)"** | dashboard.html:2620 | Término técnico, no de negocio |
| U7 | P1 | **Banda de propuesta de valor con copy genérico** "Conecta tus datos y ve tu negocio en euros" — buena dirección, falta llevarla a un CTA/ver € | dashboard.html:2475 | Bien intencionada pero sin el "ahor" del € |

### Propuestas de corrección (UX, prioridad)

**P0 — Coherencia de idioma (afecta a TODA la app, no solo agentes):**
1. Localizar TODOS los textos visibles al español: saludo ("Buenos días/tardes/noches"), estados ("Offline" → "Desconectado", "Unknown" → "—" o "Desconocido"), nombres de agentes.
2. La regla: **si un string es visible para el empresario, va en español**. Los estados internos (`running/failed/queued`) se traducen a la UI (ya hay `labels` map en inglés para esos, pero se escapan algunos como "Offline"/"Unknown").

**P1 (Beneficio en €):**
3. En el Home, junto al copy "Conecta tus datos y ve tu negocio en euros", añadir un ejemplo real: "≈ X € capturados este mes" (cuando haya dato) — cierra el loop de valor percibido.

**P2 (Pulido):**
4. Términos técnicos que se cuelan: "Insights" → "Para tu negocio", "findings" → "problemas detectados", "upside" → "potencial de €".

### Coherencia con la propuesta de valor (verdict)
VANOVA promete "alguien vigila tus números y te dice qué y cuánto". Para que el empresario lo sienta, la interfaz debe hablar su idioma (español) y su lenguaje (€, beneficio, no tecnología). El inglés actual y los estados técnicos crudos diluyen esa propuesta. **La localización completa (P0) es el paso de mayor impacto en adopción.**

---

> *Barrido completo de UX añadido por Strati. Complementa la sección de agentes (arriba) y la QA de Mathew. Los hallazgos se pasan a Nickx. Regla: solo propuestas, no se toca código.*
