"""BUG-065 (candidato → docs obsoletas): login ceo/mooving2026 da 401.

Root cause confirmada: las credenciales documentadas (ceo/mooving2026) están
OBSOLETAS. El fix de BUG-031 regenera automáticamente la contraseña débil del
instalador (mooving2026) a una aleatoria de 22 chars en cloud/.env. La DB y el
.env usan la contraseña aleatoria vigente; mooving2026 es una weak password
rechazada por el sistema en producción (KNOWN_WEAK_PASSWORDS). El código de
auth es CORRECTO — la documentación (DEPLOY.md) quedó desactualizada.

Fix: actualizar DEPLOY.md para no documentar mooving2026 como credencial de
login, sino señalar que la contraseña se genera aleatoriamente en cloud/.env.

Estos tests FALLAN con la doc anterior (que decía "Login: ceo / mooving2026")
y PASAN con el fix.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "DEPLOY.md"
MAIN = ROOT / "cloud" / "main.py"


class Bug065ObsoleteLoginDocsTests(unittest.TestCase):
    def test_deploy_md_no_documenta_mooving2026_como_login(self):
        """DEPLOY.md no debe decir 'Login: ceo / mooving2026' (obsoleto)."""
        text = DEPLOY.read_text(encoding="utf-8")
        self.assertNotIn("Login: **`ceo` / `mooving2026`**", text)
        self.assertNotIn("Login: `ceo` / `mooving2026`", text)
        self.assertNotIn("`ceo` / `mooving2026`", text)

    def test_deploy_md_indica_password_en_cloud_env(self):
        """DEPLOY.md debe señalar que la contraseña vive en cloud/.env."""
        text = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("cloud/.env", text)
        self.assertIn("MAIOS_DEMO_PASSWORD", text)

    def test_mooving2026_sigue_en_weak_passwords(self):
        """mooving2026 debe seguir siendo weak password (regeneración automática)."""
        src = MAIN.read_text(encoding="utf-8")
        self.assertIn("mooving2026", src)
        self.assertIn("KNOWN_WEAK_PASSWORDS", src)


if __name__ == "__main__":
    unittest.main()
