from dataclasses import asdict, dataclass, field
from uuid import uuid4

from memory.RoomExit import RoomExit
from memory.SessionItem import SessionItem
from util.SharedUtil import SharedUtil


@dataclass
class SessionRoom:
    name: str
    description: str = ""
    items: list[SessionItem] = field(default_factory=list)
    room_id: str = field(default_factory=lambda: "Room-" + uuid4().hex)
    provisional: bool = True
    exit_records: list[RoomExit] = field(default_factory=list)

    @property
    def exits(self) -> list[str]:
        return [entry.direction for entry in self.exit_records]

    def update(self, name: str, description: str | None = None, exits: list[str] | None = None, items: list[SessionItem] | None = None) -> None:
        self.name = name
        if description is not None:
            self.description = description
        if exits is not None:
            previous = {entry.direction: entry for entry in self.exit_records}
            directions = list(dict.fromkeys(direction.strip().lower() for direction in exits if direction.strip()))
            for entry in self.exit_records:
                entry.active = entry.direction in directions
            self.exit_records = [previous[direction] if direction in previous else RoomExit(direction, self.room_id) for direction in directions]
        if items is not None:
            self.items = list(items)

    def to_review(self) -> dict:
        return {"name": self.name, "description": self.description, "exits": self.exits, "items": [asdict(item) for item in self.items], "room_id": self.room_id, "provisional": self.provisional, "exit_records": [asdict(entry) for entry in self.exit_records]}

    def to_legacy(self) -> dict:
        return {"name": self.name, "description": self.description, "exits": self.exits, "items": [item.to_legacy() for item in self.items]}

    @classmethod
    def from_json(cls, data: dict) -> "SessionRoom":
        payload = SharedUtil.snake_tree(data)
        items = [SessionItem.from_json(item) for item in payload.pop("items", [])]
        records = payload.pop("exit_records", None)
        exits = payload.pop("exits", None)
        room = cls(**payload, items=items)
        if records is not None:
            room.exit_records = [RoomExit.from_json(entry) for entry in records]
        else:
            room.update(room.name, exits=exits)
        return room
