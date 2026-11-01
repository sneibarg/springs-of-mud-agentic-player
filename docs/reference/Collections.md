# Collection Data

The JSON files under `resources/collections` remain fixtures. Live agent, prompt, and memory documents come from `GET /api/v1/agents`, `GET /api/v1/agent-prompts`, and `GET /api/v1/agent-memory/{agentName}`.

`SOMDB.Agents.json` is a JSON array of Mongo-style documents. Keep these names and shapes stable so the file can move into the `SOMDB` database collection `Agents` later:

- `_id.$oid` is the document id.
- `name` is the local agent name used by `--agent`.
- `accountName` is the account passed to `/api/auth/login`.
- `characterName` selects a character from the login response.
- `enabled` must be a boolean.
- `description` is designer-facing text.

Leave passwords, JWTs, and telnet hosts out of agent documents. Saved account passwords live in `resources/connections.json`, obfuscated with base64 the same way `springs-of-mud-ui` stores them. Deobfuscate a password only for the login call. Do not log it or write it back as plaintext.

`SOMDB.Memories.json` is a JSON array of session snapshots. Look a document up by `agentName`, the same local name as `Agents.name`. One document belongs to one agent. Its sections are `players`, `agenticPlayers`, `mobiles`, `npcs`, `aggressiveMobiles`, `rooms`, `commands`, `considers`, and `conversations`. Nested names use camelCase, such as `roomName` and `helpText`. This collection is not world knowledge.

Read this collection directly while it stays small. If it grows large, add a local query tool and use that tool before pasting documents into context.
