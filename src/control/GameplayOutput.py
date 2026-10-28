import logging
import threading

from pathlib import Path
from typing import Callable, Optional


logger = logging.getLogger(__name__)

# Lines that carry the telnet logon payload, an Authorization header, or a bearer token.
_AUTH_MARKERS = (
    '"accountid"',
    '"characterid"',
    '"password"',
    "authorization:",
    "authorization ",
    "bearer ",
    "password=",
)


class GameplayOutput:
    """Where received game lines are shown.

    Console printing is on until `disable`. A session file is optional.
    Authentication lines are dropped before either destination.
    """

    DEFAULT_SESSION_PATH = "session.txt"

    def __init__(
        self,
        console: Optional[Callable[[str], None]] = None,
        *,
        enabled: bool = True,
        default_session_path: str = DEFAULT_SESSION_PATH,
    ):
        self._console = console or _default_console
        self._enabled = enabled
        self.default_session_path = default_session_path or self.DEFAULT_SESSION_PATH
        self._session_path = ""
        self._file = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    @property
    def session_path(self) -> str:
        with self._lock:
            return self._session_path

    def enable(self) -> None:
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        with self._lock:
            self._enabled = False

    def set_session_file(self, path: str) -> str:
        """Append later gameplay lines to `path`. Returns the path that was opened."""
        cleaned = str(path or "").strip()
        if not cleaned:
            raise ValueError("Session file path is empty")
        destination = Path(cleaned)
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle = destination.open("a", encoding="utf-8")
        with self._lock:
            self._close_file()
            self._file = handle
            self._session_path = str(destination)
            return self._session_path

    def clear_session_file(self) -> None:
        with self._lock:
            self._close_file()
            self._session_path = ""

    def close(self) -> None:
        with self._lock:
            self._close_file()

    def write(self, line: str) -> None:
        """Show one received line. Disabled output and authentication lines are skipped."""
        if not isinstance(line, str) or is_authentication_detail(line):
            return
        with self._lock:
            if not self._enabled:
                return
            console = self._console
            handle = self._file
            try:
                if handle is not None:
                    handle.write(line + "\n")
                    handle.flush()
            except OSError as exc:
                logger.warning("Gameplay output was not written: %s", exc.__class__.__name__)
        try:
            console(line)
        except Exception as exc:
            logger.warning("Gameplay output was not printed: %s", exc.__class__.__name__)

    def _close_file(self) -> None:
        handle = self._file
        self._file = None
        if handle is not None:
            handle.close()


def is_authentication_detail(line: str) -> bool:
    """True for the logon command and lines that carry a token or auth field."""
    text = line.strip().lower()
    if text == "logon" or text.startswith("logon "):
        return True
    return any(marker in text for marker in _AUTH_MARKERS)


def _default_console(line: str) -> None:
    print(line, flush=True)
