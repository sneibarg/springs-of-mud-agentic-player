import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.rest.PromptClient import PromptClient, PromptStoreError


class _Response:
    def __init__(self, status_code=200, payload=None, content=b"{}"):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class TestPromptClient(unittest.TestCase):
    def test_list_gets_the_collection(self):
        captured = {}

        def request(method, url, json, headers, timeout):
            captured.update(method=method, url=url, headers=headers)
            return _Response(payload=[{"name": "categories", "model": "gpt-oss:20b", "system": "Read the index.", "user": "{help}"}])

        client = PromptClient("http://dragon:9080/", headers_provider=lambda: {"Authorization": "Bearer jwt-token"}, request=request)
        documents = client.list()

        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["url"], "http://dragon:9080/api/v1/agent-prompts")
        self.assertEqual(captured["headers"], {"Authorization": "Bearer jwt-token"})
        self.assertEqual(documents[0]["name"], "categories")

    def test_get_quotes_one_name(self):
        captured = {}

        def request(method, url, json, headers, timeout):
            captured["url"] = url
            return _Response(payload={"name": "help me", "model": "gpt-oss:20b", "system": "Read help.", "user": "{help}"})

        client = PromptClient("http://dragon:9080", request=request)
        document = client.get("help me")

        self.assertEqual(captured["url"], "http://dragon:9080/api/v1/agent-prompts/help%20me")
        self.assertEqual(document["name"], "help me")

    def test_get_returns_none_when_the_name_is_absent(self):
        def request(method, url, json, headers, timeout):
            return _Response(status_code=404, payload={"detail": "missing"}, content=b"missing")

        client = PromptClient("http://dragon:9080", request=request)
        self.assertIsNone(client.get("missing"))

    def test_http_error_names_the_status_and_not_the_body(self):
        def request(method, url, json, headers, timeout):
            return _Response(status_code=503, payload={"token": "secret"}, content=b"secret")

        client = PromptClient("http://dragon:9080", request=request)
        with self.assertRaises(PromptStoreError) as raised:
            client.get("categories")
        self.assertIn("HTTP 503", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))

    def test_a_blank_name_is_rejected(self):
        client = PromptClient("http://dragon:9080", request=lambda *args, **kwargs: _Response())
        with self.assertRaises(ValueError) as raised:
            client.get("   ")
        self.assertEqual(str(raised.exception), "name must not be blank")


if __name__ == "__main__":
    unittest.main()
