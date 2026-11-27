import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import _begin_play
from memory.EvidenceJournal import EvidenceJournal
from memory.PlaySession import PlaySession
from memory.WorkingMemory import WorkingMemory
from net.rest.KmAnswer import KmAnswer
from net.rest.KmClient import KmError
from net.rest.OllamaClient import OllamaError
from play.BootstrapCompletion import BootstrapCompletion
from play.Bootstrapper import Bootstrapper
from play.CommandAvailability import restore_commands
from play.CommandChannel import CommandChannel
from play.GameplayEngine import GameplayEngine
from play.ObservationPipeline import ObservationPipeline
from play.PlayError import PromptTimeout
from play.WorldKnowledge import WorldKnowledge
from prompt.Prompt import Prompt
from tests.test_bootstrapper import _Clock, _Model, _ScriptedClient


class _Player:
    def __init__(self, name="Player-account-Example"):
        self.name = name
        self.forms = []
        self.answer = KmAnswer(True, "t")

    def assert_expression(self, form):
        self.forms.append(form)
        return self.answer


def _bootstrap(*, memory=None, player=None, defer=True, model=None, replies=None, request_prompt=False):
    pages = {"help": ["INFORMATION", "look"], "commands": ["look          help"], "help look": ["LOOK", "Look around."], "help help": ["HELP", "Read help."], "areas": ["[1-5] Romy: Temple"], "who": ["[1 human Mag] Example the agent", "Players found: 1"], "look": ["Temple", "A quiet temple.", "Obvious exits:", "North", "rat is here."]}
    pages.update(replies or {})
    client = _ScriptedClient([] if request_prompt else ["Welcome.", "<10hp 10m 10mv>"], pages)
    clock = _Clock()
    channel = CommandChannel(client, timeout_s=0.2, clock=clock, sleep=clock.sleep)
    prompts = {name: Prompt(name=name, model="test", system=name, user="{" + name + "}", json_schema={"type": "object"}, tokens={}) for name in ("categories", "commands", "help", "look")}
    bootstrap = Bootstrapper(None, ["Example"], "Example", channel=channel, memory=memory, player=player, defer=defer, prompts=prompts, ollama=model, request_prompt=request_prompt)
    return bootstrap, client


