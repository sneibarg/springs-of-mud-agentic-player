import json

from pathlib import Path
from typing import List, Union

from agent.Agent import Agent


class AgentCollection:
    """Snapshot of the SOMDB.Agents collection."""

    DATABASE = "SOMDB"
    NAME = "Agents"
    FILENAME = "SOMDB.Agents.json"

    def __init__(self, agents: List[Agent], source: str):
        self.agents = agents
        self.source = source

    @classmethod
    def load(cls, path: Union[str, Path]) -> "AgentCollection":
        collection_path = Path(path)
        with collection_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise ValueError(f"{collection_path} must be a JSON array of agent documents")
        agents = [Agent.from_json(item) for item in payload]
        return cls(agents, str(collection_path))
