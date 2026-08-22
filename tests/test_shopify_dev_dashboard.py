"""Dev Dashboard (client credentials) Shopify token support.

Shopify deprecó los Custom Apps del admin: el Admin API token `shpat_` ya no se
puede obtener hoy desde la UI. En el Dev Dashboard el usuario ve Client ID +
Client Secret (`shpss_`). El Client Secret NO vale como `X-Shopify-Access-Token`
(da 401); hay que canjearlo por un access token real vía client credentials
grant (POST /admin/oauth/access_token).

Regresion: VANOVA debe aceptar `shpss_` + Client ID, canjearlo por un access
token real y usarlo en las llamadas a la Admin API. Sin romper el soporte
existente de `shpat_` directo.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import shopify_sync

URL = "https://demo.myshopify.com"
CLIENT_ID = "abc123clientid"
CLIENT_SECRET = "shpss_abcdef1234567890"
ACCESS_TOKEN = "shpat_resolved_access_token"


class DevDashboardClientCredentialsTests(unittest.TestCase):
    def setUp(self):
        # Limpiar el cache de estado de modulo entre tests (evita interferencia).
        shopify_sync._CC_CACHE.clear()

    def test_shpat_used_directly(self):
        """shpat_* es un token de Admin valido -> uso directo (no se canjea)."""
        self.assertEqual(shopify_sync.resolve_admin_token(URL, "shpat_sometoken"), "shpat_sometoken")

    def test_shpss_requires_client_id(self):
        """shpss_ (Client Secret) sin Client ID -> error claro (no inventa)."""
        with patch.object(shopify_sync.integrations_store, "get_shopify_entry", return_value={}):
            with self.assertRaises(RuntimeError):
                shopify_sync.resolve_admin_token(URL, CLIENT_SECRET)

    def test_shpss_exchanges_for_access_token(self):
        """shpss_ + client_id -> canje client credentials -> access token real."""
        with patch.object(shopify_sync.integrations_store, "get_shopify_entry",
                          return_value={"api_key": CLIENT_ID}), \
             patch.object(shopify_sync, "_exchange_client_credentials", return_value=ACCESS_TOKEN) as ex:
            resolved = shopify_sync.resolve_admin_token(URL, CLIENT_SECRET)
        self.assertEqual(resolved, ACCESS_TOKEN)
        ex.assert_called_once_with(URL, CLIENT_ID, CLIENT_SECRET)

    def test_shpss_cache(self):
        """El access token canjeado se cachea (no se re-canjea en cada llamada)."""
        with patch.object(shopify_sync.integrations_store, "get_shopify_entry",
                          return_value={"api_key": CLIENT_ID}), \
             patch.object(shopify_sync, "_exchange_client_credentials", return_value=ACCESS_TOKEN) as ex:
            shopify_sync.resolve_admin_token(URL, CLIENT_SECRET)
            shopify_sync.resolve_admin_token(URL, CLIENT_SECRET)
        self.assertEqual(ex.call_count, 1)

    def test_failed_exchange_raises(self):
        """Si el canje falla -> RuntimeError (no devuelve un token invalido)."""
        with patch.object(shopify_sync.integrations_store, "get_shopify_entry",
                          return_value={"api_key": CLIENT_ID}), \
             patch.object(shopify_sync, "_exchange_client_credentials", return_value=None):
            with self.assertRaises(RuntimeError):
                shopify_sync.resolve_admin_token(URL, CLIENT_SECRET)


if __name__ == "__main__":
    unittest.main()
