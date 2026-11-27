from dataclasses import dataclass, field
from uuid import uuid4

from util.SharedUtil import SharedUtil


@dataclass
class SessionItem:
    """A provisional item sighting; the look keyword is not its identity."""

    name: str
    line: str = ""
    source: str = ""
    item_id: str = field(default_factory=lambda: "Item-" + uuid4().hex)
    provisional: bool = True
    keyword_known: bool = True
    room_id: str = ""

    def to_legacy(self) -> dict:
        return {"name": self.name, "line": self.line, "source": self.source}

    @classmethod
    def from_json(cls, data: dict) -> "SessionItem":
        return cls(**SharedUtil.snake_tree(data))
