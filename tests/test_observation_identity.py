import json
import os
import sys
import unittest
from dataclasses import asdict


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.RoomExit import RoomExit
from memory.SessionBeing import SessionBeing
from memory.SessionItem import SessionItem
from memory.SessionRoom import SessionRoom
from memory.PlayClock import PlayClock
from memory.WorkingMemory import WorkingMemory
from play.GameplayEngine import GameplayEngine
from play.Bootstrapper import Bootstrapper
from play.MemoryObservation import apply_room_observation, observe_line
from play.WorldReader import parse_room
from play.WorldKnowledge import PlayerRecord
from tests.test_gameplay_engine import _channel, _engine, _Km, _QueueClient
from tests.test_bootstrapper import _Model
from prompt.Prompt import Prompt
from util.SharedUtil import SharedUtil


class TestObservationIdentity(unittest.TestCase):
    def test_explicit_consider_absence_removes_only_the_target_from_current_presence(self):
        client = _QueueClient()
        client.on_send["consider rat"] = ["They're not here.", "<30hp 100m 100mv>"]
        engine = _engine(client, _Km('((:args survey "information / communication" consider rat))'), room_current=True, clock=PlayClock(score_count=1, level=1))
        engine.memory.observe_room("The Temple of Mota", beings=[SessionBeing("rat", "mobile"), SessionBeing("wolf", "mobile")])
        rat = engine.memory.resolve_current_being("rat")
        self.assertEqual(engine.step(), "consider rat")
        self.assertEqual([being.name for being in engine.memory.current_beings()], ["wolf"])
        self.assertIs(engine.memory.being_by_id(rat.being_id), rat)

    def test_failed_look_keeps_history_without_authorizing_old_presence_or_exits(self):
        client = _QueueClient()
        client.on_send["look"] = ["You cannot see anything.", "<30hp 100m 100mv>"]
        engine = _engine(client, _Km('((:args travel movement north ""))'), room_current=True, clock=PlayClock(score_count=1, level=1))
        engine.memory.observe_room("The Temple of Mota", beings=[SessionBeing("rat", "mobile")])
        identifier = engine.memory.current_beings()[0].being_id
        engine.memory.session.room.current = False
        self.assertEqual(engine.step(), "look")
        self.assertEqual(engine.memory.current_beings(), [])
        self.assertIsNotNone(engine.memory.being_by_id(identifier))
        self.assertEqual(engine.step(), "")
        self.assertEqual(client.sent, ["look"])

    def test_player_fight_observations_keep_player_classification_and_identity(self):
        memory = WorkingMemory()
        player = PlayerRecord(name="Marcus", level=1, race="human", character_class="War")
        apply_room_observation(memory, parse_room(["Temple", "Obvious exits:", "North", "Marcus is here, fighting YOU!"], [player]))
        marcus = memory.current_beings()[0]
        self.assertEqual(marcus.kind, "player")
        self.assertIn(marcus.being_id, memory.session.combat.threats)
        same = observe_line(memory, "Marcus is here, fighting YOU!")
        self.assertIs(same, marcus)
        self.assertEqual(marcus.kind, "player")
        self.assertEqual(memory.mobiles(), [])

    def test_model_keyword_enrichment_preserves_item_identity_on_later_server_looks(self):
        memory = WorkingMemory()
        lines = ["Temple", "    A ring lies here.", "Obvious exits:", "None."]
        apply_room_observation(memory, parse_room(lines, []))
        room = memory.room_by_id(memory.session.room.room_id)
        identifier = room.items[0].item_id
        self.assertFalse(room.items[0].keyword_known)
        self.assertTrue(memory.apply_room_items(room.room_id, memory.session.room.revision, [{"name": "ring", "line": "A ring lies here.", "source": "object"}]))
        self.assertEqual(room.items[0].item_id, identifier)
        apply_room_observation(memory, parse_room(lines, []))
        self.assertEqual(room.items[0].item_id, identifier)
        self.assertEqual(room.items[0].name, "ring")
        self.assertTrue(room.items[0].keyword_known)

    def test_header_without_a_room_title_cannot_replace_the_current_snapshot(self):
        client = _QueueClient()
        client.on_send["look"] = ["The Temple of Mota", "Obvious exits:", "North", "<30hp 100m 100mv>"]
        engine = _engine(client, _Km(), goal=False, room_current=True)
        room_id = engine.memory.session.room.room_id
        client.pending = ["Obvious exits:", "None.", "<30hp 100m 100mv>"]
        self.assertEqual(engine.step(), "look")
        self.assertEqual(engine.memory.session.room.room_id, room_id)
        self.assertEqual(engine.memory.session.room.name, "The Temple of Mota")
        self.assertEqual(engine.memory.session.room.exits, ["north"])

    def test_unprompted_speech_does_not_stall_the_gameplay_loop(self):
        client = _QueueClient()
        client.pending = ["Marcus tells you 'Hello.'"]
        client.on_send["save"] = ["Saved.", "<30hp 100m 100mv>"]
        engine = _engine(client, _Km('((:args checkpoint other save ""))'), room_current=True, clock=PlayClock(score_count=1, level=1))
        self.assertEqual(engine.step(), "save")
        self.assertEqual(engine.memory.session.observation_lines, [])

    def test_a_closed_door_in_the_destination_description_is_not_a_movement_refusal(self):
        client = _QueueClient()
        client.on_send["north"] = ["North Road", "A gate is closed at the far end.", "Obvious exits:", "South", "<30hp 100m 100mv>"]
        engine = _engine(client, _Km('((:args travel movement north ""))'), room_current=True, clock=PlayClock(score_count=1, level=1))
        origin = engine.memory.room_by_id(engine.memory.session.room.room_id)
        self.assertEqual(engine.step(), "north")
        self.assertEqual(engine.memory.session.room.name, "North Road")
        self.assertEqual(origin.exit_records[0].destination_id, engine.memory.session.room.room_id)
        self.assertIsNone(origin.exit_records[0].requires_open)

    def test_bootstrap_applies_duplicate_sightings_before_the_legacy_world_snapshot_collapses_names(self):
        memory = WorkingMemory()
        bootstrap = Bootstrapper(None, [], "Example", channel=object(), memory=memory)
        bootstrap._observe_room(["Temple", "Obvious exits:", "North", "rat is here.", "rat is here."])
        self.assertEqual(len(memory.current_beings()), 2)
        self.assertEqual(len({being.being_id for being in memory.current_beings()}), 2)
        self.assertEqual(len(bootstrap.knowledge.mobiles), 1)

    def test_bootstrap_rejects_model_results_for_a_replaced_source_observation(self):
        memory = WorkingMemory()
        initial = ["Temple", "Obvious exits:", "North"]
        bootstrap = Bootstrapper(None, [], "Example", channel=object(), memory=memory, prompts={"look": Prompt(name="look", model="test", system="Read the room.", user="{look}", json_schema={"type": "object"}, tokens={})})
        bootstrap._observe_room(initial)

        def answer(_body):
            bootstrap._observe_room(["Temple", "Obvious exits:", "None."])
            return json.dumps({"items": [{"name": "phantom"}]})

        bootstrap._ollama = _Model(answer)
        bootstrap._send_room_prompts(initial)
        self.assertEqual(memory.room_by_id(memory.session.room.room_id).items, [])
        self.assertEqual(memory.session.room.exits, [])

    def test_model_enrichment_cannot_collapse_observed_duplicate_objects(self):
        memory = WorkingMemory()
        apply_room_observation(memory, parse_room(["Temple", "    A ring lies here.", "    A ring lies here.", "Obvious exits:", "None."], []))
        room = memory.room_by_id(memory.session.room.room_id)
        identifiers = {item.item_id for item in room.items}
        self.assertTrue(memory.apply_room_items(room.room_id, memory.session.room.revision, [{"name": "ring", "line": "A ring lies here.", "source": "object"}]))
        self.assertEqual({item.item_id for item in room.items}, identifiers)
        self.assertEqual(len(room.items), 2)
        self.assertTrue(all(not item.keyword_known for item in room.items))

    def test_complete_empty_look_replaces_presence_exits_and_items_but_keeps_history(self):
        memory = WorkingMemory()
        room = memory.observe_room("Temple", description="Stone.", exits=["north"], beings=[SessionBeing("rat", "mobile")], items=[{"name": "ring", "line": "A ring lies here.", "source": "object"}])
        rat = memory.current_beings()[0]
        item_id = room.items[0].item_id
        exit_id = room.exit_records[0].exit_id
        memory.remember_consider("rat", ["rat looks like an easy kill."], kind="mobile", being_id=rat.being_id)
        memory.session.room.note_consider(rat.being_id)
        memory.session.combat.note_threat(rat.being_id)
        apply_room_observation(memory, parse_room(["Temple", "Obvious exits:", "None."], []))

        self.assertEqual(memory.session.room.room_id, room.room_id)
        self.assertEqual(memory.current_beings(), [])
        self.assertEqual(room.exits, [])
        self.assertEqual(room.items, [])
        self.assertEqual(memory.session.room.fresh, set())
        self.assertEqual(memory.session.combat.threats, set())
        self.assertIs(memory.being_by_id(rat.being_id), rat)
        self.assertEqual(memory.consider_for_id(rat.being_id).outlook, "safe")
        self.assertIsNotNone(memory.item_by_id(item_id))
        self.assertFalse(memory.exit_by_id(exit_id).active)

    def test_omitted_fields_preserve_values_and_explicit_empty_values_replace_them(self):
        memory = WorkingMemory()
        room = memory.remember_room("Temple", description="Stone.", exits=["north"], items=[{"name": "ring"}])
        memory.remember_room("Temple")
        self.assertEqual((room.description, room.exits, len(room.items)), ("Stone.", ["north"], 1))
        memory.remember_room("Temple", description="", exits=[], items=[])
        self.assertEqual((room.description, room.exits, room.items), ("", [], []))
        being = memory.remember_mobile("rat", auras=["White Aura"])
        self.assertIsNone(being.aggressive)
        memory.note_aggressive("rat")
        memory.remember_mobile("rat")
        self.assertTrue(being.aggressive)
        self.assertEqual(being.auras, ["White Aura"])
        memory.remember_mobile("rat", aggressive=False, auras=[])
        self.assertIs(being.aggressive, False)
        self.assertEqual(being.auras, [])

    def test_duplicate_beings_are_distinct_and_ambiguous_refresh_does_not_reuse_evidence(self):
        memory = WorkingMemory()
        memory.observe_room("Temple", exits=[], beings=[SessionBeing("rat", "mobile"), SessionBeing("rat", "mobile")])
        first_ids = {being.being_id for being in memory.current_beings()}
        self.assertEqual(len(first_ids), 2)
        self.assertIsNone(memory.resolve_current_being("rat"))
        self.assertIsNone(memory.being_named("rat"))
        with self.assertRaises(ValueError):
            memory.remember_mobile("rat")
        for identifier in first_ids:
            memory.session.room.note_consider(identifier)
        memory.observe_room("Temple", beings=[SessionBeing("rat", "mobile"), SessionBeing("rat", "mobile")])
        self.assertTrue(first_ids.isdisjoint({being.being_id for being in memory.current_beings()}))
        self.assertEqual(len(memory.beings_named("rat")), 4)
        self.assertEqual(memory.session.room.fresh, set())

    def test_disappearance_and_return_do_not_revive_an_old_consider(self):
        memory = WorkingMemory()
        memory.observe_room("Temple", beings=[SessionBeing("rat", "mobile")])
        old = memory.current_beings()[0]
        memory.remember_consider("rat", ["rat looks like an easy kill."], kind="mobile", being_id=old.being_id)
        memory.session.room.note_consider(old.being_id)
        memory.observe_room("Temple", beings=[])
        memory.observe_room("Temple", beings=[SessionBeing("rat", "mobile")])
        new = memory.current_beings()[0]
        self.assertNotEqual(new.being_id, old.being_id)
        self.assertIsNone(memory.consider_for_id(new.being_id))
        self.assertEqual(memory.session.room.fresh, set())

    def test_unique_continuous_sighting_keeps_id_but_changed_auras_invalidate_consider(self):
        memory = WorkingMemory()
        memory.observe_room("Temple", beings=[SessionBeing("rat", "mobile")])
        rat = memory.current_beings()[0]
        memory.session.room.note_consider(rat.being_id)
        memory.observe_room("Temple", beings=[SessionBeing("rat", "mobile")])
        self.assertIs(memory.current_beings()[0], rat)
        self.assertIn(rat.being_id, memory.session.room.fresh)
        memory.observe_room("Temple", beings=[SessionBeing("rat", "mobile", auras=["Red Aura"])])
        self.assertEqual(memory.current_beings()[0].being_id, rat.being_id)
        self.assertNotIn(rat.being_id, memory.session.room.fresh)

    def test_same_named_rooms_and_beings_remain_distinct_across_visits(self):
        memory = WorkingMemory()
        first = memory.observe_room("Corridor", exits=["north"], beings=[SessionBeing("rat", "mobile")])
        old_rat = memory.current_beings()[0]
        old_visit = memory.session.room.visit_id
        second = memory.observe_room("Corridor", exits=["south"], beings=[SessionBeing("rat", "mobile")], new_visit=True, connect_from=first.room_id, direction="north")
        self.assertNotEqual(first.room_id, second.room_id)
        self.assertNotEqual(old_visit, memory.session.room.visit_id)
        self.assertNotEqual(old_rat.being_id, memory.current_beings()[0].being_id)
        self.assertEqual(len(memory.rooms_named("Corridor")), 2)
        self.assertIsNone(memory.room_named("Corridor"))
        self.assertEqual(first.exit_records[0].destination_id, second.room_id)
        self.assertIsNone(second.exit_records[0].destination_id)

    def test_duplicate_gear_sightings_have_separate_ids_and_removed_sightings_remain_history(self):
        memory = WorkingMemory()
        room = memory.observe_room("Temple", items=[{"name": "ring", "line": "A ring lies here.", "source": "object"}, {"name": "ring", "line": "A ring lies here.", "source": "object"}])
        identifiers = {item.item_id for item in room.items}
        self.assertEqual(len(identifiers), 2)
        memory.observe_room("Temple", items=[])
        self.assertEqual(room.items, [])
        self.assertTrue(all(memory.item_by_id(identifier) is not None for identifier in identifiers))

    def test_identity_records_round_trip_without_turning_unknown_flags_into_false(self):
        room = SessionRoom("Temple")
        room.update("Temple", exits=["north"], items=[SessionItem("ring")])
        restored = SessionRoom.from_json(SharedUtil.camel_keys(room.to_review()))
        self.assertEqual(restored.to_review(), room.to_review())
        self.assertIsNone(restored.exit_records[0].requires_open)
        self.assertIsNone(restored.exit_records[0].requires_unlock)
        being = SessionBeing.from_json(SharedUtil.camel_keys(asdict(SessionBeing("mysterious figure", "unknown"))))
        self.assertIsNone(being.aggressive)
        self.assertIsNone(being.agentic)
        entry = RoomExit.from_json({"direction": "north", "roomId": room.room_id, "requiresOpen": False})
        self.assertIs(entry.requires_open, False)

    def test_legacy_snapshot_keeps_duplicate_rows_but_never_claims_to_restore_ids(self):
        memory = WorkingMemory()
        memory.observe_room("Corridor", beings=[SessionBeing("rat", "mobile"), SessionBeing("rat", "mobile")])
        memory.observe_room("Corridor", new_visit=True)
        document = json.loads(json.dumps(memory.to_collection("Example")))
        self.assertNotIn("roomId", document["rooms"][0])
        self.assertNotIn("beingId", document["mobiles"][0])
        self.assertNotIn("roomExits", document)
        restored = WorkingMemory.from_collection(document)
        self.assertEqual(len(restored.beings_named("rat")), 2)
        self.assertEqual(len(restored.rooms_named("Corridor")), 2)
        self.assertEqual(restored.current_beings(), [])

    def test_partial_room_observation_cannot_clear_an_unobserved_section(self):
        memory = WorkingMemory()
        room = memory.observe_room("Temple", exits=["north"], beings=[SessionBeing("rat", "mobile")])
        rat_id = memory.current_beings()[0].being_id
        partial = parse_room(["Temple", "A changed description."], [])
        self.assertFalse(partial.complete)
        apply_room_observation(memory, partial)
        self.assertEqual(room.exits, ["north"])
        self.assertEqual(memory.session.room.occupant_ids, [rat_id])

    def test_late_model_enrichment_is_rejected_after_a_newer_look_or_visit(self):
        memory = WorkingMemory()
        room = memory.observe_room("Temple", exits=["north"], beings=[])
        revision = memory.session.room.revision
        memory.observe_room("Temple", exits=[], beings=[])
        self.assertFalse(memory.apply_room_items(room.room_id, revision, [{"name": "phantom"}]))
        old_revision = memory.session.room.revision
        memory.observe_room("Temple", new_visit=True)
        self.assertFalse(memory.apply_room_items(room.room_id, old_revision, [{"name": "phantom"}]))
        self.assertEqual(room.items, [])

    def test_partial_fighting_line_does_not_choose_between_identical_mobiles(self):
        memory = WorkingMemory()
        memory.observe_room("Temple", beings=[SessionBeing("rat", "mobile"), SessionBeing("rat", "mobile")])
        self.assertIsNone(observe_line(memory, "rat is here, fighting YOU!"))
        self.assertTrue(memory.session.combat.has_uninvited_threat())
        self.assertEqual(memory.session.combat.threats, set())
        self.assertTrue(all(being.aggressive is None for being in memory.current_beings()))

    def test_split_room_page_is_buffered_across_engine_recreation(self):
        client = _QueueClient()
        engine = _engine(client, _Km(), goal=False, room_current=True)
        engine.memory.observe_room("The Temple of Mota", exits=["north"], beings=[SessionBeing("rat", "mobile")])
        rat_id = engine.memory.current_beings()[0].being_id
        client.pending = ["The Temple of Mota", "Obvious exits:"]
        self.assertEqual(engine.step(), "")
        self.assertEqual(engine.memory.session.room.occupant_ids, [rat_id])
        self.assertEqual(engine.memory.session.room.exits, ["north"])
        recreated = GameplayEngine(_channel(client), engine.memory, engine.knowledge, engine.km)
        client.pending = ["None.", "<30hp 100m 100mv>"]
        self.assertEqual(recreated.step(), "")
        self.assertEqual(engine.memory.current_beings(), [])
        self.assertEqual(engine.memory.session.room.exits, [])
        self.assertEqual(client.sent, [])

    def test_multiple_queued_room_pages_apply_in_prompt_order(self):
        client = _QueueClient()
        engine = _engine(client, _Km(), goal=False, room_current=True)
        client.pending = ["The Temple of Mota", "Obvious exits:", "North", "rat is here.", "<30hp 100m 100mv>", "The Temple of Mota", "Obvious exits:", "None.", "<30hp 100m 100mv>"]
        self.assertEqual(engine.step(), "")
        self.assertEqual(engine.memory.current_beings(), [])
        self.assertEqual(len(engine.memory.beings_named("rat")), 1)
        self.assertEqual(engine.memory.session.room.exits, [])

    def test_same_title_movement_creates_a_new_visit_and_only_a_directed_connection(self):
        client = _QueueClient()
        client.on_send["north"] = ["The Temple of Mota", "Obvious exits:", "South", "rat is here.", "<30hp 100m 100mv>"]
        engine = _engine(client, _Km('((:args travel movement north ""))'), room_current=True, clock=PlayClock(score_count=1, level=1))
        origin = engine.memory.room_by_id(engine.memory.session.room.room_id)
        self.assertEqual(engine.step(), "north")
        arrival = engine.memory.room_by_id(engine.memory.session.room.room_id)
        self.assertNotEqual(origin.room_id, arrival.room_id)
        self.assertTrue(engine.memory.session.room.current)
        self.assertEqual(origin.exit_records[0].destination_id, arrival.room_id)
        self.assertIsNone(arrival.exit_records[0].destination_id)

    def test_refused_movement_preserves_room_identity_and_records_only_observed_door_evidence(self):
        client = _QueueClient()
        client.on_send["north"] = ["The gate is closed.", "<30hp 100m 100mv>"]
        engine = _engine(client, _Km('((:args travel movement north ""))'), room_current=True, clock=PlayClock(score_count=1, level=1))
        origin_id = engine.memory.session.room.room_id
        self.assertEqual(engine.step(), "north")
        room = engine.memory.room_by_id(origin_id)
        self.assertEqual(engine.memory.session.room.room_id, origin_id)
        self.assertTrue(engine.memory.session.room.current)
        self.assertEqual(engine.memory.session.room.tried, {"north"})
        self.assertTrue(room.exit_records[0].requires_open)
        self.assertIsNone(room.exit_records[0].requires_unlock)
        self.assertIsNone(room.exit_records[0].destination_id)
        self.assertEqual(len(engine.memory.rooms()), 1)

    def test_uncertain_move_and_later_look_do_not_fabricate_a_connection(self):
        client = _QueueClient()
        client.on_send["north"] = ["Nothing happens.", "<30hp 100m 100mv>"]
        client.on_send["look"] = ["The Temple of Mota", "Obvious exits:", "South", "<30hp 100m 100mv>"]
        engine = _engine(client, _Km('((:args travel movement north ""))'), room_current=True, clock=PlayClock(score_count=1, level=1))
        origin = engine.memory.room_by_id(engine.memory.session.room.room_id)
        self.assertEqual(engine.step(), "north")
        self.assertFalse(engine.memory.session.room.current)
        self.assertEqual(engine.step(), "look")
        self.assertNotEqual(engine.memory.session.room.room_id, origin.room_id)
        self.assertIsNone(origin.exit_records[0].destination_id)

    def test_failed_flee_does_not_clear_the_fight_or_change_rooms(self):
        client = _QueueClient()
        client.on_send["flee"] = ["PANIC! You couldn't escape!", "<10hp 100m 100mv>"]
        engine = _engine(client, _Km(), room_current=True)
        engine.memory.session.combat.fighting = True
        engine.memory.session.combat.hit = 10
        origin_id = engine.memory.session.room.room_id
        self.assertEqual(engine.step(), "flee")
        self.assertTrue(engine.memory.session.combat.fighting)
        self.assertTrue(engine.memory.session.room.current)
        self.assertEqual(engine.memory.session.room.room_id, origin_id)

    def test_historical_or_ambiguous_mobiles_cannot_be_sent_as_current_targets(self):
        client = _QueueClient()
        km = _Km('((:args engage combat kill rat))')
        engine = _engine(client, km, room_current=True, clock=PlayClock(score_count=1, level=1))
        engine.memory.remember_mobile("historical rat", room_name="The Temple of Mota")
        engine.memory.observe_room("The Temple of Mota", beings=[SessionBeing("rat", "mobile"), SessionBeing("rat", "mobile")])
        self.assertEqual(engine.step(), "")
        self.assertNotIn("historical rat", "\n".join(km.questions[-1]))
        self.assertEqual(client.sent, [])
        km.attempts = '((:args survey "information / communication" consider rat))'
        self.assertEqual(engine.step(), "")
        self.assertEqual(client.sent, [])


if __name__ == "__main__":
    unittest.main()
