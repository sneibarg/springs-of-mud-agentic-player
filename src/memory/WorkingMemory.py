import json

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4
from collections import Counter

from memory.ConsiderOpponent import ConsiderOpponent, parse_consider
from memory.Conversation import Conversation
from memory.CommandList import CommandList
from memory.KnownCommand import KnownCommand
from memory.PlaySession import PlaySession
from memory.RoomExit import RoomExit
from memory.SessionBeing import SessionBeing
from memory.SessionItem import SessionItem
from memory.SessionRoom import SessionRoom
from util.SharedUtil import SharedUtil


_KINDS = {"player", "mobile", "npc"}


class WorkingMemory:
    """Session state and historical records for one player runtime.

    `command_knowledge` is a legacy description view, shared with the current
    WorldKnowledge during bootstrap/restoration. It never grants permission.
    Only `session` holds freshly observed command availability. Review output
    includes live state; the legacy memory REST projection omits it.
    """

    def __init__(self):
        self.session = PlaySession()
        self._beings: dict[str, SessionBeing] = {}
        self._rooms: dict[str, SessionRoom] = {}
        self._exits: dict[str, RoomExit] = {}
        self._items: dict[str, SessionItem] = {}
        self.command_knowledge = CommandList()
        self._considers: dict[str, ConsiderOpponent] = {}
        self._conversations: dict[tuple[str, str, str], Conversation] = {}

    def clear(self) -> None:
        self.session = PlaySession()
        self._beings.clear()
        self._rooms.clear()
        self._exits.clear()
        self._items.clear()
        self.command_knowledge = CommandList()
        self._considers.clear()
        self._conversations.clear()

    def remember_player(self, name: str, *, agentic: bool | None = None, room_name: str = "", auras: list[str] | None = None, being_id: str | None = None, room_id: str = "") -> SessionBeing:
        being = self._upsert(name, "player", room_name, auras, being_id, room_id)
        if agentic is not None:
            being.agentic = agentic
        return being

    def remember_mobile(self, name: str, *, room_name: str = "", aggressive: bool | None = None, auras: list[str] | None = None, being_id: str | None = None, room_id: str = "") -> SessionBeing:
        being = self._upsert(name, "mobile", room_name, auras, being_id, room_id)
        if aggressive is not None:
            being.aggressive = aggressive
        return being

    def remember_npc(self, name: str, *, room_name: str = "", auras: list[str] | None = None, being_id: str | None = None, room_id: str = "") -> SessionBeing:
        return self._upsert(name, "npc", room_name, auras, being_id, room_id)

    def note_aggressive(self, name: str, *, room_name: str = "", being_id: str | None = None, room_id: str = "") -> SessionBeing:
        return self.remember_mobile(name, room_name=room_name, aggressive=True, being_id=being_id, room_id=room_id)

    def remember_room(self, name: str, *, description: str | None = None, exits: list[str] | None = None, items: list | None = None, room_id: str | None = None) -> SessionRoom:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("A session room needs a name")
        if room_id is not None:
            room = self._rooms.get(room_id)
        else:
            matches = self.rooms_named(cleaned)
            if len(matches) > 1:
                raise ValueError("Room name is ambiguous; supply room_id")
            room = matches[0] if matches else None
        if room is None:
            room = SessionRoom(name=cleaned, room_id=room_id or "Room-" + uuid4().hex)
            self._rooms[room.room_id] = room
        room.update(cleaned, description, exits, _session_items(items) if items is not None else None)
        for item in room.items:
            item.room_id = room.room_id
        self._exits.update((entry.exit_id, entry) for entry in room.exit_records)
        self._items.update((item.item_id, item) for item in room.items)
        return room

    def room_by_id(self, room_id: str) -> SessionRoom | None:
        return self._rooms.get(room_id)

    def exit_by_id(self, exit_id: str) -> RoomExit | None:
        return self._exits.get(exit_id)

    def item_by_id(self, item_id: str) -> SessionItem | None:
        return self._items.get(item_id)

    def rooms_named(self, name: str) -> list[SessionRoom]:
        return [room for room in self._rooms.values() if room.name.lower() == name.strip().lower()]

    def room_named(self, name: str) -> SessionRoom | None:
        matches = self.rooms_named(name)
        return matches[0] if len(matches) == 1 else None

    def rooms(self) -> list[SessionRoom]:
        return sorted(self._rooms.values(), key=lambda room: room.name.lower())

    def current_beings(self) -> list[SessionBeing]:
        if not self.session.room.current:
            return []
        return [self._beings[key] for key in self.session.room.occupant_ids if key in self._beings]

    def resolve_current_being(self, target: str) -> SessionBeing | None:
        words = target.strip().lower().split()
        matches = [being for being in self.current_beings() if words and all(word in being.name.lower().split() for word in words)]
        return matches[0] if len(matches) == 1 else None

    def observe_room(self, name: str, *, description: str | None = None, exits: list[str] | None = None, beings: list[SessionBeing] | None = None, items: list | None = None, room_id: str | None = None, new_visit: bool = False, connect_from: str = "", direction: str = "", replace_presence: bool = True) -> SessionRoom:
        visit = self.session.room
        if room_id is None:
            same_visit = not new_visit and visit.room_id and visit.name.lower() == name.strip().lower()
            room_id = visit.room_id if same_visit else "Room-" + uuid4().hex
        previous = self.current_beings() if visit.room_id == room_id and not new_visit else []
        room = self.remember_room(name, description=description, exits=exits, room_id=room_id)
        visit.observe(room.name, room.exits, room_id=room.room_id, new_visit=new_visit)
        self.session.look_unread = False
        if beings is not None:
            old_counts = Counter((being.kind, being.name.lower()) for being in previous)
            new_counts = Counter((being.kind, being.name.lower()) for being in beings)
            occupants = [] if replace_presence else list(visit.occupant_ids)
            for incoming in beings:
                key = (incoming.kind, incoming.name.lower())
                prior = next((being for being in previous if (being.kind, being.name.lower()) == key), None)
                if incoming.provisional and old_counts[key] == new_counts[key] == 1:
                    being = prior
                    if being.auras != incoming.auras or incoming.aggressive is True:
                        visit.fresh.discard(being.being_id)
                    being.observe(incoming.name, incoming.kind, room.name, room.room_id, incoming.auras, incoming.aggressive, incoming.agentic)
                    incoming.being_id = being.being_id
                else:
                    being = incoming
                    being.room_id = room.room_id
                    being.room_name = room.name
                self._beings[being.being_id] = being
                if being.being_id not in occupants:
                    occupants.append(being.being_id)
            visit.occupant_ids = occupants
            if replace_presence:
                visit.fresh.intersection_update(occupants)
                self.session.combat.retain_present(set(occupants))
                visit.presence_complete = True
        if items is not None:
            incoming_items = _session_items(items)
            old_counts = Counter((item.line or item.name, item.source) for item in room.items)
            new_counts = Counter((item.line or item.name, item.source) for item in incoming_items)
            for item in incoming_items:
                key = (item.line or item.name, item.source)
                if old_counts[key] == new_counts[key] == 1:
                    previous_item = next(old for old in room.items if (old.line or old.name, old.source) == key)
                    item.item_id = previous_item.item_id
                    if previous_item.keyword_known and not item.keyword_known:
                        item.name = previous_item.name
                        item.keyword_known = True
            room.update(room.name, items=incoming_items)
            for item in room.items:
                item.room_id = room.room_id
            self._items.update((item.item_id, item) for item in room.items)
        if connect_from and direction:
            origin = self.room_by_id(connect_from)
            if origin is not None:
                for entry in origin.exit_records:
                    if entry.direction == direction:
                        entry.note_destination(room.room_id)
        return room

    def apply_room_items(self, room_id: str, revision: int, items: list) -> bool:
        visit = self.session.room
        room = self.room_by_id(room_id)
        if room is None or not visit.current or visit.room_id != room_id or visit.revision != revision:
            return False
        enriched = _session_items(items)
        raw_counts = Counter(item.line for item in room.items if item.source == "object")
        for line, count in raw_counts.items():
            offered = sum(item.line == line for item in enriched)
            if offered and offered != count:
                enriched = [item for item in enriched if item.line != line]
        for item in enriched:
            matching = [old for old in room.items if old.line and old.line == item.line]
            if len(matching) == 1 and sum(other.line == item.line for other in enriched) == 1:
                item.item_id = matching[0].item_id
                if not item.source:
                    item.source = matching[0].source
        for line in raw_counts:
            if not any(item.line == line for item in enriched):
                enriched.extend(item for item in room.items if item.source == "object" and item.line == line)
        room.update(room.name, items=enriched)
        for item in room.items:
            item.room_id = room.room_id
        self._items.update((item.item_id, item) for item in room.items)
        visit.revision += 1
        return True

    def remember_command(self, name: str, *, category: str = "", help_text: str = "") -> KnownCommand:
        """Update cached descriptions. This never changes session availability."""
        return self.command_knowledge.remember(name, category=category, help_text=help_text)

    def observe_commands(self, names: list[str]) -> list[KnownCommand]:
        """Replace availability from a full server list, preserving description history."""
        observed = [KnownCommand(name) for name in names]
        ordered = CommandList()
        for command in observed:
            previous = self.command_knowledge.named(command.name)
            ordered.remember(command.name, category=previous.category if previous else "", help_text=previous.help_text if previous else "")
        self.command_knowledge.replace(ordered.merged_with(self.command_knowledge).records())
        self.session.observe_commands([command.name for command in observed])
        return [self.command_knowledge.named(command.name) for command in observed]

    def command_named(self, name: str) -> KnownCommand | None:
        return self.command_knowledge.named(name)

    def commands(self) -> list[KnownCommand]:
        """The legacy description view; use session.command_available for permission."""
        return self.command_knowledge.records()

    def replace_commands(self, commands: list[KnownCommand]) -> None:
        """Restore/replace descriptions only, without granting execution authority."""
        self.command_knowledge.replace(commands)

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

    def remember_consider(self, target: str, lines: list[str], *, kind: str, agentic: bool = False, being_id: str | None = None, create_subject: bool = True) -> ConsiderOpponent:
        if kind not in _KINDS:
            raise ValueError(f"Consider kind must be player, mobile, or npc, got {kind}")
        reading = parse_consider(target, lines, kind="agentic" if agentic and kind == "player" else kind)
        self._considers[reading.target.lower()] = reading
        if reading.subject and reading.subject.lower() != reading.target.lower():
            self._considers[reading.subject.lower()] = reading
        if being_id is not None:
            self._considers["id:" + being_id] = reading
        if reading.estimated and being_id is None and create_subject:
            if len(self.beings_named(reading.subject)) <= 1:
                self._remember_subject(reading, agentic=agentic)
        return reading

    def being_by_id(self, being_id: str) -> SessionBeing | None:
        return self._beings.get(being_id)

    def beings_named(self, name: str) -> list[SessionBeing]:
        return [being for being in self._beings.values() if being.name.lower() == name.strip().lower()]

    def being_named(self, name: str) -> SessionBeing | None:
        matches = self.beings_named(name)
        return matches[0] if len(matches) == 1 else None

    def consider_for_id(self, being_id: str) -> ConsiderOpponent | None:
        return self._considers.get("id:" + being_id)

    def consider_for(self, name: str) -> ConsiderOpponent | None:
        if len(self.beings_named(name)) > 1:
            return None
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
        return {"session": self.session.to_review(), "players": [asdict(being) for being in _by_name(self.players())], "agentic_players": [asdict(being) for being in _by_name(self.agentic_players())], "mobiles": [asdict(being) for being in _by_name(self.mobiles())], "npcs": [asdict(being) for being in _by_name(self.npcs())], "aggressive_mobiles": [asdict(being) for being in _by_name(self.aggressive_mobiles())], "rooms": [room.to_review() for room in self.rooms()], "room_exits": [asdict(entry) for entry in self._exits.values()], "encounter_considers": {key[3:]: asdict(reading) for key, reading in self._considers.items() if key.startswith("id:")}, "items": [asdict(item) for item in self._items.values()], "commands": [asdict(command) for command in self.commands()], "considers": [asdict(reading) for reading in _by_target(self.considers())], "conversations": [asdict(conversation) for conversation in self.conversations()]}

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
        review = self.to_review()
        for key in ("players", "agentic_players", "mobiles", "npcs", "aggressive_mobiles"):
            review[key] = [being.to_legacy() for being in _by_name(getattr(self, key)())]
        review["rooms"] = [room.to_legacy() for room in self.rooms()]
        for key, value in review.items():
            if key in {"session", "room_exits", "items", "encounter_considers"}:
                continue
            document[SharedUtil.snake_to_camel(key)] = SharedUtil.camel_keys(value)
        return document

    @classmethod
    def from_collection(cls, document: dict) -> "WorkingMemory":
        """Restore one Memories document. `savedAt` and `id` are ignored."""
        if not isinstance(document, dict):
            raise TypeError("Working memory document must be an object")
        payload = SharedUtil.snake_tree(document)
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
            if isinstance(item, dict) and str(item.get("name", "")).strip() and not memory.beings_named(str(item.get("name"))):
                memory.note_aggressive(str(item.get("name")), room_name=str(item.get("room_name", "") or ""))
        for item in payload.get("rooms") or []:
            if isinstance(item, dict) and str(item.get("name", "")).strip():
                memory.remember_room(str(item.get("name")), description=str(item.get("description", "") or ""), exits=[str(exit_name) for exit_name in item.get("exits") or []], items=[dict(entry, keyword_known=False) if isinstance(entry, dict) else entry for entry in item["items"]] if isinstance(item.get("items"), list) else None, room_id="Room-" + uuid4().hex)
        memory.command_knowledge = CommandList.from_json([item for item in payload.get("commands") or [] if isinstance(item, dict) and str(item.get("name", "")).strip()])
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
        destination = Path(str(path).strip()) if path is not None else SharedUtil.default_collection_path()
        documents = SharedUtil.read_collection(destination)
        SharedUtil.write_collection(destination, _upsert_agent(documents, document))
        return str(destination)

    def _remember_subject(self, reading: ConsiderOpponent, *, agentic: bool) -> None:
        if reading.kind == "agentic":
            self.remember_player(reading.subject, agentic=True)
        elif reading.kind == "player":
            self.remember_player(reading.subject, agentic=agentic)
        elif reading.kind == "mobile":
            self.remember_mobile(reading.subject)
        else:
            self.remember_npc(reading.subject)

    def _upsert(self, name: str, kind: str, room_name: str, auras: list[str] | None = None, being_id: str | None = None, room_id: str = "") -> SessionBeing:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("A session being needs a name")
        if being_id is not None:
            being = self._beings.get(being_id)
        else:
            matches = self.beings_named(cleaned)
            if len(matches) > 1:
                raise ValueError("Being name is ambiguous; supply being_id")
            being = matches[0] if matches else None
        if being is None:
            being = SessionBeing(cleaned, kind, being_id=being_id or "Being-" + uuid4().hex)
            self._beings[being.being_id] = being
        being.observe(cleaned, kind, room_name, room_id, auras)
        return being


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
        memory.remember_player(name, agentic=agentic or bool(item.get("agentic")), room_name=room_name, auras=aura_list, being_id="Being-" + uuid4().hex)
    elif kind == "mobile":
        memory.remember_mobile(name, room_name=room_name, aggressive=bool(item.get("aggressive")), auras=aura_list, being_id="Being-" + uuid4().hex)
    else:
        memory.remember_npc(name, room_name=room_name, auras=aura_list, being_id="Being-" + uuid4().hex)


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
    reading = memory.remember_consider(target, text.splitlines(), kind=kind, agentic=agentic)
    memory._considers["legacy:" + uuid4().hex] = reading


