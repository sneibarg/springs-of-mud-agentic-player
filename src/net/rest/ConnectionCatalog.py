import json

from pathlib import Path
from typing import Optional

from net.rest.SavedConnection import SavedConnection


class ConnectionCatalog:
    """Saved UI connections. Passwords are base64 text, not plaintext."""

    def __init__(self, connections: list[SavedConnection]):
        self.connections = list(connections)

    @classmethod
    def load(cls, path: str | Path) -> "ConnectionCatalog":
        file_path = Path(path)
        with file_path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, list):
            raise ValueError(f"{file_path} must be a JSON array")
        return cls([_connection(entry, index) for index, entry in enumerate(raw)])

    def named(self, name: str) -> SavedConnection:
        target = str(name or "").strip().lower()
        if not target:
            raise ValueError("Usage: connect <connection-name>")
        for connection in self.connections:
            if connection.name.lower() == target:
                return connection
        raise LookupError(f"Connection '{name.strip()}' not found")

    def for_account(self, account_name: str) -> SavedConnection:
        """The first saved connection whose account name matches, ignoring case."""
        target = str(account_name or "").strip().lower()
        if not target:
            raise LookupError("Agent account name is required.")
        for connection in self.connections:
            if connection.account_name.strip().lower() == target:
                return connection
        raise LookupError(f"No saved connection for account '{account_name.strip()}'.")


def _connection(entry, index: int) -> SavedConnection:
    if not isinstance(entry, dict):
        raise ValueError(f"Connection {index} must be an object")
    name = str(entry.get("name", "")).strip()
    if not name:
        raise ValueError(f"Connection {index} requires a name")
    host = str(entry.get("telnet_host", "") or "").strip()
    return SavedConnection(name=name, server_url=str(entry.get("server_url", "") or "").strip(), account_name=str(entry.get("account_name", "") or "").strip(), telnet_host=host or None, telnet_port=_port(entry.get("telnet_port"), name), obfuscated_password=str(entry.get("password", "") or ""))


def _port(value, name: str) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"Connection '{name}' telnet_port must be a number") from exc
