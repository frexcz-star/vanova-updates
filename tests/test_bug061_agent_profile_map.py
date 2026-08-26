"""BUG-061 (Mathew): el scheduler lanza el agente 'sales-analyst' que genera el
perfil 'vanova-sales-analyst', pero ese perfil NO existe en disco. El perfil
existente es 'vanova-agente-de-ventas'. Resultado: la tarea programada falla
recurrente con 'Error: Profile vanova-sales-analyst does not exist'.

Fix: mapa de compatibilidad _AGENT_ID_TO_PROFILE que mapea 'sales-analyst' ->
'vanova-agente-de-ventas' (perfil existente).

Falla con el código anterior (sin el mapa, generaba 'vanova-sales-analyst').
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class AgentProfileMapTests(unittest.TestCase):
    """BUG-061: agent_slug debe mapear sales-analyst al perfil existente."""

    def test_sales_analyst_mapea_a_perfil_existente(self):
        from desktop.runtime.agent_hermes_bot import agent_slug

        agent = {"id": "sales-analyst", "name": "Analista de Ventas"}
        slug = agent_slug(agent)
        self.assertEqual(slug, "vanova-agente-de-ventas",
                         "sales-analyst debe mapear al perfil vanova-agente-de-ventas que existe en disco")

    def test_agente_de_ventas_sin_mapeo_no_se_rompe(self):
        from desktop.runtime.agent_hermes_bot import agent_slug

        # Un agente sin mapeo debe seguir generando el slug por el mecanismo normal
        agent = {"id": "inventory-agent", "name": "Agente de Stock"}
        slug = agent_slug(agent)
        self.assertEqual(slug, "vanova-inventory-agent")

    def test_source_tiene_mapa_de_compatibilidad(self):
        src = (ROOT / "desktop" / "runtime" / "agent_hermes_bot.py").read_text(encoding="utf-8")
        self.assertIn("_AGENT_ID_TO_PROFILE", src,
                      "Debe existir el mapa de compatibilidad _AGENT_ID_TO_PROFILE")
        self.assertIn('"sales-analyst": "vanova-agente-de-ventas"', src,
                      "El mapa debe contener el mapeo sales-analyst -> vanova-agente-de-ventas")


if __name__ == "__main__":
    unittest.main()
