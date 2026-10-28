import logging
import re
import time

from typing import Callable, Optional

from play.PlayError import AuthenticationRejected, CharacterSavePending, PromptTimeout, SessionDeclined


logger = logging.getLogger(__name__)

# Default playing prompt from springs-of-mud-server PromptFormat, for example <20hp 100m 100mv>.
_PROMPT = re.compile(r"^<[^>\n]*\d+\s*hp\b[^>]*>$", re.IGNORECASE)
_PAGER = "[hit enter to continue]"
_REPLACE = "do you wish to connect anyway"
_REPLACE_AGAIN = "please type y or n"
_SAVING = "that character is being saved"
_REJECTED = (
    "authentication failed",
    "invalid authentication message",
    "your site has been banned from this mud",
)


def is_prompt(line: str) -> bool:
    return _PROMPT.match(line.strip()) is not None


def _server_text(line: str) -> str:
    text = line.strip()
    if text.lower().startswith("error:"):
        text = text.split(":", 1)[1].strip()
    return text


class CommandChannel:
    """Send one game command and collect telnet lines until the playing prompt returns.

    Also answers the server login and paging gates that arrive before that prompt.
    `replace_existing` is sent when the character is already playing. `Y` takes the link.
    `N` declines it and raises SessionDeclined.
    """

    def __init__(
        self,
        client,
        timeout_s: float = 5.0,
        poll_interval_s: float = 0.05,
        replace_existing: str = "Y",
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
    ):
        self.client = client
        self.timeout_s = timeout_s
        self.poll_interval_s = poll_interval_s
        self.replace_existing = _yes_or_no(replace_existing)
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self.saw_prompt = False

    def exchange(self, command: str, timeout_s: Optional[float] = None) -> list[str]:
        self.client.send_line(command)
        lines = self.read_until_prompt(timeout_s)
        if not self.saw_prompt:
            raise PromptTimeout(f"No playing prompt after {command}.", lines)
        return lines

    def read_until_prompt(self, timeout_s: Optional[float] = None) -> list[str]:
        wait_s = self.timeout_s if timeout_s is None else timeout_s
        lines: list[str] = []
        deadline = self._clock() + wait_s
        self.saw_prompt = False
        while self._clock() < deadline:
            line = self.client.poll_line()
            if line is None:
                if not getattr(self.client, "connected", True):
                    break
                self._sleep(self.poll_interval_s)
                continue
            if is_prompt(line):
                self.saw_prompt = True
                break
            if self._answer_gate(line):
                deadline = self._clock() + wait_s
                continue
            lines.append(line)
            deadline = self._clock() + wait_s
        return lines

    def _answer_gate(self, line: str) -> bool:
        text = _server_text(line).lower()
        if text.startswith(_PAGER):
            logger.debug("Acknowledging a paged message.")
            self.client.send_line("")
            return True
        if _REPLACE in text or text.startswith(_REPLACE_AGAIN):
            logger.info("Character is already playing. Sending %s.", self.replace_existing)
            self.client.send_line(self.replace_existing)
            if self.replace_existing == "N":
                raise SessionDeclined("Declined to replace the playing character.", [line])
            return True
        if text.startswith(_SAVING):
            raise CharacterSavePending(_server_text(line), [line])
        if any(text.startswith(phrase) for phrase in _REJECTED):
            raise AuthenticationRejected(_server_text(line), [line])
        return False


def _yes_or_no(value: str) -> str:
    answer = str(value or "").strip().lower()
    if answer.startswith("y"):
        return "Y"
    if answer.startswith("n"):
        return "N"
    raise ValueError("replace_existing must be Y or N")
