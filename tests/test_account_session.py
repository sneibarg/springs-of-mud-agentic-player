import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.AccountSession import AccountSession
from net.rest.AuthClient import AuthClient
from net.rest.ConnectionCatalog import ConnectionCatalog, SavedConnection, obfuscate_password
from net.telnet.PlayerSession import PlayerSession
from net.telnet.TelnetClient import TelnetConfig


class _Response:
    def __init__(self, payload, headers):
        self._payload = payload
        self.headers = headers

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _Client:
    def __init__(self):
        self.sent = []
        self.connected = False

    def connect(self):
        self.connected = True

    def send_line(self, text):
        self.sent.append(text)

    def close(self):
        self.connected = False


def _catalog():
    return ConnectionCatalog([
        SavedConnection(
            name="SpringsOfMUD",
            server_url="http://localhost:8169",
            account_name="sneibarg",
            telnet_host="malboji",
            telnet_port=6969,
            obfuscated_password=obfuscate_password("secret"),
        )
    ])


class TestAccountSession(unittest.TestCase):
    def test_logon_accepts_only_a_returned_character(self):
        captured = {}
        clients = []

        def post(url, json, timeout):
            captured["json"] = json
            return _Response(
                {
                    "id": "account-1",
                    "accountName": "sneibarg",
                    "playerCharacterList": [
                        {"id": "char-1", "name": "Example"},
                        {"id": "char-2", "name": "Other"},
                    ],
                },
                {"Authorization": "jwt-token"},
            )

        def auth_client(base_url):
            return AuthClient(base_url, post=post)

        def session_factory(host, port):
            client = _Client()
            clients.append((host, port, client))
            return PlayerSession(TelnetConfig(host=host, port=port), client=client)

        account = AccountSession(
            _catalog(),
            auth_client_factory=auth_client,
            session_factory=session_factory,
        )

        self.assertEqual(account.list_characters(), "Connect an account before listing characters.")
        connected = account.connect("SpringsOfMUD")
        self.assertEqual(connected, "Connected as sneibarg. Characters: Example, Other.")
        self.assertEqual(captured["json"]["accountName"], "sneibarg")
        self.assertEqual(captured["json"]["password"], "secret")
        self.assertNotIn("secret", connected)
        self.assertEqual(
            account.list_characters(),
            "Available characters:\n- Example\n- Other",
        )
        refused = account.logon("Nobody")
        self.assertIn("not available", refused)
        self.assertFalse(account.logged_on)
        self.assertEqual(clients, [])

        logged = account.logon("example")
        self.assertEqual(logged, "Logged on as Example.")
        self.assertTrue(account.logged_on)
        host, port, client = clients[0]
        self.assertEqual((host, port), ("malboji", 6969))
        self.assertTrue(client.connected)
        self.assertTrue(client.sent[0].startswith("logon "))
        self.assertIn("Example", client.sent[0])
        self.assertNotIn("secret", client.sent[0])
        self.assertNotIn("secret", logged)

    def test_missing_telnet_fields_use_the_configured_defaults(self):
        opened = {}

        def post(url, json, timeout):
            return _Response(
                {
                    "id": "account-2",
                    "accountName": "neibarge",
                    "playerCharacterList": [{"id": "char-9", "name": "Alt"}],
                },
                {"Authorization": "jwt-token"},
            )

        def session_factory(host, port):
            opened["endpoint"] = (host, port)
            return PlayerSession(TelnetConfig(host=host, port=port), client=_Client())

        catalog = ConnectionCatalog([
            SavedConnection(
                name="SpringsOfMUD-alt",
                server_url="",
                account_name="neibarge",
                telnet_host=None,
                telnet_port=None,
                obfuscated_password=obfuscate_password("secret"),
            )
        ])
        account = AccountSession(
            catalog,
            auth_base_url="http://localhost:8169",
            telnet_host="localhost",
            telnet_port=6969,
            auth_client_factory=lambda base_url: AuthClient(base_url, post=post),
            session_factory=session_factory,
        )
        account.connect("SpringsOfMUD-alt")
        self.assertEqual(account.logon("Alt"), "Logged on as Alt.")
        self.assertEqual(opened["endpoint"], ("localhost", 6969))

    def test_connect_accepts_a_login_without_an_authorization_header(self):
        def post(url, json, timeout):
            return _Response(
                {
                    "id": "account-1",
                    "accountName": "sneibarg",
                    "playerCharacterList": [{"id": "char-2", "name": "Janky", "level": 8}],
                },
                {},
            )

        account = AccountSession(
            _catalog(),
            auth_client_factory=lambda base_url: AuthClient(base_url, post=post),
            session_factory=lambda host, port: PlayerSession(TelnetConfig(host=host, port=port), client=_Client()),
        )
        connected = account.connect("SpringsOfMUD")
        self.assertEqual(connected, "Connected as sneibarg. Characters: Janky.")
        self.assertIsNone(account.auth_client.jwt_token)
        self.assertEqual(account.logon("Janky"), "Logged on as Janky.")


if __name__ == "__main__":
    unittest.main()
