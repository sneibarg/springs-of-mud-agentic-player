import json
import os
import sys
import unittest
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.EvidenceJournal import EvidenceJournal
from memory.PendingAction import PendingAction
from memory.WorkingMemory import WorkingMemory
from play.EvidenceMapping import EvidenceMapping
from play.KmEvidenceAdapter import KmEvidenceAdapter
from play.KmSyntax import frame, km_string, player_frame, seq, token, unwrap
from play.ObservationPipeline import ObservationPipeline
from play.WorldKnowledge import WorldKnowledge


def _record(journal, kind, payload, **kwargs):
    return journal.append(kind, origin="gameplay", payload=payload, transferable=True, **kwargs)


def _room(identifier="R1", exits=None):
    return {"room_id": identifier, "name": "Temple", "exit_records": exits or []}


def _visit(identifier="R1", fresh=(), current=True):
    return {"room_id": identifier, "current": current, "fresh": list(fresh)}


def _room_record(journal, room=None, beings=(), **extra):
    room = room or _room()
    return _record(journal, "room", {"room": room, "visit": _visit(room["room_id"]), "complete": True, "beings": list(beings), **extra})


class TestKmEvidenceAdapter(unittest.TestCase):
    def setUp(self):
        self.journal = EvidenceJournal(stream_id="session")
        self.adapter = KmEvidenceAdapter("Player-account-Example")

    def plan(self, record):
        return self.adapter.plan(record, self.journal)

    def text(self, record):
        return "\n".join(self.plan(record).expressions)

    def test_km_encoding_handles_reserved_tokens_quotes_unicode_and_identity_collisions(self):
        self.assertEqual(token("north"), "north")
        self.assertEqual(token("where"), '"where"')
        self.assertEqual(token("delete"), '"delete"')
        self.assertEqual(token("NIL"), '"NIL"')
        self.assertEqual(token("WHERE"), '"WHERE"')
        self.assertEqual(km_string('say "hi"\\\nnext'), '"say \\"hi\\"\\\\ next"')
        self.assertNotEqual(frame("Player-a", "room", "é"), frame("Player-a", "room", "e"))
        self.assertNotEqual(frame("Player-a", "room", "a:b"), frame("Player-a", "room", "a_b"))
        self.assertEqual(seq([]), "(:seq)")
        self.assertEqual(unwrap(" ((:seq north)) "), "(:seq north)")
        for bad in ("Global", "a) (delete", "", "Player a"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                player_frame(bad)

    def test_commands_keep_server_order_and_replace_with_explicit_empty_membership(self):
        first = _record(self.journal, "commands", {"available": ["where", "look", "north"]})
        result = self.plan(first)
        expected = [frame(self.adapter.player_name, "command", first.observation_id + ":" + name) for name in ("where", "look", "north")]
        self.assertEqual(result.status, "mapped")
        self.assertIn(seq(expected), result.expressions[-1])
        self.assertIn('(som-command-name ("where"))', self.text(first))
        self.assertTrue(all(" now-has " in form for form in result.expressions))
        last = _record(self.journal, "commands", {"available": []})
        self.assertIn("(som-known-command ((:seq)))", self.plan(last).expressions[-1])

    def test_help_and_model_categories_do_not_grant_availability(self):
        commands = _record(self.journal, "commands", {"available": ["look"]})
        help_page = _record(self.journal, "help", {"command": "invented", "text": 'Read "this"\\\nnext.'})
        output = self.text(help_page)
        self.assertIn('(som-command-help ("Read \\"this\\"\\\\ next."))', output)
        self.assertNotIn(frame(self.adapter.player_name, "command", help_page.observation_id + ":invented"), self.plan(help_page).expressions[-1])
        model = _record(self.journal, "model_enrichment", {"applied": True, "commands": [{"name": "invented", "category": "movement"}]}, source="model", source_ids=[commands.observation_id], command="commands")
        self.assertIn("(som-command-category (movement))", self.text(model))
        self.assertNotIn(frame(self.adapter.player_name, "command", model.observation_id + ":invented"), self.plan(model).expressions[-1])

    def test_metadata_without_command_observation_has_no_availability_index(self):
        record = _record(self.journal, "help", {"command": "look", "text": "Look around."})
        self.assertNotIn("som-known-command", self.text(record))

    def test_plan_is_deterministic_after_newer_records_and_never_acknowledges(self):
        record = _record(self.journal, "commands", {"available": ["look"]})
        first = self.plan(record)
        _record(self.journal, "commands", {"available": []})
        self.assertEqual(self.plan(record), first)
        self.assertEqual(self.journal.accepted_ids, set())
        self.assertEqual(EvidenceMapping.from_json(json.loads(json.dumps(asdict(first)))), first)

    def test_player_and_stream_frames_are_isolated(self):
        record = _record(self.journal, "commands", {"available": ["look"]})
        other = KmEvidenceAdapter("Player-other-Example").plan(record, self.journal)
        self.assertNotEqual(other.expressions, self.plan(record).expressions)
        other_journal = EvidenceJournal(stream_id="other")
        other_record = _record(other_journal, "commands", {"available": ["look"]})
        self.assertNotEqual(self.adapter.plan(other_record, other_journal).expressions, self.plan(record).expressions)
        with self.assertRaises(ValueError):
            self.adapter.plan(record, other_journal)

    def test_areas_preserve_order_and_do_not_become_explored(self):
        record = _record(self.journal, "listed_areas", {"areas": [{"name": "B", "author": "Romy", "level_range": "1-5"}, {"name": "A", "level_range": ""}]})
        output = self.text(record)
        self.assertIn("(som-level-low (1)) (som-level-high (5))", output)
        self.assertNotIn("som-explored", output)
        self.assertLess(output.index('(som-area-name ("B"))'), output.index('(som-area-name ("A"))'))
        empty = _record(self.journal, "listed_areas", {"areas": []})
        self.assertEqual(self.plan(empty).expressions, ("(*Player-account-Example now-has (som-area ((:seq))))",))

    def test_uninterpreted_area_ranges_are_partial_and_do_not_invent_levels(self):
        record = _record(self.journal, "listed_areas", {"areas": [{"name": "Immortal", "level_range": "IMP"}]})
        self.assertEqual(self.plan(record).status, "partial")
        self.assertNotIn("som-level-low", self.text(record))

    def test_room_ids_not_names_define_identity_and_empty_exits_replace(self):
        first = _room_record(self.journal)
        second = _room_record(self.journal, _room("R2"))
        expected = seq([frame(self.adapter.player_name, "room", "R1"), frame(self.adapter.player_name, "room", "R2")])
        self.assertIn(expected, self.plan(second).expressions[-2] if "som-explored-room" in self.plan(second).expressions[-2] else self.text(second))
        self.assertIn("(som-room-exit ((:seq)))", self.text(second))
        self.assertEqual(self.plan(first).status, "mapped")

    def test_forward_exits_require_destination_observation_and_assessed_door_flags(self):
        edge = {"exit_id": "E1", "direction": "north", "destination_id": "R2", "requires_open": False, "requires_unlock": False}
        _room_record(self.journal, _room("R1", [edge]))
        destination = _room_record(self.journal, _room("R2"))
        output = self.text(destination)
        self.assertIn("(som-exit-to (" + frame(self.adapter.player_name, "room", "R2") + "))", output)
        self.assertIn("(som-requires-open (f)) (som-requires-unlock (f))", output)
        self.assertEqual(output.count("(som-exit-to"), 1)
        self.assertNotIn("(som-exit-direction (south))", output)

    def test_unknown_door_requirements_cannot_become_routable(self):
        edge = {"exit_id": "E1", "direction": "north", "destination_id": "R2", "requires_open": None, "requires_unlock": None}
        _room_record(self.journal, _room("R1", [edge]))
        record = _room_record(self.journal, _room("R2"))
        self.assertEqual(self.plan(record).status, "partial")
        self.assertNotIn("som-exit-to", self.text(record))
        self.assertNotIn("som-requires-open", self.text(record))

    def test_changed_exit_flags_use_new_frames_and_inactive_exits_are_removed(self):
        edge = {"exit_id": "E1", "direction": "north", "requires_open": True, "requires_unlock": False}
        first = _room_record(self.journal, _room("R1", [edge]))
        second = _room_record(self.journal, _room("R1", [{**edge, "requires_open": None, "active": False}]))
        self.assertNotEqual(self.plan(first).expressions, self.plan(second).expressions)
        self.assertNotIn("Som-Room-Exit", self.text(second))
        self.assertIn("(som-room-exit ((:seq)))", self.text(second))

    def test_partial_look_does_not_declare_an_explored_room(self):
        record = _record(self.journal, "room", {"room": _room(), "complete": False})
        self.assertEqual(self.plan(record).status, "unsupported")
        self.assertEqual(self.plan(record).expressions, ())

    def test_duplicate_encounters_remain_historical_when_current_presence_is_empty(self):
        beings = [{"being_id": name, "name": "rat", "kind": "mobile", "room_id": "R1", "aggressive": None} for name in ("M1", "M2")]
        _room_record(self.journal, beings=beings)
        empty = _room_record(self.journal)
        output = self.text(empty)
        self.assertIn(seq(frame(self.adapter.player_name, "encounter", identifier) for identifier in ("M1", "M2")), output)
        self.assertIn("(som-reading ((:seq)))", output)
        self.assertNotIn("som-aggressive", output)

    def test_fresh_readings_require_matching_visit_freshness_and_use_new_frames(self):
        being = {"being_id": "M", "name": "rat", "kind": "mobile", "room_id": "R1", "aggressive": False}
        _room_record(self.journal, beings=[being])
        fresh = _record(self.journal, "consider", {"visit": _visit(fresh=["M"]), "beings": [being], "fresh_considers": {"M": "safe"}})
        stale = _record(self.journal, "consider", {"visit": _visit(), "beings": [being], "fresh_considers": {"M": "safe"}})
        self.assertIn("(som-fresh (t)) (som-outlook (safe))", self.text(fresh))
        self.assertNotIn("som-outlook", self.text(stale))
        self.assertIn("(som-fresh (f))", self.text(stale))
        self.assertNotEqual(frame(self.adapter.player_name, "reading", fresh.observation_id + ":M"), frame(self.adapter.player_name, "reading", stale.observation_id + ":M"))

    def test_players_are_explicitly_classified_and_unknown_kinds_not_licensed(self):
        record = _room_record(self.journal, beings=[{"being_id": "P", "name": "Other", "kind": "player", "room_id": "R1", "aggressive": True}, {"being_id": "U", "name": "unknown", "kind": "unknown"}])
        output = self.text(record)
        self.assertIn("(som-player (t))", output)
        self.assertIn("(som-aggressive (t))", output)
        self.assertEqual(self.plan(record).status, "partial")
        self.assertNotIn(frame(self.adapter.player_name, "encounter", "U"), output)

    def test_unsupported_and_local_evidence_never_produces_fake_success(self):
        for kind in ("conversation", "players", "score"):
            record = _record(self.journal, kind, {})
            self.assertEqual(self.plan(record).status, "unsupported")
        local = self.journal.append("login", origin="bootstrap", lines=["Welcome."])
        self.assertEqual(self.plan(local).status, "local")
        self.assertEqual(self.plan(local).expressions, ())

    def test_malformed_prefix_does_not_contaminate_later_catalogs(self):
        broken = _record(self.journal, "listed_areas", {"areas": [{"name": "Bad", "level_range": "5-1"}]})
        self.assertEqual(self.plan(broken).status, "unsupported")
        good = _record(self.journal, "listed_areas", {"areas": [{"name": "Good"}]})
        self.assertNotIn(frame(self.adapter.player_name, "area", broken.observation_id + ":bad"), self.text(good))

    def test_source_validation_rejects_model_output_attributed_to_unrelated_evidence(self):
        source = _record(self.journal, "players", {"players": []})
        model = _record(self.journal, "model_enrichment", {"applied": True, "commands": []}, command="categories", source="model", source_ids=[source.observation_id])
        with self.assertRaises(ValueError):
            self.plan(model)

    def test_pipeline_captures_confirmed_forward_edge_and_consider_context(self):
        memory = WorkingMemory()
        observations = ObservationPipeline(memory, WorldKnowledge())
        observations.receive(["Temple", "Obvious exits:", "North", "rat is here."], "look", origin="gameplay")
        origin = memory.session.room.room_id
        target = memory.current_beings()[0]
        memory.session.pending_action = PendingAction("consider rat", target_id=target.being_id)
        consider = observations.receive(["The perfect match!"], "consider rat", origin="gameplay")
        self.assertEqual(consider.payload["fresh_considers"], {target.being_id: "even"})
        memory.session.room.depart("north")
        destination = observations.receive(["Square", "Obvious exits:", "None."], "north", origin="gameplay")
        self.assertEqual(destination.payload["room_updates"][0]["room_id"], origin)
        self.assertEqual(destination.payload["room_updates"][0]["exit_records"][0]["destination_id"], memory.session.room.room_id)
        self.assertIn("Som-Mobile-Reading", "\n".join(self.adapter.plan(consider, memory.session.evidence).expressions))

    def test_confirmed_gear_empty_inventory_equipment_and_zero_purse_are_explicit(self):
        _room_record(self.journal)
        record = _record(self.journal, "gear_state", {"state_id": "S", "confirmed": True, "owned": [], "equipped": [], "coins": 0, "room_id": "R1", "level": 1})
        output = self.text(record)
        self.assertEqual(self.plan(record).status, "mapped")
        self.assertIn("(som-gear-owned ((:seq))) (som-gear-equipped ((:seq))) (som-gear-coins (0))", output)
        self.assertIn("(som-gear-confirmed (t))", output)

    def test_gear_identity_not_label_links_owned_equipped_and_source_pieces(self):
        _room_record(self.journal)
        pieces = [{"item_id": "ring1", "short": "a ring", "worn_slot": "finger", "slot_index": 1, "usable": True}, {"item_id": "ring2", "short": "a ring", "worn_slot": "finger", "slot_index": 2, "usable": False}]
        record = _record(self.journal, "gear_state", {"state_id": "S", "confirmed": True, "owned": pieces, "equipped": ["ring2"], "coins": 5, "room_id": "R1", "level": 3, "alignment_side": "good"})
        output = self.text(record)
        self.assertIn("(som-gear-usable (f))", output)
        self.assertIn("(som-gear-equipped ((:seq " + frame(self.adapter.player_name, "gear", "ring2") + ")))", output)
        self.assertNotEqual(frame(self.adapter.player_name, "gear", "ring1"), frame(self.adapter.player_name, "gear", "ring2"))

    def test_unconfirmed_model_or_inconsistent_gear_state_is_rejected(self):
        _room_record(self.journal)
        valid = {"state_id": "S", "confirmed": True, "owned": [], "equipped": [], "coins": 0, "room_id": "R1", "level": 1}
        for changes in ({"confirmed": False}, {"coins": None}, {"coins": True}, {"equipped": ["unowned"]}, {"room_id": "unvisited"}):
            record = _record(self.journal, "gear_state", {**valid, **changes})
            self.assertEqual(self.plan(record).status, "unsupported")
            self.assertEqual(self.plan(record).expressions, ())
        model = _record(self.journal, "gear_state", valid, source="model")
        self.assertEqual(self.plan(model).status, "unsupported")

    def test_gear_sources_preserve_unknown_flags_and_explicit_negative_flags(self):
        _room_record(self.journal)
        source = {"source_id": "offer", "kind": "room", "item": {"item_id": "club", "short": "a club"}, "room_id": "R1", "available": True, "permitted": False}
        record = _record(self.journal, "gear_sources", {"sources": [source]})
        output = self.text(record)
        self.assertIn("(som-gear-source-available (t)) (som-gear-source-permitted (f))", output)
        self.assertNotIn("som-gear-source-accessible", output)
        self.assertNotIn("som-gear-owned", output)
        empty = _record(self.journal, "gear_sources", {"sources": []})
        self.assertEqual(self.plan(empty).expressions, ("(*Player-account-Example now-has (som-known-gear-source ((:seq))))",))

    def test_mobile_opportunity_does_not_invent_loot_or_combat_model(self):
        _room_record(self.journal)
        source = {"source_id": "offer", "kind": "mobile", "holder_id": "bandit1", "item": {"item_id": "sword"}, "room_id": "R1", "available": True}
        record = _record(self.journal, "gear_sources", {"sources": [source]})
        output = self.text(record)
        self.assertIn(frame(self.adapter.player_name, "encounter", "bandit1"), output)
        self.assertNotIn("som-gear-source-loot-known", output)
        self.assertNotIn("som-gear-source-model-known", output)
        assessed = _record(self.journal, "gear_sources", {"sources": [{**source, "requires": [], "loot_known": True, "model_known": True, "assessed_level": 3, "risk": "cautious", "yields": ["sword"]}]})
        self.assertIn("(som-gear-source-requires ((:seq)))", self.text(assessed))
        self.assertEqual(self.plan(assessed).status, "mapped")

    def test_raw_room_items_are_not_automatically_gear_opportunities(self):
        record = _room_record(self.journal, {**_room(), "items": [{"name": "sign", "source": "description", "keyword_known": False}]})
        self.assertNotIn("Som-Gear", self.text(record))

    def test_restored_descriptions_are_captured_before_mutable_knowledge_changes(self):
        memory = WorkingMemory()
        knowledge = WorldKnowledge()
        memory.command_knowledge = knowledge.commands
        knowledge.remember_command("look", category="information", help_text="Old help.")
        observations = ObservationPipeline(memory, knowledge)
        record = observations.receive(["look"], "commands", origin="restore")
        knowledge.remember_command("look", help_text="New help.")
        plan = self.adapter.plan(record, memory.session.evidence)
        self.assertIn('(som-command-help ("Old help."))', "\n".join(plan.expressions))
        self.assertNotIn("New help.", "\n".join(plan.expressions))

    def test_gear_source_refresh_does_not_reuse_old_permission_or_access_flags(self):
        _room_record(self.journal)
        source = {"source_id": "offer", "kind": "room", "item": {"item_id": "club"}, "room_id": "R1"}
        first = _record(self.journal, "gear_sources", {"sources": [{**source, "available": True, "permitted": True, "accessible": True}]})
        second = _record(self.journal, "gear_sources", {"sources": [source]})
        self.assertIn("som-gear-source-permitted", self.text(first))
        self.assertNotIn("som-gear-source-permitted", self.text(second))
        self.assertNotIn(frame(self.adapter.player_name, "gear-source", first.observation_id + ":offer"), self.plan(second).expressions[-1])


if __name__ == "__main__":
    unittest.main()