class TestSessionEvidence(unittest.TestCase):
    def test_journal_snapshots_are_ordered_and_detached_from_inputs_and_reads(self):
        journal = EvidenceJournal()
        data = {"names": ["rat", "rat"]}
        first = journal.append("room", origin="bootstrap", lines=["Temple"], payload=data, transferable=True)
        second = journal.append("model_enrichment", origin="bootstrap", source="model", source_ids=[first.observation_id])
        data["names"].clear()
        first.payload["names"].clear()
        self.assertEqual(first.payload["names"], ["rat", "rat"])
        self.assertEqual([record.sequence for record in journal.records], [1, 2])
        self.assertEqual(second.source_ids, (first.observation_id,))
        self.assertIn("+00:00", first.observed_at)
        with self.assertRaises(ValueError):
            journal.append("model_enrichment", origin="bootstrap", source_ids=["other:1"])
        with self.assertRaises(ValueError):
            journal.acknowledge([first.observation_id, "other:1"])
        self.assertEqual(journal.accepted_ids, set())
        with self.assertRaises(ValueError):
            journal.acknowledge([second.observation_id])

    def test_local_review_round_trip_preserves_queue_and_acceptance_but_legacy_does_not(self):
        bootstrap, _client = _bootstrap()
        bootstrap.bootstrap()
        journal = bootstrap.memory.session.evidence
        journal.acknowledge([journal.pending()[0].observation_id])
        review = json.loads(json.dumps(bootstrap.memory.session.to_review()))
        self.assertEqual(PlaySession.from_json(review).to_review(), review)
        body = bootstrap.memory.to_collection("Agent")
        self.assertNotIn("session", body)
        body["session"] = review
        restored = WorkingMemory.from_collection(body)
        self.assertEqual(restored.session.evidence.records, [])
        self.assertEqual(restored.session.bootstrap.status, "not_started")

    def test_both_defer_modes_retain_raw_help_and_queue_source_linked_evidence(self):
        def answer(body):
            if body["system"] == "categories":
                return json.dumps({"categories": [{"name": "information", "commands": ["look", "invented"]}]})
            if body["system"] == "commands":
                return '{"commands": ["invented"]}'
            if body["system"] == "look":
                return '{"items": []}'
            return '{"missing": false, "topics": [{"keyword": "LOOK", "text": "Enriched help."}], "category": "information"}'

        for defer in (True, False):
            with self.subTest(defer=defer):
                model = _Model(answer)
                bootstrap, client = _bootstrap(defer=defer, model=model, replies={"help invented": ["No help on that word."]})
                knowledge = bootstrap.bootstrap()
                journal = bootstrap.memory.session.evidence
                self.assertEqual(knowledge.help_for("look").raw, "LOOK\nLook around.")
                self.assertTrue(knowledge.commands.named("look").help_text)
                self.assertTrue(bootstrap.memory.session.command_available("look"))
                self.assertFalse(bootstrap.memory.session.command_available("invented"))
                self.assertEqual(bootstrap.memory.session.bootstrap.status, "awaiting_acceptance")
                self.assertEqual(journal.accepted_ids, set())
                self.assertEqual([record.command for record in journal.records if record.kind == "server_response"], ["login"] + client.sent)
                raw_help = next(record for record in journal.records if record.kind == "help" and record.command == "help look")
                self.assertEqual(raw_help.payload["text"], "Look around.")
                model_records = [record for record in journal.records if record.source == "model"]
                self.assertEqual(bool(model_records), not defer)
                if not defer:
                    enrichment = next(record for record in model_records if record.command == "help look")
                    self.assertEqual(enrichment.source_ids, (raw_help.observation_id,))
                    self.assertEqual(enrichment.payload["help"]["text"], "Enriched help.")

    def test_partial_room_cannot_be_completed_even_when_every_record_is_acknowledged(self):
        player = _Player()
        bootstrap, _client = _bootstrap(player=player, replies={"look": ["Temple", "A quiet temple."]})
        bootstrap.bootstrap()
        journal = bootstrap.memory.session.evidence
        journal.acknowledge(record.observation_id for record in journal.pending())
        self.assertEqual(bootstrap.memory.session.bootstrap.status, "incomplete")
        self.assertFalse(bootstrap.memory.session.room.current)
        self.assertFalse(BootstrapCompletion(bootstrap.memory).publish(player))
        self.assertEqual(player.forms, [f"(*{player.name} now-has (som-bootstrap (f)))"])

    def test_completion_requires_all_records_then_publishes_once(self):
        player = _Player()
        bootstrap, _client = _bootstrap(player=player)
        bootstrap.bootstrap()
        progress = bootstrap.memory.session.bootstrap
        journal = bootstrap.memory.session.evidence
        completion = BootstrapCompletion(bootstrap.memory)
        self.assertFalse(completion.publish(player))
        journal.acknowledge(progress.required_ids[1:])
        self.assertFalse(completion.publish(player))
        journal.acknowledge(progress.required_ids[:1])
        self.assertTrue(completion.publish(player))
        self.assertTrue(completion.publish(player))
        self.assertEqual(player.forms, [f"(*{player.name} now-has (som-bootstrap (f)))", f"(*{player.name} now-has (som-bootstrap (t)))"])
        self.assertEqual(progress.status, "complete")

    def test_reasoning_errors_and_wrong_player_never_mark_completion(self):
        player = _Player()
        bootstrap, _client = _bootstrap(player=player)
        bootstrap.bootstrap()
        progress = bootstrap.memory.session.bootstrap
        bootstrap.memory.session.evidence.acknowledge(progress.required_ids)
        completion = BootstrapCompletion(bootstrap.memory)
        with self.assertRaises(KmError):
            completion.publish(_Player("Player-other"))
        player.answer = KmAnswer(True, "nil", errors=("reasoning failed",))
        with self.assertRaises(KmError):
            completion.publish(player)
        self.assertEqual(progress.status, "awaiting_acceptance")
        player.answer = KmAnswer(True, "t")
        self.assertTrue(completion.publish(player))

    def test_reset_failure_retains_local_evidence_and_retries_before_completion(self):
        player = _Player()
        player.answer = KmAnswer(False, "nil", message="unavailable")
        bootstrap, _client = _bootstrap(player=player)
        bootstrap.bootstrap()
        progress = bootstrap.memory.session.bootstrap
        self.assertFalse(progress.marker_reset)
        self.assertEqual(progress.error, "unavailable")
        bootstrap.memory.session.evidence.acknowledge(progress.required_ids)
        player.answer = KmAnswer(True, "t")
        BootstrapCompletion(bootstrap.memory).publish(player)
        self.assertTrue(progress.marker_reset)
        self.assertEqual(player.forms[-2:], [f"(*{player.name} now-has (som-bootstrap (f)))", f"(*{player.name} now-has (som-bootstrap (t)))"])

    def test_interrupted_bootstrap_keeps_prior_and_partial_evidence(self):
        bootstrap, client = _bootstrap()
        send = client.send_line

        def interrupt(command):
            if command == "areas":
                client.sent.append(command)
                client._pending.extend(["[1-5] Romy: Temple"])
                client.connected = False
            else:
                send(command)

        client.send_line = interrupt
        with self.assertRaises(PromptTimeout):
            bootstrap.bootstrap()
        progress = bootstrap.memory.session.bootstrap
        self.assertEqual(progress.status, "incomplete")
        self.assertTrue(progress.stages["commands"])
        self.assertTrue(progress.stages["help"])
        self.assertFalse(progress.stages["areas"])
        partial = bootstrap.memory.session.evidence.records[-1]
        self.assertEqual(partial.command, "areas")
        self.assertEqual(partial.lines, ("[1-5] Romy: Temple",))
        self.assertFalse(partial.payload["complete"])
        self.assertEqual(bootstrap.knowledge.areas, {})

    def test_model_failure_keeps_server_knowledge_without_blocking_collection(self):
        def fail(_body):
            raise OllamaError("offline")

        bootstrap, _client = _bootstrap(defer=False, model=_Model(fail))
        knowledge = bootstrap.bootstrap()
        self.assertEqual(bootstrap.memory.session.bootstrap.status, "awaiting_acceptance")
        self.assertEqual(knowledge.commands.named("look").help_text, "Look around.")
        model_records = [record for record in bootstrap.memory.session.evidence.records if record.source == "model"]
        self.assertTrue(model_records)
        self.assertTrue(all(not record.payload["applied"] and record.payload["error"] == "offline" for record in model_records))

    def test_forced_bootstrap_keeps_stream_history_and_resets_attempt_requirements(self):
        memory = WorkingMemory()
        player = _Player()
        first, _client = _bootstrap(memory=memory, player=player)
        first.bootstrap()
        old_ids = list(memory.session.bootstrap.required_ids)
        old_attempt = memory.session.bootstrap.attempt_id
        stream = memory.session.evidence.stream_id
        memory.session.evidence.acknowledge(old_ids)
        BootstrapCompletion(memory).publish(player)
        second, client = _bootstrap(memory=memory, player=player, request_prompt=True)
        second.bootstrap()
        self.assertEqual(client.sent[0], "")
        self.assertEqual(memory.session.evidence.stream_id, stream)
        self.assertNotEqual(memory.session.bootstrap.attempt_id, old_attempt)
        self.assertFalse(set(old_ids) & set(memory.session.bootstrap.required_ids))
        self.assertFalse(BootstrapCompletion(memory).publish(player))
        self.assertEqual(player.forms[-1], f"(*{player.name} now-has (som-bootstrap (f)))")

    def test_bootstrap_and_gameplay_share_replacement_and_the_same_pending_queue(self):
        bootstrap, client = _bootstrap()
        knowledge = bootstrap.bootstrap()
        memory = bootstrap.memory
        first = next(record for record in memory.session.evidence.records if record.kind == "room")
        required = list(memory.session.bootstrap.required_ids)
        engine = GameplayEngine(bootstrap.channel, memory, knowledge, None)
        engine._observe(["Temple", "Obvious exits:", "None."], "look")
        last = memory.session.evidence.records[-1]
        self.assertEqual(last.origin, "gameplay")
        self.assertEqual(last.kind, first.kind)
        self.assertEqual(last.payload["beings"], [])
        self.assertEqual(memory.current_beings(), [])
        self.assertEqual(knowledge.room.exits, [])
        self.assertEqual(len(first.payload["beings"]), 1)
        self.assertEqual(memory.session.bootstrap.required_ids, required)
        self.assertEqual(memory.session.evidence.pending(), [record for record in memory.session.evidence.records if record.transferable])

    def test_areas_and_who_do_not_establish_exploration_or_current_presence(self):
        memory = WorkingMemory()
        knowledge = WorldKnowledge()
        observations = ObservationPipeline(memory, knowledge, agent_character_names=["Other"], self_character="Example")
        areas = observations.receive(["[1-5] Romy: Temple"], "areas", origin="gameplay")
        who = observations.receive(["[1 human Mag] Other the wanderer"], "who", origin="gameplay")
        self.assertEqual(areas.kind, "listed_areas")
        self.assertNotIn("explored", areas.payload["areas"][0])
        self.assertEqual(who.kind, "players")
        self.assertTrue(who.payload["players"][0]["agentic"])
        self.assertEqual(memory.current_beings(), [])
        self.assertFalse(memory.session.room.current)

    def test_help_examples_do_not_become_current_room_or_combat(self):
        memory = WorkingMemory()
        observations = ObservationPipeline(memory, WorldKnowledge())
        record = observations.receive(["Temple", "Obvious exits:", "None.", "rat is here, fighting YOU!"], "help look", origin="gameplay")
        self.assertEqual(record.kind, "help")
        self.assertFalse(memory.session.combat.fighting)
        self.assertFalse(memory.session.room.current)
        self.assertEqual(memory.current_beings(), [])

    def test_restored_command_verification_uses_common_evidence_queue(self):
        bootstrap, client = _bootstrap()
        memory = WorkingMemory()
        knowledge = WorldKnowledge()
        knowledge.remember_command("look", help_text="Remembered help.")
        restore_commands(bootstrap.channel, memory, knowledge)
        self.assertEqual(client.sent, ["commands"])
        self.assertEqual([record.kind for record in memory.session.evidence.records], ["server_response", "login", "server_response", "commands"])
        self.assertTrue(all(record.origin == "restore" for record in memory.session.evidence.records))
        self.assertEqual(memory.session.bootstrap.status, "not_started")

    def test_missing_required_pages_remain_incomplete(self):
        for command in ("commands", "help look", "areas", "who"):
            with self.subTest(command=command):
                bootstrap, _client = _bootstrap(replies={command: []})
                bootstrap.bootstrap()
                self.assertEqual(bootstrap.memory.session.bootstrap.status, "incomplete")

    def test_delayed_model_evidence_retains_its_source_and_is_not_applied(self):
        bootstrap, _client = _bootstrap(defer=False)
        bootstrap._observe_room(["Temple", "There is a sign.", "Obvious exits:", "None."])
        source = bootstrap.memory.session.evidence.records[-1]

        def delayed(_body):
            bootstrap._observe_room(["Temple", "Obvious exits:", "None."])
            return '{"items": [{"name": "sign", "source": "description", "line": "There is a sign."}]}'

        bootstrap._ollama = _Model(delayed)
        bootstrap._send_room_prompts(["Temple", "There is a sign.", "Obvious exits:", "None."])
        record = bootstrap.memory.session.evidence.records[-1]
        self.assertEqual(record.source_ids, (source.observation_id,))
        self.assertEqual(record.payload["revision"], source.payload["visit"]["revision"])
        self.assertFalse(record.payload["applied"])
        self.assertEqual(bootstrap.memory.room_by_id(bootstrap.memory.session.room.room_id).items, [])

    def test_interrupted_gameplay_queues_partial_reply_without_replacing_presence(self):
        bootstrap, client = _bootstrap()
        bootstrap.bootstrap()
        memory = bootstrap.memory
        engine = GameplayEngine(bootstrap.channel, memory, bootstrap.knowledge, None)
        original_ids = list(memory.session.room.occupant_ids)
        memory.session.room.current = False

        def interrupted(command):
            client._pending.extend(["Temple", "Obvious exits:"])
            client.connected = False

        client.send_line = interrupted
        with self.assertRaises(PromptTimeout):
            engine.step()
        partial = memory.session.evidence.records[-1]
        self.assertEqual(partial.origin, "gameplay")
        self.assertEqual(partial.command, "look")
        self.assertFalse(partial.payload["complete"])
        self.assertEqual(memory.session.room.occupant_ids, original_ids)
        self.assertIsNotNone(memory.session.pending_action)

    def test_missing_login_prompt_keeps_only_partial_evidence_and_unknown_availability(self):
        bootstrap, client = _bootstrap()
        client._pending = ["Welcome."]
        client.connected = False
        with self.assertRaises(PromptTimeout):
            bootstrap.bootstrap()
        self.assertEqual(client.sent, [])
        self.assertFalse(bootstrap.memory.session.commands_observed)
        self.assertEqual(bootstrap.memory.session.bootstrap.status, "incomplete")
        self.assertFalse(bootstrap.memory.session.evidence.records[-1].payload["complete"])

    def test_main_reuses_bootstrap_channel_without_legacy_room_import_or_early_completion(self):
        bootstrap, _client = _bootstrap()
        memory = bootstrap.memory
        account = SimpleNamespace(logged_on=True, character=SimpleNamespace(id="c", name="Example"), auth_client=None, session=None)
        config = SimpleNamespace(telnet_replace_existing="Y", ollama_base_url="http://unused", ollama_path="/unused", defer_bootstrap=True)
        registry = SimpleNamespace(all=lambda: [SimpleNamespace(character_name="Example")])
        with patch("main.Bootstrapper", return_value=bootstrap), patch("main._save_knowledge"), patch("main._load_prompts", return_value={}), patch("main._play_engine", return_value="engine") as build, redirect_stdout(io.StringIO()):
            result = _begin_play(account, registry, SimpleNamespace(name="Agent"), config, memory, None, False, force=True)
        self.assertEqual(result, "engine")
        self.assertIs(build.call_args.kwargs["channel"], bootstrap.channel)
        self.assertFalse(build.call_args.kwargs["room_current"])
        self.assertEqual(memory.session.bootstrap.status, "awaiting_acceptance")
        self.assertEqual(memory.session.evidence.accepted_ids, set())


if __name__ == "__main__":
    unittest.main()
