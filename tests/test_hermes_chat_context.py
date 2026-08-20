"""Tests for Hermes chat context relevance filtering."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop.runtime import hermes_chat


class HermesChatContextTests(unittest.TestCase):
    def test_generic_message_omits_shopify_context(self):
        # FASE 15: mensaje de negocio (no casual, sin mención a Shopify) →
        # contexto completo con include_shopify=False.
        with patch.object(
            hermes_chat,
            "build_operational_context",
            return_value={"textBlock": "[Contexto VANOVA — usa estos hechos; no contradigas el estado real]\n- dataMode: real"},
        ) as mock_ctx:
            block = hermes_chat._build_chat_context("¿Cuántos pedidos tengo?")
        mock_ctx.assert_called_once_with(include_shopify=False, domain="general")
        self.assertIn("no menciones Shopify", block)

    def test_shopify_question_includes_shopify_context(self):
        with patch.object(
            hermes_chat,
            "build_operational_context",
            return_value={"textBlock": "[Contexto VANOVA — usa estos hechos; no contradigas el estado real]\n- Shopify: conectado"},
        ) as mock_ctx:
            block = hermes_chat._build_chat_context("¿Cuántos pedidos tengo en Shopify?")
        mock_ctx.assert_called_once_with(include_shopify=True, domain="general")
        self.assertNotIn("no menciones Shopify", block)

    def test_casual_message_uses_light_route_without_context(self):
        # FASE 15: saludo casual → ruta ligera, NO se construye el operational
        # context (el cuello de botella medido: ~11s antes, 0s ahora).
        with patch.object(hermes_chat, "build_operational_context") as mock_ctx:
            block = hermes_chat._build_chat_context("hola")
        mock_ctx.assert_not_called()
        self.assertIn("conversación casual", block)
        self.assertIn("Nunca inventes números", block)

    def test_casual_route_still_guards_against_hallucination(self):
        # El contexto ligero deja claro que NO hay datos cargados: Hermes debe
        # decirlo, nunca inventar cifras si el usuario pregunta por datos.
        block = hermes_chat._build_chat_context("gracias!")
        self.assertIn("NO se cargaron datos de negocio", block)
        self.assertIn("Nunca inventes números", block)

    def test_business_words_prevent_casual_route(self):
        # Ante la duda (palabra de negocio) → contexto completo. Nunca perder
        # exactitud por velocidad.
        self.assertFalse(hermes_chat._is_casual_message("hola, ¿cuánto he vendido?"))
        self.assertFalse(hermes_chat._is_casual_message("hola, ¿cuántos pedidos tengo?"))
        self.assertFalse(hermes_chat._is_casual_message("qué productos venden más"))
        self.assertFalse(hermes_chat._is_casual_message("estado operativo"))
        self.assertTrue(hermes_chat._is_casual_message("hola"))
        self.assertTrue(hermes_chat._is_casual_message("buenos días"))
        self.assertTrue(hermes_chat._is_casual_message("gracias!"))


class HermesRequestLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.original_requests = hermes_chat._requests
        self.original_conversations = hermes_chat._conversations
        self.original_active = hermes_chat._active_request_ids
        hermes_chat._requests = {}
        hermes_chat._conversations = {}
        hermes_chat._active_request_ids = set()

    def tearDown(self):
        hermes_chat._requests = self.original_requests
        hermes_chat._conversations = self.original_conversations
        hermes_chat._active_request_ids = self.original_active

    def test_orphaned_processing_request_is_recovered(self):
        hermes_chat._requests = {
            "req-1": {
                "id": "req-1",
                "conversation_id": "conv-1",
                "message": "revisa productos",
                "status": "processing",
                "created_at": "2020-01-01T00:00:00+00:00",
                "activityLog": [],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(hermes_chat, "CHAT_FILE", Path(tmp) / "hermes_chat.json"):
                recovered = hermes_chat.recover_orphaned_requests(max_age_seconds=0)
        self.assertEqual(recovered, 1)
        req = hermes_chat._requests["req-1"]
        self.assertEqual(req["status"], "error")
        self.assertIn("interrumpió", req["error"])
        self.assertIsNotNone(req["processed_at"])

    def test_worker_exception_does_not_leave_processing_request(self):
        hermes_chat._requests = {
            "req-2": {
                "id": "req-2",
                "conversation_id": "conv-2",
                "message": "hola",
                "status": "processing",
                "created_at": "2020-01-01T00:00:00+00:00",
                "activityLog": [],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(hermes_chat, "CHAT_FILE", Path(tmp) / "hermes_chat.json"):
                with patch.object(hermes_chat, "_process_request_impl", side_effect=RuntimeError("worker boom")):
                    hermes_chat._process_request("req-2")
        req = hermes_chat._requests["req-2"]
        self.assertEqual(req["status"], "error")
        self.assertIn("worker boom", req["error"])
        self.assertNotIn("req-2", hermes_chat._active_request_ids)

    def test_stream_reader_keeps_timeout_interruptible(self):
        source = (ROOT / "desktop" / "runtime" / "hermes_chat.py").read_text(encoding="utf-8")
        self.assertIn("stream_queue.get(timeout=", source)
        self.assertIn("_terminate_cli_process(proc)", source)
        self.assertIn("taskkill", source)
        self.assertIn("_chat_semaphore", source)


class HermesPromptLeakGuardTests(unittest.TestCase):
    """FASE C — protección general contra prompt/context leakage.

    El CLI de Hermes puede devolver el prompt completo (system hint + contexto
    operativo + pregunta) en lugar de una respuesta. Los tests son GENÉRICOS:
    no dependen de ninguna pregunta concreta (la de M02 se usa solo como una
    muestra del leak real).
    """

    ACTION_HINT = (
        "[Sistema] Eres el orquestador de VANOVA. Responde al mensaje del usuario usando "
        "el proveedor de IA ya configurado en Hermes (NVIDIA, Ollama, etc.).] "
    )

    def _strip(self, text, *, context="", message=""):
        return hermes_chat._strip_prompt_leak(
            text,
            action_hint=self.ACTION_HINT,
            context=context,
            message=message,
        )

    def test_normal_answer_is_untouched(self):
        answer = (
            "HECHO: el margen bruto es 18,9%. INFERENCIA: conviene revisar precios. "
            "NO DISPONIBLE: tesorería en vivo."
        )
        self.assertEqual(self._strip(answer), answer)

    def test_legitimate_business_terms_are_kept(self):
        # Hermes PUEDE usar estos nombres en su respuesta sin que se consideren leak.
        answer = (
            "BUSINESS HEALTH: revenue 100.000 €. TOP RISKS: margen bajo. "
            "OPPORTUNITIES: LH-031. DATA QUALITY: 2 entidades pendientes de revisión."
        )
        self.assertEqual(self._strip(answer), answer)

    def test_full_prompt_echo_is_removed_keeping_real_answer(self):
        context = "[Contexto VANOVA — usa estos hechos; no contradigas el estado real]\n- dataMode: real"
        message = "¿Dependo demasiado de algún proveedor?"
        echo = (
            self.ACTION_HINT + context + "\n\n" + message
            + "\n\nAquí va la respuesta real del asistente."
        )
        cleaned = self._strip(echo, context=context, message=message)
        self.assertNotIn("[Contexto VANOVA", cleaned)
        self.assertNotIn("[Sistema]", cleaned)
        self.assertIn("respuesta real del asistente", cleaned)

    def test_paraphrased_system_hint_variants_removed(self):
        """VANOVA 3.0: si Hermes parafrasea el hint del sistema ("orquestador
        de datos de VANOVA", "orquestador del sistema"), el sanitizador debe
        seguir cortando el bloque — el marker cubre el prefijo, no la redacción
        exacta del prompt inyectado."""
        message = "¿Cómo está mi empresa?"
        for variant in (
            "[Sistema] Eres el orquestador de datos de VANOVA\nAnaliza y responde.\nTu margen es 31%.",
            "[Sistema] Eres el orquestador del sistema.\nBUSINESS HEALTH\nRevenue: 1000",
        ):
            cleaned = self._strip(variant, message=message)
            self.assertNotIn("orquestador", cleaned)
            self.assertNotIn("[Sistema]", cleaned)

    def test_real_m02_leak_is_fully_removed(self):
        # Reproduce el leak real observado en el benchmark (empresa-2, M02):
        # el CLI devolvió el prompt + error de API + comando resume.
        leak = (
            self.ACTION_HINT
            + "[Contexto VANOVA — usa estos hechos; no contradigas el estado real]\n"
            + "- dataMode: real (Conectado)\n- Productos organizados: 100 total\n"
            + "\n⚕ Hermes\nAPI call failed after 3 retries: HTTP 502: {\"error\":\"Post "
            + "https://ollama.com:443/v1/chat/completions: dial tcp: lookup ollama.com: no such host\"}\n"
            + "hermes --resume 20260817_142724_1a902c"
        )
        cleaned = self._strip(leak, message="¿Dependo demasiado de algún proveedor?")
        self.assertEqual(cleaned, "")

    def test_context_block_after_real_answer_keeps_answer(self):
        mixed = (
            "Tu tesorería está tensa.\n"
            "[Contexto VANOVA — usa estos hechos; no contradigas el estado real]\n"
            "- dataMode: real\n- Ventas: 320 pedidos"
        )
        cleaned = self._strip(mixed, message="¿cómo está mi tesorería?")
        self.assertEqual(cleaned, "Tu tesorería está tensa.")

    def test_api_failure_noise_alone_becomes_empty(self):
        # Log interno de fallo del proveedor sin respuesta → vacío (error honesto).
        noise = (
            "Initializing agent...\n⚠️ API call failed (attempt 1/3): InternalServerError "
            "[HTTP 502]\n🔌 Provider: custom Model: deepseek-v4-flash:cloud\n"
            "📝 Error: HTTP 502: {\"error\":\"Post https://ollama.com...\"}"
        )
        self.assertEqual(self._strip(noise), "")

    def test_real_answer_before_api_noise_is_kept(self):
        answer = "Tu margen bruto es 18,9%. " * 5  # respuesta sustancial (>80 chars)
        noisy = answer + "\nInitializing agent...\n⚠️ API call failed (attempt 1/3)\n"
        cleaned = self._strip(noisy)
        self.assertIn("margen bruto", cleaned)
        self.assertNotIn("API call failed", cleaned)
        self.assertNotIn("Initializing", cleaned)

    def test_guard_wired_into_cli_runner(self):
        # El sanitizador se invoca en _run_hermes_cli sobre el summary final.
        source = (ROOT / "desktop" / "runtime" / "hermes_chat.py").read_text(encoding="utf-8")
        self.assertIn("_strip_prompt_leak(summary", source)


if __name__ == "__main__":
    unittest.main()
