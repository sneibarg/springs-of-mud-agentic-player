import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from play.CommandChannel import CommandChannel
from play.PlayError import PromptTimeout, SessionDeclined


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


class TestCommandChannel(unittest.TestCase):
    def _channel(self, client: _QueueClient, replace_existing: str = "Y") -> CommandChannel:
        clock = _Clock()
        return CommandChannel(
            client,
            timeout_s=0.3,
            poll_interval_s=0.1,
            replace_existing=replace_existing,
            clock=clock,
            sleep=clock.sleep,
        )

    def test_pager_is_acknowledged_and_omitted_from_the_page(self):
        client = _QueueClient()
        client.on_send["help look"] = ["LOOK", "First page.", "[Hit Enter to continue]"]
        client.on_send[""] = ["Second page.", "<10hp 10m 10mv>"]
        channel = self._channel(client)

        lines = channel.exchange("help look")

        self.assertEqual(client.sent, ["help look", ""])
        self.assertEqual(lines, ["LOOK", "First page.", "Second page."])
        self.assertTrue(channel.saw_prompt)

    def test_existing_session_is_replaced_with_y(self):
        client = _QueueClient()
        client.pending = [
            "That character is already playing.",
            "Do you wish to connect anyway (Y/N)?",
        ]
        client.on_send["Y"] = ["Welcome to the server!", "<10hp 10m 10mv>"]
        channel = self._channel(client)

        lines = channel.read_until_prompt()

        self.assertEqual(client.sent, ["Y"])
        self.assertEqual(lines, ["That character is already playing.", "Welcome to the server!"])
        self.assertTrue(channel.saw_prompt)

    def test_declining_replacement_stops_the_session(self):
        client = _QueueClient()
        client.pending = ["Do you wish to connect anyway (Y/N)?"]
        channel = self._channel(client, replace_existing="N")

        with self.assertRaises(SessionDeclined):
            channel.read_until_prompt()
        self.assertEqual(client.sent, ["N"])

    def test_exchange_without_a_prompt_raises(self):
        client = _QueueClient()
        client.on_send["look"] = ["partial"]
        channel = self._channel(client)

        with self.assertRaises(PromptTimeout):
            channel.exchange("look")
        self.assertFalse(channel.saw_prompt)


if __name__ == "__main__":
    unittest.main()
