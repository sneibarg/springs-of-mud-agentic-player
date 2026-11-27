from dataclasses import asdict
import re

from play.HelpReader import parse_command_names, parse_help
from play.MemoryObservation import apply_room_observation, observe_line, parse_score
from play.WorldReader import parse_areas, parse_room, parse_who

_DIRECTIONS = {"north", "south", "east", "west", "up", "down"}
_MOVEMENT_REFUSAL = re.compile(r"cannot go|can['’]t go|couldn['’]t escape|could not escape|is closed|is locked|too exhausted|not enough movement", re.IGNORECASE)


class ObservationPipeline:
    """Fold all server observations and queue immutable evidence on the drive thread."""

    def __init__(self, memory, knowledge, *, agent_character_names=(), self_character=""):
        self.memory = memory
        self.knowledge = knowledge
        self.agent_character_names = set(agent_character_names) or {player.name for player in knowledge.players.values() if player.agentic}
        self.self_character = self_character or next((player.name for player in knowledge.players.values() if player.self_character), "")

    def receive(self, lines: list[str], command: str, *, origin: str, prompt: str = "", allow_partial_room: bool = False, complete: bool = True):
        journal = self.memory.session.evidence
        origin_room_id = self.memory.session.room.movement_origin_id
        raw = journal.append("server_response", origin=origin, command=command, lines=lines, payload={"prompt": prompt, "complete": complete})
        if not complete:
            return raw
        if prompt:
            self.memory.session.last_prompt = prompt
        kind = "observation"
        payload = {}
        if command == "login":
            self.knowledge.login_lines = list(lines)
            kind = "login"
        elif command == "commands":
            self.memory.observe_commands(parse_command_names(lines))
            kind = "commands"
            payload = {"available": [record.name for record in self.memory.session.available_commands.records()], "commands": [asdict(record) for record in self.memory.command_knowledge.records()]}
        elif command.startswith("help "):
            name = command.partition(" ")[2]
            topic = parse_help(name, lines)
            self.knowledge.remember_help(topic)
            self.knowledge.remember_command(name, help_text=topic.text)
            kind = "help"
            payload = asdict(topic)
        elif command == "help":
            kind = "help_index"
        elif command == "who":
            players = parse_who(lines, self.agent_character_names, self.self_character)
            for player in players:
                self.knowledge.remember_player(player)
            kind = "players"
            payload = {"players": [asdict(player) for player in players]}
        if command not in {"login", "commands", "help", "who"} and not command.startswith("help "):
            self._fold(lines, command)
        if command == "look" and allow_partial_room and not any(line.strip().lower().startswith("obvious exits") for line in lines):
            self._observe_room(lines, allow_partial=True)
            self.memory.session.room.current = False
            self.memory.session.room.presence_complete = False
        if command == "areas":
            kind = "listed_areas"
            payload = {"areas": [asdict(area) for area in parse_areas(lines)]}
        if kind == "observation" and (command == "look" or any(line.strip().lower().startswith("obvious exits") for line in lines)):
            kind = "room"
            visit = self.memory.session.room
            room = self.memory.room_by_id(visit.room_id)
            payload = {"visit": visit.to_review(), "room": room.to_review() if room is not None else None, "beings": [asdict(being) for being in self.memory.current_beings()], "complete": parse_room(lines, list(self.knowledge.players.values())).complete}
        if kind == "observation":
            payload = {"visit": self.memory.session.room.to_review(), "combat": self.memory.session.combat.to_review(), "progress": asdict(self.memory.session.progress)}
            pending = self.memory.session.pending_action
            if command.startswith("consider "):
                payload["target_id"] = pending.target_id if pending is not None else ""
        score = parse_score(lines) if kind == "observation" else None
        if score is not None:
            kind = "score"
            payload["score"] = asdict(score)
        if command.startswith("consider "):
            kind = "consider"
            pending = self.memory.session.pending_action
            target = self.memory.being_by_id(pending.target_id) if pending is not None and pending.target_id else self.memory.resolve_current_being(command.partition(" ")[2])
            reading = self.memory.consider_for_id(target.being_id) if target is not None else None
            payload["target_id"] = target.being_id if target is not None else ""
            payload["reading"] = asdict(reading) if reading is not None else None
        if kind in {"room", "consider", "observation", "score"}:
            # Capture the original edge after confirmed movement/refusal, not just the destination.
            origin_room = self.memory.room_by_id(origin_room_id) if origin_room_id else None
            payload["room_updates"] = [origin_room.to_review()] if origin_room is not None else []
            beings = self.memory.current_beings()
            payload["beings"] = [asdict(being) for being in beings]
            payload["fresh_considers"] = {being.being_id: reading.outlook for being in beings if being.being_id in self.memory.session.room.fresh and (reading := self.memory.consider_for_id(being.being_id)) is not None}
        record = journal.append(kind, origin=origin, command=command, source_ids=(raw.observation_id,), payload=payload, transferable=kind not in {"login", "help_index"})
        progress = self.memory.session.bootstrap
        if origin == "bootstrap" and progress.status == "collecting" and record.transferable:
            progress.require(record.observation_id)
        return record

    def enrich(self, name: str, response: str, *, source_id: str, origin: str = "bootstrap", error: str = "", applied: bool = False, payload: dict | None = None):
        details = {"error": error, "applied": applied, "commands": [asdict(command) for command in self.knowledge.command_records()]}
        if name.startswith("help "):
            topic = self.knowledge.help_for(name.partition(" ")[2])
            details["help"] = asdict(topic) if topic is not None else None
        details.update(payload or {})
        record = self.memory.session.evidence.append("model_enrichment", origin=origin, source="model", command=name, lines=(response,), source_ids=(source_id,), payload=details, transferable=applied)
        if applied and self.memory.session.bootstrap.status == "collecting" and origin == "bootstrap":
            self.memory.session.bootstrap.require(record.observation_id)
        return record

    def _fold(self, lines: list[str], command: str) -> None:
        verb = command.partition(" ")[0]
        full_room = any(line.strip().lower().startswith("obvious exits") for line in lines)
        refused = bool(_MOVEMENT_REFUSAL.search(lines[0] if full_room and lines else "\n".join(lines)))
        visit = self.memory.session.room
        if refused and verb in _DIRECTIONS | {"flee", "recall"}:
            if verb in _DIRECTIONS:
                room = self.memory.room_by_id(visit.movement_origin_id)
                if room is not None:
                    for entry in room.exit_records:
                        if entry.direction == verb:
                            if any("is closed" in line.lower() or "is locked" in line.lower() for line in lines):
                                entry.requires_open = True
                            if any("is locked" in line.lower() for line in lines):
                                entry.requires_unlock = True
            visit.refuse_movement()
        if full_room:
            origin = visit.movement_origin_id if verb in _DIRECTIONS and not refused else ""
            self._observe_room(lines, new_visit=bool(visit.movement_origin_id), connect_from=origin, direction=verb if origin else "")
        else:
            if verb == "look":
                visit.current = False
                visit.presence_complete = False
                visit.fresh.clear()
            for line in lines:
                being = observe_line(self.memory, line, room_name=visit.name)
                if being is not None:
                    self.memory.session.combat.note_threat(being.being_id)
        self._observe_score(lines)
        if command == "areas":
            found = parse_areas(lines)
            for area in found:
                self.knowledge.remember_area(area)
            if not found:
                self.memory.session.areas_unread = True
        if command.startswith("consider "):
            target = command.split(" ", 1)[1]
            pending = self.memory.session.pending_action
            being = self.memory.being_by_id(pending.target_id) if pending is not None and pending.target_id else self.memory.resolve_current_being(target)
            reading = self.memory.remember_consider(target, lines, kind=being.kind if being is not None else "mobile", being_id=being.being_id if being is not None else None, create_subject=False)
            if being is not None and being in self.memory.current_beings():
                self.memory.session.room.fresh.discard(being.being_id)
                if any(line.strip().lower() == "they're not here." for line in lines):
                    self.memory.session.room.occupant_ids.remove(being.being_id)
                    self.memory.session.room.revision += 1
                    self.memory.session.combat.retain_present(set(self.memory.session.room.occupant_ids))
                if reading.estimated:
                    self.memory.session.room.note_consider(being.being_id)

    def _observe_room(self, lines: list[str], *, new_visit: bool = False, connect_from: str = "", direction: str = "", allow_partial: bool = False) -> None:
        first_line = next((line.strip() for line in lines if line.strip()), "")
        if first_line.lower().startswith("obvious exits"):
            self.memory.session.room.current = False
            return
        observation = parse_room(lines, list(self.knowledge.players.values()))
        if observation.complete or allow_partial:
            apply_room_observation(self.memory, observation, new_visit=new_visit, connect_from=connect_from, direction=direction)
            if observation.room.name or observation.room.description or observation.room.exits:
                self.knowledge.room = observation.room
            for being in observation.mobiles:
                self.knowledge.remember_mobile(being)
            for being in observation.npcs:
                self.knowledge.remember_npc(being)
            for player in observation.players_present:
                self.knowledge.note_player_seen(player.name, observation.room.name)

    def _observe_score(self, lines: list[str]) -> None:
        score = parse_score(lines)
        if score is not None:
            self.memory.session.note_score(score.level, score.hours, score.exp_to_level, score.hit, score.max_hit, score.position)

