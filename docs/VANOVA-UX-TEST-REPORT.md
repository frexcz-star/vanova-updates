# VANOVA 1.0.2 — TEST UX INTERFAZ

**Fecha:** 2026-08-13  
**Entorno:** Dashboard `http://127.0.0.1:8000/` · Runtime API `:8765`  
**Versión verificada:** 1.0.2 (canal stable)  
**Método:** Navegación automatizada con Playwright (headless Chromium). Las herramientas MCP `cursor-ide-browser` no pudieron abrir pestaña (`No browser tab available`); se usó captura visual equivalente.  
**Login:** `ceo` / credenciales demo del entorno local — acceso correcto, sin bloqueo.

**Capturas:** `docs/ux-screenshots/` (PNG full-page por sección)

---

## Resumen visual (nota 1–10 por sección)

| Sección | Nota | Comentario breve |
|---------|------|------------------|
| Navegación y layout | **8/10** | Sidebar clara, jerarquía por grupos; sidebar más extensa que el checklist mínimo |
| Inicio | **8/10** | Cards legibles, buen foco en atención/ejecución; saludo en inglés |
| Insights | **7/10** | Empty state limpio; filtros pill bien diseñados |
| Tareas | **7/10** | Lista clara; estados en inglés crudo (`running`, `failed`) |
| **Hermes** | **8/10** | Layout 2 columnas usable; **sin bloqueo "Cargando contexto"**; panel operativo colapsable |
| Integraciones | **7/10** | Grid de tarjetas profesional; bug `${companyName()}` visible |
| Productos | **8/10** | Tabla limpia con 249 filas; título en inglés |
| Diagnóstico | **6/10** | Semáforos útiles; carga inicial lenta; etiqueta "Connector" no traducida |
| Ajustes / Updates | **9/10** | v1.0.2 visible, update-center funcional, tema claro/oscuro OK |
| Responsive móvil | **5/10** | Solapamiento de badges en header; nav lateral fuera de viewport |

**Nota global interfaz:** **7.5/10** — Aspecto SaaS comercial creíble; detalles de i18n, estados crudos y carga de diagnóstico restan pulido.

---

## Capturas / descripción de cada pantalla

### 00 — Sidebar y navegación
**Archivo:** `docs/ux-screenshots/00-sidebar.png`

- Logo VANOVA (M rojo) + wordmark en sidebar fija ~240px.
- Grupos colapsables: Command Center, Work, Data, Automation, System.
- Items visibles: Inicio, Insights, Actividad, Tareas, Agentes, Hermes, Aprobaciones, Integraciones, Archivos, Productos, Fuentes, Automatizaciones, Decisiones, Diagnóstico, Ajustes.
- Item activo: barra vertical roja/coral + fondo tintado suave.
- Header superior: breadcrumb de vista, selector workspace "MOOVING PAPER", búsqueda "Buscar en VANOVA… ⌘K", campana, toggle tema (sol/luna), pills "Actualizaciones" y "Sistema operativo" (punto verde), acceso Hermes, avatar "PA / Pablo".
- Botón "Colapsar panel" al pie del sidebar.

### Inicio
**Archivo:** `docs/ux-screenshots/home.png`

- Saludo grande: **"Good afternoon, Pablo"** (inglés).
- Sub-stats: oportunidades / riesgos / decisiones pendientes.
- Línea sync: punto verde + timestamp ISO + "4 fuentes conectadas".
- Cards apiladas con buen espaciado (radius ~12px, sombra sutil):
  - **"Qué necesita tu atención"** — borde izquierdo rojo, icono escudo, CTA "Ver aprobaciones →".
  - **"Ejecutándose ahora"** — filas con puntos de color (verde/azul) y estados "En ejecución" / "En cola".
  - **"Resultados recientes"** — fondo azul claro, preview de informe Marketing Agent.
- Jerarquía visual clara: atención → ejecución → resultados.

### Insights
**Archivo:** `docs/ux-screenshots/insights.png`

- Título "Insights de IA", subtítulo descriptivo.
- Filtros pill: Todos (activo, coral), Riesgos, Oportunidades, Recomendaciones, Anomalías, Predicciones.
- Empty state centrado: icono estrella + "No hay insights de este tipo." — diseño limpio, no parece error.

