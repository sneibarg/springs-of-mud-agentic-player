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
