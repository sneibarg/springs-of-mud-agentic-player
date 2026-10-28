# Repository Guidelines

## Project Direction

This repository is the Python runtime for Springs of MUD agentic player characters. An agent is a player that logs into the game server and plays a character on its own.

Game identity and persona live in the `Agents` collection. The long-term source is the `Agents` collection in the `SOMDB` MongoDB database. Until that database is wired in, load the same documents from `resources/collections/SOMDB.Agents.json`.

Add Python for the runtime: collection loading, auth, the telnet session, and later the decision loop. Put ordinary agent tuning in the collection document.

The companion server is `springs-of-mud-server`. The login and telnet behavior follows `springs-of-mud-ui/src/net`.

## Architecture Map

- `src/main.py` loads `resources/agent.yml`, reads the Agents snapshot, and listens on the local control socket. The agent starts idle. `play` bootstraps game knowledge once.
- `src/agent` owns `Agent`, `AgentCollection`, `AgentRegistry`, and `AgentConfig`.
- `src/control` owns `PlayerControl` and `GameplayOutput`. `handle` accepts `idle`, `play`, `memory`, `output`, `connect`, `list`, and `logon`.
- `src/cli` is the operator invoker. `python -m cli` sends one known command. `src/net/local/ControlServer` accepts it on `127.0.0.1`. The transport is one raw TCP socket.
- `src/net/AccountSession` connects a saved account and logs on with one character from that login.
- `src/play` owns the first-login `Bootstrapper`, `CommandChannel`, help and world readers, and `WorldKnowledge`.
- `src/memory` owns short-lived `WorkingMemory` for the current session: players, agentic players, mobiles, NPCs, rooms, `consider` readings, and aggressive mobiles. It is not part of the knowledge document.
- `src/prompt` loads `SOMDB.Prompts` and fills a prompt's tokens before that text is submitted to som-nlp-service.
- `src/net/rest` retrieves the auth token, saves world knowledge, and calls the Ollama service. `AuthClient` posts to `/api/auth/login` and stores the `Authorization` response header, matching `springs-of-mud-ui`. `KnowledgeClient` puts the knowledge snapshot to the agent-knowledge API. `OllamaClient` posts to `/ollama/completions`.
- `src/net/telnet` owns the telnet socket client and `PlayerSession`, which sends the server `logon` line.
- `src/util` holds small shared helpers such as camelCase normalization.
- `resources/agent.yml` holds auth URL, telnet host and port, the local control address, and the collection location.
- `resources/collections/SOMDB.Agents.json` is the current `SOMDB.Agents` snapshot.

## Collection Data

`SOMDB.Agents.json` is a JSON array of Mongo-style documents. Keep these names and shapes stable so the file can move into the `SOMDB` database collection `Agents` later:

- `_id.$oid` is the document id.
- `name` is the local agent name used by `--agent`.
- `accountName` is the account passed to `/api/auth/login`.
- `characterName` selects a character from the login response.
- `enabled` must be a boolean.
- `description` is designer-facing text.

Leave passwords, JWTs, and telnet hosts out of agent documents. Saved account passwords live in `resources/connections.json`, obfuscated with base64 the same way `springs-of-mud-ui` stores them. Deobfuscate a password only for the login call. Do not log it or write it back as plaintext.

Read this collection directly while it stays small. If it grows large, add a local query tool and use that tool before pasting documents into context.

## Authentication And Telnet

1. `connect <connection-name>` loads that entry from `resources/connections.json`. The password field is base64, matching `springs-of-mud-ui` `ConnectionSettings._deobfuscate_password`. `AuthClient.login(account_name, password)` posts `{"accountName", "password"}` to the connection `server_url` plus `/api/auth/login`.
2. The auth token is the `Authorization` response header. `get_auth_headers()` sends it as a Bearer token for later REST calls. A value that already starts with `Bearer ` is not prefixed again.
3. The login body supplies `id` and `playerCharacterList`. `list` prints those character names. `logon <characterName>` accepts only one of those names. `PlayerSession` then connects with `TelnetClient` and sends one line:

