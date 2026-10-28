import socket
import threading

from cli.ControlProtocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    UNKNOWN_COMMAND,
    accepted_command,
    encode_reply,
    read_request,
    require_loopback,
)


class ControlServer:
    """Localhost listener for the agent control thread.

    One daemon thread accepts one command at a time. The peer must be
    127.0.0.1. Unknown commands get a fixed rejection and are not handled.
    """

    def __init__(self, control, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.control = control
        self.host = require_loopback(host)
        self.port = int(port)
        self.bound_port = int(port)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self.host, self.port))
            listener.listen(1)
            listener.settimeout(0.2)
        except OSError:
            listener.close()
            raise
        self._socket = listener
        self.bound_port = listener.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, name="PlayerControl", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(2)

    def _serve(self) -> None:
        listener = self._socket
        if listener is None:
            return
        while not self._stop.is_set():
            try:
                connection, address = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self._exchange(connection, address)
            finally:
                connection.close()

    def _exchange(self, connection: socket.socket, address) -> None:
        if not address or address[0] != "127.0.0.1":
            return
        connection.settimeout(5)
        try:
            line = read_request(connection)
            command = accepted_command(line or "")
            if command is None:
                connection.sendall(encode_reply(UNKNOWN_COMMAND))
                return
            reply = self.control.handle(command)
            connection.sendall(encode_reply(reply or ""))
        except OSError:
            return
