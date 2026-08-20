# Auditoría Técnica VANOVA — FASE 1

**Fecha:** 2026-08-16 · **Método:** lectura de código + verificación con datos reales de la tienda (461 productos, 99 pedidos, conexión Shopify real).

---

## Resumen ejecutivo

VANOVA tiene una base arquitectónicamente buena: **ya existe un modelo de datos central** (`config_store` → `organizedProducts` / `organizedSales` / `organizedCustomers`), el API sirve una sola vista de dashboard (`/api/dashboard/local`), el runtime es autocontenido (Python embebido, sin dependencia del sistema), las skills de Gmail funcionan, y la suite de tests (293) cubre las capas principales.

Sin embargo, la auditoría encontró **violaciones de la fuente única de verdad** y **datos presentados de forma incompleta**, exactamente los dos problemas que el usuario percibe ("el dashboard dice una cosa y Hermes otra", "los datos no son correctos").

**Los 3 hallazgos CRÍTICOS:**
1. El catálogo que ven los agentes se **trunca silenciosamente a 400 filas** (hay 461) — los agentes declaran datos incompletos como si fueran el total.
2. El snapshot del dashboard tiene **dos escritores** (`business_scanner.save_scan_results` y `file_organizer.sync_dashboard_overview`) que se pisan.
3. El **frontend sobrescribe** `store.overview` con cálculos propios cliente-side, ignorando el snapshot del servidor (fuente canónica).

---

## Inventario de arquitectura actual

| Capa | Componente | Rol |
|---|---|---|
| Modelo de datos | `config_store.py` | Fuente de verdad: `organizedProducts/Sales/Customers`, snapshot, credenciales |
| Normalización | `file_organizer.py` | Ingesta de archivos, dedupe, `sync_dashboard_overview` (escritor del snapshot) |
| Integración | `shopify_sync.py` | Sync incremental Shopify → modelo (con `line_items` desde 2.0.18) |
| Integración | `integration_providers.py` | Conectores: Gmail, Drive, FacturaScripts (solo *conexión*) |
| API | `api_server.py` | FastAPI: `/api/dashboard/local`, `/api/agent/data/*`, tareas, skills |
| Agentes | `hermes_chat.py` + `agent_data_tools.py` | Conversación Hermes + tools de datos (misma fuente de verdad) |
| Dashboard | `web/dashboard.html` | SPA — lee `/api/dashboard/local` + recálculos propios |
| Análisis | `business_scanner.py`, `business_analyst.py` | Scan de archivos, recomendaciones de agentes |

**Lo que ya está bien (no tocar):**
- Los agentes y el dashboard **sí consultan la misma capa** (`config_store`) — el modelo central existe.
- `get_product_performance` desglosa por `line_items` reales (fix 2.0.18) y **declara honestamente** cuando no hay SKU por línea.
- El runtime empaqueta Python completo (usuario sin nada instalado funciona — verificado end-to-end).
- Los tests de `agent_data_tools` ya excluyen entidades falsas ("faltan permisos de shopify" no entra como producto).

---

## Hallazgos

### CRÍTICO

**H1 — El catálogo se trunca silenciosamente a 400 filas**
- **Causa raíz:** `MAX_ROWS = 400` en `agent_data_tools.py` se aplica a los *datos* (`_products()`, `_sales()`, `_customers()`), no solo a la presentación. `availability()`, `get_products()` y el contexto de los agentes declaran "400 productos" cuando hay 461.
- **Impacto:** Hermes trabaja con un catálogo incompleto **sin saberlo** y lo presenta como total. Es el "no hay 249 productos, hay más, están mal" y el "400 productos" que dice el Sales Analyst en la UI.
- **Solución:** eliminar el truncado silencioso de datos (cap de seguridad alto y documentado, ej. 20.000, muy por encima de cualquier negocio real). El truncado de *presentación* ya vive en `render_context_block(limit=30)` — separar datos de display.

**H2 — Dos escritores del dashboardSnapshot (duplicación de fuente de verdad)**
- **Causa raíz:** `business_scanner.save_scan_results()` **reemplaza** todo el `dashboardSnapshot` con un snapshot derivado del scan de archivos; `file_organizer.sync_dashboard_overview()` **muta** el overview con datos normalizados/sincronizados. Si un scan corre después de un sync, pisa datos reales con estimaciones de scan.
- **Impacto:** el dashboard puede mostrar una verdad distinta según quién escribió último; Hermes lee el mismo snapshot y propaga la inconsistencia.
- **Solución:** un solo escritor del overview (`sync_dashboard_overview`). El scan solo persiste metadatos (`lastScan`) y siembra el overview únicamente cuando nadie lo ha escrito aún.

**H3 — El frontend sobrescribe la fuente canónica con cálculos propios**
- **Causa raíz:** en `web/dashboard.html` (`pollCommerceNow` L3369-3370 y la carga inicial L5475-5485) el cliente **pisa** `store.overview.orders/revenue/customers` con un `summary` calculado cliente-side desde `ds.getSales()`. Dos cálculos independientes del mismo dato → divergencia dashboard vs Hermes.
- **Impacto:** es la receta exacta de "el dashboard dice €12.400 y Hermes dice €14.200".
- **Solución:** el valor del servidor (snapshot) gana siempre; el cliente solo rellena cuando el servidor aún no ha producido el dato (null).

### ALTO

**H4 — Frescura de datos: parcial**
- El snapshot lleva `fetchedAt` y el frontend ya lo guarda en `store.lastSync` y lo muestra (L2246). **Cubierto parcialmente.** Falta verificar que el badge aparezca en todas las vistas de KPI y que un dato stale se distinga visualmente. → FASE 7.

**H5 — FacturaScripts es solo un conector, no una fuente de datos**
- **Causa raíz:** `integration_providers` hace *probe* (web: sondea rutas API; local: busca `.sqlite`) y devuelve ok/detalle. **No existe sincronización de facturas, cobros, pagos, vencimientos, IVA ni tesorería.** No hay normalización, dedupe, ni reintentos.
- **Impacto:** la FASE 4 del plan (FacturaScripts como fuente financiera real) está **sin empezar**.
- **Solución:** FASE 4 completa: sync incremental, validación, normalización al modelo central, estado de sync, reintentos, timeouts, y tests de integración. El error de FacturaScripts nunca debe entrar al modelo como entidad.

