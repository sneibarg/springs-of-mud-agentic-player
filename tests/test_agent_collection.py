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
        self.assertEqual(config.auth_base_url, "http://localhost:8169")
        self.assertEqual(config.telnet_port, 6969)

    def test_duplicate_name_is_rejected(self):
        document = {
            "_id": {"$oid": "66f0a1b2c3d4e5f607182931"},
            "name": "Guide",
            "accountName": "account",
            "characterName": "Guide",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SOMDB.Agents.json"
            path.write_text(json.dumps([document, dict(document, name="guide")]), encoding="utf-8")
            collection = AgentCollection.load(path)
            with self.assertRaises(ValueError):
                AgentRegistry(collection.agents)

    def test_disabled_agent_is_not_required(self):
        document = {
            "_id": "abc",
            "name": "sleeper",
            "accountName": "account",
            "characterName": "Sleeper",
            "enabled": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SOMDB.Agents.json"
            path.write_text(json.dumps([document]), encoding="utf-8")
            registry = AgentRegistry(AgentCollection.load(path).agents)
            self.assertFalse(registry.get("sleeper").enabled)
            with self.assertRaises(ValueError):
                registry.require("sleeper")


if __name__ == "__main__":
    unittest.main()
