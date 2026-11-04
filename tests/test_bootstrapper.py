import json
import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path

from play.Bootstrapper import Bootstrapper
from play.CategoryLesson import CategoryLesson
from play.CommandLesson import CommandLesson
from play.HelpLesson import HelpLesson
from play.CommandChannel import CommandChannel
from play.PlayError import AuthenticationRejected, CharacterSavePending
from play.WorldKnowledge import WorldKnowledge
from prompt.Prompt import Prompt
from prompt.PromptCollection import PromptCollection


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
        client = _ScriptedClient(opening=["Welcome to the server!", "<10hp 10m 10mv>"], replies={"commands": ["look          help          areas         who           "], "help look": ["LOOK", "Look around."], "help help": ["HELP", "Read a help page."], "help areas": ["AREAS", "List the areas."], "help who": ["WHO", "See who is playing."], "areas": [f"{'[1-5] Romy: Temple of Mota':<39}"], "who": ["[1    human    Mag] Example the agent", "Players found: 1"], "look": ["Temple of Mota", "\t\tA quiet temple.", "A goblin is here.", "Marcus is here.", "Example is resting here."]})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        published = {}

        def on_commands(snapshot):
            published["names"] = [command.name for command in snapshot.command_records()]
            published["help"] = snapshot.help_for("look").text
            published["areas"] = len(snapshot.areas)

        bootstrapper = Bootstrapper(None, ["Example", "Other"], "Example", channel=channel, on_commands=on_commands)
        knowledge = bootstrapper.bootstrap()

        self.assertEqual(client.sent, ["commands", "help look", "help help", "help areas", "help who", "areas", "who", "look"])
        self.assertEqual(published["names"], ["look", "help", "areas", "who"])
        self.assertEqual(published["help"], "Look around.")
        self.assertEqual(published["areas"], 0)
        self.assertEqual([command.name for command in bootstrapper.memory.commands()], ["look", "help", "areas", "who"])
        self.assertEqual([command.help_text for command in bootstrapper.memory.commands()], ["Look around.", "Read a help page.", "List the areas.", "See who is playing."])
        self.assertEqual([command.help_text for command in knowledge.command_records()], ["Look around.", "Read a help page.", "List the areas.", "See who is playing."])
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

    def test_defer_true_does_not_send_ollama(self):
        index = "MOVEMENT                            OTHER\nnorth                                !"
        client = _ScriptedClient(opening=["Welcome to the server!", "<10hp 10m 10mv>"], replies={"help": [index], "commands": ["look        north       "], "help look": ["LOOK", "Look around.", "LOOK <thing>", "Look at something."], "help north": ["NORTH", "Walk north."], "help !": ["!", "Repeat the last command."], "areas": [f"{'[1-5] Romy: Temple of Mota':<39}"], "who": ["[1    human    Mag] Example the agent", "Players found: 1"], "look": ["Temple of Mota", "A quiet temple."]})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompts = {"categories": Prompt(name="categories", model="gpt-oss:20b", system="Read the help index.", user="{categories}", json_schema={"type": "object", "required": ["categories"]}, tokens={}), "commands": Prompt(name="commands", model="gpt-oss:20b", system="Read the command columns.", user="{commands}", json_schema={"type": "object", "required": ["commands"]}, tokens={}), "help": Prompt(name="help", model="gpt-oss:20b", system="Read the help page.", user="{help}", json_schema={"type": "object", "required": ["missing", "topics"]}, tokens={}), "look": Prompt(name="look", model="gpt-oss:20b", system="Read the room.", user="{look}", json_schema={"type": "object"}, tokens={})}
        model = _Model('{"categories": [{"name": "movement", "commands": ["north"]}]}')
        published = []
        bootstrapper = Bootstrapper(None, ["Example"], "Example", channel=channel, on_commands=published.append, prompts=prompts, ollama=model, defer=True)
        knowledge = bootstrapper.bootstrap()

        self.assertEqual(model.bodies, [])
        self.assertTrue(published)
        self.assertEqual(client.sent, ["commands", "help look", "help north", "areas", "who", "look"])
        self.assertEqual([command.name for command in bootstrapper.memory.commands()], ["look", "north"])
        self.assertTrue(all(command.category == "" for command in bootstrapper.memory.commands()))
        self.assertIn("Look around.", knowledge.help_for("look").text)
        self.assertEqual(knowledge.help_for("look").topics, [])
        self.assertIsNone(knowledge.help_for("!"))
        self.assertEqual(knowledge.room.items, [])
        self.assertEqual(WorldKnowledge.summary(knowledge).split("\n")[0], "Knowledge: 2 help, 0 topics, 2 commands, 0 categorized, 1 areas, 0 mobiles, 0 npcs, 1 players, 0 items.")

    def test_defer_false_keeps_ollama_results_in_working_memory(self):
        client = _ScriptedClient(opening=["Welcome to the server!", "<10hp 10m 10mv>"], replies={"help": ["MOVEMENT\nnorth"], "commands": ["look        north       "], "help look": ["LOOK", "Look around.", "LOOK <thing>", "Look at something."], "help north": ["NORTH", "Walk north."], "areas": [f"{'[1-5] Romy: Temple of Mota':<39}"], "who": ["[1    human    Mag] Example the agent", "Players found: 1"], "look": ["Temple of Mota", "You are by the altar. There is a sign on the wall."]})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompts = {"categories": Prompt(name="categories", model="gpt-oss:20b", system="Read the help index.", user="{categories}", json_schema={"type": "object", "required": ["categories"]}, tokens={}), "commands": Prompt(name="commands", model="gpt-oss:20b", system="Read the command columns.", user="{commands}", json_schema={"type": "object", "required": ["commands"]}, tokens={}), "help": Prompt(name="help", model="gpt-oss:20b", system="Read the help page.", user="{help}", json_schema={"type": "object", "required": ["missing", "topics"]}, tokens={}), "look": Prompt(name="look", model="gpt-oss:20b", system="Read the room.", user="{look}", json_schema={"type": "object"}, tokens={})}

        def answer(body):
            if body["system"].startswith("Read the help index."):
                return json.dumps({"categories": [{"name": "movement", "commands": ["north"]}]})
            if body["system"].startswith("Read the command columns."):
                return json.dumps({"commands": ["look", "north"]})
            if body["system"] == "Read the room.":
                return json.dumps({"name": "Temple of Mota", "items": [{"name": "sign", "line": "There is a sign on the wall.", "source": "description"}]})
            if "LOOK <thing>" in body["user"]:
                return json.dumps({"missing": False, "topics": [{"keyword": "LOOK", "text": "Look around."}, {"keyword": "LOOK <thing>", "text": "Look at something."}], "category": "information"})
            return json.dumps({"missing": False, "topics": [{"keyword": "NORTH", "text": "Walk north."}]})

        published = []
        model = _Model(answer)
        bootstrapper = Bootstrapper(None, ["Example"], "Example", channel=channel, on_commands=published.append, prompts=prompts, ollama=model)
        knowledge = bootstrapper.bootstrap()

        self.assertTrue(model.bodies)
        self.assertEqual(published, [])
        self.assertIsNone(knowledge.help_for("look"))
        self.assertEqual(knowledge.command_records(), [])
        self.assertEqual(knowledge.room.items, [])
        self.assertEqual(bootstrapper.memory.command_named("north").category, "movement")
        self.assertEqual(bootstrapper.memory.command_named("look").category, "information")
        self.assertIn("Look around.", bootstrapper.memory.command_named("look").help_text)
        self.assertEqual(bootstrapper.memory.room_named("Temple of Mota").items[0].name, "sign")

    def test_login_room_is_sent_as_the_user_prompt(self):
        look = ["By the Temple Altar", "    A pit for sacrifices is in front of the altar.", "A healer is here."]
        client = _ScriptedClient(opening=["Welcome to the server!", "<10hp 10m 10mv>"], replies={"commands": ["look          help          areas         who           "], "help look": ["LOOK", "Look around."], "help help": ["HELP", "Read a help page."], "help areas": ["AREAS", "List the areas."], "help who": ["WHO", "See who is playing."], "areas": [f"{'[1-5] Romy: Temple of Mota':<39}"], "who": ["[1    human    Mag] Example the agent", "Players found: 1"], "look": look})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        room = "\n".join(look)
        prompts = {"items": Prompt(name="items", model="gpt-oss:20b", system="Classify the items.", user="By the Temple Altar is a sample, not the live room.", json_schema={"type": "object", "required": ["items"]}, tokens={}), "look": Prompt(name="look", model="gpt-oss:20b", system="Read the room.", user="{look}", json_schema={"type": "object"}, tokens={})}
        model = _Model('{"items": [{"name": "pit", "line": "A pit for sacrifices is in front of the altar.", "itemType": "container"}]}')

        Bootstrapper(None, ["Example"], "Example", channel=channel, prompts=prompts, ollama=model).bootstrap()

        self.assertEqual([body["user"] for body in model.bodies], [room, room])
        self.assertNotIn("sample", model.bodies[0]["user"])

    def test_look_prompt_notes_a_sign_on_the_session_room(self):
        look = ["By the Temple Altar", "You are by the altar. There is a sign on the wall.", "    A pit for sacrifices is in front of the altar."]
        client = _ScriptedClient(opening=["Welcome to the server!", "<10hp 10m 10mv>"], replies={"commands": ["look          help          areas         who           "], "help look": ["LOOK", "Look around."], "help help": ["HELP", "Read a help page."], "help areas": ["AREAS", "List the areas."], "help who": ["WHO", "See who is playing."], "areas": [f"{'[1-5] Romy: Temple of Mota':<39}"], "who": ["[1    human    Mag] Example the agent", "Players found: 1"], "look": look})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompts = {"look": Prompt(name="look", model="gpt-oss:20b", system="Read the room.", user="{look}", json_schema={"type": "object"}, tokens={}), "items": Prompt(name="items", model="gpt-oss:20b", system="Classify the items.", user="{look}", json_schema={"type": "object"}, tokens={})}

        def answer(body):
            if body["system"] == "Read the room.":
                return json.dumps({"name": "By the Temple Altar", "description": "You are by the altar. There is a sign on the wall.", "exits": ["south"], "items": [{"name": "sign", "line": "There is a sign on the wall.", "source": "description"}, {"name": "pit", "line": "A pit for sacrifices is in front of the altar.", "source": "object"}], "beings": []})
            return '{"items": []}'

        bootstrapper = Bootstrapper(None, ["Example"], "Example", channel=channel, prompts=prompts, ollama=_Model(answer))
        bootstrapper.bootstrap()
        bootstrapper.memory.absorb_world(bootstrapper.knowledge)
        room = bootstrapper.memory.room_named("By the Temple Altar")
        self.assertEqual([(item.name, item.line, item.source) for item in room.items], [("sign", "There is a sign on the wall.", "description"), ("pit", "A pit for sacrifices is in front of the altar.", "object")])
        bootstrapper._remember_look_items("not json")
        self.assertEqual(bootstrapper.memory.room_named("By the Temple Altar").items[0].name, "sign")

    def test_learn_commands_keeps_the_prompt_and_the_model_response(self):
        columns = "look        help        areas       "
        client = _ScriptedClient(opening=[], replies={"commands": [columns]})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompt = Prompt(name="commands", model="gpt-oss:20b", system="Read the command columns.", user="example only", json_schema={"type": "object", "required": ["commands"]}, tokens={})
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
        client = _ScriptedClient(opening=[], replies={"help look": ["LOOK", "Look around."], "help xyz": ["No help on that word."]})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompt = Prompt(name="help", model="gpt-oss:20b", system="Read the help page.", user="example only", json_schema={"type": "object", "required": ["missing", "topics"]}, tokens={})

        def reply(body):
            if "No help" in body["user"]:
                return '{"missing": true, "topics": [], "category": "other"}'
            return '{"missing": false, "topics": [{"keyword": "LOOK", "text": "Look around."}]}'

        model = _Model(reply)
        bootstrapper = Bootstrapper(None, [], "Example", channel=channel)
        bootstrapper.memory.remember_command("look", category="information")
        seen = []
        lessons = bootstrapper.learn_help(prompt, model, names=["look", "xyz"], on_lesson=seen.append)

        self.assertEqual(client.sent, ["help look", "help xyz"])
        self.assertEqual(seen, lessons)
        self.assertEqual(lessons[0].prompt["system"], "Read the help page.")
        self.assertNotIn("category", lessons[0].prompt["jsonSchema"].get("required", []))
        self.assertEqual(lessons[0].prompt["user"], "LOOK\nLook around.")
        self.assertIn("The category for this command is not known yet.", lessons[1].prompt["system"])
        self.assertIn("category", lessons[1].prompt["jsonSchema"]["required"])
        self.assertEqual(bootstrapper.memory.command_named("look").category, "information")
        self.assertEqual(bootstrapper.memory.command_named("xyz").category, "other")
        self.assertNotIn("category", prompt.json_schema.get("required", []))
        self.assertEqual(lessons[0].prompt["model"], "gpt-oss:20b")
        self.assertNotIn("parseError", lessons[0].to_review())
        parsed, parse_error = lessons[0].parsed_help()
        self.assertIsNotNone(parsed, parse_error)
        self.assertFalse(parsed["missing"])
        self.assertEqual(parsed["topics"][0], {"keyword": "LOOK", "text": "Look around."})
        self.assertEqual(bootstrapper.memory.command_named("look").help_text, "Look around.")
        self.assertIsNone(bootstrapper.knowledge.help_for("look"))
        missing, missing_error = lessons[1].parsed_help()
        self.assertIsNotNone(missing, missing_error)
        self.assertTrue(missing["missing"])
        self.assertEqual(missing["topics"], [])
        self.assertEqual(bootstrapper.memory.command_named("xyz").help_text, "")
        self.assertIsNone(bootstrapper.knowledge.help_for("xyz"))
        self.assertEqual(bootstrapper.knowledge.command_records(), [])

    def test_unparsed_help_keeps_the_response_and_the_server_topic(self):
        client = _ScriptedClient(opening=[], replies={"help look": ["LOOK", "Look around."]})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompt = Prompt(name="help", model="gpt-oss:20b", system="Read the help page.", user="example only", json_schema={"type": "object"}, tokens={})
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

    def test_help_index_stores_categories_without_replacing_one(self):
        index = "\n".join(["MOVEMENT                            GROUP", "north south east west up down       follow group gtell split"])
        client = _ScriptedClient(opening=[], replies={"help": [index]})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompt = Prompt(name="categories", model="gpt-oss:20b", system="Read the help index.", user="example only", json_schema={"type": "object", "required": ["categories"]}, tokens={})
        model = _Model(json.dumps({"categories": [{"name": "Movement", "commands": ["north", "south", "follow"]}, {"name": "group", "commands": ["follow", "group"]}]}))
        bootstrapper = Bootstrapper(None, [], "Example", channel=channel)
        bootstrapper.memory.remember_command("north", category="movement")
        lesson = bootstrapper.learn_categories(prompt, model)

        self.assertEqual(client.sent, ["help"])
        self.assertEqual(lesson.prompt["user"], index)
        self.assertEqual(lesson.prompt["system"], "Read the help index.")
        self.assertNotIn("parseError", lesson.to_review())
        self.assertEqual(bootstrapper.memory.command_named("north").category, "movement")
        self.assertEqual(bootstrapper.memory.command_named("south").category, "movement")
        self.assertEqual(bootstrapper.memory.command_named("follow").category, "movement")
        self.assertEqual(bootstrapper.memory.command_named("group").category, "group")
        self.assertEqual(lesson.to_review()["parsedCategories"], [{"name": "movement", "commands": ["north", "south", "follow"]}, {"name": "group", "commands": ["group"]}])

    def test_command_list_keeps_categories_already_stored(self):
        columns = "look        help        "
        client = _ScriptedClient(opening=[], replies={"commands": [columns]})
        clock = _Clock()
        channel = CommandChannel(client, timeout_s=1.0, clock=clock, sleep=clock.sleep)
        prompt = Prompt(name="commands", model="gpt-oss:20b", system="Read the command columns.", user="example only", json_schema={"type": "object"}, tokens={})
        bootstrapper = Bootstrapper(None, [], "Example", channel=channel)
        bootstrapper.memory.remember_command("look", category="information")
        lesson = bootstrapper.learn_commands(prompt, _Model('{"commands": ["look", "help"]}'))
        self.assertEqual(lesson.commands, ["look", "help"])
        self.assertEqual(bootstrapper.memory.command_named("look").category, "information")
        self.assertEqual(bootstrapper.memory.command_named("help").category, "")

    def test_help_reading_includes_commands_the_list_omitted(self):
        bootstrapper = Bootstrapper(None, [], "Example", channel=object())
        bootstrapper.memory.remember_command("north", category="movement")
        bootstrapper.memory.remember_command("!", category="other")
        self.assertEqual(bootstrapper.commands_for_help(["look", "North", "help"]), ["look", "north", "help", "!"])
        self.assertEqual(bootstrapper.commands_for_help(None), ["north", "!"])

    def test_categories_prompt_loads_from_the_collection(self):
        prompt = PromptCollection.load(Path(__file__).resolve().parents[1] / "resources" / "collections" / "SOMDB.Prompts.json").get("categories")
        self.assertEqual(prompt.model, "gpt-oss:20b")
        self.assertIn("36 characters", prompt.system)
        self.assertIn("categories", prompt.json_schema["required"])

    def test_items_prompt_classifies_interactable_room_objects(self):
        prompt = PromptCollection.load(Path(__file__).resolve().parents[1] / "resources" / "collections" / "SOMDB.Prompts.json").get("items")
        item = prompt.json_schema["properties"]["items"]["items"]
        self.assertEqual(prompt.model, "gpt-oss:20b")
        self.assertEqual(prompt.json_schema["required"], ["items"])
        self.assertEqual(item["required"], ["name", "line", "itemType"])
        self.assertIn("container", item["properties"]["itemType"]["enum"])
        self.assertIn("pit", prompt.system)
        self.assertEqual(prompt.user, "{look}")
        room = "By the Temple Altar\n    A pit for sacrifices is in front of the altar."
        self.assertEqual(prompt.for_text(room).user, room)

    def test_room_look_prompt_extracts_items_named_in_the_description(self):
        prompt = PromptCollection.load(Path(__file__).resolve().parents[1] / "resources" / "collections" / "SOMDB.Prompts.json").get("look")
        item = prompt.json_schema["properties"]["items"]["items"]
        self.assertEqual(prompt.user, "{look}")
        self.assertEqual(prompt.json_schema["required"], ["name", "description", "exits", "items", "beings"])
        self.assertEqual(item["required"], ["name", "line", "source"])
        self.assertEqual(item["properties"]["source"]["enum"], ["object", "description"])
        self.assertIn("There is a sign on the wall.", prompt.system)
        self.assertIn("look sign", prompt.system)
        self.assertIn("signs of", prompt.system)

    def test_look_target_prompts_read_the_command_reply(self):
        prompts = PromptCollection.load(Path(__file__).resolve().parents[1] / "resources" / "collections" / "SOMDB.Prompts.json")
        self.assertEqual(prompts.get("look").user, "{look}")
        item = prompts.get("look_item")
        player = prompts.get("look_player")
        mobile = prompts.get("look_mobile")
        direction = prompts.get("look_direction")
        self.assertEqual(item.model, "gpt-oss:20b")
        self.assertEqual(item.user, "{item}")
        self.assertEqual(item.json_schema["required"], ["found", "result", "name", "description"])
        self.assertIn("missing", item.json_schema["properties"]["result"]["enum"])
        self.assertIn("pit", item.system)
        reply = "A pit for sacrifices is in front of the altar."
        self.assertEqual(item.for_text(reply).user, reply)
        self.assertEqual(player.user, "{player}")
        self.assertEqual(player.json_schema["required"], ["found", "name", "description", "condition", "equipment", "inventory"])
        self.assertIn("excellent", player.json_schema["properties"]["condition"]["enum"])
        self.assertIn("wielded", player.json_schema["properties"]["equipment"]["items"]["properties"]["slot"]["enum"])
        self.assertIn("fizban", player.system)
        seen = "Fizban is in excellent condition."
        self.assertEqual(player.for_text(seen).user, seen)
        self.assertEqual(mobile.user, "{mobile}")
        self.assertEqual(mobile.json_schema["required"], player.json_schema["required"])
        self.assertIn("cityguard", mobile.system)
        self.assertEqual(mobile.for_text("the cityguard is in excellent condition.").user, "the cityguard is in excellent condition.")
        self.assertEqual(direction.user, "{direction}")
        self.assertEqual(direction.json_schema["required"], ["found", "door", "keyword", "description"])
        self.assertEqual(direction.json_schema["properties"]["door"]["enum"], ["none", "open", "closed"])
        self.assertIn("Nothing special there.", direction.system)
        self.assertEqual(direction.for_text("The gate is closed.").user, "The gate is closed.")

    def test_unparsed_categories_stay_in_the_review(self):
        lesson = CategoryLesson(prompt={"system": "Read the index.", "user": "MOVEMENT"}, response="not json")
        review = lesson.to_review()
        self.assertEqual(review["response"], "not json")
        self.assertIsNone(review["parsedCategories"])
        self.assertIn("parseError", review)

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
        client = _ScriptedClient(opening=["ERROR: That character is being saved. Please reconnect in a moment."], replies={})
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
