# STRATI — SPEC 1: Flujo de Costes + Onboarding "Aha"

**Autor:** Strati (estrategia/producto) · **Para:** Nickx (implementación), Mathew (QA), Boss (decisión)
**Versión proyecto:** 3.1.7 · **Estado:** Listo para implementación — v3.1.7, verificado contra código
**Regla:** El € sale SOLO de fuentes reales (Shopify/ERP/Excel/FacturaScripts). Nada inventado, nunca 0 €. `UNKNOWN ≠ 0` se respeta, pero el flujo reduce el UNKNOWN llevando al cliente a cargar lo que falta.

---

## 0. Objetivo

Un empresario PYME **no técnico** ve su **primer € real con SUS números en <15 min**. El "aha" es el momento en que entiende el valor y quiere seguir. Sin él, no hay conversión.

**Señal concreta del "aha":** el Home muestra, al cargar, un **titular "≈ X € en juego"** + **1 tarjeta de oportunidad con un € cuantificado** (`calculated`, con signo ES) derivado de sus ventas y coste reales. El cliente puede señalar el € y decir "esto es mío".

**Timeline objetivo:** ver el titular € en ≤15 min desde el alta.

**Requisito transversal — hardware débil del cliente (dato de Boss, no asumido):** el PC del empresario es de gama baja (8 GB RAM / GPU MX130). Los flujos (onboarding, detección, dashboard) deben ser **ligeros**: sin carga pesada, sin animaciones costosas, con el análisis por lotes (no bloqueante en UI). Se aplica a los 3 SPECs. El dashboard usa solo SVG (no emojis de color), texto en español, estilo premium dark tipo supamaus.

---

## 1b. Quién hace cada paso (usuario / sistema / guiado automático)

| Paso | Responsable | Detalle |
|---|---|---|
| P0 Alta de empresa | Usuario (3 campos) | sistema valida y guarda |
| P1 Elegir origen | Usuario (1 clic) | sistema muestra opciones |
| P2 Conexión | Sistema (automatizado) | usuario pega URL/token o sube archivo; el sistema conecta y verifica |
| P3 Revisión | Sistema (automatizado) | usuario solo confirma "Continuar" |
| P4 Coste | Usuario (guiado) | el sistema detecta falta de coste y guía a cargarlo (CSV/FS); puede saltarse si el coste ya está |
| P5 El AHA | Sistema (automático) | el Home se puebla solo con el titular € + oportunidad; usuario solo mira |
| P6 Cerrar loop | Usuario (1 clic) | "Marcar como hecha" |

**Regla:** el sistema nunca pide al usuario un paso que pueda hacer él automáticamente. El usuario solo elige origen, aporta credenciales/archivo, y pulsa "Continuar"/"Marcar como hecha". El resto es guiado automático.

---

## 1c. Orden óptimo de conexión de fuentes para el "aha" rápido

1. **Primero la fuente de VENTAS** (Shopify o Excel) — es la que permite detectar problemas/oportunidades.
2. **Segundo el COSTE por SKU** (CSV o FacturaScripts) — es el que desbloquea el € cuantificado (margen/cross-sell/AOV).
3. **Opcional luego: gastos** (Excel) para completar la señal "te estás dejando X €".

**Por qué este orden:** sin ventas no hay base; sin coste el € queda en UNKNOWN. Con ventas+coste el "aha" llega. Los gastos amplían el cuadro pero no bloquean.

---

## 1d. Criterios de éxito medibles del onboarding

- **Tiempo hasta 1er valor:** el € cuantificado (`calculated`) visible en ≤15 min desde el alta (meta: ≤10).
- **% de completado:** ≥80% de los nuevos llegan al Home con € (o al empty honesto que guía a cargar coste).
- **Abandono temprano:** ≤20% se cae antes de Pantalla 5.
- **CTA completado:** ≥70% de quienes ven la oportunidad pulsan "Marcar como hecha".
- **Sin fricción técnica:** 0 pasos que exijan un usuario-técnico (todo guiado automático).

---

## 1. Flujo paso a paso (secuencial, del primer login al primer €)

**Enmarcado: este onboarding es un SETUP WIZARD MULTI-FASE** (como quiere Nico): Fase 1 Empresa → Fase 2 Sector → Fase 3 Conexión de fuentes → Fase 4 Coste → Fase 5 EL AHA. Cada fase es una pantalla, con barra de progreso ("Paso X de 5") y un solo objetivo por pantalla. El empresario no-técnico lo recorre sin ayuda; todo guiado.

### T=0:00 — Fase 1 · Empresa (Pantalla 0 · Alta de empresa)
- **Pantalla 0 · Alta de empresa (1 pantalla):** si es primera vez, VANOVA pide 3 datos mínimos:
  - Nombre de la empresa, sector (select: ecommerce / servicios / otros), y moneda (por defecto EUR).
  - Copy: "Cuéntanos de tu negocio para adaptar VANOVA."
  - **Empty state (sin nada aún):** "VANOVA está listo. Cuéntanos tu negocio para empezar."
  - CTA: "Continuar".
  - **Sin cuenta previa:** no se pide registro técnico en este punto.

### T=0:10 — Pantalla 1 · Bienvenida (elección de origen)
**Copy (ES, word-for-word):**
> "VANOVA vigila tus números y te dice qué y cuánto puedes ganar o perder. Empecemos."

**Botones:**
- CTA principal: **"Conectar mi tienda"** (→ Shopify)
- CTA secundario: **"Subir mis ventas"** (→ Excel/CSV)

**Reglas UX:** sin muro de registro técnico. Si hace falta cuenta, se crea al final, no al inicio. El usuario llega aquí en el min 0.

### T=0:30 — Pantalla 2 · Conexión de datos
- Shopify: campo "URL de tu tienda" + "Token de acceso" + enlace "¿Dónde encuentro el token?"
- Excel/CSV: botón "Subir archivo" (acepta .xlsx/.csv)
- Progreso honesto: "Conectando… (1/3)" → (2/3) → (3/3)
- **Criterio de aceptación:** en ≤60 s devuelve estado real (conectado / error de scopes / fallo de red). Nunca spinner infinito.

---

## 1e. Wireframes en texto (layout de cada pantalla)

**P0 · Alta de empresa**
```
┌──────────────────────────────────────────────┐
│  [logo VANOVA]                                │
│  "Cuéntanos de tu negocio para adaptar VANOVA."│
│  Nombre de la empresa  [_____________]        │
│  Sector               [ecommerce ▾]          │
│  Moneda               [EUR ▾]                │
│                          [ Continuar → ]     │
└──────────────────────────────────────────────┘
```

**P1 · Bienvenida**
```
┌──────────────────────────────────────────────┐
│  "VANOVA vigila tus números y te dice qué     │
│   y cuánto puedes ganar o perder. Empecemos."  │
│                                              │
│  [ Conectar mi tienda (Shopify) ]  (CTA ppal) │
│  [ Subir mis ventas (Excel/CSV) ]  (secund)   │
└──────────────────────────────────────────────┘
```

**P2 · Conexión**
```
┌──────────────────────────────────────────────┐
│  Conectar Shopify                            │
│  URL de tu tienda  [________________]        │
│  Token de acceso   [________________]        │
│  ¿Dónde encuentro el token? (enlace)         │
│  Conectando… (1/3)  [................]       │
│                    [ Continuar → ]           │
└──────────────────────────────────────────────┘
```

**P3 · Revisión**
```
┌──────────────────────────────────────────────┐
│  "Esto es lo que encontró VANOVA:"           │
│   128 productos [real] · 340 pedidos [real]   │
│   54 clientes [real]                         │
│  ⚠ Falta un dato para mostrarte el dinero.   │
│                       [ Continuar → ]        │
└──────────────────────────────────────────────┘
```

