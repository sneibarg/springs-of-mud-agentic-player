import os
import sys
import unittest
from dataclasses import FrozenInstanceError, asdict


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.CommandList import CommandList
from memory.KnownCommand import KnownCommand
from memory.WorkingMemory import WorkingMemory
from play.WorldKnowledge import HelpTopic, WorldKnowledge


class TestCommandList(unittest.TestCase):
    def test_records_normalize_service_fields_and_are_immutable(self):
        command = KnownCommand.from_json({"name": " LOOK ", "category": " information ", "helpText": " Look around. "})
        self.assertEqual(asdict(command), {"name": "look", "category": "information", "help_text": "Look around."})
        with self.assertRaises(FrozenInstanceError):
            command.name = "kill"
        for name in ("", "  ", None):
            with self.assertRaises(ValueError):
                KnownCommand(name)
        for field in ("category", "helpText"):
            with self.assertRaises(TypeError):
                KnownCommand.from_json({"name": "look", field: False})

    def test_order_is_first_insert_and_blank_fields_preserve_descriptions(self):
        commands = CommandList()
        commands.remember("LOOK", category="information", help_text="Look around.")
        commands.remember("north")
        commands.remember("look", category=" ", help_text="")
        self.assertEqual([command.name for command in commands.records()], ["look", "north"])
        self.assertEqual(commands.named(" LOOK "), KnownCommand("look", "information", "Look around."))
        commands.remember("look", category="objects")
        self.assertEqual(commands.named("look"), KnownCommand("look", "objects", "Look around."))

    def test_merge_keeps_primary_order_and_nonblank_fields_then_appends_fallback(self):
        primary = CommandList.from_json([{"name": "score", "category": "information"}, {"name": "north"}])
        fallback = CommandList.from_json([{"name": "north", "category": "movement", "helpText": "Walk."}, {"name": "score", "category": "other", "helpText": "Score."}, {"name": "east"}])
        merged = primary.merged_with(fallback)
        self.assertEqual(merged.records(), [KnownCommand("score", "information", "Score."), KnownCommand("north", "movement", "Walk."), KnownCommand("east")])
        self.assertEqual(primary.named("north").category, "")
        self.assertEqual(fallback.named("score").category, "other")

    def test_replace_is_atomic_and_safe_when_replacing_from_its_own_records(self):
        commands = CommandList.from_json([{"name": "look"}, {"name": "north"}])
        commands.replace(commands.records())
        self.assertEqual([command.name for command in commands.records()], ["look", "north"])
        with self.assertRaises(TypeError):
            commands.replace([KnownCommand("score"), {"name": "kill"}])
        self.assertEqual([command.name for command in commands.records()], ["look", "north"])
        commands.replace([])
        self.assertEqual(commands.records(), [])

    def test_returned_record_lists_cannot_mutate_catalog_membership(self):
        commands = CommandList.from_json([{"name": "look"}])
        commands.records().clear()
        self.assertEqual(commands.records(), [KnownCommand("look")])

    def test_both_aggregates_use_the_same_value_and_collection_rules(self):
        memory = WorkingMemory()
        knowledge = WorldKnowledge()
        memory.remember_command("LOOK", category="information", help_text="Look.")
        knowledge.remember_command("LOOK", category="information", help_text="Look.")
        memory.remember_command("look")
        knowledge.remember_command("look")
        self.assertIsInstance(memory.command_knowledge, CommandList)
        self.assertIsInstance(knowledge.commands, CommandList)
        self.assertEqual(memory.commands(), knowledge.command_records())
        self.assertIsInstance(memory.command_named("look"), KnownCommand)
        self.assertFalse(memory.session.command_available("look"))

    def test_help_only_knowledge_has_an_explicit_legacy_fallback_but_no_command_rows(self):
        knowledge = WorldKnowledge()
        knowledge.remember_help(HelpTopic("look", "LOOK", "Look around.", ""))
        self.assertTrue(knowledge.has_commands())
        self.assertEqual(knowledge.command_records(), [])
        self.assertEqual(knowledge.commands_from_help(), [KnownCommand("look", help_text="Look around.")])
        self.assertEqual(knowledge.to_document(character_id="c", character_name="Example", agent_name="Agent")["commands"], [])
        self.assertIn("0 commands, 0 categorized", WorldKnowledge.summary(knowledge))

    def test_live_availability_order_does_not_erase_unavailable_description_history(self):
        memory = WorkingMemory()
        memory.remember_command("retired", category="other", help_text="Old help.")
        memory.remember_command("look", category="objects")
        memory.observe_commands(["NORTH", "look", "north"])
        self.assertEqual([command.name for command in memory.session.available_commands.records()], ["north", "look"])
        self.assertEqual([command.name for command in memory.commands()], ["north", "look", "retired"])
        memory.observe_commands(["look"])
        self.assertFalse(memory.session.command_available("north"))
        self.assertTrue(memory.session.command_available("look"))
        self.assertEqual(memory.command_named("retired").help_text, "Old help.")
        self.assertEqual(memory.command_named("look").category, "objects")

    def test_replacing_cached_descriptions_cannot_grant_or_revoke_availability(self):
        memory = WorkingMemory()
        memory.observe_commands(["look"])
        memory.replace_commands([KnownCommand("kill")])
        self.assertTrue(memory.session.command_available("look"))
        self.assertFalse(memory.session.command_available("kill"))

    def test_legacy_memory_round_trip_preserves_descriptions_without_restoring_permission(self):
        memory = WorkingMemory()
        memory.observe_commands(["look"])
        memory.remember_command("look", category="objects", help_text="Look.")
        body = memory.to_collection("Example")
        restored = WorkingMemory.from_collection(body)
        self.assertEqual(restored.commands(), memory.commands())
        self.assertFalse(restored.session.commands_observed)
        self.assertFalse(restored.session.command_available("look"))
        self.assertNotIn("session", body)


if __name__ == "__main__":
    unittest.main()
