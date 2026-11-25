import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent.AgentCollection import AgentCollection
from agent.AgentConfig import AgentConfig
from agent.AgentRegistry import AgentRegistry


ROOT = Path(__file__).resolve().parents[1]


class TestAgentCollection(unittest.TestCase):
    def test_snapshot_loads_example_agent(self):
        collection = AgentCollection.load(ROOT / "resources" / "collections" / "SOMDB.Agents.json")
        registry = AgentRegistry(collection.agents)
        agent = registry.require("example-agent")

        self.assertEqual(collection.DATABASE, "SOMDB")
        self.assertEqual(collection.NAME, "Agents")
        self.assertEqual(agent.id, "66f0a1b2c3d4e5f607182930")
        self.assertEqual(agent.account_name, "agent-account")
        self.assertEqual(agent.character_name, "Example")
        self.assertTrue(agent.enabled)

    def test_config_points_at_somdb_agents(self):
        config = AgentConfig.load(str(ROOT / "resources" / "agent.yml"))
        self.assertEqual(config.database, "SOMDB")
        self.assertEqual(config.collection_name, "Agents")
        self.assertEqual(config.collection_path, ROOT / "resources" / "collections" / "SOMDB.Agents.json")
        self.assertEqual(config.auth_base_url, "http://dragon:8169")
        self.assertEqual(config.login_path, "/api/auth/login")
        self.assertEqual(config.telnet_port, 6969)
        self.assertEqual(config.telnet_replace_existing, "Y")
        self.assertEqual(config.api_base_url, "http://dragon:9080")
        self.assertEqual(config.agents_path, "/api/v1/agents")
        self.assertEqual(config.prompts_path, "/api/v1/agent-prompts")
        self.assertEqual(config.memory_path, "/api/v1/agent-memory")
        self.assertEqual(config.knowledge_path, "/api/v1/agent-knowledge")
        self.assertEqual(config.ollama_base_url, "http://localhost:9081")
        self.assertEqual(config.ollama_path, "/ollama/completions")
        self.assertEqual(config.connections_path, ROOT / "resources" / "connections.json")
        self.assertEqual(config.control_host, "127.0.0.1")
        self.assertEqual(config.control_port, 9711)
        self.assertTrue(config.initial_bootstrap)
        self.assertTrue(config.defer_bootstrap)

    def test_duplicate_name_is_rejected(self):
        document = {"_id": {"$oid": "66f0a1b2c3d4e5f607182931"}, "name": "Guide", "accountName": "account", "characterName": "Guide"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SOMDB.Agents.json"
            path.write_text(json.dumps([document, dict(document, name="guide")]), encoding="utf-8")
            collection = AgentCollection.load(path)
            with self.assertRaises(ValueError):
                AgentRegistry(collection.agents)

    def test_disabled_agent_is_not_required(self):
        document = {"_id": "abc", "name": "sleeper", "accountName": "account", "characterName": "Sleeper", "enabled": False}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SOMDB.Agents.json"
            path.write_text(json.dumps([document]), encoding="utf-8")
            registry = AgentRegistry(AgentCollection.load(path).agents)
            self.assertFalse(registry.get("sleeper").enabled)
            with self.assertRaises(ValueError):
                registry.require("sleeper")

    def test_control_host_must_be_loopback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.yml"
            path.write_text("auth:\n  base_url: http://dragon:8169\n  login_path: /api/auth/login\ncontrol:\n  host: 10.0.0.1\n  port: 9711\n", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                AgentConfig.load(str(path))
            self.assertEqual(str(caught.exception), "Control host must be localhost")

            path.write_text("auth:\n  base_url: http://dragon:8169\n  login_path: /api/auth/login\ncontrol:\n  host: localhost\n  port: 0\n", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                AgentConfig.load(str(path))
            self.assertEqual(str(caught.exception), "control.port must be a TCP port")

    def test_initial_bootstrap_defaults_off_and_rejects_a_non_boolean(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.yml"
            path.write_text("auth:\n  base_url: http://dragon:8169\n  login_path: /api/auth/login\ncontrol:\n  host: 127.0.0.1\n  port: 9711\n", encoding="utf-8")
            self.assertFalse(AgentConfig.load(str(path)).initial_bootstrap)
            path.write_text("control:\n  host: 127.0.0.1\n  port: 9711\n", encoding="utf-8")
            with self.assertRaises(ValueError) as missing:
                AgentConfig.load(str(path))
            self.assertEqual(str(missing.exception), "auth.base_url is required")
            path.write_text("auth:\n  base_url: http://dragon:8169\n  login_path: /api/auth/login\nbootstrap:\n  initial: \"no\"\n", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                AgentConfig.load(str(path))
            self.assertEqual(str(caught.exception), "bootstrap.initial must be a boolean")
            path.write_text("auth:\n  base_url: http://dragon:8169\n  login_path: /api/auth/login\nbootstrap:\n  defer: \"later\"\n", encoding="utf-8")
            with self.assertRaises(ValueError) as deferred:
                AgentConfig.load(str(path))
            self.assertEqual(str(deferred.exception), "bootstrap.defer must be a boolean")
            path.write_text("auth:\n  base_url: http://dragon:8169\n  login_path: /api/auth/login\n", encoding="utf-8")
            self.assertFalse(AgentConfig.load(str(path)).defer_bootstrap)

    def test_km_bridge_defaults_to_the_nlp_service(self):
        config = AgentConfig.load(str(ROOT / "resources" / "agent.yml"))
        self.assertEqual(config.km_base_url, config.ollama_base_url)
        self.assertEqual(config.km_query_path, "/km/query")
        self.assertEqual(config.km_assertions_path, "/km/assertions")
        self.assertEqual(config.km_baseline_path, "/km/baseline")
        self.assertIsNone(config.level_goal)

    def test_goal_and_km_settings_are_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.yml"
            path.write_text("auth:\n  base_url: http://dragon:8169\n  login_path: /api/auth/login\nkm:\n  base_url: http://dragon:9081/\n  baseline_path: /km/baseline\ngoal:\n  level: 5\n  risk: cautious\n  minutes: 0\n", encoding="utf-8")
            config = AgentConfig.load(str(path))
            self.assertEqual(config.km_base_url, "http://dragon:9081")
            self.assertEqual(config.level_goal.target_level, 5)
            self.assertEqual(config.level_goal.risk, "cautious")
            self.assertEqual(config.level_goal.minutes, 0)
            path.write_text("auth:\n  base_url: http://dragon:8169\n  login_path: /api/auth/login\ngoal:\n  level: 0\n", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                AgentConfig.load(str(path))
            self.assertEqual(str(caught.exception), "goal.level must be an integer of 1 or more")
            path.write_text("auth:\n  base_url: http://dragon:8169\n  login_path: /api/auth/login\ngoal:\n  level: 2\n  risk: wild\n", encoding="utf-8")
            with self.assertRaises(ValueError) as risk:
                AgentConfig.load(str(path))
            self.assertEqual(str(risk.exception), "goal.risk must be cautious, steady, or bold")


if __name__ == "__main__":
    unittest.main()
