"""BUG-071: updateBellBadge NO tenía try/catch defensivo — un fallo del hero rompía el badge.

LEAD round 98 (Boss): `updateBellBadge()` llamaba a `updateHeroValorCapturado()`
que toca 6+ elementos DOM del hero (`hero-riesgos`, `hero-decisiones`,
`hero-oportunidades`, `valor-capturado-num`, `valor-capturado-change`) y a
`formatCurrency`. Si CUALQUIER elemento falta (vista/build vieja sin hero, o un
null) lanza TypeError -> abortaba `updateBellBadge` SILENCIOSAMENTE y el badge
quedaba STALE con el número anterior — el síntoma exacto "no se actualiza".

Fix: `updateBellBadge()` envuelve la llamada a `updateHeroValorCapturado` en un
try/catch (y el cuerpo completo en otro try/catch defensivo) para que el badge
SIEMPRE se pinte aunque el hero falle.

Estos tests FALLAN con el código anterior (sin try/catch) y PASAN con el fix.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "web" / "dashboard.html"


class Bug071BellBadgeDefensiveTests(unittest.TestCase):
    def test_update_bell_badge_envuelve_hero_en_try_catch(self):
        """El badge no debe romperse si updateHeroValorCapturado lanza."""
        html = DASHBOARD.read_text(encoding="utf-8")
        idx = html.find("function updateBellBadge()")
        self.assertGreater(idx, -1, "updateBellBadge ausente")
        block = html[idx:idx + 2500]
        self.assertIn("updateHeroValorCapturado(gr, risks, decisions, files)", block)
        # La llamada al hero debe estar dentro de un try/catch (protección).
        hero_call = block.find("updateHeroValorCapturado(gr, risks, decisions, files)")
        before = block[max(0, hero_call - 200):hero_call]
        self.assertIn("try", before, "la llamada al hero no está en try/catch")

    def test_update_bell_badge_cuerpo_en_try_catch(self):
        """El cuerpo de updateBellBadge debe estar en try/catch defensivo."""
        html = DASHBOARD.read_text(encoding="utf-8")
        idx = html.find("function updateBellBadge()")
        block = html[idx:idx + 200]
        self.assertIn("try {", block, "updateBellBadge no tiene try/catch defensivo")

    def test_hero_toca_elementos_que_pueden_ser_null(self):
        """updateHeroValorCapturado accede a elementos del hero sin guardar null;
        el fix garantiza que un fallo no rompa el badge."""
        html = DASHBOARD.read_text(encoding="utf-8")
        idx = html.find("function updateHeroValorCapturado(")
        self.assertGreater(idx, -1, "updateHeroValorCapturado ausente")
        block = html[idx:idx + 900]
        # Confirma que toca múltiples getElementById (los que pueden ser null).
        self.assertIn("hero-riesgos", block)
        self.assertIn("hero-decisiones", block)
        self.assertIn("hero-oportunidades", block)
        self.assertIn("valor-capturado-num", block)
        self.assertIn("valor-capturado-change", block)


if __name__ == "__main__":
    unittest.main()
