import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from play.HelpReader import parse_command_names, parse_help
from play.WorldKnowledge import PlayerRecord
from play.WorldReader import parse_areas, parse_room, parse_who


class TestHelpReader(unittest.TestCase):
    def test_command_columns_become_unique_names(self):
        lines = ["look          help          areas         who           north         look          "]
        self.assertEqual(parse_command_names(lines), ["look", "help", "areas", "who", "north"])

    def test_help_page_keeps_keyword_and_text(self):
        topic = parse_help("look", ["LOOK", "Look at a room, a person, or an object."])
        self.assertEqual(topic.keyword, "LOOK")
        self.assertEqual(topic.text, "Look at a room, a person, or an object.")

    def test_missing_help_is_empty(self):
        topic = parse_help("xyzzy", ["No help on that word."])
        self.assertEqual(topic.keyword, "")
        self.assertEqual(topic.text, "")


class TestWorldReader(unittest.TestCase):
    def test_area_columns_keep_level_author_and_name(self):
        left = f"{'[1-5] Romy: Temple of Mota':<39}"
        right = "[10-20] Kahn: Midgaard"
        areas = parse_areas([left + right])
        self.assertEqual(areas[0].name, "Temple of Mota")
        self.assertEqual(areas[0].author, "Romy")
        self.assertEqual(areas[0].level_range, "1-5")
        self.assertEqual(areas[1].name, "Midgaard")
        self.assertEqual(areas[1].author, "Kahn")

    def test_who_marks_agentic_players_and_self(self):
        lines = [
            "[1    human    Mag] Example the new one",
            "[10    elf    War] (Wizi) Marcus the wanderer",
            "Players found: 2",
        ]
        players = parse_who(lines, {"example", "other"}, "Example")
        example = players[0]
        marcus = players[1]
        self.assertTrue(example.agentic)
        self.assertTrue(example.self_character)
        self.assertEqual(example.level, 1)
        self.assertEqual(example.character_class, "Mag")
        self.assertEqual(example.title, "the new one")
        self.assertFalse(marcus.agentic)
        self.assertEqual(marcus.flags, "(Wizi)")
        self.assertFalse(marcus.self_character)

    def test_look_splits_mobiles_npcs_and_players(self):
        players = [
            PlayerRecord(name="Example", level=1, race="human", character_class="Mag", agentic=True, self_character=True)
        ]
        lines = [
            "Temple of Mota",
            "\t\tA quiet stone temple.",
            "    a fountain bubbles quietly.",
            "Obvious exits:",
            "north  Temple Square",
            "east   Market",
            "A goblin warrior is here.",
            "Marcus is sitting here.",
            "Example is here, fighting a goblin warrior.",
        ]
        observation = parse_room(lines, players)
        self.assertEqual(observation.room.name, "Temple of Mota")
        self.assertEqual(observation.room.description, "A quiet stone temple.")
        self.assertEqual(observation.room.exits, ["north", "east"])
        self.assertEqual(observation.room.item_lines, ["a fountain bubbles quietly."])
        self.assertEqual(observation.mobiles[0].name, "A goblin warrior")
        self.assertEqual(observation.mobiles[0].kind, "mobile")
        self.assertEqual(observation.npcs[0].name, "Marcus")
        self.assertEqual(observation.npcs[0].pose, "sitting")
        self.assertEqual(observation.players_present[0].name, "Example")

    def test_look_reads_an_aura_long_description_and_exit_labels(self):
        players = [
            PlayerRecord(name="Fizban", level=60, race="Human", character_class="IMP")
        ]
        lines = [
            "By the Temple Altar",
            "\t\tYou are by the temple altar.",
            "    A pit for sacrifices is in front of the altar.",
            "Fizban is here.",
            "(White Aura) A healer is here, selling spells.",
            "Hassan is here, waiting to dispense some justice.",
            "Obvious exits:",
            "South - The Temple Of Mota",
            "Up    - Head of the Rainbow Bridge",
        ]
        observation = parse_room(lines, players)
        self.assertEqual(observation.room.name, "By the Temple Altar")
        self.assertEqual(observation.room.description, "You are by the temple altar.")
        self.assertEqual(observation.room.exits, ["south", "up"])
        self.assertEqual(observation.room.item_lines, ["A pit for sacrifices is in front of the altar."])
        self.assertEqual(observation.players_present[0].name, "Fizban")
        healer = observation.mobiles[0]
        self.assertEqual(healer.name, "A healer")
        self.assertEqual(healer.kind, "mobile")
        self.assertEqual(healer.pose, "here")
        self.assertEqual(healer.detail, "selling spells.")
        self.assertEqual(healer.auras, ["White Aura"])
        self.assertEqual(observation.npcs[0].name, "Hassan")
        self.assertEqual(observation.npcs[0].pose, "here")
        self.assertEqual(observation.npcs[0].detail, "waiting to dispense some justice.")
        self.assertEqual(observation.npcs[0].auras, [])
        self.assertEqual(players[0].auras, [])

    def test_look_keeps_aura_lists_for_mobiles_npcs_and_players(self):
        players = [
            PlayerRecord(name="Fizban", level=60, race="Human", character_class="IMP")
        ]
        lines = [
            "By the Temple Altar",
            "(Red Aura) (White Aura) A healer is here, selling spells.",
            "(Invis) (Golden Aura) Hassan is here, waiting to dispense some justice.",
            "(Wizi) (Pink Aura) Fizban is resting here.",
        ]
        observation = parse_room(lines, players)
        self.assertEqual(observation.mobiles[0].name, "A healer")
        self.assertEqual(observation.mobiles[0].auras, ["Red Aura", "White Aura"])
        self.assertEqual(observation.npcs[0].name, "Hassan")
        self.assertEqual(observation.npcs[0].auras, ["Golden Aura"])
        self.assertEqual(players[0].auras, ["Pink Aura"])
        self.assertIs(observation.players_present[0], players[0])


if __name__ == "__main__":
    unittest.main()
