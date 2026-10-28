import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.WorkingMemory import WorkingMemory
from play.WorldKnowledge import BeingRecord, PlayerRecord, RoomSnapshot, WorldKnowledge


class TestConsiderMemory(unittest.TestCase):
    def test_consider_verdicts_match_the_server_lines(self):
        memory = WorkingMemory()
        cases = [
            ("goblin", "You can kill a goblin naked and weaponless.", "naked", "safe", "a goblin"),
            ("guard", "The guard is no match for you.", "no_match", "safe", "The guard"),
            ("orc", "An orc looks like an easy kill.", "easy_kill", "safe", "An orc"),
            ("bandit", "The perfect match!", "even", "even", "bandit"),
            ("knight", "A knight says 'Do you feel lucky, punk?'.", "lucky", "risky", "A knight"),
            ("dragon", "The dragon laughs at you mercilessly.", "laughs", "risky", "The dragon"),
            ("titan", "Death will thank you for your gift.", "death", "fatal", "titan"),
        ]
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
        memory.clear()
        self.assertEqual(memory.mobiles(), [])
        self.assertEqual(memory.rooms(), [])
        self.assertEqual(memory.commands(), [])
        self.assertIsNone(memory.consider_for("a wolf"))


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
        self.assertEqual(
            memory.to_review()["commands"][0],
            {"name": "look", "category": "information", "help_text": "Look around."},
        )

        with self.assertRaises(ValueError):
            memory.remember_command("   ")


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
        knowledge.remember_player(PlayerRecord(
            name="Fizban", level=60, race="Human", character_class="IMP", room_name="Altar", auras=["White Aura"]
        ))
        knowledge.remember_mobile(BeingRecord(
            name="A healer", kind="mobile", pose="here", room_name="Altar", auras=["Red Aura", "White Aura"]
        ))
        knowledge.remember_npc(BeingRecord(
            name="Hassan", kind="npc", pose="here", room_name="Temple", auras=["Golden Aura"]
        ))
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


class TestAbsorbWorld(unittest.TestCase):
    def test_world_snapshot_seeds_players_and_mobiles(self):
        knowledge = WorldKnowledge()
        knowledge.remember_player(PlayerRecord(
            name="Example", level=1, race="human", character_class="Mag", self_character=True
        ))
        knowledge.remember_player(PlayerRecord(
            name="Marcus", level=10, race="elf", character_class="War", agentic=True, room_name="Temple"
        ))
        knowledge.remember_mobile(BeingRecord(
            name="A goblin", kind="mobile", pose="fighting", room_name="Temple", detail="YOU!"
        ))
        knowledge.remember_npc(BeingRecord(name="Guildmaster", kind="npc", pose="here", room_name="Temple"))

        memory = WorkingMemory()
        memory.absorb_world(knowledge)

        self.assertIsNone(memory.being_named("Example"))
        self.assertTrue(memory.being_named("Marcus").agentic)
        self.assertTrue(memory.being_named("A goblin").aggressive)
        self.assertEqual(memory.being_named("Guildmaster").kind, "npc")

    def test_rooms_are_remembered_and_copied_from_the_world(self):
        memory = WorkingMemory()
        altar = memory.remember_room(
            "By the Temple Altar",
            description="A marble altar.",
            exits=["south", "up"],
        )
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


if __name__ == "__main__":
    unittest.main()
