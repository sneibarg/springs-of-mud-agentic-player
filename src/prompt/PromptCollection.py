import json

from pathlib import Path
from typing import Dict, List, Union

from prompt.Prompt import Prompt


class PromptCollection:
    """Snapshot of the SOMDB.Prompts collection."""

    DATABASE = "SOMDB"
    NAME = "Prompts"
    FILENAME = "SOMDB.Prompts.json"

    def __init__(self, prompts: List[Prompt], source: str):
        self.prompts = prompts
        self.source = source
        self._by_name: Dict[str, Prompt] = {}
        for prompt in prompts:
            key = prompt.name.lower()
            if key in self._by_name:
                raise ValueError(f"Duplicate prompt name: {prompt.name}")
            self._by_name[key] = prompt

    @classmethod
    def load(cls, path: Union[str, Path]) -> "PromptCollection":
        collection_path = Path(path)
        with collection_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise ValueError(f"{collection_path} must be a JSON array of prompt documents")
        return cls([Prompt.from_json(item) for item in payload], str(collection_path))

    def get(self, name: str) -> Prompt:
        prompt = self._by_name.get(name.strip().lower())
        if prompt is None:
            raise KeyError(f"Prompt '{name}' was not found")
        return prompt
