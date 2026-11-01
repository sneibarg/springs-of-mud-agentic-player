import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.rest.MemoryClient import MemoryClient, MemoryStoreError


class _Response:
    def __init__(self, status_code=200, payload=None, content=b"{}"):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class TestMemoryClient(unittest.TestCase):
    def test_save_quotes_the_name_and_omits_saved_at_and_id(self):
        captured = {}

        def request(method, url, json, headers, timeout):
            captured.update(method=method, url=url, json=json, headers=headers)
            stored = dict(json)
            stored["savedAt"] = "2026-11-01T00:00:00Z"
            return _Response(payload=stored)

        client = MemoryClient("http://dragon:9080/", headers_provider=lambda: {"Authorization": "Bearer jwt-token"}, request=request)
        saved = client.save("agent one", {"agentName": "Agent One", "savedAt": "yesterday", "id": "memory-id", "players": []})

        self.assertEqual(captured["method"], "PUT")
        self.assertEqual(captured["url"], "http://dragon:9080/api/v1/agent-memory/agent%20one")
        self.assertEqual(captured["headers"], {"Authorization": "Bearer jwt-token"})
        self.assertEqual(captured["json"]["agentName"], "Agent One")
        self.assertNotIn("savedAt", captured["json"])
        self.assertNotIn("id", captured["json"])
        self.assertEqual(saved["savedAt"], "2026-11-01T00:00:00Z")

    def test_omitted_agent_name_is_taken_from_the_path(self):
        captured = {}

        def request(method, url, json, headers, timeout):
            captured["json"] = json
            return _Response(payload=json)

        client = MemoryClient("http://dragon:9080", request=request)
        client.save("example-agent", {"players": []})
        self.assertEqual(captured["json"]["agentName"], "example-agent")

    def test_agent_name_must_match_the_path_ignoring_case(self):
        called = []

        def request(method, url, json, headers, timeout):
            called.append(url)
            return _Response(payload=json)

        client = MemoryClient("http://dragon:9080", request=request)
        client.save("example-agent", {"agentName": "Example-Agent"})
        self.assertTrue(called)
        with self.assertRaises(ValueError) as raised:
            client.save("example-agent", {"agentName": "other-agent"})
        self.assertEqual(str(raised.exception), "agentName does not match the memory path")
        self.assertEqual(len(called), 1)

    def test_a_blank_agent_name_is_rejected(self):
        client = MemoryClient("http://dragon:9080", request=lambda *args, **kwargs: _Response())
        with self.assertRaises(ValueError) as raised:
            client.save("   ", {})
        self.assertEqual(str(raised.exception), "agentName must not be blank")
        with self.assertRaises(ValueError) as raised:
            client.save("example-agent", {"agentName": " "})
        self.assertEqual(str(raised.exception), "agentName must not be blank")

    def test_load_returns_none_on_404(self):
        captured = {}

        def request(method, url, json, headers, timeout):
            captured.update(method=method, url=url)
            return _Response(status_code=404, payload={"detail": "expired"}, content=b"expired")

        client = MemoryClient("http://dragon:9080", request=request)
        self.assertIsNone(client.load("agent one"))
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["url"], "http://dragon:9080/api/v1/agent-memory/agent%20one")

    def test_http_error_names_the_status_and_not_the_body(self):
        def request(method, url, json, headers, timeout):
            return _Response(status_code=503, payload={"token": "secret"}, content=b"secret")

        client = MemoryClient("http://dragon:9080", request=request)
        with self.assertRaises(MemoryStoreError) as raised:
            client.load("example-agent")
        self.assertIn("HTTP 503", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
