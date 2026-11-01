from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class CharacterSummary:
    id: str
    name: str
    level: Optional[int] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "CharacterSummary":
        if not isinstance(data, dict):
            raise TypeError("Character entry must be an object")
        character_id = str(data.get("id", "")).strip()
        name = str(data.get("name", "")).strip()
        if not character_id or not name:
            raise ValueError("Character entry requires id and name")
        return cls(id=character_id, name=name, level=_character_level(data))


def _character_level(data: Dict[str, Any]) -> Optional[int]:
    if "level" not in data or data.get("level") is None or data.get("level") == "":
        return None
    return int(data["level"])
