import re
from dataclasses import dataclass

from memory.WorkingMemory import SessionBeing, WorkingMemory
from play.WorldKnowledge import WorldKnowledge
from play.WorldReader import RoomObservation, split_look_prefixes


_FIGHTING_YOU = re.compile(r"^(?P<name>.+) is here, fighting YOU!$", re.IGNORECASE)
_LEVEL = re.compile(r"^You are .+?, level (?P<level>\d+), (?P<age>\d+) years old \((?P<hours>\d+) hours\)\.$")
_VITALS = re.compile(r"^You have (?P<hit>\d+)/(?P<max_hit>\d+) hit, \d+/\d+ mana, \d+/\d+ movement\.$")
_EXP = re.compile(r"^You need (?P<exp>\d+) exp to level\.$")
_POSITION = re.compile(r"^You are (?P<position>standing|resting|sitting|sleeping|fighting)\.$")
_POSITION_LINES = {"You are DEAD!!": "dead", "You are mortally wounded.": "mortally wounded", "You are incapacitated.": "incapacitated", "You are stunned.": "stunned"}


@dataclass(frozen=True)
class ScoreReading:
    level: int
    hours: int
    exp_to_level: int
    hit: int | None
    max_hit: int | None
    position: str


def parse_score(lines: list[str]) -> ScoreReading | None:
    level = hours = hit = max_hit = exp = None
    position = ""
    for line in lines:
        stripped = line.strip()
        level_match = _LEVEL.match(stripped)
        if level_match is not None:
            level = int(level_match.group("level"))
            hours = int(level_match.group("hours"))
        vitals = _VITALS.match(stripped)
        if vitals is not None:
            hit = int(vitals.group("hit"))
            max_hit = int(vitals.group("max_hit"))
        exp_match = _EXP.match(stripped)
        if exp_match is not None:
            exp = int(exp_match.group("exp"))
        position_match = _POSITION.match(stripped)
        if position_match is not None:
            position = position_match.group("position")
        elif stripped in _POSITION_LINES:
            position = _POSITION_LINES[stripped]
    if level is None or hours is None or exp is None:
        return None
    return ScoreReading(level, hours, exp, hit, max_hit, position)


def observe_line(memory: WorkingMemory, line: str, *, room_name: str = "") -> SessionBeing | None:
    """A partial fighting line identifies a target only when unambiguous."""
    auras, rest = split_look_prefixes(line)
    match = _FIGHTING_YOU.match(rest)
    if match is None:
        return None
    name = match.group("name").strip()
    visit = memory.session.room
    if visit.room_id and visit.current:
        matches = [being for being in memory.current_beings() if being.name.lower() == name.lower()]
        if len(matches) > 1:
            memory.session.combat.fighting = True
            memory.session.combat.unidentified_threat = True
            return None
        identifier = matches[0].being_id if matches else SessionBeing(name, "mobile").being_id
        if matches:
            being = matches[0]
            being.observe(name, being.kind, visit.name, visit.room_id, aggressive=True)
        else:
            being = memory.note_aggressive(name, room_name=visit.name, room_id=visit.room_id, being_id=identifier)
        being.auras = list(auras)
        visit.fresh.discard(being.being_id)
        if identifier not in visit.occupant_ids:
            visit.occupant_ids.append(identifier)
        return being
    if visit.room_id or len(memory.beings_named(name)) > 1:
        return memory.remember_mobile(name, aggressive=True, auras=auras, being_id=SessionBeing(name, "mobile").being_id)
    return memory.remember_mobile(name, room_name=room_name, aggressive=True, auras=auras)


def apply_room_observation(memory: WorkingMemory, observation: RoomObservation, *, new_visit: bool = False, connect_from: str = "", direction: str = "") -> None:
    """Apply one parsed observation without turning missing sections into emptiness."""
    snapshot = observation.room
    if not snapshot.name.strip():
        return
    beings = []
    for record in observation.mobiles + observation.npcs:
        fighting_you = record.pose == "fighting" and record.detail.upper().startswith("YOU")
        beings.append(SessionBeing(record.name, record.kind, aggressive=True if fighting_you else None, auras=list(record.auras)))
    for player in observation.players_present:
        if not player.self_character:
            beings.append(SessionBeing(player.name, "player", agentic=player.agentic, aggressive=True if player.name in observation.fighting_players else None, auras=list(player.auras)))
    items = [{"name": line, "line": line, "source": "object", "keyword_known": False} for line in snapshot.item_lines]
    memory.observe_room(snapshot.name, description=snapshot.description if observation.complete or snapshot.description else None, exits=snapshot.exits if observation.complete else None, beings=beings, items=items if observation.complete else None, new_visit=new_visit, connect_from=connect_from, direction=direction, replace_presence=observation.complete)
    for record, incoming in zip(observation.mobiles + observation.npcs, beings):
        if record.pose == "fighting":
            memory.session.room.fresh.discard(incoming.being_id)
    if observation.complete:
        memory.session.combat.unidentified_threat = False
    for incoming in beings:
        if incoming.aggressive is True:
            memory.session.combat.note_threat(incoming.being_id)
        elif observation.complete:
            memory.session.combat.threats.discard(incoming.being_id)


def absorb_world(memory: WorkingMemory, knowledge: WorldKnowledge) -> None:
    """Import legacy bootstrap facts without replacing an already observed live look."""
    for player in knowledge.players.values():
        if player.self_character or memory.beings_named(player.name):
            continue
        memory.remember_player(player.name, agentic=player.agentic, room_name=player.room_name or "", auras=list(player.auras))
    for record in list(knowledge.mobiles.values()) + list(knowledge.npcs.values()):
        if memory.beings_named(record.name):
            continue
        remember = memory.remember_mobile if record.kind == "mobile" else memory.remember_npc
        being = remember(record.name, room_name=record.room_name, auras=list(record.auras))
        if record.pose == "fighting" and record.detail.upper().startswith("YOU"):
            being.aggressive = True
    room = knowledge.room
    if room is not None and room.name.strip() and not memory.session.room.room_id:
        known = memory.room_named(room.name)
        room = memory.remember_room(room.name, description=room.description or "", exits=list(room.exits or []), room_id=known.room_id if known else None)
        memory.session.room.observe(room.name, room.exits, room_id=room.room_id)
