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



class TestConversations(unittest.TestCase):
    def test_a_conversation_keeps_topic_participants_location_and_interest(self):
        memory = WorkingMemory()
        gossip = memory.remember_conversation("the caravan", "channel", "gossip", participants=["Marcus", "marcus", "  ", "Sam"], interest=2)
        tells = memory.remember_conversation("where is the key", "tells", "Sam", participants=["Sam"])
        room = memory.remember_conversation("the gate", "ROOM", "The Temple Of Mota", participants=["Guard"], interest=5)

        self.assertIs(memory.conversation_for("The Caravan", "Channel", "Gossip"), gossip)
        self.assertEqual(gossip.participants, ["Marcus", "Sam"])
        self.assertEqual(gossip.location, "channel")
        self.assertEqual(tells.interest, 0)
        self.assertEqual(room.location, "room")
        self.assertEqual([item.topic for item in memory.conversations()], ["the gate", "the caravan", "where is the key"])

        memory.remember_conversation("the caravan", "channel", "gossip")
        self.assertEqual(gossip.interest, 2)
        self.assertEqual(gossip.participants, ["Marcus", "Sam"])
        memory.remember_conversation("the caravan", "channel", "gossip", participants=["Fizban"], interest=1)
        self.assertEqual(gossip.participants, ["Fizban"])
        self.assertEqual(gossip.set_interest(4), 4)
        self.assertEqual([item.topic for item in memory.conversations()], ["the gate", "the caravan", "where is the key"])

        review = memory.to_review()["conversations"]
        self.assertEqual(review[1]["location_name"], "gossip")
        document = memory.to_collection("example-agent")
        self.assertEqual(document["conversations"][1]["locationName"], "gossip")
        self.assertEqual(document["conversations"][1]["interest"], 4)
        self.assertNotIn("location_name", document["conversations"][1])

        loaded = Conversation.from_json({"topic": "the gate", "location": "room", "locationName": "The Temple Of Mota", "participants": ["Guard"], "interest": 5})
        self.assertEqual(loaded.location_name, "The Temple Of Mota")
        self.assertEqual(loaded.interest, 5)

    def test_conversation_rejects_a_blank_topic_bad_location_or_non_integer_interest(self):
        memory = WorkingMemory()
        with self.assertRaises(ValueError):
            memory.remember_conversation("   ", "room", "Temple")
        with self.assertRaises(ValueError):
            memory.remember_conversation("the gate", "whisper", "Temple")
        with self.assertRaises(ValueError):
            memory.remember_conversation("the gate", "room", "   ")
        with self.assertRaises(ValueError):
            memory.remember_conversation("the gate", "room", "Temple", interest=True)
        with self.assertRaises(TypeError):
            Conversation.from_json(["the gate"])
        self.assertEqual(memory.conversations(), [])


if __name__ == "__main__":
    unittest.main()