```text
logon {"accountId":"<account id>","characterId":"<character id>","characterName":"<name>"}
```

That line is the contract in `springs-of-mud-server` `MessageCodec`: a `logon ` prefix plus JSON becomes `MessageType.AUTH`. The game server currently accepts `accountId`, `characterId`, and `characterName`. Keep the JWT off the telnet line so it does not land in game logs. Hold it on `AuthClient` for REST calls.

Default ports match the UI client: auth `http://localhost:8169`, telnet `localhost:6969`. Override them in `resources/agent.yml`.

## First Login Knowledge

`Bootstrapper.bootstrap()` runs when the operator command is `play` after `logon`. It learns only from text the game server sends. The logged-on character is the one named in `logon`, and that name must be one returned for the connected account.

`CommandChannel` answers these gates before treating a reply as finished:

- `Do you wish to connect anyway (Y/N)?` and `Please type Y or N?` get `telnet.replace_existing` from `resources/agent.yml`. `Y` takes the existing link. `N` stops the session.
- `That character is being saved. Please reconnect in a moment.` stops the session.
- `Authentication failed.`, `Invalid authentication message.`, and a site ban stop the session. The server sends these as `ERROR: ` lines.
- `[Hit Enter to continue]` is acknowledged with an empty line and is left out of the stored text.

A normal reply ends on a playing prompt such as `<20hp 100m 100mv>`. The next command is sent only after that prompt. An idle timeout with no prompt raises `PromptTimeout`.

1. Drain the login burst until the playing prompt. Keep those lines on `WorldKnowledge.login_lines`.
2. Send `commands`. Remember those names, in that order, on the session `WorkingMemory`. This step does not categorize them. For each name, send `help <name>` and store a `HelpTopic`. `learn_commands` remembers the same names, sends the server text as the user message of the `commands` prompt, and keeps the raw model response. `learn_help` then sends `help <name>` for each remembered command, submits that page as the user message of the `help` prompt, and stores the model's topics on that `HelpTopic` and as the session command's `help_text`. `bootstrap()` does not call either Ollama step.
3. Send `areas` and store `AreaRecord` entries from the two-column, 39-character layout (`[level] author: name`).
4. Send `who` and store `PlayerRecord` entries. A player is `agentic` when the character name matches an agent document. The logged-in character is `self_character`.
5. Send `look`. Store the room, exits, and item lines. Classify people in the room:
   - a name that matches `who` is a player, and the record gains `room_name`
   - a proper name that is not in `who` is an NPC
   - an article-led description (`a`, `an`, `the`, `some`) is a mobile

`CommandChannel` uses the telnet client and does not open its own socket. Later play decisions read `WorldKnowledge`. They do not scrape the telnet client directly.

## World Knowledge API

After bootstrap, `KnowledgeClient` saves the snapshot. The HTTP server for this API is not in this repository yet. Implement it against this client.

- `PUT {knowledge.base_url}{knowledge.path}/{characterId}` replaces one character's snapshot.
- `GET` the same path returns that document. `404` means nothing is stored.
- Send the login `Authorization` header. Leave the token out of the body and out of logs.
- The body is camelCase JSON from `WorldKnowledge.to_document`: `characterId`, `characterName`, `agentName`, `loginLines`, `helpTopics`, `areas`, `mobiles`, `npcs`, `players`, and `room`.
- `characterId` in the body matches the path. A PUT replaces the whole snapshot.

`resources/agent.yml` `knowledge` holds the base URL and path. The default path is `/api/v1/agent-knowledge`. A failed save is reported and the telnet session continues.

## Operator Control

The agent process listens on `control.host` and `control.port` from `resources/agent.yml`. The default is `127.0.0.1:9711`. The host must be localhost. `ControlServer` binds that address, accepts one connection at a time, and requires the peer to be `127.0.0.1`. A daemon thread named `PlayerControl` runs the listener. `drive`, on the caller thread, runs the play action once the first time the mode becomes `play`.

