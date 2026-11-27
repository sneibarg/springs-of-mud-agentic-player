from dataclasses import dataclass

from util.SharedUtil import SharedUtil


@dataclass(frozen=True)
class EvidenceMapping:
    """A deterministic mapping plan, never a transport or acceptance receipt."""

    observation_id: str
    player_name: str
    status: str
    expressions: tuple[str, ...] = ()
    unmapped: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, data: dict) -> "EvidenceMapping":
        payload = SharedUtil.snake_tree(data)
        return cls(observation_id=payload["observation_id"], player_name=payload["player_name"], status=payload["status"], expressions=tuple(payload.get("expressions", [])), unmapped=tuple(payload.get("unmapped", [])))
