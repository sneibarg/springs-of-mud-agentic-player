import json
import os
import socket
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent.AgentConfig import AgentConfig
from net.rest.OllamaClient import OllamaClient
from play.Bootstrapper import Bootstrapper
from prompt.PromptCollection import PromptCollection
from tests.live_session import QUIT_PHRASE, require_live_play


_OUTPUT = Path(__file__).resolve().parent / "output"
_ROOT = Path(__file__).resolve().parents[1]
_OLLAMA_FALLBACK_HOST = "dragon"


class TestLiveCommandBootstrap(unittest.TestCase):
    def setUp(self):
        _OUTPUT.mkdir(parents=True, exist_ok=True)
        self.review_path = _OUTPUT / f"{self._testMethodName}.json"

    def test_live_command_bootstrap(self):
        base_url = _ollama_url()
        if not base_url:
            self.skipTest("Ollama is not accepting connections.")
        play = require_live_play(self)
        if self.review_path.is_file():
            self.review_path.unlink()
        try:
            config = AgentConfig.load(_ROOT / "resources" / "agent.yml")
            prompts = PromptCollection.load(_ROOT / "resources" / "collections" / "SOMDB.Prompts.json")
            client = OllamaClient(base_url, path=config.ollama_path)
            bootstrapper = Bootstrapper(play.account.session, [], play.character.name, channel=play.channel)
            categories = bootstrapper.learn_categories(prompts.get("categories"), client)
            self._write(categories)
            lesson = bootstrapper.learn_commands(prompts.get("commands"), client)
            names = bootstrapper.commands_for_help(lesson.commands)
            categorized = {command.name: command.category for command in bootstrapper.memory.commands() if command.category.strip()}
            help_lessons = []

            def keep(item):
                help_lessons.append(item)
                self._write(categories, lesson, help_lessons)

            self._write(categories, lesson, help_lessons)
            learned = bootstrapper.learn_help(prompts.get("help"), client, names=names, on_lesson=keep)
            review = json.loads(self.review_path.read_text(encoding="utf-8"))

            category_review = review["categories"]
            self.assertTrue(category_review["prompt"]["system"].strip())
            self.assertTrue(category_review["prompt"]["user"].strip())
            self.assertEqual(category_review["response"], categories.response)
            self.assertFalse(categories.error, categories.error)
            grouped, group_error = categories.parsed_categories()
            self.assertIsNotNone(grouped, group_error)
            self.assertTrue(grouped, group_error)
            self.assertNotIn("parseError", category_review)
            for group in grouped:
                for name in group["commands"]:
                    remembered = bootstrapper.memory.command_named(name)
                    self.assertIsNotNone(remembered, name)
                    self.assertEqual(remembered.category, group["name"], name)

            command_review = review["commands"]
            self.assertTrue(command_review["prompt"]["system"].strip())
            self.assertTrue(command_review["prompt"]["user"].strip())
            self.assertEqual(command_review["response"], lesson.response)
            self.assertTrue(lesson.commands)
            self.assertFalse(lesson.error, lesson.error)
            self.assertTrue(lesson.response.strip())
            parsed, parse_error = lesson.parsed_commands()
            self.assertIsNotNone(parsed, parse_error)
            self.assertTrue(parsed, parse_error)
            self.assertNotIn("parseError", command_review)

            self.assertEqual(len(learned), len(names))
            self.assertEqual(len(review["help"]), len(names))
            uncategorized = []
            failures = []
            for name in names:
                remembered = bootstrapper.memory.command_named(name)
                if remembered is None or not remembered.category.strip():
                    uncategorized.append(name)
            for item, entry in zip(learned, review["help"]):
                self.assertEqual(entry["command"], item.command)
                self.assertTrue(entry["prompt"]["system"].strip(), item.command)
                self.assertTrue(entry["prompt"]["user"].strip(), item.command)
                self.assertEqual(entry["response"], item.response)
                remembered = bootstrapper.memory.command_named(item.command)
                self.assertIsNotNone(remembered, item.command)
                if item.command in categorized:
                    self.assertFalse(item.category_requested, item.command)
                    self.assertEqual(remembered.category, categorized[item.command], item.command)
                    self.assertNotIn("category", entry["prompt"]["jsonSchema"].get("required", []), item.command)
                else:
                    self.assertTrue(item.category_requested, item.command)
                    self.assertIn("category", entry["prompt"]["jsonSchema"]["required"], item.command)
                    self.assertIn(item.command, entry["prompt"]["system"])
                    if entry.get("categoryError"):
                        failures.append(f"{item.command}: {entry['categoryError']}")
                if item.error or entry.get("parseError"):
                    failures.append(f"{item.command}: {item.error or entry.get('parseError')}")
                    continue
                stored = bootstrapper.knowledge.help_for(item.command)
                self.assertIsNotNone(stored, item.command)
                self.assertIsNotNone(remembered, item.command)
                self.assertEqual(stored.missing, entry["parsed"]["missing"])
                if stored.missing:
                    self.assertEqual(remembered.help_text, "")
                else:
                    self.assertTrue(remembered.help_text.strip(), item.command)
                    self.assertTrue(stored.topics, item.command)
            self.assertFalse(uncategorized, "uncategorized: " + ", ".join(uncategorized))
            self.assertFalse(failures, "\n".join(failures))

            farewell = play.quit()
            self.assertTrue(any(QUIT_PHRASE in line for line in farewell))
        finally:
            play.close()

    def test_live_help_categories(self):
        base_url = _ollama_url()
        if not base_url:
            self.skipTest("Ollama is not accepting connections.")
        play = require_live_play(self)
        if self.review_path.is_file():
            self.review_path.unlink()
        try:
            config = AgentConfig.load(_ROOT / "resources" / "agent.yml")
            prompt = PromptCollection.load(_ROOT / "resources" / "collections" / "SOMDB.Prompts.json").get("categories")
            bootstrapper = Bootstrapper(play.account.session, [], play.character.name, channel=play.channel)
            lesson = bootstrapper.learn_categories(prompt, OllamaClient(base_url, path=config.ollama_path))
            self.review_path.write_text(json.dumps(lesson.to_review(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            review = json.loads(self.review_path.read_text(encoding="utf-8"))

            self.assertTrue(review["prompt"]["system"].strip())
            self.assertIn("MOVEMENT", review["prompt"]["user"])
            self.assertEqual(review["response"], lesson.response)
            self.assertFalse(lesson.error, lesson.error)
            self.assertTrue(lesson.response.strip())
            grouped, group_error = lesson.parsed_categories()
            self.assertIsNotNone(grouped, group_error)
            self.assertTrue(grouped, group_error)
            self.assertNotIn("parseError", review)
            for group in grouped:
                self.assertTrue(group["commands"], group["name"])
                for name in group["commands"]:
                    remembered = bootstrapper.memory.command_named(name)
                    self.assertIsNotNone(remembered, name)
                    self.assertEqual(remembered.category, group["name"], name)

            farewell = play.quit()
            self.assertTrue(any(QUIT_PHRASE in line for line in farewell))
        finally:
            play.close()

    def _write(self, categories, commands=None, help_lessons=None) -> Path:
        document = {"categories": categories.to_review(), "help": [item.to_review() for item in (help_lessons or [])]}
        if commands is not None:
            document["commands"] = commands.to_review()
        self.review_path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertTrue(self.review_path.is_file())
        self.assertGreater(self.review_path.stat().st_size, 0)
        return self.review_path


def _ollama_url() -> str:
    config = AgentConfig.load(_ROOT / "resources" / "agent.yml")
    host, port = _endpoint(config.ollama_base_url, 9081)
    if _tcp_open(host, port):
        return config.ollama_base_url
    if host in {"localhost", "127.0.0.1"} and _tcp_open(_OLLAMA_FALLBACK_HOST, port):
        return f"http://{_OLLAMA_FALLBACK_HOST}:{port}"
    return ""


def _endpoint(url: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return parsed.hostname or "", parsed.port or default_port


def _tcp_open(host: str, port: int, timeout_s: float = 0.8) -> bool:
    if not host or port < 1:
        return False
    probe = socket.socket()
    probe.settimeout(timeout_s)
    try:
        probe.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


if __name__ == "__main__":
    unittest.main()
