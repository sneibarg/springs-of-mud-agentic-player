import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.rest.KmAnswer import KmAnswer
from play.LevelGoal import LevelGoal
from play.LevelQuestion import LevelQuestion, MobileReading
from memory.PlayClock import PlayClock
from memory.CombatState import CombatState


def _results(attempts):
    filler = [KmAnswer(ok=True, answer="(*Frame)")]
    tail = [KmAnswer(ok=True, answer="(steady)"), KmAnswer(ok=True, answer="(4)"), KmAnswer(ok=True, answer="(10)"), KmAnswer(ok=True, answer=attempts)]
    return filler + tail


class TestLevelQuestion(unittest.TestCase):
    def test_unquoted_arguments_do_not_include_surrounding_sequence_parentheses(self):
        decision = LevelQuestion.read(_results('((:seq (:args survey "information / communication" consider rat) (:args engage combat kill wolf)))'))
        self.assertEqual([attempt.command() for attempt in decision.attempts], ["consider rat", "kill wolf"])

    def test_combat_projection_uses_the_session_combat_state(self):
        combat = CombatState(hit=12, max_hit=40, fighting=True, position="fighting")
        question = LevelQuestion(LevelGoal(target_level=2, risk="steady", minutes=0), PlayClock(score_count=1, level=1), [], [], areas_known=False, flee_hp=20, combat=combat)
        text = "\n".join(question.expressions())
        self.assertIn("(som-fighting (t))", text)
        self.assertIn("(som-hit (12))", text)
        self.assertIn("(som-max-hit (40))", text)
        self.assertIn("(som-position (fighting))", text)

    def test_prior_notch_is_clamped_and_a_stale_reading_has_no_outlook(self):
        goal = LevelGoal(target_level=5, risk="cautious", minutes=0)
        clock = PlayClock(start_level=1, level=1, exp_to_level=1000, exp_span=1000, score_count=1, prior_notch="bold", score_steps=2, saves=1)
        question = LevelQuestion(goal, clock, [MobileReading("goblin", outlook="safe", fresh=False), MobileReading("orc", outlook="safe", fresh=True)], ["north"], areas_known=True, flee_hp=20)
        text = "\n".join(question.expressions())

        self.assertIn("(som-prior-notch (cautious))", text)
        self.assertNotIn("(som-prior-notch (bold))", text)
        self.assertIn("(som-risk-ceiling (cautious))", text)
        self.assertIn("(som-budget-minutes (0))", text)
        self.assertIn('(*Mobile1 has (instance-of (Som-Mobile-Reading)) (som-mobile-name (goblin)))', text)
        self.assertNotIn("(*Mobile1 has (instance-of (Som-Mobile-Reading)) (som-mobile-name (goblin)) (som-outlook", text)
        self.assertIn("(som-outlook (safe))", text)
        self.assertIn("(som-fresh (t))", text)
        self.assertIn("(som-untried-exits ((:seq north)))", text)
        self.assertIn("(som-areas-known (t))", text)
        self.assertIn("(the som-attempts of (the som-licensed-directive of *View))", text)
        self.assertNotIn("practice", text)

    def test_reads_a_sequence_of_attempts_and_a_yield(self):
        decision = LevelQuestion.read(_results('((:seq (:args survey "information / communication" areas "") (:args travel movement north "")))'))
        self.assertEqual(decision.notch, "steady")
        self.assertEqual(decision.cooldown, 4)
        self.assertEqual(decision.rule, 10)
        self.assertEqual(decision.attempts[0].command(), "areas")
        self.assertEqual(decision.attempts[1].command(), "north")
        self.assertEqual(decision.attempts[0].category, "information / communication")

        yielded = LevelQuestion.read(_results("nil"))
        self.assertEqual(yielded.attempts, ())
        self.assertEqual(yielded.notch, "steady")

    def test_a_quoted_mobile_name_stays_on_the_command(self):
        question = LevelQuestion(LevelGoal(target_level=2, risk="steady", minutes=0), PlayClock(score_count=1, level=1, start_level=1), [MobileReading("a goblin")], [], areas_known=False, flee_hp=20)
        text = "\n".join(question.expressions())
        self.assertIn('(som-mobile-name ("a goblin"))', text)
        decision = LevelQuestion.read(_results('((:args survey "information / communication" consider "a goblin"))'))
        self.assertEqual(decision.attempts[0].command(), "consider a goblin")


if __name__ == "__main__":
    unittest.main()
