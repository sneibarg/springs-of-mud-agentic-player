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



class TestCommands(unittest.TestCase):
    def test_commands_stay_in_the_order_the_server_offered(self):
        memory = WorkingMemory()
        remembered = memory.remember_commands(["look", "help", "look", "WHO"])
        self.assertEqual([command.name for command in remembered], ["look", "help", "look", "who"])
        self.assertEqual([command.name for command in memory.commands()], ["look", "help", "who"])
        self.assertEqual(memory.command_named("Look").category, "")

        memory.remember_command("look", category="information", help_text="Look around.")
        memory.remember_command("look")
        self.assertEqual(memory.command_named("LOOK").category, "information")
        self.assertEqual(memory.command_named("look").help_text, "Look around.")
        memory.absorb_world(WorldKnowledge())
        self.assertEqual([command.name for command in memory.commands()], ["look", "help", "who"])
        self.assertEqual(memory.to_review()["commands"][0], {"name": "look", "category": "information", "help_text": "Look around."})

        with self.assertRaises(ValueError):
            memory.remember_command("   ")


if __name__ == "__main__":
    unittest.main()
