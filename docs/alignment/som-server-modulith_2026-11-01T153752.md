# som-server-modulith alignment

Compared repository: `springs-of-mud-agentic-player`.

The live endpoints are in `E:\IdeaProjects\som-server-modulith`. This file proposes changes here. It does not change either repository.

The skill's target list names `springs-of-mud-ui`, `springs-of-mud-server`, and `springs-of-mud-designer`. This task names `som-server-modulith`, the process that serves the four APIs below. The filename uses that name.

Standards read: `AGENTS.md` (no `AGENTS.override.md`), `.grok/skills/compact-python/SKILL.md`, and `.grok/skills/collection-modify/SKILL.md`. No collection document needs a rewrite, so collection-modify is not the owner of any proposal below. `resources/connections.json` stays as it is. The working copy of `resources/collections/SOMDB.Agents.json` differs from the committed `example-agent` document. This report leaves that file alone.

## Live API

`som-server-modulith` listens on port `9080`. There is no servlet context path. `som.web-security.enabled` is `false`, so the dev chain permits every request. When that flag is `true`, `/api/v1/**` requires `ROLE_somplayer`, `ROLE_game-master`, or `ROLE_somadmin`. `som.memory.retention` is `P1D`.

| API | Routes | Lookup | Body |
| --- | --- | --- | --- |
| Agents | `GET /api/v1/agents`, `GET /api/v1/agents/{name}`, `PUT /api/v1/agents/{name}` | `name`, ignore case | `id`, `name`, `accountName`, `characterName`, `enabled`, `description` |
| Prompts | `GET /api/v1/agent-prompts`, `GET /api/v1/agent-prompts/{name}`, `PUT /api/v1/agent-prompts/{name}` | `name`, ignore case | `name`, `model`, `system`, `user`, `jsonSchema`, `tokens` |
| Memory | `GET /api/v1/agent-memory/{agentName}`, `PUT /api/v1/agent-memory/{agentName}` | `agentName`, ignore case | `agentName`, `savedAt`, `players`, `agenticPlayers`, `mobiles`, `npcs`, `aggressiveMobiles`, `rooms`, `commands`, `considers`, `conversations` |
| Knowledge | `GET /api/v1/agent-knowledge/{characterId}`, `PUT /api/v1/agent-knowledge/{characterId}` | `characterId`, exact | `characterId`, `characterName`, `agentName`, `loginLines`, `helpTopics`, `areas`, `mobiles`, `npcs`, `players`, `room` |

There is no delete route on any of the four. A missing document is HTTP 404 with a problem detail. A blank name, a path/body name mismatch, or a prompt token that lacks `text` or `example` is HTTP 400. A Mongo failure is HTTP 503. Clients report the status and leave the body out of the message and the log.

Agent `PUT` keeps a client `id` on insert and keeps the stored `id` when the name already exists. A missing `enabled` is stored as `true`. Prompt `id` and memory `id` are not part of the JSON. Memory `PUT` sets `savedAt` on the server. Memory `GET` returns 404 when `savedAt` is missing or older than retention. Knowledge `characterId` in the body must equal the path exactly. Memory and agent names match the path ignoring case.

Knowledge beings and players include `auras`. Memory beings include `name`, `kind`, `agentic`, `roomName`, `aggressive`, and `auras`.

Startup loads agents before `connect`. With security disabled, that `GET` can run without a token. Whether the login `Authorization` header is a JWT this resource server accepts when security is enabled is still unknown. This proposal sends the header when `AuthClient` has one, and it does not add a service account.

## Already aligned

`Agent.from_json` reads `id` or `_id.$oid`, requires `name`, `accountName`, and `characterName`, and requires `enabled` to be a boolean. A prompt view matches `Prompt.from_json`, including a null token `example`. `WorkingMemory.to_collection` already writes the memory section names in camelCase. `KnowledgeClient.save` and `load` already use `PUT` and `GET` on `/api/v1/agent-knowledge/{characterId}`, quote the id, require an exact `characterId`, treat 404 as absence, and send the login `Authorization` header. `WorldKnowledge.to_document` already writes the knowledge fields other than `auras`.

HTTP clients belong in `src/net/rest`. `src/agent`, `src/prompt`, `src/memory`, and `src/play` keep the documents and do not open sockets.

## Agents

### `src/main.py`

Standard: Project Direction and Architecture Map. The long-term source is the `Agents` collection. The runtime still calls `AgentCollection.load` on the JSON snapshot for `--list` and for `run_agent`.

