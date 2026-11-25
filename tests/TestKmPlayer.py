import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent.Agent import Agent
from agent.AgentConfig import AgentConfig
from main import run_agent
from net.rest.KmAnswer import KmAnswer
from net.rest.KmClient import KmClient, KmError
from net.rest.KmPlayer import KmPlayer


class TestKmPlayer(unittest.TestCase):
    def test_first_start_creates_and_second_start_reuses_situation_and_facts(self):
        calls = []
        exists = False
        facts = {}

        def request(method, url, json, headers, timeout):
            nonlocal exists
            expression = json["expression"]
            calls.append((url, expression))
            answer = "nil"
            if url.endswith("/km/query"):
                answer = "(Som-Agentic-Player Situation)" if exists else "nil"
            elif url.endswith("/km/assertions"):
                exists = True
                answer = "(*Player-sneibarg-Janky)"
            elif url.endswith("/assertions"):
                facts["level"] = "(5)"
            else:
                answer = facts["level"]
            response = Mock(status_code=200, content=b"{}")
            response.json.return_value = {"ok": True, "answer": answer}
            return response

        first = KmPlayer(KmClient(request=request), "sneibarg", "Janky")
        first.ensure()
        first.assert_expression("(*Goal has (som-target-level (5)))")
        second = KmPlayer(KmClient(request=request), "sneibarg", "Janky")
        second.ensure()
        self.assertEqual(second.query("(the som-target-level of *Goal)").answer, "(5)")
        declarations = [expression for url, expression in calls if url.endswith("/km/assertions")]
        self.assertEqual(declarations, ["(in-situation *Global (*Player-sneibarg-Janky has (instance-of (Som-Agentic-Player))))"])
        self.assertEqual(calls[0][1], "(in-situation *Global (the instance-of of *Player-sneibarg-Janky))")
        self.assertTrue(calls[-1][0].endswith("/km/players/Player-sneibarg-Janky/query"))
        self.assertFalse(any("baseline" in url for url, expression in calls))

    def test_identity_is_stable_safe_and_unambiguous(self):
        client = Mock(spec=KmClient)
        self.assertEqual(KmPlayer(client, "sneibarg", "Janky").name, "Player-sneibarg-Janky")
        pairs = [("a-b", "c"), ("a", "b-c"), ("a_2db", "c"), ("é", "A) (bad)")]
        names = [KmPlayer(client, account, character).name for account, character in pairs]
        self.assertEqual(len(set(names)), len(names))
        for name in names:
            self.assertRegex(name, r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
        self.assertNotEqual(KmPlayer(client, "a", "B").name, KmPlayer(client, "a", "b").name)
        with self.assertRaises(KmError):
            KmPlayer(client, "", "Janky")

    def test_failed_or_wrong_type_query_never_creates(self):
        for answer in [KmAnswer(False, "nil", errors=("reasoning failed",)), KmAnswer(True, "(Some-Other-Class)")]:
            client = Mock(spec=KmClient)
            client.query.return_value = answer
            with self.subTest(answer=answer), self.assertRaises(KmError):
                KmPlayer(client, "account", "character").ensure()
            client.assert_expression.assert_not_called()

    def test_unconfirmed_creation_stops_startup(self):
        client = Mock(spec=KmClient)
        client.query.return_value = KmAnswer(True, "nil")
        client.assert_expression.return_value = KmAnswer(True, "(*Player-a-b)")
        with self.assertRaisesRegex(KmError, "not confirmed"):
            KmPlayer(client, "a", "b").ensure()

    def test_failed_assertion_is_not_treated_as_created(self):
        client = Mock(spec=KmClient)
        client.query.return_value = KmAnswer(True, "nil")
        client.assert_expression.return_value = KmAnswer(False, "nil", errors=("failed",))
        with self.assertRaisesRegex(KmError, "failed"):
            KmPlayer(client, "a", "b").ensure()
        self.assertEqual(client.query.call_count, 1)

    def test_runtime_checks_even_when_idle_and_bootstrap_disabled(self):
        config = AgentConfig.load(os.path.join(os.path.dirname(__file__), "..", "resources", "agent.yml"))
        agent = Agent("1", "AgentJanky", "sneibarg", "Janky")
        with patch("main.load_registry") as registry, patch("main.KmPlayer") as player, patch("main._km_client") as client, patch("main.ConnectionCatalog.load", side_effect=RuntimeError("after KM check")):
            registry.return_value.require.return_value = agent
            with self.assertRaisesRegex(RuntimeError, "after KM check"):
                run_agent(agent.name, config)
            player.assert_called_once_with(client.return_value, "sneibarg", "Janky")
            player.return_value.ensure.assert_called_once_with()

    def test_runtime_failure_stops_before_opening_connections(self):
        config = AgentConfig.load(os.path.join(os.path.dirname(__file__), "..", "resources", "agent.yml"))
        with patch("main.load_registry"), patch("main.KmPlayer") as player, patch("main.ConnectionCatalog.load") as catalog, patch("sys.stderr"):
            player.return_value.ensure.side_effect = KmError("unavailable")
            self.assertEqual(run_agent("AgentJanky", config), 1)
            catalog.assert_not_called()

    def test_player_routes_validate_names_and_use_configured_path(self):
        response = Mock(status_code=200, content=b"{}")
        response.json.return_value = {"ok": True, "answer": "nil"}
        request = Mock(return_value=response)
        client = KmClient("http://nlp:9081", request=request, players_path="/custom/players/")
        client.query_player("*Player-a-b", "(the som-target-level of *Goal)")
        self.assertEqual(request.call_args.args[1], "http://nlp:9081/custom/players/Player-a-b/query")
        for name in ["Global", "*Global", "a/b", "a) (bad)", "", None]:
            with self.subTest(name=name), self.assertRaises(KmError):
                client.query_player(name, "(1 + 2)")
        self.assertEqual(request.call_count, 1)
        response.status_code = 400
        response.json.return_value = {"error": "Player reasoning failed"}
        with self.assertRaisesRegex(KmError, "Player reasoning failed"):
            client.assert_player("Player-a-b", "(bad)")

    def test_player_path_config_default_and_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.yml"
            base = "auth:\n  base_url: http://auth\n  login_path: /login\n"
            path.write_text(base, encoding="utf-8")
            self.assertEqual(AgentConfig.load(str(path)).km_players_path, "/km/players")
            path.write_text(base + "km:\n  players_path: custom/players\n", encoding="utf-8")
            self.assertEqual(AgentConfig.load(str(path)).km_players_path, "/custom/players")
