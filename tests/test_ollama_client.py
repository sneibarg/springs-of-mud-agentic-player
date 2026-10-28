import os
import sys
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.rest.OllamaClient import OllamaClient, OllamaError
from prompt.PromptCollection import PromptCollection


ROOT = Path(__file__).resolve().parents[1]


class _Response:
    def __init__(self, status_code=200, payload=None, content=b"{}"):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class TestOllamaClient(unittest.TestCase):
    def test_posts_the_prompt_body_and_returns_the_completion_text(self):
        captured = {}

        def request(method, url, json, headers, timeout):
            captured.update(method=method, url=url, json=json, headers=headers, timeout=timeout)
            return _Response(payload={"text": '{"expToLevel": 50}'})

        score = PromptCollection.load(ROOT / "resources" / "collections" / "SOMDB.Prompts.json").get("score")
        submission = score.tokenize("You need 50 exp to level.", "expToLevel")
        client = OllamaClient("http://localhost:9081/", request=request)
        text = client.complete(submission.to_request())

        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["url"], "http://localhost:9081/ollama/completions")
        self.assertEqual(captured["headers"], {"Content-Type": "application/json"})
        self.assertEqual(captured["timeout"], 120.0)
        self.assertEqual(captured["json"]["model"], "gpt-oss:20b")
        self.assertEqual(captured["json"]["user"], "You need 50 exp to level.")
        self.assertEqual(captured["json"]["jsonSchema"]["required"], ["expToLevel"])
        self.assertEqual(text, '{"expToLevel": 50}')
        self.assertEqual(submission.read_completion(text), {"expToLevel": 50})

    def test_bad_request_uses_the_service_error(self):
        def request(method, url, json, headers, timeout):
            return _Response(
                status_code=400,
                payload={"error": "User prompt cannot be null or empty", "user": "secret score"},
                content=b"secret score",
            )

        client = OllamaClient("http://localhost:9081", request=request)
        with self.assertRaises(OllamaError) as raised:
            client.complete({"user": "Hello"})
        self.assertEqual(str(raised.exception), "User prompt cannot be null or empty")
        self.assertNotIn("secret", str(raised.exception))

    def test_upstream_failure_uses_the_service_error(self):
        def request(method, url, json, headers, timeout):
            return _Response(status_code=502, payload={"error": "Ollama could not complete the request"})

        client = OllamaClient("http://localhost:9081", request=request)
        with self.assertRaises(OllamaError) as raised:
            client.complete({"user": "Hello"})
        self.assertEqual(str(raised.exception), "Ollama could not complete the request")

    def test_empty_completion_is_rejected(self):
        def request(method, url, json, headers, timeout):
            return _Response(payload={"text": "  "})

        client = OllamaClient("http://localhost:9081", request=request)
        with self.assertRaises(OllamaError) as raised:
            client.complete({"user": "Hello"})
        self.assertEqual(str(raised.exception), "Ollama returned an empty response")

    def test_blank_user_is_not_sent(self):
        def request(method, url, json, headers, timeout):
            raise AssertionError("request was sent")

        client = OllamaClient("http://localhost:9081", request=request)
        with self.assertRaises(OllamaError) as raised:
            client.complete({"user": "  "})
        self.assertEqual(str(raised.exception), "User prompt cannot be null or empty")

    def test_transport_error_names_the_exception_class(self):
        def request(method, url, json, headers, timeout):
            raise TimeoutError("timed out talking to secret-host")

        client = OllamaClient("http://localhost:9081", request=request)
        with self.assertRaises(OllamaError) as raised:
            client.complete({"user": "Hello"})
        self.assertIn("TimeoutError", str(raised.exception))
        self.assertNotIn("secret-host", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
