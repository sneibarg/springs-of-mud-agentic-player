from dataclasses import dataclass


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


@dataclass(frozen=True)
class LevelAttempt:
    """One command the licensed directive offers, in the order KM printed it."""

    role: str
    category: str
    verb: str
    argument: str

    def command(self) -> str:
        argument = _unquote(self.argument)
        if not argument:
            return self.verb
        return f"{self.verb} {argument}"
