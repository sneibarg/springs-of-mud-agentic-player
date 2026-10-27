from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CharacterSummary:
    id: str
    name: str

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "CharacterSummary":
        if not isinstance(data, dict):
            raise TypeError("Character entry must be an object")
        character_id = str(data.get("id", "")).strip()
        name = str(data.get("name", "")).strip()
        if not character_id or not name:
            raise ValueError("Character entry requires id and name")
        return cls(id=character_id, name=name)


@dataclass
class AuthResponse:
    id: str
    first_name: str
    last_name: str
    account_name: str
    email_address: str
    player_character_list: List[CharacterSummary] = field(default_factory=list)

    def character_named(self, name: str) -> CharacterSummary:
        target = name.strip().lower()
        for character in self.player_character_list:
            if character.name.lower() == target:
                return character
        known = ", ".join(character.name for character in self.player_character_list) or "(none)"
        raise LookupError(f"Character '{name}' not found. Known characters: {known}")

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "AuthResponse":
        if not isinstance(data, dict):
            raise TypeError("Login response must be an object")
        account_id = str(data.get("id", "")).strip()
        account_name = str(data.get("accountName", "")).strip()
        if not account_id or not account_name:
            raise ValueError("Login response requires id and accountName")

        characters = []
        for entry in data.get("playerCharacterList", []) or []:
            characters.append(CharacterSummary.from_json(entry))

        return cls(
            id=account_id,
            first_name=str(data.get("firstName", "") or ""),
            last_name=str(data.get("lastName", "") or ""),
            account_name=account_name,
            email_address=str(data.get("emailAddress", "") or ""),
            player_character_list=characters,
        )
