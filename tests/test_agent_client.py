import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent.Agent import Agent
from net.rest.AgentClient import AgentClient, AgentStoreError


class _Response:
    def __init__(self, status_code=200, payload=None, content=b"{}"):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class TestAgentClient(unittest.TestCase):
    def test_list_gets_the_collection_and_sends_headers(self):
        captured = {}

        def request(method, url, json, headers, timeout):
            captured.update(method=method, url=url, json=json, headers=headers, timeout=timeout)
            return _Response(payload=[{"id": "abc", "name": "Guide", "accountName": "account", "characterName": "Guide", "enabled": True}])

        client = AgentClient("http://dragon:9080/", headers_provider=lambda: {"Authorization": "Bearer jwt-token"}, request=request)
        documents = client.list()

        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["url"], "http://dragon:9080/api/v1/agents")
        self.assertIsNone(captured["json"])
        self.assertEqual(captured["headers"], {"Authorization": "Bearer jwt-token"})
        self.assertEqual(documents[0]["name"], "Guide")

    def test_get_quotes_the_name_and_reads_the_id_field(self):
        captured = {}
        document = {"id": "66f0a1b2c3d4e5f607182930", "name": "Guide/One", "accountName": "agent-account", "characterName": "Example", "enabled": True, "description": "A guide"}

        def request(method, url, json, headers, timeout):
            captured["url"] = url
            return _Response(payload=document)

        client = AgentClient("http://dragon:9080", request=request)
        agent = Agent.from_json(client.get("Guide/One"))

        self.assertEqual(captured["url"], "http://dragon:9080/api/v1/agents/Guide%2FOne")
        self.assertEqual(agent.id, "66f0a1b2c3d4e5f607182930")
        self.assertEqual(agent.account_name, "agent-account")
        self.assertEqual(agent.character_name, "Example")

    def test_get_returns_none_when_the_name_is_absent(self):
        def request(method, url, json, headers, timeout):
            return _Response(status_code=404, payload={"detail": "missing"}, content=b"missing")

        client = AgentClient("http://dragon:9080", request=request)
        self.assertIsNone(client.get("missing agent"))

    def test_http_error_names_the_status_and_not_the_body(self):
        def request(method, url, json, headers, timeout):
            return _Response(status_code=503, payload={"token": "secret"}, content=b"secret")

        client = AgentClient("http://dragon:9080", request=request)
        with self.assertRaises(AgentStoreError) as raised:
            client.list()
        self.assertIn("HTTP 503", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))

    def test_a_non_list_payload_is_rejected(self):
        def request(method, url, json, headers, timeout):
            return _Response(payload={"name": "Guide"})

        client = AgentClient("http://dragon:9080", request=request)
        with self.assertRaises(AgentStoreError):
            client.list()

    def test_a_blank_name_is_rejected(self):
        client = AgentClient("http://dragon:9080", request=lambda *args, **kwargs: _Response())
        with self.assertRaises(ValueError) as raised:
            client.get("   ")
        self.assertEqual(str(raised.exception), "name must not be blank")


if __name__ == "__main__":
    unittest.main()
