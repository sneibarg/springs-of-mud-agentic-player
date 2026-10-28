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
    telnet_replace_existing: str
    knowledge_base_url: str
    knowledge_path: str
    ollama_base_url: str
    ollama_path: str
    database: str
    collection_name: str
    collection_path: Path
    connections_path: Path
    control_host: str
    control_port: int

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
        knowledge = _section(raw, "knowledge")
        ollama = _section(raw, "ollama")
        collection = _section(raw, "collection")
        connections = _section(raw, "connections")
        control = _section(raw, "control")
        auth_base_url = str(auth.get("base_url", "http://localhost:8169")).rstrip("/")
        replace_existing = str(telnet.get("replace_existing", "Y")).strip().upper()[:1] or "Y"
        if replace_existing not in ("Y", "N"):
            raise ValueError("telnet.replace_existing must be Y or N")
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
        connections_path = Path(str(connections.get("path", "resources/connections.json")))
        if not connections_path.is_absolute():
            connections_path = _repo_root(config_path) / connections_path
        control_host = _loopback_host(control.get("host", "127.0.0.1"))
        try:
            control_port = int(control.get("port", 9711))
        except (TypeError, ValueError):
            raise ValueError("control.port must be a TCP port") from None
        if not 1 <= control_port <= 65535:
            raise ValueError("control.port must be a TCP port")

        return cls(
            auth_base_url=auth_base_url,
            login_path=str(auth.get("login_path", "/api/auth/login")),
            telnet_host=str(telnet.get("host", "localhost")),
            telnet_port=int(telnet.get("port", 6969)),
            telnet_replace_existing=replace_existing,
            knowledge_base_url=str(knowledge.get("base_url", auth_base_url)).rstrip("/"),
            knowledge_path=str(knowledge.get("path", "/api/v1/agent-knowledge")),
            ollama_base_url=str(ollama.get("base_url", "http://localhost:9081")).rstrip("/"),
            ollama_path=str(ollama.get("path", "/ollama/completions")),
            database=database,
            collection_name=collection_name,
            collection_path=collection_path,
            connections_path=connections_path,
            control_host=control_host,
            control_port=control_port,
        )


def _section(raw: Dict[str, Any], name: str) -> Dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{name}' must be a mapping")
    return value


def _loopback_host(value: object) -> str:
    cleaned = str(value or "").strip().lower()
    if cleaned in {"localhost", "127.0.0.1"}:
        return "127.0.0.1"
    raise ValueError("Control host must be localhost")


def _repo_root(config_path: Path) -> Path:
    if config_path.parent.name == "resources":
        return config_path.parent.parent
    return config_path.parent