### Tareas
**Archivo:** `docs/ux-screenshots/tasks.png`

- Título "Tareas", subtítulo "8 en historial reciente".
- Cards verticales por tarea: nombre agente, timestamp ISO, badge estado (esquina superior derecha).
- Contenido expandido en tareas completadas (informe marketing).
- Error visible en rojo: timeout Hermes 240s — legible pero crudo técnicamente.
- Estados mostrados como texto inglés: `running`, `queued`, `completed`, `needs_approval`, `failed`.

### Hermes (CRÍTICO)
**Archivos:** `docs/ux-screenshots/hermes.png`, `hermes-full-scroll.png`

**Layout:**
- Banner superior verde: **"Chat listo"** + "Hermes listo — conexión local (~2.4–2.6 s)".
- Grid 2 columnas (≈50/50):
  - **Izquierda — "Pregunta a Hermes":** input alto 48px, botón "Adjuntar archivo" (clip), chips sugeridos (Hola, ¿Cómo está la empresa?, etc.), CTA primario coral "Enviar a Hermes", secundario "Conversaciones anteriores".
  - **Derecha — "Conversación con Hermes":** empty state con icono spark, texto guía, link "Ver diagnóstico →", botones contextuales "Organizar Excel" / "Ver productos disponibles".
- **Panel operativo** (`<details>`): summary "Estado operativo" — **colapsable, debajo del chat**, no bloquea interacción.
- Sección inferior "Sesiones anteriores" con entradas de historial terminal.

**Verificación bloqueo "Cargando contexto":**
- **NO aparece** como overlay ni banner bloqueante en ninguna captura.
- El panel operativo muestra texto de carga en segundo plano ("Los datos operativos se cargan en segundo plano") sin impedir el chat.
- Input, adjuntar y enviar permanecen accesibles.

**Comparación vs Hermes standalone:**
- Menos "chat puro" (burbujas WhatsApp-style); más **consola de mando** con input + log lateral.
- Quick replies y chips de acción integrados en el panel de conversación vacío.
- Sesiones y arquitectura (ocultable) añaden contexto enterprise que standalone no tiene.
- Color acento rojo/coral en avatares "H" y "TÚ" — coherente con VANOVA, distinto de terminal CLI.

### Integraciones
**Archivos:** `docs/ux-screenshots/integrations.png`, `integrations-drawer.png`, `shopify-drawer-open.png`

- Grid 3×4 de tarjetas con icono color, nombre, punto de estado (verde Conectado / naranja Pendiente), descripción, meta inferior, botón acción.
- Shopify: **Conectado**, meta "Sync cada 3 min", botón **Gestionar** (coral outline).
- Excel/CSV, Word, JSON: Conectado con conteo de archivos.
- PDF, Drive, ERP, MCP, Email, Instagram: Pendiente.
- **Bug visual:** descripciones muestran literal `${companyName()}` sin interpolar (Excel/CSV, FacturaScript).
- Drawer/modal Shopify: prompt nativo "URL de tu tienda Shopify" con placeholder `https://tu-tienda.myshopify.com`, botones Cancelar / Aceptar — funcional pero estilo `prompt()` del navegador, no drawer Polaris.

### Productos
**Archivo:** `docs/ux-screenshots/products.png`

- Título **"Products"** (inglés) — subtítulo sí en español: "249 productos reales del catálogo de MOOVING PAPER."
- Botón "+ Nuevo" coral, filtros Todas / Recientes.
- Tabla: columnas PRODUCTO, SKU, PRECIO NETO (€), RRP — filas alternadas, tipografía 13px legible.
- **No** hay fila de error como dato; catálogo poblado correctamente.
- Banner warning Shopify: no visible con sync activa (esperado).

### Diagnóstico
**Archivos:** `docs/ux-screenshots/diagnostics.png`, `diagnostics-loaded.png`

- Carga inicial: solo texto "Cargando diagnóstico…" (~1–2 s percibidos).
- Tras carga: banner ámbar "Runtime no disponible — mostrando datos parciales" (estado fluctuante según runtime).
- Secciones PUERTOS, ESTADO DE CONEXIONES, DIAGNÓSTICO DEL SISTEMA.
- Filas con puntos semáforo: rojo (Runtime), verde (Cloud activo), naranja (Connector, Hermes desconocido).
- Botón "Actualizar" ghost, alineado a la derecha.
- Etiquetas: **"Connector"** en inglés (no "Conector").

