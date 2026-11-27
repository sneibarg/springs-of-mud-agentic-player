import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import _begin_play
from memory.KnownCommand import KnownCommand
from memory.PlaySession import PlaySession
from memory.WorkingMemory import WorkingMemory
from play.Bootstrapper import Bootstrapper
from play.CommandAvailability import restore_commands
from play.CommandSituation import assert_learned, available_commands
from play.GameplayEngine import GameplayEngine
from play.HelpReader import parse_command_names
from memory.PlayClock import PlayClock
from play.PlayError import PromptTimeout
from play.WorldKnowledge import HelpTopic, WorldKnowledge
from tests.test_command_situation import _Player
from tests.test_gameplay_engine import _channel, _engine, _Km, _QueueClient


class TestCommandAvailability(unittest.TestCase):
    def test_help_and_saved_knowledge_cannot_authorize_engine_commands(self):
        client = _QueueClient()
        memory = WorkingMemory()
        memory.remember_command("look")
        knowledge = WorldKnowledge()
        knowledge.remember_command("look", help_text="Look.")
        knowledge.remember_help(HelpTopic("flee", "FLEE", "Run away.", ""))
        engine = GameplayEngine(_channel(client), memory, knowledge, _Km())
        self.assertEqual(engine.step(), "")
        self.assertEqual(client.sent, [])

    def test_refresh_revokes_a_verb_even_when_knowledge_and_cached_help_keep_it(self):
        client = _QueueClient()
        engine = _engine(client, _Km('((:args checkpoint other save ""))'), room_current=True, clock=PlayClock(score_count=1, level=1))
        engine.knowledge.remember_command("save", category="other", help_text="Save.")
        engine.memory.observe_commands(["look", "score"])
        self.assertEqual(engine.step(), "")
        self.assertFalse(engine._known("save"))
        self.assertIsNotNone(engine.memory.command_named("save"))
        self.assertIsNotNone(engine.knowledge.commands.named("save"))
        self.assertEqual(client.sent, [])

    def test_danger_and_prohibited_command_rules_still_apply_to_available_verbs(self):
        client = _QueueClient()
        engine = _engine(client, _Km(), room_current=True)
        engine.memory.observe_commands(["quit", "delete", "murder", "steal", "password", "!", "flee"])
        for command in ("quit", "delete", "murder rat", "steal coin rat", "password x", "!"):
            self.assertEqual(engine._accepted(command), "")
        engine.memory.session.combat.fighting = True
        engine.memory.session.combat.hit = 10
        self.assertEqual(engine._choose(), "flee")
        engine.memory.observe_commands([])
        self.assertEqual(engine._choose(), "")

    def test_observed_empty_catalog_clears_the_retained_km_index(self):
        memory = WorkingMemory()
        memory.remember_command("north", category="movement")
        memory.observe_commands([])
        player = _Player("((:seq *Cmd-north))")
        forms = assert_learned(player, memory, WorldKnowledge())
        self.assertEqual(forms, ["(*Player-a-b now-has (som-known-command ((:seq))))"])
        self.assertEqual(player.assertions, forms)
        self.assertIsNotNone(memory.command_named("north"))

    def test_unknown_availability_publishes_nothing_even_with_saved_descriptions(self):
        memory = WorkingMemory()
        memory.remember_command("north", category="movement")
        player = _Player("((:seq *Cmd-north))")
        self.assertEqual(assert_learned(player, memory, WorldKnowledge()), [])
        self.assertEqual(player.queries, [])
        self.assertEqual(player.assertions, [])

    def test_available_projection_keeps_server_order_and_category_precedence(self):
        memory = WorkingMemory()
        memory.remember_command("score", category="information / communication")
        memory.observe_commands(["north", "score"])
        knowledge = WorldKnowledge()
        knowledge.remember_command("score", category="other", help_text="Score.")
        knowledge.remember_command("north", category="movement")
        knowledge.remember_command("east", category="movement")
        knowledge.remember_help(HelpTopic("socials", "SOCIALS", "Smile.", ""))
        self.assertEqual(available_commands(memory, knowledge), [KnownCommand("north", "movement"), KnownCommand("score", "information / communication", "Score.")])

    def test_km_replacement_updates_existing_command_metadata_as_well_as_membership(self):
        memory = WorkingMemory()
        memory.observe_commands(["north"])
        knowledge = WorldKnowledge()
        knowledge.remember_command("north", category="movement", help_text="New help.")
        player = _Player("((:seq *Cmd-north))")
        forms = assert_learned(player, memory, knowledge)
        self.assertIn('(*Cmd-north now-has (instance-of (Som-Known-Command)) (som-command-name (north)) (som-command-category (movement)) (som-command-help ("New help.")))', forms)

    def test_restored_login_verifies_commands_and_binds_one_description_collection(self):
        client = _QueueClient()
        client.pending = ["Welcome.", "<30hp 100m 100mv>"]
        client.on_send["commands"] = ["look          score", "<30hp 100m 100mv>"]
        memory = WorkingMemory()
        memory.remember_command("look", category="objects")
        knowledge = WorldKnowledge()
        knowledge.remember_command("look", category="information", help_text="Look.")
        knowledge.remember_command("north", category="movement")
        channel = _channel(client)
        restore_commands(channel, memory, knowledge)
        self.assertIs(memory.command_knowledge, knowledge.commands)
        self.assertEqual([command.name for command in memory.session.available_commands.records()], ["look", "score"])
        self.assertFalse(memory.session.command_available("north"))
        self.assertEqual(knowledge.commands.named("look"), KnownCommand("look", "objects", "Look."))
        self.assertEqual(memory.session.last_prompt, "<30hp 100m 100mv>")
        self.assertEqual(client.sent, ["commands"])

    def test_help_only_restore_promotes_descriptions_only_after_the_verb_is_observed(self):
        client = _QueueClient()
        client.pending = ["<30hp 100m 100mv>"]
        client.on_send["commands"] = ["look", "<30hp 100m 100mv>"]
        knowledge = WorldKnowledge()
        knowledge.remember_help(HelpTopic("look", "LOOK", "Look around.", ""))
        knowledge.remember_help(HelpTopic("kill", "KILL", "Attack.", ""))
        memory = WorkingMemory()
        restore_commands(_channel(client), memory, knowledge)
        self.assertEqual(knowledge.command_records(), [KnownCommand("look", help_text="Look around.")])
        self.assertTrue(memory.session.command_available("look"))
        self.assertFalse(memory.session.command_available("kill"))

    def test_verification_failure_revokes_previous_availability_without_erasing_help(self):
        client = _QueueClient()
        client.pending = ["<30hp 100m 100mv>"]
        memory = WorkingMemory()
        memory.observe_commands(["north"])
        memory.remember_command("north", help_text="Walk.")
        knowledge = WorldKnowledge()
        with self.assertRaises(PromptTimeout):
            restore_commands(_channel(client), memory, knowledge)
        self.assertFalse(memory.session.commands_observed)
        self.assertFalse(memory.session.command_available("north"))
        self.assertEqual(knowledge.commands.named("north").help_text, "Walk.")

    def test_main_restores_descriptions_but_sends_commands_before_creating_the_engine(self):
        client = _QueueClient()
        client.pending = ["Welcome.", "<30hp 100m 100mv>"]
        client.on_send["commands"] = ["look", "<30hp 100m 100mv>"]
        account = SimpleNamespace(logged_on=True, character=SimpleNamespace(id="c", name="Example"), auth_client=None, session=SimpleNamespace(client=client))
        knowledge = WorldKnowledge()
        knowledge.remember_command("north", category="movement")
        body = knowledge.to_document(character_id="c", character_name="Example", agent_name="Agent")
        memory = WorkingMemory()
        result_engine = object()
        with patch("main._load_knowledge", return_value=(body, True)), patch("main._play_engine", return_value=result_engine) as build, redirect_stdout(io.StringIO()):
            result = _begin_play(account, None, None, SimpleNamespace(telnet_replace_existing="Y"), memory, None, False)
        self.assertIs(result, result_engine)
        self.assertEqual(client.sent, ["commands"])
        self.assertIs(build.call_args.kwargs["channel"].client, client)
        self.assertFalse(build.call_args.kwargs["room_current"])
        self.assertTrue(memory.session.command_available("look"))
        self.assertFalse(memory.session.command_available("north"))

    def test_bootstrap_keeps_help_index_entries_out_of_availability(self):
        memory = WorkingMemory()
        bootstrap = Bootstrapper(None, [], "Example", channel=object(), memory=memory)
        bootstrap._remember_categories([{"name": "movement", "commands": ["north", "east"]}])
        self.assertFalse(memory.session.command_available("north"))
        memory.observe_commands(["north"])
        self.assertIs(memory.command_knowledge, bootstrap.knowledge.commands)
        self.assertTrue(memory.session.command_available("north"))
        self.assertFalse(memory.session.command_available("east"))
        self.assertEqual(bootstrap.knowledge.commands.named("east").category, "movement")

    def test_clear_detaches_the_legacy_view_without_deleting_learned_world_knowledge(self):
        memory = WorkingMemory()
        bootstrap = Bootstrapper(None, [], "Example", channel=object(), memory=memory)
        bootstrap.knowledge.remember_command("north", category="movement")
        memory.observe_commands(["north"])
        memory.clear()
        self.assertFalse(memory.session.command_available("north"))
        self.assertEqual(bootstrap.knowledge.command_records(), [KnownCommand("north", "movement")])

    def test_prose_cannot_be_parsed_as_available_verbs(self):
        self.assertEqual(parse_command_names(["You cannot do that while fighting.", "Huh?", "No help on that word."]), [])
        self.assertEqual(parse_command_names(["look          !          north", "score"]), ["look", "north", "score"])

    def test_session_review_round_trip_preserves_observation_state_but_rejects_string_flags(self):
        session = PlaySession()
        session.observe_commands(["look", "north"])
        restored = PlaySession.from_json(session.to_review())
        self.assertTrue(restored.command_available("look"))
        with self.assertRaises(ValueError):
            PlaySession.from_json({"commandsObserved": "false", "availableCommands": ["kill"]})


if __name__ == "__main__":
    unittest.main()
