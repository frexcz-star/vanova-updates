"""FASE B, PASO 3 — tests de rutina cron por agente ([bot:<name>]).

Verifica la traducción de schedules VANOVA -> cron de Hermes y el prompt de
la rutina (honestidad). Sin crear cron jobs reales: se parchea el CLI.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.runtime import agent_hermes_bot as bot


class ScheduleToCronTests(unittest.TestCase):
    def test_daily(self):
        self.assertEqual(bot.schedule_to_cron("Daily 18:00"), "0 18 * * *")

    def test_weekly(self):
        self.assertEqual(bot.schedule_to_cron("Weekly Monday 09:00"), "0 9 * * 1")

    def test_weekly_sunday(self):
        self.assertEqual(bot.schedule_to_cron("Weekly Sunday 09:00"), "0 9 * * 0")

    def test_invalid_returns_none(self):
        self.assertIsNone(bot.schedule_to_cron("nope"))
        self.assertIsNone(bot.schedule_to_cron(""))


class RoutinePromptTests(unittest.TestCase):
    def test_prompt_includes_honesty(self):
        p = bot._routine_prompt({"name": "Ventas", "responsibilities": ["Analizar ventas"]})
        self.assertIn("Ventas", p)
        self.assertIn("NUNCA inventes", p)  # regla de honestidad
        self.assertIn("dato", p)  # "si falta un dato, dilo con claridad"
        self.assertIn("Analizar ventas", p)


class SyncRoutinesTests(unittest.TestCase):
    def test_no_schedules_is_ok_and_empty(self):
        with patch.object(bot, "_hermes_cli", return_value=None):
            r = bot.sync_agent_routines({"id": "custom-x", "name": "X", "schedules": []})
        self.assertFalse(r["ok"])  # sin CLI -> error honesto
        with patch.object(bot, "_hermes_cli", return_value=["hermes"]):
            r = bot.sync_agent_routines({"id": "custom-x", "name": "X", "schedules": []})
        self.assertTrue(r["ok"])
        self.assertEqual(r["routines"], [])


if __name__ == "__main__":
    unittest.main()
