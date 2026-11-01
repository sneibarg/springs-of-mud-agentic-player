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



class TestAggressiveMobiles(unittest.TestCase):
    def test_a_mobile_fighting_you_is_aggressive(self):
        memory = WorkingMemory()
        memory.remember_mobile("a goblin", room_name="Temple")
        seen = memory.observe_line("A goblin is here, fighting YOU!", room_name="Temple")
        self.assertTrue(seen.aggressive)
        self.assertEqual(memory.aggressive_mobiles(), [seen])

    def test_seeing_the_mobile_again_keeps_the_aggressive_flag(self):
        memory = WorkingMemory()
        memory.note_aggressive("a wolf", room_name="Road")
        memory.remember_mobile("a wolf", room_name="Road")
        self.assertTrue(memory.being_named("a wolf").aggressive)

    def test_clear_drops_the_session(self):
        memory = WorkingMemory()
        memory.note_aggressive("a wolf")
        memory.remember_consider("a wolf", ["A wolf looks like an easy kill."], kind="mobile")
        memory.remember_room("Temple", description="Stone.", exits=["north"])
        memory.remember_commands(["look", "north"])
        memory.remember_conversation("the gate", "room", "Temple", participants=["Marcus"])
        memory.clear()
        self.assertEqual(memory.mobiles(), [])
        self.assertEqual(memory.rooms(), [])
        self.assertEqual(memory.commands(), [])
        self.assertEqual(memory.conversations(), [])
        self.assertIsNone(memory.consider_for("a wolf"))


if __name__ == "__main__":
    unittest.main()
