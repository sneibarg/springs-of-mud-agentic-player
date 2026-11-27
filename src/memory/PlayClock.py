from dataclasses import dataclass

from util.SharedUtil import SharedUtil


@dataclass
class PlayClock:
    """Session-owned progress between KM questions. Zero span means unknown."""

    start_level: int = 0
    level: int = 0
    exp_to_level: int = 0
    exp_span: int = 0
    start_hours: int = 0
    hours: int = 0
    score_count: int = 0
    prior_notch: str = "cautious"
    cooldown_steps: int = 0
    saves: int = 0
    score_steps: int = 0

    def note_score(self, level: int, hours: int, exp_to_level: int) -> None:
        if self.score_count == 0:
            self.start_level = level
            self.start_hours = hours
            self.exp_span = exp_to_level
        elif self.level != level:
            self.exp_span = exp_to_level
        self.level = level
        self.hours = hours
        self.exp_to_level = exp_to_level
        self.score_count += 1
        self.score_steps = 0

    @classmethod
    def from_json(cls, data: dict) -> "PlayClock":
        return cls(**SharedUtil.snake_tree(data))
