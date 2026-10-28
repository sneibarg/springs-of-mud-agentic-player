import re

from dataclasses import dataclass, field

from play.CommandChannel import CommandChannel, is_prompt
from play.WorldKnowledge import AreaRecord, BeingRecord, PlayerRecord, RoomSnapshot


_AREA_COLUMNS = 39
_AREA = re.compile(
    r"^(?:\[(?P<levels>[^\]]+)\]\s*)?(?:(?P<author>[^:\[]+):\s*)?(?P<name>\S.*?)\s*$"
)
_WHO = re.compile(
    r"^\[(?P<level>\d+)\s+(?P<race>\S+)\s+(?P<class_name>\S+)\]"
    r"(?P<flags>(?:\s+\([^)]+\))*)\s+"
    r"(?P<name>\S+)\s*(?P<title>.*)$"
)
_POSES = (
    (" is DEAD!!", "dead"),
    (" is mortally wounded.", "mortally wounded"),
    (" is incapacitated.", "incapacitated"),
    (" is lying here stunned.", "stunned"),
    (" is sleeping here.", "sleeping"),
    (" is resting here.", "resting"),
    (" is sitting here.", "sitting"),
    (" is here, fighting ", "fighting"),
    (" is here.", "here"),
)
_DIRECTIONS = {"north", "east", "south", "west", "up", "down"}
_ARTICLES = {"a", "an", "the", "some"}
_LOOK_PREFIX = re.compile(r"^\((?P<label>[^)\n]+)\)\s*")


@dataclass
class Presence:
    name: str
    pose: str
    detail: str = ""
    auras: list[str] = field(default_factory=list)


@dataclass
class RoomObservation:
    room: RoomSnapshot
    mobiles: list[BeingRecord] = field(default_factory=list)
    npcs: list[BeingRecord] = field(default_factory=list)
    players_present: list[PlayerRecord] = field(default_factory=list)


class WorldReader:
    """Turn areas, who, and look output into knowledge records."""

    def read_areas(self, channel: CommandChannel) -> list[AreaRecord]:
        return parse_areas(channel.exchange("areas"))

    def read_players(
        self,
        channel: CommandChannel,
        agent_character_names: set[str],
        self_character: str,
    ) -> list[PlayerRecord]:
        return parse_who(channel.exchange("who"), agent_character_names, self_character)

    def read_room(self, lines: list[str], players: list[PlayerRecord]) -> RoomObservation:
        return parse_room(lines, players)


def parse_areas(lines: list[str]) -> list[AreaRecord]:
    areas: list[AreaRecord] = []
    seen: set[str] = set()
    for line in lines:
        if is_prompt(line) or not line.strip():
            continue
        for chunk in _column_chunks(line, _AREA_COLUMNS):
            area = _parse_area_chunk(chunk)
            if area is None:
                continue
            key = area.name.lower()
            if key in seen:
                continue
            seen.add(key)
            areas.append(area)
    return areas


def parse_who(lines: list[str], agent_character_names: set[str], self_character: str) -> list[PlayerRecord]:
    agent_names = {name.strip().lower() for name in agent_character_names if name and name.strip()}
    self_name = self_character.strip().lower()
    players: list[PlayerRecord] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or is_prompt(stripped) or stripped.lower().startswith("players found"):
            continue
        match = _WHO.match(stripped)
        if match is None:
            continue
        name = match.group("name")
        players.append(
            PlayerRecord(
                name=name,
                level=int(match.group("level")),
                race=match.group("race"),
                character_class=match.group("class_name"),
                title=match.group("title").strip(),
                flags=match.group("flags").strip(),
                agentic=name.lower() in agent_names,
                self_character=name.lower() == self_name,
            )
        )
    return players


