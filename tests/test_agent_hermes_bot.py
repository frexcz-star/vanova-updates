"""FASE B — tests de sincronización agente VANOVA → bot Hermes persistente.

Verifica la generación del slug de perfil, la construcción del SOUL.md (con la
regla de honestidad) y el borrado de perfil. Sin crear perfiles Hermes reales:
se parchea la resolución del CLI.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.runtime import agent_hermes_bot as bot


class AgentHermesBotSlugTests(unittest.TestCase):
    def test_agent_slug_namespaced(self):
        a = {"id": "custom-ventas", "name": "Agente de Ventas"}
        self.assertEqual(bot.agent_slug(a), "vanova-ventas")

    def test_agent_slug_handles_missing_id(self):
        a = {"id": "", "name": "Stock"}
        self.assertEqual(bot.agent_slug(a), "vanova-stock")

    def test_agent_slug_sanitizes(self):
        a = {"id": "custom-mi agente/", "name": "Mi Agente"}
        self.assertTrue(bot.agent_slug(a).startswith("vanova-"))


class AgentHermesBotSoulTests(unittest.TestCase):
    def test_soul_includes_honesty_rule(self):
        soul = bot._build_soul({"name": "Ventas", "role": "sales", "responsibilities": ["Analizar ventas"]})
        self.assertIn("Eres Ventas", soul)
        self.assertIn("honestidad", soul.lower())
        self.assertIn("UNKNOWN", soul)
        self.assertIn("Analizar ventas", soul)

    def test_soul_uses_role_titles(self):
        soul = bot._build_soul({"name": "Contable", "role": "accounting", "responsibilities": []})
        self.assertIn("salud financiera", soul)


class AgentHermesBotSyncTests(unittest.TestCase):
    def test_sync_returns_honest_error_without_cli(self):
        with patch.object(bot, "_hermes_cli", return_value=None):
            r = bot.sync_agent_to_bot({"id": "custom-x", "name": "X"})
        self.assertFalse(r["ok"])
        self.assertIn("CLI", r["error"])


if __name__ == "__main__":
    unittest.main()
