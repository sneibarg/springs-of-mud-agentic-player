import argparse
import sys

from cli.ControlClient import ControlClient, UnknownCommand
from cli.ControlProtocol import DEFAULT_HOST, DEFAULT_PORT


USAGE = (
    "Usage: python -m cli [--port PORT] <command>\n"
    "Commands: idle, play, list, connect <name>, logon <name>, "
    "memory [path], output [on|off|file [off|path]]"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cli", description="Send one command to the local agent control.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Must be localhost")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    line = " ".join(args.command).strip()
    if not line:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        client = ControlClient(args.host, args.port)
        reply = client.invoke(line)
    except UnknownCommand as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError:
        print(f"Control is not listening on 127.0.0.1:{args.port}.", file=sys.stderr)
        return 1
    print(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
