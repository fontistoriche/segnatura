import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from segnatura.llm import (InvalidLLMResponseError,
                           OpenAICompatibleBackend, OpenAICompatibleConfig,
                           StructuredLLMBackend)


class FakeTransport:
    def __init__(self):
        self.get = 0
        self.post = 0
        self.payload = None

    def __call__(self, method, url, payload, headers, timeout):
        if method == "GET":
            self.get += 1
            return {"data": [{"id": "google/gemma-3-27b-it-q4"}]}
        self.post += 1
        self.payload = payload
        return {"choices": [{"message": {
            "content": json.dumps({"findings": []})
        }}]}


class TruncatedFirstResponse(FakeTransport):
    def __call__(self, method, url, payload, headers, timeout):
        if method == "GET":
            return super().__call__(method, url, payload, headers, timeout)
        self.post += 1
        self.payload = payload
        if self.post == 1:
            return {"choices": [{"finish_reason": "length", "message": {
                "content": '{"findings":'
            }}]}
        return {"choices": [{"finish_reason": "stop", "message": {
            "content": '{"findings": []}'
        }}]}


SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "audit",
        "strict": True,
        "schema": {"type": "object"},
    },
}


class LLMBackendTest(unittest.TestCase):
    def test_model_discovery_does_not_require_a_model_configuration(self):
        transport = FakeTransport()

        models = OpenAICompatibleBackend.discover_models(
            base_url="http://localhost:1234/v1",
            api_key="temporary-key",
            timeout=12,
            transport=transport,
        )

        self.assertEqual(["google/gemma-3-27b-it-q4"], models)
        self.assertEqual(1, transport.get)
        self.assertEqual(0, transport.post)

    def test_cache_writes_use_unique_atomic_temporary_files(self):
        written = []
        original_write_text = Path.write_text

        def record_write_text(path, *args, **kwargs):
            written.append(path)
            return original_write_text(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "cache.json"
            with patch.object(Path, "write_text", record_write_text):
                OpenAICompatibleBackend._save_cache(target, {"value": 1})
                OpenAICompatibleBackend._save_cache(target, {"value": 2})
            saved = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual({"value": 2}, saved)
        self.assertEqual(2, len(written))
        self.assertNotEqual(written[0], written[1])
        self.assertTrue(all(path.name.endswith(".tmp") for path in written))

    def test_cache_key_is_scoped_to_endpoint_and_schema(self):
        first = OpenAICompatibleBackend(OpenAICompatibleConfig(
            model="same-model", base_url="http://one.local/v1", cache=None))
        second = OpenAICompatibleBackend(OpenAICompatibleConfig(
            model="same-model", base_url="http://two.local/v1", cache=None))

        first_key = first._cache_key(
            "same-model", {"text": "same"}, "audit-1", SCHEMA)
        second_key = second._cache_key(
            "same-model", {"text": "same"}, "audit-1", SCHEMA)

        self.assertNotEqual(first_key, second_key)

    def test_lm_studio_discovers_model_and_reuses_verified_cache(self):
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as temporary:
            backend = OpenAICompatibleBackend.lm_studio(
                "gemma 27b", cache=Path(temporary),
                reasoning_effort="none")
            backend._transport = transport
            first = backend.request_structured(
                {"book": "Example"}, "Audit", SCHEMA, "audit-1")
            second = backend.request_structured(
                {"book": "Example"}, "Audit", SCHEMA, "audit-1")

        self.assertIsInstance(backend, StructuredLLMBackend)
        self.assertEqual("google/gemma-3-27b-it-q4", first.model)
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertEqual(1, transport.get)
        self.assertEqual(1, transport.post)
        self.assertEqual("json_schema",
                         transport.payload["response_format"]["type"])
        self.assertEqual("none", transport.payload["reasoning_effort"])

    def test_invalid_json_is_retried_once_and_diagnosed(self):
        transport = TruncatedFirstResponse()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backend = OpenAICompatibleBackend(OpenAICompatibleConfig(
                model="local-model", base_url="http://localhost:1234/v1",
                cache=root, max_tokens=2400), transport=transport)
            response = backend.request_structured(
                {"book": "Example"}, "Audit", SCHEMA, "audit-1")
            diagnostics = list(root.rglob("*.invalid-1.json"))

        self.assertEqual({"findings": []}, response.data)
        self.assertEqual(2, response.network_attempts)
        self.assertEqual(1, response.invalid_json_responses)
        self.assertEqual(2, transport.post)
        self.assertEqual(4800, transport.payload["max_tokens"])
        self.assertEqual(1, len(diagnostics))

    def test_remote_compatible_endpoint_does_not_require_model_listing(self):
        transport = FakeTransport()
        backend = OpenAICompatibleBackend(OpenAICompatibleConfig(
            model="remote-model", base_url="https://example.invalid/v1",
            cache=None), transport=transport)

        response = backend.request_structured(
            {"book": "Example"}, "Audit", SCHEMA, "audit-1")

        self.assertEqual({"findings": []}, response.data)
        self.assertEqual(0, transport.get)
        self.assertEqual(1, transport.post)

    def test_connection_probe_can_disable_invalid_json_retry(self):
        transport = TruncatedFirstResponse()
        backend = OpenAICompatibleBackend(OpenAICompatibleConfig(
            model="local-model", base_url="http://localhost:1234/v1",
            cache=None, max_tokens=128), transport=transport)

        with self.assertRaises(InvalidLLMResponseError):
            backend.request_structured(
                {"task": "test"}, "Test", SCHEMA, "connection-test-1",
                retry_invalid=False)

        self.assertEqual(1, transport.post)


if __name__ == "__main__":
    unittest.main()
