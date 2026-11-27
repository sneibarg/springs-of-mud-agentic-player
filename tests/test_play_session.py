import json
import os
import sys
import unittest
from dataclasses import asdict


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.PendingAction import PendingAction
from memory.PlaySession import PlaySession
from memory.WorkingMemory import WorkingMemory
from play.MemoryObservation import parse_score
from util.SharedUtil import SharedUtil


class TestPlaySession(unittest.TestCase):
    def test_review_contains_all_live_state_and_is_detached_and_json_serializable(self):
        memory = WorkingMemory()
        session = memory.session
        session.note_score(2, 3, 500, 25, 40, "fighting")
        session.room.observe("Temple", ["north", "east"])
        session.room.tried.add("north")
        session.room.note_consider("Being-wolf")
        session.combat.engage("rat")
        session.combat.note_threat("wolf")
        session.pending_action = PendingAction("consider wolf")
        session.last_prompt = "<25hp 100m 100mv>"
        session.look_unread = session.score_unread = session.areas_unread = True

        review = json.loads(json.dumps(memory.to_review()))["session"]
        self.assertEqual(review["progress"]["level"], 2)
        self.assertEqual(review["room"]["tried"], ["north"])
        self.assertEqual(review["room"]["fresh"], ["Being-wolf"])
        self.assertEqual(review["combat"]["engaged"], ["rat"])
        self.assertEqual(review["combat"]["threats"], ["wolf"])
        self.assertTrue(review["combat"]["fighting"])
        self.assertTrue(review["areas_unread"])
        self.assertTrue(review["look_unread"])
        self.assertTrue(review["score_unread"])
        restored = PlaySession.from_json(SharedUtil.camel_keys(review))
        self.assertEqual(restored.to_review(), review)
        restored.room.exits.clear()
        self.assertEqual(session.room.exits, ["north", "east"])

    def test_live_state_stays_out_of_legacy_documents_and_is_not_restored_from_them(self):
        memory = WorkingMemory()
        memory.session.note_score(3, 4, 200, 5, 40, "fighting")
        memory.session.room.observe("Temple", ["north"])
        memory.session.pending_action = PendingAction("kill wolf")
        document = memory.to_collection("Example")
        self.assertNotIn("session", document)
        document["session"] = memory.session.to_review()
        restored = WorkingMemory.from_collection(document)
        self.assertEqual(restored.session.to_review(), PlaySession().to_review())

    def test_clear_discards_live_state_and_instances_do_not_share_it(self):
        memory = WorkingMemory()
        old_session = memory.session
        old_session.room.observe("Temple", ["north"])
        old_session.combat.note_threat("wolf")
        old_session.pending_action = PendingAction("look")
        memory.clear()
        self.assertIsNot(memory.session, old_session)
        self.assertEqual(memory.session.to_review(), PlaySession().to_review())
        memory.session.room.observe("Inn", ["south"])
        self.assertEqual(WorkingMemory().session.to_review(), PlaySession().to_review())

    def test_score_updates_progress_and_combat_without_erasing_missing_vitals(self):
        session = PlaySession()
        session.combat.engage("rat")
        session.combat.note_threat("wolf")
        session.note_score(1, 2, 1000, 20, 30, "fighting")
        session.progress.score_steps = 5
        session.note_score(1, 3, 700, None, None, "standing")
        self.assertEqual(session.progress.exp_span, 1000)
        self.assertEqual(session.progress.start_hours, 2)
        self.assertEqual(session.progress.score_count, 2)
        self.assertEqual(session.progress.score_steps, 0)
        self.assertEqual(session.combat.hit, 20)
        self.assertEqual(session.combat.max_hit, 30)
        self.assertFalse(session.combat.fighting)
        self.assertEqual(session.combat.threats, set())
        self.assertEqual(session.combat.engaged, {"rat"})
        session.note_score(2, 4, 1500, 30, 40, "standing")
        self.assertEqual(session.progress.exp_span, 1500)
        self.assertEqual(session.progress.start_level, 1)

    def test_score_parser_requires_a_complete_progress_page(self):
        self.assertIsNone(parse_score(["You have 5/40 hit, 10/20 mana, 30/40 movement.", "You are fighting."]))
        score = parse_score(["You are Example the novice, level 2, 17 years old (3 hours).", "You have 25/40 hit, 100/100 mana, 100/100 movement.", "You need 500 exp to level.", "You are standing."])
        self.assertEqual(asdict(score), {"level": 2, "hours": 3, "exp_to_level": 500, "hit": 25, "max_hit": 40, "position": "standing"})


if __name__ == "__main__":
    unittest.main()