**H6 — Cálculos duplicados entre servidor y cliente**
- Además de H3, hay lógica duplicada: dedupe de ventas y de clientes existen en `file_organizer.py` (servidor) y en el frontend. La única versión válida es la del servidor (modelo central).
- **Solución:** el servidor es el único que calcula; el cliente solo renderiza. (Se corrige junto a H3.)

### MEDIO

**H7 — `business_analyst.recommend()` es un esqueleto (91 líneas)**
- La proactividad real vive dispersa en `business_scanner`. Para la FASE 8 (motor de análisis: margen, cross-selling, tensión de caja) hace falta un motor dedicado con la cadena DATOS → OBSERVACIÓN → INTERPRETACIÓN → RECOMENDACIÓN → IMPACTO y la regla "no tengo suficientes datos".

**H8 — `load_local_dashboard._enrich_snapshot` mezcla counts live con snapshot guardado**
- Aceptable hoy, pero hay que documentar que el snapshot guardado puede divergir de los counts live. Con H2 (escritor único) y FASE 7 (frescura visible) queda acotado.

### BAJO

**H9 — Nombres internos** ("maios.agent.data", prefijos `MAIOS*` en el frontend): no visibles al usuario, no tocar para no romper la app.

---

## Estado real de las integraciones (verificado end-to-end)

| Integración | ¿Funciona E2E? | Notas |
|---|---|---|
| Shopify | ✅ Sí | 461 productos, 99 pedidos con `line_items` reales, paginación, sync cada 3 min, auto-curativo |
| Gmail (skill) | ✅ Sí | Bridge v2, auto-instala himalaya, estado real en UI, credenciales propagadas |
| Drive | ✅ Sí (conexión) | OAuth2 con refresh |
| FacturaScripts | ⚠️ Solo conexión | **Sin datos financieros** — FASE 4 |
| Archivos (Excel/CSV) | ✅ Sí | Scan + organización + dedupe + snapshot |

---

## Cobertura de tests (293 pasando)

**Cubierto:** config store, organizer, scanner, contexto de Hermes, sesiones, sync Shopify + paginación + line_items, skill Gmail, no-Python, hardening de Electron/runtime, RBAC/permisos, E2E smoke, integridad de datos básica.

**Huecos (FASE 9):**
- Integración FacturaScripts (no existe código que testear).
- Contract tests del API (`/api/dashboard/local`, `/api/agent/data/*`) — hoy solo smoke.
- Data integrity: cruzar totales (revenue del snapshot vs suma de ventas reales).
- E2E con UI real (el actual es HTTP-level).

---

## Plan de ejecución

| Fase | Contenido | Estado |
|---|---|---|
| **1** | Auditoría completa | ✅ **Esta documentación** |
| **2** | Corregir CRÍTICO + ALTO | ✅ H1, H2, H3 corregidos con tests de regresión |
| **3** | Modelo de datos central + validación formal | ✅ `business_model.py`: validadores en la frontera, procedencia por entidad, margen canónico, `sales_summary` de fuente única, `/api/integrity` + chequeo automático por sync |
| **4** | FacturaScripts profundo | ✅ `facturascripts_sync.py`: API `/api/3` + header `Token`, facturas/cobros/pagos/clientes/proveedores, retries, timeouts, rate-limit, protección parcial, estado visible; tools `get_invoices`/`get_treasury`/`get_suppliers`; contexto Hermes |
| **5** | Tesorería y datos financieros | ✅ Tesorería categorizada REAL/CALCULADO/NO DISPONIBLE (`treasury_summary`) + panel en Finanzas del dashboard que solo renderiza del modelo canónico |

### Nuevos hallazgos de FASE 3 y FASE 4 (auditados sobre el código)

**H10 — Margen con dos definiciones incompatibles (CRÍTICO, corregido):** `_with_margin`
(agent_data_tools) calculaba margen sobre COSTE (150%) mientras `_sales_summary`
(file_organizer) lo calculaba sobre VENTA (60%) — el agente y el dashboard decían cosas
contradictorias con los mismos datos. Corregido con una definición canónica en
`business_model.margin()` (marginPct sobre venta + markupPct sobre coste, explícitos).

**H11 — `_sales_summary` duplicado con implementaciones distintas (ALTO, corregido):**
file_organizer tenía la versión rica (mes/año/margen) y agent_data_tools la mínima
(solo pedidos+ingresos). Ahora ambas delegan en `business_model.sales_summary()`.

**H12 — Conector FacturaScripts con auth y endpoints equivocados (CRÍTICO, corregido):**
sondeaba `/index.php` con header `X-API-KEY`/`Bearer`; la API real de FacturaScripts vive en
`/api/3` y autentica con header `Token` (verificado contra la documentación oficial). Nunca
habría llegado a los datos.

**H13 — Persistencia por reemplazo en el sync (ALTO, corregido en test):** el primer diseño de
`_persist` reemplazaba el dataset completo, así que `facturasprov` pisaba a `facturascli` y un
recurso fallido perdía sus datos. Corregido a merge idempotente por id — detectado por el test
de integración, no por el caso feliz.

**H14 — Error-payload genérico (ALTO, corregido):** `_is_product_entity` rechazaba errores
por lista de frases conocidas (frágil). Ahora `business_model.is_error_payload` detecta
cualquier payload de error/diagnóstico con independencia del texto.

**H15 — El bucle de normalización trataba las líneas como partners (CRÍTICO, corregido):**
al añadir `lineascli`/`lineasprov`, el bucle de normalización no tenía la rama `line` y
las convertía con `_normalize_partner` → validación fallaba → las líneas se descartaban en
silencio (log decía "2 líneas", el modelo guardaba 0). Detectado por el test de integración
(no por el caso feliz), igual que H13.

