import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.Conversation import Conversation
from memory.WorkingMemory import WorkingMemory
from play.WorldKnowledge import BeingRecord, PlayerRecord, RoomSnapshot, WorldKnowledge
from util.SharedUtil import SharedUtil



class TestMemoryReview(unittest.TestCase):
    def test_review_file_lists_each_consider_once(self):
        memory = WorkingMemory()
        memory.remember_player("Sam", room_name="Inn")
        memory.remember_player("Marcus", agentic=True)
        memory.remember_npc("Guildmaster", room_name="Temple")
        memory.note_aggressive("a wolf", room_name="Road")
        memory.remember_consider("goblin", ["You can kill a goblin naked and weaponless."], kind="mobile")

        with tempfile.TemporaryDirectory() as directory:
            written = memory.write_review(os.path.join(directory, "nested", "review.json"))
            document = json.loads(Path(written).read_text(encoding="utf-8"))

        self.assertEqual([item["name"] for item in document["players"]], ["Sam"])
        self.assertEqual(document["players"][0]["room_name"], "Inn")
        self.assertEqual(document["agentic_players"][0]["name"], "Marcus")
        self.assertEqual(document["npcs"][0]["name"], "Guildmaster")
        self.assertEqual(document["aggressive_mobiles"][0]["name"], "a wolf")
        self.assertTrue(document["aggressive_mobiles"][0]["aggressive"])
        self.assertEqual(document["rooms"], [])
        self.assertEqual(document["commands"], [])
        self.assertEqual(len(document["considers"]), 1)
        self.assertEqual(document["considers"][0]["target"], "goblin")
        self.assertEqual(document["considers"][0]["verdict"], "naked")
        self.assertTrue(written.endswith("review.json"))

    def test_empty_review_path_is_rejected(self):
        memory = WorkingMemory()
        with self.assertRaises(ValueError):
            memory.write_review("   ")

    def test_collection_document_is_looked_up_by_agent_name(self):
        memory = WorkingMemory()
        memory.remember_player("Sam", room_name="Inn", auras=["Red Aura"])
        memory.remember_player("Marcus", agentic=True)
        memory.remember_room("Temple", description="Stone.", exits=["north"])
        memory.remember_command("look", category="information", help_text="Look around.")
        memory.remember_consider("guard", ["The guard is no match for you."], kind="mobile")

        document = memory.to_collection("  Example-Agent  ")

        self.assertEqual(document["agentName"], "Example-Agent")
        self.assertEqual(document["players"][0]["roomName"], "Inn")
        self.assertEqual(document["players"][0]["auras"], ["Red Aura"])
        self.assertEqual(document["agenticPlayers"][0]["name"], "Marcus")
        self.assertEqual(document["rooms"][0]["exits"], ["north"])
        self.assertEqual(document["commands"][0]["helpText"], "Look around.")
        self.assertEqual(document["considers"][0]["verdict"], "no_match")
        self.assertNotIn("agentic_players", document)
        self.assertNotIn("room_name", document["players"][0])
        self.assertEqual(SharedUtil.default_collection_path().name, "SOMDB.Memories.json")

    def test_collection_dump_replaces_the_same_agent(self):
        memory = WorkingMemory()
        memory.remember_mobile("a wolf", aggressive=True)
        other = {"agentName": "other-agent", "players": [{"name": "Sam"}]}

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "SOMDB.Memories.json")
            Path(path).write_text(json.dumps([other, {"agentName": "example-agent", "players": []}], indent=2) + "\n", encoding="utf-8")
            written = memory.write_collection("Example-Agent", path)
            memory.remember_npc("Hassan")
            memory.write_collection("example-agent", path)
            documents = json.loads(Path(written).read_text(encoding="utf-8"))

        self.assertEqual([item["agentName"] for item in documents], ["other-agent", "example-agent"])
        self.assertEqual(documents[0]["players"][0]["name"], "Sam")
        self.assertEqual(documents[1]["mobiles"][0]["name"], "a wolf")
        self.assertTrue(documents[1]["mobiles"][0]["aggressive"])
        self.assertEqual(documents[1]["npcs"][0]["name"], "Hassan")
        self.assertTrue(written.endswith("SOMDB.Memories.json"))

    def test_collection_dump_rejects_a_blank_agent_or_a_non_array(self):
        memory = WorkingMemory()
        with self.assertRaises(ValueError):
            memory.to_collection("   ")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "SOMDB.Memories.json")
            Path(path).write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                memory.write_collection("example-agent", path)
            with self.assertRaises(ValueError):
                memory.write_collection("example-agent", "   ")

    def test_collection_document_round_trips_and_ignores_saved_at(self):
        memory = WorkingMemory()
        memory.remember_player("Sam", room_name="Inn", auras=["Red Aura"])
        memory.remember_player("Marcus", agentic=True, room_name="Temple", auras=["Blue Aura"])
        memory.remember_mobile("a healer", room_name="Temple", auras=["White Aura"])
        memory.remember_npc("Hassan", room_name="Temple", auras=["Golden Aura"])
        memory.note_aggressive("a wolf", room_name="Road")
        memory.remember_room("Temple", description="Stone.", exits=["north", "east"])
        memory.remember_command("look", category="information", help_text="Look around.")
        memory.remember_command("north", category="movement", help_text="Move north.")
        memory.remember_consider("guard", ["The guard is no match for you."], kind="mobile")
        memory.remember_consider("Marcus", ["The perfect match!"], kind="player", agentic=True)
        memory.remember_conversation("the gate", "room", "Temple", participants=["Sam", "Marcus"], interest=2)

        original = memory.to_collection("Example-Agent")
        loaded = dict(original)
        loaded["savedAt"] = "2026-11-01T00:00:00Z"
        loaded["id"] = "memory-id"
        restored = WorkingMemory.from_collection(loaded)
        again = restored.to_collection("Example-Agent")

        self.assertEqual(again, original)
        self.assertNotIn("savedAt", again)
        self.assertNotIn("id", again)

    def test_collection_document_rejects_a_blank_agent_name(self):
        with self.assertRaises(ValueError) as raised:
            WorkingMemory.from_collection({"agentName": "  ", "savedAt": "2026-11-01T00:00:00Z"})
        self.assertEqual(str(raised.exception), "Working memory collection requires an agent name")
        with self.assertRaises(ValueError):
            WorkingMemory.from_collection({})


if __name__ == "__main__":
    unittest.main()
