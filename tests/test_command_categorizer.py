import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.WorkingMemory import WorkingMemory
from play.CommandCategorizer import CommandCategorizer
from prompt.Prompt import Prompt


class _Client:
    def __init__(self, text: str):
        self.text = text
        self.bodies = []

    def complete(self, body):
        self.bodies.append(body)
        return self.text


def _prompt() -> Prompt:
    return Prompt(
        name="command-category",
        model="gpt-oss:20b",
        system="Categorize the command.",
        user="Command: {command}\n{help}",
        json_schema={"type": "object", "properties": {"category": {"type": "string"}}},
        tokens={},
    )


class TestCommandCategorizer(unittest.TestCase):
    def test_submission_fills_the_command_and_help_without_calling_the_model(self):
        client = _Client('{"category": "movement"}')
        categorizer = CommandCategorizer(client, _prompt())
        submission = categorizer.submission("north", "Walk north.")
        self.assertEqual(client.bodies, [])
        self.assertEqual(submission.user, "Command: north\nWalk north.")
        self.assertEqual(submission.to_request()["model"], "gpt-oss:20b")
        self.assertIn("north", submission.to_request()["user"])

    def test_categorize_stores_the_model_category(self):
        client = _Client('{"category": "movement"}')
        memory = WorkingMemory()
        memory.remember_commands(["north", "look"])
        category = CommandCategorizer(client, _prompt()).categorize(memory, "north", "Walk north.")
        self.assertEqual(category, "movement")
        self.assertEqual(memory.command_named("north").category, "movement")
        self.assertEqual(memory.command_named("look").category, "")
        self.assertEqual(client.bodies[0]["user"], "Command: north\nWalk north.")

    def test_categorize_waits_for_a_prompt_and_a_client(self):
        memory = WorkingMemory()
        with self.assertRaises(RuntimeError):
            CommandCategorizer(prompt=_prompt()).categorize(memory, "look", "Look around.")
        with self.assertRaises(RuntimeError):
            CommandCategorizer(_Client("{}")).submission("look", "Look around.")


if __name__ == "__main__":
    unittest.main()
