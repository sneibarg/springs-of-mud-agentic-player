from dataclasses import dataclass, field
from typing import Any

from util.SharedUtil import SharedUtil


_LOCATIONS = {"channel", "tells", "room"}


@dataclass
class Conversation:
    """One conversation noticed during the play session."""

    topic: str
    location: str
    location_name: str
    participants: list[str] = field(default_factory=list)
    interest: int = 0

    def __post_init__(self):
        self.topic = str(self.topic).strip()
        if not self.topic:
            raise ValueError("A conversation needs a topic")
        self.location = str(self.location).strip().lower()
        if self.location not in _LOCATIONS:
            raise ValueError("Conversation location must be channel, tells, or room")
        self.location_name = str(self.location_name).strip()
        if not self.location_name:
            raise ValueError("A conversation needs a location name")
        self.participants = _participants(self.participants)
        self.interest = _priority(self.interest)

    def set_interest(self, priority: int) -> int:
        """Replace the agent's interest. A higher integer is a higher priority."""
        self.interest = _priority(priority)
        return self.interest

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Conversation":
        if not isinstance(data, dict):
            raise TypeError("Conversation document must be an object")
        normalized = SharedUtil.camel_to_snake_case(data)
        return cls(topic=str(normalized.get("topic", "")), location=str(normalized.get("location", "")), location_name=str(normalized.get("location_name", "")), participants=normalized.get("participants", []), interest=normalized.get("interest", 0))


def _priority(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Conversation interest must be an integer priority")
    return value


def _participants(values) -> list[str]:
    if isinstance(values, str) or not isinstance(values, list):
        raise ValueError("Conversation participants must be a list of names")
    names = []
    seen = set()
    for value in values:
        name = str(value).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names
