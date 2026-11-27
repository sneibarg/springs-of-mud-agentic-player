from dataclasses import dataclass, field
from uuid import uuid4

from util.SharedUtil import SharedUtil


@dataclass
class BootstrapProgress:
    """One collection attempt and its exact acceptance requirements."""

    attempt_id: str = ""
    status: str = "not_started"
    stages: dict[str, bool] = field(default_factory=dict)
    required_ids: list[str] = field(default_factory=list)
    error: str = ""
    player_name: str = ""
    marker_reset: bool = False

    def begin(self, player_name: str = "") -> None:
        self.attempt_id = uuid4().hex
        self.status = "collecting"
        self.stages = {name: False for name in ("login", "commands", "help", "areas", "who", "look")}
        self.required_ids = []
        self.error = ""
        self.player_name = player_name
        self.marker_reset = False

    def require(self, identifier: str) -> None:
        if identifier not in self.required_ids:
            self.required_ids.append(identifier)

    def finish_collection(self) -> None:
        self.status = "awaiting_acceptance" if all(self.stages.values()) else "incomplete"

    def ready(self, journal) -> bool:
        return self.status == "awaiting_acceptance" and bool(self.required_ids) and set(self.required_ids) <= journal.accepted_ids

    def to_review(self) -> dict:
        return {"attempt_id": self.attempt_id, "status": self.status, "stages": dict(self.stages), "required_ids": list(self.required_ids), "error": self.error, "player_name": self.player_name, "marker_reset": self.marker_reset}

    @classmethod
    def from_json(cls, data: dict) -> "BootstrapProgress":
        return cls(**SharedUtil.snake_tree(data))
