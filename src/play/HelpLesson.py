from dataclasses import dataclass

from play.CommandLesson import _completion_value


@dataclass
class HelpLesson:
    """One help page and the Ollama exchange that read it.

    `prompt` is the completion body that was sent. `response` is the raw text
    the model returned. The parsed topics stay on this lesson. Working memory keeps the help text.
    """

    command: str
    prompt: dict
    response: str
    error: str = ""
    category_requested: bool = False

    def parsed_help(self) -> tuple[dict | None, str]:
        parsed, error = _completion_value(self.error, self.response)
        if error:
            return None, error
        if not isinstance(parsed, dict):
            return None, "Ollama completion did not return a help document"
        missing = parsed.get("missing")
        topics = parsed.get("topics")
        if not isinstance(missing, bool) or not isinstance(topics, list):
            return None, "Ollama completion did not return help topics"
        cleaned = []
        for topic in topics:
            if not isinstance(topic, dict):
                return None, "Ollama completion did not return help topics"
            keyword = topic.get("keyword")
            text = topic.get("text")
            if not isinstance(keyword, str) or not keyword.strip() or not isinstance(text, str):
                return None, "Ollama completion did not return help topics"
            cleaned.append({"keyword": keyword.strip(), "text": text.strip()})
        if missing and cleaned:
            return None, "Ollama completion marked the help missing and also returned topics"
        if not missing and not cleaned:
            return None, "Ollama completion returned no help topics"
        return {"missing": missing, "topics": cleaned}, ""

    def parsed_category(self) -> tuple[str | None, str]:
        parsed, error = _completion_value(self.error, self.response)
        if error:
            return None, error
        category = parsed.get("category") if isinstance(parsed, dict) else None
        if not isinstance(category, str) or not category.strip():
            return None, "Ollama completion did not name a category"
        return category.strip().lower(), ""

    def to_review(self) -> dict:
        parsed, parse_error = self.parsed_help()
        document = {"command": self.command, "prompt": self.prompt, "response": self.response, "parsed": parsed}
        if self.category_requested:
            category, category_error = self.parsed_category()
            document["category"] = category
            if category_error and not self.error:
                document["categoryError"] = category_error
        if self.error:
            document["error"] = self.error
        if parse_error and not self.error:
            document["parseError"] = parse_error
        return document
