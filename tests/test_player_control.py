import json
import os
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from control.GameplayOutput import GameplayOutput
from control.PlayerControl import PlayerControl
from memory.WorkingMemory import WorkingMemory


def _next_line(lines: queue.Queue):
    line = lines.get()
    if line is None:
        raise EOFError
    return line


def _wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestPlayerControl(unittest.TestCase):
    def test_start_is_idle_and_names_the_commands(self):
        lines = queue.Queue()
        replies = []
        control = PlayerControl(reader=lambda: _next_line(lines), writer=replies.append)

        control.start()
        try:
            self.assertEqual(replies, [PlayerControl.GREETING])
            self.assertEqual(control.mode, PlayerControl.IDLE)
            self.assertIsNotNone(control.thread)
            self.assertTrue(control.thread.daemon)
            self.assertEqual(control.thread.name, "PlayerControl")
            self.assertTrue(control.thread.is_alive())
        finally:
            self._finish(control, lines)

    def test_idle_and_play_change_the_mode(self):
        lines = queue.Queue()
        replies = []
        control = PlayerControl(reader=lambda: _next_line(lines), writer=replies.append)
        control.start()
        try:
            lines.put("  PLAY  ")
            self.assertTrue(_wait_for(lambda: control.mode == PlayerControl.PLAY))
            lines.put("Idle")
            self.assertTrue(_wait_for(lambda: control.mode == PlayerControl.IDLE))
            lines.put("   ")
            lines.put("dance")
            self.assertTrue(_wait_for(lambda: replies.count(PlayerControl.UNKNOWN_REPLY) == 2))
            self.assertEqual(
                replies,
                [
                    PlayerControl.GREETING,
                    PlayerControl.PLAY_REPLY,
                    PlayerControl.IDLE_REPLY,
                    PlayerControl.UNKNOWN_REPLY,
                    PlayerControl.UNKNOWN_REPLY,
                ],
            )
            self.assertEqual(control.mode, PlayerControl.IDLE)
        finally:
            self._finish(control, lines)

    def test_play_runs_once_on_the_caller_thread(self):
        lines = queue.Queue()
        replies = []
        control = PlayerControl(reader=lambda: _next_line(lines), writer=replies.append)
        calls = []
        started = threading.Event()
        release = threading.Event()

        def on_play() -> None:
            calls.append(threading.current_thread().name)
            started.set()
            self.assertTrue(release.wait(2))

        control.start()
        driver = threading.Thread(
            target=lambda: control.drive(on_play, wait_s=0.05),
            name="session",
        )
        driver.start()
        try:
            lines.put("play")
            self.assertTrue(started.wait(2))
            lines.put("idle")
            self.assertTrue(_wait_for(lambda: PlayerControl.IDLE_REPLY in replies))
            self.assertEqual(calls, ["session"])
            self.assertNotEqual(calls[0], control.thread.name)
            self.assertEqual(control.mode, PlayerControl.IDLE)
            release.set()
            lines.put("play")
            self.assertTrue(_wait_for(lambda: control.mode == PlayerControl.PLAY))
            time.sleep(0.1)
            self.assertEqual(calls, ["session"])
        finally:
            release.set()
            self._finish(control, lines, driver)

    def test_memory_writes_a_review_and_keeps_the_mode(self):
        lines = queue.Queue()
        replies = []
        memory = WorkingMemory()
        memory.remember_mobile("a goblin", aggressive=True)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "review.json")
            control = PlayerControl(
                reader=lambda: _next_line(lines),
                writer=replies.append,
                memory=memory,
                memory_path=path,
            )
            control.start()
            try:
                lines.put("memory")
                self.assertTrue(_wait_for(lambda: f"Memory written to {path}." in replies))
                self.assertEqual(control.mode, PlayerControl.IDLE)
                document = json.loads(Path(path).read_text(encoding="utf-8"))
                self.assertEqual(document["mobiles"][0]["name"], "a goblin")
                self.assertTrue(document["mobiles"][0]["aggressive"])
                lines.put("play")
                self.assertTrue(_wait_for(lambda: control.mode == PlayerControl.PLAY))
                lines.put(f"memory {directory}")
                self.assertTrue(_wait_for(lambda: "Memory was not written: " in "".join(replies)))
                self.assertEqual(control.mode, PlayerControl.PLAY)
            finally:
                self._finish(control, lines)

    def test_output_toggles_console_and_session_file(self):
        lines = queue.Queue()
        replies = []
        shown = []
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "session.txt")
            output = GameplayOutput(console=shown.append, default_session_path=path)
            control = PlayerControl(
                reader=lambda: _next_line(lines),
                writer=replies.append,
                output=output,
            )
            control.start()
            try:
                self.assertEqual(control.mode, PlayerControl.IDLE)
                output.write("Temple Square")
                lines.put("output off")
                self.assertTrue(_wait_for(lambda: "Output off." in replies))
                output.write("hidden")
                lines.put("output file")
                self.assertTrue(_wait_for(lambda: f"Session file {path}." in "".join(replies)))
                self.assertFalse(Path(path).exists() and "hidden" in Path(path).read_text(encoding="utf-8"))
                lines.put("play")
                self.assertTrue(_wait_for(lambda: control.mode == PlayerControl.PLAY))
                lines.put("output on")
                self.assertTrue(_wait_for(lambda: any(reply.startswith("Output on.") for reply in replies)))
                output.write("The square")
                lines.put(f"output file {directory}")
                self.assertTrue(_wait_for(lambda: "Session file was not written: " in "".join(replies)))
                lines.put("output file off")
                self.assertTrue(_wait_for(lambda: any(reply == "Output on." for reply in replies)))
                self.assertEqual(control.mode, PlayerControl.PLAY)
                self.assertEqual(shown, ["Temple Square", "The square"])
                self.assertEqual(Path(path).read_text(encoding="utf-8"), "The square\n")
                self.assertEqual(output.session_path, "")
            finally:
                output.close()
                self._finish(control, lines)

    def test_logon_uses_only_characters_from_connect(self):
        lines = queue.Queue()
        replies = []

        class _Account:
            def __init__(self):
                self.logged_on = False
                self.connected = False

            def connect(self, name):
                self.connected = True
                return "Connected as sneibarg. Characters: Example."

            def list_characters(self):
                if not self.connected:
                    return "Connect an account before listing characters."
                return "Available characters:\n- Example"

            def logon(self, name):
                if not self.connected:
                    return "Connect an account before logon."
                if name.strip().lower() != "example":
                    return "Character 'Nobody' is not available. Available characters: Example."
                self.logged_on = True
                return "Logged on as Example."

        account = _Account()
        control = PlayerControl(
            reader=lambda: _next_line(lines),
            writer=replies.append,
            account=account,
        )
        control.start()
        try:
            lines.put("play")
            self.assertTrue(_wait_for(lambda: "Log on with an available character before play." in replies))
            self.assertEqual(control.mode, PlayerControl.IDLE)
            lines.put("list")
            self.assertTrue(_wait_for(lambda: "Connect an account before listing characters." in replies))
            lines.put("connect SpringsOfMUD")
            self.assertTrue(_wait_for(lambda: "Connected as sneibarg. Characters: Example." in replies))
            lines.put("logon Nobody")
            self.assertTrue(_wait_for(lambda: "not available" in "".join(replies)))
            self.assertFalse(account.logged_on)
            lines.put("logon Example")
            self.assertTrue(_wait_for(lambda: "Logged on as Example." in replies))
            self.assertTrue(account.logged_on)
            lines.put("play")
            self.assertTrue(_wait_for(lambda: control.mode == PlayerControl.PLAY))
        finally:
            self._finish(control, lines)

    def test_end_of_input_stops_the_listener(self):
        lines = queue.Queue()
        control = PlayerControl(reader=lambda: _next_line(lines), writer=lambda _text: None)
        control.start()
        driver = threading.Thread(target=lambda: control.drive(lambda: None))
        driver.start()
        lines.put(None)
        driver.join(2)
        control.join(2)
        self.assertFalse(driver.is_alive())
        self.assertFalse(control.thread.is_alive())
        self.assertTrue(control.stopped)

    def test_stop_releases_drive(self):
        lines = queue.Queue()
        control = PlayerControl(reader=lambda: _next_line(lines), writer=lambda _text: None)
        control.start()
        driver = threading.Thread(target=lambda: control.drive(lambda: None, wait_s=5))
        driver.start()
        try:
            control.stop()
            driver.join(2)
            self.assertFalse(driver.is_alive())
        finally:
            lines.put(None)
            control.join(2)

    def _finish(self, control: PlayerControl, lines: queue.Queue, driver: threading.Thread | None = None) -> None:
        control.stop()
        lines.put(None)
        if driver is not None:
            driver.join(2)
            self.assertFalse(driver.is_alive())
        control.join(2)
        self.assertFalse(control.thread.is_alive())


if __name__ == "__main__":
    unittest.main()
