import json
import logging

from typing import Callable, Iterable, Optional

from memory.WorkingMemory import WorkingMemory
from net.rest.OllamaClient import OllamaClient, OllamaError
from play.CategoryLesson import CategoryLesson
from play.CommandChannel import CommandChannel
from play.CommandLesson import CommandLesson
from play.HelpLesson import HelpLesson
from play.HelpReader import HelpReader, parse_command_names, parse_help
from play.PlayError import PromptTimeout
from play.WorldKnowledge import HelpArticle, RoomItem, RoomSnapshot, WorldKnowledge
from play.WorldReader import WorldReader
from prompt.Prompt import Prompt
from prompt.PromptSubmission import PromptSubmission

logger = logging.getLogger(__name__)


class Bootstrapper:
    """Build the agent's first picture of the game after a successful logon.

    Command categories come from the bare `help` index first. A command the
    index does not list is categorized from its own help page.
    """

    def __init__(self, session, agent_character_names: Iterable[str], self_character: str,
                 channel: Optional[CommandChannel] = None, help_reader: Optional[HelpReader] = None,
                 world_reader: Optional[WorldReader] = None, memory: Optional[WorkingMemory] = None,
                 replace_existing: str = "Y", on_commands: Optional[Callable[[WorldKnowledge], None]] = None,
                 prompts: Optional[dict] = None, ollama: Optional[OllamaClient] = None, defer: bool = False):
        self.channel = channel or CommandChannel(session.client, replace_existing=replace_existing)
        self.agent_character_names = {name.strip().lower() for name in agent_character_names if
                                      name and str(name).strip()}
        self.self_character = self_character.strip()
        self.help_reader = help_reader or HelpReader()
        self.world_reader = world_reader or WorldReader()
        self.memory = memory if memory is not None else WorkingMemory()
        self.knowledge = WorldKnowledge()
        self._on_commands = on_commands
        self._prompts = {str(name).strip().lower(): prompt for name, prompt in (prompts or {}).items()}
        self._ollama = ollama
        self._defer = defer

    def bootstrap(self) -> WorldKnowledge:
        self.knowledge.login_lines = self.channel.read_until_prompt()
        if not self.channel.saw_prompt:
            raise PromptTimeout("No playing prompt after logon.", self.knowledge.login_lines)
        self.memory.replace_commands([])
        if self._defer or not self._can_learn_commands():
            if self._defer:
                logger.info("Deferring Ollama requests. Server help is stored on world knowledge.")
            self._read_server_help()
        else:
            self._learn_command_knowledge()

        logger.info("Reading areas, players, and the current room.")
        for area in self.world_reader.read_areas(self.channel):
            self.knowledge.remember_area(area)
        for player in self.world_reader.read_players(self.channel, self.agent_character_names, self.self_character):
            self.knowledge.remember_player(player)
        look_lines = self.channel.exchange("look")
        self._observe_room(look_lines)
        if not self._defer:
            self._send_room_prompts(look_lines)
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
        if self._defer:
            logger.info("Deferring the commands prompt.")
            self._publish_commands()
            return CommandLesson(prompt={}, response="", commands=names)
        submission = _commands_submission(prompt, "\n".join(lines))
        request = submission.to_request()
        try:
            response = client.complete(request)
            error = ""
        except OllamaError as exc:
            response = ""
            error = str(exc)
        self._commit_ollama()
        return CommandLesson(prompt=request, response=response, commands=names, error=error)

    def learn_categories(self, prompt: Prompt, client: OllamaClient) -> CategoryLesson:
        """Read bare `help` and store each listed command's category.

        The user message is the server text. The system text and schema come
        from the `categories` prompt. A category already stored is left in place.
        """
        logger.info("Reading command categories from the help index.")
        lines = self.channel.exchange("help")
        if self._defer:
            logger.info("Deferring the categories prompt.")
            return CategoryLesson(prompt={}, response="")
        try:
            request = _submission(prompt, "\n".join(lines), "{categories}").to_request()
        except ValueError as exc:
            return CategoryLesson(prompt={}, response="", error=str(exc))
        try:
            response = client.complete(request)
            error = ""
        except OllamaError as exc:
            response = ""
            error = str(exc)
        lesson = CategoryLesson(prompt=request, response=response, error=error)
        parsed, _parse_error = lesson.parsed_categories()
        if parsed:
            self._remember_categories(parsed)
        self._commit_ollama()
        return lesson

    def learn_help(self, prompt: Prompt, client: OllamaClient, names: list[str] | None = None, on_lesson=None) -> list[HelpLesson]:
        """Read `help` for each command and store the help prompt's topics.

        The user message is the server page. The system text and schema come from
        the `help` prompt. A command the columnar list omitted still gets a page
        when it is already stored. When its category is empty, that request also
        asks for one category. Each raw model response is kept for prompt review.
        """
        command_names = self.commands_for_help(names)
        categories = _known_categories(self.memory)
        lessons = []
        total = len(command_names)
        for index, name in enumerate(command_names, start=1):
            logger.info("Reading help for %s (%s/%s).", name, index, total)
            current = self.memory.command_named(name)
            needs_category = current is None or not current.category.strip()
            lines = self.channel.exchange(f"help {name}")
            if self._defer:
                self._remember_server_help(name, lines)
                lessons.append(HelpLesson(command=name, prompt={}, response=""))
                if on_lesson is not None:
                    on_lesson(lessons[-1])
                continue
            lesson = _ask_help(prompt, client, name, lines, categories if needs_category else None)
            self._remember_help(name, lines, lesson)
            if needs_category:
                category, _category_error = lesson.parsed_category()
                if category:
                    self.memory.remember_command(name, category=category)
            lessons.append(lesson)
            if on_lesson is not None:
                on_lesson(lesson)
        self._commit_ollama()
        return lessons

    def commands_for_help(self, listed: list[str] | None = None) -> list[str]:
        """Names to read with `help`, in the order their pages should be fetched.

        The columnar `commands` list comes first. A command already stored from
        the help index and missing from that list, such as `!`, is appended.
        Passing no list uses every command already in working memory.
        """
        names = []
        seen: set[str] = set()
        for name in listed or []:
            token = name.strip().lower()
            if not token or token in seen:
                continue
            seen.add(token)
            names.append(token)
        for command in self.memory.commands():
            if command.name not in seen:
                seen.add(command.name)
                names.append(command.name)
        return names

    def _remember_categories(self, categories: list[dict]) -> None:
        for category in categories:
            for name in category["commands"]:
                current = self.memory.command_named(name)
                if current is not None and current.category.strip():
                    continue
                self.memory.remember_command(name, category=category["name"])

    def _remember_server_help(self, name: str, lines: list[str]) -> None:
        """Store one server help page without asking Ollama."""
        topic = parse_help(name, lines)
        self.knowledge.remember_help(topic)
        self.memory.remember_command(name, help_text=topic.text)

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
        if self._defer:
            self.knowledge.remember_help(topic)

    def _commit_ollama(self) -> None:
        """Persist server command help when bootstrap.defer is true. A false setting leaves model results on working memory."""
        if self._defer:
            self._publish_commands()

    def _publish_commands(self) -> None:
        """Copy the session command list onto world knowledge and persist it when a saver is installed."""
        self.knowledge.replace_commands(self.memory.commands())
        for command in self.knowledge.command_records():
            if command.help_text.strip():
                continue
            topic = self.knowledge.help_for(command.name)
            if topic is not None and str(topic.text or "").strip():
                command.help_text = topic.text.strip()
        if self._on_commands is not None:
            self._on_commands(self.knowledge)

    def _can_learn_commands(self) -> bool:
        """True when the live command bootstrap can run: categories, commands, help, and Ollama."""
        return self._ollama is not None and all(name in self._prompts for name in ("categories", "commands", "help"))

    def _learn_command_knowledge(self) -> None:
        """The same order as the live command bootstrap.

        Bare `help` supplies categories. `commands` adds the columnar list
        without clearing those categories. `help <name>` then covers that list
        plus any index command the list omitted, and stores each extracted topic.
        """
        self.learn_categories(self._prompts["categories"], self._ollama)
        lesson = self.learn_commands(self._prompts["commands"], self._ollama)
        self.learn_help(self._prompts["help"], self._ollama, names=self.commands_for_help(lesson.commands))

    def _read_server_help(self) -> None:
        """Store the server command list and each help page without asking Ollama."""
        command_names = self._remember_commands()
        logger.info("Reading help for the commands the server made available.")
        for topic in self.help_reader.read_named(self.channel, command_names):
            self.knowledge.remember_help(topic)
        self._publish_commands()
        for command in self.knowledge.command_records():
            if command.help_text.strip():
                self.memory.remember_command(command.name, help_text=command.help_text)

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

    def _send_room_prompts(self, lines: list[str]) -> None:
        """Send the printed room as the user text of the room prompts."""
        if self._defer or self._ollama is None:
            return
        text = "\n".join(lines)
        for name in _ROOM_PROMPTS:
            prompt = self._prompts.get(name)
            if prompt is None:
                continue
            try:
                request = prompt.for_text(text).to_request()
            except ValueError as exc:
                logger.warning("Room prompt %s was not sent: %s", name, exc)
                continue
            logger.info("Sending the room printout as the user prompt for %s.", name)
            try:
                response = self._ollama.complete(request)
            except OllamaError as exc:
                logger.warning("Room prompt %s failed: %s", name, exc)
                continue
            if name == "look":
                self._remember_look_items(response)

    def _remember_look_items(self, response: str) -> None:
        """Store the look prompt's items on the session room.

        A sign named in the description is one of those items. Later play
        reads the saved room instead of asking the model again.
        """
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            logger.warning("Room prompt look was not stored: the response was not JSON.")
            return
        if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
            logger.warning("Room prompt look was not stored: the response did not list items.")
            return
        room = self.knowledge.room
        observed = str(room.name or "").strip() if room is not None else ""
        name = observed or str(parsed.get("name") or "").strip()
        if not name:
            return
        description = str(room.description or "") if observed else str(parsed.get("description") or "")
        exits = list(room.exits or []) if observed else [str(exit_name) for exit_name in parsed.get("exits") or []]
        session_room = self.memory.remember_room(name, description=description, exits=exits or None, items=parsed["items"])
        if not self._defer:
            return
        snapshot = self.knowledge.room
        if snapshot is None:
            snapshot = RoomSnapshot(name=name, description=description, exits=list(exits))
            self.knowledge.room = snapshot
        snapshot.items = [RoomItem(name=item.name, line=item.line, source=item.source) for item in session_room.items]
        self._publish_commands()