Send commands with `python -m cli`. The invoker and the listener share one command grammar. The invoker refuses any other line before it opens a socket. The listener answers any other line with `Unknown command.` and does not run it. The rejection does not echo the line. One command is one TCP connection: a UTF-8 line ending in newline, then a reply of an ASCII byte length, a newline, and that many UTF-8 bytes. The socket is the whole transport.

The process starts in `idle` and answers `idle`, `play`, `memory`, `output`, `connect`, `list`, and `logon`. The listener changes the mode for `idle` and `play`. A later `idle` leaves the session connected and sends no further game commands. A later `play` returns to that mode and does not bootstrap again. Ctrl+C stops the process and closes the telnet session.

`connect <connection-name>` authenticates a saved connection and reports the account name and available characters. `list` prints those names. `logon <characterName>` opens telnet only when that name is in the login list. `play` waits until that logon has succeeded. A missing telnet host or port on the connection uses `resources/agent.yml`.

`memory` writes the session `WorkingMemory` to `working-memory.json` in the current directory. `memory <path>` writes that path instead. The reply names the file. A failed write names the error type and leaves the mode unchanged. `play` copies the bootstrap snapshot into working memory with `absorb_world` before the file can be reviewed.

`output` controls gameplay text. Received telnet lines are still queued for play. `GameplayOutput` also prints them. Output is on by default and prints to the console. `output off` stops printing. `output on` resumes it. `output file` also appends to `session.txt`. `output file <path>` appends to that path. `output file off` stops the file. A line is omitted when it is the `logon` command or it carries `accountId`, `characterId`, `password`, `Authorization`, or a bearer token. The playing prompt and ordinary server text are printed.

## Working Memory

`WorkingMemory` lasts for one play session. `clear` drops it. Do not add it to `WorldKnowledge.to_document`.

- `remember_player`, `remember_mobile`, and `remember_npc` track who is in the session. Agentic players are players with `agentic` set. Each being keeps an `auras` list. Look prefixes that end in `Aura`, such as `(White Aura)`, are stored by the label. A later look replaces that list. Remembering the being again without an aura list leaves the stored auras in place. `(Invis)`, `(Wizi)`, and the other non-aura prefixes are not stored.
- `remember_commands` keeps the names from the server `commands` list, in the order they were offered. `remember_command` can store a category and the help text later. Remembering the name again without a category or help text leaves the stored values in place.
- `remember_room` keeps each room seen this session: name, description, and exits. A later look at the same room updates those fields. An empty description or exit list leaves the stored values in place.
- `CommandCategorizer` is the later categorization phase. It fills `{command}` and `{help}` on a prompt and sends that body through `OllamaClient`. First login does not call it, and no command-category prompt is in `SOMDB.Prompts` yet.
- `remember_consider` stores one `consider` reply. The survival lines are the seven strings from `springs-of-mud-server` `Info.do_consider`. `outlook` is `safe`, `even`, `risky`, or `fatal`. A refusal such as `They're not here.` stays stored with `outlook` `unknown`.
- `note_aggressive` and a room line ending in `is here, fighting YOU!` mark a mobile aggressive. Seeing that mobile again does not clear the flag.
- `absorb_world` copies the current world snapshot, including the current room, and keeps rooms already remembered.
- `write_review(path)` writes `to_review()` as indented JSON: players, agentic players, mobiles, npcs, aggressive mobiles, rooms, commands, and consider readings. The same consider stored under a target and a subject is written once.

## Prompts

`SOMDB.Prompts.json` holds extractor prompts for model `gpt-oss:20b`. `score` asks for one or more intent tokens, such as `expToLevel` or `armorClass`. `Prompt.tokenize(score_text, *intents)` replaces `{intent}`, `{response}`, and `{score}` and narrows `jsonSchema` to those facts.

