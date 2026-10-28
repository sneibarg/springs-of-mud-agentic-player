import socket

from cli.ControlProtocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    UNKNOWN_COMMAND,
    accepted_command,
    encode_request,
    read_reply,
    require_loopback,
)


class UnknownCommand(ValueError):
    """The CLI refused to send a command it does not know."""


class ControlClient:
    """One-shot invoker. A raw TCP socket to 127.0.0.1 sends one known command."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout_s: float = 5.0):
        self.host = require_loopback(host)
        self.port = int(port)
        self.timeout_s = timeout_s

    def invoke(self, line: str) -> str:
        command = accepted_command(line)
        if command is None:
            raise UnknownCommand(UNKNOWN_COMMAND)
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(self.timeout_s)
        try:
            connection.connect((self.host, self.port))
            connection.sendall(encode_request(command))
            return read_reply(connection)
        finally:
            connection.close()
