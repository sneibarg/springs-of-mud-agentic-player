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


if __name__ == "__main__":
    unittest.main()