**H16 — Latencia del contexto de Hermes (ALTO, corregido):** el contexto operativo se
construía **2 veces por pregunta** y cada build sondaba procesos/HTTP con timeouts de
~1,5s por componente → **~5,1s de sobrecarga antes de que el modelo piense**. Corregido con
cachés TTL de 10s a nivel de contexto (solo si el build tarda ≥150ms) + cachés de 2s en
`health_monitor.check_all`, `agent_architect.list_agents` y `port_utils.probe_runtime`.
**Resultado medido: 5,1s → ~0ms** por pregunta tras la primera.
| **6** | Hermes: velocidad (caching, tools selectivas), coherencia (contexto persistente), explicabilidad (cada % con su origen) | ✅ FASE 6 (contexto 5,1s→0ms) |
| **7** | Dashboard 100% conectado a la fuente de verdad + frescura visible | ⏳ (faltan: integraciones visibles + migración line_items) |
| **8** | Motor de análisis y proactividad (cadena DATOS→RECOMENDACIÓN, "no tengo suficientes datos") | ✅ FASE 8 (detection_engine + feed + Hermes) |
| **9** | Testing completo (unit, integration, contract, E2E, integridad, regresión) | ⏳ |
| **10** | Performance + hardening + release gate | ⏳ |

---

## FASE 8 — Motor de detección empresarial determinista

**Arquitectura**: DATOS CANÓNICOS → MÉTRICAS/SERIES → DETECCIÓN (reglas) → HALLAZGOS →
EVIDENCIA → IMPACTO → HERMES (interpretación). Nunca: LLM → OPINIÓN → DATO INVENTADO.

**Detectores y umbrales (constantes documentadas en `detection_engine.py`)**:
- Producto en caída/crecimiento: comparación de **períodos equivalentes** (30d actuales vs 30d
  previos), variación ≥30%, base ≥5 unidades y ≥50€ en el período previo (una muestra diminuta
  nunca se marca como tendencia).
- Mucho revenue + poco margen (share ≥15% y margen ≤ promedio−10pt) / poco revenue + alto
  margen (share ≤5%, margen ≥ promedio+10pt, revenue ≥100€). Margen siempre sobre venta,
  markup sobre coste, separados.
- Cross-selling: co-aparición con frecuencia ≥15% y ≥10 pedidos base que contienen A; el
  hallazgo muestra pedidos juntos, frecuencia y margen combinado cuando hay coste.
- Ticket medio: solo con ≥10 pedidos por período y variación ≥10%.
- Gastos: crecimiento ≥25% entre meses con ≥2 facturas recibidas.
- Tesorería: concentración de pagos próximos (vencimientos 30d ≥50% de los cobros) — el hallazgo
  declara explícitamente que **NO puede afirmar tensión de liquidez sin saldo bancario**.

**Calidad de datos como puerta**: muestra ≥20 pedidos fechados, cobertura de costes ≥60%,
 datos frescos (<7 días), reconciliación sin discrepancias high. Si no se cumple → sin finding
 o estado "Datos insuficientes".

**Cada hallazgo**: id, signature (dedupe), type, severity, category (problem/opportunity/
positive), title, observation, evidence[], metrics, period, source, confidence,
estimatedImpact {kind: calculated|estimated}, recommendedAction, createdAt, status con
lifecycle new→active→acknowledged→resolved→archived. Dedupe por firma: un problema que
persiste NO crea 20 copias; reaparece como ACTIVE tras resolverse.

**Hallazgos reales en datos actuales**: con los datos reales del usuario (461 productos, 99
pedidos) el motor genera 0 hallazgos — **correcto y honesto**: los pedidos de Shopify en disco
no tienen `line_items` (guardados antes de esa feature), así que el análisis por producto no
puede calcularse; el AOV comparado solo tiene 3+6 pedidos en 60 días (muestra diminuta,
bloqueada por el umbral); no hay facturas → tesorería/gastos correctamente en "Datos
insuficientes". Requiere **re-sync de Shopify** (backfill de line items) para activar la
analítica de producto — registrado en PENDING.

**Bug encontrado durante FASE 8**: la reestructuración del detector de producto dejó la lógica
de caída/crecimiento duplicada dentro de `_emit_margin_findings` con indentación rota
(IndentationError). Detectado por la suite (colección), corregido: el emisor de margen solo
emite hallazgos de margen y las caídas/crecimientos viven una sola vez en el bucle de producto.
Los tests de detección (15) cubren: dataset insuficiente, margen bajo/normal, caída real,
variación pequeña, muestra diminuta, cross-sell suficiente/insuficiente, tesorería sin saldo,
dedupe, lifecycle y actualización de estado.

---

## FASE 9 — Validación real y hardening

**Bug H18 (CRÍTICO) — `sales_summary` NameError**: la suma del revenue mensual usaba una
variable inexistente (`t`). Con los datos reales (99 pedidos con totales) `/api/integrity`
reventaba con `NameError`. Detectado al ejecutar `integrity_report` contra el backup real.
Corregido (`s.get("total")`) + test de regresión.

**Backfill de line_items de Shopify**: los pedidos del backup (v2.0.16+) no tienen
`line_items` porque se guardaron antes de esa feature. Nuevo `backfill_line_items()`
(`POST /api/shopify/backfill`, también automático tras cada sync ok): recupera líneas por
nombre de pedido, conserva id/customer/total/date/status, idempotente (2ª pasada = 0
candidatos), errores por pedido registrados individualmente y NUNCA borra datos válidos.
Verificado en E2E la cadena pedido→línea→SKU→cantidad→precio→coste→margen. **Pendiente de
autorización** para ejecutarlo contra la tienda real (escribe en la instalación local).

**Motor de detección — gates por evidencia**: el umbral de margen (<5 productos con coste)
bloqueaba también las caídas/crecimientos (que solo usan revenue/unidades). Ahora cada
detección usa SU PROPIA evidencia. Con los datos reales (461 productos, 99 pedidos, líneas
simuladas deterministas) el motor genera 0 hallazgos de forma HONESTA: solo 14 SKUs con
actividad en los últimos 60 días, 4 con margen (muestra insuficiente), sin caídas reales
entre períodos equivalentes, AOV con 3+6 pedidos (muestra diminuta bloqueada). No se tocaron
los umbrales para forzar resultados.

**Hardening**: (a) guarda de reentrada en la sync de Shopify (el loop de fondo y una llamada
manual nunca sincronizan a la vez; liberada en `finally`); (b) un `maios.json` corrupto no
se sobrescribe en silencio: se resguarda a `maios.corrupt-<ts>.json` antes de guardar y, si
el resguardo falla, se aborta el guardado. (c) `pytest.ini` aísla la colección de tests del
`python-bundle`.

**Proactividad**: toast al detectar un hallazgo nuevo (timesSeen=1, status=new, dedupe por
id en `_notifiedFindingIds`) + badge 🔴 de problemas activos en el nav Inicio, sobre el
lifecycle new→active→acknowledged→resolved→archived existente.