def _commands_submission(prompt: Prompt, command_text: str) -> PromptSubmission:
    return _submission(prompt, command_text, "{commands}")


def _ask_help(prompt: Prompt, client: OllamaClient, command: str, lines: list[str],
              categories: list[str] | None = None) -> HelpLesson:
    requested = categories is not None
    try:
        request = _submission(prompt, "\n".join(lines), "{help}").to_request()
    except ValueError as exc:
        return HelpLesson(command=command, prompt={}, response="", error=str(exc), category_requested=requested)
    if requested:
        request = _with_category(request, command, categories)
    try:
        response = client.complete(request)
        error = ""
    except OllamaError as exc:
        response = ""
        error = str(exc)
    return HelpLesson(command=command, prompt=request, response=response, error=error, category_requested=requested)


def _with_category(request: dict, command: str, categories: list[str]) -> dict:
    body = dict(request)
    system = body.get("system") if isinstance(body.get("system"), str) else ""
    body["system"] = system.rstrip() + "\n\n" + _category_instruction(command, categories)
    schema = json.loads(json.dumps(body.get("jsonSchema") or {"type": "object"}))
    properties = schema.setdefault("properties", {})
    properties["category"] = {"type": "string"}
    required = schema.setdefault("required", [])
    if "category" not in required:
        required.append("category")
    body["jsonSchema"] = schema
    return body


