from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
from typing import Callable, Optional

import socket
import threading

IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250
SE = 240


@dataclass(frozen=True)
class TelnetConfig:
    host: str
    port: int = 6969
    connect_timeout_s: float = 5.0
    recv_buf: int = 4096
    keepalive: bool = True


class TelnetClient:
    """Threaded telnet client. Negotiation defaults match springs-of-mud-ui."""

    def __init__(self, cfg: TelnetConfig, *, on_status: Optional[Callable[[str], None]] = None):
        self.cfg = cfg
        self._on_status = on_status
        self._sock: Optional[socket.socket] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._in_lines: "Queue[str]" = Queue()
        self._out_lock = threading.Lock()
        self._text_buf = bytearray()
        self._last_text_was_cr = False
        self._iac_state = 0
        self._iac_cmd = 0
        self._sb_opt = 0
        self._sb_buf = bytearray()

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> None:
        if self.connected:
            return

        self._stop.clear()
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(self.cfg.connect_timeout_s)
        connection.connect((self.cfg.host, self.cfg.port))
        connection.settimeout(None)

        if self.cfg.keepalive:
            try:
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except OSError:
                pass

        self._sock = connection
        self._rx_thread = threading.Thread(target=self._rx_loop, name="TelnetClient.rx", daemon=True)
        self._rx_thread.start()
        self._status(f"Connected to {self.cfg.host}:{self.cfg.port}")

    def close(self) -> None:
        if not self.connected:
            return
        self._status("Disconnecting...")
        self._stop.set()
        try:
            if self._sock:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._sock.close()
        finally:
            self._sock = None
        self._status("Disconnected")

    def send_line(self, text: str) -> None:
        if not self._sock:
            raise RuntimeError("Not connected")
        data = (text + "\r\n").encode("utf-8", errors="replace")
        with self._out_lock:
            self._sock.sendall(data)

    def poll_line(self) -> Optional[str]:
        try:
            return self._in_lines.get_nowait()
        except Empty:
            return None

    def _status(self, msg: str) -> None:
        if self._on_status:
            try:
                self._on_status(msg)
            except Exception:
                pass

    def _rx_loop(self) -> None:
        assert self._sock is not None
        connection = self._sock
        try:
            while not self._stop.is_set():
                data = connection.recv(self.cfg.recv_buf)
                if not data:
                    break
                self._feed(data)
        except OSError as exc:
            self._status(f"Socket error: {exc}")
        finally:
            if self._text_buf:
                self._emit_buffered_line()
            try:
                connection.close()
            except OSError:
                pass
            if self._sock is connection:
                self._sock = None
            self._status("Connection closed")

    def _feed(self, data: bytes) -> None:
        for byte in data:
            if self._iac_state == 0:
                if byte == IAC:
                    self._iac_state = 1
                else:
                    self._push_text_byte(byte)
                continue

            if self._iac_state == 1:
                if byte == IAC:
                    self._text_buf.append(IAC)
                    self._iac_state = 0
                elif byte == SB:
                    self._iac_state = 3
                    self._sb_opt = 0
                    self._sb_buf.clear()
                else:
                    self._iac_cmd = byte
                    self._iac_state = 2
                continue

            if self._iac_state == 2:
                self._handle_iac(self._iac_cmd, byte)
                self._iac_state = 0
                continue

            if self._iac_state == 3:
                if self._sb_opt == 0:
                    self._sb_opt = byte
                    continue
                if byte == IAC:
                    self._iac_state = 4
                    continue
                self._sb_buf.append(byte)
                continue

            if self._iac_state == 4:
                if byte == SE:
                    self._iac_state = 0
                else:
                    self._sb_buf.append(IAC)
                    self._sb_buf.append(byte)
                    self._iac_state = 3

    def _push_text_byte(self, byte: int) -> None:
        if byte == 13:
            self._emit_buffered_line()
            self._last_text_was_cr = True
            return
        if byte == 10:
            if self._last_text_was_cr:
                self._last_text_was_cr = False
                return
            self._emit_buffered_line()
            return
        self._last_text_was_cr = False
        self._text_buf.append(byte)

    def _emit_buffered_line(self) -> None:
        line = self._text_buf.decode("utf-8", errors="replace")
        self._in_lines.put(line)
        self._text_buf.clear()

    def _send_iac(self, cmd: int, opt: int) -> None:
        if not self._sock:
            return
        with self._out_lock:
            self._sock.sendall(bytes([IAC, cmd, opt]))

    def _handle_iac(self, cmd: int, opt: int) -> None:
        if cmd == WILL:
            self._send_iac(DONT, opt)
        elif cmd == DO:
            self._send_iac(WONT, opt)
