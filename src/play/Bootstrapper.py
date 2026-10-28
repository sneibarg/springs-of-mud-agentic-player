import json
import logging

from dataclasses import dataclass
from typing import Iterable, Optional

from memory.WorkingMemory import WorkingMemory
from net.rest.OllamaClient import OllamaClient, OllamaError
from play.CommandChannel import CommandChannel
from play.HelpReader import HelpReader, parse_command_names, parse_help
from play.PlayError import PromptTimeout
from play.WorldKnowledge import HelpArticle, WorldKnowledge
from play.WorldReader import WorldReader
from prompt.Prompt import Prompt, PromptSubmission


logger = logging.getLogger(__name__)


@dataclass
class CommandLesson:
    """One `commands` reading and the Ollama exchange that reviewed it.

    `prompt` is the completion body that was sent. `response` is the raw text
    the model returned. `commands` are the names remembered from the server text.
    """

    prompt: dict
    response: str
    commands: list[str]
    error: str = ""

    def parsed_commands(self) -> tuple[list[str] | None, str]:
        if self.error:
            return None, self.error
        if not self.response.strip():
            return None, "Ollama returned an empty response"
        try:
            parsed = json.loads(self.response)
        except json.JSONDecodeError as exc:
            return None, f"Ollama completion was not JSON: {exc}"
        names = parsed.get("commands") if isinstance(parsed, dict) else None
        if not isinstance(names, list) or not all(isinstance(name, str) and name.strip() for name in names):
            return None, "Ollama completion did not return a commands list"
        return [name.strip().lower() for name in names], ""

    def to_review(self) -> dict:
        parsed, parse_error = self.parsed_commands()
        document = {
            "prompt": self.prompt,
            "response": self.response,
            "commands": list(self.commands),
            "parsedCommands": parsed,
        }
        if self.error:
            document["error"] = self.error
        if parse_error and not self.error:
            document["parseError"] = parse_error
        return document


@dataclass
class HelpLesson:
    """One help page and the Ollama exchange that read it.

    `prompt` is the completion body that was sent. `response` is the raw text
    the model returned. The parsed topics are stored on world knowledge.
    """

    command: str
    prompt: dict
    response: str
    error: str = ""

    def parsed_help(self) -> tuple[dict | None, str]:
        if self.error:
            return None, self.error
        if not self.response.strip():
            return None, "Ollama returned an empty response"
        try:
            parsed = json.loads(self.response)
        except json.JSONDecodeError as exc:
            return None, f"Ollama completion was not JSON: {exc}"
        if not isinstance(parsed, dict):
            return None, "Ollama completion did not return a help document"
        missing = parsed.get("missing")
        topics = parsed.get("topics")
        if not isinstance(missing, bool) or not isinstance(topics, list):
            return None, "Ollama completion did not return help topics"
        cleaned = []
        for topic in topics:
            if not isinstance(topic, dict):
                return None, "Ollama completion did not return help topics"
            keyword = topic.get("keyword")
            text = topic.get("text")
            if not isinstance(keyword, str) or not keyword.strip() or not isinstance(text, str):
                return None, "Ollama completion did not return help topics"
            cleaned.append({"keyword": keyword.strip(), "text": text.strip()})
        if missing and cleaned:
            return None, "Ollama completion marked the help missing and also returned topics"
        if not missing and not cleaned:
            return None, "Ollama completion returned no help topics"
        return {"missing": missing, "topics": cleaned}, ""

    def to_review(self) -> dict:
        parsed, parse_error = self.parsed_help()
        document = {
            "command": self.command,
            "prompt": self.prompt,
            "response": self.response,
            "parsed": parsed,
        }
        if self.error:
            document["error"] = self.error
        if parse_error and not self.error:
            document["parseError"] = parse_error
        return document


