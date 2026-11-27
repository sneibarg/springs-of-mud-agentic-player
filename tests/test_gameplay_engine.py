import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.WorkingMemory import WorkingMemory
from net.rest.KmAnswer import KmAnswer
from play.CommandChannel import CommandChannel, PromptTimeout
from play.GameplayEngine import GameplayEngine
from play.LevelGoal import LevelGoal
from memory.PlayClock import PlayClock
from play.WorldKnowledge import PlayerRecord, RoomSnapshot, WorldKnowledge


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


class _Situation:
    def __init__(self, attempts="nil"):
        self.attempts = attempts
        self.queries = []
        self.assertions = []

    def query(self, expression):
        self.queries.append(expression)
        if "som-attempts" in expression:
            return KmAnswer(ok=True, answer=self.attempts)
        if "som-notch" in expression:
            return KmAnswer(ok=True, answer="(steady)")
        if "som-cooldown" in expression:
            return KmAnswer(ok=True, answer="(0)")
        if "som-licensed-rule" in expression:
            return KmAnswer(ok=True, answer="(10)")
        return KmAnswer(ok=True, answer="nil")

    def assert_expression(self, expression):
        self.assertions.append(expression)
        return KmAnswer(ok=True, answer="(*Frame)")


def _channel(client: _QueueClient) -> CommandChannel:
    clock = _Clock()
    return CommandChannel(client, timeout_s=0.2, poll_interval_s=0.1, clock=clock, sleep=clock.sleep)


def _engine(client, km, *, goal=True, room_current=False, clock=None, commands=None, player=None):
    memory = WorkingMemory()
    if clock is not None:
        memory.session.progress = clock
    memory.observe_commands(commands or ["look", "score", "north", "flee", "kill", "save", "consider"])
    knowledge = WorldKnowledge()
    if room_current:
        knowledge.room = RoomSnapshot(name="The Temple of Mota", description="", exits=["north"])
    level_goal = LevelGoal(target_level=5, risk="cautious", minutes=0) if goal else None
    return GameplayEngine(_channel(client), memory, knowledge, km, goal=level_goal, room_current=room_current, player=player)


_SCORE = ["You are Example the novice, level 1, 17 years old (0 hours).", "You have 30/30 hit, 100/100 mana, 100/100 movement.", "You need 1000 exp to level.", "You are standing.", "<30hp 100m 100mv>"]
_LOOK = ["The Temple of Mota", "A quiet temple.", "Obvious exits:", "North", "a goblin is here.", "<30hp 100m 100mv>"]