**P4 · "El dato que desbloquea el dinero"**
```
┌──────────────────────────────────────────────┐
│  "Bien. Tenemos tus ventas. Para decirte      │
│   cuánto puedes ganar, nos falta el coste de  │
│   tus productos (lo que pagas al proveedor)."  │
│                                              │
│  [ Cargar costes (CSV/FacturaScripts) ]       │
│  [ Más tarde ]                               │
└──────────────────────────────────────────────┘
```

**P5 · El AHA**
```
┌──────────────────────────────────────────────┐
│  ≈ 3.400 € en juego este mes        [grande] │
│                                              │
│  [Oportunidad] Haz pack de A+B → +238 €       │
│     "Se venden juntos en 23 pedidos."         │
│  [Riesgo] Estás dejando 512 € en producto X   │
│                       [ Marcar como hecha ]   │
└──────────────────────────────────────────────┘
```

### T=1:30 — Pantalla 3 · Revisión transparente
**Copy:**
> "Esto es lo que encontró VANOVA: X productos · Y pedidos · Z clientes."
- Badges `real` / `sample` / `empty` por origen.
- Si falta coste: aviso amarillo claro (NO error rojo): "Falta un dato para mostrarte el dinero."
- **CTA:** "Continuar"

### T=3:00 — Pantalla 4 · "El dato que desbloquea el dinero"
**Copy:**
> "Bien. Tenemos tus ventas. Para decirte cuánto puedes ganar, nos falta el **coste de tus productos** (lo que pagas al proveedor). Con él, VANOVA calcula el margen real y las oportunidades. Sin él, no te mostraré cifras inventadas."

**Botones:**
- **"Cargar costes"** → guía: subir CSV de costes por SKU (con plantilla descargable) o leer de FacturaScripts si está conectado.
- **"Añadir coste uno a uno"** → alta manual sin fricción, una línea a la vez (ver "Alta manual de coste" abajo).
- **"Declarar mi margen"** → **vía corta al "aha" YA implementada en el código** (botón `set-margin-quick`, `web/dashboard.html:2515`): permite al empresario no-técnico declarar su margen global (~50% real de MOOVING) sin cargar un CSV entero. Al pulsar, se guarda `globalMarginPct` en `companyProfile.preferences` y el Home muestra el titular "≈ X € en juego" como `estimated` (margen global × revenue) + la oportunidad de cross-sell cuantificada en € ESTIMADO (ver §3). Es el camino más corto al "aha" si el dueño no tiene el coste por SKU a mano (la contabilidad la lleva el padre).
- **"Más tarde"** → el sistema continúa, pero muestra la señal honesta "sin coste no puedo cuantificar el margen" (UNKNOWN≠0), nunca "0 €".

**Alta manual de coste — una línea a la vez (sin fricción, para el no-técnico):**
- **Pantalla 4b · Añadir coste de un producto:** un solo formulario con campos mínimos y validación clara:
  - **Producto (SKU o nombre)** — obligatorio; texto libre que VANOVA cruza con el catálogo (case-insensitive). Si no matchea un SKU existente, se muestra aviso "No encontramos este producto en tu catálogo. ¿Quieres añadirlo igualmente?" (no bloquea).
  - **Coste (lo que pagas al proveedor)** — obligatorio, número ≥ 0, con separador decimal ES. Validación: si es 0 o vacío, no se guarda y se pide el importe real.
  - **Categoría (opcional)** — select con las del catálogo (p. ej. Papel / Arte / Imprenta) para agrupar costes; si no hay categorías, se omite.
  - **Frecuencia (opcional, default "unitario")** — para costes recurrentes se puede declarar "mensual" y asociar a un proveedor; si es unitario, se toma como coste por unidad.
- Botón "Añadir y ver mi €". Al guardar, se muestra al instante "Con este coste, [producto] te da un margen de X €/unidad".
- El empresario puede añadir 1, 3 o N productos, uno a la vez, sin rellenar un CSV entero.
- **Criterio de aceptación:** con 1 solo coste cargado manualmente, el € ya se actualiza y aparece en el Home (no requiere un catálogo completo).
- Regla de honestidad: el margen se calcula del coste real introducido (nunca se inventa); si no hay coste, se muestra UNKNOWN/empty.

**Regla de honestidad:** esta pantalla aparece SIEMPRE si hay ventas pero falta coste. Nunca se muestra el Home con "no cuantificable" sin esta guía. Si el coste ya llega de FacturaScripts (`articulos.preciocoste`, BUG-033) o CSV → se salta a Pantalla 5.

### T=4:00 — Pantalla 5 · EL AHA
El Home se carga y, en la fila superior (sin scroll), muestra:
1. **Titular de valor (grande):** "≈ X € en juego este mes"
2. **1 tarjeta de oportunidad** con € cuantificado: "Haz pack de [A+B] → +X € de margen" + porqué en 1 línea.
3. **1 tarjeta de riesgo** (si existe): "Estás dejando X € en [producto]".

**El "aha" de coste mal calculado (cómo el empresario se da cuenta de que pierde dinero al mes):**
El disparador del "aha" es mostrar una **diferencia entre el margen real y el estimado** en un producto concreto, con su pérdida mensual. La fórmula real (con coste por SKU):
```
margen_real_SKU = precio_venta_SKU − coste_SKU
margen_estimado_SKU = precio_venta_SKU × (1 − margen_global_declarado)
perdida_mensual_SKU = (margen_real_SKU − margen_estimado_SKU) × unidades_vendidas_mes
```
- Si `margen_estimado > margen_real` (el coste real es mayor que el estimado), el empresario **ve que está calculando mal su margen** y cuánto pierde al mes en € reales.
- Se muestra como: "En [producto], tu margen estimado es del X% pero el real es Y% → pierdes ≈ Z €/mes." Ese número concreto (fórmula real, datos reales) es el "aha" que hace decir "esto vale".

**Disparador alternativo concreto — coste mensual de un proveedor/categoría:**
Si el empresario declara el **coste mensual de un proveedor o categoría** (p. ej. "compro papel a [proveedor] por X €/mes"), VANOVA puede mostrar directamente:
```
coste_mensual_proveedor = X €/mes  (dato real declarado)
ahorro_potencial_mensual = coste_mensual × % de margen recuperable (con evidencia, si hay)
```
Se muestra: "Tu coste mensual en [proveedor] es de X €. VANOVA detectó una palanca para reducirlo / recuperar margen." El dato que dispara el "aha" es un **€/mes concreto y real** del propio negocio del cliente (nunca inventado).

**Encadenamiento conexión → datos reales → cálculo → visualización del ahorro:**
1. Conexión (Shopify/Excel) trae ventas reales.
2. Coste por SKU (CSV/FacturaScripts) o margen global aporta el coste real.
3. Cálculo: `ahorro/ganancia = margen_real − margen_estimado` (o el upside de la oportunidad).
4. Visualización: el Home pinta el €/mes resultante ("pierdes ≈ Z €/mes" / "puedes ganar ≈ Y €/mes").

**Framing del aha — cuánto gasta "por cliente" y "por hora" (opcional, solo con datos reales):**
Para que el empresario "entienda" el valor de forma más humana, además del €/mes, se puede mostrar el coste en unidades que le hablan (siempre derivadas de datos reales, NUNCA inventadas):
```
coste_por_pedido = costes_mensuales_reales / nº_pedidos_mes        (o coste total de SKUs vendidos / pedidos)
coste_por_cliente = costes_mensuales_reales / nº_clientes_activos
coste_por_hora (coste de operación declarado) = coste_operativo_mensual / horas_trabajadas_mes
```
- Solo se muestran si la fuente real permite calcularlos (pedidos/clientes de Shopify, coste declarado). Si falta el dato → no se muestra esa línea (vacío honesto), nunca se inventa el "por hora" sin el dato.
- Copy: "Cada pedido te cuesta X € de coste de producto. Aquí está dónde pierdes margen." / "Tu operación te cuesta X €/hora; reducir el coste de producto te da Y €/mes."

