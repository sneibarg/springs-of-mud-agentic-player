import re

from typing import Any, Dict


class GenericUtil:
    @staticmethod
    def camel_to_snake_case(dictionary: Dict[str, Any]) -> Dict[str, Any]:
        if dictionary is None:
            return {}

        def camel_case_to_snake_case(key: str) -> str:
            spaced = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", key)
            return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", spaced).lower()

        return {camel_case_to_snake_case(str(key)): value for key, value in dictionary.items()}