**Validación real (FS)**: la instancia local tiene FacturaScripts DESCONECTADO (url
placeholder, sin API key) → no se puede validar contra el servidor real sin credenciales.
Procedimiento documentado en `docs/VALIDACION-FACTURASCRIPTS.md` (auth `Token` sobre
`/api/3`, verificación por capa, reconciliación, idempotencia, fallos). Shopify real está
conectado; el backfill real requiere autorización para escribir en la instalación.

**Latencia real medida (FASE 9)**: contexto de Hermes 0,1 ms/pregunta tras la primera (TTL
10s; cold ~5,3s solo si los servicios están caídos), tools 0,02–2,7 ms (get_sales 2,7 ms;
resto <1,5 ms). El resto de la latencia de una pregunta es el modelo LLM externo, ya
instrumentado como `modelMs` en `timings`.

---

## FASE 10 — Validación final real

**Backfill REAL ejecutado (autorizado)**: 99/99 pedidos actualizados contra la tienda real,
236 líneas recuperadas, 0 fallidos, idempotente (2ª pasada 0 candidatos), 0 duplicados de
pedidos, campos originales conservados. Precondición: el config local estaba VACÍO (los datos
solo vivían en backups) — se restauró organizedProducts/Sales del último backup con backup
explícito previo, y tras el backfill se re-sincronizó el overview (integrity OK, 0 issues).

**Bug H19 — contexto de Hermes insuficiente**: el contexto no incluía los agregados de ventas
(revenue total, ticket medio, evolución mensual), así que Hermes pedía "consulta get_sales()"
en vez de responder. Corregido; verificado con LLM real: respuesta = valor canónico exacto.

**Bug H20 — escritura durante lectura (CRÍTICO)**: `_ensure_normalized_data` persistía
organized* derivados del `config_store.load()` durante el build del contexto (operación de
solo lectura). Un test que parcheaba `load` (sin `save`) SOBRESCRIBIÓ el config real
(3 pedidos en vez de 99). Restaurado desde backup y backfill re-ejecutado. Fix de raíz: la
migración solo reescribe organized* si `_needs_normalization_repair` es real; sin archivos y
sin reparación, solo avanza la versión. Regla: **leer el contexto NUNCA persiste datos**.
**Hallazgo adicional (explica el misterio del config vacío)**: `tests/test_hermes_operational_context.py`
(PRECEDENTE a FASE 10) parcheaba `config_store.load` sin `save`, y su fake incluía `scanFiles`
→ cada ejecución de la suite ESCRIBÍA sus datos de prueba (P1/P2/S1) sobre el config real del
usuario. Igual con `test_agent_data_tools.py` (fake con filas excel → repair=True). Ambos
+ `test_agent_status.py` ahora blindan `save` como no-op (setUp/with). Verificado: la suite
completa (367 tests) corre sin tocar el config real (99/461 con líneas intactos).

**Validación Hermes con LLM real (deepseek-v4-flash:cloud)**:
- Ventas: "99 pedidos, revenue 3.119,12 €, ticket medio 31,51 €" = canónico exacto (H19).
- Finanzas: "no te invento la facturación — no hay FacturaScripts" (honesto).
- No-alucinación: "saldo bancario no incluido en los datos sincronizados... no te invento una
  cifra" (superado). Beneficio neto: explica exactamente qué falta (COGS por pedido, gastos).
- Productos: no inventa ranking — pide get_product_performance/get_profitability.
- El CLI de Hermes SERIALIZA consultas: en paralelo falla con "Hermes ya está procesando otra
  consulta" (error claro, no corrompe nada).

**Hallazgos de datos reales (bloquean la analítica de margen, no son bugs de código)**:
(a) catálogo con coste=PVD en las 461 filas (sin costes reales cargados) → margen 0;
(b) 0/115 SKUs de líneas Shopify enlazados al catálogo Excel → coste por línea no resoluble;
(c) solo ~9 pedidos en los últimos 60 días → el motor genera 0 findings de forma HONESTA.

**Latencia real medida**: pregunta simple ~13-19s totales = ~5,2s contexto (cold, solo la
primera; 0,1ms tras TTL) + ~7-13s del modelo LLM externo. El CLI serializa consultas.

**FacturaScripts real**: pendiente de credenciales (desconectada). Procedimiento en
`docs/VALIDACION-FACTURASCRIPTS.md`.

---

## Principios que guían la implementación

1. **NO INVENTAR** — sin dato, se dice que no lo hay (ya lo hace el Sales Analyst: modelo a seguir).
2. **NO OCULTAR ERRORES** — los errores de integración viven en logs/estado, nunca en el modelo como entidades.
3. **UNA sola fuente de verdad** — servidor calcula, cliente renderiza, agentes consultan la misma capa.
4. **NO RECOMENDAR SIN DATOS** — "No tengo suficientes datos" es una respuesta válida.
5. **NO MOSTRAR STALE COMO ACTUAL** — toda cifra del dashboard tiene `fetchedAt`/fuente/estado.
6. **Cada bug → test de regresión** — para que no vuelva a aparecer.

---

## FASE 11 — Desbloqueo con veracidad total (product identity + cost verification)

### Problema de raíz
Tres bloqueos impedían la analítica de margen con datos reales: (1) FacturaScripts
desconectada; (2) **461/461 productos con coste = PVD** (sin evidencia de coste real,
pero el código lo usaba a ciegas como coste); (3) **0/115 SKUs de líneas Shopify
coincidían con el catálogo Excel** (los line_items guardan variant IDs de Shopify).

### Solución (capas canónicas, ninguna estima nada)
- **`desktop/runtime/product_identity.py` (nuevo)** — dos responsabilidades separadas:
  1. **COSTE**: `resolve_cost()` con regla absoluta *coste == PVD sin evidencia NO es
     coste* (`costStatus: verified|imported|estimated|missing` + `costSource`).
  2. **IDENTIDAD**: matching por fiabilidad `SKU exacto → barcode/EAN/GTIN → variant ID
     ↔ externalId → mapping manual persistido`; el **nombre SOLO genera propuesta**
     (`name_suggestion`, nunca match automático). La relación es de identidad
     (`productMappings` con matchMethod/confidence/verified/timestamps), nunca copia.
  3. **Coberturas** (`cost_coverage`, `identity_coverage`, `build_reconciliation`) que
     miden el REVENUE analizable, no solo el conteo de filas.
