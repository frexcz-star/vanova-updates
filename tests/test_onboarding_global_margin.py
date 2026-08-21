"""Regression tests — BUG-037 + margen global (onboarding simplificado).

BUG-037: save_profile sobrescribía el perfil completo; un PATCH parcial (solo
preferences.globalMarginPct) borraba identity/channels. Fix: merge.

Margen global (SPEC STRATI FLUJO COSTES): el empresario declara su margen y
VANOVA estima el coste de SKUs sin coste por unidad (costStatus=estimated,
nunca verified/imported real). Honesto: deriva de un dato declarado por el
usuario, nunca inventado por el sistema.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import company_profile, config_store, opportunity_catalog  # noqa: E402


class CompanyProfileMergeTests(unittest.TestCase):
    """BUG-037: save_profile debe hacer merge con el perfil existente."""

    def test_partial_save_keeps_identity_and_channels(self):
        stored = {
            "companyProfile": {
                "identity": {"name": "MOOVING PAPER", "slug": "mooving"},
                "channels": ["shopify"],
                "preferences": {},
            }
        }
        with patch.object(config_store, "load", return_value=dict(stored)), patch.object(
            config_store, "save", side_effect=lambda d: stored.update(d)
        ):
            partial = company_profile.CompanyProfile.from_dict({"preferences": {"globalMarginPct": 60}})
            company_profile.save_profile(partial)
        saved = stored["companyProfile"]
        self.assertEqual(saved["identity"]["name"], "MOOVING PAPER")  # no se borró
        self.assertEqual(saved["channels"], ["shopify"])  # no se borró
        self.assertEqual(saved["preferences"]["globalMarginPct"], 60)  # sí se añadió


class GlobalMarginTests(unittest.TestCase):
    """Margen global declarado: desbloquea el € sin coste por SKU."""

    def test_global_margin_unblocks_cross_sell(self):
        f = {
            "type": "cross_sell", "category": "opportunity", "status": "new",
            "metrics": {"pair": "a+b", "ordersTogether": 60}, "signature": "cross_sell:gm",
            "title": "Pack A+B", "observation": "x", "recommendedAction": "y",
        }
        prods = [{"sku": "a", "rrp": 100.0}, {"sku": "b", "rrp": 100.0}]
        # Sin margen global -> UNKNOWN (honesto)
        res_none = opportunity_catalog.build_catalog([f], products=prods)
        self.assertIsNone(res_none[0]["upsideEuro"])
        # Con margen global 60% -> estimado 40 -> upside 36 -> calculado
        data = {"companyProfile": {"preferences": {"globalMarginPct": 60}}}
        res = opportunity_catalog.build_catalog([f], products=prods, data=data)
        self.assertIsNotNone(res[0]["upsideEuro"])
        self.assertEqual(res[0]["impactKind"], "calculated")


if __name__ == "__main__":
    unittest.main()
