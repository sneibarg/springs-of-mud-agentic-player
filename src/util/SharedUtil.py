import json
import os
import re
import tempfile

from pathlib import Path
from typing import Any, Dict


class SharedUtil:
    @staticmethod
    def camel_to_snake_case(dictionary: Dict[str, Any]) -> Dict[str, Any]:
        if dictionary is None:
            return {}

        def camel_case_to_snake_case(key: str) -> str:
            spaced = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", key)
            return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", spaced).lower()

        return {camel_case_to_snake_case(str(key)): value for key, value in dictionary.items()}

    @staticmethod
    def snake_to_camel(key: str) -> str:
        parts = str(key).split("_")
        if len(parts) == 1:
            return str(key)
        return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])

    @staticmethod
    def camel_keys(value):
        if isinstance(value, list):
            return [SharedUtil.camel_keys(item) for item in value]
        if isinstance(value, dict):
            return {SharedUtil.snake_to_camel(key): SharedUtil.camel_keys(item) for key, item in value.items()}
        return value

    @staticmethod
    def read_collection(path: Path) -> list:
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Working memory collection is not JSON: {exc}") from exc
        if not isinstance(payload, list):
            raise ValueError("Working memory collection must be a JSON array")
        return payload

    @staticmethod
    def write_collection(path: Path, documents: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as handle:
                temp_name = handle.name
                json.dump(documents, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            os.replace(temp_name, path)
            temp_name = None
        finally:
            if temp_name is not None:
                try:
                    os.remove(temp_name)
                except OSError:
                    pass
