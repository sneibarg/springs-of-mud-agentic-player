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



class TestAbsorbWorld(unittest.TestCase):
    def test_world_snapshot_seeds_players_and_mobiles(self):
        knowledge = WorldKnowledge()
        knowledge.remember_player(PlayerRecord(name="Example", level=1, race="human", character_class="Mag", self_character=True))
        knowledge.remember_player(PlayerRecord(name="Marcus", level=10, race="elf", character_class="War", agentic=True, room_name="Temple"))
        knowledge.remember_mobile(BeingRecord(name="A goblin", kind="mobile", pose="fighting", room_name="Temple", detail="YOU!"))
        knowledge.remember_npc(BeingRecord(name="Guildmaster", kind="npc", pose="here", room_name="Temple"))

        memory = WorkingMemory()
        memory.absorb_world(knowledge)

        self.assertIsNone(memory.being_named("Example"))
        self.assertTrue(memory.being_named("Marcus").agentic)
        self.assertTrue(memory.being_named("A goblin").aggressive)
        self.assertEqual(memory.being_named("Guildmaster").kind, "npc")

    def test_rooms_are_remembered_and_copied_from_the_world(self):
        memory = WorkingMemory()
        altar = memory.remember_room("By the Temple Altar", description="A marble altar.", exits=["south", "up"])
        self.assertEqual(altar.exits, ["south", "up"])
        memory.remember_room("By the Temple Altar")
        self.assertEqual(len(memory.rooms()), 1)
        kept = memory.room_named("BY THE TEMPLE ALTAR")
        self.assertEqual(kept.description, "A marble altar.")
        self.assertEqual(kept.exits, ["south", "up"])
        self.assertEqual(kept.name, "By the Temple Altar")
        rewritten = memory.remember_room("by the temple altar")
        self.assertIs(rewritten, kept)
        self.assertEqual(rewritten.name, "by the temple altar")
        self.assertEqual(rewritten.description, "A marble altar.")

        knowledge = WorldKnowledge()
        knowledge.room = RoomSnapshot(name="The Temple Of Mota", description="Stone hall.", exits=["north"])
        memory.absorb_world(knowledge)
        memory.absorb_world(knowledge)
        self.assertEqual(len(memory.rooms()), 2)
        self.assertEqual(memory.room_named("The Temple Of Mota").description, "Stone hall.")
        self.assertEqual(memory.room_named("The Temple Of Mota").exits, ["north"])
        self.assertEqual(memory.to_review()["rooms"][0]["name"], "by the temple altar")

        with self.assertRaises(ValueError):
            memory.remember_room("   ")


if __name__ == "__main__":
    unittest.main()
