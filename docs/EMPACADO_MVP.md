# EMPAQUETADO MVP — VANOVA para un empresario no-técnico

**Meta:** un empresario (sin Python, sin Node, sin saber qué es Hermes) instala
VANOVA en su PC y en pocos minutos ve el € de su negocio.

**Estado (actualizado 2026-08-21):** el empaquetado Electron está completo y
publicado (v3.1.1). El wizard está en **ESPAÑOL** (traducción completada y
verificada dentro del instalador empaquetado). Lo que queda documentado y
verificado abajo es el flujo de instalación en un PC "stock".

---

## 1. Estado actual del empaquetado (verificado)

| Pieza | Qué hace | Estado (2026-08-21) |
|---|---|---|
| **Instalador Electron** (`desktop/`, `scripts/release.ps1`) | Genera `VANOVA-Setup-X.exe` auto-contenido + `latest.json` | ✅ Listo — `VANOVA-Setup-3.1.1.exe` (107.5 MB) publicado, `latest.json` apunta a 3.1.1 con sha256 correcto |
| **python-bundle** (`desktop/python-bundle/`) | CPython standalone completo (python.exe, python311.dll, Lib, DLLs) SIN venv ni rutas de build | ✅ Listo — verificado presente en release/win-unpacked y en la instalación real (`resources/vanova/python-bundle/python.exe`) |
| **Runtime local** (`desktop/runtime/`) | FastAPI en 127.0.0.1:8765 — arranca solo desde el bundle | ✅ Listo — no depende de Python del sistema |
| **Cloud local** (`cloud/main.py`) | Sirve el dashboard en 127.0.0.1:8000 | ✅ Listo |
| **Wizard de setup** (`desktop/ui/setup.js`) | 9 pasos: análisis → empresa → canales → objetivos → IA → instalación → agentes → listo | ✅ **ESPAÑOL** (traducción verificada: 8 coincidencias ES, 0 EN dentro del app.asar de la build 3.1.1). Va empaquetado en `app.asar` (bundle Electron). |
| **Updater** (`desktop/updater/`) | Actualizaciones automáticas desde manifest | ✅ Listo — manifest 3.1.1 público, updater detecta la versión |
| **Hermes por detrás** | VANOVA lo instala/arranca automáticamente (`hermes_service.py`) — el empresario NO lo ve | ✅ Listo (Ollama launch o standalone) |

**El empresario NO necesita saber** de Python (embebido), Node (solo build),
ni Hermes (VANOVA lo gestiona por detrás; experiencia 100% VANOVA).

---

## 2. Verificación end-to-end en PC "stock" (documentado)

**Honestidad:** NO se ha podido ejecutar en una VM real — esta máquina de
desarrollo no tiene VirtualBox ni Hyper-V instalados. Los pasos siguientes son
el **plan de verificación** que debe ejecutarse en un entorno limpio. No se
reporta ningún resultado de prueba que no se haya hecho.

### Precondiciones del entorno "stock" (a confirmar antes de probar)
- [ ] Windows 10/11 sin Python en PATH, sin Node, sin Hermes.
- [ ] El `.exe` descargado solo (no hace falta nada más).

### Pasos de verificación y resultado esperado

1. **Instalar**
   - Acción: doble clic en `VANOVA-Setup-3.1.1.exe`, siguiente → instalar.
   - Esperado: se instala en `AppData/Local/Programs/VANOVA`, sin terminales
     ni instalación de Python/Hermes visibles. Aparece el wizard.

2. **Primer arranque — wizard en español**
   - Esperado: pantalla "Bienvenido", pregunta "¿Cómo se llama tu empresa?",
     pasos de canales/objetivos/IA/agentes, todo en español, sin jerga técnica.

3. **Conectar datos — importación guiada**
   - Esperado: el asistente guía conectar Shopify (o subir Excel/CSV de
     ventas), e importa productos/pedidos. Verificado el código: el coste de
     los artículos llega al catálogo (BUG-033) y el margen/€ se calcula con
     coste verificado o importado (resolución honesta, nunca UNKNOWN≠0).

4. **Ver el €**
   - Esperado: el dashboard muestra oportunidades reales con su impacto en
     € (cross-sell, margen, clientes en riesgo) y "Qué hacer hoy". Si no hay
     datos/costes suficientes, el dashboard dice "Impacto no cuantificable" /
     empty state honesto — nunca inventa un €.

5. **Hermes por detrás**
   - Esperado: Hermes se instala/arranca automáticamente la primera vez; el
     empresario no lo ve. Si falla (Ollama no disponible), VANOVA continúa
     con los agentes degradados pero sin romper el resto.

### Riesgos / gaps identificados (honesto)
1. **VM no disponible** — no se ha ejecutado el flujo completo en PC "stock".
   Es el último hueco para lanzar con total confianza.
2. **Hermes en PC stock** — el paso de instalación de Hermes/Ollama en un PC
   sin ningún prerequisito es el que más puede fallar (descarga de modelo,
   Ollama). Debe probarse explícitamente.
3. **Dependencia de red la primera vez** — instalar Hermes / conectar Shopify
   requiere internet; si el empresario está offline, el onboarding debe
   degradar con gracia (Excel local funciona sin red).

---

## 4. Primer esbozo: cómo un empresario instala VANOVA en 5 pasos

1. **Descarga** el instalador de la web de VANOVA (solo un archivo `.exe`).
2. **Instala**: doble clic en `VANOVA-Setup.exe` → siguiente, siguiente,
   instalar. No aparece ningún terminal ni instalación de Python/Hermes.
3. **Primer arranque**: un asistente simple (en español) te pregunta:
   - "¿Cómo se llama tu empresa?"
   - "¿Qué vendes?" (canales: tienda online, marketplaces, Excel)
   - "¿Dónde están tus datos?" → conectar Shopify, o importar un Excel.
4. **Conecta tus datos**: elige tu tienda Shopify (o sube tus ventas en
   Excel/CSV) y VANOVA importa productos/pedidos solo.
5. **Ve tu negocio en €**: el dashboard muestra las oportunidades reales con
   su impacto en euros (cross-sell, margen, clientes en riesgo), y "Qué hacer
   hoy" con acciones concretas. Hermes trabaja por detrás, sin que tengas que
   saber que existe.

**Honestidad:** si no hay datos o costes suficientes, el dashboard lo dice
con claridad ("Impacto no cuantificable" / empty state honesto) — nunca
inventa un € que no se pueda calcular.
