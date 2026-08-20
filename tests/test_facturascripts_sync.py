"""FASE 4 — tests de la integración profunda de FacturaScripts.

Cubre: parsing defensivo, normalización al modelo canónico, errores que NUNCA
se convierten en entidades, retries con backoff, protección contra datos
parciales, idempotencia/dedupe, fusión de clientes y tesorería.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from desktop.runtime import business_model, facturascripts_sync as fs


class _FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"content-type": "application/json" if isinstance(payload, (dict, list)) else "text/html"}

    @property
    def text(self):
        return self._payload if isinstance(self._payload, str) else ""

    def json(self):
        if not isinstance(self._payload, (dict, list)):
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    """Deterministic fake httpx client for sync_now end-to-end tests."""

    def __init__(self, routes: dict[str, object], fail: set[str] | None = None, retries: dict[str, int] | None = None):
        self.routes = routes
        self.fail = fail or set()
        self.retries = retries or {}
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        self.calls.append((url, params or {}))
        if any(tag in url for tag in self.fail):
            raise httpx.ConnectError("red caída", request=None)
        # Retry simulation: fail N times with 503 then succeed.
        for tag, n in self.retries.items():
            if tag in url:
                already = sum(1 for u, _ in self.calls if tag in u)
                if already <= n:
                    return _FakeResponse(503, None)
        # Match by final path segment: probe ".../api/3" vs ".../api/3/cobros".
        norm_url = url.rstrip("/")
        for tag, payload in self.routes.items():
            norm = tag.rstrip("/")
            if norm_url.endswith("/" + norm) or norm_url == norm:
                if isinstance(payload, Exception):
                    raise payload
                return _FakeResponse(200, payload)
        return _FakeResponse(404, None)

    def close(self):
        self.closed = True


def _cfg(**overrides):
    cfg = {"base_url": "https://erp.example.com", "api_key": "k-123", "connected": True}
    cfg.update(overrides)
    return cfg


def _full_payloads():
    return {
        "api/3/": {"status": "success"},
        "clientes": {"data": [{"codcliente": "C1", "nombre": "Acme SA", "email": "acme@test.es", "cifnif": "B123"}]},
        "proveedores": {"data": [{"codproveedor": "P1", "nombre": "Papelera SL", "cifnif": "A999"}]},
        "facturascli": {
            "data": [
                {
                    "idfactura": 101,
                    "codigo": "F2026-001",
                    "fecha": "2026-07-01",
                    "codcliente": "C1",
                    "nombrecliente": "Acme SA",
                    "neto": "100.00",
                    "totaliva": "21.00",
                    "total": "121.00",
                    "pagada": False,
                    "vencimiento": "2026-08-30",
                }
            ]
        },
        "facturasprov": {"data": [{"idfactura": 7, "codigo": "FP-7", "fecha": "2026-06-15", "total": "55.00", "pagada": True}]},
        "lineascli": {"data": [{"idlinea": 1, "idfactura": 101, "referencia": "AG1", "descripcion": "Agenda", "cantidad": 2, "pvpunitario": "50.00", "dtopor": 0, "iva": 21, "pvptotal": "100.00"}]},
        "lineasprov": {"data": [{"idlinea": 1, "idfactura": 7, "referencia": "PAP", "descripcion": "Papel", "cantidad": 1, "pvpunitario": "55.00", "dtopor": 0, "iva": 21, "pvptotal": "55.00"}]},
        "cobros": {"data": [{"idcobro": 1, "fecha": "2026-07-10", "importe": "121.00", "codcliente": "C1", "codigo": "F2026-001"}]},
        "pagos": {"data": [{"idpago": 2, "fecha": "2026-06-20", "importe": "55.00", "codproveedor": "P1"}]},
    }


class ExtractTests(unittest.TestCase):
    def test_defensive_payload_parsing(self):
        self.assertEqual(len(fs._extract_rows([{"a": 1}])), 1)
        self.assertEqual(len(fs._extract_rows({"data": [{"a": 1}]})), 1)
        self.assertEqual(len(fs._extract_rows({"items": [{"a": 1}]})), 1)
        self.assertIsNone(fs._extract_rows({"status": "error", "message": "API key inválida"}))
        self.assertIsNone(fs._extract_rows("no soy json"))
        self.assertIsNone(fs._extract_rows({"detail": "not found"}))


class NormalizationTests(unittest.TestCase):
    def test_invoice_normalized_to_canonical(self):
        raw = _full_payloads()["facturascli"]["data"][0]
        inv = fs._normalize_invoice(raw, "issued")
        self.assertEqual(inv["type"], "issued")
        self.assertEqual(inv["id"], "101")
        self.assertEqual(inv["code"], "F2026-001")
        self.assertEqual(inv["total"], 121.0)
        self.assertEqual(inv["net"], 100.0)
        self.assertEqual(inv["paid"], False)
        self.assertEqual(inv["dueDate"], "2026-08-30")
        self.assertTrue(business_model.validate_invoice(inv)[0])

    def test_cash_normalized(self):
        raw = _full_payloads()["cobros"]["data"][0]
        cash = fs._normalize_cash(raw, "collection")
        self.assertEqual(cash["type"], "collection")
        self.assertEqual(cash["amount"], 121.0)
        self.assertTrue(business_model.validate_cash_row(cash)[0])


class PersistTests(unittest.TestCase):
    def test_error_payload_never_becomes_entity(self):
        stored: dict = {}
        with patch.object(fs.config_store, "save", side_effect=lambda d: stored.update(d)):
            fs._persist(
                "invoice",
                [{"id": "9", "code": "E1", "type": "issued", "total": "faltan permisos"}],
                source="facturascript",
            )
        self.assertEqual(stored.get("organizedInvoices"), [])

    def test_persist_dedupes_by_id(self):
        stored: dict = {}
        dup = {"id": "101", "code": "F1", "type": "issued", "total": 121.0, "date": "2026-01-01"}
        with patch.object(fs.config_store, "save", side_effect=lambda d: stored.update(d)):
            fs._persist("invoice", [dup, dict(dup)], source="facturascript")
        self.assertEqual(len(stored["organizedInvoices"]), 1)

    def test_customer_merge_keeps_existing(self):
        stored = {"organizedCustomers": [{"name": "Acme SA", "email": "acme@test.es", "taxId": "B123"}]}
        with patch.object(fs.config_store, "load", return_value=stored), patch.object(
            fs.config_store, "save", side_effect=lambda d: stored.update(d)
        ):
            fs._merge_customers([
                {"name": "Acme SA", "email": "acme@test.es", "taxId": "B123"},  # already exists
                {"name": "Nueva SL", "email": "nueva@test.es"},
            ])
        self.assertEqual(len(stored["organizedCustomers"]), 2)


class DedupeCollisionTests(unittest.TestCase):
    def test_issued_and_received_same_id_both_kept(self):
        """H15: idfactura es una secuencia independiente por tabla — issued id=1
        y received id=1 no deben colisionar al deduplicar."""
        stored: dict = {}
        issued = {"id": "1", "code": "F1", "type": "issued", "total": 100.0, "date": "2026-01-01"}
        received = {"id": "1", "code": "FP1", "type": "received", "total": 50.0, "date": "2026-01-02"}
        with patch.object(fs.config_store, "load", side_effect=lambda: dict(stored)), patch.object(
            fs.config_store, "save", side_effect=lambda d: stored.update(d)
        ):
            fs._persist("invoice", [issued], source="facturascript")
            fs._persist("invoice", [received], source="facturascript")
        self.assertEqual(len(stored["organizedInvoices"]), 2)
        types = {i["type"] for i in stored["organizedInvoices"]}
        self.assertEqual(types, {"issued", "received"})

    def test_line_ids_prefixed_by_type(self):
        stored: dict = {}
        cli = {"id": "issued:1", "invoiceId": "1", "invoiceType": "issued", "quantity": 1.0, "lineTotal": 10.0}
        prov = {"id": "received:1", "invoiceId": "1", "invoiceType": "received", "quantity": 1.0, "lineTotal": 5.0}
        with patch.object(fs.config_store, "load", side_effect=lambda: dict(stored)), patch.object(
            fs.config_store, "save", side_effect=lambda d: stored.update(d)
        ):
            fs._persist("line", [cli], source="facturascript")
            fs._persist("line", [prov], source="facturascript")
        self.assertEqual(len(stored["organizedInvoiceLines"]), 2)


class RequestTests(unittest.TestCase):
    def test_retry_on_transient_error(self):
        class Flaky:
            def __init__(self):
                self.n = 0

            def get(self, url, params=None, headers=None):
                self.n += 1
                if self.n < 3:
                    raise httpx.TimeoutException("t", request=None)
                return _FakeResponse(200, {"data": [{"a": 1}]})

        with patch.object(fs.time, "sleep", return_value=None):
            payload, error = fs._request(Flaky(), "http://x/api/3/facturascli", "k", {})
        self.assertIsNone(error)
        self.assertEqual(payload["data"], [{"a": 1}])

    def test_auth_error_no_retry(self):
        client = _FakeClient({}, fail=set())
        payload, error = fs._request(_AuthClient(), "http://x/api/3/", "k", {})
        self.assertIsNone(payload)
        self.assertIn("401", error or "")


class _AuthClient:
    def get(self, url, params=None, headers=None):
        return _FakeResponse(401, {"status": "error"})


class SyncPipelineTests(unittest.TestCase):
    def _run(self, client, stored=None):
        stored = stored or {}
        with patch.object(fs.integrations_store, "get_config", return_value=_cfg()), patch.object(
            fs.config_store, "load", side_effect=lambda: dict(stored)
        ), patch.object(fs.config_store, "save", side_effect=lambda d: stored.update(d)), patch.object(
            fs.httpx, "Client", return_value=client
        ), patch.object(fs.time, "sleep", return_value=None):
            result = fs.sync_now()
        return result, stored

    def test_full_sync_ok(self):
        client = _FakeClient(_full_payloads())
        result, stored = self._run(client)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(stored["organizedInvoices"]), 2)  # issued + received
        self.assertEqual(len(stored["organizedFinance"]), 2)  # cobro + pago
        self.assertEqual(len(stored["organizedInvoiceLines"]), 2)  # cli + prov
        self.assertEqual(len(stored["organizedCustomers"]), 1)
        self.assertEqual(len(stored["organizedSuppliers"]), 1)
        state = stored["facturascriptSync"]
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["dataMode"], "real")
        self.assertEqual(state["counts"]["invoices"], 2)
        self.assertEqual(state["counts"]["lines"], 2)
        self.assertIsNotNone(state["lastSync"])

    def test_partial_failure_keeps_existing_data(self):
        client = _FakeClient(_full_payloads(), fail={"cobros"})
        stored = {
            # Previously synced treasury — must survive a failed cobros fetch
            "organizedFinance": [
                {"id": "9", "type": "collection", "amount": 999.0, "date": "2026-05-01", "_source": "facturascript"}
            ]
        }
        result, stored = self._run(client, stored)
        self.assertEqual(result["status"], "partial")
        self.assertIn("red caída", result["resourceErrors"]["cobros"])
        # The failed resource keeps its previous data (no wipe, no contamination)
        amounts = [f["amount"] for f in stored["organizedFinance"] if f.get("type") == "collection"]
        self.assertEqual(amounts, [999.0])
        # The successful resources were synced (pagos merged alongside cobros)
        self.assertEqual(len(stored["organizedFinance"]), 2)
        self.assertEqual(len(stored["organizedInvoices"]), 2)

    def test_all_resources_fail_touches_nothing(self):
        client = _FakeClient(
            _full_payloads(),
            fail={"facturascli", "facturasprov", "lineascli", "lineasprov", "cobros", "pagos", "clientes", "proveedores"},
        )
        stored = {"organizedInvoices": [{"id": "old", "code": "OLD", "type": "issued", "total": 5.0, "date": "2026-01-01"}]}
        result, stored = self._run(client, stored)
        self.assertEqual(result["status"], "error")
        self.assertEqual(len(stored["organizedInvoices"]), 1)  # untouched

    def test_error_payload_from_api_never_stored(self):
        payloads = dict(_full_payloads())
        payloads["facturascli"] = {"status": "error", "message": "acceso denegado al recurso"}
        client = _FakeClient(payloads)
        result, stored = self._run(client)
        # facturascli fails → resource error; no invoices from it. facturasprov ok.
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(stored["organizedInvoices"]), 1)  # only received
        self.assertTrue(all(business_model.validate_invoice(i)[0] for i in stored["organizedInvoices"]))


class TreasuryTests(unittest.TestCase):
    def test_treasury_unavailable_when_no_data(self):
        with patch.object(fs.config_store, "load", return_value={"organizedInvoices": [], "organizedFinance": []}):
            t = fs.treasury_summary()
        self.assertFalse(t["available"])

    def test_treasury_sums_and_pending(self):
        data = {
            "organizedFinance": [
                {"id": "1", "type": "collection", "amount": 121.0},
                {"id": "2", "type": "payment", "amount": 55.0},
            ],
            "organizedInvoices": [
                {"id": "101", "type": "issued", "total": 121.0, "paid": False, "dueDate": "2099-01-01"},
                {"id": "102", "type": "issued", "total": 50.0, "paid": True},
                {"id": "7", "type": "received", "total": 55.0, "paid": False},
            ],
        }
        with patch.object(fs.config_store, "load", return_value=data):
            t = fs.treasury_summary()
        self.assertTrue(t["available"])
        m = t["metrics"]
        # REAL — from FacturaScripts
        self.assertEqual(m["collections"]["value"], 121.0)
        self.assertEqual(m["collections"]["category"], "real")
        self.assertEqual(m["payments"]["value"], 55.0)
        # CALCULADO — derived, tagged
        self.assertEqual(m["netCashMovement"]["value"], 66.0)
        self.assertEqual(m["netCashMovement"]["category"], "calculated")
        self.assertEqual(m["pendingCollections"]["value"], 121.0)
        self.assertEqual(m["pendingCollections"]["count"], 1)
        self.assertEqual(m["pendingPayments"]["value"], 55.0)
        # NO DISPONIBLE — explicit, never mixed
        self.assertEqual(m["bankBalance"]["category"], "not_available")
        self.assertIn("no tiene integración bancaria", m["bankBalance"]["reason"])


class StatusTests(unittest.TestCase):
    def test_status_reflects_configuration(self):
        with patch.object(fs.integrations_store, "get_config", return_value={}), patch.object(
            fs.config_store, "load", return_value={}
        ):
            st = fs.sync_status()
        self.assertFalse(st["configured"])
        self.assertEqual(st["status"], "not_configured")


class UrlNormalizationTests(unittest.TestCase):
    """Regression: users paste the API URL (with /api/3) from the official docs.
    The connector must not append /api/3 twice (bug reportado por el tester)."""

    def test_bare_host_unchanged(self):
        self.assertEqual(fs.normalize_fs_base_url("https://erp.example.com"), "https://erp.example.com")

    def test_host_with_trailing_slash(self):
        self.assertEqual(fs.normalize_fs_base_url("https://erp.example.com/"), "https://erp.example.com")

    def test_api3_suffix_stripped(self):
        # Official docs instruct users to use {instalación}/api/3 — stripping
        # avoids the double /api/3/api/3/ 404 that blocked the tester.
        self.assertEqual(fs.normalize_fs_base_url("https://erp.example.com/api/3"), "https://erp.example.com")
        self.assertEqual(fs.normalize_fs_base_url("https://erp.example.com/api/3/"), "https://erp.example.com")

    def test_api_suffix_stripped(self):
        self.assertEqual(fs.normalize_fs_base_url("https://erp.example.com/api"), "https://erp.example.com")

    def test_subpath_install_kept(self):
        # Instalaciones en subdirectorio: /facturascripts/api/3 → /facturascripts
        self.assertEqual(
            fs.normalize_fs_base_url("https://host.com/facturascripts/api/3"), "https://host.com/facturascripts"
        )

    def test_no_scheme_gets_https(self):
        self.assertEqual(fs.normalize_fs_base_url("erp.example.com/api/3"), "https://erp.example.com")

    def test_empty_returns_empty(self):
        self.assertEqual(fs.normalize_fs_base_url(""), "")

    def test_sync_now_probes_both_api3_variants(self):
        """sync_now must reach the API when the stored URL is bare or with /api/3."""
        self.assertIn("/api/3", fs.FS_PROBE_PATHS)
        self.assertIn("/api/3/", fs.FS_PROBE_PATHS)

    def test_full_sync_ok_with_api3_url_stored(self):
        """End-to-end: if the stored base_url already ends in /api/3, sync still
        works (previously it built /api/3/api/3/ → 404 → 'no se pudo conectar')."""
        client = _FakeClient(_full_payloads())
        stored: dict = {}
        with patch.object(fs.integrations_store, "get_config", return_value=_cfg(base_url="https://erp.example.com/api/3")), patch.object(
            fs.config_store, "load", side_effect=lambda: dict(stored)
        ), patch.object(fs.config_store, "save", side_effect=lambda d: stored.update(d)), patch.object(
            fs.httpx, "Client", return_value=client
        ), patch.object(fs.time, "sleep", return_value=None):
            result = fs.sync_now()
        self.assertTrue(result["ok"], result)
        # The probe and resource URLs must not contain a duplicated /api/3 segment.
        probed = [u for u, _ in client.calls]
        self.assertFalse(any("/api/3/api/3" in u for u in probed))
        self.assertTrue(any(u.rstrip("/").endswith("/api/3") for u in probed))


class ProviderConnectionTests(unittest.TestCase):
    """test_connection (integration_providers) must not accept HTML as connected."""

    def test_html_homepage_is_not_accepted(self):
        from desktop.runtime import integration_providers as ip

        hits: list[str] = []

        class _HTMLClient:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, headers=None, **kw):
                hits.append(url)
                return _FakeResponse(200, "<!DOCTYPE html><html>homepage</html>")

        with patch.object(ip.httpx, "Client", return_value=_HTMLClient()):
            res = ip.connect_facturascript({"base_url": "https://alige360.example.com", "api_key": "k"})
        self.assertFalse(res["ok"])
        self.assertIn("No se encontró una API válida", res["error"])

    def test_json_api_accepted_and_url_normalized(self):
        from desktop.runtime import integration_providers as ip

        hits: list[str] = []

        class _JSONClient:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, headers=None, **kw):
                hits.append(url)
                return _FakeResponse(200, {"status": "success", "resources": ["clientes"]})

        with patch.object(ip.httpx, "Client", return_value=_JSONClient()):
            res = ip.connect_facturascript({"base_url": "https://erp.example.com/api/3", "api_key": "k"})
        self.assertTrue(res["ok"])
        # URL was normalized: /api/3 stripped before probing, so the probe is /api/3 once.
        self.assertTrue(any(h.rstrip("/").endswith("/api/3") for h in hits))
        self.assertFalse(any("/api/3/api/3" in h for h in hits))


if __name__ == "__main__":
    unittest.main()
