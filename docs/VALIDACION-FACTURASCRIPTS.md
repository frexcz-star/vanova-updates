# Validación real de FacturaScripts (FASE 9 — P2)

Objetivo: demostrar el flujo **FacturaScripts → API real → VANOVA → modelo
canónico → dashboard → Hermes** con la instancia real, no con mocks.

## Estado actual (verificado 2026-08-16)

- `integrations.json` → `facturascript.connected = False`, desconectado el
  15/08. La URL guardada (`https://facturas.miempresa.com`) es un placeholder.
- **Sin token ni credenciales válidas** → no es posible ejecutar la validación
  real hoy. El código de integración (`facturascripts_sync.py`) y su conector
  (`integration_providers.py`, auth con header `Token` sobre `/api/3`) ya están
  implementados y probados con tests de contrato (15 tests) contra un sandbox.

## Qué necesito para ejecutarla

1. **URL real** de la instalación de FacturaScripts (ej. `https://tu-dominio.com/fs`).
2. **API key / Token** de la instalación (menú FacturaScripts → API → generar
   token, o plugin API REST). La API vive en `/api/3` y autentica con header
   `Token` (NUNCA `X-API-KEY`).
3. Autorización para **escribir en la instalación local** (el sync guarda en
   `%LOCALAPPDATA%/VANOVA/config/maios.json`).

Con esos tres datos: Settings → Integraciones → FacturaScripts → conectar y
sincronizar (o `POST /api/facturascript/sync`).

## Procedimiento de validación (cuando haya credenciales)

1. **Auth**: `GET {url}/api/3/...` con header `Token` → debe responder 200.
2. **Recursos**: sincronizar `clientes`, `proveedores`, `facturascli`,
   `facturasprov`, `lineascli`, `lineasprov`, `cobros`, `pagos` (incremental).
3. **Verificación por capa** — los datos deben ser idénticos en cada paso:
   - API real → JSON crudo (comparar cuenta de filas por recurso).
   - Extracción → validación (`is_error_payload` rechaza cualquier error).
   - Normalización → modelo canónico (`organizedInvoices`, `organizedFinance`,
     `organizedInvoiceLines`, `organizedSuppliers`).
   - Dashboard → `/api/finance/overview` (solo renderiza, nunca recalcula).
   - Hermes → `get_invoices`, `get_treasury`, `get_suppliers` y el contexto
     financiero (mismos números).
4. **Reconciliación**: `POST /api/finance/reconcile` → Σ líneas ≈ neto factura,
   Σ facturas emitidas vs Σ ventas del período. Discrepancias se registran con
   severidad, nunca se corrigen.
5. **Idempotencia**: ejecutar la sync 2 veces → mismo resultado, sin duplicados.
6. **Fallos**: desconectar el servicio a mitad → la sync guarda `partial`,
   conserva los datos previos y no contamina recursos sanos.

## Cómo validar yo (agente) sin credenciales

- Tests de contrato con sandbox: `tests/test_facturascripts_sync.py` (15 tests)
  y `tests/test_business_model.py` (validación, reconciliación, tesorería).
- Prueba de humo del pipeline completo con mocks: ver P4/P9 (simulación del
  backfill + detección con forma de datos reales).
- En cuanto existan credenciales reales y autorización, ejecutar el
  procedimiento anterior y registrar el resultado en la bitácora.