class Bootstrapper:
    """Build the agent's first picture of the game after a successful logon.

    The command step only remembers the names from `commands` on working memory.
    Categorizing those commands from their help pages is a later phase.
    """

    def __init__(
        self,
        session,
        agent_character_names: Iterable[str],
        self_character: str,
        channel: Optional[CommandChannel] = None,
        help_reader: Optional[HelpReader] = None,
        world_reader: Optional[WorldReader] = None,
        memory: Optional[WorkingMemory] = None,
        replace_existing: str = "Y",
    ):
        self.channel = channel or CommandChannel(session.client, replace_existing=replace_existing)
        self.agent_character_names = {
            name.strip().lower() for name in agent_character_names if name and str(name).strip()
        }
        self.self_character = self_character.strip()
        self.help_reader = help_reader or HelpReader()
        self.world_reader = world_reader or WorldReader()
        self.memory = memory if memory is not None else WorkingMemory()
        self.knowledge = WorldKnowledge()

    def bootstrap(self) -> WorldKnowledge:
        self.knowledge.login_lines = self.channel.read_until_prompt()
        if not self.channel.saw_prompt:
            raise PromptTimeout("No playing prompt after logon.", self.knowledge.login_lines)
        command_names = self._remember_commands()
        logger.info("Reading help for the commands the server made available.")
        for topic in self.help_reader.read_named(self.channel, command_names):
            self.knowledge.remember_help(topic)

        logger.info("Reading areas, players, and the current room.")
        for area in self.world_reader.read_areas(self.channel):
            self.knowledge.remember_area(area)
        for player in self.world_reader.read_players(
            self.channel,
            self.agent_character_names,
            self.self_character,
        ):
            self.knowledge.remember_player(player)
        self._observe_room(self.channel.exchange("look"))
        return self.knowledge

    def learn_commands(self, prompt: Prompt, client: OllamaClient) -> CommandLesson:
        """Remember the `commands` list, then ask the commands prompt to read it.

        The user message is the server text. The system text and schema come from
        the `commands` prompt. The raw model text is kept for prompt review.
        """
        logger.info("Remembering the commands the server made available.")
        lines = self.channel.exchange("commands")
        names = parse_command_names(lines)
        self.memory.remember_commands(names)
        submission = _commands_submission(prompt, "\n".join(lines))
        request = submission.to_request()
        try:
            response = client.complete(request)
            error = ""
        except OllamaError as exc:
            response = ""
            error = str(exc)
        return CommandLesson(
            prompt=request,
            response=response,
            commands=[command.name for command in self.memory.commands()],
            error=error,
        )

    def learn_help(self, prompt: Prompt, client: OllamaClient, names: list[str] | None = None, on_lesson=None) -> list[HelpLesson]:
        """Read `help` for each command and store the help prompt's topics.

        The user message is the server page. The system text and schema come from
        the `help` prompt. Each raw model response is kept for prompt review.
        """
        command_names = list(names) if names is not None else [command.name for command in self.memory.commands()]
        lessons = []
        total = len(command_names)
        for index, name in enumerate(command_names, start=1):
            logger.info("Reading help for %s (%s/%s).", name, index, total)
            lines = self.channel.exchange(f"help {name}")
            lesson = _ask_help(prompt, client, name, lines)
            self._remember_help(name, lines, lesson)
            lessons.append(lesson)
            if on_lesson is not None:
                on_lesson(lesson)
        return lessons

    def _remember_help(self, name: str, lines: list[str], lesson: HelpLesson) -> None:
        topic = parse_help(name, lines)
        parsed, _parse_error = lesson.parsed_help()
        self.memory.remember_command(name)
        if parsed is None:
            self.knowledge.remember_help(topic)
            return
        articles = [HelpArticle(keyword=item["keyword"], text=item["text"]) for item in parsed["topics"]]
        topic.missing = parsed["missing"]
        topic.topics = articles
        if articles:
            topic.keyword = articles[0].keyword
            topic.text = _help_text(articles)
            self.memory.remember_command(name, help_text=topic.text)
        else:
            topic.keyword = ""
            topic.text = ""
        self.knowledge.remember_help(topic)

    def _remember_commands(self) -> list[str]:
        """Store the names from `commands`. This step does not categorize them."""
        logger.info("Remembering the commands the server made available.")
        names = parse_command_names(self.channel.exchange("commands"))
        self.memory.remember_commands(names)
        return names

    def _observe_room(self, lines: list[str]) -> None:
        observation = self.world_reader.read_room(lines, list(self.knowledge.players.values()))
        if observation.room.name or observation.room.description or observation.room.exits:
            self.knowledge.room = observation.room
        for being in observation.mobiles:
            self.knowledge.remember_mobile(being)
        for being in observation.npcs:
            self.knowledge.remember_npc(being)
        for player in observation.players_present:
            self.knowledge.note_player_seen(player.name, observation.room.name)


def _commands_submission(prompt: Prompt, command_text: str) -> PromptSubmission:
    return _submission(prompt, command_text, "{commands}")


def _ask_help(prompt: Prompt, client: OllamaClient, command: str, lines: list[str]) -> HelpLesson:
    try:
        request = _submission(prompt, "\n".join(lines), "{help}").to_request()
    except ValueError as exc:
        return HelpLesson(command=command, prompt={}, response="", error=str(exc))
    try:
        response = client.complete(request)
        error = ""
    except OllamaError as exc:
        response = ""
        error = str(exc)
    return HelpLesson(command=command, prompt=request, response=response, error=error)


def _submission(prompt: Prompt, server_text: str, placeholder: str) -> PromptSubmission:
    user = prompt.user
    if placeholder in user:
        user = user.replace(placeholder, server_text)
    else:
        user = server_text
    return PromptSubmission(
        name=prompt.name,
        model=prompt.model,
        system=prompt.system,
        user=user,
        json_schema=dict(prompt.json_schema),
        intents=(),
    )


def _help_text(articles: list[HelpArticle]) -> str:
    if len(articles) == 1:
        return articles[0].text.strip() or articles[0].keyword
    return "\n\n".join(f"{article.keyword}\n{article.text}".strip() for article in articles)