class TestGameplayEngine(unittest.TestCase):
    def test_recreating_the_engine_preserves_progress_fresh_readings_and_combat(self):
        client = _QueueClient()
        client.on_send["look"] = list(_LOOK)
        client.on_send["score"] = list(_SCORE)
        client.on_send["consider a goblin"] = ["A goblin looks like an easy kill.", "<30hp 100m 100mv>"]
        client.on_send["kill a goblin"] = ["You attack a goblin.", "<10hp 100m 100mv>"]
        client.on_send["flee"] = ["You flee north.", "<10hp 100m 100mv>"]
        km = _Km('((:args survey "information / communication" consider "a goblin"))')
        engine = _engine(client, km)
        self.assertEqual(engine.step(), "look")
        self.assertEqual(engine.step(), "score")
        self.assertEqual(engine.step(), "consider a goblin")
        session = engine.memory.session
        session.progress.cooldown_steps = 4
        session.progress.saves = 2
        session.areas_unread = True

        km.attempts = '((:args engage combat kill "a goblin"))'
        recreated = GameplayEngine(_channel(client), engine.memory, engine.knowledge, km, goal=engine.goal)
        self.assertIs(recreated.memory.session, session)
        self.assertEqual(session.progress.cooldown_steps, 4)
        self.assertEqual(session.progress.saves, 2)
        self.assertEqual(recreated.step(), "kill a goblin")
        question = "\n".join(km.questions[-1])
        self.assertIn("(som-outlook (safe))", question)
        self.assertIn("(som-fresh (t))", question)
        self.assertIn("(som-score-count (1))", question)
        self.assertIn("(som-cooldown-steps (4))", question)
        self.assertIn("(som-saves (2))", question)
        self.assertTrue(session.combat.fighting)
        self.assertIn(engine.memory.resolve_current_being("a goblin").being_id, session.combat.engaged)
        self.assertIsNone(session.pending_action)

        questions = len(km.questions)
        after_attack = GameplayEngine(_channel(client), engine.memory, engine.knowledge, km, goal=engine.goal)
        self.assertEqual(after_attack.channel.last_prompt, "")
        self.assertEqual(after_attack.step(), "flee")
        self.assertEqual(len(km.questions), questions)
        self.assertFalse(session.combat.fighting)
        self.assertEqual(client.sent, ["look", "score", "consider a goblin", "kill a goblin", "flee"])

    def test_recreating_the_engine_preserves_tried_exits_and_uninvited_threats(self):
        client = _QueueClient()
        client.on_send["north"] = ["You cannot go that way.", "<30hp 100m 100mv>"]
        client.on_send["look"] = ["The Temple of Mota", "Obvious exits:", "North", "East", "a wolf is here, fighting YOU!", "<30hp 100m 100mv>"]
        client.on_send["east"] = ["You cannot go that way.", "<30hp 100m 100mv>"]
        km = _Km('((:args travel movement north ""))')
        engine = _engine(client, km, room_current=True, clock=PlayClock(score_count=1, level=1), commands=["look", "north", "east", "flee"])
        self.assertEqual(engine.step(), "north")
        self.assertEqual(engine.memory.session.room.tried, {"north"})

        recreated = GameplayEngine(_channel(client), engine.memory, engine.knowledge, km, goal=engine.goal, room_current=True)
        client.pending = list(client.on_send["look"])
        recreated._observe(recreated.channel.drain(), "")
        self.assertEqual(recreated.memory.session.combat.threats, {recreated.memory.resolve_current_being("a wolf").being_id})
        after_look = GameplayEngine(_channel(client), engine.memory, engine.knowledge, km, goal=engine.goal)
        self.assertEqual(after_look.step(), "east")
        self.assertEqual(client.sent, ["north", "east"])
        self.assertEqual(len(km.questions), 1)

    def test_an_interrupted_exchange_remains_visible_and_is_not_resent(self):
        client = _QueueClient()
        engine = _engine(client, _Km(), goal=False)
        with self.assertRaises(PromptTimeout):
            engine.step()
        pending = engine.memory.session.pending_action
        self.assertEqual(pending.command, "look")
        self.assertFalse(pending.response_received)
        self.assertEqual(engine.memory.to_review()["session"]["pending_action"]["command"], "look")

        recreated = GameplayEngine(_channel(client), engine.memory, engine.knowledge, engine.km)
        self.assertEqual(recreated.step(), "")
        self.assertIs(recreated.memory.session.pending_action, pending)
        self.assertEqual(client.sent, ["look"])

    def test_unread_reply_markers_survive_engine_recreation_and_clear_resets_it(self):
        client = _QueueClient()
        client.on_send["look"] = ["You cannot see anything.", "<30hp 100m 100mv>"]
        engine = _engine(client, _Km(), goal=False)
        self.assertEqual(engine.step(), "look")
        recreated = GameplayEngine(_channel(client), engine.memory, engine.knowledge, engine.km)
        self.assertEqual(recreated.step(), "")
        self.assertEqual(client.sent, ["look"])

        engine.memory.clear()
        engine.memory.observe_commands(["look"])
        self.assertEqual(recreated.step(), "look")
        self.assertEqual(client.sent, ["look", "look"])

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

    def test_a_player_situation_is_asked_and_baseline_is_not(self):
        client = _QueueClient()
        client.on_send["north"] = ["The North Road", "Obvious exits:", "South", "<30hp 100m 100mv>"]
        km = _Km('((:args travel movement north ""))')
        player = _Situation('((:args travel movement north ""))')
        clock = PlayClock(start_level=1, level=1, exp_to_level=1000, exp_span=1000, score_count=1, saves=1)
        engine = _engine(client, km, room_current=True, clock=clock, player=player)

        self.assertEqual(engine.step(), "north")
        self.assertEqual(km.questions, [])
        self.assertTrue(player.queries)
        self.assertTrue(all(item.startswith("(the ") for item in player.queries))
        self.assertTrue(player.assertions)
        self.assertFalse(any(item.startswith("(the ") for item in player.assertions))

    def test_an_uninvited_fight_leaves_and_does_not_ask_km_to_kill(self):
        client = _QueueClient()
        client.pending = ["a goblin is here, fighting YOU!", "<30hp 100m 100mv>"]
        client.on_send["north"] = ["The North Road", "Obvious exits:", "South", "<30hp 100m 100mv>"]
        km = _Km("((:args engage combat kill goblin))")
        clock = PlayClock(start_level=1, level=1, exp_to_level=1000, exp_span=1000, score_count=1)
        engine = _engine(client, km, room_current=True, clock=clock)

        self.assertEqual(engine.step(), "north")
        self.assertEqual(km.questions, [])
        self.assertNotIn("kill goblin", client.sent)

    def test_low_hit_points_while_fighting_flee_before_a_hunt(self):
        client = _QueueClient()
        client.on_send["flee"] = ["You flee north.", "<10hp 100m 100mv>"]
        km = _Km("((:args engage combat kill goblin))")
        clock = PlayClock(start_level=1, level=1, exp_to_level=1000, exp_span=1000, score_count=1)
        engine = _engine(client, km, room_current=True, clock=clock)
        engine.memory.session.combat.fighting = True
        engine.memory.session.combat.hit = 10
        engine.memory.session.combat.max_hit = 30
        engine.channel.last_prompt = "<10hp 100m 100mv>"
        engine.memory.session.combat.engaged.add("goblin")

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
        client.pending = ["The Temple of Mota", "Obvious exits:", "North", "Marcus is here.", "goblin is here.", "<30hp 100m 100mv>"]
        engine.knowledge.remember_player(PlayerRecord(name="Marcus", level=1, race="human", character_class="War"))
        engine._observe(engine.channel.drain(), "")
        goblin = engine.memory.resolve_current_being("goblin")
        engine.memory.remember_consider("goblin", ["goblin looks like an easy kill."], kind="mobile", being_id=goblin.being_id)
        engine.memory.session.room.note_consider(goblin.being_id)

        self.assertEqual(engine.step(), "")
        text = "\n".join(km.questions[0])
        self.assertNotIn("Marcus", text)
        self.assertIn("(som-outlook (safe))", text)
        self.assertIn("(som-fresh (t))", text)


if __name__ == "__main__":
    unittest.main()
