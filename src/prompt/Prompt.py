import json

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence

from util.GenericUtil import GenericUtil


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


@dataclass
class Prompt:
    """One SOMDB.Prompts document.

    system and user may contain {intent}, {response}, and {score}. tokenize()
    replaces those before the text is submitted to the model.
    """

    name: str
    model: str
    system: str
    user: str
    json_schema: Dict[str, Any]
    tokens: Dict[str, Dict[str, Any]]

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "Prompt":
        if not isinstance(data, dict):
            raise TypeError("Prompt document must be an object")

        normalized = GenericUtil.camel_to_snake_case(data)
        name = str(normalized.get("name", "")).strip()
        model = str(normalized.get("model", "")).strip()
        system = normalized.get("system", "")
        user = normalized.get("user", "")
        json_schema = normalized.get("json_schema", {})
        tokens = data.get("tokens", {})
        if not name or not model:
            raise ValueError("Prompt document requires name and model")
        if not isinstance(system, str) or not isinstance(user, str):
            raise ValueError(f"Prompt '{name}' system and user must be strings")
        if not isinstance(json_schema, dict):
            raise ValueError(f"Prompt '{name}' jsonSchema must be an object")
        if not isinstance(tokens, dict):
            raise ValueError(f"Prompt '{name}' tokens must be an object")
        for token_name, spec in tokens.items():
            if not isinstance(spec, dict) or "example" not in spec:
                raise ValueError(f"Prompt '{name}' token '{token_name}' requires an example")
            text = spec.get("text", "")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Prompt '{name}' token '{token_name}' requires text")
        return cls(
            name=name,
            model=model,
            system=system,
            user=user,
            json_schema=json_schema,
            tokens=tokens,
        )

    def tokenize(self, score: str | Sequence[str], *intents: str) -> PromptSubmission:
        """Fill intent, response, and score tokens for one model submission."""
        if not self.tokens:
            raise ValueError(f"Prompt '{self.name}' has no tokens.")
        if not intents:
            raise ValueError(f"Prompt '{self.name}' requires one or more intent tokens.")
        if self.system.count("{intent}") != 1 or self.system.count("{response}") != 1:
            raise ValueError(f"Prompt '{self.name}' is missing the {{intent}} or {{response}} placeholder.")
        if self.user.count("{score}") != 1:
            raise ValueError(f"Prompt '{self.name}' is missing the {{score}} placeholder.")

        chosen: list[str] = []
        response: Dict[str, Any] = {}
        phrases: list[str] = []
        for intent in intents:
            name = str(intent).strip()
            if name in chosen:
                raise ValueError(f"Intent token '{name}' was repeated.")
            spec = self.tokens.get(name)
            if spec is None:
                raise ValueError(f"Prompt '{self.name}' has no token '{name}'.")
            chosen.append(name)
            phrases.append(str(spec["text"]).strip())
            for key, value in _example_fields(name, spec["example"]).items():
                if key not in self.json_schema.get("properties", {}):
                    raise ValueError(
                        f"Prompt '{self.name}' token '{name}' uses '{key}', which is not in jsonSchema."
                    )
                response[key] = value

        properties = self.json_schema.get("properties", {})
        schema = {
            "type": "object",
            "properties": {key: deepcopy(properties[key]) for key in response},
            "required": list(response),
        }
        response_json = json.dumps(response, indent=2, ensure_ascii=False)
        system = self.system.replace("{response}", response_json, 1).replace("{intent}", ", ".join(phrases), 1)
        user = self.user.replace("{score}", _score_text(score), 1)
        return PromptSubmission(
            name=self.name,
            model=self.model,
            system=system,
            user=user,
            json_schema=schema,
            intents=tuple(chosen),
        )


def _example_fields(name: str, example: Any) -> Mapping[str, Any]:
    if isinstance(example, dict):
        return example
    return {name: example}


def _completion_text(completion: Any) -> str:
    if isinstance(completion, str):
        return completion
    if isinstance(completion, Mapping):
        text = completion.get("text", "")
        return text if isinstance(text, str) else ""
    text = getattr(completion, "text", "")
    return text if isinstance(text, str) else ""


def _score_text(score: str | Sequence[str]) -> str:
    if isinstance(score, str):
        return score
    if isinstance(score, Sequence):
        return "\n".join(str(line) for line in score)
    raise TypeError("Score text must be a string or a sequence of lines.")