### Ajustes / About / Updates
**Archivos:** `docs/ux-screenshots/settings.png`, `settings-dark-theme.png`

- Perfil: campos Nombre, Email, Rol con inputs gris claro; CTA "Guardar cambios" coral.
- Notificaciones: toggles "Activado" por fila.
- Conexión Hermes: punto verde "Conectado", botón "Probar conexión".
- Proveedor IA: badges "Config: Local/Hermes/config.yaml", "Ollama OK".
- **Actualizaciones (update-center):**
  - Versión actual: **1.0.2**
  - Canal: stable
  - Origen: Local / personalizado
  - Estado: "✓ VANOVA está actualizado."
  - Botón "Buscar actualizaciones"
  - Historial con versiones anteriores (0.9.13 installing…)
- Tema: toggle "Cambiar a oscuro/claro" — transición a dark mode con fondo #1a1a1a, cards #252525, badges verdes legibles.

### Responsive móvil (390×844)
**Archivos:** `docs/ux-screenshots/mobile-home.png`, `mobile-hermes.png`

- Sidebar oculta; hamburger visible.
- **Problema:** pills del header se solapan — "Cargando panel…" cubre parcialmente "Actualizaciones" / "Hermes".
- Contenido principal apila cards correctamente (ancho completo).
- Hermes en móvil: layout single-column, banner verde + card input + CTA full-width — usable.
- Nav por click en sidebar no funciona fuera de viewport (elemento no estable).

---

## Problemas de interfaz (crítico → bajo)

### Crítico
*Ninguno que impida usar el dashboard con login demo.*

### Alto
1. **Header móvil — solapamiento de badges** (`mobile-home.png`, `mobile-hermes.png`): "Cargando panel…" se superpone a "Actualizaciones" / "Hermes". Rompe legibilidad en viewports estrechos.
2. **Diagnóstico — estado de carga prolongado / parcial** (`diagnostics.png`): pantalla vacía con solo "Cargando diagnóstico…" antes de poblar; si runtime cae, mensaje "Runtime no disponible" con muchos campos "—".

### Medio
3. **Integraciones — variable sin renderizar** (`integrations.png`): `${companyName()}` visible al usuario en tarjetas Excel/CSV y FacturaScript.
4. **Mezcla de idiomas:** saludo "Good afternoon, Pablo" vs UI española; título "Products"; estados de tareas `running`/`failed`; etiqueta "Connector" en diagnóstico.
5. **Drawer Shopify = `prompt()` nativo** (`shopify-drawer-open.png`): rompe la estética del resto del dashboard; no es drawer lateral con botones etiquetados del design system.
6. **Hermes — latencia visible en banner** (~2459 ms): correcto técnicamente pero puede percibirse como lento para usuario no técnico.

### Bajo
7. **Insights / Productos — empty vs populated:** Insights empty state impecable; Productos sin banner Shopify cuando conectado (OK, pero no hay CTA de sync visible en vista).
8. **Tareas — timestamps ISO crudos** (`2026-08-13T21:21:38`) sin formato local amigable.
9. **Settings — texto "Loading update status…"** mezclado con español en carga inicial del update-center (captura settings claro).
10. **Sidebar más items que checklist mínimo** (Actividad, Agentes, Aprobaciones, etc.) — no es bug, pero puede abrumar en onboarding.

---

## Lo que se ve profesional/comercial

- **Design system coherente:** tokens light-first, acento coral, radius consistente, sombras suaves, tipografía sans moderna.
- **Sidebar + header** al nivel de Linear/Notion enterprise — navegación por grupos, search global, status pills.
- **Cards de inicio** con jerarquía clara (atención → ejecución → resultados) y CTAs discretos.
- **Grid de integraciones** con iconografía color, estados Conectado/Pendiente y acciones por tarjeta.
- **Tabla de productos** limpia, paginación, filtros Todas/Recientes, precios en €.
- **Hermes embebido** con empty state guiado, chips de sugerencia, panel operativo colapsable — sensación de producto integrado, no iframe.
- **Update center** con versión, canal, historial y confirmación "VANOVA está actualizado" — listo para GA.
- **Dark mode** completo y legible en Ajustes.
- **Empty states** (Insights, Hermes chat vacío) con icono + copy + acción — no pantallas en blanco.

