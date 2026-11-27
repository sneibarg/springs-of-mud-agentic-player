import json
from dataclasses import dataclass

from util.SharedUtil import SharedUtil


@dataclass(frozen=True)
class SessionEvidence:
    """An immutable observation snapshot, independent of later mutable views."""

    observation_id: str
    sequence: int
    observed_at: str
    kind: str
    origin: str
    source: str
    command: str
    lines: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    payload_json: str = "{}"
    transferable: bool = False

    @property
    def payload(self) -> dict:
        return json.loads(self.payload_json)

    def to_review(self) -> dict:
        return {"observation_id": self.observation_id, "sequence": self.sequence, "observed_at": self.observed_at, "kind": self.kind, "origin": self.origin, "source": self.source, "command": self.command, "lines": list(self.lines), "source_ids": list(self.source_ids), "payload": self.payload, "transferable": self.transferable}

    @classmethod
    def from_json(cls, data: dict) -> "SessionEvidence":
        data = SharedUtil.snake_tree(data)
        return cls(observation_id=data["observation_id"], sequence=data["sequence"], observed_at=data["observed_at"], kind=data["kind"], origin=data["origin"], source=data["source"], command=data["command"], lines=tuple(data.get("lines", [])), source_ids=tuple(data.get("source_ids", [])), payload_json=json.dumps(data.get("payload", {})), transferable=data.get("transferable", False))