- **`business_model.py`** — `with_margin`, `sales_summary`, `resolve_line_product` y
  `profitability` resuelven el coste vía `resolve_cost` + identidad. Sin coste verificado
  o sin identidad → `marginPct/markupPct = null` y motivo explícito (`costCoverage`).
- **`detection_engine.py`** — nuevos gates `costCoverageOk` e `identityCoverageOk`
  (`canAnalyzeMargin`); el motor ahora dice **por qué** no genera
  (`blockedReasons`: "Bloqueado por falta de coste real…", "Bloqueado por identidad…").
  La caída/crecimiento de producto sigue sin depender del coste (evidencia propia).
- **`agent_data_tools.py` / `hermes_chat.py`** — tools nuevas
  `get_product_reconciliation`, `get_cost_coverage`, `get_identity_coverage` y bloque
  `CALIDAD DE DATOS` en el contexto (Hermes responde con números canónicos).
- **API + UI** — `GET /api/products/reconciliation`, `GET /api/products/coverage`,
  `POST /api/products/match` (+remove, mutaciones con bearer); bloque **Calidad de datos**
  (VERIFIED/PARTIAL/BLOCKED) en Inicio y página **Reconciliación de productos**
  (MATCHED/REVIEW/UNMATCHED con vínculo manual explícito).

### Validación real (461 productos, 99 pedidos, 236 líneas, €3.119,12)
- **Reconciliación**: 114 SKUs de venta → 0 matched, 23 unmatched, **91 con propuesta por
  nombre** (REVIEW), 461 del catálogo nunca usados. Cobertura 0% — honesto.
- **Coste real**: 0/461 productos con coste verificado (todos coste=PVD) → revenue con
  coste 0€. **Margen no calculable — y ahora el sistema lo dice con números.**
- **Identidad**: 0% del revenue con match. **Profitability: 0 pedidos con coste.**
- **Motor**: 0 findings con `blockedReasons` explícitos en vez de 0 silencioso.

### Suite
- **+28 tests** (`tests/test_product_identity.py`): PVD≠coste, coste verificado,
  margen bloqueado/sin identidad/parcial, matching por fiabilidad, mapping manual que
  desbloquea margen SOLO de esa línea, gates del motor, reconciliación que no modifica
  datos fuente, mappings idempotentes, la suite no toca la instalación real, y secretos
  que nunca salen a output/logs. Contrato UX actualizado (polling + coverage + recon).
- **Resultado: 395 passed, 1 skipped.** Config real intacto tras la suite (461/99).

### Estado
🟠 **PRODUCTION READY — DATA BLOCKED**: el código está validado y veraz. Siguen
bloqueados los DATOS: (1) FacturaScripts sin credenciales (P14 ⛔ BLOCKED);
(2) costes reales del catálogo (coste=PVD); (3) mapping de los SKUs de Shopify
(vía la nueva UI de reconciliación: cada vínculo manual verificado desbloquea margen).

---

# Auditoría Técnica — FASE 12 (Operación real de calidad de datos)

**Fecha:** 2026-08-16 · **Método:** operación REAL sobre la instalación (backup previo a cada escritura) + validación independiente.

## Qué se desbloqueó (números reales, ANTES → DESPUÉS)

| Métrica | ANTES | DESPUÉS |
|---|---|---|
| Productos con coste verificado | 0/461 | **414/461 (89,8%)** — coste NET EX WORKS real del proveedor (Carrefour) |
| Revenue con coste real | 0 € | **1.254,74 € (41,6%)** |
| Identidad de producto (líneas matched) | 0/114 SKUs | **114/114 (100%)** vía variant ID recuperado |
| Revenue con identidad | 0% | **75,2%** (187 líneas matched / 49 sin match) |
| Pedidos con coste | 0/99 | **55/99** |
| Revenue analizable (identidad + coste) | 0 € | **1.254,74 €** (43,1% del revenue con ambas) |

## Causa raíz de los 3 bloqueos → resuelto

1. **Coste=PVD** → importador `cost_importer.py` con BACKUP → PREVIEW (414/414 matches por SKU, 0 sobrescrituras) → IMPORT → INTEGRITY. Los 47 restantes no están en la lista del proveedor → siguen `missing`, sin inventar.
2. **SKUs de Shopify ≠ catálogo** → el sync **descartaba** `variant.id`/`barcode` y las líneas guardaban variant_id como sku. Fix: `_map_shopify_products` conserva `shopifyVariantId`+`barcode`; `_map_shopify_orders` guarda `variant_id` por línea; `recover_variant_identity()` recuperó 446/461 variant IDs del catálogo (idempotente, solo añade); `resolve_identity` resuelve variant_id en `sku` ↔ `shopifyVariantId` del catálogo.
3. **FacturaScripts** → sigue ⛔ BLOCKED — credentials required (no hay URL/token reales; no se simula nada).

## Bugs encontrados y corregidos

- **H21 (contexto Hermes)**: el contexto no incluía revenue por producto → Hermes decía "no puedo rankear productos". Fix: bloque "Top ventas" en `render_context_block` + `get_product_performance` ahora **ordena por revenue descendente** (antes devolvía orden de inserción). Verificado con LLM real: responde el top real (Agenda Harry Potter 842 €, 6× el segundo) + matices de calidad de datos.
- **P2 (UX)**: "Ignorar" se implementó primero como mapping falso → descartado; ahora `productIgnoredSkus` (lista revisable, `ignore_sku`/`unignore_sku`), nunca crea vínculo.

## Validación independiente (P8)

25 productos reales: margen/markup VANOVA == cálculo manual desde la lista Carrefour + líneas Shopify, dentro del redondeo (±0,1 pp). Sin usar el código de VANOVA para validar a VANOVA.

## Motor de detección (P9)

Gates honestos: `canAnalyzeMargin: true` (cobertura 89,8%) pero solo 9 pedidos en los últimos 60 días → **0 findings con explicación explícita** ("Muestra reciente insuficiente… no se emiten para no inventar") en `blockedReasons`.

## Hermes real (P10)

