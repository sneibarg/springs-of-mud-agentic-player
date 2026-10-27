from dataclasses import dataclass
from typing import Any, Dict

from util.GenericUtil import GenericUtil


def _read_id(data: Dict[str, Any]) -> str:
    raw = data.get("_id", data.get("id", ""))
    if isinstance(raw, dict):
        return str(raw.get("$oid", "")).strip()
    return str(raw or "").strip()


@dataclass
class Agent:
    id: str
    name: str
    account_name: str
    character_name: str
    enabled: bool = True
    description: str = ""

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "Agent":
        if not isinstance(data, dict):
            raise TypeError("Agent document must be an object")

        normalized = GenericUtil.camel_to_snake_case(data)
        name = str(normalized.get("name", "")).strip()
        account_name = str(normalized.get("account_name", "")).strip()
        character_name = str(normalized.get("character_name", "")).strip()
        if not name or not account_name or not character_name:
            raise ValueError("Agent document requires name, accountName, and characterName")

        enabled = normalized.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"Agent '{name}' enabled must be a boolean")

        description = str(normalized.get("description", "") or "")
        return cls(
            id=_read_id(data),
            name=name,
            account_name=account_name,
            character_name=character_name,
            enabled=enabled,
            description=description,
        )
