import re

from play.CommandChannel import CommandChannel, is_prompt
from play.WorldKnowledge import HelpTopic


_COMMAND_NAME = re.compile(r"[a-z][a-z']*")
_NO_HELP = "no help on that word"


class HelpReader:
    """Read the command list, then the help page for every command the server offered."""

    def read(self, channel: CommandChannel) -> list[HelpTopic]:
        return self.read_named(channel, parse_command_names(channel.exchange("commands")))

    def read_named(self, channel: CommandChannel, names: list[str]) -> list[HelpTopic]:
        return [parse_help(name, channel.exchange(f"help {name}")) for name in names]


def parse_command_names(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for line in lines:
        if is_prompt(line):
            continue
        for token in line.split():
            command = token.strip().lower()
            if not _COMMAND_NAME.fullmatch(command) or command in seen:
                continue
            seen.add(command)
            names.append(command)
    return names


def parse_help(command: str, lines: list[str]) -> HelpTopic:
    raw = "\n".join(lines)
    body = [line.strip() for line in lines if line.strip() and not is_prompt(line)]
    if not body or body[0].lower().startswith(_NO_HELP):
        return HelpTopic(command=command, keyword="", text="", raw=raw)
    return HelpTopic(command=command, keyword=body[0], text="\n".join(body[1:]).strip(), raw=raw)
