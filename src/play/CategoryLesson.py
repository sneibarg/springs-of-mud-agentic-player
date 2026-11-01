from dataclasses import dataclass

from play.CommandLesson import _completion_value


@dataclass
class CategoryLesson:
    """One bare `help` index and the Ollama exchange that read its categories.

    `prompt` is the completion body that was sent. `response` is the raw text
    the model returned. Parsed categories are stored on working memory.
    """

    prompt: dict
    response: str
    error: str = ""

    def parsed_categories(self) -> tuple[list[dict] | None, str]:
        parsed, error = _completion_value(self.error, self.response)
        if error:
            return None, error
        groups = parsed.get("categories") if isinstance(parsed, dict) else None
        if not isinstance(groups, list):
            return None, "Ollama completion did not return categories"
        cleaned = []
        seen: set[str] = set()
        for group in groups:
            if not isinstance(group, dict):
                return None, "Ollama completion did not return categories"
            name = group.get("name")
            commands = group.get("commands")
            if not isinstance(name, str) or not name.strip() or not isinstance(commands, list):
                return None, "Ollama completion did not return categories"
            names = []
            for command in commands:
                if not isinstance(command, str) or not command.strip():
                    return None, "Ollama completion did not return categories"
                token = command.strip().lower()
                if token in seen:
                    continue
                seen.add(token)
                names.append(token)
            if names:
                cleaned.append({"name": name.strip().lower(), "commands": names})
        if not cleaned:
            return None, "Ollama completion did not return categories"
        return cleaned, ""

    def to_review(self) -> dict:
        parsed, parse_error = self.parsed_categories()
        document = {"prompt": self.prompt, "response": self.response, "parsedCategories": parsed}
        if self.error:
            document["error"] = self.error
        if parse_error and not self.error:
            document["parseError"] = parse_error
        return document
