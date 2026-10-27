# Repository Guidelines

## Project Direction

This repository is the Python runtime for Springs of MUD agentic player characters. An agent is a player that logs into the game server and plays a character on its own.

Game identity and persona live in the `Agents` collection. The long-term source is the `Agents` collection in the `SOMDB` MongoDB database. Until that database is wired in, load the same documents from `resources/collections/SOMDB.Agents.json`.

Add Python for the runtime: collection loading, auth, the telnet session, and later the decision loop. Put ordinary agent tuning in the collection document.

The companion server is `springs-of-mud-server`. The login and telnet behavior follows `springs-of-mud-ui/src/net`.

## Architecture Map

- `src/main.py` loads `resources/agent.yml`, reads the Agents snapshot, logs in, and opens a telnet session for one agent.
- `src/agent` owns `Agent`, `AgentCollection`, `AgentRegistry`, and `AgentConfig`.
- `src/net/rest` retrieves the auth token. `AuthClient` posts to `/api/auth/login` and stores the `Authorization` response header, matching `springs-of-mud-ui`.
- `src/net/telnet` owns the telnet socket client and `PlayerSession`, which sends the server `logon` line.
- `src/util` holds small shared helpers such as camelCase normalization.
- `resources/agent.yml` holds auth URL, telnet host and port, and the collection location.
- `resources/collections/SOMDB.Agents.json` is the current `SOMDB.Agents` snapshot.

## Collection Data

`SOMDB.Agents.json` is a JSON array of Mongo-style documents. Keep these names and shapes stable so the file can move into the `SOMDB` database collection `Agents` later:

- `_id.$oid` is the document id.
- `name` is the local agent name used by `--agent`.
- `accountName` is the account passed to `/api/auth/login`.
- `characterName` selects a character from the login response.
- `enabled` must be a boolean.
- `description` is designer-facing text.

Leave passwords, JWTs, and telnet hosts out of agent documents. Account passwords come from the `SOM_ACCOUNT_PASSWORD` environment variable.

Read this collection directly while it stays small. If it grows large, add a local query tool and use that tool before pasting documents into context.

## Authentication And Telnet

1. `AuthClient.login(account_name, password)` posts `{"accountName", "password"}` to the configured auth base URL plus `/api/auth/login`.
2. The auth token is the `Authorization` response header. `get_auth_headers()` sends it as a Bearer token for later REST calls. A value that already starts with `Bearer ` is not prefixed again.
3. The login body supplies `id` and `playerCharacterList`. `PlayerSession` connects with `TelnetClient` and sends one line:

```text
logon {"accountId":"<account id>","characterId":"<character id>","characterName":"<name>"}
```

That line is the contract in `springs-of-mud-server` `MessageCodec`: a `logon ` prefix plus JSON becomes `MessageType.AUTH`. The game server currently accepts `accountId`, `characterId`, and `characterName`. Keep the JWT off the telnet line so it does not land in game logs. Hold it on `AuthClient` for REST calls.

Default ports match the UI client: auth `http://localhost:8169`, telnet `localhost:6969`. Override them in `resources/agent.yml`.

## Coding Conventions

- Follow the Springs of MUD Python style used by the server and UI. Modules that export a primary type use PascalCase filenames. Domain objects are dataclasses with `from_json`.
- Normalize camelCase collection and service fields to snake_case at the boundary. Internal fields stay snake_case.
- Registries expose lookup by agent name. Raise when a required agent is missing or disabled.
- Keep network I/O inside `src/net`. Agent documents do not open sockets.
- Use the standard library `logging` module. Do not log passwords, JWTs, or `Authorization` headers.
- Preserve the telnet client's refusal of option negotiation. The game server speaks telnet IAC; the client answers `WILL` with `DONT` and `DO` with `WONT`.

## Testing

Use `unittest`. Tests add `src` to `sys.path` and do not open network sockets.

Run focused tests for the area you changed:

```powershell
python -m unittest tests.test_agent_collection
python -m unittest tests.test_auth_client
python -m unittest tests.test_player_session
python -m unittest discover -s tests
```

When changing collection documents, auth parsing, or the logon line, extend these tests with the fixture or the real `resources/collections/SOMDB.Agents.json` snapshot.

## Change Discipline

- Keep persona, account name, character name, and enabled state in `SOMDB.Agents.json`.
- Keep the login request and the telnet `logon` line compatible with `springs-of-mud-ui` and `springs-of-mud-server`.
- Do not add a live MongoDB client until a task replaces the JSON snapshot. The database name `SOMDB` and collection name `Agents` stay in config so that cutover is explicit.
- Do not commit passwords, tokens, or local `.env` files.
- Avoid broad refactors of the telnet byte parser unless a test covers the negotiation change.
