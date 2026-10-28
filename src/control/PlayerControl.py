import logging
import threading

from typing import Callable, Optional

from cli.ControlProtocol import UNKNOWN_COMMAND, accepted_command
from control.GameplayOutput import GameplayOutput
from memory.WorkingMemory import WorkingMemory
from net.AccountSession import AccountSession


logger = logging.getLogger(__name__)


class PlayerControl:
    """Operator commands for one agent process.

    `handle` accepts `idle`, `play`, `memory`, `output`, `connect`, `list`, and
    `logon`. The production caller is the localhost control socket. `start`
    reads the same commands from an injected reader. The mode changes for
    `idle` and `play`. `drive` runs on the caller thread and invokes `on_play`
    once, the first time the mode is play. `connect` logs in a saved account.
    `logon` accepts only a character from that account. `memory` and `output`
    do not change the mode.
    """

    IDLE = "idle"
    PLAY = "play"
    MEMORY = "memory"
    OUTPUT = "output"
    CONNECT = "connect"
    LIST = "list"
    LOGON = "logon"
    DEFAULT_MEMORY_PATH = "working-memory.json"
    GREETING = "Idle. Commands: idle, play, memory, output, connect, list, logon."
    IDLE_REPLY = "Idle."
    PLAY_REPLY = "Play."
    UNKNOWN_REPLY = UNKNOWN_COMMAND

    def __init__(
        self,
        reader: Optional[Callable[[], str]] = None,
        writer: Optional[Callable[[str], None]] = None,
        memory: Optional[WorkingMemory] = None,
        memory_path: str = DEFAULT_MEMORY_PATH,
        output: Optional[GameplayOutput] = None,
        account: Optional[AccountSession] = None,
    ):
        self._reader = reader or _default_reader
        self._writer = writer or _default_writer
        self.memory = memory if memory is not None else WorkingMemory()
        self.memory_path = memory_path or self.DEFAULT_MEMORY_PATH
        self.output = output if output is not None else GameplayOutput()
        self.account = account
        self._mode = self.IDLE
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def mode(self) -> str:
        with self._condition:
            return self._mode

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    @property
    def thread(self) -> Optional[threading.Thread]:
        return self._thread

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._write(self.GREETING)
        self._thread = threading.Thread(target=self._listen, name="PlayerControl", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def drive(
        self,
        on_play: Callable[[], None],
        *,
        connected: Callable[[], bool] = lambda: True,
        wait_s: float = 0.2,
    ) -> None:
        """Block until stop or disconnect. `on_play` runs on this thread, once."""
        played = False
        while True:
            with self._condition:
                if self._stop.is_set() or not connected():
                    return
                if self._mode != self.PLAY or played:
                    self._condition.wait(wait_s)
                    continue
            on_play()
            played = True

    def _listen(self) -> None:
        try:
            while not self._stop.is_set():
                line = self._read_line()
                if line is None or self._stop.is_set():
                    break
                reply = self.handle(line)
                if reply:
                    self._write(reply)
        finally:
            self.stop()

    def _read_line(self) -> Optional[str]:
        try:
            line = self._reader()
        except EOFError:
            return None
        return line if isinstance(line, str) else None

    def handle(self, line: str) -> str:
        """Run one known command. Any other shape is rejected before dispatch."""
        command = accepted_command(line)
        if command is None:
            logger.info("Unknown control command.")
            return self.UNKNOWN_REPLY
        return self._dispatch(command)

    def _dispatch(self, line: str) -> str:
        parts = line.split(maxsplit=1)
        command = parts[0]
        argument = parts[1] if len(parts) > 1 else ""
        if command == self.MEMORY:
            return self._dump_memory(argument)
        if command == self.OUTPUT:
            return self._output(argument)
        if command == self.CONNECT:
            return self._connect(argument)
        if command == self.LIST:
            return self._list_characters()
        if command == self.LOGON:
            return self._logon(argument)
        with self._condition:
            if command == self.IDLE:
                self._mode = self.IDLE
                self._condition.notify_all()
                logger.info("Control mode is idle.")
                return self.IDLE_REPLY
            if command == self.PLAY:
                if self.account is not None and not self.account.logged_on:
                    return "Log on with an available character before play."
                self._mode = self.PLAY
                self._condition.notify_all()
                logger.info("Control mode is play.")
                return self.PLAY_REPLY
        logger.info("Unknown control command.")
        return self.UNKNOWN_REPLY

    def _dump_memory(self, argument: str) -> str:
        path = argument.strip() or self.memory_path
        try:
            written = self.memory.write_review(path)
        except (OSError, ValueError) as exc:
            logger.warning("Working memory was not written: %s", exc.__class__.__name__)
            return f"Memory was not written: {exc.__class__.__name__}"
        logger.info("Working memory written to %s.", written)
        return f"Memory written to {written}."

    def _connect(self, argument: str) -> str:
        if self.account is None:
            return "No saved connections are available."
        return self.account.connect(argument)

    def _list_characters(self) -> str:
        if self.account is None:
            return "Connect an account before listing characters."
        return self.account.list_characters()

    def _logon(self, argument: str) -> str:
        if self.account is None:
            return "Connect an account before logon."
        return self.account.logon(argument)

    def _output(self, argument: str) -> str:
        parts = argument.split(maxsplit=1)
        if not parts:
            return self._output_status()
        verb = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""
        if verb == "on":
            self.output.enable()
            return self._output_status()
        if verb == "off":
            self.output.disable()
            return self._output_status()
        if verb == "file":
            if rest.lower() == "off":
                self.output.clear_session_file()
                return self._output_status()
            return self._set_session_file(rest or self.output.default_session_path)
        logger.info("Unknown control command.")
        return self.UNKNOWN_REPLY

    def _set_session_file(self, path: str) -> str:
        try:
            self.output.set_session_file(path)
        except (OSError, ValueError) as exc:
            logger.warning("Session file was not opened: %s", exc.__class__.__name__)
            return f"Session file was not written: {exc.__class__.__name__}"
        return self._output_status()

    def _output_status(self) -> str:
        state = "Output on." if self.output.enabled else "Output off."
        path = self.output.session_path
        if path:
            return f"{state} Session file {path}."
        return state

    def _write(self, text: str) -> None:
        self._writer(text)


def _default_reader() -> str:
    return input()


def _default_writer(text: str) -> None:
    print(text, flush=True)
