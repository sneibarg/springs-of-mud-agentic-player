import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent.Agent import Agent
from main import _run_initial_bootstrap
from net.AccountSession import AccountSession
from net.rest.AuthClient import AuthClient
from net.rest.ConnectionCatalog import ConnectionCatalog
from net.rest.SavedConnection import SavedConnection, obfuscate_password
from net.telnet.PlayerSession import PlayerSession
from net.telnet.TelnetClient import TelnetConfig


class _Response:
    def __init__(self, payload, headers):
        self.headers = headers
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _Client:
    def __init__(self):
        self.connected = False
        self.sent = []

    def connect(self):
        self.connected = True

    def send_line(self, text):
        self.sent.append(text)

    def close(self):
        self.connected = False


def _agent():
    return Agent(id="1", name="AgentJanky", account_name="sneibarg", character_name="Janky")


def _catalog():
    return ConnectionCatalog([SavedConnection(name="SpringsOfMUD", server_url="http://localhost:8169", account_name="sneibarg", telnet_host="malboji", telnet_port=6969, obfuscated_password=obfuscate_password("secret")), SavedConnection(name="Other", server_url="http://localhost:8169", account_name="neibarge", telnet_host=None, telnet_port=None, obfuscated_password=obfuscate_password("secret"))])


def _account(post):
    def session_factory(host, port):
        return PlayerSession(TelnetConfig(host=host, port=port), client=_Client())

    return AccountSession(_catalog(), auth_base_url="http://dragon:8169", login_path="/api/auth/login", telnet_host="malboji", telnet_port=6969, auth_client_factory=lambda base_url: AuthClient(base_url, "/api/auth/login", post=post), session_factory=session_factory)


class TestInitialBootstrap(unittest.TestCase):
    def test_logged_on_agent_runs_bootstrap(self):
        calls = []

        def post(url, json, timeout):
            return _Response({"id": "account-1", "accountName": "sneibarg", "playerCharacterList": [{"id": "char-2", "name": "Janky"}]}, {"Authorization": "jwt-token"})

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            started = _run_initial_bootstrap(_account(post), _catalog(), _agent(), lambda: calls.append("bootstrap") or True)
        text = stdout.getvalue()
        self.assertTrue(started)
        self.assertEqual(calls, ["bootstrap"])
        self.assertIn("Connected as sneibarg.", text)
        self.assertIn("Logged on as Janky.", text)
        self.assertNotIn("secret", text)

    def test_missing_connection_does_not_bootstrap(self):
        agent = Agent(id="1", name="AgentJanky", account_name="missing", character_name="Janky")
        calls = []
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            started = _run_initial_bootstrap(_account(lambda url, json, timeout: None), _catalog(), agent, lambda: calls.append("bootstrap") or True)
        self.assertFalse(started)
        self.assertEqual(calls, [])
        self.assertIn("No saved connection for account 'missing'.", stderr.getvalue())

    def test_unavailable_character_does_not_bootstrap(self):
        def post(url, json, timeout):
            return _Response({"id": "account-1", "accountName": "sneibarg", "playerCharacterList": [{"id": "char-1", "name": "Example"}]}, {})

        calls = []
        with redirect_stdout(io.StringIO()):
            started = _run_initial_bootstrap(_account(post), _catalog(), _agent(), lambda: calls.append("bootstrap") or True)
        self.assertFalse(started)
        self.assertEqual(calls, [])

    def test_failed_connect_does_not_bootstrap(self):
        def post(url, json, timeout):
            raise RuntimeError("down")

        calls = []
        with redirect_stdout(io.StringIO()):
            started = _run_initial_bootstrap(_account(post), _catalog(), _agent(), lambda: calls.append("bootstrap") or True)
        self.assertFalse(started)
        self.assertEqual(calls, [])

    def test_bootstrap_result_is_returned(self):
        def post(url, json, timeout):
            return _Response({"id": "account-1", "accountName": "sneibarg", "playerCharacterList": [{"id": "char-2", "name": "Janky"}]}, {})

        with redirect_stdout(io.StringIO()):
            started = _run_initial_bootstrap(_account(post), _catalog(), _agent(), lambda: False)
        self.assertFalse(started)


if __name__ == "__main__":
    unittest.main()
