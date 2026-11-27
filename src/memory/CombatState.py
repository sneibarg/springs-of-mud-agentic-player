from dataclasses import dataclass, field

from util.SharedUtil import SharedUtil


@dataclass
class CombatState:
    """Observed vitals, position, and the session's engagement markers."""

    hit: int | None = None
    max_hit: int | None = None
    position: str = ""
    fighting: bool = False
    engaged: set[str] = field(default_factory=set)
    threats: set[str] = field(default_factory=set)
    unidentified_threat: bool = False

    def note_threat(self, name: str) -> None:
        self.fighting = True
        if name not in self.engaged:
            self.threats.add(name)

    def engage(self, name: str) -> None:
        self.engaged.add(name)
        self.fighting = True

    def leave_fight(self) -> None:
        self.fighting = False
        self.threats.clear()
        self.unidentified_threat = False

    def retain_present(self, identifiers: set[str]) -> None:
        self.engaged.intersection_update(identifiers)
        self.threats.intersection_update(identifiers)

    def has_uninvited_threat(self) -> bool:
        return self.unidentified_threat or any(name not in self.engaged for name in self.threats)

    def note_score(self, hit: int | None, max_hit: int | None, position: str) -> None:
        if hit is not None:
            self.hit = hit
        if max_hit is not None:
            self.max_hit = max_hit
        if position:
            self.position = position
            if position == "fighting":
                self.fighting = True
            elif position == "standing":
                self.leave_fight()

    def to_review(self) -> dict:
        return {"hit": self.hit, "max_hit": self.max_hit, "position": self.position, "fighting": self.fighting, "engaged": sorted(self.engaged), "threats": sorted(self.threats), "unidentified_threat": self.unidentified_threat}

    @classmethod
    def from_json(cls, data: dict) -> "CombatState":
        payload = SharedUtil.snake_tree(data)
        payload["engaged"] = set(payload.get("engaged", []))
        payload["threats"] = set(payload.get("threats", []))
        return cls(**payload)