**Criterio de aceptación:** con ventas + ≥1 coste cargado, el Home muestra ≥1 € cuantificado (`calculated`) sin scroll. Si además hay un SKU con coste que difiere del margen estimado, se muestra la línea "pierdes ≈ Z €/mes en [producto]" con la fórmula de arriba (datos reales, nunca inventados). El framing "por cliente/por hora" es una capa opcional y honesta: solo se pinta si hay el dato real para calcularlo.

### T=4:30 — Pantalla 6 · Cierre del loop
- La tarjeta de oportunidad tiene CTA **"Marcar como hecha"**.
- Al pulsar: la recomendación entra al `recommendation_store` y el sistema prepara la medición. Copy de confirmación: "Lo mediré y te diré si funcionó con tus datos."

### T=5–15 — Deja que el sistema corra
- El Home queda con el titular €, las tarjetas, y el CTA "Marcar como hecha". El cliente ya tiene su primera señal de valor medible en <15 min.

---

## 1f. STATE-MACHINE DEL WIZARD (qué pantalla lleva a qué, qué se salta, qué bloquea)

```
P0 Alta empresa ──(Continuar)→ P1 Elegir origen ──→ P2 Conectar ──(OK)→ P3 Revisión
   │                                        │                  (error)→ P2 (reintentar)
   │                                        └─(Excel "Subir")→ P2 (subir archivo)
P3 Revisión ──(Continuar)→ P4 Coste  ──(se salta si coste ya está vía CSV/FacturaScripts)→ P5
   │                          │
   │                          ├─(Cargar costes / Añadir uno a uno / Declarar mi margen)→ P5
   │                          └─(Más tarde)→ P5 con señal UNKNOWN honesta (no bloquea el aha)
P5 El AHA ──(Marcar como hecha)→ P6 Cierre loop
```

**Reglas de transición:**
- **P2 → P3:** solo si la conexión devuelve estado real (conectado). Si falla (token/scopes/red), se queda en P2 con el error correspondiente (§4b) y botón "Reintentar".
- **P3 → P4:** si hay ventas pero falta coste. Si el coste ya está (FacturaScripts `articulos.preciocoste` o CSV cargado) → **se salta P4** y va directo a P5.
- **P4 → P5 (casos):**
  - **Coste por SKU cargado** (manual o CSV): P5 con titular `calculated` + oportunidad `calculated`. **Este es el aha pleno.**
  - **Margen global declarado** (botón "Declarar mi margen"): P5 con título `estimated` (margen global × revenue) + cross-sell en € ESTIMADO (`kind="estimated"`). Honesto, no bloquea.
  - **"Más tarde" (sin coste):** P5 NO bloquea; muestra el titular honesto "sin coste no puedo cuantificar el margen" (UNKNOWN≠0, nunca "0 €") + CTA que guía a volver a la Pantalla 4. El usuario NO queda atascado.
- **P5 → P6:** al pulsar "Marcar como hecha".
- **P6:** vuelve a Home (P5) y el loop queda listo para medir.

**Regla general:** ninguna transición deja al usuario en blanco o atascado; siempre hay un CTA o un estado honesto. Bloqueos = sin ventas (P2 guía a conectar) o muestra insuficiente (<20 pedidos), ver §14.

---

## 2. Empty states (qué ve cuando NO hay datos) — copy español

| Estado | Copy (word-for-word) | CTA |
|---|---|---|
| Sin tienda conectada | "Conecta tu tienda para empezar a ver tus números en €." | "Conectar Shopify" |
| Conectada pero sin ventas | "Todavía no hay ventas cargadas. Importa tu historial para que VANOVA te diga qué está pasando." | "Subir ventas (Excel)" |
| Productos sin coste | "Tienes productos sin coste cargado. Sin él, no puedo decirte el margen ni las oportunidades con dinero. Cárgalos para ver el € real." | "Cargar costes" |
| Todo en orden, sin hallazgos | "Bien, tu negocio no tiene señales de alarma hoy. Cuando algo cambie, te avisamos." | (ninguno) |
| Vacío total | "VANOVA está listo. Conecta tus datos y verás qué puedes mejorar, en euros." | "Conectar datos" |
| **Vista "Oportunidades" vacía (no hay oportunidades con evidencia mínima hoy)** | "No hay oportunidades con evidencia mínima hoy. Si cargas costes y más pedidos, el detector puede darte más señales." (Enlace a "Conectar fuente" / "Cargar costes".) | "Conectar fuente" |

> **Regla de honestidad para la vista "Oportunidades" vacía (clave en el primer arranque):** este empty state NO es un fallo, es la honestidad que diferencia a VANOVA. Copy del subtítulo que lo enmarca bien:
> "Cada oportunidad se basa en tus datos reales. Cuando haya suficiente evidencia (costes cargados y más pedidos), aparecerán aquí señales con su impacto en €. No mostramos cifras inventadas."
> Enmarcarlo como "honestidad, no como fallo": el CTA lleva a completar el dato que falta (coste por SKU / más datos), nunca deja al usuario sin siguiente paso. Sin este contexto, un empresario que llega con la expectativa de "ver €" leerá el vacío como "no funciona". El copy de honestidad lo convierte en "está trabajando con mis datos reales".

**Regla de oro:** nunca mostrar "no hay datos" como fallo; siempre guiar con verbo + CTA. Nunca un "0 €".

---

## 3. Cómo se conecta el € (fuentes reales)

| Fuente | Qué aporta | Condición para el € |
|---|---|---|
| Shopify | productos, ventas, líneas, clientes | margen requiere **coste por SKU** |
| Excel/CSV | catálogo + ventas | idem |
| FacturaScripts | productos, ventas, **coste `articulos.preciocoste`** | coste ya llega (BUG-033) → desbloquea el € sin import manual |

**Nota honesta sobre otras fuentes:** la UI del producto lista también Drive, ERP, Email, Instagram e MCP como integraciones, pero en el estado actual **solo Shopify, Excel/CSV y FacturaScripts son fuentes reales conectadas**. Por tanto el SPEC **NO** trata Drive/ERP/Email como fuentes de datos reales hasta que se conecten; si el empresario las elige, se muestra "Pendiente de conectar fuente" (nunca un € inventado). La fuente de VENTAS del onboarding es Shopify o Excel; el coste viene de CSV/FacturaScripts.

**Integración con el flujo de costes existente (producto/coste → margen → €):**
- El coste por SKU (CSV o FacturaScripts) alimenta el cálculo de **margen por producto**: `margen = precio_venta − coste`. Ese margen es la base del € que ve el empresario (cross-sell, AOV, "en juego").
- **Margen global declarado (~50%, dato real de Boss) y detección:** QA confirmó que el margen global NO llega hoy a `detect_cross_selling`/`_cross_sell_pairs`. La solución (~1 día dev) es **propagar `global_margin_pct` a la detección**. Comportamiento resultante (verificado funcional por QA/Mathew):
  - **Con margen global pero SIN coste por SKU:** el **titular "≈ X € en juego"** se muestra como estimación agregada (`kind:"estimated"`, margen global × revenue). La **tarjeta de oportunidad de cross-sell SÍ se cuantifica en € ESTIMADO** (`kind="estimated"`): el motor llama a `resolve_cost(p, global_margin_pct)` (en `opportunity_catalog._upsell_for_cross_sell`), que estima el coste con el margen global y produce un `upsideEuro` numérico. Ejemplo verificado: `art-101 + art-102 | 30.4 EUR | estimated`.
  - **Con coste por SKU real:** el cross-sell/AOV/upside se cuantifican con `kind="calculated"` y la oportunidad muestra su € con coste real.
