import json
import re

from dataclasses import asdict, dataclass, field
from pathlib import Path

from memory.ConsiderReading import ConsiderReading, parse_consider
from play.WorldReader import split_look_prefixes


_KINDS = {"player", "mobile", "npc"}
_FIGHTING_YOU = re.compile(r"^(?P<name>.+) is here, fighting YOU!$", re.IGNORECASE)


@dataclass
class SessionBeing:
    name: str
    kind: str
    agentic: bool = False
    room_name: str = ""
    aggressive: bool = False
    auras: list[str] = field(default_factory=list)


@dataclass
class SessionRoom:
    name: str
    description: str = ""
    exits: list[str] = field(default_factory=list)


@dataclass
class SessionCommand:
    name: str
    category: str = ""
    help_text: str = ""


class WorkingMemory:
    """Short-lived memory for one play session.

    This is not saved with world knowledge. Call `clear` when the session ends.
    """

    def __init__(self):
        self._beings: dict[str, SessionBeing] = {}
        self._rooms: dict[str, SessionRoom] = {}
        self._commands: dict[str, SessionCommand] = {}
        self._command_order: list[str] = []
        self._considers: dict[str, ConsiderReading] = {}

    def clear(self) -> None:
        self._beings.clear()
        self._rooms.clear()
        self._commands.clear()
        self._command_order.clear()
        self._considers.clear()

    def remember_player(
        self,
        name: str,
        *,
        agentic: bool = False,
        room_name: str = "",
        auras: list[str] | None = None,
    ) -> SessionBeing:
        being = self._upsert(name, "player", room_name, auras)
        being.agentic = agentic
        return being

    def remember_mobile(
        self,
        name: str,
        *,
        room_name: str = "",
        aggressive: bool = False,
        auras: list[str] | None = None,
    ) -> SessionBeing:
        being = self._upsert(name, "mobile", room_name, auras)
        if aggressive:
            being.aggressive = True
        return being

    def remember_npc(self, name: str, *, room_name: str = "", auras: list[str] | None = None) -> SessionBeing:
        return self._upsert(name, "npc", room_name, auras)

    def note_aggressive(self, name: str, *, room_name: str = "") -> SessionBeing:
        return self.remember_mobile(name, room_name=room_name, aggressive=True)

    def remember_room(self, name: str, *, description: str = "", exits: list[str] | None = None) -> SessionRoom:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("A session room needs a name")
        key = cleaned.lower()
        room = self._rooms.get(key)
        if room is None:
            room = SessionRoom(name=cleaned)
            self._rooms[key] = room
        room.name = cleaned
        if description:
            room.description = description
        if exits:
            room.exits = list(exits)
        return room

    def room_named(self, name: str) -> SessionRoom | None:
        return self._rooms.get(name.strip().lower())

    def rooms(self) -> list[SessionRoom]:
        return sorted(self._rooms.values(), key=lambda room: room.name.lower())

    def remember_command(self, name: str, *, category: str = "", help_text: str = "") -> SessionCommand:
        """Remember one command from the server `commands` list.

        A later call without a category or help text leaves those values stored.
        """
        cleaned = name.strip().lower()
        if not cleaned:
            raise ValueError("A session command needs a name")
        command = self._commands.get(cleaned)
        if command is None:
            command = SessionCommand(name=cleaned)
            self._commands[cleaned] = command
            self._command_order.append(cleaned)
        command.name = cleaned
        if category.strip():
            command.category = category.strip()
        if help_text.strip():
            command.help_text = help_text.strip()
        return command

    def remember_commands(self, names: list[str]) -> list[SessionCommand]:
        """Remember command names in the order the server offered them."""
        return [self.remember_command(name) for name in names]

    def command_named(self, name: str) -> SessionCommand | None:
        return self._commands.get(name.strip().lower())

    def commands(self) -> list[SessionCommand]:
        return [self._commands[key] for key in self._command_order]

    def observe_line(self, line: str, *, room_name: str = "") -> SessionBeing | None:
        """A mobile already fighting you is treated as aggressive."""
        auras, rest = split_look_prefixes(line)
        match = _FIGHTING_YOU.match(rest)
        if match is None:
            return None
        return self.remember_mobile(
            match.group("name").strip(),
            room_name=room_name,
            aggressive=True,
            auras=auras,
        )

    def remember_consider(self, target: str, lines: list[str], *, kind: str, agentic: bool = False) -> ConsiderReading:
        if kind not in _KINDS:
            raise ValueError(f"Consider kind must be player, mobile, or npc, got {kind}")
        reading = parse_consider(target, lines, kind="agentic" if agentic and kind == "player" else kind)
        self._considers[reading.target.lower()] = reading
        if reading.subject and reading.subject.lower() != reading.target.lower():
            self._considers[reading.subject.lower()] = reading
        if reading.estimated:
            self._remember_subject(reading, agentic=agentic)
        return reading

    def being_named(self, name: str) -> SessionBeing | None:
        return self._beings.get(name.strip().lower())

    def consider_for(self, name: str) -> ConsiderReading | None:
        return self._considers.get(name.strip().lower())

    def players(self) -> list[SessionBeing]:
        return [being for being in self._beings.values() if being.kind == "player" and not being.agentic]

    def agentic_players(self) -> list[SessionBeing]:
        return [being for being in self._beings.values() if being.kind == "player" and being.agentic]

    def mobiles(self) -> list[SessionBeing]:
        return [being for being in self._beings.values() if being.kind == "mobile"]

    def npcs(self) -> list[SessionBeing]:
        return [being for being in self._beings.values() if being.kind == "npc"]

    def aggressive_mobiles(self) -> list[SessionBeing]:
        return [being for being in self.mobiles() if being.aggressive]

    def considers(self) -> list[ConsiderReading]:
        seen: set[int] = set()
        readings: list[ConsiderReading] = []
        for reading in self._considers.values():
            if id(reading) in seen:
                continue
            seen.add(id(reading))
            readings.append(reading)
        return readings

    def to_review(self) -> dict:
        """A readable snapshot. This is not the world-knowledge document."""
        return {
            "players": [_being_review(being) for being in _by_name(self.players())],
            "agentic_players": [_being_review(being) for being in _by_name(self.agentic_players())],
            "mobiles": [_being_review(being) for being in _by_name(self.mobiles())],
            "npcs": [_being_review(being) for being in _by_name(self.npcs())],
            "aggressive_mobiles": [_being_review(being) for being in _by_name(self.aggressive_mobiles())],
            "rooms": [_room_review(room) for room in self.rooms()],
            "commands": [_command_review(command) for command in self.commands()],
            "considers": [_consider_review(reading) for reading in _by_target(self.considers())],
        }

    def write_review(self, path: str) -> str:
        """Write to_review() as indented JSON. Returns the path that was written."""
        cleaned = str(path or "").strip()
        if not cleaned:
            raise ValueError("Working memory review path is empty")
        destination = Path(cleaned)
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_review(), indent=2, ensure_ascii=False) + "\n"
        destination.write_text(text, encoding="utf-8")
        return str(destination)

    def absorb_world(self, knowledge) -> None:
        """Copy the current world snapshot. Does not clear earlier consider results."""
        for player in knowledge.players.values():
            if getattr(player, "self_character", False):
                continue
            self.remember_player(
                player.name,
                agentic=bool(getattr(player, "agentic", False)),
                room_name=getattr(player, "room_name", "") or "",
                auras=_copied_auras(player),
            )
        for mobile in knowledge.mobiles.values():
            fighting_you = getattr(mobile, "pose", "") == "fighting" and str(getattr(mobile, "detail", "")).upper().startswith("YOU")
            self.remember_mobile(
                mobile.name,
                room_name=getattr(mobile, "room_name", "") or "",
                aggressive=fighting_you,
                auras=_copied_auras(mobile),
            )
        for npc in getattr(knowledge, "npcs", {}).values():
            self.remember_npc(
                npc.name,
                room_name=getattr(npc, "room_name", "") or "",
                auras=_copied_auras(npc),
            )
        room = getattr(knowledge, "room", None)
        if room is not None and str(getattr(room, "name", "") or "").strip():
            self.remember_room(
                room.name,
                description=str(getattr(room, "description", "") or ""),
                exits=list(getattr(room, "exits", []) or []),
            )

    def _remember_subject(self, reading: ConsiderReading, *, agentic: bool) -> None:
        if reading.kind == "agentic":
            self.remember_player(reading.subject, agentic=True)
        elif reading.kind == "player":
            self.remember_player(reading.subject, agentic=agentic)
        elif reading.kind == "mobile":
            self.remember_mobile(reading.subject)
        else:
            self.remember_npc(reading.subject)

    def _upsert(self, name: str, kind: str, room_name: str, auras: list[str] | None = None) -> SessionBeing:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("A session being needs a name")
        key = cleaned.lower()
        being = self._beings.get(key)
        if being is None:
            being = SessionBeing(name=cleaned, kind=kind, room_name=room_name)
            self._beings[key] = being
        else:
            if being.kind != kind:
                being.aggressive = False
                being.agentic = False
            being.kind = kind
            being.name = cleaned
            if room_name:
                being.room_name = room_name
        if auras is not None:
            being.auras = list(auras)
        return being


def _copied_auras(record) -> list[str]:
    return [str(aura) for aura in (getattr(record, "auras", None) or [])]


def _being_review(being: SessionBeing) -> dict:
    return asdict(being)


def _room_review(room: SessionRoom) -> dict:
    return asdict(room)


def _command_review(command: SessionCommand) -> dict:
    return asdict(command)


def _consider_review(reading: ConsiderReading) -> dict:
    return asdict(reading)


def _by_name(beings: list[SessionBeing]) -> list[SessionBeing]:
    return sorted(beings, key=lambda being: being.name.lower())


def _by_target(readings: list[ConsiderReading]) -> list[ConsiderReading]:
    return sorted(readings, key=lambda reading: reading.target.lower())
