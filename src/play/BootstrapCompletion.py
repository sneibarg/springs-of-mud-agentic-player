import re

from net.rest.KmClient import KmError


class BootstrapCompletion:
    """Publish completion only after the collected evidence has been accepted."""

    def __init__(self, memory):
        self.memory = memory

    def reset(self, player) -> None:
        if player.name != self.memory.session.bootstrap.player_name:
            raise KmError("Bootstrap player does not match the collection attempt")
        self._assert(player, "f")
        self.memory.session.bootstrap.marker_reset = True

    def publish(self, player) -> bool:
        progress = self.memory.session.bootstrap
        if player.name != progress.player_name:
            raise KmError("Bootstrap player does not match the collection attempt")
        if progress.status == "complete":
            return True
        if not progress.ready(self.memory.session.evidence):
            return False
        if not progress.marker_reset:
            self.reset(player)
        self._assert(player, "t")
        progress.status = "complete"
        progress.error = ""
        return True

    def _assert(self, player, value: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", player.name):
            raise KmError("Invalid bootstrap player name")
        answer = player.assert_expression(f"(*{player.name} now-has (som-bootstrap ({value})))")
        if not answer.ok or answer.errors:
            raise KmError(answer.message or "; ".join(answer.errors) or "Bootstrap marker was not accepted")
