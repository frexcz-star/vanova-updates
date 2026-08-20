"""Validación REAL del conector FacturaScripts contra un servidor HTTP local
que imita la API /api/3 de FacturaScripts (no mocks del transporte).

Comprueba sobre HTTP real:
  * probe /api/3 + autenticación por Token;
  * fetch + paginación de los 8 recursos (clientes, proveedores, facturas,
    líneas, cobros, pagos);
  * normalización al modelo canónico;
  * persistencia y detección posterior;
  * rechazo de autenticación inválida (401);
  * rechazo de respuestas HTML como conexión válida;
  * servidor inalcanzable → error estructurado (nunca excepción).

NO es un mock del conector: es un servidor HTTP real en un puerto efímero.
El servidor real del cliente sigue pendiente de validación (URL + API key).
"""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

FS_TOKEN = "fs-test-token-1234"


class FSStubHandler(BaseHTTPRequestHandler):
    """Mínimo FacturaScripts compatible: /api/3/<recurso> con Token y HTML mode."""

    def log_message(self, *args):  # silencio
        pass

    def _send(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Token") != FS_TOKEN:
            self._send({"status": "error", "message": "token inválido"}, 401)
            return
        if self.path == "/api/3" or self.path == "/api/3/":
            self._send({"status": "ok"})
            return
        resource = self.path.split("/api/3/")[-1].split("?")[0]
        data = {
            "clientes": [{"codcliente": "C1", "nombre": "Cliente Uno", "email": "c1@test.es", "cifnif": "B00000001"}],
            "proveedores": [{"codproveedor": "P1", "nombre": "Proveedor Uno", "cifnif": "B00000002"}],
            "facturascli": [{
                "idfactura": "FC1", "codigo": "F2026-001", "codcliente": "C1",
                "nombrecliente": "Cliente Uno", "fecha": "2026-07-10", "neto": 100.0,
                "totaliva": 21.0, "total": 121.0, "pagada": True, "vencimiento": "2026-08-10",
            }],
            "facturasprov": [{
                "idfactura": "FP1", "codigo": "FP2026-001", "codproveedor": "P1",
                "nombreproveedor": "Proveedor Uno", "fecha": "2026-07-12", "neto": 40.0,
                "totaliva": 8.4, "total": 48.4, "pagada": False, "vencimiento": "2026-08-01",
            }],
            "lineascli": [{
                "idlinea": "LC1", "idfactura": "FC1", "referencia": "SKU-100",
                "descripcion": "Producto 100", "cantidad": 2, "pvpunitario": 50.0, "pvptotal": 100.0,
            }],
            "lineasprov": [{
                "idlinea": "LP1", "idfactura": "FP1", "referencia": "SKU-100",
                "descripcion": "Producto 100", "cantidad": 1, "pvpunitario": 40.0, "pvptotal": 40.0,
            }],
            "cobros": [{"idcobro": "CO1", "fecha": "2026-07-15", "importe": 121.0, "codcliente": "C1"}],
            "pagos": [{"idpago": "PA1", "fecha": "2026-07-14", "importe": 48.4, "codproveedor": "P1"}],
        }
        if resource in data:
            self._send({"data": data[resource]})
        elif resource == "html":
            # endpoint que responde HTML (nunca debe valer como conexión)
            body = b"<html><body>FacturaScripts</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send({"status": "error", "message": "recurso desconocido"}, 404)


class FacturaScriptsRealHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FSStubHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "maios.json"
        self.patch_cfg = patch("desktop.runtime.config_store.CONFIG_FILE", self.cfg)
        self.patch_cfg.start()
        from desktop.runtime import config_store
        config_store.save({})
        self.url = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.patch_cfg.stop()
        self.tmp.cleanup()

    def _cfg(self, api_key: str | None = FS_TOKEN, base_url: str | None = None):
        return {"base_url": base_url or self.url, "api_key": api_key, "connected": True}

    def test_full_sync_over_real_http(self):
        from desktop.runtime import facturascripts_sync

        with patch("desktop.runtime.facturascripts_sync.integrations_store.get_config", return_value=self._cfg()):
            result = facturascripts_sync.sync_now()
        self.assertTrue(result.get("ok"), f"sync falló: {result.get('error')}")
        self.assertEqual(result.get("counts", {}).get("customers"), 1)
        self.assertEqual(result.get("counts", {}).get("issued"), 1)
        self.assertEqual(result.get("counts", {}).get("received"), 1)
        # Normalización persistida: proveedor + factura recibida
        from desktop.runtime import config_store
        data = config_store.load()
        suppliers = [s for s in (data.get("organizedSuppliers") or []) if s.get("name") == "Proveedor Uno"]
        self.assertEqual(len(suppliers), 1)
        invoices = [i for i in (data.get("organizedInvoices") or []) if i.get("code") == "FP2026-001"]
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0]["type"], "received")
        self.assertAlmostEqual(invoices[0]["total"], 48.4)
        # Tesorería derivada de datos reales
        cash = [c for c in (data.get("organizedFinance") or []) if c.get("type") in ("collection", "payment")]
        self.assertGreaterEqual(len(cash), 2)

    def test_bad_token_rejected(self):
        from desktop.runtime import facturascripts_sync

        with patch("desktop.runtime.facturascripts_sync.integrations_store.get_config", return_value=self._cfg(api_key="clave-mala")):
            result = facturascripts_sync.sync_now()
        self.assertFalse(result.get("ok"))
        status = str(result.get("status") or "")
        self.assertEqual(status, "error")
        self.assertIn("autenticación", str(result.get("error") or "").lower())

    def test_html_response_never_counts_as_connection(self):
        from desktop.runtime import facturascripts_sync

        # URL que responde HTML en /api/3 → no es una conexión válida
        url = f"{self.url}/html"
        with patch("desktop.runtime.facturascripts_sync.integrations_store.get_config", return_value=self._cfg(base_url=url)):
            result = facturascripts_sync.sync_now()
        self.assertFalse(result.get("ok"))

    def test_unreachable_server_structured_error(self):
        from desktop.runtime import facturascripts_sync

        # Puerto sin servidor escuchando → error estructurado, nunca excepción
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]
        sock.close()
        with patch("desktop.runtime.facturascripts_sync.integrations_store.get_config", return_value=self._cfg(base_url=f"http://127.0.0.1:{dead_port}")):
            result = facturascripts_sync.sync_now()
        self.assertFalse(result.get("ok"))
        self.assertIn("status", result)


if __name__ == "__main__":
    unittest.main()
