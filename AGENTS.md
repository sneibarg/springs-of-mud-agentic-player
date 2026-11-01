# Repository Guidelines

## Project Direction

This repository is the Python runtime for Springs of MUD agentic player characters. An agent is a player that logs into the game server and plays a character on its own.

Game identity and persona live in the `Agents` collection. The runtime reads agents with `GET /api/v1/agents` on som-server-modulith. `resources/collections/SOMDB.Agents.json` remains the unit-test fixture.

Add Python for the runtime: collection loading, auth, the telnet session, and later the decision loop. Put ordinary agent tuning in the collection document.

The companion server is `springs-of-mud-server`. The login and telnet behavior follows `springs-of-mud-ui/src/net`. Agent, prompt, memory, and knowledge documents are served by som-server-modulith.

Do not update any other repository to meet the requirements of the current iteration. That includes som-server-modulith, springs-of-mud-server, springs-of-mud-ui, springs-of-mud-designer, and every other checkout. Implement the iteration in this runtime. Read those repositories when you need a contract. Leave their source, tests, config, and builds unchanged unless the user explicitly asks for a change in that repository. A missing field or endpoint on a companion service is a gap to report. It is not permission to edit that service in this iteration.

## Reference

Open a reference when the work touches that area.

- Package ownership, startup, and where the sockets and REST clients live ([Architecture Map](docs/reference/Architecture.md)).
- Agent, prompt, and memory document shapes, and which JSON files stay fixtures ([Collection Data](docs/reference/Collections.md)).
- Saved connections, the auth login, and the telnet `logon` line ([Authentication And Telnet](docs/reference/Authentication.md)).
- First login: command order, help, when bootstrap runs, and the control `bootstrap` command ([First Login Knowledge](docs/reference/Bootstrap.md)).
- Knowledge load and save, the document fields, and a failed save ([World Knowledge API](docs/reference/WorldKnowledge.md)).
- The control socket, the command grammar, and idle, play, and bootstrap ([Operator Control](docs/reference/OperatorControl.md)).
- Session memory: beings, commands, considers, conversations, and what is saved ([Working Memory](docs/reference/WorkingMemory.md)).
- Prompt fixtures, score intent tokens, and the Ollama completion body ([Prompts](docs/reference/Prompts.md)).
- Which tests to run, including the live logon, memory, and command-bootstrap tests ([Testing](docs/reference/Testing.md)).

## Coding Conventions

- Format Python with the `compact-python` skill at `.grok/skills/compact-python/SKILL.md`. That skill is the formatting rule for this repository. There is no line-length limit. Put class bases, constructor parameter lists, function parameter lists, calls, collections, parenthesized imports, dotted chains, and backslash continuations on one line. Drop a trailing comma that only kept a closer on its own line. Keep the comma in a one-element tuple, including a subscript such as `a[index,]`. Keep blank lines between related blocks, newlines inside strings and docstrings, and any body with more than one statement. Keep a class suite under its header, including a subclass whose body is only a docstring or `pass`. Keep a function suite under its header. A wrapper that immediately returns an updated value is two lines: the signature, then the return. Keep `try`, `with`, `for`, `while`, `if`, and `match` headers that introduce a suite. Leave names, literals, control flow, and behavior unchanged. After a formatting edit, run `python -m py_compile` on each changed file. Do not run Black, Ruff, PEP 8, or another formatter afterward.
- A class or dataclass that has functions, or that is about to gain them, lives in its own file. Name that file with the type's PascalCase name. Extract the type before adding the function when it currently shares a module. A class whose body is only fields, a docstring, or `pass` may stay beside the code that uses it. Domain objects are dataclasses with `from_json`.
- Normalize camelCase collection and service fields to snake_case at the boundary. Internal fields stay snake_case.
- Registries expose lookup by agent name. Raise when a required agent is missing or disabled.
- Keep game sockets inside `src/net`. The local control listener is `src/net/local`. The CLI invoker is the other end of that socket. `src/play` may send and read lines through `CommandChannel`, and agent documents do not open sockets.
- Use the standard library `logging` module. Do not log passwords, JWTs, or `Authorization` headers.
- Preserve the telnet client's refusal of option negotiation. The game server speaks telnet IAC; the client answers `WILL` with `DONT` and `DO` with `WONT`.

## Change Discipline

- Do not update another repository to meet the requirements of the current iteration. Implement the change in this runtime. Leave som-server-modulith, springs-of-mud-server, springs-of-mud-ui, springs-of-mud-designer, and every other checkout unchanged unless the user explicitly asks for that repository to change.
- Keep persona, account name, character name, and enabled state on the agent document served by `GET /api/v1/agents`. `SOMDB.Agents.json` remains the unit-test fixture.
- Keep the login request and the telnet `logon` line compatible with `springs-of-mud-ui` and `springs-of-mud-server`.
- The cutover from the JSON snapshots is these REST clients. A live Mongo client is still out of scope. The database name `SOMDB` and collection name `Agents` stay in config.
- Do not commit passwords, tokens, or local `.env` files.
- Avoid broad refactors of the telnet byte parser unless a test covers the negotiation change.
