"""Regression tests — BUG-015 (RMW atómico en ai_providers + hermes_config).

Patrón acumulativo: el fix de lost-update debe usar config_store.update() y
NO perder otros providers al escribir la clave 'primary'.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import ai_providers, config_store  # noqa: E402


class AiProvidersConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_file = Path(self.tmp.name) / "maios.json"
        self.config_patcher = patch.object(config_store, "CONFIG_FILE", self.config_file)
        self.config_patcher.start()
        config_store.save({"aiProviders": {}})
        # Aislar credenciales
        self.cred_path = Path(self.tmp.name) / "credentials.json"
        self.cred_patcher = patch.object(config_store, "credential_vault", create=True)
        # Evitar escritura de env
        self.env_patcher = patch.object(ai_providers, "_write_env_provider", return_value=None)

    def tearDown(self):
        self.config_patcher.stop()
        self.tmp.cleanup()

    def test_bug015_save_provider_config_uses_atomic_update(self):
        from desktop.runtime import ai_providers
        with patch.object(config_store, "update", side_effect=lambda mut: mut(config_store.load())) as mock_update:
            ai_providers.save_provider_config("openrouter", "key-123", "deepseek")
        mock_update.assert_called_once()

    def test_bug015_hermes_config_sync_preserves_other_providers(self):
        """El sync de hermes_config NO debe borrar otros providers al actualizar primary."""
        from desktop.runtime import hermes_config
        # Pre-configurar un provider manual distinto de primary
        cfg = config_store.load()
        cfg["aiProviders"] = {"manual": {"providerId": "manual", "configured": True}}
        config_store.save(cfg)
        # Mockear load_config para que devuelva un provider hermes-config
        fake_cfg = {"found": True, "providerId": "ollama-launch", "model": "llama3", "providerName": "Ollama"}
        # Reset de la caché de sync para forzar la escritura
        hermes_config._sync_last_key = ""
        hermes_config._sync_last_at = 0.0
        with patch.object(hermes_config, "load_config", return_value=fake_cfg), \
             patch.object(hermes_config, "_sync_connector_env", return_value=None):
            hermes_config.sync_maios_from_hermes()
        data = config_store.load()
        providers = data.get("aiProviders", {})
        # El provider manual debe seguir presente
        self.assertIn("manual", providers)
        self.assertIn("primary", providers)
        self.assertEqual(providers["primary"]["providerId"], "ollama-launch")
        self.assertEqual(providers["primary"]["source"], "hermes-config")


if __name__ == "__main__":
    unittest.main()
