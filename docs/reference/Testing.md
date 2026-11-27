# Testing

Use `unittest`. Tests add `src` to `sys.path`. `tests.TestControlServer` binds `127.0.0.1` on an ephemeral port. `tests.test_live_logon` connects profile `SpringsOfMUD` and logs on its lowest-level character when that profile's auth service and telnet port are accepting connections. It skips when they are not. `tests.test_live_working_memory` uses that same logon. `test_live_working_memory_mobiles` records a mobile from the live room and a `ConsiderOpponent`. `test_live_working_memory_players` records another player from `who` and `look`, including that player's auras, room, and `ConsiderOpponent`, and reads agent character names with `GET /api/v1/agents`. `test_live_working_memory_rooms` records two rooms after one move. Each test quits before it returns, and each skips when auth or telnet is closed. `test_live_working_memory_players` also skips when som-server-modulith is closed. `tests.test_live_command_bootstrap` uses that same logon. It sends bare `help` and asks the `categories` prompt, then sends `commands` and asks the `commands` prompt, then sends `help` for each command in that list and for any help-index command the list omitted. Each page goes to the help prompt. A command the index did not categorize asks that prompt for a category as well. It writes `tests/output/test_live_command_bootstrap.json` with every Ollama prompt and raw response, then quits. `test_live_help_categories` sends only bare `help`, asks the `categories` prompt, writes `tests/output/test_live_help_categories.json` with that prompt and raw response, and quits. It does not send `commands` or read individual help pages. Both load prompts with `GET /api/v1/agent-prompts`. Both skip when auth, telnet, Ollama, or som-server-modulith is closed. The other tests do not open a telnet session or call a live auth, agent, prompt, memory, knowledge, or model service.

Run focused tests for the area you changed:

```powershell
python -m unittest tests.test_agent_collection
python -m unittest tests.test_agent_client
python -m unittest tests.test_auth_client
python -m unittest tests.test_connection_catalog
python -m unittest tests.test_account_session
python -m unittest tests.test_player_session
python -m unittest tests.TestHelpReader
python -m unittest tests.TestWorldReader
python -m unittest tests.test_bootstrapper
python -m unittest tests.test_command_categorizer
python -m unittest tests.test_command_list
python -m unittest tests.test_command_availability
python -m unittest tests.test_command_channel
python -m unittest tests.test_knowledge_client
python -m unittest tests.TestConsiderMemory
python -m unittest tests.TestAggressiveMobiles
python -m unittest tests.TestCommands
python -m unittest tests.TestAuras
python -m unittest tests.TestAbsorbWorld
python -m unittest tests.TestConversations
python -m unittest tests.TestMemoryReview
python -m unittest tests.test_memory_client
python -m unittest tests.test_prompt_tokenizer
python -m unittest tests.test_prompt_client
python -m unittest tests.test_ollama_client
python -m unittest tests.test_km_client
python -m unittest tests.TestKmPlayer
python -m unittest tests.test_level_question
python -m unittest tests.test_gameplay_engine
python -m unittest tests.test_play_session
python -m unittest tests.test_session_evidence
python -m unittest tests.test_km_evidence_adapter
python -m unittest tests.test_observation_identity
python -m unittest tests.test_player_control
python -m unittest tests.test_gameplay_output
python -m unittest tests.TestControlProtocol
python -m unittest tests.TestControlServer
python -m unittest tests.test_initial_bootstrap
python -m unittest tests.test_logging
python -m unittest tests.test_live_logon
python -m unittest tests.test_live_working_memory
python -m unittest tests.test_live_command_bootstrap.TestLiveCommandBootstrap.test_live_help_categories
python -m unittest tests.test_live_command_bootstrap
python -m unittest discover -s tests
```

When changing collection documents, auth parsing, the logon line, or first-login parsing, extend these tests with a fixture or the real `resources/collections/SOMDB.Agents.json` snapshot. Parser tests feed server-shaped text and do not open a socket.

`tests.test_play_session` covers live review serialization, fresh legacy restores, clear/isolation, and score parsing/state updates. `tests.test_gameplay_engine` covers engine recreation with the same memory, preservation of consider/travel/combat/prompt state, unusable-reply suppression, and interrupted exchanges that remain pending without being resent. These tests use fake channels and do not call live services.

`tests.test_observation_identity` covers complete/partial replacement, duplicate room/being/item identities, absent and returning mobs, encounter-bound freshness, nullable flags, legacy duplicate rows, prompt framing, refused/uncertain/confirmed movement, forward-only edges, failed fleeing, player classification, and stale model enrichment. It uses fake channels and source-shaped room text, without live game or KM calls.

`tests.test_command_list` verifies shared immutable values, normalization, ordered merge/replacement, and legacy description behavior. `tests.test_command_availability` verifies fresh-login command checks, help-only migration, revocation, known-empty versus unknown availability, KM index replacement, metadata ownership, prohibited verbs, and failure behavior with fake channels and patched startup clients.

`tests.test_session_evidence` covers immutable ordering/source links, local review and legacy isolation, both defer modes, partial/missing pages, interrupted bootstrap and gameplay, model failure/staleness, forced attempts, fresh prompt synchronization, shared replacement, restored availability, and the completion acceptance gate. KM reasoning failures and cross-player completion are exercised with fakes; these tests do not claim a live KM round trip or durable saving.

`tests.test_km_evidence_adapter` covers deterministic prefix replay, player/stream isolation, metadata versus availability, ordered replacement and emptiness, quoting/reserved constants, listed-area semantics, provisional room/encounter identity, directed edges and unknown door prerequisites, historical versus tactical membership, fresh considers, confirmed gear validation, source permissions/loot prerequisites, source provenance, malformed-prefix isolation, and unsupported records. Tests compare generated plans and do not submit them to live KM or acknowledge the journal.
