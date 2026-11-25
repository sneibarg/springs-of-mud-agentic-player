import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.WorkingMemory import WorkingMemory
from net.rest.KmAnswer import KmAnswer
from play.CommandChannel import CommandChannel
from play.GameplayEngine import GameplayEngine
from play.LevelGoal import LevelGoal
from play.PlayClock import PlayClock
from play.WorldKnowledge import RoomSnapshot, WorldKnowledge


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _QueueClient:
    def __init__(self):
        self.connected = True
        self.sent: list[str] = []
        self.pending: list[str] = []
        self.on_send: dict[str, list[str]] = {}

    def send_line(self, text: str) -> None:
        self.sent.append(text)
        self.pending.extend(self.on_send.get(text, []))

    def poll_line(self):
        if self.pending:
            return self.pending.pop(0)
        return None


class _Km:
    def __init__(self, attempts="nil"):
        self.attempts = attempts
        self.questions = []

    def baseline(self, expressions):
        self.questions.append(list(expressions))
        answers = [KmAnswer(ok=True, answer="(*Frame)")] * len(expressions)
        answers[-4] = KmAnswer(ok=True, answer="(steady)")
        answers[-3] = KmAnswer(ok=True, answer="(0)")
        answers[-2] = KmAnswer(ok=True, answer="(10)")
        answers[-1] = KmAnswer(ok=True, answer=self.attempts)
        return answers


def _channel(client: _QueueClient) -> CommandChannel:
    clock = _Clock()
    return CommandChannel(client, timeout_s=0.2, poll_interval_s=0.1, clock=clock, sleep=clock.sleep)


def _engine(client, km, *, goal=True, room_current=False, clock=None, commands=None):
    memory = WorkingMemory()
    memory.remember_commands(commands or ["look", "score", "north", "flee", "kill", "save", "consider"])
    knowledge = WorldKnowledge()
    if room_current:
        knowledge.room = RoomSnapshot(name="The Temple of Mota", description="", exits=["north"])
    level_goal = LevelGoal(target_level=5, risk="cautious", minutes=0) if goal else None
    return GameplayEngine(_channel(client), memory, knowledge, km, goal=level_goal, room_current=room_current, clock=clock)


_SCORE = ["You are Example the novice, level 1, 17 years old (0 hours).", "You have 30/30 hit, 100/100 mana, 100/100 movement.", "You need 1000 exp to level.", "You are standing.", "<30hp 100m 100mv>"]
_LOOK = ["The Temple of Mota", "A quiet temple.", "Obvious exits:", "North", "a goblin is here.", "<30hp 100m 100mv>"]


