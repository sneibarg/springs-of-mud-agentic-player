import re

from dataclasses import dataclass

from play.LevelAttempt import LevelAttempt
from play.LevelGoal import LevelGoal
from play.PlayClock import PlayClock


_RANKS = {"cautious": 0, "steady": 1, "bold": 2}
_ATTEMPT = re.compile(r"\(:args\s+(\S+)\s+(\"[^\"]*\"|\S+)\s+(\S+)\s+(\"[^\"]*\"|\S+)\)")
_QUERIES = ("(the som-notch of *View)", "(the som-cooldown-next of *View)", "(the som-licensed-rule of *View)", "(the som-attempts of (the som-licensed-directive of *View))")


@dataclass(frozen=True)
class MobileReading:
    """One mobile the caller has already ordered for this question."""

    name: str
    outlook: str = ""
    fresh: bool = False


@dataclass(frozen=True)
class LevelDecision:
    notch: str
    cooldown: int | None
    rule: int | None
    attempts: tuple[LevelAttempt, ...]


class LevelQuestion:
    """The KM text for one level-goal question, and the reads taken from its answer.

    Frame names are `*Goal`, `*Clock`, `*View`, and `*MobileN`. The caller
    starts this text from the loaded library. A player is not a reading.
    A stale consider is passed with no outlook, so the library surveys it.
    """

    def __init__(self, goal: LevelGoal, clock: PlayClock, readings: list[MobileReading], exits: list[str], *, areas_known: bool, flee_hp: int):
        self.goal = goal
        self.clock = clock
        self.readings = list(readings)
        self.exits = list(exits)
        self.areas_known = areas_known
        self.flee_hp = flee_hp

    def expressions(self) -> list[str]:
        frames = []
        names = []
        for index, reading in enumerate(self.readings, start=1):
            frame = f"*Mobile{index}"
            names.append(frame)
            pairs = [("instance-of", "Som-Mobile-Reading"), ("som-mobile-name", _token(reading.name))]
            if reading.fresh and reading.outlook:
                pairs.append(("som-outlook", reading.outlook))
                pairs.append(("som-fresh", "t"))
            frames.append(_has(frame, pairs))
        ceiling = self.goal.risk if self.goal.risk in _RANKS else "steady"
        prior = _clamp(self.clock.prior_notch, ceiling)
        elapsed = 0 if self.clock.score_count == 0 else max(0, (self.clock.hours - self.clock.start_hours) * 60)
        clock_pairs = [("instance-of", "Som-Progress-Projection"), ("som-event", "view"), ("som-clock-kind", "level"), ("som-clock-target", str(self.goal.target_level)), ("som-start-level", str(self.clock.start_level)), ("som-start-fraction", "0"), ("som-level", str(self.clock.level)), ("som-exp-to-level", str(self.clock.exp_to_level)), ("som-exp-span", str(self.clock.exp_span)), ("som-elapsed-minutes", str(elapsed)), ("som-score-count", str(self.clock.score_count)), ("som-prior-notch", prior), ("som-cooldown-steps", str(self.clock.cooldown_steps)), ("som-saves", str(self.clock.saves)), ("som-score-steps", str(self.clock.score_steps)), ("som-flee-floor", str(self.flee_hp)), ("som-untried-exits", _seq(self.exits))]
        if self.areas_known:
            clock_pairs.append(("som-areas-known", "t"))
        if self.clock.fighting:
            clock_pairs.append(("som-fighting", "t"))
        if self.clock.hit is not None:
            clock_pairs.append(("som-hit", str(self.clock.hit)))
        if self.clock.max_hit is not None:
            clock_pairs.append(("som-max-hit", str(self.clock.max_hit)))
        if self.clock.position:
            clock_pairs.append(("som-position", self.clock.position))
        if names:
            clock_pairs.append(("som-reading", _seq(names)))
        frames.append(_has("*Goal", [("instance-of", "Som-Level-Goal"), ("som-target-level", str(self.goal.target_level)), ("som-risk-ceiling", ceiling), ("som-budget-minutes", str(self.goal.minutes))]))
        frames.append(_has("*Clock", clock_pairs))
        frames.append("(*View has (instance-of (Som-Goal-View)) (som-goal (*Goal)) (som-progress (*Clock)))")
        return frames + list(_QUERIES)

    @staticmethod
    def read(results) -> LevelDecision:
        if len(results) < len(_QUERIES):
            raise ValueError("KM baseline did not return the level question")
        tail = list(results)[-len(_QUERIES):]
        return LevelDecision(notch=_symbol(_answer(tail[0])), cooldown=_integer(_answer(tail[1])), rule=_integer(_answer(tail[2])), attempts=tuple(_attempts(_answer(tail[3]))))


def clamp_notch(prior: str, ceiling: str) -> str:
    return _clamp(prior, ceiling)


def _clamp(prior: str, ceiling: str) -> str:
    stored = prior if prior in _RANKS else "cautious"
    limit = ceiling if ceiling in _RANKS else "steady"
    if _RANKS[stored] > _RANKS[limit]:
        return limit
    return stored


def _has(frame: str, pairs: list[tuple[str, str]]) -> str:
    body = " ".join(f"({slot} ({value}))" for slot, value in pairs)
    return f"({frame} has {body})"


def _seq(items: list[str]) -> str:
    if not items:
        return "(:seq)"
    return "(:seq " + " ".join(_token(item) if not item.startswith("*") else item for item in items) + ")"


def _token(value: str) -> str:
    if re.fullmatch(r"[A-Za-z*][A-Za-z0-9_+-]*", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _answer(result) -> str:
    return str(getattr(result, "answer", "") or "")


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def _symbol(answer: str) -> str:
    text = answer.strip()
    if not text or text == "nil":
        return ""
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def _integer(answer: str) -> int | None:
    text = _symbol(answer)
    if not text:
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return None


def _attempts(answer: str) -> list[LevelAttempt]:
    if not answer.strip() or answer.strip() == "nil":
        return []
    found = []
    for role, category, verb, argument in _ATTEMPT.findall(answer):
        found.append(LevelAttempt(role=role, category=_unquote(category), verb=verb, argument=argument))
    return found
