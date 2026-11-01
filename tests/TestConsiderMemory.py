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



class TestConsiderMemory(unittest.TestCase):
    def test_consider_verdicts_match_the_server_lines(self):
        memory = WorkingMemory()
        cases = [("goblin", "You can kill a goblin naked and weaponless.", "naked", "safe", "a goblin"), ("guard", "The guard is no match for you.", "no_match", "safe", "The guard"), ("orc", "An orc looks like an easy kill.", "easy_kill", "safe", "An orc"), ("bandit", "The perfect match!", "even", "even", "bandit"), ("knight", "A knight says 'Do you feel lucky, punk?'.", "lucky", "risky", "A knight"), ("dragon", "The dragon laughs at you mercilessly.", "laughs", "risky", "The dragon"), ("titan", "Death will thank you for your gift.", "death", "fatal", "titan")]
        for target, line, verdict, outlook, subject in cases:
            reading = memory.remember_consider(target, [line], kind="mobile")
            self.assertEqual(reading.verdict, verdict)
            self.assertEqual(reading.outlook, outlook)
            self.assertEqual(reading.subject, subject)
            self.assertTrue(reading.estimated)
            self.assertIs(memory.consider_for(target), reading)

    def test_missing_target_is_remembered_without_an_estimate(self):
        memory = WorkingMemory()
        reading = memory.remember_consider("ghost", ["They're not here."], kind="mobile")
        self.assertEqual(reading.verdict, "refused")
        self.assertEqual(reading.outlook, "unknown")
        self.assertFalse(reading.estimated)
        self.assertIsNone(memory.being_named("ghost"))

    def test_agentic_player_consider_is_stored_on_that_player(self):
        memory = WorkingMemory()
        reading = memory.remember_consider("Marcus", ["The perfect match!"], kind="player", agentic=True)
        self.assertEqual(reading.kind, "agentic")
        marcus = memory.being_named("Marcus")
        self.assertTrue(marcus.agentic)
        self.assertEqual(memory.agentic_players(), [marcus])
        self.assertEqual(memory.players(), [])


if __name__ == "__main__":
    unittest.main()
