import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.Conversation import Conversation
from memory.WorkingMemory import WorkingMemory, default_collection_path
from play.WorldKnowledge import BeingRecord, PlayerRecord, RoomSnapshot, WorldKnowledge



class TestAuras(unittest.TestCase):
    def test_auras_are_kept_on_mobiles_npcs_and_players(self):
        memory = WorkingMemory()
        mobile = memory.remember_mobile("A healer", room_name="Altar", auras=["White Aura"])
        npc = memory.remember_npc("Hassan", room_name="Temple", auras=["Golden Aura"])
        player = memory.remember_player("Fizban", room_name="Altar", auras=["Red Aura", "Pink Aura"])
        self.assertEqual(mobile.auras, ["White Aura"])
        self.assertEqual(npc.auras, ["Golden Aura"])
        self.assertEqual(player.auras, ["Red Aura", "Pink Aura"])

        memory.remember_mobile("A healer")
        self.assertEqual(memory.being_named("A healer").auras, ["White Aura"])
        memory.remember_mobile("A healer", auras=["Pink Aura"])
        self.assertEqual(memory.being_named("A healer").auras, ["Pink Aura"])

        review = memory.to_review()
        self.assertEqual(review["mobiles"][0]["auras"], ["Pink Aura"])
        self.assertEqual(review["npcs"][0]["auras"], ["Golden Aura"])
        self.assertEqual(review["players"][0]["auras"], ["Red Aura", "Pink Aura"])

    def test_absorb_copies_aura_lists(self):
        knowledge = WorldKnowledge()
        knowledge.remember_player(PlayerRecord(name="Fizban", level=60, race="Human", character_class="IMP", room_name="Altar", auras=["White Aura"]))
        knowledge.remember_mobile(BeingRecord(name="A healer", kind="mobile", pose="here", room_name="Altar", auras=["Red Aura", "White Aura"]))
        knowledge.remember_npc(BeingRecord(name="Hassan", kind="npc", pose="here", room_name="Temple", auras=["Golden Aura"]))
        memory = WorkingMemory()
        memory.absorb_world(knowledge)
        self.assertEqual(memory.being_named("Fizban").auras, ["White Aura"])
        self.assertEqual(memory.being_named("A healer").auras, ["Red Aura", "White Aura"])
        self.assertEqual(memory.being_named("Hassan").auras, ["Golden Aura"])

    def test_a_fighting_line_keeps_the_aura_and_drops_other_prefixes(self):
        memory = WorkingMemory()
        seen = memory.observe_line("(Invis) (White Aura) A goblin is here, fighting YOU!", room_name="Temple")
        self.assertEqual(seen.name, "A goblin")
        self.assertTrue(seen.aggressive)
        self.assertEqual(seen.auras, ["White Aura"])


if __name__ == "__main__":
    unittest.main()