Proposed change: load the registry from `GET /api/v1/agents` through an `AgentClient` in `src/net/rest/AgentClient.py`. `AgentRegistry.require` still raises when the name is missing or disabled. `AgentRegistry` still raises when two documents share a name ignoring case. The server collapses case-variant duplicates on `PUT`, and `GET` can still return them. Keep the raise.

`AgentClient.list` returns the JSON array. `AgentClient.get` returns one document, and 404 means the name is absent. Both quote the name as one path segment. Both use the same header provider and status handling as `KnowledgeClient`. The runtime does not `PUT` agents. Publishing the snapshot is a separate operation. This proposal does not upload `SOMDB.Agents.json`.

Importers of `AgentCollection.load` that stay on the file: `tests/test_agent_collection.py`. The live test below switches.

No cycle: `AgentClient` imports `Agent`. `Agent` does not import `src/net`.

### `src/agent/AgentCollection.py`

Standard: Collection Data. `load` reads a JSON array from disk. `DATABASE` and `NAME` stay `SOMDB` and `Agents` for that fixture.

Proposed change: add `from_documents(documents, source)` so the client and the file loader share one constructor. `load` remains the fixture reader for unit tests. `Agent.from_json` already accepts the API `id` field. No parser change.

### `src/net/rest/__init__.py`

Standard: Architecture Map. The package exports the REST clients.

Proposed change: export `AgentClient` from `src/net/rest/AgentClient.py`.

### `tests/test_live_working_memory.py`

Standard: Testing. The live logon loads `AgentCollection` from `resources/collections/SOMDB.Agents.json` to decide which characters are agentic.

Proposed change: take that list from `GET /api/v1/agents`. Skip when the modulith is not accepting connections, in the same way the test already skips when auth or telnet is closed.

### `tests/test_agent_client.py`

Standard: Testing. Non-live tests inject the request callable and do not call a live service. Cover the list URL, the single-name URL, a 404, an HTTP error that names the status and omits the body, and `Agent.from_json` on an `id` field.

Add `python -m unittest tests.test_agent_client` to the Testing command list in `AGENTS.md`.

## Prompts

### `src/prompt/PromptCollection.py`

Standard: Architecture Map and Prompts. `NAME` is `Prompts` and `load` reads `resources/collections/SOMDB.Prompts.json`. The live collection is served at `/api/v1/agent-prompts`. The Mongo name `AgentPrompts` stays on the server. This client does not need it.

`src/main.py` does not load prompts. `Bootstrapper.bootstrap` does not call the Ollama steps. `learn_categories`, `learn_commands`, and `learn_help` receive a `Prompt` from the caller. The live caller is `tests/test_live_command_bootstrap.py`, which loads the JSON file.

Proposed change: add `PromptClient` at `src/net/rest/PromptClient.py` with `list` and `get` for `/api/v1/agent-prompts` and `/api/v1/agent-prompts/{name}`. Quote the name. 404 on `get` means the prompt is absent. Add `PromptCollection.from_documents`. Keep `load` for unit tests. Do not call the client from `bootstrap()`. A later caller that already takes a `Prompt` gets it from `PromptClient.get`. The runtime does not `PUT` prompts. A future `PUT` has to send `tokens` as an object. Several local documents omit `tokens`, and `Prompt.from_json` already treats a missing key as `{}`.

No cycle: `PromptClient` imports `Prompt`. `Prompt` does not import `src/net`.

### `src/net/rest/__init__.py`

Proposed change: export `PromptClient` from the new module.

### `tests/test_live_command_bootstrap.py`

Standard: Testing. Both live methods load `PromptCollection` from the snapshot.

Proposed change: load `categories`, `commands`, and `help` with `PromptClient`. Skip when the modulith is closed, in addition to the current auth, telnet, and Ollama skips.

### `tests/test_prompt_client.py`

Standard: Testing. Inject the request. Cover the collection URL, one name, 404, and a status error that omits the body. `tests/test_prompt_tokenizer.py`, `tests/test_ollama_client.py`, `tests/test_bootstrapper.py`, and `tests/test_command_categorizer.py` keep loading the snapshot.

Add `python -m unittest tests.test_prompt_client` to the Testing command list.

### `src/prompt/Prompt.py`

Standard: Coding Conventions. `PromptSubmission` and `Prompt` both have methods and share this file.

Proposed change: move `PromptSubmission` to `src/prompt/PromptSubmission.py`. Move `_completion_text` with it. `_example_fields` and `_score_text` stay in `Prompt.py`. They serve `Prompt.tokenize` only.

