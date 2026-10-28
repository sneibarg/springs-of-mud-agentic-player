import ast
import os
import socket
import sys
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cli.ControlClient import ControlClient
from cli.ControlProtocol import UNKNOWN_COMMAND, accepted_command, read_reply
from cli.__main__ import main
from control.PlayerControl import PlayerControl
from net.local.ControlServer import ControlServer


ROOT = Path(__file__).resolve().parents[1]


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


class TestControlProtocol(unittest.TestCase):
    def test_transport_modules_import_only_the_socket_stack(self):
        src = ROOT / "src"
        self.assertEqual(_imported_roots(src / "cli" / "ControlProtocol.py"), {"typing"})
        self.assertEqual(_imported_roots(src / "cli" / "ControlClient.py"), {"socket", "cli"})
        self.assertEqual(_imported_roots(src / "cli" / "__main__.py"), {"argparse", "sys", "cli"})
        self.assertEqual(_imported_roots(src / "net" / "local" / "ControlServer.py"), {"socket", "threading", "cli"})

    def test_only_known_command_shapes_are_accepted(self):
        self.assertEqual(accepted_command("  PLAY  "), "play")
        self.assertEqual(accepted_command("Idle"), "idle")
        self.assertEqual(accepted_command("list"), "list")
        self.assertEqual(accepted_command("connect Springs Of MUD"), "connect Springs Of MUD")
        self.assertEqual(accepted_command("LOGON Example"), "logon Example")
        self.assertEqual(accepted_command("memory"), "memory")
        self.assertEqual(accepted_command("memory my review.json"), "memory my review.json")
        self.assertEqual(accepted_command("output"), "output")
        self.assertEqual(accepted_command("output ON"), "output on")
        self.assertEqual(accepted_command("output file"), "output file")
        self.assertEqual(accepted_command("output FILE off"), "output file off")
        self.assertEqual(accepted_command("output file session log.txt"), "output file session log.txt")
        for line in ("", "   ", "dance", "idle now", "connect", "logon", "list extra", "output sideways", "output on extra"):
            self.assertIsNone(accepted_command(line), line)

    def test_handle_rejects_unknown_shapes_before_dispatch(self):
        called = []

        class _Account:
            def connect(self, name):
                called.append(name)
                return "Connected."

        control = PlayerControl(account=_Account(), writer=lambda _text: None)
        self.assertEqual(control.handle("dance"), UNKNOWN_COMMAND)
        self.assertEqual(control.handle("connect"), UNKNOWN_COMMAND)
        self.assertEqual(control.handle("idle now"), UNKNOWN_COMMAND)
        self.assertEqual(called, [])
        self.assertEqual(control.mode, PlayerControl.IDLE)
        self.assertEqual(control.handle("idle"), PlayerControl.IDLE_REPLY)

    def test_client_refuses_an_unknown_command_before_connecting(self):
        with mock.patch("cli.ControlClient.socket.socket", side_effect=AssertionError("socket opened")):
            error = StringIO()
            with redirect_stderr(error):
                code = main(["dance"])
            self.assertEqual(code, 2)
            self.assertEqual(error.getvalue().strip(), UNKNOWN_COMMAND)

            error = StringIO()
            with redirect_stderr(error):
                code = main(["--host", "10.0.0.1", "idle"])
            self.assertEqual(code, 2)
            self.assertEqual(error.getvalue().strip(), "Control host must be localhost")

    def test_client_reports_a_missing_listener(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        error = StringIO()
        with redirect_stderr(error):
            code = main(["--port", str(port), "idle"])
        self.assertEqual(code, 1)
        self.assertEqual(error.getvalue().strip(), f"Control is not listening on 127.0.0.1:{port}.")

    def test_usage_does_not_connect(self):
        with mock.patch("cli.ControlClient.socket.socket", side_effect=AssertionError("socket opened")):
            error = StringIO()
            with redirect_stderr(error):
                code = main([])
            self.assertEqual(code, 2)
            self.assertIn("Usage:", error.getvalue())


class TestControlServer(unittest.TestCase):
    def test_localhost_round_trip_rejects_unknown_commands(self):
        calls = []
        control = PlayerControl(writer=lambda _text: None)

        class _Gate:
            def handle(self, command):
                calls.append(command)
                return control.handle(command)

        server = ControlServer(_Gate(), port=0)
        server.start()
        try:
            self.assertEqual(server.host, "127.0.0.1")
            self.assertGreater(server.bound_port, 0)
            self.assertEqual(server._thread.name, "PlayerControl")
            raw = socket.create_connection(("127.0.0.1", server.bound_port), timeout=2)
            try:
                raw.sendall(b"dance\n")
                reply = read_reply(raw)
            finally:
                raw.close()
            self.assertEqual(reply, UNKNOWN_COMMAND)
            self.assertNotIn("dance", reply)
            self.assertEqual(calls, [])
            self.assertEqual(control.mode, PlayerControl.IDLE)

            client = ControlClient(port=server.bound_port, timeout_s=2)
            self.assertEqual(client.invoke("PLAY"), "Play.")
            self.assertEqual(calls, ["play"])
            self.assertEqual(control.mode, PlayerControl.PLAY)

            output = StringIO()
            with redirect_stdout(output):
                code = main(["--port", str(server.bound_port), "idle"])
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue().strip(), "Idle.")
            self.assertEqual(control.mode, PlayerControl.IDLE)
            self.assertNotIn(PlayerControl.GREETING, output.getvalue())
        finally:
            server.stop()
            control.stop()

    def test_multiline_reply_round_trip(self):
        class _Account:
            logged_on = False

            def list_characters(self):
                return "Available characters:\n- Example\n- Guide"

        control = PlayerControl(account=_Account(), writer=lambda _text: None)
        server = ControlServer(control, port=0)
        server.start()
        try:
            reply = ControlClient("localhost", server.bound_port, timeout_s=2).invoke("list")
            self.assertEqual(reply, "Available characters:\n- Example\n- Guide")
        finally:
            server.stop()
            control.stop()

    def test_play_from_the_socket_runs_drive_once(self):
        control = PlayerControl(writer=lambda _text: None)
        server = ControlServer(control, port=0)
        calls = []
        started = threading.Event()

        def on_play() -> None:
            calls.append(threading.current_thread().name)
            started.set()

        server.start()
        driver = threading.Thread(target=lambda: control.drive(on_play, wait_s=0.05), name="session")
        driver.start()
        try:
            client = ControlClient(port=server.bound_port, timeout_s=2)
            self.assertEqual(client.invoke("play"), "Play.")
            self.assertTrue(started.wait(2))
            self.assertEqual(calls, ["session"])
            self.assertEqual(client.invoke("idle"), "Idle.")
            self.assertEqual(client.invoke("play"), "Play.")
            time.sleep(0.1)
            self.assertEqual(calls, ["session"])
        finally:
            control.stop()
            driver.join(2)
            server.stop()
            self.assertFalse(driver.is_alive())

    def test_play_before_logon_stays_idle(self):
        class _Account:
            logged_on = False

        control = PlayerControl(account=_Account(), writer=lambda _text: None)
        server = ControlServer(control, port=0)
        server.start()
        try:
            reply = ControlClient(port=server.bound_port, timeout_s=2).invoke("play")
            self.assertEqual(reply, "Log on with an available character before play.")
            self.assertEqual(control.mode, PlayerControl.IDLE)
        finally:
            server.stop()
            control.stop()

    def test_remote_peer_receives_nothing(self):
        control = PlayerControl(writer=lambda _text: None)
        server = ControlServer(control, port=0)
        left, right = socket.socketpair()
        try:
            left.settimeout(0.3)
            server._exchange(right, ("10.0.0.8", 40000))
            with self.assertRaises(TimeoutError):
                left.recv(16)
            self.assertEqual(control.mode, PlayerControl.IDLE)
        finally:
            left.close()
            right.close()
            control.stop()


if __name__ == "__main__":
    unittest.main()
