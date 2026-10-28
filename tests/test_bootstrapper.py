import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from play.Bootstrapper import Bootstrapper, CommandLesson, HelpLesson
from play.CommandChannel import CommandChannel
from play.PlayError import AuthenticationRejected, CharacterSavePending
from play.WorldKnowledge import WorldKnowledge
from prompt.Prompt import Prompt


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _ScriptedClient:
    def __init__(self, opening: list[str], replies: dict[str, list[str]]):
        self.connected = True
        self.sent: list[str] = []
        self._pending = list(opening)
        self._replies = replies

    def send_line(self, text: str) -> None:
        self.sent.append(text)
        self._pending.extend(self._replies.get(text, []))
        self._pending.append("<10hp 10m 10mv>")

    def poll_line(self):
        if self._pending:
            return self._pending.pop(0)
        return None


class _Model:
    def __init__(self, text: str):
        self.text = text
        self.bodies = []

    def complete(self, body):
        self.bodies.append(body)
        if callable(self.text):
            return self.text(body)
        return self.text


class TestBootstrapper(unittest.TestCase):
    def test_first_login_reads_help_then_world(self):
        client = _ScriptedClient(
            opening=["Welcome to the server!", "<10hp 10m 10mv>"],
            replies={
                "commands": ["look          help          areas         who           "],
                "help look": ["LOOK", "Look around."],
                "help help": ["HELP", "Read a help page."],
                "help areas": ["AREAS", "List the areas."],
                "help who": ["WHO", "See who is playing."],
                "areas": [f"{'[1-5] Romy: Temple of Mota':<39}"],
                "who": ["[1    human    Mag] Example the agent", "Players found: 1"],
                "look": [
                    "Temple of Mota",
                    "\t\tA quiet temple.",
                    "A goblin is here.",
                    "Marcus is here.",
                    "Example is resting here.",
                ],
            },
        )
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        bootstrapper = Bootstrapper(None, ["Example", "Other"], "Example", channel=channel)
        knowledge = bootstrapper.bootstrap()

        self.assertEqual(
            client.sent,
            ["commands", "help look", "help help", "help areas", "help who", "areas", "who", "look"],
        )
        self.assertEqual(
            [command.name for command in bootstrapper.memory.commands()],
            ["look", "help", "areas", "who"],
        )
        self.assertTrue(all(command.category == "" for command in bootstrapper.memory.commands()))
        self.assertEqual(knowledge.login_lines, ["Welcome to the server!"])
        self.assertEqual(knowledge.help_for("look").text, "Look around.")
        self.assertEqual(knowledge.area_named("Temple of Mota").author, "Romy")
        example = knowledge.player_named("Example")
        self.assertTrue(example.agentic)
        self.assertTrue(example.self_character)
        self.assertEqual(example.room_name, "Temple of Mota")
        self.assertEqual(knowledge.room.name, "Temple of Mota")
        self.assertIn("temple of mota|a goblin", knowledge.mobiles)
        self.assertIn("temple of mota|marcus", knowledge.npcs)
        self.assertEqual(knowledge.npcs["temple of mota|marcus"].kind, "npc")

    def test_learn_commands_keeps_the_prompt_and_the_model_response(self):
        columns = "look        help        areas       "
        client = _ScriptedClient(opening=[], replies={"commands": [columns]})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompt = Prompt(
            name="commands",
            model="gpt-oss:20b",
            system="Read the command columns.",
            user="example only",
            json_schema={"type": "object", "required": ["commands"]},
            tokens={},
        )
        model = _Model('{"commands": ["look", "help", "areas"]}')
        lesson = Bootstrapper(None, [], "Example", channel=channel).learn_commands(prompt, model)

        self.assertEqual(client.sent, ["commands"])
        self.assertEqual(lesson.commands, ["look", "help", "areas"])
        self.assertEqual(lesson.prompt["system"], "Read the command columns.")
        self.assertEqual(lesson.prompt["user"], columns)
        self.assertEqual(lesson.prompt["model"], "gpt-oss:20b")
        self.assertEqual(lesson.response, '{"commands": ["look", "help", "areas"]}')
        self.assertEqual(model.bodies, [lesson.prompt])
        review = lesson.to_review()
        self.assertEqual(review["prompt"], lesson.prompt)
        self.assertEqual(review["response"], lesson.response)
        self.assertEqual(review["parsedCommands"], ["look", "help", "areas"])
        self.assertNotIn("parseError", review)

    def test_unparsed_model_text_stays_in_the_review(self):
        lesson = CommandLesson(prompt={"system": "Read the columns.", "user": "look"}, response="not json", commands=["look"])
        review = lesson.to_review()
        self.assertEqual(review["prompt"]["user"], "look")
        self.assertEqual(review["response"], "not json")
        self.assertIsNone(review["parsedCommands"])
        self.assertIn("parseError", review)

    def test_learn_help_stores_each_prompt_and_the_model_topics(self):
        client = _ScriptedClient(
            opening=[],
            replies={
                "help look": ["LOOK", "Look around."],
                "help xyz": ["No help on that word."],
            },
        )
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompt = Prompt(
            name="help",
            model="gpt-oss:20b",
            system="Read the help page.",
            user="example only",
            json_schema={"type": "object", "required": ["missing", "topics"]},
            tokens={},
        )

        def reply(body):
            if "No help" in body["user"]:
                return '{"missing": true, "topics": []}'
            return '{"missing": false, "topics": [{"keyword": "LOOK", "text": "Look around."}]}'

        model = _Model(reply)
        bootstrapper = Bootstrapper(None, [], "Example", channel=channel)
        seen = []
        lessons = bootstrapper.learn_help(prompt, model, names=["look", "xyz"], on_lesson=seen.append)

        self.assertEqual(client.sent, ["help look", "help xyz"])
        self.assertEqual(seen, lessons)
        self.assertEqual(lessons[0].prompt["system"], "Read the help page.")
        self.assertEqual(lessons[0].prompt["user"], "LOOK\nLook around.")
        self.assertEqual(lessons[0].prompt["model"], "gpt-oss:20b")
        self.assertNotIn("parseError", lessons[0].to_review())
        look = bootstrapper.knowledge.help_for("look")
        self.assertFalse(look.missing)
        self.assertEqual(look.keyword, "LOOK")
        self.assertEqual(look.text, "Look around.")
        self.assertEqual(look.topics[0].keyword, "LOOK")
        self.assertEqual(bootstrapper.memory.command_named("look").help_text, "Look around.")
        missing = bootstrapper.knowledge.help_for("xyz")
        self.assertTrue(missing.missing)
        self.assertEqual(missing.topics, [])
        self.assertEqual(missing.keyword, "")
        self.assertEqual(bootstrapper.memory.command_named("xyz").help_text, "")
        document = bootstrapper.knowledge.to_document(
            character_id="char-1",
            character_name="Example",
            agent_name="example-agent",
        )
        restored = WorldKnowledge.from_document(document)
        self.assertEqual(restored.help_for("look").topics[0].text, "Look around.")
        self.assertTrue(restored.help_for("xyz").missing)

    def test_unparsed_help_keeps_the_response_and_the_server_topic(self):
        client = _ScriptedClient(opening=[], replies={"help look": ["LOOK", "Look around."]})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompt = Prompt(
            name="help",
            model="gpt-oss:20b",
            system="Read the help page.",
            user="example only",
            json_schema={"type": "object"},
            tokens={},
        )
        bootstrapper = Bootstrapper(None, [], "Example", channel=channel)
        lesson = bootstrapper.learn_help(prompt, _Model("not json"), names=["look"])[0]
        review = lesson.to_review()
        self.assertEqual(review["command"], "look")
        self.assertEqual(review["prompt"]["user"], "LOOK\nLook around.")
        self.assertEqual(review["response"], "not json")
        self.assertIsNone(review["parsed"])
        self.assertIn("parseError", review)
        stored = bootstrapper.knowledge.help_for("look")
        self.assertEqual(stored.keyword, "LOOK")
        self.assertEqual(stored.text, "Look around.")
        self.assertEqual(stored.topics, [])
        self.assertEqual(bootstrapper.memory.command_named("look").help_text, "")

    def test_unparsed_help_lesson_stays_in_the_review(self):
        lesson = HelpLesson(command="look", prompt={"system": "Read.", "user": "LOOK"}, response="not json")
        review = lesson.to_review()
        self.assertEqual(review["response"], "not json")
        self.assertIsNone(review["parsed"])
        self.assertIn("parseError", review)

    def test_rejected_logon_does_not_send_commands(self):
        client = _ScriptedClient(opening=["ERROR: Authentication failed."], replies={})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        with self.assertRaises(AuthenticationRejected):
            Bootstrapper(None, ["Example"], "Example", channel=channel).bootstrap()
        self.assertEqual(client.sent, [])

    def test_saved_character_stops_before_commands(self):
        client = _ScriptedClient(
            opening=["ERROR: That character is being saved. Please reconnect in a moment."],
            replies={},
        )
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        with self.assertRaises(CharacterSavePending):
            Bootstrapper(None, ["Example"], "Example", channel=channel).bootstrap()
        self.assertEqual(client.sent, [])

    def test_read_stops_when_the_prompt_never_arrives(self):
        client = _ScriptedClient(opening=["Welcome to the server!"], replies={})
        client._pending = ["partial"]
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=0.2, poll_interval_s=0.1, clock=clock, sleep=clock.sleep)
        lines = channel.read_until_prompt()
        self.assertEqual(lines, ["partial"])
        self.assertFalse(channel.saw_prompt)


if __name__ == "__main__":
    unittest.main()
