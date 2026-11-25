import logging
import re

from net.rest.KmClient import KmError
from play.LevelGoal import LevelGoal
from play.LevelQuestion import LevelQuestion, MobileReading, clamp_notch
from play.PlayClock import PlayClock
from play.WorldReader import parse_areas, parse_room

logger = logging.getLogger(__name__)

_DIRECTIONS = {"north", "south", "east", "west", "up", "down"}
_REFUSED = {"quit", "delete", "murder", "steal", "password", "!"}
_TRAVEL_WHILE_FIGHTING = _DIRECTIONS | {"kill", "recall"}
_LEVEL = re.compile(r"^You are .+?, level (?P<level>\d+), (?P<age>\d+) years old \((?P<hours>\d+) hours\)\.$")
_VITALS = re.compile(r"^You have (?P<hit>\d+)/(?P<max_hit>\d+) hit, \d+/\d+ mana, \d+/\d+ movement\.$")
_EXP = re.compile(r"^You need (?P<exp>\d+) exp to level\.$")
_POSITION = re.compile(r"^You are (?P<position>standing|resting|sitting|sleeping|fighting)\.$")
_PROMPT_HIT = re.compile(r"<\s*(?P<hit>\d+)\s*hp\b", re.IGNORECASE)
_POSITION_LINES = {"You are DEAD!!": "dead", "You are mortally wounded.": "mortally wounded", "You are incapacitated.": "incapacitated", "You are stunned.": "stunned"}


