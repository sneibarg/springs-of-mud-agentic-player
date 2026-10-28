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
        if self.review_path.is_file():
            self.review_path.unlink()

    def test_live_command_bootstrap(self):
        base_url = _ollama_url()
        if not base_url:
            self.skipTest("Ollama is not accepting connections.")
        play = require_live_play(self)
        try:
            config = AgentConfig.load(_ROOT / "resources" / "agent.yml")
            prompts = PromptCollection.load(_ROOT / "resources" / "collections" / "SOMDB.Prompts.json")
            client = OllamaClient(base_url, path=config.ollama_path)
            bootstrapper = Bootstrapper(play.account.session, [], play.character.name, channel=play.channel)
            lesson = bootstrapper.learn_commands(prompts.get("commands"), client)
            help_lessons = []

            def keep(item):
                help_lessons.append(item)
                self._write(lesson, help_lessons)

            self._write(lesson, help_lessons)
            learned = bootstrapper.learn_help(prompts.get("help"), client, on_lesson=keep)
            review = json.loads(self.review_path.read_text(encoding="utf-8"))

            self.assertTrue(review["prompt"]["system"].strip())
            self.assertTrue(review["prompt"]["user"].strip())
            self.assertEqual(review["response"], lesson.response)
            self.assertTrue(lesson.commands)
            self.assertFalse(lesson.error, lesson.error)
            self.assertTrue(lesson.response.strip())
            parsed, parse_error = lesson.parsed_commands()
            self.assertIsNotNone(parsed, parse_error)
            self.assertTrue(parsed, parse_error)
            self.assertNotIn("parseError", review)

            self.assertEqual(len(learned), len(lesson.commands))
            self.assertEqual(len(review["help"]), len(lesson.commands))
            failures = []
            for item, entry in zip(learned, review["help"]):
                self.assertEqual(entry["command"], item.command)
                self.assertTrue(entry["prompt"]["system"].strip(), item.command)
                self.assertTrue(entry["prompt"]["user"].strip(), item.command)
                self.assertEqual(entry["response"], item.response)
                if item.error or entry.get("parseError"):
                    failures.append(f"{item.command}: {item.error or entry.get('parseError')}")
                    continue
                stored = bootstrapper.knowledge.help_for(item.command)
                remembered = bootstrapper.memory.command_named(item.command)
                self.assertIsNotNone(stored, item.command)
                self.assertIsNotNone(remembered, item.command)
                self.assertEqual(stored.missing, entry["parsed"]["missing"])
                if stored.missing:
                    self.assertEqual(remembered.help_text, "")
                else:
                    self.assertTrue(remembered.help_text.strip(), item.command)
                    self.assertTrue(stored.topics, item.command)
            self.assertFalse(failures, "\n".join(failures))

            farewell = play.quit()
            self.assertTrue(any(QUIT_PHRASE in line for line in farewell))
        finally:
            play.close()

    def _write(self, lesson, help_lessons) -> Path:
        document = lesson.to_review()
        document["help"] = [item.to_review() for item in help_lessons]
        self.review_path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
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