def parse_room(lines: list[str], players: list[PlayerRecord]) -> RoomObservation:
    exits: list[str] = []
    items: list[str] = []
    prose: list[str] = []
    presences: list[Presence] = []
    in_exits = False
    for line in lines:
        if is_prompt(line):
            continue
        stripped = line.strip()
        if stripped.lower().startswith("obvious exits"):
            in_exits = True
            continue
        presence = _parse_presence(stripped)
        if presence is not None:
            in_exits = False
            presences.append(presence)
            continue
        if in_exits:
            direction = _exit_direction(stripped)
            if direction is not None:
                exits.append(direction)
                continue
            in_exits = False
        if line.startswith("    ") and stripped:
            items.append(stripped)
            continue
        if stripped:
            prose.append(stripped)

    room = RoomSnapshot(
        name=prose[0] if prose else "",
        description="\n".join(prose[1:]) if len(prose) > 1 else "",
        exits=exits,
        item_lines=items,
    )
    observation = RoomObservation(room=room)
    for presence in presences:
        player = _match_player(presence.name, players)
        if player is not None:
            player.auras = list(presence.auras)
            observation.players_present.append(player)
            continue
        being = BeingRecord(
            name=presence.name,
            kind=_being_kind(presence.name),
            pose=presence.pose,
            room_name=room.name,
            detail=presence.detail,
            auras=list(presence.auras),
        )
        if being.kind == "npc":
            observation.npcs.append(being)
        else:
            observation.mobiles.append(being)
    return observation


def _column_chunks(line: str, width: int) -> list[str]:
    chunks = []
    for start in range(0, len(line), width):
        chunk = line[start:start + width].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _parse_area_chunk(chunk: str) -> AreaRecord | None:
    match = _AREA.match(chunk.strip())
    if match is None:
        return None
    name = (match.group("name") or "").strip()
    if not name:
        return None
    author = (match.group("author") or "").strip()
    levels = (match.group("levels") or "").strip()
    return AreaRecord(name=name, author=author, level_range=levels)


def split_look_prefixes(line: str) -> tuple[list[str], str]:
    """Separate aura labels from the rest of a look line.

    The server prints `(White Aura)` and the other aura labels before the
    name. Other prefixes, such as `(Invis)` or `(Wizi)`, are not auras.
    """
    auras: list[str] = []
    rest = line.strip()
    while True:
        match = _LOOK_PREFIX.match(rest)
        if match is None:
            break
        label = match.group("label").strip()
        if label.lower().endswith(" aura"):
            auras.append(label)
        rest = rest[match.end():]
    return auras, rest


def _parse_presence(line: str) -> Presence | None:
    """Read one character line from look.

    The server prefixes auras such as `(White Aura)` and may use a mobile's
    long description: `A healer is here, selling spells.`
    """
    auras, stripped = split_look_prefixes(line)
    for suffix, pose in _POSES:
        if stripped.endswith(suffix) or (pose == "fighting" and suffix in stripped):
            name = stripped.split(suffix, 1)[0].strip()
            if not name:
                return None
            detail = ""
            if pose == "fighting":
                detail = stripped.split(suffix, 1)[1].strip()
            return Presence(name=name, pose=pose, detail=detail, auras=auras)
    marker = " is here,"
    if marker in stripped:
        name, _, detail = stripped.partition(marker)
        name = name.strip()
        if name:
            return Presence(name=name, pose="here", detail=detail.strip(), auras=auras)
    return None


def _exit_direction(line: str) -> str | None:
    if not line:
        return None
    token = line.split()[0].lower()
    if token in _DIRECTIONS:
        return token
    return None


def _match_player(display_name: str, players: list[PlayerRecord]) -> PlayerRecord | None:
    target = display_name.strip().lower()
    first = target.split()[0] if target else ""
    for player in players:
        player_name = player.name.strip().lower()
        if player_name == target or player_name == first:
            return player
    return None


def _being_kind(display_name: str) -> str:
    """Proper names are NPCs. Article-led descriptions are mobiles.

    This is the first classification rule. Players are removed before it runs.
    """
    token = display_name.strip().split()[0] if display_name.strip() else ""
    if not token or token.lower() in _ARTICLES or token[:1].islower():
        return "mobile"
    return "npc"
