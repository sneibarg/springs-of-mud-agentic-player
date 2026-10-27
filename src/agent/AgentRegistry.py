from typing import Iterable, List

from agent.Agent import Agent


class AgentRegistry:
    def __init__(self, agents: Iterable[Agent]):
        self._agents: List[Agent] = []
        self._by_name: dict[str, Agent] = {}
        for agent in agents:
            key = agent.name.lower()
            if key in self._by_name:
                raise ValueError(f"Duplicate agent name: {agent.name}")
            self._agents.append(agent)
            self._by_name[key] = agent

    def all(self) -> List[Agent]:
        return list(self._agents)

    def get(self, name: str) -> Agent:
        agent = self._by_name.get(name.strip().lower())
        if agent is None:
            raise KeyError(f"Agent '{name}' was not found")
        return agent

    def require(self, name: str) -> Agent:
        agent = self.get(name)
        if not agent.enabled:
            raise ValueError(f"Agent '{agent.name}' is disabled")
        return agent
