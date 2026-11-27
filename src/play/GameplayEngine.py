import logging
import re

from memory.PendingAction import PendingAction
from net.rest.KmClient import KmError
from play.LevelGoal import LevelGoal
from play.LevelQuestion import LevelQuestion, MobileReading, clamp_notch
from play.ObservationPipeline import ObservationPipeline
from play.PlayError import PlayError

logger = logging.getLogger(__name__)

_DIRECTIONS = {"north", "south", "east", "west", "up", "down"}
_REFUSED = {"quit", "delete", "murder", "steal", "password", "!"}
_TRAVEL_WHILE_FIGHTING = _DIRECTIONS | {"kill", "recall"}
_MOVEMENT_REFUSAL = re.compile(r"cannot go|can['’]t go|couldn['’]t escape|could not escape|is closed|is locked|too exhausted|not enough movement", re.IGNORECASE)
_PROMPT_HIT = re.compile(r"<\s*(?P<hit>\d+)\s*hp\b", re.IGNORECASE)


class GameplayEngine:
    """One observe-decide-act step on the drive thread.

    Observe drains telnet lines and folds a score or a look into the clock.
    Decide asks the player's situation when one was given, and otherwise asks
    one baseline question from the loaded KM library. Act sends the first
    command that question licenses, or sends nothing. The next step sees the
    reply before it asks again.
    """

    def __init__(self, channel, memory, knowledge, km, *, goal: LevelGoal | None = None, room_current: bool = False, flee_hp: int = 20, player=None):
        self.channel = channel
        self.memory = memory
        self.knowledge = knowledge
        self.observations = ObservationPipeline(memory, knowledge)
        self.km = km
        self.player = player
        self.goal = goal
        self.flee_hp = flee_hp
        if room_current and not self.memory.session.room.name:
            self._take_known_room()

    def step(self) -> str:
        """Drain, choose at most one command, and observe its reply. A wait returns an empty string."""
        self.channel.drain()
        for lines, complete in self.channel.drained_frames:
            room_fragment = any(line.strip().lower().startswith("obvious exits") or line.strip() == self.memory.session.room.name for line in lines)
            if not complete and not self.memory.session.observation_lines and not room_fragment:
                self._observe(lines, "")
                continue
            self.memory.session.observation_lines.extend(lines)
            if complete:
                self._observe(self.memory.session.observation_lines, "")
                self.memory.session.observation_lines.clear()
        if self.memory.session.pending_action is not None or self.memory.session.observation_lines:
            return ""
        if self.memory.session.progress.score_count > 0:
            self.memory.session.progress.score_steps += 1
        command = self._choose()
        if not command:
            return ""
        verb, _, argument = command.partition(" ")
        target = self.memory.resolve_current_being(argument) if verb in {"kill", "consider"} else None
        self.memory.session.pending_action = PendingAction(command, target_id=target.being_id if target is not None else "")
        if verb in _DIRECTIONS or verb in {"flee", "recall"}:
            self.memory.session.room.depart(verb if verb in _DIRECTIONS else "")
            self.memory.session.look_unread = False
        if verb == "kill":
            self.memory.session.room.fresh.clear()
        try:
            lines = self.channel.exchange(command)
        except PlayError as exc:
            self.observations.receive(exc.lines, command, origin="gameplay", complete=False)
            raise
        self.memory.session.pending_action.response_received = True
        self._observe(lines, command)
        self._note_sent(command, lines)
        self.memory.session.pending_action = None
        logger.info("Play step sent %s.", command)
        return command

    def _choose(self) -> str:
        hit = self._prompt_hit()
        if self.memory.session.combat.fighting and hit is not None and hit <= self.flee_hp and self._known("flee"):
            return "flee"
        if self.memory.session.combat.has_uninvited_threat():
            return self._leave()
        if not self.memory.session.room.current and not self.memory.session.look_unread and self._known("look"):
            return "look"
        if self.goal is None or self.km is None:
            return ""
        if self.memory.session.progress.score_count == 0 and not self.memory.session.score_unread and self._known("score"):
            return "score"
        if self.memory.session.progress.score_count == 0:
            return ""
        return self._licensed_command()

    def _licensed_command(self) -> str:
        self.memory.session.progress.prior_notch = clamp_notch(self.memory.session.progress.prior_notch, self.goal.risk)
        question = LevelQuestion(self.goal, self.memory.session.progress, self._readings(), self.memory.session.room.untried(), areas_known=bool(self.knowledge.areas) or self.memory.session.areas_unread, flee_hp=self.flee_hp, combat=self.memory.session.combat)
        try:
            results = self._ask(question.expressions())
        except KmError as exc:
            logger.warning("KM baseline was not answered: %s", exc)
            return ""
        try:
            decision = LevelQuestion.read(results)
        except ValueError as exc:
            logger.warning("KM baseline was not answered: %s", exc)
            return ""
        if decision.notch in {"cautious", "steady", "bold"}:
            self.memory.session.progress.prior_notch = clamp_notch(decision.notch, self.goal.risk)
        if decision.cooldown is not None and decision.cooldown >= 0:
            self.memory.session.progress.cooldown_steps = decision.cooldown
        for attempt in decision.attempts:
            command = self._accepted(attempt.command())
            if command:
                return command
        return ""

    def _ask(self, expressions: list[str]):
        """Send the question through the player situation when this step has one."""
        if self.player is None:
            return self.km.baseline(expressions)
        results = []
        for expression in expressions:
            if expression.startswith("(the "):
                results.append(self.player.query(expression))
            else:
                results.append(self.player.assert_expression(expression))
        return results

    def _accepted(self, command: str) -> str:
        verb = command.split(maxsplit=1)[0].lower()
        if verb in _REFUSED:
            return ""
        if self.memory.session.combat.fighting and verb in _TRAVEL_WHILE_FIGHTING:
            return ""
        if not self._known(verb):
            return ""
        if verb in _DIRECTIONS and not self.memory.session.room.current:
            return ""
        if verb in {"kill", "consider"}:
            target = self.memory.resolve_current_being(command.partition(" ")[2])
            if target is None or target.kind not in {"mobile", "npc"}:
                return ""
        return command

    def _leave(self) -> str:
        for direction in self.memory.session.room.untried() if self.memory.session.room.current else []:
            if self._known(direction):
                return direction
        if self._known("flee"):
            return "flee"
        return ""

    def _readings(self) -> list[MobileReading]:
        found = []
        for being in self.memory.current_beings():
            if being.kind != "mobile":
                continue
            consider = self.memory.consider_for_id(being.being_id)
            fresh = being.being_id in self.memory.session.room.fresh
            outlook = consider.outlook if fresh and consider is not None else ""
            found.append(MobileReading(name=being.name, outlook=outlook, fresh=bool(outlook) and outlook != "unknown"))
        found.sort(key=lambda reading: reading.name.lower())
        return found

    def _observe(self, lines: list[str], command: str) -> None:
        self.observations.receive(lines, command, origin="gameplay", prompt=self.channel.last_prompt)

    def _note_sent(self, command: str, lines: list[str]) -> None:
        verb, _, argument = command.partition(" ")
        verb = verb.lower()
        if verb == "kill" and argument:
            pending = self.memory.session.pending_action
            if pending is not None and pending.target_id and pending.target_id in self.memory.session.room.occupant_ids:
                self.memory.session.combat.engage(pending.target_id)
        elif verb == "flee" and (self.memory.session.room.current or any("you flee" in line.lower() for line in lines)) and not _MOVEMENT_REFUSAL.search("\n".join(lines)):
            self.memory.session.combat.leave_fight()
        elif verb == "save":
            self.memory.session.progress.saves += 1
        elif verb == "rest":
            self.memory.session.combat.position = "resting"
        elif verb == "stand":
            self.memory.session.combat.position = "standing"
        elif verb == "look" and not self.memory.session.room.current:
            self.memory.session.look_unread = True
        elif verb == "score" and self.memory.session.progress.score_count == 0:
            self.memory.session.score_unread = True

    def _prompt_hit(self) -> int | None:
        match = _PROMPT_HIT.search(self.memory.session.last_prompt)
        if match is not None:
            return int(match.group("hit"))
        return self.memory.session.combat.hit

    def _known(self, verb: str) -> bool:
        cleaned = verb.strip().lower()
        if not cleaned:
            return False
        return self.memory.session.command_available(cleaned)

    def _take_known_room(self) -> None:
        room = getattr(self.knowledge, "room", None)
        name = str(getattr(room, "name", "") or "").strip()
        if not name:
            self.memory.session.room.current = False
            return
        self.memory.observe_room(name, description=getattr(room, "description", None), exits=[str(exit_name).strip().lower() for exit_name in (getattr(room, "exits", []) or []) if str(exit_name).strip()])