7 preguntas con LLM (deepseek-v4-flash:cloud): respuestas = datos canónicos exactos (99 pedidos / 3.119,12 € / 41,6% coste / 75,2% identidad). No generaliza el margen parcial: "el margen NO es calculable de forma fiable… no invento ningún coste que no esté verificado".

## Tests

399 passed, 1 skipped (antes 395). +4: variant_id en sku ↔ catálogo, mapper conserva variant_id/barcode, performance ordenado + contexto, SKU ignorado reversible. Config real intacto tras la suite (461/99/414/446).

## Estado final

🟠 **PRODUCTION READY — DATA BLOCKED parcial** (mejorado): 43,1% del negocio analizable con coste real. Qué falta para 🟢: (1) **FacturaScripts real** (URL + API key); (2) **costes de los 47 productos** restantes (no están en la lista Carrefour); (3) **más actividad reciente** (solo 9 pedidos en 60 días → el motor no emite findings de período). La UI ya permite: reconciliación con detalles + bulk confirm + ignorar + exportar, recuperación de identidad, e importador de costes con preview.

---

# Auditoría Técnica — FASE 13 (Desacoplar VANOVA de Shopify)

**Fecha:** 2026-08-16 · **Método:** auditoría de acoplamiento + contrato de conectores + tests de desacoplamiento. Nada publicado, config real intacto.

## 1. Qué seguía acoplado a Shopify (P1)

| Módulo | Ref count | Clasificación | Acción |
|---|---|---|---|
| `business_model.py` | 2 | C (cosmético) | Solo strings de error → sin cambio |
| `detection_engine.py` | 1 | C | Comentario → sin cambio |
| `product_identity.py` | ~15 | **B** | Params `shopify_sku`, claves `shopifySku` → **generalizado a `sourceSku`/`sourceVariantId`** (alias de compatibilidad) |
| `agent_data_tools.py` | 2 | C | Etiqueta "line_items (Shopify)" → **genérica** |
| `hermes_chat.py` | 61 | **B (pesado)** | Contexto hardcodeaba "Shopify:" → **«Fuentes de datos» genérico desde el registry** |
| `file_organizer.py` | 12 | **B** | Merge hardcodeaba `source == "shopify"` → **`_is_connector_source` (cualquier conector registrado)**; dedupe cliente genérico |
| `api_server.py` | 16 | A/B | `/api/shopify/*` = connector (correcto); `/api/products/match` acepta `sourceSku` genérico |
| `integrations_store.py` | ~10 | A | Helpers de credenciales Shopify = connector (correcto) |
| `shopify_sync.py` | — | A | El conector (correcto) |
| `data-services.js` / `dashboard.html` | 29 / 124 | B/C | Copy "conecta Shopify" → genérico; nueva página **Fuentes de datos** |

## 2. Contrato de Connector (P2/P3) — `connector_base.py`

- **`Connector`**: id, label, description, implemented, capabilities(), effective_capabilities(), status(), sync_now().
- **Capabilities normalizadas**: products, orders, order_lines, customers, inventory, invoices, invoice_lines, payments, suppliers, costs, finance, stock.
- **Declaradas vs efectivas**: Shopify declara products/orders/… pero NO invoices (no es ERP); FacturaScripts declara invoices/payments/suppliers/finance pero su *efectiva* depende de conexión. WooCommerce/PrestaShop registrados con `implemented=False` → "Próximamente" (no se simulan).
- **`missing_capability_reason(cap)`** distingue: "FacturaScripts puede proporcionarlo pero está desconectado" vs "ninguna fuente soportada lo proporciona".
- **API**: `GET /api/sources` → source_summaries() + aggregate_capabilities().

## 3. Modelo canónico (P4) + identidad multi-fuente (P5)

- Los objetos ya eran genéricos (source/sourceFile/id/line_items) salvo la identidad: ahora `resolve_identity` acepta `variant_id`/`source_variant_id`/`sourceVariantId`/`externalId`/`shopifyVariantId` y los mappings usan `sourceSku`+`source`+`sourceVariantId` (con alias `shopifySku` para datos previos).
- **Nuevo `normalize_sale_lines()`** en `business_model`: una fila plana de CSV/Excel (sku/qty/total) se convierte en UNA línea canónica — el core (profitability, detección, métricas, coberturas) trata por igual un pedido de Shopify que un CSV antiguo. **Esto era un bug real (H22): las ventas CSV no entraban en profitability/detección.**

## 4. Hermes (P9)

- Contexto operativo con bloque «Fuentes de datos»: cada fuente con estado, última sync y capacidades; `CAPACIDADES FALTANTES` explica con `missing_capability_reason`. Hermes ya no puede decir "Shopify tiene X" — ve "los datos disponibles vienen de estas fuentes".
- `_message_wants_shopify_context` se mantiene como heurística de intención (no es acoplamiento estructural).

## 5. Dashboard (P10)

- Nueva página **Fuentes de datos** (`/sources`): cada conector con estado, capabilities y "Próximamente" para WooCommerce/PrestaShop.
- Panel operativo de Hermes con grid de fuentes (tienda online, FS, CSV/Excel).
- Copy "Importa archivos o conecta Shopify" → "Importa archivos CSV/Excel o conecta una tienda o ERP".

## 6. Tests (P12)

`tests/test_decoupling.py` — 12 casos: profitability con CSV, detección con CSV, costes de ERP, costes de Excel, identidad entre dos fuentes, IDs de proveedor no contaminan el canónico, mapping genérico multi-fuente, capabilities declaradas/efectivas, razón de capacidad faltante, fuente sin invoices no rompe finance, Hermes contexto genérico, Shopify desconectado no rompe el core.

**Suite completa: 411 passed, 1 skipped** (antes 399). Config real intacto tras la suite (461/99).

## 7. Estado final

- Conectores implementados: **shopify, facturascript, fileimport (CSV/Excel)**.
- Preparados (no implementados): **woocommerce, prestashop** → "Próximamente".
- Qué puede hacer una empresa SIN Shopify: importar CSV/Excel (productos, ventas, costes, clientes) y conectar FacturaScripts — todo alimenta el mismo modelo canónico.
- Con Shopify + FacturaScripts: pedidos/líneas/clientes de la tienda + facturas/pagos/proveedores/tesorería del ERP, costes de Excel, todo reconciliado en el mismo modelo.
- Pendiente: conectar FacturaScripts real (URL+key), implementar WooCommerce/PrestaShop cuando haya cliente que lo pida, y el conector de inventario (ninguna fuente lo expone hoy).

