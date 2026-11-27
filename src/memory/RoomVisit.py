from dataclasses import dataclass, field
from uuid import uuid4

from util.SharedUtil import SharedUtil


@dataclass
class RoomVisit:
    """Current room and visit-local travel and consider markers."""

    name: str = ""
    exits: list[str] = field(default_factory=list)
    current: bool = False
    tried: set[str] = field(default_factory=set)
    fresh: set[str] = field(default_factory=set)
    room_id: str = ""
    visit_id: str = ""
    occupant_ids: list[str] = field(default_factory=list)
    revision: int = 0
    presence_complete: bool = False
    movement_origin_id: str = ""
    movement_direction: str = ""

    def observe(self, name: str, exits: list[str], *, room_id: str = "", new_visit: bool = False) -> None:
        identifier = room_id or (self.room_id if name.lower() == self.name.lower() else "") or "Room-" + uuid4().hex
        if new_visit or identifier != self.room_id:
            self.tried.clear()
            self.fresh.clear()
            self.occupant_ids.clear()
            self.presence_complete = False
            self.visit_id = "Visit-" + uuid4().hex
        self.room_id = identifier
        self.name = name
        self.exits = list(exits)
        self.current = True
        self.revision += 1
        self.movement_origin_id = ""
        self.movement_direction = ""

    def depart(self, direction: str) -> None:
        if direction:
            self.tried.add(direction)
        self.fresh.clear()
        self.current = False
        self.movement_origin_id = self.room_id
        self.movement_direction = direction
        self.revision += 1

    def refuse_movement(self) -> None:
        self.current = bool(self.room_id)
        self.movement_origin_id = ""
        self.movement_direction = ""

    def untried(self) -> list[str]:
        return [direction for direction in self.exits if direction not in self.tried]

    def note_consider(self, being_id: str) -> None:
        self.fresh.add(being_id)

    def to_review(self) -> dict:
        return {"name": self.name, "exits": list(self.exits), "current": self.current, "tried": sorted(self.tried), "fresh": sorted(self.fresh), "room_id": self.room_id, "visit_id": self.visit_id, "occupant_ids": list(self.occupant_ids), "revision": self.revision, "presence_complete": self.presence_complete, "movement_origin_id": self.movement_origin_id, "movement_direction": self.movement_direction}

    @classmethod
    def from_json(cls, data: dict) -> "RoomVisit":
        payload = SharedUtil.snake_tree(data)
        payload["tried"] = set(payload.get("tried", []))
        payload["fresh"] = set(payload.get("fresh", []))
        return cls(**payload)
