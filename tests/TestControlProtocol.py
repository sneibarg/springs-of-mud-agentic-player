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
        self.assertEqual(accepted_command("Bootstrap"), "bootstrap")
        self.assertEqual(accepted_command("connect Springs Of MUD"), "connect Springs Of MUD")
        self.assertEqual(accepted_command("LOGON Example"), "logon Example")
        self.assertEqual(accepted_command("memory"), "memory")
        self.assertEqual(accepted_command("memory my review.json"), "memory my review.json")
        self.assertEqual(accepted_command("output"), "output")
        self.assertEqual(accepted_command("output ON"), "output on")
        self.assertEqual(accepted_command("output file"), "output file")
        self.assertEqual(accepted_command("output FILE off"), "output file off")
        self.assertEqual(accepted_command("output file session log.txt"), "output file session log.txt")
        for line in ("", "   ", "dance", "idle now", "connect", "logon", "list extra", "bootstrap extra", "output sideways", "output on extra"):
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


if __name__ == "__main__":
    unittest.main()
