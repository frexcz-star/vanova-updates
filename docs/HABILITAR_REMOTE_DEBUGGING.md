# Habilitar remote debugging de Chrome para pruebas de UI real (Mathew QA)

Mathew necesita leer el DOM real del dashboard VANOVA para completar las pruebas
de UI (contador badge==drawer, hero Valor Capturado, navegación). Para ello debe
habilitarse el **remote debugging de Chrome**. Es un permiso MANUAL del navegador
que NO puede aprobar ningún agente — requiere que el usuario (Nico) o boss lo
habilite una sola vez.

## Pasos exactos (para Nico/boss)

### Opción 1 — Chrome con flag --remote-debugging-port (recomendada)
1. Cierra todas las ventanas de Chrome.
2. Lanza Chrome con el flag de remote debugging:
   - Windows (PowerShell o cmd):
     ```
     "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\chrome-debug
     ```
   - El `--user-data-dir` es importante: usa un perfil separado para no mezclar
     con tu sesión real de Chrome.
3. Verifica que está activo abriendo `http://127.0.0.1:9222/json` en el navegador
   → debe devolver un JSON con las pestañas/tabs.
4. Abre el dashboard VANOVA en esa instancia de Chrome (`http://127.0.0.1:8000`).
5. Listo: Mathew podrá conectarse vía CDP y leer el DOM real.

### Opción 2 — chrome://inspect (manual)
1. Abre Chrome → navega a `chrome://inspect`.
2. En "Devices" asegúrate de que "Discover network targets" / "Allow remote
   debugging" esté activado (clic en el checkbox/botón).
3. En "Remote debugging" clic en **"Allow remote debugging"** cuando aparezca.
4. Abre el dashboard VANOVA y confirma que la pestaña aparece en chrome://inspect.

## Qué hace falta para el agente
- Que Chrome esté corriendo con `--remote-debugging-port=9222` (o el port que se
  elija).
- Que el agente (Mathew) pueda conectarse al endpoint CDP `http://127.0.0.1:9222`.
- Si se usa `--user-data-dir`, el port y la ruta del perfil deben pasarse a Mathew.

## Alternativa (si no se aprueba remote debugging)
- `computer_use` con `focus_app` en la ventana VANOVA (captura la ventana). Esto
  también requiere aprobación de permisos y NO permite leer el DOM directamente,
  solo hacer screenshots y clics por coordenadas.

## Nota de seguridad
- El remote debugging expone el navegador a conexiones locales. Usar solo en
  localhost y cerrar el port al terminar las pruebas.
- No compartir el port fuera de la máquina local.