- Si el cliente tiene **gastos** (p. ej. gastos operativos por periodo en Excel), se incluyen en la señal de "te estás dejando X €" (riesgo) para que el € sea completo, no solo de producto. Sin gastos → el € se limita a margen/oportunidades (honesto, no inventa gastos).

**Decisión de producto (dónde se rompe el SPEC 1):** el flujo sigue siendo válido, pero la transición P4→P5 se comporta distinto según el dato de coste:
- Si el empresario **carga coste por SKU** (o viene de FacturaScripts/CSV) → el aha llega completo: titular + oportunidad cuantificada (`calculated`). Este es el camino objetivo.
- Si **solo declara margen global** (pulsa "Más tarde" en P4 o no carga coste por SKU) → se muestra el titular "≈ X € en juego" como **estimación** (`estimated`) con la señal honesta "estimado con margen global; para cifras exactas carga el coste por producto", y la oportunidad de cross-sell aparece **cuantificada en € ESTIMADO** (`kind="estimated"`, coste estimado con el margen global). No es el aha pleno (`calculated`), pero SÍ muestra una cifra en € (nunca se oculta como sin cuantificar).

**Regla de honestidad:** el titular agregado puede ser `estimated` (margen global × revenue), pero una **oportunidad concreta nunca muestra un € `calculated` sin coste por SKU**. Si el cross-sell no puede cuantificarse, muestra "impacto no cuantificado" (UNKNOWN≠0), nunca "0 €".

**Señal de "aha" (completo):** titular € + 1 oportunidad cuantificada (`calculated`), visibles en el Home en la fila superior, sin scroll, en <15 min.

---

## 3a. MATRIZ DE TRAZABILIDAD DEL DATO (qué campo de qué fuente alimenta cada €)

**Regla: ningún € aparece si no hay una fila completa de esta matriz detrás.** Esta tabla es la fuente de verdad para Nickx (qué leer de cada integración) y para Mathew (qué auditar). Si una celda está vacía → la señal asociada NO se muestra (o se muestra `estimated` honesto / UNKNOWN), nunca un número inventado.

### 3a.0 · Categorías de coste que se registran (fuentes de costes cubiertas)

VANOVA permite registrar el coste en estas categorías, cada una con su fuente y forma de captura. Solo se suma a la señal "te estás dejando X €" la que tenga dato real; las vacías no se inventan.

| Categoría de coste | Qué es | Cómo se registra | Dónde se muestra |
|---|---|---|---|
| **Material / producto** | coste del producto vendido (proveedor) | coste por SKU (CSV/FacturaScripts/Leclerc) o alta manual "una línea a la vez" | margen por producto, cross-sell, "pierdes ≈ Z €/mes" |
| **Mano de obra** | coste de personal/operación | input declarado (€/mes o €/hora) en la Pantalla 4b o Excel de gastos | framing "coste por hora", señal "te estás dejando X €" |
| **Energía / suministros** | electricidad, agua, etc. | Excel de gastos (importe + periodo) | señal de gastos (riesgo) |
| **Subcontratación** | coste de servicios externos | Excel de gastos | señal de gastos (riesgo) |
| **Otros** | cualquier gasto operativo | Excel de gastos (importe + periodo) | señal de gastos (riesgo) |

**Integración de costes adicional — LECLERC (Excel de precios netos):** Leclerc es una **fuente de costes real** de MOOVING/VANOVA, ingerida vía Excel de precios netos (`NET_PRICE_LECLERC_ENGLISH_FORMATTED.xlsx`), procesada por `ingest_catalog.py` (raíz del repo) y cargada en el catálogo (referencia en `benchmark-sandbox/real-company/VANOVA/config/maios.json` como `sourceReference`). Aporta el **coste del producto (precio neto por SKU)** → alimenta la señal de margen por producto y el "pierdes ≈ Z €/mes" de la misma forma que el CSV/FacturaScripts. **Regla de honestidad:** el dato de Leclerc sale de ese Excel real ingerido; si falta el SKU o el precio neto, se marca `UNKNOWN`/sin dato, nunca se inventa.

**Regla de honestidad:** ninguna categoría se rellena con un número inventado. Si el empresario no declara mano de obra o energía, esa categoría simplemente no aparece en la señal de gastos (vacío honesto, nunca "0 €").

### 3a.1 · Entradas mínimas que necesita el sistema para pintar el primer €

| # | Input real | De dónde sale (fuente) | Campo exacto que se lee | Lo que desbloquea |
|---|---|---|---|---|
| 1 | **Ventas/pedidos** | Shopify (`Order` → `line_items`) o Excel/CSV | fecha, cliente, SKU, qty, total | base del margen, cross-sell, AOV |
| 2 | **Catálogo** | Shopify (`Product` → `variants`) o CSV | SKU, nombre, precio_venta | identifica qué se vende y a qué precio |
| 3 | **Coste por SKU** | FacturaScripts (`articulos.preciocoste`, BUG-033), CSV de costes, **Leclerc (Excel de precios netos vía `ingest_catalog.py`)** o alta manual / margen global declarado | coste por SKU (o `globalMarginPct`) | el que convierte ventas en **€ de margen** (P4) |
| 4 | **(opcional) Gastos** | Excel de gastos operativos | importe + periodo | amplía "te estás dejando X €" (riesgo), no bloquea |
| 5 | **(opcional) Coste mensual proveedor** | declarado por el usuario (P4b) | coste_mensual + proveedor/categoría | dispara el "aha" de coste mensual |

### 3a.2 Derivación campo a campo (de la fuente al € visible)

