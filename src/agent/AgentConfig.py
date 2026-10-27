from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from agent.AgentCollection import AgentCollection


@dataclass(frozen=True)
class AgentConfig:
    auth_base_url: str
    login_path: str
    telnet_host: str
    telnet_port: int
    database: str
    collection_name: str
    collection_path: Path

    @classmethod
    def load(cls, path: str) -> "AgentConfig":
        import yaml

        config_path = Path(path).resolve()
        with config_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{config_path} must be a YAML mapping")

        auth = _section(raw, "auth")
        telnet = _section(raw, "telnet")
        collection = _section(raw, "collection")
        database = str(collection.get("database", AgentCollection.DATABASE))
        collection_name = str(collection.get("name", AgentCollection.NAME))
        if database != AgentCollection.DATABASE or collection_name != AgentCollection.NAME:
            raise ValueError(
                f"Expected {AgentCollection.DATABASE}.{AgentCollection.NAME}, "
                f"got {database}.{collection_name}"
            )

        collection_path = Path(str(collection.get("path", f"resources/collections/{AgentCollection.FILENAME}")))
        if not collection_path.is_absolute():
            collection_path = _repo_root(config_path) / collection_path

        return cls(
            auth_base_url=str(auth.get("base_url", "http://localhost:8169")).rstrip("/"),
            login_path=str(auth.get("login_path", "/api/auth/login")),
            telnet_host=str(telnet.get("host", "localhost")),
            telnet_port=int(telnet.get("port", 6969)),
            database=database,
            collection_name=collection_name,
            collection_path=collection_path,
        )


def _section(raw: Dict[str, Any], name: str) -> Dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{name}' must be a mapping")
    return value


def _repo_root(config_path: Path) -> Path:
    if config_path.parent.name == "resources":
        return config_path.parent.parent
    return config_path.parent