def _category_instruction(command: str, categories: list[str]) -> str:
    lines = ["The category for this command is not known yet.", f"The command name is {command}."]
    if categories:
        lines.append("Choose exactly one of these category names and copy it exactly: " + ", ".join(categories) + ".")
        lines.append("Do not invent a category name.")
    else:
        lines.append("Choose a short category name for this command.")
    lines.append('Add a "category" string to the JSON object.')
    lines.append(
        'If the page is exactly "No help on that word.", return missing true, an empty topics list, and the category.')
    lines.append("If the page has help text, return the topics and the category.")
    return "\n".join(lines)


def _known_categories(memory: WorkingMemory) -> list[str]:
    names = []
    seen: set[str] = set()
    for command in memory.commands():
        category = command.category.strip().lower()
        if category and category not in seen:
            seen.add(category)
            names.append(category)
    return names


_ROOM_PROMPTS = ("look", "items", "exits", "mobs")


def _submission(prompt: Prompt, server_text: str, placeholder: str) -> PromptSubmission:
    """The user message is the server text. A sample stored on the prompt is not sent."""
    submission = prompt.for_text(server_text)
    if placeholder in prompt.user and placeholder in submission.user:
        raise ValueError(f"Prompt '{prompt.name}' did not fill {placeholder}.")
    return submission


def _help_text(articles: list[HelpArticle]) -> str:
    if len(articles) == 1:
        return articles[0].text.strip() or articles[0].keyword
    return "\n\n".join(f"{article.keyword}\n{article.text}".strip() for article in articles)
