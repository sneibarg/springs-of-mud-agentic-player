from dataclasses import asdict, dataclass, field

from memory.BootstrapProgress import BootstrapProgress
from memory.EvidenceJournal import EvidenceJournal
from memory.CombatState import CombatState
from memory.CommandList import CommandList
from memory.KnownCommand import KnownCommand
from memory.PendingAction import PendingAction
from memory.PlayClock import PlayClock
from memory.RoomVisit import RoomVisit
from util.SharedUtil import SharedUtil


@dataclass
class PlaySession:
    """Live process state owned by WorkingMemory, independent of the engine."""

    progress: PlayClock = field(default_factory=PlayClock)
    room: RoomVisit = field(default_factory=RoomVisit)
    combat: CombatState = field(default_factory=CombatState)
    pending_action: PendingAction | None = None
    last_prompt: str = ""
    look_unread: bool = False
    score_unread: bool = False
    areas_unread: bool = False
    observation_lines: list[str] = field(default_factory=list)
    available_commands: CommandList = field(default_factory=CommandList)
    commands_observed: bool = False
    evidence: EvidenceJournal = field(default_factory=EvidenceJournal)
    bootstrap: BootstrapProgress = field(default_factory=BootstrapProgress)

    def observe_commands(self, names: list[str]) -> None:
        self.available_commands.replace(KnownCommand(name) for name in names)
        self.commands_observed = True

    def clear_command_availability(self) -> None:
        self.available_commands = CommandList()
        self.commands_observed = False

    def command_available(self, name: str) -> bool:
        return self.commands_observed and self.available_commands.named(name) is not None

    def note_score(self, level: int, hours: int, exp_to_level: int, hit: int | None, max_hit: int | None, position: str) -> None:
        self.progress.note_score(level, hours, exp_to_level)
        self.combat.note_score(hit, max_hit, position)

    def to_review(self) -> dict:
        return {"evidence": self.evidence.to_review(), "bootstrap": self.bootstrap.to_review(), "progress": asdict(self.progress), "room": self.room.to_review(), "combat": self.combat.to_review(), "pending_action": asdict(self.pending_action) if self.pending_action is not None else None, "last_prompt": self.last_prompt, "look_unread": self.look_unread, "score_unread": self.score_unread, "areas_unread": self.areas_unread, "observation_lines": list(self.observation_lines), "available_commands": [command.name for command in self.available_commands.records()], "commands_observed": self.commands_observed}

    @classmethod
    def from_json(cls, data: dict) -> "PlaySession":
        payload = SharedUtil.snake_tree(data)
        pending = payload.get("pending_action")
        if not isinstance(payload.get("commands_observed", False), bool):
            raise ValueError("commands_observed must be a boolean")
        available = CommandList.from_json([{"name": name} for name in payload.get("available_commands", [])])
        return cls(evidence=EvidenceJournal.from_json(payload.get("evidence", {})), bootstrap=BootstrapProgress.from_json(payload.get("bootstrap", {})), progress=PlayClock.from_json(payload.get("progress", {})), room=RoomVisit.from_json(payload.get("room", {})), combat=CombatState.from_json(payload.get("combat", {})), pending_action=PendingAction.from_json(pending) if pending is not None else None, last_prompt=payload.get("last_prompt", ""), look_unread=payload.get("look_unread", False), score_unread=payload.get("score_unread", False), areas_unread=payload.get("areas_unread", False), observation_lines=list(payload.get("observation_lines", [])), available_commands=available, commands_observed=payload.get("commands_observed", False))
