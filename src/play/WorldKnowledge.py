from dataclasses import dataclass, field
from typing import Any

from util.GenericUtil import GenericUtil


@dataclass
class HelpArticle:
    """One topic the help prompt extracted from a help page."""

    keyword: str
    text: str


@dataclass
class HelpTopic:
    command: str
    keyword: str
    text: str
    raw: str
    missing: bool = False
    topics: list[HelpArticle] = field(default_factory=list)


@dataclass
class AreaRecord:
    name: str
    author: str = ""
    level_range: str = ""


@dataclass
class PlayerRecord:
    name: str
    level: int
    race: str
    character_class: str
    title: str = ""
    agentic: bool = False
    self_character: bool = False
    room_name: str = ""
    flags: str = ""
    auras: list[str] = field(default_factory=list)


@dataclass
class BeingRecord:
    name: str
    kind: str
    pose: str
    room_name: str
    detail: str = ""
    auras: list[str] = field(default_factory=list)


@dataclass
class RoomSnapshot:
    name: str = ""
    description: str = ""
    exits: list[str] = field(default_factory=list)
    item_lines: list[str] = field(default_factory=list)


def _key(value: str) -> str:
    return value.strip().lower()


class WorldKnowledge:
    """What the agent has learned from the game since login."""

    def __init__(self):
        self.login_lines: list[str] = []
        self.help_topics: dict[str, HelpTopic] = {}
        self.areas: dict[str, AreaRecord] = {}
        self.mobiles: dict[str, BeingRecord] = {}
        self.npcs: dict[str, BeingRecord] = {}
        self.players: dict[str, PlayerRecord] = {}
        self.room: RoomSnapshot | None = None

    def remember_help(self, topic: HelpTopic) -> None:
        self.help_topics[_key(topic.command)] = topic

    def remember_area(self, area: AreaRecord) -> None:
        self.areas[_key(area.name)] = area

    def remember_player(self, player: PlayerRecord) -> None:
        self.players[_key(player.name)] = player

    def remember_mobile(self, being: BeingRecord) -> None:
        self.mobiles[self._being_key(being)] = being

    def remember_npc(self, being: BeingRecord) -> None:
        self.npcs[self._being_key(being)] = being

    def help_for(self, command: str) -> HelpTopic | None:
        return self.help_topics.get(_key(command))

    def area_named(self, name: str) -> AreaRecord | None:
        return self.areas.get(_key(name))

    def player_named(self, name: str) -> PlayerRecord | None:
        return self.players.get(_key(name))

    def note_player_seen(self, name: str, room_name: str) -> None:
        player = self._match_player(name)
        if player is not None and room_name:
            player.room_name = room_name

    def _match_player(self, display_name: str) -> PlayerRecord | None:
        target = _key(display_name)
        first = target.split()[0] if target else ""
        for player in self.players.values():
            player_name = _key(player.name)
            if player_name == target or player_name == first:
                return player
        return None

    @staticmethod
    def _being_key(being: BeingRecord) -> str:
        return f"{_key(being.room_name)}|{_key(being.name)}"

    def to_document(self, *, character_id: str, character_name: str, agent_name: str) -> dict[str, Any]:
        """CamelCase snapshot for PUT /api/v1/agent-knowledge/{characterId}."""
        room = None
        if self.room is not None:
            room = {
                "name": self.room.name,
                "description": self.room.description,
                "exits": list(self.room.exits),
                "itemLines": list(self.room.item_lines),
            }
        return {
            "characterId": character_id,
            "characterName": character_name,
            "agentName": agent_name,
            "loginLines": list(self.login_lines),
            "helpTopics": [
                {
                    "command": topic.command,
                    "keyword": topic.keyword,
                    "text": topic.text,
                    "raw": topic.raw,
                    "missing": topic.missing,
                    "topics": [
                        {"keyword": article.keyword, "text": article.text}
                        for article in topic.topics
                    ],
                }
                for topic in _sorted_values(self.help_topics)
            ],
            "areas": [
                {"name": area.name, "author": area.author, "levelRange": area.level_range}
                for area in _sorted_values(self.areas)
            ],
            "mobiles": [_being_document(being) for being in _sorted_beings(self.mobiles)],
            "npcs": [_being_document(being) for being in _sorted_beings(self.npcs)],
            "players": [_player_document(player) for player in _sorted_values(self.players)],
            "room": room,
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "WorldKnowledge":
        payload = _snake_tree(document or {})
        knowledge = cls()
        knowledge.login_lines = [str(line) for line in payload.get("login_lines") or []]
        for item in payload.get("help_topics") or []:
            if isinstance(item, dict):
                knowledge.remember_help(HelpTopic(
                    command=str(item.get("command", "")),
                    keyword=str(item.get("keyword", "")),
                    text=str(item.get("text", "")),
                    raw=str(item.get("raw", "")),
                    missing=bool(item.get("missing", False)),
                    topics=[
                        HelpArticle(keyword=str(article.get("keyword", "")), text=str(article.get("text", "")))
                        for article in item.get("topics") or []
                        if isinstance(article, dict)
                    ],
                ))
        for item in payload.get("areas") or []:
            if isinstance(item, dict) and str(item.get("name", "")).strip():
                knowledge.remember_area(AreaRecord(
                    name=str(item.get("name", "")),
                    author=str(item.get("author", "") or ""),
                    level_range=str(item.get("level_range", "") or ""),
                ))
        for item in payload.get("mobiles") or []:
            being = _being_from(item, "mobile")
            if being is not None:
                knowledge.remember_mobile(being)
        for item in payload.get("npcs") or []:
            being = _being_from(item, "npc")
            if being is not None:
                knowledge.remember_npc(being)
        for item in payload.get("players") or []:
            player = _player_from(item)
            if player is not None:
                knowledge.remember_player(player)
        room = payload.get("room")
        if isinstance(room, dict):
            knowledge.room = RoomSnapshot(
                name=str(room.get("name", "") or ""),
                description=str(room.get("description", "") or ""),
                exits=[str(exit_name) for exit_name in room.get("exits") or []],
                item_lines=[str(line) for line in room.get("item_lines") or []],
            )
        return knowledge


def _sorted_values(records: dict):
    return [records[key] for key in sorted(records)]


def _sorted_beings(records: dict[str, BeingRecord]) -> list[BeingRecord]:
    return sorted(records.values(), key=lambda being: (_key(being.room_name), _key(being.name)))


def _being_document(being: BeingRecord) -> dict[str, str]:
    return {
        "name": being.name,
        "kind": being.kind,
        "pose": being.pose,
        "roomName": being.room_name,
        "detail": being.detail,
    }


def _player_document(player: PlayerRecord) -> dict[str, Any]:
    return {
        "name": player.name,
        "level": player.level,
        "race": player.race,
        "characterClass": player.character_class,
        "title": player.title,
        "agentic": player.agentic,
        "selfCharacter": player.self_character,
        "roomName": player.room_name,
        "flags": player.flags,
    }


def _being_from(item: Any, default_kind: str) -> BeingRecord | None:
    if not isinstance(item, dict) or not str(item.get("name", "")).strip():
        return None
    return BeingRecord(
        name=str(item.get("name", "")),
        kind=str(item.get("kind", default_kind) or default_kind),
        pose=str(item.get("pose", "") or ""),
        room_name=str(item.get("room_name", "") or ""),
        detail=str(item.get("detail", "") or ""),
    )


def _player_from(item: Any) -> PlayerRecord | None:
    if not isinstance(item, dict) or not str(item.get("name", "")).strip():
        return None
    return PlayerRecord(
        name=str(item.get("name", "")),
        level=int(item.get("level", 0) or 0),
        race=str(item.get("race", "") or ""),
        character_class=str(item.get("character_class", "") or ""),
        title=str(item.get("title", "") or ""),
        agentic=bool(item.get("agentic", False)),
        self_character=bool(item.get("self_character", False)),
        room_name=str(item.get("room_name", "") or ""),
        flags=str(item.get("flags", "") or ""),
    )


def _snake_tree(value: Any) -> Any:
    if isinstance(value, dict):
        converted = GenericUtil.camel_to_snake_case(value)
        return {key: _snake_tree(item) for key, item in converted.items()}
    if isinstance(value, list):
        return [_snake_tree(item) for item in value]
    return value