---

# Auditoría Técnica — FASE 14 (Release de producción 2.0.21)

**Fecha:** 2026-08-16 · **Estado:** PUBLICADA en GitHub Releases (`frexcz-star/vanova-updates`, tag `v.2.0.21`).

## Build
- Build limpio desde cero con `scripts/release.ps1 -Version 2.0.21`: bump de versión (version.json, desktop/package.json, shared/version_info.py), sync de web/dist, bundle Python, instalador NSIS x64, verify-package, checksums, manifest. Sin artefactos temporales, sin backups ni credenciales en el paquete (scan de `shpat_`/`shpss_` limpio).

## Update real (2.0.20 → 2.0.21)
- E2E automático: manifest + SHA256 + size coinciden; `update_available_from_2.0.20: True`; download verificado.
- Instalación REAL silenciosa sobre la 2.0.20 instalada: versión pasa a 2.0.21, **config byte-idéntico** (sha256 9878e0d1… igual antes/después: 461 productos / 414 costes / 446 variant IDs / 99 pedidos), `integrations.json` intacto (token Shopify + FS conservados). Migraciones idempotentes.

## BUG CRÍTICO encontrado en smoke test (H23) → corregido ANTES de publicar
- **Síntoma**: tras arrancar la app 2.0.21, `costCoverage` pasó de 41.6% a 0% (414 costes → 0).
- **Causa raíz**: `shopify_sync._merge_products` descartaba los productos Shopify existentes y los reemplazaba por la respuesta fresca de la API — que NO incluye los costes importados (`cost`/`costSource`/`costStatus`/`sourceReference`). Cada sync borraba el enriquecimiento local. Afectaría a TODOS los clientes con costes importados.
- **Fix**: preservar los campos de enriquecimiento local al fusionar (`_LOCAL_ENRICHMENT_FIELDS`), indexando todos los existentes antes de reemplazar.
- **Verificación**: test de regresión (`test_shopify_sync_preserves_imported_costs`), simulación de merge real (414 → 414), y **re-sync real de la app tras reinstalar: cost 41.6% / identidad 75.2% se mantienen**.

## Smoke test de producción (app 2.0.21 instalada + runtime :8765)
- Core: health ok, version 2.0.21, integrity 0 issues.
- Datos: coverage cost 41.6% (1254,74 €) / identidad 75.2%; reconciliación 114/114 (100%).
- Integraciones: Shopify CONECTADO (4 caps), FacturaScripts DESCONECTADO (8 caps declaradas), FileImport CONECTADO (5 caps), WooCommerce/PrestaShop PRÓXIMAMENTE.
- Hermes: contexto con «Fuentes de datos» genérico + CAPACIDADES FALTANTES explicadas + agregados reales.
- UI: nuevas páginas/secciones presentes en el paquete (13 refs dashboard, 3 métodos data-services).

## Suite
412 passed, 1 skipped (+1 H23). La única ejecución no-verde fue la app corriendo en paralelo compitiendo con un test de backups (flaky por concurrencia, no por el código) — con la app detenida, suite 100% verde.

## Release publicada
- Tag `v.2.0.21`, asset `VANOVA-Setup-2.0.21.exe` (107.403.134 bytes, sha256 57eda640…), manifest estable `latest.json` → 2.0.21, 11 release notes, verificado por HTTP (200 + Content-Length coincide).

---

## FASE 15 — Optimización de latencia de Hermes (2026-08-16)

### Medición ANTES (pipeline real con LLM deepseek-v4-flash:cloud)

| Fase | ms |
|---|---|
| Contexto VANOVA frío | 10.390–12.282 ms |
|  └ render_context_block | 5.844–6.156 ms |
|    ├ list_findings (→data_quality→cost_coverage+identity_coverage) | 2.781 ms |
|    ├ cost_coverage | 1.328–1.344 ms |
|    └ identity_coverage | 1.328 ms |
| CLI arranque puro (--version) | 109 ms |
| CLI negociación provider (hasta 1ª línea) | ~1.625 ms |
| CLI generación LLM | ~4.000 ms |
| "hola" end-to-end | ~15 s (2× contexto sin caché + CLI) |

### Cuello de botella exacto
1. **contextMs**: el contexto se construía 2× por consulta casual (caché solo
   con include_shopify=True; "hola" → include_shopify=False → sin caché).
2. **Coberturas O(líneas × catálogo)**: resolve_identity reconstruía by_sku y
   recorría el catálogo por cada línea; cost_coverage añadía otro bucle
   O(catálogo) por línea; list_findings→data_quality repetía ambas.
3. **LLM**: 85–99 % del tiempo tras la optimización VANOVA.

### Cambios realizados
1. `product_identity.build_catalog_index()` — índice precomputado (sku/barcode/
   variant/name) reutilizado por lote: coberturas O(líneas + catálogo).
2. `cost_coverage` — mapa cost_by_sku precomputado (elimina bucle interno).
3. `resolve_identity(catalog_index=, ignored=)` — opcionales, sin cambiar firma
   pública; `build_reconciliation` también usa el índice.
4. `hermes_chat._is_casual_message()` — ruta ligera para saludos/casual sin
   datos; el contexto mínimo declara que NO hay datos (anti-alucinación).
5. `_build_chat_context()` — ruta ligera primero; caché del contexto aplica
   SIEMPRE (antes solo include_shopify=True).
6. `_process_request_impl()` — el contexto pesado solo se construye si hace
   falta (detalle operativo y no casual).
7. Frontend: polling 600→400 ms inicial (más agresivo al arranque).

### Medición DESPUÉS (misma batería, LLM real)

| Pregunta | contextMs | modelMs | polling real |
|---|---|---|---|
| "hola" (casual) | 0 | 7.500 | 8.016 ms |
| "gracias!" (casual) | 0 | 6.531 | 7.031 ms |
| "¿cuántos pedidos?" | 0 (caché) | 8.641 | 9.000 ms |
| "¿cuánto he vendido?" | 0 (caché) | 8.391 | 9.015 ms |
| "¿tesorería?" | 0 (caché) | 21.672 | 22.031 ms |
| "¿productos rentables?" | 0 (caché) | 13.172 | 13.344 ms |

Contexto frío: 11.250 → **1.157 ms** (10×). Contexto caliente: 0 ms.
render_context_block: 6.156 → **140 ms** (44×).

