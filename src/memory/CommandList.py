from dataclasses import dataclass, field
from typing import Iterable

from memory.KnownCommand import KnownCommand


@dataclass
class CommandList:
    """Ordered unique descriptions, with one owner for normalization and merge rules."""

    _records: dict[str, KnownCommand] = field(default_factory=dict, init=False, repr=False)

    def remember(self, name: str, *, category: str = "", help_text: str = "") -> KnownCommand:
        incoming = KnownCommand(name, category, help_text)
        previous = self._records.get(incoming.name)
        if previous is not None:
            incoming = KnownCommand(incoming.name, incoming.category or previous.category, incoming.help_text or previous.help_text)
        self._records[incoming.name] = incoming
        return incoming

    def named(self, name: str) -> KnownCommand | None:
        return self._records.get(name.strip().lower())

    def records(self) -> list[KnownCommand]:
        return list(self._records.values())

    def replace(self, commands: Iterable[KnownCommand]) -> None:
        replacement = CommandList()
        for command in commands:
            if not isinstance(command, KnownCommand):
                raise TypeError("CommandList.replace requires KnownCommand values")
            replacement.remember(command.name, category=command.category, help_text=command.help_text)
        self._records = replacement._records

    def merged_with(self, fallback: "CommandList") -> "CommandList":
        """Keep this order and nonblank fields; fill gaps and append fallback names."""
        merged = CommandList()
        merged.replace(self.records())
        for command in fallback.records():
            previous = merged.named(command.name)
            merged.remember(command.name, category=previous.category if previous is not None and previous.category else command.category, help_text=previous.help_text if previous is not None and previous.help_text else command.help_text)
        return merged

    @classmethod
    def from_json(cls, data: list[dict]) -> "CommandList":
        if not isinstance(data, list):
            raise TypeError("Command records must be a list")
        commands = cls()
        commands.replace(KnownCommand.from_json(item) for item in data)
        return commands
