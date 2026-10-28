import logging

from typing import Callable, Optional

from net.rest.AuthClient import AuthClient
from net.rest.AuthResponse import AuthResponse, CharacterSummary
from net.rest.ConnectionCatalog import ConnectionCatalog, SavedConnection
from net.telnet.PlayerSession import PlayerSession
from net.telnet.TelnetClient import TelnetConfig


logger = logging.getLogger(__name__)


class AccountSession:
    """Connect a saved account, then log on as one of its characters.

    The password is deobfuscated only for the login call. Logon refuses a
    name that was not in the login character list.
    """

    def __init__(
        self,
        catalog: ConnectionCatalog,
        *,
        auth_base_url: str = "http://localhost:8169",
        login_path: str = "/api/auth/login",
        telnet_host: str = "localhost",
        telnet_port: int = 6969,
        auth_client_factory: Optional[Callable[[str], AuthClient]] = None,
        session_factory: Optional[Callable[[str, int], PlayerSession]] = None,
    ):
        self.catalog = catalog
        self.auth_base_url = auth_base_url.rstrip("/")
        self.login_path = login_path
        self.telnet_host = telnet_host
        self.telnet_port = telnet_port
        self._auth_client_factory = auth_client_factory or self._default_auth_client
        self._session_factory = session_factory or self._default_session
        self.connection: Optional[SavedConnection] = None
        self.auth_client: Optional[AuthClient] = None
        self.auth: Optional[AuthResponse] = None
        self.session: Optional[PlayerSession] = None
        self.character: Optional[CharacterSummary] = None

    @property
    def logged_on(self) -> bool:
        return self.session is not None and self.character is not None

    def connect(self, name: str) -> str:
        cleaned = str(name or "").strip()
        if not cleaned:
            return "Usage: connect <connection-name>"
        try:
            connection = self.catalog.named(cleaned)
        except LookupError as exc:
            return str(exc)
        password = connection.login_password()
        if not connection.account_name or not password:
            return "Account name and password are required."
        base_url = connection.server_url or self.auth_base_url
        try:
            client = self._auth_client_factory(base_url)
            auth = client.login(connection.account_name, password)
        except Exception as exc:
            logger.warning("Connect failed: %s", exc.__class__.__name__)
            return f"Connect failed: {exc.__class__.__name__}"
        if not client.jwt_token:
            logger.info("Login returned no Authorization token.")
        self.connection = connection
        self.auth_client = client
        self.auth = auth
        names = ", ".join(character.name for character in auth.player_character_list) or "(none)"
        return f"Connected as {auth.account_name}. Characters: {names}."

    def list_characters(self) -> str:
        if self.auth is None:
            return "Connect an account before listing characters."
        if not self.auth.player_character_list:
            return "No characters are available."
        lines = ["Available characters:"]
        lines.extend(f"- {character.name}" for character in self.auth.player_character_list)
        return "\n".join(lines)

    def logon(self, name: str) -> str:
        if self.auth is None:
            return "Connect an account before logon."
        cleaned = str(name or "").strip()
        if not cleaned:
            return "Usage: logon <characterName>"
        character = _available_character(self.auth, cleaned)
        if character is None:
            known = ", ".join(item.name for item in self.auth.player_character_list) or "(none)"
            return f"Character '{cleaned}' is not available. Available characters: {known}."
        try:
            self._open_session(character)
        except Exception as exc:
            logger.warning("Logon failed: %s", exc.__class__.__name__)
            return f"Logon failed: {exc.__class__.__name__}"
        return f"Logged on as {character.name}."

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None
        self.character = None

    def _open_session(self, character: CharacterSummary) -> None:
        connection = self.connection
        host = (connection.telnet_host if connection and connection.telnet_host else self.telnet_host)
        port = connection.telnet_port if connection and connection.telnet_port is not None else self.telnet_port
        session = self._session_factory(host, port)
        try:
            session.connect()
            session.logon(self.auth, character.name)
        except Exception:
            session.close()
            raise
        if self.session is not None:
            self.session.close()
        self.session = session
        self.character = character

    def _default_auth_client(self, base_url: str) -> AuthClient:
        return AuthClient(base_url, login_path=self.login_path)

    def _default_session(self, host: str, port: int) -> PlayerSession:
        return PlayerSession(TelnetConfig(host=host, port=port))


def _available_character(auth: AuthResponse, name: str) -> Optional[CharacterSummary]:
    target = name.strip().lower()
    for character in auth.player_character_list:
        if character.name.lower() == target:
            return character
    return None
