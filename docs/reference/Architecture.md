# Architecture Map

- `src/main.py` loads `resources/agent.yml`, reads agents with `GET /api/v1/agents`, and listens on the local control socket. The agent starts idle. The first `play` bootstraps game knowledge. A later `play` restores commands from stored world knowledge. `bootstrap` runs that login again. When `bootstrap.initial` is true, startup connects the saved account for the agent's `accountName`, logs on `characterName`, and runs that same bootstrap before the control loop. The mode stays idle.
- `src/agent` owns `Agent`, `AgentCollection`, `AgentRegistry`, and `AgentConfig`.
- `src/control` owns `PlayerControl` and `GameplayOutput`. `handle` accepts `idle`, `play`, `bootstrap`, `memory`, `output`, `connect`, `list`, and `logon`.
- `src/cli` is the operator invoker. `python -m cli` sends one known command. `src/net/local/ControlServer` accepts it on `127.0.0.1`. The transport is one raw TCP socket.
- `src/net/AccountSession` connects a saved account and logs on with one character from that login.
- `src/play` owns the first-login `Bootstrapper`, `CommandChannel`, help and world readers, and `WorldKnowledge`.
- `src/memory` owns short-lived `WorkingMemory` for the current session: players, agentic players, mobiles, NPCs, rooms, commands, `ConsiderOpponent` records, conversations, and aggressive mobiles. Command records are copied onto the knowledge document. The other sections are not part of that document.
- `src/prompt` fills a prompt's tokens before that text is submitted to som-nlp-service. A caller that needs a prompt loads it with `GET /api/v1/agent-prompts/{name}`.
- `src/net/rest` retrieves the auth token, loads agents and prompts, loads and saves working memory, loads and saves world knowledge, and calls the Ollama service. The modulith origin is `api.base_url`. `AuthClient` posts to `/api/auth/login` and stores the `Authorization` response header, matching `springs-of-mud-ui`. `AgentClient` gets `/api/v1/agents`. `PromptClient` gets `/api/v1/agent-prompts`. `MemoryClient` gets and puts `/api/v1/agent-memory/{agentName}`. `KnowledgeClient` gets and puts `/api/v1/agent-knowledge/{characterId}`. `OllamaClient` posts to `/ollama/completions`.
- `src/net/telnet` owns the telnet socket client and `PlayerSession`, which sends the server `logon` line.
- `src/util` holds small shared helpers: camelCase conversion and reading or writing a JSON collection file.
- `resources/agent.yml` holds the auth URL, telnet host and port, `api.base_url`, the local control address, and the collection location.
- `resources/collections/SOMDB.Agents.json` is the unit-test fixture for `SOMDB.Agents`. `SOMDB.Prompts.json` is the unit-test fixture for prompts. `SOMDB.Memories.json` is the local working-memory fixture, one document per agent.
