# VANOVA — Checklist manual de Experiencia de Usuario (por release)

> Se ejecuta **siempre**, por muy pequeña que sea la release. Complementa al test
> automático (`maios-ux-audit/ux_release_test.py`, que ya valida empaquetado,
> canal de updates y API en vivo). Esto cubre lo que solo se ve con ojos:
> ventanas, botones, iconos, tiempos de carga y flujos de pantalla.

## Cómo usarla

1. Instala el instalador de la release nueva (o actualiza la app) en un equipo de prueba.
2. Recorre cada punto y marca ✅ / ❌. Si algo falla, **NO publicar** hasta corregirlo.
3. Tras la release, guardar el resultado junto al build (ej. `maios-ux-audit/ux-<version>.md`).

---

## A. Arranque e instalación

- [ ] El setup abre la ventana **al instante** (sin pantalla negra >2s).
- [ ] La pantalla "Loading Environment" carga en <60s o muestra error claro con botón **Reintentar** (nunca "Conectando…" infinito).
- [ ] Primer arranque: VANOVA abre en <2 min en un PC normal (sin descargas de pip ni de modelos Ollama locales).
- [ ] El panel principal carga sin errores en consola (F12 → Console, sin rojo).

## B. Home / Actividad

- [ ] El Inicio muestra datos reales (conectado) o un estado claro (sin conexión) — nunca vacío silencioso.
- [ ] Las estrellas fugaces están detrás de la interfaz (no tapan texto ni botones).
- [ ] Los iconos se ven a tamaño normal (nada gigante/roto tipo el reloj amarillo).

## C. Tareas vs Insights

- [ ] **Tareas** solo lista tareas creadas por el usuario (manuales).
- [ ] Las rutinas automáticas de los agentes aparecen en **Insights** con su informe, no en Tareas.
- [ ] La vista Insights muestra rutinas y prioridades; si no hay nada, se ve un estado vacío amigable.

## D. Agentes

- [ ] Cada agente muestra **qué está haciendo ahora** (actividad actual), progreso, próxima rutina y último informe.
- [ ] La info se actualiza en tiempo real (cambia al ejecutarse una rutina).
- [ ] Activar/desactivar un agente responde al instante.

## E. Archivos y escaneo

- [ ] El escaneo solo importa archivos claramente de empresa (no música/fotos/descargas/archivos personales).
- [ ] Los archivos dudosos generan **notificación** → modal con **Aprobar / Rechazar**.
- [ ] Aprobar importa el archivo; Rechazar lo descarta y no reaparece en el siguiente escaneo.

## F. Actualizaciones

- [ ] Ajustes → Centro de actualizaciones → **Buscar actualizaciones** responde (no "Sin conexión" si el canal está vivo).
- [ ] Si hay update: barra de progreso visible, botones Reintentar / Más tarde funcionan.
- [ ] Tras instalar, la app se reinicia sola y queda en la versión nueva.

## G. Regresión rápida (todo lo demás)

- [ ] Aprobaciones, Automatizaciones, Decisiones y Diagnóstico abren sin error.
- [ ] Los botones de notificación (ir a Insights / Decisiones) navegan bien.
- [ ] Modo claro/oscuro funciona.
- [ ] La búsqueda ⌘K responde.
