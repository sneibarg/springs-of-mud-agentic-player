import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.WorkingMemory import WorkingMemory
from net.rest.KmAnswer import KmAnswer
from play.CommandSituation import assertion_forms, assert_learned, available_commands
from play.WorldKnowledge import HelpTopic, WorldKnowledge


class _Player:
    def __init__(self, stored="nil"):
        self.name = "Player-a-b"
        self.stored = stored
        self.queries = []
        self.assertions = []

    def query(self, expression):
        self.queries.append(expression)
        return KmAnswer(ok=True, answer=self.stored)

    def assert_expression(self, expression):
        self.assertions.append(expression)
        return KmAnswer(ok=True, answer="(*Player-a-b)")


class TestCommandSituation(unittest.TestCase):
    def test_where_and_bang_are_strings_and_bang_uses_the_hex_frame(self):
        memory = WorkingMemory()
        memory.observe_commands(["north", "where", "!", "delete", "score"])
        memory.remember_command("north")
        memory.remember_command("where")
        memory.remember_command("!", category="other")
        memory.remember_command("delete")
        memory.remember_command("score", category="information / communication", help_text='Say "hi"\\\nnext')
        knowledge = WorldKnowledge()
        knowledge.remember_command("north", category="movement", help_text="Go north.")
        knowledge.remember_command("score", category="other")
        knowledge.remember_command("east", category="movement")
        knowledge.remember_help(HelpTopic(command="socials", keyword="", text="smile", raw=""))
        commands = available_commands(memory, knowledge)
        forms = assertion_forms("Player-a-b", commands)
        text = "\n".join(forms)

        self.assertEqual([command.name for command in commands], ["north", "where", "!", "delete", "score"])
        self.assertNotIn("socials", [command.name for command in commands])
        self.assertEqual(commands[0].category, "movement")
        self.assertEqual(commands[0].help_text, "Go north.")
        self.assertEqual(commands[4].category, "information / communication")
        self.assertIn('(*Cmd-north has (instance-of (Som-Known-Command)) (som-command-name (north)) (som-command-category (movement)) (som-command-help ("Go north.")))', text)
        self.assertIn('(*Cmd-7768657265 has (instance-of (Som-Known-Command)) (som-command-name ("where")))', text)
        self.assertIn('(*Cmd-21 has (instance-of (Som-Known-Command)) (som-command-name ("!")) (som-command-category (other)))', text)
        self.assertIn('(som-command-name ("delete"))', text)
        self.assertIn('(som-command-help ("Say \\"hi\\"\\\\ next"))', text)
        self.assertIn("(som-command-category (\"information / communication\"))", text)
        self.assertNotIn("*Cmd-where", text)
        self.assertNotIn("(som-command-name (where))", text)
        self.assertNotIn("(som-command-name (delete))", text)
        self.assertIn("(*Player-a-b has (som-known-command ((:seq *Cmd-north *Cmd-7768657265 *Cmd-21", text)
        self.assertTrue(text.endswith("*Cmd-score))))"))
        self.assertNotIn("*Cmd-east", text)
        self.assertNotIn("now-has", text)
        self.assertNotIn("in-situation", text)

    def test_a_stored_seq_is_replaced_and_unobserved_availability_asserts_nothing(self):
        memory = WorkingMemory()
        memory.observe_commands(["north"])
        memory.remember_command("north", category="movement")
        player = _Player("((:seq *Cmd-north))")
        forms = assert_learned(player, memory, WorldKnowledge())

        self.assertEqual(player.queries, ["(the som-known-command of *Player-a-b)"])
        self.assertIn("(*Player-a-b now-has (som-known-command ((:seq *Cmd-north))))", forms)
        self.assertEqual(player.assertions, forms)

        empty = _Player()
        self.assertEqual(assert_learned(empty, WorkingMemory(), WorldKnowledge()), [])
        self.assertEqual(empty.queries, [])
        self.assertEqual(empty.assertions, [])


if __name__ == "__main__":
    unittest.main()
