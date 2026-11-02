import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.rest.KnowledgeClient import KnowledgeClient, KnowledgeStoreError
from play.WorldKnowledge import AreaRecord, BeingRecord, HelpTopic, PlayerRecord, RoomSnapshot, WorldKnowledge


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

        client = KnowledgeClient("http://localhost:8169/", headers_provider=lambda: {"Authorization": "Bearer jwt-token"}, request=request)
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
        knowledge.remember_command("look", category="information", help_text="Look around.")
        knowledge.remember_area(AreaRecord(name="Temple of Mota", author="Romy", level_range="1-5"))
        knowledge.remember_mobile(BeingRecord(name="a healer", kind="mobile", pose="here", room_name="Temple of Mota", auras=["White Aura"]))
        knowledge.remember_npc(BeingRecord(name="Hassan", kind="npc", pose="standing", room_name="Temple of Mota", auras=["Golden Aura"]))
        knowledge.remember_player(PlayerRecord(name="Example", level=1, race="human", character_class="Mag", title="the agent", agentic=True, self_character=True, room_name="Temple of Mota", auras=["Red Aura"]))
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
        self.assertEqual(document["mobiles"][0]["auras"], ["White Aura"])
        self.assertEqual(document["npcs"][0]["auras"], ["Golden Aura"])
        self.assertEqual(document["players"][0]["auras"], ["Red Aura"])
        self.assertEqual(restored.player_named("Example").auras, ["Red Aura"])
        self.assertEqual(document["commands"][0]["helpText"], "Look around.")
        self.assertEqual(restored.command_records()[0].category, "information")

    def test_summary_counts_the_items_in_the_room(self):
        knowledge = WorldKnowledge()
        knowledge.remember_help(HelpTopic(command="look", keyword="LOOK", text="Look around.", raw="LOOK"))
        knowledge.remember_command("look", help_text="Look around.")
        knowledge.remember_area(AreaRecord(name="Temple of Mota", author="Romy"))
        knowledge.remember_mobile(BeingRecord(name="a healer", kind="mobile", pose="here", room_name="By the Temple Altar"))
        knowledge.remember_player(PlayerRecord(name="Janky", level=8, race="human", character_class="War"))
        knowledge.remember_player(PlayerRecord(name="Fizban", level=60, race="human", character_class="IMP"))
        knowledge.room = RoomSnapshot(name="By the Temple Altar", exits=["south", "up"], item_lines=["A pit for sacrifices is in front of the altar."])

        text = WorldKnowledge.summary(knowledge)

        self.assertEqual(text, "Knowledge: 1 help, 1 commands, 1 areas, 1 mobiles, 0 npcs, 2 players, 1 items.\nCurrent room: By the Temple Altar")
        self.assertEqual(WorldKnowledge.summary(WorldKnowledge()), "Knowledge: 0 help, 0 commands, 0 areas, 0 mobiles, 0 npcs, 0 players, 0 items.")

    def test_help_topics_supply_commands_when_the_command_list_is_absent(self):
        knowledge = WorldKnowledge.from_document({"helpTopics": [{"command": "look", "keyword": "LOOK", "text": "Look around.", "raw": "LOOK", "missing": False, "topics": []}]})
        self.assertTrue(knowledge.has_commands())
        self.assertEqual([(command.name, command.help_text) for command in knowledge.command_records()], [("look", "Look around.")])
        self.assertEqual(knowledge.to_document(character_id="char-1", character_name="Example", agent_name="example-agent")["commands"], [])


if __name__ == "__main__":
    unittest.main()
