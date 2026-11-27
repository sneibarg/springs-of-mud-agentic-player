from dataclasses import dataclass, field
from uuid import uuid4

from util.SharedUtil import SharedUtil


@dataclass
class RoomExit:
    direction: str
    room_id: str
    exit_id: str = field(default_factory=lambda: "Exit-" + uuid4().hex)
    destination_id: str | None = None
    requires_open: bool | None = None
    requires_unlock: bool | None = None
    active: bool = True
    destination_history: list[str] = field(default_factory=list)

    def note_destination(self, room_id: str) -> None:
        self.destination_id = room_id
        if not self.destination_history or self.destination_history[-1] != room_id:
            self.destination_history.append(room_id)

    @classmethod
    def from_json(cls, data: dict) -> "RoomExit":
        return cls(**SharedUtil.snake_tree(data))
