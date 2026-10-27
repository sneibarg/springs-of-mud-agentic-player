import json
import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.rest.AuthResponse import AuthResponse
from net.telnet.PlayerSession import PlayerSession, build_logon_line
from net.telnet.TelnetClient import TelnetClient, TelnetConfig


class _FakeSocket:
    def __init__(self):
        self.sent = b""

    def sendall(self, data):
        self.sent += data


class TestPlayerSession(unittest.TestCase):
    def setUp(self):
        self.auth = AuthResponse.from_json(
            {
                "id": "account-1",
                "accountName": "ada",
                "playerCharacterList": [{"id": "char-1", "name": "Example"}],
            }
        )

    def test_logon_line_matches_server_auth_payload(self):
        line = build_logon_line(self.auth, "example")
        verb, payload_json = line.split(" ", 1)
        payload = json.loads(payload_json)

        self.assertEqual(verb, "logon")
        self.assertEqual(
            payload,
            {"accountId": "account-1", "characterId": "char-1", "characterName": "Example"},
        )

    def test_session_sends_logon_with_crlf(self):
        client = TelnetClient(TelnetConfig(host="localhost", port=6969))
        client._sock = _FakeSocket()
        session = PlayerSession(TelnetConfig(host="localhost", port=6969), client=client)

        line = session.logon(self.auth, "Example")

        self.assertTrue(line.startswith("logon "))
        self.assertEqual(client._sock.sent, (line + "\r\n").encode("utf-8"))

    def test_unknown_character_raises(self):
        with self.assertRaises(LookupError):
            build_logon_line(self.auth, "Missing")


if __name__ == "__main__":
    unittest.main()