def _session_items(items) -> list[SessionItem]:
    """Keep distinct item sightings, including duplicate look keywords."""
    stored: list[SessionItem] = []
    if not isinstance(items, list):
        return stored
    for item in items:
        session_item = _session_item(item)
        if session_item is None:
            continue
        stored.append(session_item)
    return stored


def _session_item(item) -> SessionItem | None:
    if isinstance(item, SessionItem):
        name, line, source = item.name, item.line, item.source
    elif isinstance(item, dict):
        name, line, source = item.get("name", ""), item.get("line", ""), item.get("source", "")
    else:
        return None
    cleaned = str(name or "").strip().lower()
    if not cleaned:
        return None
    identifier = item.item_id if isinstance(item, SessionItem) else "Item-" + uuid4().hex
    keyword_known = item.keyword_known if isinstance(item, SessionItem) else bool(item.get("keyword_known", item.get("keywordKnown", True)))
    provisional = item.provisional if isinstance(item, SessionItem) else True
    room_id = item.room_id if isinstance(item, SessionItem) else ""
    return SessionItem(name=cleaned, line=str(line or "").strip(), source=str(source or "").strip().lower(), item_id=identifier, keyword_known=keyword_known, provisional=provisional, room_id=room_id)


def _conversation_key(conversation: Conversation) -> tuple[str, str, str]:
    return conversation.topic.lower(), conversation.location, conversation.location_name.lower()


def _by_name(beings: list[SessionBeing]) -> list[SessionBeing]:
    return sorted(beings, key=lambda being: being.name.lower())


def _by_target(readings: list[ConsiderOpponent]) -> list[ConsiderOpponent]:
    return sorted(readings, key=lambda reading: reading.target.lower())
