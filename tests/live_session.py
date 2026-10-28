"""One live SpringsOfMUD session for integration tests.

The saved profile names localhost. som-auth-service answers on dragon at the
same port when localhost does not. Telnet stays on the profile host.
"""

import os
import socket
import sys
import time
import unittest
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.AccountSession import AccountSession
from net.rest.ConnectionCatalog import ConnectionCatalog
from play.CommandChannel import CommandChannel


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "SpringsOfMUD"
SKIP_REASON = f"{PROFILE} auth or telnet is not accepting connections."
QUIT_PHRASE = "Alas, all good things must come to an end."
PROMPT_TIMEOUT_S = 20.0
_AUTH_FALLBACK_HOST = "dragon"


def _tcp_open(host: str, port: int, timeout_s: float = 0.8) -> bool:
    if not host or port < 1:
        return False
    probe = socket.socket()
    probe.settimeout(timeout_s)
    try:
        probe.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _endpoint(url: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return parsed.hostname or "", parsed.port or default_port


def _auth_url(server_url: str) -> str:
    host, port = _endpoint(server_url, 8169)
    if _tcp_open(host, port):
        return server_url
    if host in {"localhost", "127.0.0.1"} and _tcp_open(_AUTH_FALLBACK_HOST, port):
        parsed = urlparse(server_url if "://" in server_url else f"http://{server_url}")
        scheme = parsed.scheme or "http"
        return f"{scheme}://{_AUTH_FALLBACK_HOST}:{port}"
    return ""


class LivePlay:
    """A logged-on character. `close` quits before it drops the socket."""

    def __init__(self, account: AccountSession, channel: CommandChannel):
        self.account = account
        self.channel = channel
        self.character = account.character
        self._quit = False

    def exchange(self, command: str) -> list[str]:
        return self.channel.exchange(command, timeout_s=PROMPT_TIMEOUT_S)

    def quit(self) -> list[str]:
        if self._quit:
            return []
        client = self.account.session.client
        client.send_line("quit")
        self._quit = True
        lines = []
        deadline = time.monotonic() + PROMPT_TIMEOUT_S
        while time.monotonic() < deadline:
            line = client.poll_line()
            if line is None:
                time.sleep(0.05)
                continue
            lines.append(line)
            if "all good things must come to an end" in line:
                return lines
        return lines

    def close(self) -> None:
        try:
            client = None
            if self.account.session is not None:
                client = self.account.session.client
            if not self._quit and client is not None and client.connected:
                try:
                    self.quit()
                except OSError:
                    try:
                        client.send_line("quit")
                        time.sleep(1)
                    except OSError:
                        pass
        finally:
            self.account.close()


def open_live_play() -> LivePlay | None:
    """Log on the lowest-level character. None means auth or telnet is closed."""
    catalog = ConnectionCatalog.load(ROOT / "resources" / "connections.json")
    saved = catalog.named(PROFILE)
    auth_url = _auth_url(saved.server_url or "http://localhost:8169")
    telnet_host = saved.telnet_host or "localhost"
    telnet_port = saved.telnet_port or 6969
    if not auth_url or not _tcp_open(telnet_host, telnet_port):
        return None

    account = AccountSession(
        ConnectionCatalog([replace(saved, server_url=auth_url)]),
        telnet_host=telnet_host,
        telnet_port=telnet_port,
    )
    try:
        connected = account.connect(PROFILE)
        if not connected.startswith("Connected as ") or "failed" in connected.lower():
            raise RuntimeError(connected)
        character = account.auth.lowest_level_character()
        logged = account.logon(character.name)
        if logged != f"Logged on as {character.name}.":
            raise RuntimeError(logged)
        channel = CommandChannel(account.session.client, timeout_s=PROMPT_TIMEOUT_S, replace_existing="Y")
        channel.read_until_prompt(PROMPT_TIMEOUT_S)
        if not channel.saw_prompt:
            raise RuntimeError("No playing prompt after logon.")
        return LivePlay(account, channel)
    except Exception:
        _abandon(account)
        raise


def require_live_play(test: unittest.TestCase) -> LivePlay:
    play = open_live_play()
    if play is None:
        test.skipTest(SKIP_REASON)
    return play


def _abandon(account: AccountSession) -> None:
    try:
        if account.session is not None and account.session.client.connected:
            try:
                account.session.client.send_line("quit")
                time.sleep(1)
            except OSError:
                pass
    finally:
        account.close()
