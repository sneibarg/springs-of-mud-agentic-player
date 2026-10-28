class PlayError(Exception):
    """The telnet session cannot continue into play."""

    def __init__(self, message: str, lines: list[str] | None = None):
        super().__init__(message)
        self.lines = list(lines or [])


class AuthenticationRejected(PlayError):
    pass


class CharacterSavePending(PlayError):
    pass


class SessionDeclined(PlayError):
    pass


class PromptTimeout(PlayError):
    pass
