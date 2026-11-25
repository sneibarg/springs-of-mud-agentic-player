import logging
import re

from net.rest.KmAnswer import KmAnswer
from net.rest.KmClient import KmClient, KmError

logger = logging.getLogger(__name__)


class KmPlayer:
    """A stable KM situation shared by this account and character's runtime sessions."""

    def __init__(self, client: KmClient, account_name: str, character_name: str):
        self.client = client
        self.name = f"Player-{_component(account_name)}-{_component(character_name)}"

    def ensure(self) -> None:
        """Check every startup; declare only when missing, then verify the result."""
        expression = f"(in-situation *Global (the instance-of of *{self.name}))"
        answer = _checked(self.client.query(expression))
        if _is_player(answer):
            logger.info("Reusing KM player situation %s.", self.name)
            return
        if answer.answer.strip().lower() not in ("nil", "()"):
            raise KmError(f"KM instance {self.name} exists but is not a Som-Agentic-Player")
        _checked(self.client.assert_expression(f"(in-situation *Global (*{self.name} has (instance-of (Som-Agentic-Player))))"))
        if not _is_player(_checked(self.client.query(expression))):
            raise KmError(f"KM player situation {self.name} was not confirmed after creation")
        logger.info("Created KM player situation %s.", self.name)

    def query(self, expression: str) -> KmAnswer:
        return _checked(self.client.query_player(self.name, expression))

    def assert_expression(self, expression: str) -> KmAnswer:
        return _checked(self.client.assert_player(self.name, expression))


def _component(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KmError("KM player requires an account name and character name")
    # Encode separators and non-ASCII bytes so distinct identity pairs never collide.
    return "".join(chr(byte) if 48 <= byte <= 57 or 65 <= byte <= 90 or 97 <= byte <= 122 else f"_{byte:02x}" for byte in value.encode("utf-8"))


def _checked(answer: KmAnswer) -> KmAnswer:
    if not answer.ok or answer.errors:
        raise KmError(answer.message or "; ".join(answer.errors) or "KM player evaluation failed")
    return answer


def _is_player(answer: KmAnswer) -> bool:
    return "Som-Agentic-Player" in re.findall(r"[^\s()]+", answer.answer)
