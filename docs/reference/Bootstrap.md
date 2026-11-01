# First Login Knowledge

`Bootstrapper.bootstrap()` runs when the operator command is `play` after `logon`. It learns only from text the game server sends. The logged-on character is the one named in `logon`, and that name must be one returned for the connected account.

`CommandChannel` answers these gates before treating a reply as finished:

- `Do you wish to connect anyway (Y/N)?` and `Please type Y or N?` get `telnet.replace_existing` from `resources/agent.yml`. `Y` takes the existing link. `N` stops the session.
- `That character is being saved. Please reconnect in a moment.` stops the session.
- `Authentication failed.`, `Invalid authentication message.`, and a site ban stop the session. The server sends these as `ERROR: ` lines.
- `[Hit Enter to continue]` is acknowledged with an empty line and is left out of the stored text.

A normal reply ends on a playing prompt such as `<20hp 100m 100mv>`. The next command is sent only after that prompt. An idle timeout with no prompt raises `PromptTimeout`.

1. Drain the login burst until the playing prompt. Keep those lines on `WorldKnowledge.login_lines`.
2. Send `commands`. Remember those names, in that order, on the session `WorkingMemory`. For each name, send `help <name>` and store a `HelpTopic`. `learn_categories` runs before that list: it sends bare `help`, asks the `categories` prompt to read the two-column index, and stores each command's category on working memory. A category already stored is left in place. `learn_commands` then remembers the `commands` list without clearing those categories. `learn_help` sends `help <name>` for each command in that list, and also for a command the help index stored that the list omitted, such as `!`. When the command already has a category, the `help` prompt is sent unchanged. When it does not, that request also asks for one category chosen from the names already stored. The model's topics are stored on the `HelpTopic` and as the session command's `help_text`. A page with no help still receives a category. `bootstrap()` does not call these Ollama steps.
3. Send `areas` and store `AreaRecord` entries from the two-column, 39-character layout (`[level] author: name`).
4. Send `who` and store `PlayerRecord` entries. A player is `agentic` when the character name matches an agent document. The logged-in character is `self_character`.
5. Send `look`. Store the room, exits, and item lines. Classify people in the room:
   - a name that matches `who` is a player, and the record gains `room_name`
   - a proper name that is not in `who` is an NPC
   - an article-led description (`a`, `an`, `the`, `some`) is a mobile

When the command help pages are stored, bootstrap copies the session commands onto `WorldKnowledge` and saves that document immediately. Each stored command is `name`, `category`, and `helpText`, in the order the server listed `commands`. A blank help text is filled from the matching `HelpTopic`. `learn_categories`, `learn_commands`, and `learn_help` save the same command list when they update it. The areas, who, and look snapshot is saved again afterward and still includes those commands.

The first `play` after logon runs bootstrap when the character has no stored commands. A later `play`, including the next time the process starts, loads world knowledge. When that document has a command list, or help topics from a document saved before commands were stored, working memory replaces its command list from those records and bootstrap does not run. The stored room and players are left out of the session. A missing document, or one with neither commands nor help topics, runs bootstrap. A failed knowledge load is reported and does not bootstrap. The control command `bootstrap` runs bootstrap again after logon, including when commands are already stored.

`CommandChannel` uses the telnet client and does not open its own socket. Later play decisions read `WorldKnowledge`. They do not scrape the telnet client directly.