class GameplayEngine:
    """One observe-decide-act step on the drive thread.

    Observe drains telnet lines and folds a score or a look into the clock.
    Decide asks som-nlp-service for one level question from the loaded KM
    library. Act sends the first catalog command that question licenses, or
    sends nothing. The next step sees the reply before it asks again.
    """

    def __init__(self, channel, memory, knowledge, km, *, goal: LevelGoal | None = None, room_current: bool = False, flee_hp: int = 20, clock: PlayClock | None = None):
        self.channel = channel
        self.memory = memory
        self.knowledge = knowledge
        self.km = km
        self.goal = goal
        self.flee_hp = flee_hp
        self.clock = clock if clock is not None else PlayClock()
        self.room_current = room_current
        self.room_name = ""
        self.room_exits: list[str] = []
        self._tried: set[str] = set()
        self._fresh: set[str] = set()
        self._engaged: set[str] = set()
        self._threats: set[str] = set()
        self._look_unread = False
        self._score_unread = False
        self._areas_unread = False
        if room_current:
            self._take_known_room()

    def step(self) -> str:
        """Drain, choose at most one command, and observe its reply. A wait returns an empty string."""
        self._observe(self.channel.drain(), "")
        if self.clock.score_count > 0:
            self.clock.score_steps += 1
        command = self._choose()
        if not command:
            return ""
        lines = self.channel.exchange(command)
        self._observe(lines, command)
        self._note_sent(command)
        logger.info("Play step sent %s.", command)
        return command

    def _choose(self) -> str:
        hit = self._prompt_hit()
        if self.clock.fighting and hit is not None and hit <= self.flee_hp and self._known("flee"):
            return "flee"
        if self._uninvited_threat():
            return self._leave()
        if not self.room_current and not self._look_unread and self._known("look"):
            return "look"
        if self.goal is None or self.km is None:
            return ""
        if self.clock.score_count == 0 and not self._score_unread and self._known("score"):
            return "score"
        if self.clock.score_count == 0:
            return ""
        return self._licensed_command()

    def _licensed_command(self) -> str:
        self.clock.prior_notch = clamp_notch(self.clock.prior_notch, self.goal.risk)
        question = LevelQuestion(self.goal, self.clock, self._readings(), self._untried(), areas_known=bool(self.knowledge.areas) or self._areas_unread, flee_hp=self.flee_hp)
        try:
            results = self.km.baseline(question.expressions())
        except KmError as exc:
            logger.warning("KM baseline was not answered: %s", exc)
            return ""
        try:
            decision = LevelQuestion.read(results)
        except ValueError as exc:
            logger.warning("KM baseline was not answered: %s", exc)
            return ""
        if decision.notch in {"cautious", "steady", "bold"}:
            self.clock.prior_notch = clamp_notch(decision.notch, self.goal.risk)
        if decision.cooldown is not None and decision.cooldown >= 0:
            self.clock.cooldown_steps = decision.cooldown
        for attempt in decision.attempts:
            command = self._accepted(attempt.command())
            if command:
                return command
        return ""

    def _accepted(self, command: str) -> str:
        verb = command.split(maxsplit=1)[0].lower()
        if verb in _REFUSED:
            return ""
        if self.clock.fighting and verb in _TRAVEL_WHILE_FIGHTING:
            return ""
        if not self._known(verb):
            return ""
        return command

    def _leave(self) -> str:
        for direction in self._untried():
            if self._known(direction):
                return direction
        if self._known("flee"):
            return "flee"
        return ""

    def _uninvited_threat(self) -> bool:
        return any(name not in self._engaged for name in self._threats)

    def _untried(self) -> list[str]:
        return [direction for direction in self.room_exits if direction not in self._tried]

    def _readings(self) -> list[MobileReading]:
        if not self.room_name:
            return []
        found = []
        for being in self.memory.mobiles():
            if being.room_name.strip().lower() != self.room_name.lower():
                continue
            consider = self.memory.consider_for(being.name)
            fresh = being.name.lower() in self._fresh or (consider is not None and consider.subject.lower() in self._fresh)
            outlook = ""
            if fresh and consider is not None and consider.outlook in {"safe", "even", "risky", "fatal", "unknown"}:
                outlook = consider.outlook
            found.append(MobileReading(name=being.name, outlook=outlook, fresh=bool(outlook) and outlook != "unknown"))
        found.sort(key=lambda reading: reading.name.lower())
        return found

    def _observe(self, lines: list[str], command: str) -> None:
        room_name = self.room_name
        for line in lines:
            being = self.memory.observe_line(line, room_name=room_name)
            if being is not None:
                self.clock.fighting = True
                if being.name.lower() not in self._engaged:
                    self._threats.add(being.name.lower())
        if any(line.strip().lower().startswith("obvious exits") for line in lines):
            self._observe_room(lines)
        self._observe_score(lines)
        if command == "areas":
            found = parse_areas(lines)
            for area in found:
                self.knowledge.remember_area(area)
            if not found:
                self._areas_unread = True
        if command.startswith("consider "):
            target = command.split(" ", 1)[1]
            reading = self.memory.remember_consider(target, lines, kind="mobile")
            if reading.estimated:
                self._fresh.add(target.strip().lower())
                if reading.subject:
                    self._fresh.add(reading.subject.strip().lower())

    def _observe_room(self, lines: list[str]) -> None:
        observation = parse_room(lines, [])
        name = observation.room.name.strip()
        if not name:
            return
        if name.lower() != self.room_name.lower():
            self._tried.clear()
            self._fresh.clear()
        self.room_name = name
        self.room_exits = [exit_name.strip().lower() for exit_name in observation.room.exits if exit_name.strip()]
        self.room_current = True
        self.memory.remember_room(name, description=observation.room.description, exits=self.room_exits)
        for mobile in observation.mobiles:
            detail = str(getattr(mobile, "detail", "") or "")
            fighting_you = getattr(mobile, "pose", "") == "fighting" and detail.upper().startswith("YOU")
            self.memory.remember_mobile(mobile.name, room_name=name, aggressive=fighting_you)
            if fighting_you and mobile.name.lower() not in self._engaged:
                self.clock.fighting = True
                self._threats.add(mobile.name.lower())

    def _observe_score(self, lines: list[str]) -> None:
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
            return
        if self.clock.score_count == 0:
            self.clock.start_level = level
            self.clock.start_hours = hours
            self.clock.exp_span = exp
        elif self.clock.level != level:
            self.clock.exp_span = exp
        self.clock.level = level
        self.clock.hours = hours
        self.clock.exp_to_level = exp
        if hit is not None:
            self.clock.hit = hit
        if max_hit is not None:
            self.clock.max_hit = max_hit
        if position:
            self.clock.position = position
            if position == "fighting":
                self.clock.fighting = True
            elif position == "standing":
                self.clock.fighting = False
                self._threats.clear()
        self.clock.score_count += 1
        self.clock.score_steps = 0

    def _note_sent(self, command: str) -> None:
        verb, _, argument = command.partition(" ")
        verb = verb.lower()
        if verb == "kill" and argument:
            self._engaged.add(argument.strip().lower())
            self.clock.fighting = True
        elif verb in _DIRECTIONS:
            self._tried.add(verb)
            self._fresh.clear()
            self.room_current = False
        elif verb == "flee":
            self.clock.fighting = False
            self._threats.clear()
        elif verb == "save":
            self.clock.saves += 1
        elif verb == "rest":
            self.clock.position = "resting"
        elif verb == "stand":
            self.clock.position = "standing"
        elif verb == "look" and not self.room_current:
            self._look_unread = True
        elif verb == "score" and self.clock.score_count == 0:
            self._score_unread = True

    def _prompt_hit(self) -> int | None:
        match = _PROMPT_HIT.search(self.channel.last_prompt or "")
        if match is not None:
            return int(match.group("hit"))
        return self.clock.hit

    def _known(self, verb: str) -> bool:
        cleaned = verb.strip().lower()
        if not cleaned:
            return False
        if self.memory.command_named(cleaned) is not None:
            return True
        return any(record.name == cleaned for record in self.knowledge.command_records())

    def _take_known_room(self) -> None:
        room = getattr(self.knowledge, "room", None)
        name = str(getattr(room, "name", "") or "").strip()
        if not name:
            self.room_current = False
            return
        self.room_name = name
        self.room_exits = [str(exit_name).strip().lower() for exit_name in (getattr(room, "exits", []) or []) if str(exit_name).strip()]
