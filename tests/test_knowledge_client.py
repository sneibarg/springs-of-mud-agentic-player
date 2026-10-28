import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.rest.KnowledgeClient import KnowledgeClient, KnowledgeStoreError
from play.WorldKnowledge import AreaRecord, HelpTopic, PlayerRecord, RoomSnapshot, WorldKnowledge


class _Response:
    def __init__(self, status_code=200, payload=None, content=b"{}"):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class TestKnowledgeClient(unittest.TestCase):
    def test_save_puts_the_document_with_the_auth_header(self):
        captured = {}

        def request(method, url, json, headers, timeout):
            captured.update(method=method, url=url, json=json, headers=headers, timeout=timeout)
            return _Response(payload=json, content=b"{}")

        client = KnowledgeClient(
            "http://localhost:8169/",
            headers_provider=lambda: {"Authorization": "Bearer jwt-token"},
            request=request,
        )
        saved = client.save("char 1", {"characterName": "Example", "helpTopics": []})

        self.assertEqual(captured["method"], "PUT")
        self.assertEqual(captured["url"], "http://localhost:8169/api/v1/agent-knowledge/char%201")
        self.assertEqual(captured["headers"], {"Authorization": "Bearer jwt-token"})
        self.assertEqual(saved["characterId"], "char 1")
        self.assertEqual(captured["json"]["characterName"], "Example")

    def test_load_returns_none_when_the_character_has_no_snapshot(self):
        def request(method, url, json, headers, timeout):
            return _Response(status_code=404, content=b"")

        client = KnowledgeClient("http://localhost:8169", request=request)
        self.assertIsNone(client.load("char-1"))

    def test_http_error_names_the_status_and_not_the_body(self):
        def request(method, url, json, headers, timeout):
            return _Response(status_code=503, payload={"token": "secret"}, content=b"secret")

        client = KnowledgeClient("http://localhost:8169", request=request)
        with self.assertRaises(KnowledgeStoreError) as raised:
            client.save("char-1", {"characterId": "char-1"})
        self.assertIn("HTTP 503", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))

    def test_document_round_trip(self):
        knowledge = WorldKnowledge()
        knowledge.login_lines = ["Welcome to the server!"]
        knowledge.remember_help(HelpTopic(command="look", keyword="LOOK", text="Look around.", raw="LOOK\nLook around."))
        knowledge.remember_area(AreaRecord(name="Temple of Mota", author="Romy", level_range="1-5"))
        knowledge.remember_player(PlayerRecord(
            name="Example",
            level=1,
            race="human",
            character_class="Mag",
            title="the agent",
            agentic=True,
            self_character=True,
            room_name="Temple of Mota",
        ))
        knowledge.room = RoomSnapshot(name="Temple of Mota", description="A quiet temple.", exits=["north"], item_lines=["a fountain"])
        document = knowledge.to_document(character_id="char-1", character_name="Example", agent_name="example-agent")

        restored = WorldKnowledge.from_document(document)

        self.assertEqual(document["characterId"], "char-1")
        self.assertEqual(document["helpTopics"][0]["keyword"], "LOOK")
        self.assertEqual(document["areas"][0]["levelRange"], "1-5")
        self.assertTrue(document["players"][0]["selfCharacter"])
        self.assertEqual(restored.help_for("look").text, "Look around.")
        self.assertEqual(restored.area_named("Temple of Mota").author, "Romy")
        self.assertTrue(restored.player_named("Example").agentic)
        self.assertEqual(restored.room.exits, ["north"])
        self.assertEqual(restored.room.item_lines, ["a fountain"])


if __name__ == "__main__":
    unittest.main()