class TestGameplayEngine(unittest.TestCase):
    def test_a_queued_line_is_drained_and_does_not_send(self):
        client = _QueueClient()
        client.pending = ["Marcus tells you 'Hello.'", "<30hp 100m 100mv>"]
        engine = _engine(client, _Km(), goal=False, room_current=True)

        self.assertEqual(engine.step(), "")
        self.assertEqual(client.sent, [])
        self.assertEqual(engine.channel.last_prompt, "<30hp 100m 100mv>")

    def test_restore_looks_once_then_scores_then_asks_km_for_one_command(self):
        client = _QueueClient()
        client.on_send["look"] = list(_LOOK)
        client.on_send["score"] = list(_SCORE)
        client.on_send["north"] = ["The North Road", "Obvious exits:", "South", "<30hp 100m 100mv>"]
        km = _Km('((:args travel movement north ""))')
        engine = _engine(client, km, room_current=False)

        self.assertEqual(engine.step(), "look")
        self.assertEqual(km.questions, [])
        self.assertEqual(engine.step(), "score")
        self.assertEqual(km.questions, [])
        self.assertEqual(engine.step(), "north")
        self.assertEqual(len(km.questions), 1)
        text = "\n".join(km.questions[0])
        self.assertIn("(som-level (1))", text)
        self.assertIn("(som-prior-notch (cautious))", text)
        self.assertIn("(som-untried-exits ((:seq north)))", text)
        self.assertIn('(som-mobile-name ("a goblin"))', text)
        self.assertNotIn("(som-outlook", text)
        self.assertEqual(client.sent, ["look", "score", "north"])

    def test_a_yield_sends_nothing_and_a_second_step_observes_before_it_asks_again(self):
        client = _QueueClient()
        client.pending = ["You gain 20 experience.", "<30hp 100m 100mv>"]
        km = _Km("nil")
        clock = PlayClock(start_level=1, level=1, exp_to_level=1000, exp_span=1000, score_count=1, saves=1)
        engine = _engine(client, km, room_current=True, clock=clock)

        self.assertEqual(engine.step(), "")
        self.assertEqual(client.sent, [])
        self.assertEqual(client.pending, [])
        self.assertEqual(len(km.questions), 1)
        client.pending = ["A city guard arrives.", "<30hp 100m 100mv>"]
        self.assertEqual(engine.step(), "")
        self.assertEqual(len(km.questions), 2)

    def test_an_uninvited_fight_leaves_and_does_not_ask_km_to_kill(self):
        client = _QueueClient()
        client.pending = ["a goblin is here, fighting YOU!", "<30hp 100m 100mv>"]
        client.on_send["north"] = ["The North Road", "Obvious exits:", "South", "<30hp 100m 100mv>"]
        km = _Km("((:args engage combat kill goblin))")
        clock = PlayClock(start_level=1, level=1, exp_to_level=1000, exp_span=1000, score_count=1, hit=30, max_hit=30)
        engine = _engine(client, km, room_current=True, clock=clock)

        self.assertEqual(engine.step(), "north")
        self.assertEqual(km.questions, [])
        self.assertNotIn("kill goblin", client.sent)

    def test_low_hit_points_while_fighting_flee_before_a_hunt(self):
        client = _QueueClient()
        client.on_send["flee"] = ["You flee north.", "<10hp 100m 100mv>"]
        km = _Km("((:args engage combat kill goblin))")
        clock = PlayClock(start_level=1, level=1, exp_to_level=1000, exp_span=1000, score_count=1, fighting=True, hit=10, max_hit=30)
        engine = _engine(client, km, room_current=True, clock=clock)
        engine.channel.last_prompt = "<10hp 100m 100mv>"
        engine._engaged.add("goblin")

        self.assertEqual(engine.step(), "flee")
        self.assertEqual(km.questions, [])

    def test_unknown_verb_is_skipped_and_quit_is_not_sent(self):
        client = _QueueClient()
        client.on_send["north"] = ["The North Road", "<30hp 100m 100mv>"]
        km = _Km('((:seq (:args survey "information / communication" areas "") (:args checkpoint other quit "") (:args travel movement north "")))')
        clock = PlayClock(start_level=1, level=1, exp_to_level=1000, exp_span=1000, score_count=1, saves=1)
        engine = _engine(client, km, room_current=True, clock=clock)

        self.assertEqual(engine.step(), "north")
        self.assertEqual(client.sent, ["north"])

    def test_a_player_is_not_offered_to_the_level_question(self):
        client = _QueueClient()
        km = _Km("nil")
        clock = PlayClock(start_level=1, level=1, exp_to_level=1000, exp_span=1000, score_count=1, saves=1)
        engine = _engine(client, km, room_current=True, clock=clock)
        engine.memory.remember_player("Marcus", room_name="The Temple of Mota")
        engine.memory.remember_mobile("goblin", room_name="The Temple of Mota")
        engine.memory.remember_consider("goblin", ["goblin looks like an easy kill."], kind="mobile")
        engine._fresh.add("goblin")

        self.assertEqual(engine.step(), "")
        text = "\n".join(km.questions[0])
        self.assertNotIn("Marcus", text)
        self.assertIn("(som-outlook (safe))", text)
        self.assertIn("(som-fresh (t))", text)


if __name__ == "__main__":
    unittest.main()
