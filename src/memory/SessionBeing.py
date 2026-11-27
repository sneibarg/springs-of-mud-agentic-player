from dataclasses import dataclass, field
from uuid import uuid4

from util.SharedUtil import SharedUtil


@dataclass
class SessionBeing:
    name: str
    kind: str
    agentic: bool | None = None
    room_name: str = ""
    aggressive: bool | None = None
    auras: list[str] = field(default_factory=list)
    being_id: str = field(default_factory=lambda: "Being-" + uuid4().hex)
    room_id: str = ""
    provisional: bool = True

    def observe(self, name: str, kind: str, room_name: str, room_id: str, auras: list[str] | None = None, aggressive: bool | None = None, agentic: bool | None = None) -> None:
        if self.kind != kind:
            self.aggressive = None
            self.agentic = None
        self.name = name
        self.kind = kind
        if room_name:
            self.room_name = room_name
        if room_id:
            self.room_id = room_id
        if auras is not None:
            self.auras = list(auras)
        if aggressive is not None:
            self.aggressive = aggressive
        if agentic is not None:
            self.agentic = agentic

    def to_legacy(self) -> dict:
        return {"name": self.name, "kind": self.kind, "agentic": bool(self.agentic), "room_name": self.room_name, "aggressive": bool(self.aggressive), "auras": list(self.auras)}

    @classmethod
    def from_json(cls, data: dict) -> "SessionBeing":
        return cls(**SharedUtil.snake_tree(data))
