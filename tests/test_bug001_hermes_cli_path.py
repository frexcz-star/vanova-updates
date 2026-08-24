"""BUG-001 real (Nico): el CLI de Hermes vive en el venv de la instalación
(LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/hermes) que NO está en el PATH.
Antes `_hermes_cli` devolvía None si `which('hermes')` no lo encontraba, así que
el perfil de ventas (`vanova-sales-analyst`) nunca se creaba y el chat a Hermes
fallaba con 'Profile does not exist'.

Fix: `_hermes_cli` busca el CLI en las rutas del venv local de Hermes en AppData.
Falla con el código anterior (si no está en PATH, devolvía None).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class HermesCliLocateTests(unittest.TestCase):
    """_hermes_cli debe localizar el CLI de Hermes en el venv de AppData."""

    def test_cli_buscado_en_venv_de_appdata(self):
        from desktop.runtime import agent_hermes_bot

        # when neither PATH nor hermes_service._find_hermes find the CLI,
        # _hermes_cli must fall back to the venv under LOCALAPPDATA/hermes.
        fake = type("FakeService", (), {"_find_hermes": lambda self: None})()
        with patch.object(agent_hermes_bot, "hermes_service", fake):
            with patch.object(agent_hermes_bot, "shutil") as sh:
                sh.which.return_value = None
                with patch.object(agent_hermes_bot.os, "name", "nt"):
                    with patch.object(
                        agent_hermes_bot.os, "getenv",
                        lambda k, d="": "C:/Users/Admin/AppData/Local" if k == "LOCALAPPDATA" else d,
                    ):
                        # el candidato del venv "existe"
                        with patch.object(Path, "exists", return_value=True):
                            res = agent_hermes_bot._hermes_cli()
        self.assertIsNotNone(res, "_hermes_cli debe localizar el CLI en el venv de AppData cuando no está en PATH")
        self.assertIn("AppData", str(res[0]), "el CLI debe apuntar al venv de AppData")

    def test_source_busca_en_venv_de_appdata(self):
        # Verificación por código: _hermes_cli debe contener la búsqueda en
        # LOCALAPPDATA/hermes/.../venv/Scripts/hermes
        src = (ROOT / "desktop" / "runtime" / "agent_hermes_bot.py").read_text(encoding="utf-8")
        self.assertIn("hermes-agent", src, "_hermes_cli debe buscar el CLI en hermes-agent/venv")
        self.assertIn("Scripts", src, "_hermes_cli debe buscar el CLI en Scripts del venv")


if __name__ == "__main__":
    unittest.main()
