import json

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandLesson:
    """One `commands` reading and the Ollama exchange that reviewed it.

    `prompt` is the completion body that was sent. `response` is the raw text
    the model returned. `commands` are the names remembered from the server text.
    """

    prompt: dict
    response: str
    commands: list[str]
    error: str = ""

    def parsed_commands(self) -> tuple[list[str] | None, str]:
        parsed, error = _completion_value(self.error, self.response)
        if error:
            return None, error
        names = parsed.get("commands") if isinstance(parsed, dict) else None
        if not isinstance(names, list) or not all(isinstance(name, str) and name.strip() for name in names):
            return None, "Ollama completion did not return a commands list"
        return [name.strip().lower() for name in names], ""

    def to_review(self) -> dict:
        parsed, parse_error = self.parsed_commands()
        document = {"prompt": self.prompt, "response": self.response, "commands": list(self.commands), "parsedCommands": parsed}
        if self.error:
            document["error"] = self.error
        if parse_error and not self.error:
            document["parseError"] = parse_error
        return document


def _completion_value(error: str, response: str) -> tuple[Any, str]:
    if error:
        return None, error
    if not response.strip():
        return None, "Ollama returned an empty response"
    try:
        return json.loads(response), ""
    except json.JSONDecodeError as exc:
        return None, f"Ollama completion was not JSON: {exc}"
