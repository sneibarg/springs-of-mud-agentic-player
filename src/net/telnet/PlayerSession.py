import json

from net.rest.AuthResponse import AuthResponse
from net.telnet.TelnetClient import TelnetClient, TelnetConfig


def build_logon_line(auth: AuthResponse, character_name: str) -> str:
    """Build the telnet line springs-of-mud-server MessageCodec accepts as AUTH."""
    character = auth.character_named(character_name)
    payload = {
        "accountId": auth.id,
        "characterId": character.id,
        "characterName": character.name,
    }
    return "logon " + json.dumps(payload, separators=(",", ":"))


class PlayerSession:
    def __init__(self, config: TelnetConfig, client: TelnetClient | None = None):
        self.client = client or TelnetClient(config)

    def connect(self) -> None:
        self.client.connect()

    def logon(self, auth: AuthResponse, character_name: str) -> str:
        line = build_logon_line(auth, character_name)
        self.client.send_line(line)
        return line

    def close(self) -> None:
        self.client.close()