Importers to retarget:

- `src/prompt/__init__.py` exports `PromptSubmission`. Point that export at `src/prompt/PromptSubmission.py`.
- `src/prompt/Prompt.py` imports `PromptSubmission` for `tokenize`. `PromptSubmission` does not import `Prompt`. No cycle.
- `src/play/CommandCategorizer.py`
- `src/play/Bootstrapper.py`
- `tests/test_prompt_tokenizer.py`

The methods are already on one line. No further compact-python change after the move.

## Working memory

### `src/memory/WorkingMemory.py`

Standard: Working Memory. `to_collection` matches the memory sections. `write_collection` upserts `resources/collections/SOMDB.Memories.json`. The `memory` command writes the review file and does not call `write_collection`. There is no loader from a memory document, and nothing calls the live route.

Proposed change: add `from_collection(document)` in this file. It restores players, agentic players, mobiles, npcs, aggressive mobiles, rooms, commands, considers, and conversations through the existing `remember_*` methods and `Conversation.from_json`. Agentic players and ordinary players stay disjoint, as `to_review` already writes them. Aggressive mobiles are also present on `mobiles`. Restore mobiles first, then mark the aggressive names, so one being stays one record. Ignore `savedAt` and `id`. A blank `agentName` still raises.

Keep `write_collection` as the offline fixture writer. Unit tests in `tests/test_working_memory.py` keep using it. The `memory` command keeps calling `write_review` only.

`default_collection_path`, `_upsert_agent`, `_copied_auras`, `_conversation_key`, `_by_name`, and `_by_target` stay here. They serve `WorkingMemory`. `SessionBeing`, `SessionRoom`, and `SessionCommand` stay in this file. Their bodies are fields.

No cycle: `from_collection` does not import `src/net`. `observe_line` keeps its lazy import of `split_look_prefixes`.

### `src/net/rest/MemoryClient.py`

Standard: Architecture Map, Working Memory, and the socket rule. The HTTP call belongs in `src/net/rest`.

Proposed change: `save(agent_name, document)` `PUT`s `/api/v1/agent-memory/{agentName}`. `load(agent_name)` `GET`s the same path. Quote the name. Compare `agentName` to the path ignoring case, and set the body name from the path when the body omits it. Omit `savedAt`. The server sets it. `load` returns `None` on 404, which covers a missing document and a document past retention. Other HTTP errors raise a store error that names the status and omits the body. Send the login `Authorization` header when one exists.

Export `MemoryClient` from `src/net/rest/__init__.py`.

No cycle: the client takes a dict. It does not import `WorkingMemory`.

### `src/main.py`

Standard: Working Memory and Operator Control. `run_agent` starts an empty `WorkingMemory`. Play copies the world with `absorb_world`. Shutdown does not store the session.

Proposed change: after the agent is resolved, `GET` that agent's memory. `None` leaves the empty session. A document becomes `WorkingMemory.from_collection`. After `absorb_world` in `_begin_play`, `PUT` the current `to_collection(agent.name)`. On process shutdown, `PUT` again when play has run, so later in-process updates are stored. An idle exit that never played does not `PUT`, so opening the process does not replace a stored document or refresh `savedAt`. `clear` stays in-process. There is no delete route to call.

A failed save is reported and the telnet session continues, matching the knowledge save.

### `src/control/PlayerControl.py`

Standard: Operator Control. `memory` writes `working-memory.json` or `memory <path>` through `write_review`.

Proposed change: leave this command on `write_review`. It does not call `MemoryClient` or `write_collection`.

### `tests/test_memory_client.py` and `tests/test_working_memory.py`

Standard: Testing. Add a client test with an injected request: the quoted URL, ignore-case name check, omitted `savedAt`, 404 as `None`, and a status error that omits the body. Extend `tests/test_working_memory.py` so `from_collection` restores a `to_collection` document and ignores `savedAt`.

Add `python -m unittest tests.test_memory_client` to the Testing command list. `python -m unittest tests.test_working_memory` stays.

## World knowledge

### `resources/agent.yml` and `src/agent/AgentConfig.py`

Standard: World Knowledge API and Architecture Map. `knowledge.base_url` is `http://localhost:8169`, and `AgentConfig` defaults a missing knowledge base URL to the auth base URL. Auth stays on port `8169`. The four APIs are on the modulith, port `9080`. Ollama stays `http://localhost:9081`.

Proposed change: add an `api` section:

```yaml
api:
  base_url: http://localhost:9080
```