### Conclusión de latencia
El cuello de botella residual es el **LLM** (negociación provider ~1,6 s +
generación 4–18 s según complejidad). VANOVA ya no añade prácticamente nada
(contexto 0–1 s, polling ~0,4 s). La ruta ligera deja "hola" en ~8 s, pero ese
tiempo es del modelo externo, no de VANOVA.

**No se cambió de LLM** (regla de la fase). Pendiente evaluado: `hermes serve`
(JSON-RPC persistente, puerto 9119) podría ahorrar ~1,5 s de negociación por
consulta, pero es un cambio de integración grande con riesgo de romper el
streaming de progreso; se documenta para una fase futura, no se implementa
ahora porque el coste dominante es el LLM, no la infraestructura.

### Tests
+5 tests: clasificador casual (5 casos), ruta ligera no construye contexto,
guard anti-alucinación, equivalencia+rendimiento del índice de catálogo.
Suite completa: **417 passed, 1 skipped** (antes 412). Config real intacta
(461 productos / 99 pedidos / 414 costes / 461 variant-id). No se escribió
sobre datos reales ni se publicó nada.

---

## FASE 16 — Release 2.0.22 (optimización de latencia FASE 15) (2026-08-16)

- **Build limpio**: instalador 2.0.22 (107.405.217 bytes) desde scripts/release.ps1.
  Paquete verificado: ruta ligera `_is_casual_message` (3 refs), índice de catálogo
  `build_catalog_index` (6 refs), polling `pollCount < 30` en el frontend empaquetado.
  Sin scripts temporales, sin tokens (solo strings de validación), sin datos de test.
- **Update real**: instalado sobre 2.0.21 → versión 2.0.22, config **byte-idéntica**
  (sha256 ae1e62dc antes/después), datos intactos (461/99/414/461), credenciales
  Shopify + FacturaScripts conservadas.
- **Smoke test producción**: runtime 2.0.22 arriba; Shopify CONECTADO con sync real
  (23:50); cobertura 41,6% coste / 75,2% identidad intacta tras la sync de arranque
  (H23 OK); reconciliación 114/114 (100%); contexto Hermes con fuentes genéricas;
  cloud/connector ok.
- **Regresión**: **417 passed, 1 skipped** (0 fallos). Config real intacta tras la suite.
- **Publicación**: GitHub Releases v.2.0.22. Manifest remoto `latest.json` = 2.0.22,
  sha256 c313539... = instalador probado (107.405.217 bytes). LATEST TAG verificado.

## FASE 16 — Release 2.0.23 (fixes de validación con dataset sintético)

Publicada el 2026-08-17. Canal estable (GitHub Releases). 423 tests passing, 1 skipped.

Fixes incluidos:
- **H24**: CSV de ventas/productos/clientes >64KB se importaban parciales y silenciosos
  (la vista previa truncada a 64KB se usaba como única fuente). El extractor ahora lee
  siempre el archivo completo del disco.
- **H25**: el gate de tendencia comparaba euros contra unidades → falsos "en caída" con
  muestras diminutas. Ahora exige unidades reales vendidas.
- **H28**: umbrales porcentuales comparados como fracciones vs puntos (AOV efectivo 0,1%
  en vez de 10%). Un cambio del 3% ya no dispara alertas de ticket medio.
- **H31**: Hermes negaba tesorería/facturación aunque el modelo canónico ya tuviera los
  datos. El contexto ahora distingue "datos presentes, integración en vivo desconectada".

Validación real (FASE 16): dataset sintético NOVA HOME & TECH (149 productos, 1.742
pedidos, 370 facturas, 278 movimientos) con anomalías plantadas → 6/9 detectadas
(recall 67%), 0 falsos positivos de las anomalías. Informe completo:
docs/FASE16-DATASET-SINTETICO.md

Verificación de la release: update real 2.0.22 → 2.0.23 con config byte-idéntica,
smoke test completo en producción (cobertura 41,6% coste / 75,2% identidad intacta
tras la sync de arranque), manifest remoto = sha256 del build probado.

---

## 2.0.24 — Release FASE HERMES (2026-08-17)

**Objetivo**: calidad de respuesta, velocidad y fiabilidad analítica de Hermes.

### Cambios
- Ventana temporal honesta: el contexto declara que el total cubre TODO el histórico y añade NOTA de ventana cuando la suma de los meses visibles ≠ total (antes presentaba los últimos 3 meses como "evolución mensual" → total 3.119 € vs suma 442,89 €).
- DATA COVERAGE por dominio (Ventas DISPONIBLE · Costes PARTIAL · Identidad PARTIAL · Facturas/Tesorería NO DISPONIBLE o DATOS CANÓNICOS).
- Respuesta ejecutiva de 5 secciones (ESTADO GENERAL · NÚMEROS CLAVE · QUÉ FUNCIONA · QUÉ ESTÁ BLOQUEADO · SIGUIENTE ACCIÓN) y separación HECHO / INFERENCIA / NO DISPONIBLE.
- Paralelización de sondas del contexto: build frío 1.172 → 844 ms (−28%). Dedup de coberturas (una sola vez por build).
- Privacidad: el log del CLI ya no vierte el prompt completo (PII); registra solo modelo y tamaño del prompt.

### Medición de latencia (FASE HERMES)
- Cuello de botella = LLM cloud (deepseek-v4-flash:cloud): primer token 7,5–10 s incluso para "hola". VANOVA aporta 0–1,2 s (contexto cacheado 10 s).
- Objetivo <5–7 s NO alcanzable sin cambiar de modelo (el primer token del modelo ya supera 7,5 s).

### Validación
- 429 passed, 1 skipped (+6 regresiones FASE HERMES).
- Update real 2.0.23 → 2.0.24: maios.json byte-idéntica (salvo shopifySync.lastSync de la sync de arranque), datos intactos (461/99/414), credenciales intactas.
- Smoke: runtime 2.0.24, Shopify conectado (461/99), coberturas 41,6%/75,2% intactas, reconciliación 114/114, contexto con los 7 fixes PASS, respuesta real con estructura ejecutiva y ventana honesta.
- Publicada: GitHub Releases v.2.0.24, manifest remoto = sha256 exacto del build probado (86c2610f...), instalador 107.409.043 bytes accesible.
