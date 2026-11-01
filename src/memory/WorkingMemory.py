import json
import re

from dataclasses import asdict, dataclass, field
from pathlib import Path

from memory.ConsiderOpponent import ConsiderOpponent, parse_consider
from memory.Conversation import Conversation
from util.SharedUtil import SharedUtil


_KINDS = {"player", "mobile", "npc"}
_FIGHTING_YOU = re.compile(r"^(?P<name>.+) is here, fighting YOU!$", re.IGNORECASE)
_COLLECTION_FILE = "SOMDB.Memories.json"


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
    `to_collection` is the body for PUT /api/v1/agent-memory/{agentName}.
    `from_collection` restores that document. `write_collection` copies the
    session into the local Memories fixture.
    """

    def __init__(self):
        self._beings: dict[str, SessionBeing] = {}
        self._rooms: dict[str, SessionRoom] = {}
        self._commands: dict[str, SessionCommand] = {}
        self._command_order: list[str] = []
        self._considers: dict[str, ConsiderOpponent] = {}
        self._conversations: dict[tuple[str, str, str], Conversation] = {}

    def clear(self) -> None:
        self._beings.clear()
        self._rooms.clear()
        self._commands.clear()
        self._command_order.clear()
        self._considers.clear()
        self._conversations.clear()

    def remember_player(self, name: str, *, agentic: bool = False, room_name: str = "", auras: list[str] | None = None) -> SessionBeing:
        being = self._upsert(name, "player", room_name, auras)
        being.agentic = agentic
        return being

    def remember_mobile(self, name: str, *, room_name: str = "", aggressive: bool = False, auras: list[str] | None = None) -> SessionBeing:
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

    def remember_conversation(self, topic: str, location: str, location_name: str, *, participants: list[str] | None = None, interest: int | None = None) -> Conversation:
        """Remember one conversation.

        The same topic, location, and location name stay one conversation. A
        later call with participants replaces that list. Omitting interest
        leaves the stored priority.
        """
        draft = Conversation(topic=topic, location=location, location_name=location_name, participants=[] if participants is None else participants, interest=0 if interest is None else interest)
        stored = self._conversations.get(_conversation_key(draft))
        if stored is None:
            self._conversations[_conversation_key(draft)] = draft
            return draft
        stored.topic = draft.topic
        stored.location_name = draft.location_name
        if participants is not None:
            stored.participants = draft.participants
        if interest is not None:
            stored.set_interest(interest)
        return stored

    def conversation_for(self, topic: str, location: str, location_name: str) -> Conversation | None:
        return self._conversations.get((topic.strip().lower(), location.strip().lower(), location_name.strip().lower()))

    def conversations(self) -> list[Conversation]:
        return sorted(self._conversations.values(), key=lambda conversation: (-conversation.interest, conversation.topic.lower(), conversation.location, conversation.location_name.lower()))

    def observe_line(self, line: str, *, room_name: str = "") -> SessionBeing | None:
        """A mobile already fighting you is treated as aggressive."""
        from play.WorldReader import split_look_prefixes

        auras, rest = split_look_prefixes(line)
        match = _FIGHTING_YOU.match(rest)
        if match is None:
            return None
        return self.remember_mobile(match.group("name").strip(), room_name=room_name, aggressive=True, auras=auras)

    def remember_consider(self, target: str, lines: list[str], *, kind: str, agentic: bool = False) -> ConsiderOpponent:
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

    def consider_for(self, name: str) -> ConsiderOpponent | None:
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

    def considers(self) -> list[ConsiderOpponent]:
        seen: set[int] = set()
        readings: list[ConsiderOpponent] = []
        for reading in self._considers.values():
            if id(reading) in seen:
                continue
            seen.add(id(reading))
            readings.append(reading)
        return readings

    def to_review(self) -> dict:
        """A readable snapshot. This is not the world-knowledge document."""
        return {"players": [asdict(being) for being in _by_name(self.players())], "agentic_players": [asdict(being) for being in _by_name(self.agentic_players())], "mobiles": [asdict(being) for being in _by_name(self.mobiles())], "npcs": [asdict(being) for being in _by_name(self.npcs())], "aggressive_mobiles": [asdict(being) for being in _by_name(self.aggressive_mobiles())], "rooms": [asdict(room) for room in self.rooms()], "commands": [asdict(command) for command in self.commands()], "considers": [asdict(reading) for reading in _by_target(self.considers())], "conversations": [asdict(conversation) for conversation in self.conversations()]}

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

    def to_collection(self, agent_name: str) -> dict:
        """One Memories document for this session, looked up by `agentName`."""
        cleaned = str(agent_name or "").strip()
        if not cleaned:
            raise ValueError("Working memory collection requires an agent name")
        document = {"agentName": cleaned}
        for key, value in self.to_review().items():
            document[SharedUtil.snake_to_camel(key)] = SharedUtil.camel_keys(value)
        return document

    @classmethod
    def from_collection(cls, document: dict) -> "WorkingMemory":
        """Restore one Memories document. `savedAt` and `id` are ignored."""
        if not isinstance(document, dict):
            raise TypeError("Working memory document must be an object")
        payload = _snake_tree(document)
        if not str(payload.get("agent_name", "") or "").strip():
            raise ValueError("Working memory collection requires an agent name")
        memory = cls()
        for item in payload.get("players") or []:
            _restore_being(memory, item, "player", agentic=False)
        for item in payload.get("agentic_players") or []:
            _restore_being(memory, item, "player", agentic=True)
        for item in payload.get("mobiles") or []:
            _restore_being(memory, item, "mobile")
        for item in payload.get("npcs") or []:
            _restore_being(memory, item, "npc")
        for item in payload.get("aggressive_mobiles") or []:
            if isinstance(item, dict) and str(item.get("name", "")).strip():
                memory.note_aggressive(str(item.get("name")), room_name=str(item.get("room_name", "") or ""))
        for item in payload.get("rooms") or []:
            if isinstance(item, dict) and str(item.get("name", "")).strip():
                memory.remember_room(str(item.get("name")), description=str(item.get("description", "") or ""), exits=[str(exit_name) for exit_name in item.get("exits") or []])
        for item in payload.get("commands") or []:
            if isinstance(item, dict) and str(item.get("name", "")).strip():
                memory.remember_command(str(item.get("name")), category=str(item.get("category", "") or ""), help_text=str(item.get("help_text", "") or ""))
        for item in payload.get("considers") or []:
            _restore_consider(memory, item)
        for item in payload.get("conversations") or []:
            if isinstance(item, dict):
                conversation = Conversation.from_json(item)
                memory.remember_conversation(conversation.topic, conversation.location, conversation.location_name, participants=list(conversation.participants), interest=conversation.interest)
        return memory

    def write_collection(self, agent_name: str, path: str | None = None) -> str:
        """Upsert this session into the local Memories collection.

        Documents are matched on `agentName`, ignoring case. A later dump for
        the same agent replaces that document and leaves every other agent in
        place. The default file is `resources/collections/SOMDB.Memories.json`.
        """
        if path is not None and not str(path).strip():
            raise ValueError("Working memory collection path is empty")
        document = self.to_collection(agent_name)
        destination = Path(str(path).strip()) if path is not None else default_collection_path()
        documents = SharedUtil.read_collection(destination)
        SharedUtil.write_collection(destination, _upsert_agent(documents, document))
        return str(destination)

    def absorb_world(self, knowledge) -> None:
        """Copy the current world snapshot. Does not clear earlier consider results."""
        for player in knowledge.players.values():
            if getattr(player, "self_character", False):
                continue
            self.remember_player(player.name, agentic=bool(getattr(player, "agentic", False)), room_name=getattr(player, "room_name", "") or "", auras=_copied_auras(player))
        for mobile in knowledge.mobiles.values():
            fighting_you = getattr(mobile, "pose", "") == "fighting" and str(getattr(mobile, "detail", "")).upper().startswith("YOU")
            self.remember_mobile(mobile.name, room_name=getattr(mobile, "room_name", "") or "", aggressive=fighting_you, auras=_copied_auras(mobile))
        for npc in getattr(knowledge, "npcs", {}).values():
            self.remember_npc(npc.name, room_name=getattr(npc, "room_name", "") or "", auras=_copied_auras(npc))
        room = getattr(knowledge, "room", None)
        if room is not None and str(getattr(room, "name", "") or "").strip():
            self.remember_room(room.name, description=str(getattr(room, "description", "") or ""), exits=list(getattr(room, "exits", []) or []))

    def _remember_subject(self, reading: ConsiderOpponent, *, agentic: bool) -> None:
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


def default_collection_path() -> Path:
    return Path(__file__).resolve().parents[2] / "resources" / "collections" / _COLLECTION_FILE


def _upsert_agent(documents: list, document: dict) -> list:
    key = document["agentName"].strip().lower()
    updated = []
    replaced = False
    for existing in documents:
        if isinstance(existing, dict) and str(existing.get("agentName", "")).strip().lower() == key:
            if not replaced:
                updated.append(document)
                replaced = True
            continue
        updated.append(existing)
    if not replaced:
        updated.append(document)
    return updated


def _restore_being(memory: WorkingMemory, item, kind: str, *, agentic: bool = False) -> None:
    if not isinstance(item, dict):
        return
    name = str(item.get("name", "")).strip()
    if not name:
        return
    room_name = str(item.get("room_name", "") or "")
    auras = item.get("auras")
    aura_list = [str(aura) for aura in auras] if isinstance(auras, list) else None
    if kind == "player":
        memory.remember_player(name, agentic=agentic or bool(item.get("agentic")), room_name=room_name, auras=aura_list)
    elif kind == "mobile":
        memory.remember_mobile(name, room_name=room_name, aggressive=bool(item.get("aggressive")), auras=aura_list)
    else:
        memory.remember_npc(name, room_name=room_name, auras=aura_list)


def _restore_consider(memory: WorkingMemory, item) -> None:
    if not isinstance(item, dict):
        return
    target = str(item.get("target", "")).strip()
    if not target:
        return
    kind = str(item.get("kind", "") or "")
    agentic = kind == "agentic"
    if agentic:
        kind = "player"
    if kind not in _KINDS:
        return
    text = str(item.get("text", "") or "")
    memory.remember_consider(target, text.splitlines(), kind=kind, agentic=agentic)


def _snake_tree(value):
    if isinstance(value, dict):
        converted = SharedUtil.camel_to_snake_case(value)
        return {key: _snake_tree(item) for key, item in converted.items()}
    if isinstance(value, list):
        return [_snake_tree(item) for item in value]
    return value


def _copied_auras(record) -> list[str]:
    return [str(aura) for aura in (getattr(record, "auras", None) or [])]


def _conversation_key(conversation: Conversation) -> tuple[str, str, str]:
    return conversation.topic.lower(), conversation.location, conversation.location_name.lower()


def _by_name(beings: list[SessionBeing]) -> list[SessionBeing]:
    return sorted(beings, key=lambda being: being.name.lower())


def _by_target(readings: list[ConsiderOpponent]) -> list[ConsiderOpponent]:
    return sorted(readings, key=lambda reading: reading.target.lower())