`AgentConfig` reads `api.base_url`, default `http://localhost:9080`. Agents, prompts, memory, and knowledge use that origin. Paths default to `/api/v1/agents`, `/api/v1/agent-prompts`, `/api/v1/agent-memory`, and `/api/v1/agent-knowledge`. Remove `knowledge.base_url` from `resources/agent.yml` so knowledge no longer follows the auth host. Keep `knowledge.path`.

`tests/test_agent_collection.py` asserts `knowledge_base_url == "http://localhost:8169"`. Point that assertion at `http://localhost:9080` and the new path fields.

This `agent.yml` change is required by the World Knowledge API section once the host is the modulith.

### `src/play/WorldKnowledge.py`

Standard: World Knowledge API and Coding Conventions. `KnowledgeView` beings and players include `auras`. `_being_document` and `_player_document` omit `auras`. `_being_from` and `_player_from` drop `auras` on the way back. `BeingRecord` and `PlayerRecord` already store them, and `WorldReader` fills them. Those dataclasses stay in this file. Their bodies are fields.

Proposed change: write `auras` on mobiles, npcs, and players, and read them in `from_document`. This adds a field of the knowledge records. It does not add working-memory sections to `to_document`. `HelpArticle`, `HelpTopic`, `AreaRecord`, `PlayerRecord`, `BeingRecord`, and `RoomSnapshot` stay here.

`_key`, `_sorted_values`, `_sorted_beings`, `_being_document`, `_player_document`, `_being_from`, `_player_from`, and `_snake_tree` stay in this module. They serve `WorldKnowledge`.

### `src/net/rest/KnowledgeClient.py`

Standard: World Knowledge API. The docstring says the server is not in this repository yet.

Proposed change: name the live route on som-server-modulith. Keep the current `PUT`, `GET`, 404, exact `characterId` check, quoting, and header behavior. The client uses `api.base_url` from the caller in `src/main.py`.

### `src/main.py`

Standard: World Knowledge API. `_save_knowledge` already reports a failed save and leaves the telnet session up.

Proposed change: construct `KnowledgeClient` with the modulith origin. Keep the save after bootstrap.

### `tests/test_knowledge_client.py`

Standard: Testing. `test_document_round_trip` builds a player and a room and does not set auras.

Proposed change: round-trip `auras` on one mobile, one npc, and one player. The injected-request tests stay off the network. Their host strings can stay literal. `tests/test_world_reader.py` already checks auras on the in-memory records.

## `AGENTS.md`

Standard: the sections named on each item. Product rules stay: the `memory` command writes the review file, working memory is not copied into `WorldKnowledge.to_document` as its own sections, passwords and tokens stay out of logs and out of agent documents, `bootstrap()` does not call the Ollama steps, and this repository does not gain a Mongo client.

Proposed text:

- Project Direction: the runtime reads agents with `GET /api/v1/agents`. `resources/collections/SOMDB.Agents.json` remains the unit-test fixture.
- Architecture Map: `src/net/rest` also loads agents and prompts and loads and saves working memory. The modulith origin is `api.base_url`.
- Collection Data: the JSON files remain fixtures. Live agent, prompt, and memory documents come from the routes above.
- World Knowledge API: the server is som-server-modulith on port `9080`. The body includes `auras` on mobiles, npcs, and players. A failed save is still reported and play continues.
- Working Memory: `from_collection` restores a memory document. The live snapshot is `PUT /api/v1/agent-memory/{agentName}` after play. `GET` 404 leaves the session empty. `write_collection` remains the fixture writer. The `memory` command still writes the review file.
- Prompts: callers that need a prompt load it with `GET /api/v1/agent-prompts/{name}`. The snapshot remains the unit-test fixture. `bootstrap()` still does not call those prompts.
- Change Discipline: the cutover is these REST clients. A live Mongo client is still out of scope.
- Testing: add the three new unittest modules to the command list. Live command bootstrap and live working memory also skip when the modulith is closed.

## Coding conventions outside the four APIs

`src/` and `tests/` have no line that ends in an open parenthesis. Compact-python has nothing further to collapse in the current files. After a move, keep the moved methods on one line.

### `src/net/rest/AuthResponse.py`

Standard: Coding Conventions. `CharacterSummary` and `AuthResponse` both have methods.

Proposed change: move `CharacterSummary` to `src/net/rest/CharacterSummary.py`. Move `_character_level` with it. `AuthResponse.from_json` imports `CharacterSummary`. `CharacterSummary` does not import `AuthResponse`. No cycle.

