"""BUG-060 (Mathew): 'import bcrypt' en process_manager._sync_owner_password_in_db
lanzaba ModuleNotFoundError cuando bcrypt no está en el bundle de Python del
runtime. Al dispararse en cada login local sin try/except, la excepción no
capturada tiraba el proceso del runtime -> runtime cae recurrente -> badge del
contador stale (síntoma que Nico reporta).

Fix: import condicional de bcrypt con fallback a hashlib.scrypt (nunca crashea
el runtime) + try/except defensivo en _ensure_owner_auth_sync.

Falla con el código anterior (que hacía `import bcrypt` directo y crasheaba).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BcryptNonFatalTests(unittest.TestCase):
    """_sync_owner_password_in_db debe no crashear cuando bcrypt no está (BUG-060)."""

    def test_source_import_bcrypt_condicional(self):
        # El código NO debe hacer `import bcrypt` directo (que crashea si no está)
        src = (ROOT / "desktop" / "runtime" / "process_manager.py").read_text(encoding="utf-8")
        self.assertIn("import bcrypt  # noqa: F401", src,
                      "debe importar bcrypt de forma condicional (no directo)")
        self.assertIn("bcrypt = None", src,
                      "debe tener fallback cuando bcrypt no está")

    def test_source_no_import_bcrypt_directo(self):
        # No debe haber un `import bcrypt` directo sin el try (en la función de sync)
        src = (ROOT / "desktop" / "runtime" / "process_manager.py").read_text(encoding="utf-8")
        idx = src.find("def _sync_owner_password_in_db")
        self.assertNotEqual(idx, -1)
        block = src[idx:idx + 700]
        # El import de bcrypt dentro de la función debe estar en try
        self.assertIn("try:", block)
        self.assertIn("import bcrypt", block)
        # No debe crashear: el fallback a hashlib.scrypt presente
        self.assertIn("hashlib.scrypt", block, "debe haber fallback a scrypt sin bcrypt")

    def test_ensure_owner_auth_sync_no_crashea(self):
        # _ensure_owner_auth_sync debe tener try/except alrededor de la sync
        src = (ROOT / "desktop" / "runtime" / "process_manager.py").read_text(encoding="utf-8")
        idx = src.find("def _ensure_owner_auth_sync")
        self.assertNotEqual(idx, -1)
        block = src[idx:idx + 400]
        self.assertIn("try:", block, "_ensure_owner_auth_sync debe proteger la sync de bcrypt")


if __name__ == "__main__":
    unittest.main()
