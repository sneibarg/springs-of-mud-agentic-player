from dataclasses import dataclass

from util.SharedUtil import SharedUtil


@dataclass(frozen=True)
class KnownCommand:
    """A learned description. Its existence does not authorize execution."""

    name: str
    category: str = ""
    help_text: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("A known command needs a name")
        if not isinstance(self.category, str) or not isinstance(self.help_text, str):
            raise TypeError("Command category and help text must be strings")
        object.__setattr__(self, "name", self.name.strip().lower())
        object.__setattr__(self, "category", self.category.strip())
        object.__setattr__(self, "help_text", self.help_text.strip())

    @classmethod
    def from_json(cls, data: dict) -> "KnownCommand":
        if not isinstance(data, dict):
            raise TypeError("A command must be an object")
        payload = SharedUtil.snake_tree(data)
        return cls(name=payload.get("name", ""), category=payload.get("category") if payload.get("category") is not None else "", help_text=payload.get("help_text") if payload.get("help_text") is not None else "")