Importers:

- `src/net/rest/__init__.py` exports `CharacterSummary`. Point that export at the new module.
- `src/net/AccountSession.py` imports `CharacterSummary` from `AuthResponse`. `_available_character` stays in `AccountSession.py`. It serves `AccountSession`.

`tests/test_player_session.py` and `src/net/telnet/PlayerSession.py` import `AuthResponse` only.

### `src/net/rest/ConnectionCatalog.py`

Standard: Coding Conventions. `SavedConnection.login_password` and `ConnectionCatalog` both have methods.

Proposed change: move `SavedConnection` to `src/net/rest/SavedConnection.py`. Move `obfuscate_password` and `deobfuscate_password` with it. They serve `login_password`. `_connection` and `_port` stay in `ConnectionCatalog.py`. They serve `load`. `ConnectionCatalog` imports `SavedConnection`. `SavedConnection` does not import `ConnectionCatalog`. No cycle.

Importers:

- `src/net/rest/__init__.py` exports `SavedConnection`, `deobfuscate_password`, and `obfuscate_password`. Point those exports at the new module.
- `src/net/AccountSession.py`
- `src/main.py` imports `ConnectionCatalog` only.
- `tests/test_account_session.py` imports `ConnectionCatalog`, `SavedConnection`, and `obfuscate_password`.
- `tests/test_connection_catalog.py` imports `ConnectionCatalog`, `deobfuscate_password`, and `obfuscate_password`.
- `tests/live_session.py` imports `ConnectionCatalog` only.

### `src/play/Bootstrapper.py`

Standard: Coding Conventions. `CommandLesson`, `CategoryLesson`, `HelpLesson`, and `Bootstrapper` all have methods.

Proposed change:

- `src/play/CommandLesson.py` for `CommandLesson`
- `src/play/CategoryLesson.py` for `CategoryLesson`
- `src/play/HelpLesson.py` for `HelpLesson`

`_completion_value` serves all three. Leaving it in `Bootstrapper.py` cycles: the lesson modules would import `Bootstrapper` while `Bootstrapper` imports the lesson types. Move `_completion_value` to `CommandLesson.py`. `CategoryLesson` and `HelpLesson` import it from there. They do not import `Bootstrapper`. No cycle.

`_commands_submission`, `_ask_help`, `_with_category`, `_category_instruction`, `_known_categories`, `_submission`, and `_help_text` stay in `Bootstrapper.py`. They serve `Bootstrapper`. `_ask_help` imports `HelpLesson`.

`src/play/__init__.py` exports `Bootstrapper` and `WorldKnowledge` only. Those exports stay.

Importer: `tests/test_bootstrapper.py` imports `Bootstrapper`, `CategoryLesson`, `CommandLesson`, and `HelpLesson` from `play.Bootstrapper`. Retarget the three lesson names. The Testing command stays `python -m unittest tests.test_bootstrapper`.

### Tests with more than one class that has methods

Standard: Coding Conventions and Testing. A move of a `TestCase` changes the module the Testing section tells the operator to run. Private fakes named `_Response` live in `tests/test_account_session.py`, `tests/test_auth_client.py`, `tests/test_knowledge_client.py`, and `tests/test_ollama_client.py`. Private fakes named `_Client` live in `tests/test_account_session.py` and `tests/test_command_categorizer.py`. Each would be filed under the type name, and those two names are not unique under `tests/`. That collision blocks the move.

The `TestCase` types have unique names. Proposed files and the Testing commands that would change:

| Current module | Types | Proposed files | Testing command to update |
| --- | --- | --- | --- |
| `tests/test_local_control.py` | `TestControlProtocol`, `TestControlServer` | `tests/TestControlProtocol.py`, `tests/TestControlServer.py` | `python -m unittest tests.test_local_control` |
| `tests/test_working_memory.py` | `TestConsiderMemory`, `TestAggressiveMobiles`, `TestCommands`, `TestAuras`, `TestAbsorbWorld`, `TestConversations`, `TestMemoryReview` | one PascalCase file per type | `python -m unittest tests.test_working_memory` |
| `tests/test_world_reader.py` | `TestHelpReader`, `TestWorldReader` | `tests/TestHelpReader.py`, `tests/TestWorldReader.py` | `python -m unittest tests.test_world_reader` |

`python -m unittest discover -s tests` still collects the new modules. The focused commands above need the new module names in `AGENTS.md`.

These test moves are independent of the API client work. The new client tests proposed above can be born as one `TestCase` per file, which avoids a later split.
