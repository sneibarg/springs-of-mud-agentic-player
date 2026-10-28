from typing import Optional


# The control thread and the CLI both accept only these shapes.
# Transport is one command line, then a decimal byte length and that many reply bytes.

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9711
MAX_COMMAND_BYTES = 1024
MAX_REPLY_BYTES = 262144
UNKNOWN_COMMAND = "Unknown command."


def require_loopback(host: str) -> str:
    """Control traffic stays on this machine."""
    cleaned = str(host or "").strip().lower()
    if cleaned in {"localhost", "127.0.0.1"}:
        return DEFAULT_HOST
    raise ValueError("Control host must be localhost")


def accepted_command(line: str) -> Optional[str]:
    """Return the canonical command, or None when the line is not allowed."""
    parts = str(line or "").strip().split()
    if not parts:
        return None
    verb = parts[0].lower()
    args = parts[1:]
    if verb in {"idle", "play", "list"}:
        return verb if not args else None
    if verb == "connect":
        return "connect " + " ".join(args) if args else None
    if verb == "logon":
        return "logon " + " ".join(args) if args else None
    if verb == "memory":
        return "memory" if not args else "memory " + " ".join(args)
    if verb == "output":
        return _output_command(args)
    return None


def encode_request(command: str) -> bytes:
    payload = command.encode("utf-8")
    if len(payload) > MAX_COMMAND_BYTES:
        raise ValueError(UNKNOWN_COMMAND)
    return payload + b"\n"


def encode_reply(text: str) -> bytes:
    payload = (text or "").encode("utf-8")
    if len(payload) > MAX_REPLY_BYTES:
        payload = payload[:MAX_REPLY_BYTES]
    return f"{len(payload)}\n".encode("ascii") + payload


def read_request(sock) -> Optional[str]:
    """Read one command line from a connected socket. None means it is not a command."""
    data = bytearray()
    while b"\n" not in data:
        if len(data) > MAX_COMMAND_BYTES:
            return None
        chunk = sock.recv(min(256, MAX_COMMAND_BYTES - len(data) + 1))
        if not chunk:
            return None
        data.extend(chunk)
    line = bytes(data).split(b"\n", 1)[0]
    try:
        return line.decode("utf-8")
    except UnicodeDecodeError:
        return None


def read_reply(sock) -> str:
    """Read one length-prefixed reply from a connected socket."""
    header = bytearray()
    while b"\n" not in header:
        if len(header) > 16:
            raise ValueError("Control reply was not framed")
        chunk = sock.recv(1)
        if not chunk:
            raise ValueError("Control closed the connection")
        header.extend(chunk)
    length_text = bytes(header).split(b"\n", 1)[0]
    if not length_text.isdigit():
        raise ValueError("Control reply was not framed")
    length = int(length_text)
    if length > MAX_REPLY_BYTES:
        raise ValueError("Control reply was not framed")
    payload = bytearray()
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            raise ValueError("Control closed the connection")
        payload.extend(chunk)
    return bytes(payload).decode("utf-8", errors="replace")


def _output_command(args: list[str]) -> Optional[str]:
    if not args:
        return "output"
    head = args[0].lower()
    if head in {"on", "off", "file"} and len(args) == 1:
        return "output " + head
    if head == "file" and len(args) == 2 and args[1].lower() == "off":
        return "output file off"
    if head == "file" and len(args) >= 2:
        return "output file " + " ".join(args[1:])
    return None
