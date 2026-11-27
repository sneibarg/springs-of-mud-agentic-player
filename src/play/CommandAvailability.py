from memory.WorkingMemory import WorkingMemory
from play.CommandChannel import CommandChannel
from play.ObservationPipeline import ObservationPipeline
from play.PlayError import PlayError, PromptTimeout
from play.WorldKnowledge import WorldKnowledge


def restore_commands(channel: CommandChannel, memory: WorkingMemory, knowledge: WorldKnowledge) -> None:
    """Restore descriptions, then verify availability once for this logged-on session."""
    memory.session.clear_command_availability()
    knowledge.commands.replace(memory.command_knowledge.merged_with(knowledge.commands).records())
    memory.command_knowledge = knowledge.commands
    observations = ObservationPipeline(memory, knowledge)
    try:
        lines = channel.read_until_prompt()
    except PlayError as exc:
        observations.receive(exc.lines, "login", origin="restore", complete=False)
        raise
    observations.receive(lines, "login", origin="restore", prompt=channel.last_prompt, complete=channel.saw_prompt)
    if not channel.saw_prompt:
        raise PromptTimeout("No playing prompt before command availability verification.")
    try:
        lines = channel.exchange("commands")
    except PlayError as exc:
        observations.receive(exc.lines, "commands", origin="restore", complete=False)
        raise
    record = observations.receive(lines, "commands", origin="restore", prompt=channel.last_prompt)
    names = record.payload["available"]
    for name in names:
        command = knowledge.commands.named(name)
        topic = knowledge.help_for(name)
        if command is not None and not command.help_text and topic is not None:
            knowledge.remember_command(name, help_text=topic.text or "")
    memory.session.last_prompt = channel.last_prompt
