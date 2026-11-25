from dataclasses import dataclass


@dataclass(frozen=True)
class LevelGoal:
    """The level goal copied into one KM question.

    `minutes` of 0 is an open budget. The risk word is the notch ceiling.
    """

    target_level: int
    risk: str
    minutes: int
    kind: str = "level"

    @classmethod
    def from_section(cls, section: dict) -> "LevelGoal":
        if not isinstance(section, dict):
            raise ValueError("Config section 'goal' must be a mapping")
        kind = section.get("kind", "level")
        if kind != "level":
            raise ValueError("goal.kind must be level")
        if "level" not in section:
            raise ValueError("goal.level is required")
        level = section.get("level")
        if isinstance(level, bool) or not isinstance(level, int) or level < 1:
            raise ValueError("goal.level must be an integer of 1 or more")
        risk = section.get("risk", "steady")
        if risk not in {"cautious", "steady", "bold"}:
            raise ValueError("goal.risk must be cautious, steady, or bold")
        minutes = section.get("minutes", 0)
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 0:
            raise ValueError("goal.minutes must be an integer of 0 or more")
        return cls(target_level=level, risk=risk, minutes=minutes, kind="level")
