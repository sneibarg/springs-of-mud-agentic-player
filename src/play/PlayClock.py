from dataclasses import dataclass


@dataclass
class PlayClock:
    """Counters the caller keeps between KM questions.

    The service does not store these. The next question copies them in.
    `exp_span` of 0 means the span is not known yet. `prior_notch` is clamped
    to the goal ceiling when the question is built.
    """

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
    hit: int | None = None
    max_hit: int | None = None
    position: str = ""
    fighting: bool = False
