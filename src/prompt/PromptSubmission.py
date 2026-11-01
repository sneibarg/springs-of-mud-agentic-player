import json

from dataclasses import dataclass
from typing import Any, Dict, Mapping


@dataclass(frozen=True)
class PromptSubmission:
    """A prompt after its tokens have been filled.

    to_request() is the body for som-nlp-service POST /ollama/completions:
    model, system, user, and jsonSchema. intents stays here and is not sent.
    """

    name: str
    model: str
    system: str
    user: str
    json_schema: Dict[str, Any]
    intents: tuple

    def to_request(self) -> Dict[str, Any]:
        """Build the OllamaCompletionBody. A blank user is rejected before the call."""
        user = self.user if isinstance(self.user, str) else ""
        if not user.strip():
            raise ValueError("User prompt cannot be null or empty")
        body: Dict[str, Any] = {}
        model = self.model.strip() if isinstance(self.model, str) else ""
        system = self.system if isinstance(self.system, str) else ""
        if model:
            body["model"] = model
        if system.strip():
            body["system"] = system
        body["user"] = user
        if self.json_schema:
            body["jsonSchema"] = self.json_schema
        return body

    def read_completion(self, completion: Any) -> Any:
        """Read OllamaCompletion.text. A schema request returns the parsed JSON document."""
        text = _completion_text(completion)
        if not text.strip():
            raise ValueError("Ollama returned an empty response")
        if not self.json_schema:
            return text
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Ollama completion was not JSON") from exc


def _completion_text(completion: Any) -> str:
    if isinstance(completion, str):
        return completion
    if isinstance(completion, Mapping):
        text = completion.get("text", "")
        return text if isinstance(text, str) else ""
    text = getattr(completion, "text", "")
    return text if isinstance(text, str) else ""