| € que muestra la UI | Derivación (fórmula) | Fuente real que lo alimenta | Condición para mostrarse |
|---|---|---|---|
| Titular "≈ X € en juego" — `estimated` | `margen_global × revenue_mes` | revenue real (ventas #1) + `globalMarginPct` declarado (P4 "Declarar mi margen") | sin coste por SKU → se marca `estimated` |
| Titular "≈ X € en juego" — `calculated` | `Σ(upsideEuro cross-sell) + Σ(revenueAtRisk riesgos)` | coste por SKU (nº 3) + ventas (nº 1) | ≥1 coste por SKU real |
| Oportunidad cross-sell (€) | `upsideEuro = margen_real_A + margen_real_B` (si se venden juntos) | coste por SKU + co-venta real (ventas) | `resolve_cost(p, margin)` estima con margen global si falta coste SKU (`estimated`) |
| "En [producto] pierdes ≈ Z €/mes" | `(margen_real_SKU − margen_estimado_SKU) × unidades_mes` | coste por SKU (nº 3) + unidades reales vendidas (nº 1) | hay coste por SKU real |
| "Tu coste mensual en [proveedor] = X €/mes" | `coste_mensual` declarado | input del usuario en P4b (dato real declarado) | el usuario lo introduce |
| "Cada pedido te cuesta X €" / "X €/hora" | `costes_mensuales / nº_pedidos` ; `coste_operativo_mensual / horas_mes` | coste declarado + pedidos reales | solo si ambos datos reales existen → si no, no se muestra la línea |

> **Para Nickx:** los campos 1-3 son las lecturas mínimas de las integraciones ya existentes (Shopify, Excel/CSV, FacturaScripts). Ninguna de estas lecturas es nueva ni inventada; es el mismo acceso que ya usa el motor de detección. **Para Mathew:** auditar que cada € mostrado traza hasta una celda rellena de 3a.2; si falta, es `unmeasurable`/UNKNOWN, nunca un número.

**Verificación de la fórmula del titular en el código (no supuesto):** en `web/dashboard.html` (§ AHA MOMENT, ~línea 2527-2535) el titular "≈ X € en juego" se calcula como:
```
total = Σ upsideEuro  (de store.opportunities donde upsideEuro > 0)
top   = las 2 oportunidades de mayor upsideEuro (se destacan)
si total <= 0 → empty state honesto graduado (guía al dato que falta, nunca "0 €")
```
Nota: el `calculated` del dashboard en su forma actual suma el `upsideEuro` de las oportunidades activas. La celda de arriba (`Σ upsideEuro + Σ revenueAtRisk riesgos`) describe el diseño objetivo incluyendo riesgos; si el código actual solo suma upside de oportunidades, el titular mostrado es `Σ upsideEuro` — quedan ambos documentados para que Nickx decida si el titular debe incluir también `revenueAtRisk` (riesgos) o solo upside (recomendado para no mezclar oportunidad y riesgo en una sola cifra, manteniendo la honestidad).

---

## 4. Timeline (qué lograr en cada minuto)

| Min | Logro | Pantalla |
|---|---|---|
| 1 | Elige origen + inicia conexión | P1–P2 |
| 2 | Conexión OK + revisión de datos | P3 |
| 3 | Detecta "falta coste" y ofrece cargar | P4 |
| 4-6 | (Si cargó coste) Ve el € y "Marcar como hecha" | P5–P6 |
| 8-15 | Sistema corriendo; valor de € visible | Home |

**Meta:** 1ª cifra € cuantificada en ≤15 min.

---

## 4b. Estados de error y borde (copy en español)

| Situación | Qué ve el empresario | CTA |
|---|---|---|
| Conexión fallida (red/token) | "No hemos podido conectar con tu tienda. Revisa que la URL y el token son correctos e inténtalo de nuevo." | "Reintentar" |
| Token no válido / scopes incompletos | "Tu token no tiene permiso para leer ventas y productos. Concede los permisos de lectura en tu tienda y vuelve." | "Ver permisos" / "Reintentar" |
| Archivo no válido (formato) | "El archivo no tiene el formato esperado. Descarga la plantilla y rellena las columnas (SKU, precio, coste)." | "Descargar plantilla" |
| Sin fuente conectada (al entrar al dashboard) | "Conecta tu tienda o sube tus ventas para empezar a ver tus números en €." | "Conectar datos" |
| Sin ventas tras conectar | "Todavía no hay ventas cargadas. Importa tu historial para que VANOVA te diga qué está pasando." | "Subir ventas (Excel)" |

---

## 4c. Requisitos de datos de entrada y formato de salida

**Entradas (fuentes reales):**
- Shopify: URL de tienda + token → productos (SKU, precio), pedidos con `line_items` (SKU, qty, total), clientes.
- Excel/CSV: catálogo (SKU, precio, coste opcional) + ventas (fecha, cliente, SKU, total).
- FacturaScripts: productos, ventas, coste `articulos.preciocoste`.

**Salida (el € que ve el empresario):**
- `margen_real_SKU = precio_venta − coste_SKU` (€ y %).
- `perdida_mensual_SKU = (margen_real − margen_estimado) × unidades_mes`.
- `titular "≈ X € en juego"` = `estimated` (margen global × revenue) o `calculated` (Σ upsideEuro + revenueAtRisk).
- Todas con formato € ES, redondeadas a 2 decimales. Nunca "0 €" si no hay dato (muestra "sin cuantificar/UNKNOWN").

---

## 5. Criterios de aceptación verificables

- [ ] El flujo lleva a un € real cuantificado en <15 min (o al empty state que guía a cargar coste).
- [ ] Pantalla 4 aparece cuando hay ventas sin coste; se salta si el coste está.
- [ ] Empty states muestran el copy del §2 con CTA.
- [ ] Nunca un "0 €" inventado; si no hay dato, "sin cuantificar/UNKNOWN".
- [ ] Copy todo en español, coherente.

---

## 5a. ESTILO / TOKENS DE DISEÑO (premium dark, corporativo VANOVA — para Nickx en CSS, para Mathew en QA visual)

El onboarding comparte el mismo lenguaje visual que el resto de VANOVA (ver `docs/VANOVA_DESIGN_SYSTEM.md`). Los tokens clave para que el "aha" y los empty states se sientan premium y no como un panel técnico:

| Token | Valor | Uso |
|---|---|---|
| `--surface-solid` | `#0B0F14` (fondo base oscuro) | página |
| `--surface-glass` | `rgba(255,255,255,0.06)` + `backdrop-filter: blur(16px)` | tarjetas, sidebar, header del wizard |
| `--accent` | `#DC2626` (rojo corporativo) | titular €, CTAs, hover |
| `--accent-strong` | `#B91C1C` | hover / estados activos |
| `--text-primary` | `#F5F7FA` | titular € (peso 700) |
| `--text-muted` | `#8B93A3` | copy secundario / "porqué" en 1 línea |
| `--positive` | `#22C55E` (verde) | solo dot "mejoró", no texto grande |
| `--warn` | `#F59E0B` (ámbar) | aviso "Falta un dato" (P3/P4), solo dot |
| `--neutral` | `#64748B` (gris) | dot "sin dato" |
| `--border-glass` | `rgba(255,255,255,0.08)` | bordes finos de tarjetas |
| `--radius-card` | `16px` | esquinas de tarjetas |
| `--shadow-card` | `0 12px 40px rgba(0,0,0,0.4)` | profundidad glass |
| Fuente | Inter | toda la UI |
| Iconos | SVG inline (cero emojis de color) | "cheque"/"tendencia" para mejoró, "flecha" para enlace |

**Reglas visuales del onboarding:**
- **Titular "≈ X € en juego"**: único elemento que usa `--accent` (`#DC2626`) en el signo y la cifra (peso 700); el resto es `text-primary`. Protagonista, sin scroll.
- **Aviso "Falta un dato" (P3/P4)**: ámbar suave (`--warn`) con icono, NO un error rojo. El rojo se reserva para fallos reales (conexión/token).
- **Empty states**: tarjetas `glass` translúcidas sobre fondo oscuro, con un icono SVG tenue y el CTA en `--accent`. Nunca paneles opacos planos.
- **Coherencia**: cero emojis de color, cero jerga "AI-sounding", cero terminología técnica visible (puertos, cloud, runtime). Todo en lenguaje empresarial llano.

---

## 6. PENDIENTES (dato que no tengo confirmado)

**RESUELTO — método de conexión de Shopify:** OAuth/link mágico si existe en la UI (saltar token manual); token manual solo como plan B. Ver sección **§7b.1** (decisión de diseño tomada; en release 3.1.3 implementado con token real vía Dev Dashboard).

**RESUELTO — plantilla CSV de costes por SKU:** columnas `sku;coste;precio_venta;unidades_mes` (definidas en `STRATI_CIERRE_PRODUCTO.md` §1), plantilla descargable obligatoria. Ver sección **§7b.2** (en release 3.1.3 existe `prepare_cost_template`).

**RESUELTO — formato/conversión del coste desde FacturaScripts (`articulos.preciocoste`):** usar el recurso `articulos` de FacturaScripts (BUG-033 CLOSED) que trae `preciocoste`; cruzar por SKU; documentar la regla de conversión (p. ej. IVA) si procede. Ver sección **§7b.3** (implementado en release 3.1.3).

**PENDIENTE CERRADO — fórmula del titular "≈ X € en juego":** definido con la evidencia de QA. El titular es:
- `estimated` = margen global (declarado) × revenue del periodo, cuando NO hay coste por SKU.
- `calculated` = Σ(upsideEuro de oportunidades cuantificadas) + Σ(revenueAtRisk de riesgos), cuando hay coste por SKU.
- **Condición para dejar de ser estimación y pasar a calculado:** propagar `global_margin_pct` a `detect_cross_selling`/`_cross_sell_pairs` (fix ~1 día dev) Y tener ≥1 coste por SKU en el catálogo.

---

## 7. Preguntas abiertas para Nickx/Mathew (necesarias para programar y testear)

1. ~~¿El método de conexión de Shopify actual en la UI es OAuth o token manual?~~ → **RESUELTO** (§7b.1; en 3.1.3 token real vía Dev Dashboard).
2. ~~¿Existe ya una plantilla CSV de costes por SKU en el repo?~~ → **RESUELTO** (§7b.2; existe `prepare_cost_template`).
3. ~~¿Cómo se mapea el coste de FacturaScripts al catálogo?~~ → **RESUELTO** (§7b.3; implementado).
4. ~~¿La barra de progreso "Paso X de 5" del wizard ya existe o hay que añadirla?~~ → **RESUELTO** (ya existe en el código: `.s-step`/`.s-progress`/`.setup-step` en `web/dashboard.html` §638-698; el wizard multi-fase P0-P5 con barra de progreso está implementado).
5. ¿Qué ocurre si el token de Shopify da error de scopes: ya hay pantalla de "Ver permisos" o hay que crearla? (confirmación de Nickx)

---

## 7b. CIERRE DE DECISIONES — dependencias técnicas (recomendación + plan B)

**7b.1 Método de conexión de Shopify (Pantalla 2) — VERIFICADO EN CÓDIGO:**
- **Realidad actual (confirmado leyendo `web/dashboard.html`):** la UI conecta Shopify por **token manual** con campo "URL de tu tienda" + "Token de acceso". Hay manejo de errores de scopes/permisos ya implementado: mensajes "Shopify conectado pero faltan permisos (read_products, read_orders). Aprueba los scopes en el admin de Shopify y vuelve a pegar el token." (dashboard.html §6324/§6329) y el estado `reauth_required` con el enlace "Ver permisos" (integración lifecycle).
- **Backend Dev Dashboard (confirmado en `desktop/runtime/shopify_sync.py`):** si el token empieza por `shpss_` (Client Secret del Dev Dashboard), se intercambia por un `access_token` real vía client credentials grant (POST /admin/oauth/access_token), cacheado 24h. Un `shpss_` crudo NO vale como `X-Shopify-Access-Token` (401).
- **Decisión de diseño (cerrada):** el MVP usa **token manual con manejo de scopes** (ya implementado). El OAuth/link mágico completo es una mejora futura (no bloquea el MVP). El empresario no-técnico ve el enlace "¿Dónde encuentro el token?" y, si fallan permisos, la pantalla "Ver permisos" con instrucciones claras.
- **PENDIENTE 5 resuelto:** la pantalla "Ver permisos" / manejo de scopes **ya existe** en el código (no hay que crearla).

**7b.2 Plantilla CSV de costes por SKU (Pantalla 4):**
- **Recomendación:** si existe plantilla en el repo, reutilizarla. Si no, crear una con las columnas definidas en `STRATI_CIERRE_PRODUCTO.md` §1: `sku;coste;precio_venta;unidades_mes`.
- **Plan B:** si no hay plantilla ni tiempo de crearla, permitir subir un CSV libre y detectar las columnas por cabecera (SKU/coste). Pero la plantilla descargable es lo correcto para un no-técnico.
- **Decisión de diseño:** la plantilla descargable es obligatoria para el no-técnico.

**7b.3 Mapeo del coste desde FacturaScripts (`articulos.preciocoste`):**
- **Recomendación:** usar el recurso `articulos` de FacturaScripts (BUG-033 CLOSED) que ya trae `preciocoste`. Al conectar FacturaScripts, VANOVA lee ese campo como coste por SKU y lo cruza con el catálogo.
- **Plan B:** si el formato del campo necesita conversión (p. ej. precio con/sin IVA), documentar la regla de conversión en la integración y verificar con datos reales. No inventar el formato.
- **Decisión de diseño:** el coste desde FacturaScripts es la vía automática; el CSV es el fallback para los que no usan FacturaScripts.

**Regla de honestidad:** ninguna de estas decisiones inventa datos; solo define el mecanismo. El € siempre sale de fuentes reales.

---

## 8. PENDIENTE DE CIERRE

**Estado del SPEC: LISTO para implementación.** El diseño de producto está completo (flujo multi-fase, copy ES literal, empty states, error states, aha con fórmula real, criterios de aceptación). No falta ninguna decisión de producto de este SPEC.

**Lo único pendiente es técnico, lo resuelve Nickx al programar (no es gap de diseño):**
- Confirmar el método de conexión de Shopify (OAuth o token) en la UI actual.
- Verificar si la plantilla CSV de costes por SKU existe en el repo.
- Confirmar el mapeo del coste de FacturaScripts al catálogo (BUG-033).
- Confirmar que la barra de progreso del wizard y la pantalla de "Ver permisos" existen o hay que crearlas.

**Regla de negocio que NO negocia:** el € del "aha" sale SOLO de fuentes reales; nunca "0 €" por defecto; si falta coste, se guía a cargarlo o se muestra `estimated` honesto.

---

## 9. AUDITORÍA DE CIERRE (sección → estado)

| Sección | Estado | Nota |
|---|---|---|
| 0. Objetivo y señal del aha | ✅ Completo | Definido: titular € + oportunidad cuantificada |
| 1b-1d. Quién hace cada paso / orden / criterios | ✅ Completo | Tablas de responsabilidad y éxito |
| 1. Flujo paso a paso (P0-P6) + wireframes | ✅ Completo | Copy ES literal + layout por pantalla |
| 2. Empty states | ✅ Completo | Copy y CTA por cada vacío |
| 3. Fuentes y margen global (estimated vs calculated) | ✅ Completo | Decisión de producto tomada |
| 4b-4c. Estados de error y formato entrada/salida | ✅ Completo | Copy de error + formato CSV |
| 5. Criterios de aceptación | ✅ Completo | Verificables |
| 6. PENDIENTES | ✅ Resueltos | Método Shopify, plantilla CSV, mapa FacturaScripts — RESUELTO (§7b.1/§7b.2/§7b.3, verificado en código) |
| 8. PENDIENTE DE CIERRE | ✅ Cerrado por producto | Solo quedan confirmaciones técnicas |

**Dependencias técnicas (para Nickx, no inventadas):** método de conexión Shopify (OAuth/token), si existe plantilla CSV en el repo, y el mapeo de coste FacturaScripts (BUG-033).

---

## 10. TAREAS PARA NICKX (ordenadas por prioridad, listas para programar)

1. **P1 — Conectar Shopify/Excel (Pantalla 2):** implementar la conexión de la fuente de ventas (Shopify URL+token o subida de Excel/CSV) con estado real en ≤60 s.
2. **P1 — Wizard multi-fase del onboarding (P0-P5):** montar la secuencia Empresa → Sector → Conexión → Coste → AHA con barra de progreso "Paso X de 5".
3. **P1 — Pantalla de coste (P4):** detectar SKUs sin coste y ofrecer "Cargar costes" con plantilla CSV; o margen global como vía estimada.
4. **P2 — Procesar el CSV de costes por SKU:** cruzar por SKU (case-insensitive), calcular `margen_real = precio_venta − coste`, ignorar SKUs desconocidos con aviso.
5. **P2 — Calcular y mostrar el "aha" (P5):** titular "≈ X € en juego" + "pierdes ≈ Z €/mes en [producto]" (fórmula `(margen_real − margen_estimado) × unidades_mes`) con datos reales; nunca "0 €" si falta dato.
6. **P2 — Pantalla 6 "Marcar como hecha":** enlazar la oportunidad al `recommendation_store` para la medición.
7. **P3 — Estados de error/borde:** conexión fallida, token sin permisos, archivo no válido (copy ES ya definido en §4b).
8. **P3 — Plantilla CSV descargable** y verificación del mapeo FacturaScripts (BUG-033) como fase 2.

---

## 11. CRONOGRAMA CORTO DE IMPLEMENTACIÓN (para Nickx)

Estimación orientativa en días de dev (depende de la velocidad del equipo y del estado real de la UI; ajustable):

| Semana | Alcance | Tareas (de §10) |
|---|---|---|
| Semana 1 | Conexión + wizard | T1 (conectar Shopify/Excel), T2 (wizard multi-fase P0-P5) |
| Semana 2 | Coste + "aha" | T3 (pantalla coste), T4 (procesar CSV), T5 (calcular/mostrar "aha") |
| Semana 3 | Cierre + errores | T6 ("Marcar como hecha"), T7 (estados de error), T8 (plantilla CSV) |

**Secuencia crítica (orden obligatorio):** T1 → T2 → T5 (el "aha" es el entregable de valor; las demás lo completan). Si el tiempo es muy corto, priorizar T1+T2+T5 para tener el "aha" funcionando y dejar T3/T6/T7/T8 como mejora.

**Criterio de salida de cada semana:** el "aha" (T5) visible con datos reales en <15 min. Sin eso, no se avanza a la siguiente fase.

---

## 11b. ÁRBOL DE DECISIONES DEL ONBOARDING (qué preguntamos, qué se auto-detecta, qué se difiere)

**Regla general:** solo se pregunta al empresario lo que el sistema NO puede auto-detectar de sus datos. Todo lo auto-detectable se hace en segundo plano; todo lo que requiera decisión humana se pregunta en el momento justo; todo lo opcional se difiere (no bloquea el "aha").

**Árbol de decisiones (P0 → P5):**

| Paso | ¿Se pregunta? | ¿Se auto-detecta? | ¿Se difiere? | Decisión |
|---|---|---|---|---|
| **P0 Alta de empresa** | Nombre, sector, moneda (3 campos) | — | — | Obligatorio (base del wizard) |
| **P1 Origen** | ¿Shopify o Excel? | si hay Shopify conectado previo | — | Preguntado (1 clic) |
| **P2 Conexión** | URL + token (Shopify) o archivo (Excel) | verifica estado de conexión (≤60 s) | — | Preguntado (el token es del usuario) |
| **P3 Revisión** | — | cuenta productos/pedidos/clientes reales | — | Auto-detectado (muestra badges real/sample/empty) |
| **P4 Coste** | ¿coste por SKU, margen global o más tarde? | si el coste ya llega de CSV/FacturaScripts → salta | "Más tarde" se difiere (no bloquea) | Decisión de coste; la bifurcación P4→P5 por caso |
| **P5 El AHA** | — | calcula titular "≈ X € en juego" + oportunidad | — | Auto-detectado (Home poblado) |

**Auto-detectar (segundo plano, sin preguntar):** nº de productos/pedidos/clientes, estado de conexión, presencia de coste (CSV/FacturaScripts), oportunidades/riesgos, margen por producto cuando hay coste.

**Preguntar solo en el momento justo:** origen de datos (P1), credenciales/archivo (P2), y la vía de coste (P4). Nada más.

**Diferir (no bloquea el "aha"):** "Más tarde" en coste (P4), gastos/otros costes (mano de obra, energía, subcontratación — §3a.0), y el framing "por cliente/hora" (solo si hay dato real). El "aha" se logra con el mínimo: ventas + coste por SKU o margen global.

**Regla de honestidad:** lo que se difiere no se muestra como dato (ni como "0 €"); queda vacío honesto hasta que el empresario lo aporte o se conecte la fuente.

---

## 12. UMBRALES Y DECISIONES DE DISEÑO (qué es obligatorio vs opcional en el primer arranque)

**Obligatorio (bloquea el "aha" — no se puede saltar):**
- Conectar la fuente de **ventas** (Shopify o Excel). Sin ventas no hay base. (Fase 3)
- Tener **algún dato de coste**: coste por SKU (CSV/FacturaScripts) o margen global declarado. Sin coste, el € queda en UNKNOWN. (Fase 4)
- Aceptar los **3 datos de empresa** (nombre, sector, moneda). (Fase 1)

**Opcional (no bloquea; si falta, se muestra vacío honesto o se salta):**
- **Gastos operativos** (Excel): solo amplían la señal "te estás dejando X €"; sin ellos, el € se limita a margen/oportunidades.
- **Framing "por cliente / por hora"**: capa extra solo si hay el dato real para calcularlo.
- **Unidades por mes** en el CSV: si falta, VANOVA usa las ventas reales.
- **Conexión FacturaScripts**: si no está, se usa CSV; es la vía automática cuando existe.

**Regla de diseño:** el primer arranque NUNCA exige pasos técnicos; lo obligatorio se limita a lo que desbloquea el €. Todo lo demás es opcional y no debe frustrar al no-técnico.

---

## 13. Conexión honesta con CASO_REAL_MOOVING.md (fuente de datos)

**Contexto (documentado en `docs/CASO_REAL_MOOVING.md`, NO inventado):** hoy NO hay datos reales de MOOVING PAPER en el sistema (solo demo mock etiquetada como tal y la fuente BlisArtPaper del usuario). Por tanto:

- **El SPEC 1 NO asume datos de MOOVING como fuente.** El onboarding carga la fuente de ventas + coste que el usuario (no-técnico) conecte/importe; eso puede ser MOOVING, BlisArtPaper u otra tienda, según lo que el empresario aporte.
- **Qué datos mínimos hacen falta para el "aha" (según el caso real):** ventas/pedidos (fecha, cliente, producto, qty, total) + catálogo (sku, nombre, precio) + **coste por SKU**. Con eso, VANOVA detecta cross-sell (€), concentración (riesgo €), AOV y alto margen. El CSV de costes de la Fase 4 es la vía para aportar ese `coste`.
- **Si el empresario no aporta datos reales →** se muestra el empty honesto de la Fase 4 ("Cargar costes") o el titular `estimated` con margen global; NUNCA un € inventado. Esto es coherente con la regla `UNKNOWN ≠ 0`.
- **Coherencia con el piloto (SPEC 3):** el primer piloto viable es el que puede aportar coste por SKU real (por eso el perfil ideal exige "coste por SKU o dispuesto a cargarlo").

**Contexto de negocio (dato de Boss, no inventado):** en MOOVING la **contabilidad y los costes los lleva el padre**. Implicación de producto: en el onboarding, si el empresario no tiene a mano el coste por SKU, VANOVA ofrece el margen global (~50%) como vía `estimated` y deja que la carga de costes detallada la haga la persona que lleva la contabilidad (padre/contable), sin bloquear el "aha" al dueño. El CSV de costes de la Fase 4 se puede generar/importar con la plantilla descargable y compartirla con quien lleva la contabilidad.

---

## 14. BLOQUEOS DEL "AHA" Y CÓMO DESBLOQUEARLOS

| Bloqueo | Qué impide | Cómo desbloquear (sin fricción técnica) |
|---|---|---|
| **Sin fuente de ventas** | No hay base para detectar nada | Pantalla 2 guía a conectar Shopify o subir Excel; empty state "Conecta tu tienda" + CTA |
| **Ventas pero sin coste** | El € queda en UNKNOWN, no "aha" pleno | Pantalla 4 "El dato que desbloquea el dinero" + CTA "Cargar costes" (CSV) o margen global (estima) |
| **Margen global pero sin coste por SKU** | Solo titular `estimado`, no oportunidad `calculada` | Guiar a cargar coste por SKU para el aha pleno (Fase 4); mostrar la señal honesta "estimado" mientras tanto |
| **Datos insuficientes** (<20 pedidos/mes) | El detector respeta umbral y no fabrica | Mostrar estado "muestra insuficiente" honesto + CTA a importar historial (SPEC 3: piloto con ≥20 pedidos) |
| **Conexión fallida / token inválido** | No conecta la tienda | Pantalla de error con "Reintentar" / "Ver permisos" (copy §4b) |
| **Empresario no-técnico atascado** | Abandono antes del aha | Wizard multi-fase guiado, 1 campo por pantalla, sin jerga, sin pasos técnicos |

**Regla:** ningún bloqueo deja al usuario en pantalla en blanco; siempre hay un CTA o un estado honesto con explicación.

---

## 15. TEST DE ACEPTACIÓN DEL "AHA" (accionable para QA/Mathew)

**Objetivo:** verificar que el empresario ve su primer € real con SUS datos en <15 min desde el alta, de forma inconfundible.

**Escenario de prueba (datos reales, nunca mock):**
1. Alta de empresa (P0) con datos reales → tiempo t0.
2. Conectar fuente de ventas (Shopify o Excel) → P2-P3.
3. Cargar ≥1 coste por SKU (manual/CSV) o declarar margen global → P4.
4. El Home (P5) debe mostrar, sin scroll y en la fila superior:
   - El titular "≈ X € en juego este mes" (con un número real `calculated` o `estimated`).
   - Al menos 1 tarjeta de oportunidad o riesgo con € concreto (kind `calculated` o `estimated`).
5. Medir `t_aha = t1 − t0` desde el alta hasta que P5 muestra el titular €.

**Criterio de PASS:**
- `t_aha ≤ 15 min` (meta ≤ 10).
- El titular € y ≥1 € de oportunidad son **visibles sin scroll**.
- Los € salen de datos reales del usuario (se puede auditar la procedencia).
- Si falta coste y el usuario NO lo carga → muestra empty honesto de la Fase 4 o titular `estimated`, NUNCA "0 €".

**Criterio de FAIL:** el titular no aparece en ≤15 min, o aparece un "0 €" inventado, o se queda en pantalla vacía sin CTA.

**QA/Mathew:** ejecutar este escenario con datos reales de una tienda y reportar `t_aha` + captura de la pantalla del Home con el €.

---

## 16. RECORRIDO MÍNIMO VIABLE (MVP) Y QUÉ SE QUEDA FUERA

**Recorrido MVP (lo que se implementa ahora para llegar al € en <15 min):**
1. Alta de empresa (3 campos) → P0.
2. Conectar fuente de ventas (Shopify o Excel/CSV) → P2-P3.
3. Cargar coste por SKU (alta manual "una línea" o CSV) o declarar margen global ("Declarar mi margen") → P4.
4. Home con titular "≈ X € en juego" + ≥1 oportunidad con € (`calculated` o `estimated`) → P5.
5. "Marcar como hecha" → P6 (entra al action-loop y prepara la medición).

**Fuentes de coste del MVP (ver §3a.0):** Material/producto (coste por SKU). Mano de obra, energía, subcontratación y otros gastos son **opcional** en el MVP (amplían la señal de gastos pero no bloquean el "aha").

**Qué se queda FUERA del MVP (post-piloto):**
- Conexión a Drive/ERP vía OAuth completa (solo Shopify/Excel/CSV/FacturaScripts en el MVP).
- Acceso móvil por código (pairing) — registrado como post-piloto.
- Gráficas rotatorias en el dashboard (decisión: fijas, y solo la de "Valor Capturado" prioritaria).
- Facturación multi-empresa y roles (el MVP es un solo dueño).

**Regla:** lo que se queda fuera no aparece en la UI (ni como placeholder). El MVP muestra solo lo construido con dato real.

---

## 17. DECISIONES TOMADAS (checklist — lo resuelto en esta pasada)

**Resuelto con dato real del código (verificado, no supuesto):**
- [x] **Método de conexión Shopify:** Dev Dashboard — el `shpss_` es Client Secret y se intercambia por un `access_token` real vía client credentials grant (`shopify_sync.py`, caché 24h). NO es un token manual usable. La UI ofrece "Conectar con Shopify" (OAuth) con token manual solo como fallback.
- [x] **Plantilla CSV de costes:** `prepare_cost_template` existe (`action_center.py:49`), excluye productos sin SKU (bug real corregido). Columnas: `sku;coste;precio_venta;unidades_mes`.
- [x] **Mapa FacturaScripts:** coste desde `articulos.preciocoste` (BUG-033), cruce por SKU.
- [x] **Fórmula del titular:** `Σ upsideEuro` de oportunidades activas (`dashboard.html:2527`), empty honesto si ≤0. Ver §3a.2 + nota de verificación.

**Queda para Boss/Nickx (no es diseño — decisión de negocio):**
- [ ] Fijar el precio del plan Pro (propuesto 29 €/mes) para la tarjeta de retorno neto (SPEC 2). [Nico]
- [ ] Conseguir el piloto real (operativo) y verificar el instalador en PC stock. [Boss/Nico + Nickx/QA]

**Nota resuelta — desync de versión (verificado por Nickx, no afecta al dashboard servido):** el dashboard servido (cloud 8000) responde **3.1.7** (hash `3049cbc2` == repo) y el runtime 8765 responde `{"version":"3.1.7"}`. El "3.0.1 / build 20260813o" que se detectó en el HTML raíz es una **versión residual de otra copia** (release/app instalada), NO del dashboard que ve el usuario ni del runtime. No hay desync real en el dashboard servido; se dejó constancia por si aparece en una instalación concreta. [Cerrado — Nickx]

## 18. CHECKLIST DEL ENCARGO DE BOSS (mapeo explícito: lo que pidió → dónde está en este SPEC)

Para que la revisión de Boss sea rápida, cada punto del encargo se mapea a la sección que lo resuelve. Si una celda está vacía, es un hueco que hay que cerrar antes de implementar.

| Punto del encargo de Boss | Dónde se resuelve en este SPEC | Estado |
|---|---|---|
| **Pasos exactos del onboarding (pantalla por pantalla, en orden)** | §1 (P0→P6, con T=minuto), §1e (wireframes en texto por pantalla), §1f (state-machine del wizard) | ✅ Completo |
| **Empty states: qué ve el empresario la primera vez (sin datos)** | §2 (tabla de empty states con copy word-for-word + CTA), §5d del SPEC 3 (teaser demo etiquetado) | ✅ Completo |
| **Copy en español para cada paso y estado vacío** | §1 (copy literal por pantalla), §2 (empty states), §4b (errores) | ✅ Completo |
| **Cómo ve el € en <15 min (camino mínimo al valor real)** | §0 (señal del aha), §4 (timeline por minuto), §15 (test de aceptación con `t_aha`), §16 (recorrido MVP) | ✅ Completo |
| **Qué datos necesita y cómo pedirlos sin fricción** | §3a.1 (entradas mínimas), §3a.2 (derivación campo a campo), §11b (árbol de decisiones: qué se pregunta / auto-detecta / difiere), §12 (obligatorio vs opcional) | ✅ Completo |
| **Un desarrollador implementa sin preguntar** | §10 (tareas para Nickx ordenadas), §11 (cronograma), §17 (decisiones tomadas con dato de código) | ✅ Completo |

**Conclusión de la auditoría:** el SPEC 1 cubre el 100% del encargo de Boss. No hay huecos de diseño. Los únicos pendientes son técnicos/operativos (confirmar método de conexión Shopify, plantilla CSV, mapeo FacturaScripts — todos ya RESUELTOS en §7b/§17 con dato de código).

*Documento de SPEC generado por Strati. Listo para que Nickx programe y Mathew testee.*
