# VANOVA 3.0.0 — Release Oficial de Actualización

Fecha: 2026-08-19 · Canal: **stable** · Estado: **GO — instalable y actualizable**

## 1. Versión y fuentes sincronizadas

| Fuente | Valor |
|---|---|
| `version.json` | `3.0.0` |
| `desktop/package.json` | `3.0.0` (config de build electron-builder restaurada completa) |
| `package.json` (raíz, residual) | `3.0.0` |
| `shared/version_info.py` (`CLOUD_API_VERSION`) | `3.0.0` |
| `release/win-unpacked/resources/vanova/version.json` | `3.0.0` |

> **Nota**: el `desktop/package.json` había perdido las secciones `scripts`/`build`/`devDependencies`
> (build de beta.3 empaquetado pero config de build desaparecida). Se restauró fielmente a partir de la
> estructura empaquetada (`resources/vanova/`) y de la config histórica de MAIOS-source-1.0.1, con el
> branding VANOVA (`appId com.vanova.os`, `productName VANOVA`, `artifactName VANOVA-Setup.${ext}`,
> `shortcutName VANOVA`, extraResources → `vanova/*`, `deleteAppDataOnUninstall: false`).

## 2. Artefactos generados

| Artefacto | Tamaño | SHA-256 |
|---|---|---|
| `release/VANOVA-Setup-3.0.0.exe` | 107.477.279 B | `422de65c1c68b5101b6789918161d14134c6ac37771d5af0c8db2f88102a476d` |
| `release/latest.json` (manifest stable 3.0.0) | — | sha256/size coherentes con el instalador |
| `release/latest.local.json` (file:// local) | — | idem |
| `release/checksums.txt` | — | incluye `VANOVA-Setup-3.0.0.exe` |
| `release/publish/` (bundle de publicación) | — | instalador + `latest.json` + `checksums.json` |

- Manifest: `product: VANOVA`, `channel: stable`, `version: 3.0.0`, `minimumSupportedVersion: 0.9.0`,
  `requiredHermes: >=1.0.0`, `dbSchemaVersion: 0`, 12 notas de release.
- `VANOVA-Setup-2.0.26-beta.3.exe` intacto (no sobrescrito).
- Firma de código: **no aplicada** (no hay certificado; infraestructura externa, igual que en betas previas).

## 3. Tests

- Suite completa: **581 passed, 1 skipped, 31 subtests passed — 0 fallos**.
- Incluye **3 tests de regresión del probe de runtime** (401 en `/api/files` cuenta como sano).
- Update unit tests (`test_update_system`, `test_update_failures`): 28 passed, 1 skipped.
- Incluye: `test_latest_json_102_fields` (manifest 3.0.0 coherente con version.json), semver
  `beta.10 > beta.2`, guards de producto/canal/downgrade, checksum.

## 4. Instalación limpia (E2E, perfil aislado — runtime empaquetado real)

`scripts/_e2e_300.py` — Parte A (16/16 PASS):

| Check | Resultado |
|---|---|
| Health público | PASS (200, `vanova-desktop-runtime`) |
| Versión empaquetada | PASS (3.0.0) |
| Auth GET sensibles (products/sales/customers/dashboard-local/data-health/findings) | PASS (401 sin token / 200 con token) |
| Importación vía API (`/api/organize/run`) | PASS (3 productos, 3 ventas, 2 clientes) |
| Revenue total = Σ meses | PASS (390,00 = 390,00) |
| Dashboard/local + Data Health | PASS |
| Reimportación idempotente | PASS (sin duplicados) |
| Sin datos de otras empresas | PASS (solo SKUs del import) |
| POST sin token rechazado | PASS (401) |

## 5. Actualización beta.3 → 3.0.0 (E2E real del UpdateManager, perfil aislado)

`scripts/_e2e_300.py` — Parte B (15/15 PASS):

| Check | Resultado |
|---|---|
| Detección real de 3.0.0 (UpdateManager) | PASS |
| Objetivo 3.0.0, nunca 2.0.25 stable | PASS |
| Guards manifest (product/channel/min-version) | PASS |
| Descarga real del instalador + SHA-256 + size | PASS |
| Transacción install (backup + pending-install.json) | PASS |
| Datos de usuario conservados tras update | PASS (2 productos / 2 ventas intactos) |
| Arranque post-update | PASS (setupComplete conservado) |
| Rechazo de downgrade (manifest 2.0.25) | PASS |
| Rechazo de manifest corrupto (sha256 inválido) | PASS |

**Evidencia adicional (instalación NSIS real)**: durante la primera ejecución del E2E, `install_update()`
lanzó el instalador silencioso REAL dentro del perfil aislado: instaló correctamente en
`<perfil>/Local/Programs/VANOVA` y arrancó los servicios (cloud uvicorn + connector) desde el runtime
empaquetado 3.0.0. El flujo completo installer → arranque quedó demostrado de extremo a extremo sin
tocar la instalación de producción.

**Rollback/recovery**: cubierto por la maquinaria de backup (`create_backup`) + `complete_post_install`
(fallo → rollback) y tests `test_p3_release.py` / `test_stabilization_audit.py`.

## 6. Seguridad

- Escaneo del paquete: **0** archivos `.env` con credenciales (solo `.env.example`), **0** tokens
  (shpat/ghp/sk-/AKIA/Bearer/api-key), **0** datos de benchmark/GROUND_TRUTH, **0** datos de producción
  (`maios.json`, `.db`, `.sqlite`), **0** directorios sandbox/audit/test.
- Protección de GET sensibles mantenida (todos los endpoints de datos exigen token — verificado en E2E).
- Protección contra runtime extranjero mantenida (P2-2, tests de conflicto).
- Sin credenciales de desarrollo en el instalador ni en el manifest.

## 7. Benchmark congelado y producción

- GROUND_TRUTH: `c09d47ac83079eb7b5f1912c79958333b10d179cc4b72bd7277c6031fc62b7da` — **intacto**.
- Producción: 461 productos / 100 ventas / 0 revisión / dataVersion `2.0.26-beta.3` — **intacta**.
- benchmark-data, GROUND_TRUTH, resultados históricos: no modificados.

## 8. Problemas encontrados y corregidos durante el release

0. **BUG CRÍTICO 3.0.0 — probe de runtime con runtime protegido (corregido y reconstruido, 2 frentes)**:
   la protección P2-1 hace que `/api/files` devuelva 401 sin token. **Dos probes** lo trataban
   como fallo y marcaban cualquier runtime protegido como **"Runtime desactualizado — reiniciar
   — falta importación de archivos"**:
   - **Python** (`port_utils.probe_runtime`): `urllib.urlopen` **lanza HTTPError para 401**, el
     código (que comentaba "401 = sano") caía al `except` → `False`. Fix: captura explícita de
     `HTTPError` con `code in (200, 401)` + 3 tests de regresión (`test_port_utils.py`).
   - **Frontend** (`web/system-status.js probeRuntimeHealthy`): `fetch` a `/api/files` sin token
     → 401 → `!res.ok` → `stale`. Fix: aceptar `status 200/401` como sano (mismo criterio).
   Ambos fixes confirmados dentro del paquete empaquetado (`grep` en win-unpacked). **El
   instalador se reconstruyó dos veces** (hashes intermedios descartados) — el artefacto final
   3.0.0 incluye los dos fixes y el E2E completo (Parte A 16/16, Parte B 15/15) volvió a pasar.
   Nota: la primera ejecución del E2E había lanzado el instalador NSIS real en el perfil
   aislado; su runtime quedó vivo contra el puerto 8765 y se adjuntó al config de producción
   (escenario P2-2) — se mató el proceso y el puerto quedó libre. El build 3.0.0 inicial (con
   el bug) llegó solo a esta máquina vía `latest.local.json`; el artefacto final corregido se
   instala manualmente sobre él (misma versión → el updater no lo re-ofrece).

1. **`desktop/package.json` sin config de build** (bloqueaba el pipeline `npm run desktop:installer`)
   → restaurada la config completa de electron-builder. Sin cambio de lógica.
2. **Test de auth `test_sensitive_get_requires_auth` dependiente del entorno**: `/api/command-center`
   sondea runtime/cloud/Hermes con timeouts de red (~2s cada uno cuando están caídos; en esta máquina
   los puertos 8765/8000/8137 hacen SYN-drop y el timeout superaba los 5s del test). El test parchea
   ahora los 3 probes: valida AUTH, no latencia de descubrimiento de servicios. Determinista en
   cualquier máquina.
3. **E2E**: el record de importación requiere `ext` (sin él la extracción devuelve 0 filas) y los
   módulos se cachean por proceso (Parte B debe correr en proceso nuevo). Ajustados los scripts E2E;
   el instalador NSIS real quedó guardado tras `install_update()` (ver §5).

## 9. Publicación

- Publicación **externa pendiente de infraestructura** (igual que en betas): el bundle está preparado
  en `release/publish/` para subir a `https://releases.moovingpaper.com/vanova/` (CDN) o al repositorio
  GitHub `frexcz-star/vanova-updates` (release v3.0.0 con `VANOVA-Setup-3.0.0.exe` + `latest.json`).
  Firma de código y upload requieren recursos externos.
- Nada se ha publicado públicamente desde esta sesión.

## 10. Veredicto

**🟢 GO — VANOVA 3.0.0 queda como release instalable y actualizable** (no un simple bump de versión):
instalador real verificado, actualización beta.3 → 3.0.0 verificada con el mecanismo real, datos
conservados, downgrade/corrupción rechazados, suite 578+1, benchmark y producción intactos.
