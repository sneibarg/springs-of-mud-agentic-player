from dataclasses import dataclass

from util.SharedUtil import SharedUtil


@dataclass
class PendingAction:
    """An exchange in progress or interrupted before its reply was folded."""

    command: str
    response_received: bool = False
    target_id: str = ""

    @classmethod
    def from_json(cls, data: dict) -> "PendingAction":
        return cls(**SharedUtil.snake_tree(data))
