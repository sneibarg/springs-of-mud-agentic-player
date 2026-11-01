import base64

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SavedConnection:
    """One saved account from connections.json.

    The password stays obfuscated the same way springs-of-mud-ui stores it.
    """

    name: str
    server_url: str
    account_name: str
    telnet_host: Optional[str]
    telnet_port: Optional[int]
    obfuscated_password: str = field(repr=False)

    def login_password(self) -> str:
        return deobfuscate_password(self.obfuscated_password)


def obfuscate_password(password: str) -> str:
    """Match springs-of-mud-ui ConnectionSettings._obfuscate_password."""
    if not password:
        return ""
    return base64.b64encode(password.encode("utf-8")).decode("utf-8")


def deobfuscate_password(obfuscated: str) -> str:
    """Match springs-of-mud-ui ConnectionSettings._deobfuscate_password."""
    if not obfuscated:
        return ""
    try:
        return base64.b64decode(obfuscated.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""
