"""Project the currently available commands into one agentic player's situation.

The situation already partitions fluent values. Each command is a
`Som-Known-Command`, and `som-known-command` is one seq on that situation.
A blank category is left blank so the heading rule can apply the SUMMARY row.
A later observation replaces that seq with `now-has`, including an empty seq.
Stored descriptions alone do not populate the index.
"""

from memory.KnownCommand import KnownCommand
from memory.WorkingMemory import WorkingMemory
from play.WorldKnowledge import WorldKnowledge

from play.KmSyntax import _ABSENT, km_string as _km_string, one_line as _one_line, player_frame as _player_frame, symbol as _symbol, token as _token, unwrap as _unwrap


def available_commands(memory: WorkingMemory, knowledge: WorldKnowledge) -> list[KnownCommand]:
    """Project learned descriptions onto this session's observed server order."""
    if not memory.session.commands_observed:
        return []
    descriptions = memory.command_knowledge.merged_with(knowledge.commands)
    return [descriptions.named(command.name) or command for command in memory.session.available_commands.records()]


def assertion_forms(player_name: str, commands, *, previous: str | None = None) -> list[str]:
    """One has-form per command, then the situation seq. No in-situation wrapper."""
    rows = [command for command in list(commands or []) if command.name]
    player = _player_frame(player_name)
    forms = []
    frames = []
    for command in rows:
        frame, form = _command_form(command, replace_values=bool(str(previous or "").strip()))
        frames.append(frame)
        forms.append(form)
    seq = "(:seq " + " ".join(frames) + ")" if frames else "(:seq)"
    verb = "now-has" if str(previous or "").strip() else "has"
    forms.append(f"({player} {verb} (som-known-command ({seq})))")
    return forms


def assert_learned(player, memory, knowledge) -> list[str]:
    """Publish the available catalog; an observed empty list clears the prior index."""
    if not memory.session.commands_observed:
        return []
    commands = available_commands(memory, knowledge)
    forms = assertion_forms(player.name, commands, previous=_current_seq(player))
    for form in forms:
        player.assert_expression(form)
    return forms


def _command_form(command: KnownCommand, *, replace_values: bool = False) -> tuple[str, str]:
    frame = _frame(command.name)
    parts = ["(instance-of (Som-Known-Command))", f"(som-command-name ({_token(command.name)}))"]
    if command.category:
        parts.append(f"(som-command-category ({_token(command.category.lower())}))")
    help_text = _one_line(command.help_text)
    if help_text:
        parts.append(f"(som-command-help ({_km_string(help_text)}))")
    verb = "now-has" if replace_values else "has"
    return frame, f"({frame} {verb} {' '.join(parts)})"


def _current_seq(player) -> str | None:
    frame = _player_frame(player.name)
    answer = player.query(f"(the som-known-command of {frame})")
    text = str(getattr(answer, "answer", "") or "").strip()
    if text.lower() in _ABSENT:
        return None
    unwrapped = _unwrap(text)
    if unwrapped.lower() in _ABSENT:
        return None
    return unwrapped


def _frame(name: str) -> str:
    if _symbol(name):
        return f"*Cmd-{name}"
    return "*Cmd-" + "".join(f"{ord(character):02x}" for character in name)
