"""BUG-066 (MEDIUM, reproducible 5/5): el saludo del dashboard renderiza emoji 👋
y está en inglés ("Good afternoon") en vez de español.

Root cause: la función `greeting()` (dashboard.html) devolvía 'Good morning'/
'Good afternoon'/'Good evening' (inglés), contradiciendo la regla de UI en
español y el rediseño Paso 3 (cero emojis).

Fix: `greeting()` ahora devuelve saludo en español según la hora (Buenos días
06-12, Buenas tardes 12-20, Buenas noches resto) sin emoji.

Estos tests FALLAN con el código anterior (saludo en inglés) y PASAN con el fix.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "web" / "dashboard.html"


class Bug066GreetingSpanishTests(unittest.TestCase):
    def test_saludo_esta_en_espanol(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # No debe haber saludo en inglés en la función greeting().
        self.assertNotIn("Good morning", html)
        self.assertNotIn("Good afternoon", html)
        self.assertNotIn("Good evening", html)
        # Debe usar saludo en español.
        self.assertIn("Buenos días", html)
        self.assertIn("Buenas tardes", html)
        self.assertIn("Buenas noches", html)

    def test_saludo_sin_emoji(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # Paso 3: cero emojis de color. El saludo no debe tener 👋.
        self.assertNotIn("\U0001f44b", html, "emoji 👋 presente en el saludo")

    def test_greeting_funcion_define_horas_espanol(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        # La función greeting() debe existir y usar rangos de hora en español.
        idx = html.find("function greeting()")
        self.assertGreater(idx, -1, "función greeting() ausente")
        block = html[idx:idx + 400]
        self.assertIn("Buenos días", block)
        self.assertIn("Buenas tardes", block)
        self.assertNotIn("Good", block)

    def test_copy_informe_en_espanol(self):
        """Regla UI en español: el título del informe no debe estar en inglés."""
        html = DASHBOARD.read_text(encoding="utf-8")
        self.assertNotIn("Daily Executive Brief", html, "copy en inglés visible")
        self.assertIn("Informe Ejecutivo Diario", html, "título del informe en español ausente")


if __name__ == "__main__":
    unittest.main()