---

## Comparación Hermes embebido vs expectativa

| Aspecto | Expectativa (standalone CLI/web) | VANOVA embebido 1.0.2 | Valoración |
|---------|----------------------------------|----------------------|------------|
| Bloqueo "Cargando contexto" | No debe bloquear | **Resuelto** — chat usable de inmediato | ✅ |
| Layout chat | Burbujas + input fijo abajo | 2 columnas: input izq + log der | ⚠️ Distinto pero funcional |
| Panel operativo | N/A o secundario | `<details>` colapsable bajo chat | ✅ Buena decisión UX |
| Sesiones | Historial terminal | Card "Sesiones anteriores" al pie | ✅ |
| Adjuntar archivo | Sí | Botón paperclip visible | ✅ |
| Activity lines | Stream de pasos | Clase `.hermes-activity-step` en log | ✅ (vacío hasta interacción) |
| Latencia | Oculta | Mostrada en banner (~2.5s) | ⚠️ |
| Estética | Terminal/minimal | Enterprise coral + cards | ✅ Más comercial |

**Conclusión Hermes:** La queja anterior por bloqueo de contexto **no se reproduce**. La interfaz es más "command center" que "chat app"; aceptable para VANOVA si se mantiene el log reactivo al enviar mensajes.

---

## Recomendaciones diseño priorizadas

1. **P0 — Fix responsive header:** truncar/ocultar pills secundarios en `<768px`; nunca superponer "Cargando panel…" sobre navegación.
2. **P0 — Interpolar `${companyName()}`** en tarjetas Integraciones (bug visible al usuario).
3. **P1 — i18n consistente:** traducir "Good afternoon" → "Buenas tardes"; "Products" → "Productos"; estados tarea → "En ejecución", "Fallida", etc.; "Connector" → "Conector".
4. **P1 — Diagnóstico:** skeleton/spinner en lugar de texto plano "Cargando…"; retry automático si runtime tarda.
5. **P1 — Drawer Shopify:** reemplazar `prompt()` nativo por drawer lateral del design system (campos URL, token, botones Conectar/Desconectar/Sincronizar).
6. **P2 — Hermes mobile:** apilar conversación bajo input; ocultar columna derecha en `<900px`.
7. **P2 — Formato fechas:** `13 ago 2026, 21:21` en lugar de ISO en Tareas y sesiones.
8. **P3 — Ocultar latencia ms** del banner Hermes tras primera carga; mostrar solo "Chat listo".
9. **P3 — Unificar checklist nav** con tooltip "Más opciones" para items secundarios (Actividad, Agentes…).

---

## Anexo técnico

| Item | Valor |
|------|-------|
| Build marker HTML | `VANOVA-UI-BUILD: 20260813o` |
| Tema default | `data-theme="light"` `data-accent="coral"` |
| Login demo | `ceo` / env local |
| Runtime API | `:8765` (estado intermitente en capturas headless) |
| MCP browser | No disponible en esta sesión — ver nota método |

**Índice de capturas:**

```
docs/ux-screenshots/00-login-or-home.png
docs/ux-screenshots/00-sidebar.png
docs/ux-screenshots/home.png
docs/ux-screenshots/insights.png
docs/ux-screenshots/tasks.png
docs/ux-screenshots/hermes.png
docs/ux-screenshots/hermes-full-scroll.png
docs/ux-screenshots/integrations.png
docs/ux-screenshots/integrations-drawer.png
docs/ux-screenshots/shopify-drawer-open.png
docs/ux-screenshots/products.png
docs/ux-screenshots/diagnostics.png
docs/ux-screenshots/diagnostics-loaded.png
docs/ux-screenshots/settings.png
docs/ux-screenshots/settings-dark-theme.png
docs/ux-screenshots/mobile-home.png
docs/ux-screenshots/mobile-hermes.png
```