`PromptSubmission.to_request()` is the body for som-nlp-service `POST /ollama/completions`: `model`, `system`, `user`, and `jsonSchema`. A blank user is rejected with the service message and is not sent. `OllamaClient.complete` returns the `text` field. When the request included a schema, `read_completion` parses that text as JSON. `resources/agent.yml` `ollama.base_url` is `http://localhost:9081`.

## Coding Conventions

- Follow the Springs of MUD Python style used by the server and UI. Modules that export a primary type use PascalCase filenames. Domain objects are dataclasses with `from_json`.
- Normalize camelCase collection and service fields to snake_case at the boundary. Internal fields stay snake_case.
- Registries expose lookup by agent name. Raise when a required agent is missing or disabled.
- Keep game sockets inside `src/net`. The local control listener is `src/net/local`. The CLI invoker is the other end of that socket. `src/play` may send and read lines through `CommandChannel`, and agent documents do not open sockets.
- Use the standard library `logging` module. Do not log passwords, JWTs, or `Authorization` headers.
- Preserve the telnet client's refusal of option negotiation. The game server speaks telnet IAC; the client answers `WILL` with `DONT` and `DO` with `WONT`.

## Testing

Use `unittest`. Tests add `src` to `sys.path`. `tests.test_local_control` binds `127.0.0.1` on an ephemeral port. `tests.test_live_logon` connects profile `SpringsOfMUD` and logs on its lowest-level character when that profile's auth service and telnet port are accepting connections. It skips when they are not. `tests.test_live_working_memory` uses that same logon. `test_live_working_memory_mobiles` records a mobile from the live room and a `consider` reading. `test_live_working_memory_players` records another player from `who` and `look`, including that player's auras, room, and `consider` reading. `test_live_working_memory_rooms` records two rooms after one move. Each test quits before it returns, and each skips when auth or telnet is closed. `tests.test_live_command_bootstrap` uses that same logon, sends `commands`, and asks the `commands` prompt. It then sends `help` for each remembered command and asks the `help` prompt. It writes `tests/output/test_live_command_bootstrap.json` with every Ollama prompt and raw response, then quits. It skips when auth, telnet, or Ollama is closed. The other tests do not open a telnet session or call a live auth, knowledge, or model service.

Run focused tests for the area you changed:

```powershell
python -m unittest tests.test_agent_collection
python -m unittest tests.test_auth_client
python -m unittest tests.test_connection_catalog
python -m unittest tests.test_account_session
python -m unittest tests.test_player_session
python -m unittest tests.test_world_reader
python -m unittest tests.test_bootstrapper
python -m unittest tests.test_command_categorizer
python -m unittest tests.test_command_channel
python -m unittest tests.test_knowledge_client
python -m unittest tests.test_working_memory
python -m unittest tests.test_prompt_tokenizer
python -m unittest tests.test_ollama_client
python -m unittest tests.test_player_control
python -m unittest tests.test_gameplay_output
python -m unittest tests.test_local_control
python -m unittest tests.test_live_logon
python -m unittest tests.test_live_working_memory
python -m unittest tests.test_live_command_bootstrap
python -m unittest discover -s tests
```

When changing collection documents, auth parsing, the logon line, or first-login parsing, extend these tests with a fixture or the real `resources/collections/SOMDB.Agents.json` snapshot. Parser tests feed server-shaped text and do not open a socket.

## Change Discipline

- Keep persona, account name, character name, and enabled state in `SOMDB.Agents.json`.
- Keep the login request and the telnet `logon` line compatible with `springs-of-mud-ui` and `springs-of-mud-server`.
- Do not add a live MongoDB client until a task replaces the JSON snapshot. The database name `SOMDB` and collection name `Agents` stay in config so that cutover is explicit.
- Do not commit passwords, tokens, or local `.env` files.
- Avoid broad refactors of the telnet byte parser unless a test covers the negotiation change.
