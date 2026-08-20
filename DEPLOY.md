# VANOVA — Guía de despliegue en el ordenador del dueño (MOOVING PAPER)

Esta guía explica cómo instalar y configurar VANOVA en el ordenador del dueño
(Pablo) para que quede funcionando de extremo a extremo.

---

## Arquitectura (qué se instala dónde)

```
┌─────────────────────────────────────────────────────────────┐
│  ORDENADOR DEL DUEÑO (Pablo)                                 │
│                                                             │
│  VANOVA Cloud (local)  ──sirve la web en 127.0.0.1:8000──▶   │
│        │                                                    │
│  VANOVA Connector  ──conexión local──▶  Cloud               │
│        │                                                    │
│        └──▶ Hermes Agent (local, 127.0.0.1)                 │
│        └──▶ Fuentes reales (Excel, FacturaScript, Drive)    │
└─────────────────────────────────────────────────────────────┘
```

- **VANOVA Cloud**: sirve la web del dashboard. En modo LOCAL corre en el mismo
  PC del dueño (`http://127.0.0.1:8000`). Solo se despliega en internet si el
  dueño quiere acceder desde el móvil u otro dispositivo.
- **VANOVA Connector**: se instala en el PC del dueño. Envía los datos reales
  (Hermes + archivos) al Cloud.
- **Hermes Agent**: corre localmente en el PC del dueño (127.0.0.1). El
  Connector lo usa vía CLI.

---

## ⭐ Opción recomendada: TODO LOCAL (sin internet)

El dueño solo usa VANOVA en su propio PC. No necesita Railway, GitHub ni nada
de internet.

### Instalación (una sola vez)

1. Descomprime el zip en el PC del dueño (ej: `C:\VANOVA`).
2. Abre una terminal en esa carpeta.
3. Ejecuta:
   ```
   python install_all.py
   ```
   Esto crea el entorno, instala dependencias, genera las claves y escribe
   `cloud/.env` y `connector/.env`.

### Arranque (cada vez que quieras usar VANOVA)

1. Doble clic en **`start_all.bat`** (arranca Cloud + Connector juntos).
2. Abre el navegador en **`http://127.0.0.1:8000`**.
3. Login: **`ceo` / `mooving2026`**.

### Configurar Hermes (una vez)

Edita `connector/.env` y pon la ruta al `hermes.exe` del dueño en `HERMES_CLI`:
```
HERMES_CLI=C:\Users\<dueño>\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe
```

---

## Opción B: Cloud en internet (para acceder desde el móvil)

Solo si el dueño quiere entrar desde el móvil u otro dispositivo. El Cloud se
despliega en Railway / Render / Fly.io / VPS.

### Desplegar el Cloud

1. Sube la carpeta `cloud/` a un repo de GitHub.
2. En Railway/Render crea un servicio:
   - **Build**: `pip install -r requirements.txt`
   - **Start**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Env vars**: `MAIOS_CLOUD_SECRET_KEY`, `MAIOS_DEMO_PASSWORD`
3. Obtén la URL pública (ej: `https://maios.up.railway.app`).

### Conectar el Connector al Cloud remoto

En `connector/.env`, cambia:
```
MAIOS_CLOUD_URL=https://maios.up.railway.app
```

---

## Conectar las fuentes reales

Desde el dashboard, en **Integrations**:
- **Excel / CSV**: el Connector escanea automáticamente `Documents`, `Downloads`
  y `Desktop` del PC del dueño.
- **FacturaScript**: introduce la URL y credenciales de la instancia del dueño.
- **Google Drive**: introduce la URL de la carpeta compartida.

---

## Verificación

1. **Cloud**: `http://127.0.0.1:8000/api/health` → `200`.
2. **Connector**: en el log del Connector debe aparecer "Registered device" y
   heartbeats cada 30s.
3. **Dashboard**: debe mostrar `dataMode: real` (badge REAL DATA) cuando el
   Connector pushea datos reales de Hermes.
4. **Hermes**: escribe una pregunta en el dashboard → el Connector la procesa
   vía CLI → aparece la respuesta real.

---

## Seguridad

- El Connector **no abre puertos**; solo conexión saliente al Cloud.
- Los secretos viven SOLO en `.env` (nunca en código ni en git).
- El Cloud usa JWT + bcrypt; CORS restringible.
- Audit log de todas las acciones importantes.
- **Guardrails**: las acciones destructivas de los agentes requieren
  aprobación humana (menú Aprobaciones).

---

## Solución de problemas

| Problema | Causa probable | Solución |
|----------|----------------|----------|
| Connector no conecta | `MAIOS_DEVICE_KEY` no registrado | Regístralo en Settings → Devices |
| Dashboard en DEV SAMPLE | Hermes no corre en el PC del dueño | Arranca Hermes CLI |
| Cloud no sirve el dashboard | `MAIOS_STATIC_DIR` mal | Apunta a `web/dist/` |
| FacturaScript no conecta | URL/credenciales incorrectas | Revisa en Integrations |

