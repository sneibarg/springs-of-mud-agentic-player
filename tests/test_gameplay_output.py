import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from control.GameplayOutput import GameplayOutput, is_authentication_detail
from net.telnet.TelnetClient import TelnetClient, TelnetConfig


LOGON = 'logon {"accountId":"account-1","characterId":"char-1","characterName":"Example"}'


class TestGameplayOutput(unittest.TestCase):
    def test_console_is_on_until_disabled(self):
        shown = []
        output = GameplayOutput(console=shown.append)
        output.write("Temple Square")
        output.write("<20hp 100m 100mv>")
        output.disable()
        output.write("A goblin arrives.")
        output.enable()
        output.write("The goblin leaves.")

        self.assertEqual(shown, ["Temple Square", "<20hp 100m 100mv>", "The goblin leaves."])

    def test_session_file_receives_the_same_lines(self):
        shown = []
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "nested", "session.txt")
            output = GameplayOutput(console=shown.append, default_session_path=path)
            written = output.set_session_file(output.default_session_path)
            output.write("Temple Square")
            output.write(LOGON)
            output.write("Authorization: Bearer secret-token")
            output.disable()
            output.write("hidden while off")
            output.enable()
            output.write("The square is quiet.")
            output.close()
            text = Path(written).read_text(encoding="utf-8")

        self.assertEqual(shown, ["Temple Square", "The square is quiet."])
        self.assertEqual(text, "Temple Square\nThe square is quiet.\n")
        self.assertNotIn("account-1", text)
        self.assertNotIn("secret-token", text)
        self.assertNotIn("hidden while off", text)

    def test_authentication_lines_are_recognized(self):
        self.assertTrue(is_authentication_detail(LOGON))
        self.assertTrue(is_authentication_detail("  LOGON "))
        self.assertTrue(is_authentication_detail("Authorization: Bearer secret-token"))
        self.assertTrue(is_authentication_detail('{"password":"secret"}'))
        self.assertFalse(is_authentication_detail("Authentication failed."))
        self.assertFalse(is_authentication_detail("You remember your password."))

    def test_observer_does_not_consume_the_telnet_queue(self):
        shown = []
        output = GameplayOutput(console=shown.append)
        client = TelnetClient(TelnetConfig(host="localhost"), on_line=output.write)
        client._feed(b"Welcome\r\n")
        client._feed((LOGON + "\r\n").encode("utf-8"))
        client._feed(b"<20hp 100m 100mv>\r\n")

        self.assertEqual(shown, ["Welcome", "<20hp 100m 100mv>"])
        self.assertEqual(client.poll_line(), "Welcome")
        self.assertEqual(client.poll_line(), LOGON)
        self.assertEqual(client.poll_line(), "<20hp 100m 100mv>")


if __name__ == "__main__":
    unittest.main()
