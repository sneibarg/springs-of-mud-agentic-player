---
name: springs-of-mud-server-alignment
description: Align springs-of-mud-agentic-player code with the Springs of MUD server so an agent logs on and plays through the server's real telnet, auth, and command contracts. Use only when the user explicitly requests this skill or runs /springs-of-mud-server-alignment.
---

# Springs of MUD server alignment

Build player behavior from the server that will actually receive it. The server repository is `C:\Users\scott\PycharmProjects\springs-of-mud-server`. The player sees text over telnet. It does not share the server's Python objects.

Read the player `AGENTS.md` for ownership in this repo. Read the server `AGENTS.md` before changing login or play behavior. When a contract is unclear, read the server handler and one server test that exercises it. Copy the observed output into a player fixture. Do not invent a command, payload field, or prompt.

## Procedure

1. Name the player behavior: logon, a command, a prompt, or a piece of world knowledge.
2. Open the server file in the map below and the test that covers that output.
3. Implement the player against that text and protocol. Keep sockets in `src/net`. Put command exchange and parsing in `src/play`. Store learned facts on `WorldKnowledge`.
4. Add or update a `unittest` that feeds server-shaped text and does not open a socket.
5. Run the focused player test, then `python -m unittest discover -s tests` from this repo.

Inspect server collection documents with the server devtools rather than pasting large JSON into context:

```powershell
python -m src.devtools --collections-dir C:\Users\scott\PycharmProjects\springs-of-mud-server\resources\collections summary commands
```

Run that from the server repository root. Use `find`, `get`, and `fields` the same way. Read the server `collection-query` skill when the query shape is unfamiliar.

## Log on

Two steps, in this order.

1. Retrieve the auth token the same way `springs-of-mud-ui` `src/net/rest/AuthClient.py` does. `POST` JSON `{"accountName", "password"}` to `{auth base}/api/auth/login`. The token is the `Authorization` response header. Keep it for later REST calls. Leave it off the telnet line.
2. Connect with `TelnetClient` and send one line:

```text
logon {"accountId":"<account id>","characterId":"<character id>","characterName":"<name>"}
```

`src/server/protocol/MessageCodec.py` accepts a `logon ` prefix plus JSON as `MessageType.AUTH`. `src/server/session/AuthenticationService.py` requires `accountId` and `characterId`. `src/server/handlers/ConnectionHandler.py` rejects a first message that is not that auth payload.

Hosts and ports come from this repo's `resources/agent.yml`. The server's `resources/server.yml` is the telnet port and modulith port. Do not hard-code a new host.

Before the playing prompt, handle these server replies from `ConnectionHandler`:

- `Do you wish to connect anyway (Y/N)?` means the character is already playing. Answer `Y` or `N`. Any other reply gets `Please type Y or N?`.
- `That character is being saved. Please reconnect in a moment.` means stop and retry later.
- `Authentication failed.` and `Invalid authentication message.` mean the logon payload was rejected.
- `[Hit Enter to continue]` means a paged message is waiting. Send an empty line until the page ends.

The playing prompt is rendered by `src/interp/PromptFormat.py` and sent from `MessageBus.send_prompt`. The default form contains `hp`, `m`, and `mv` inside angle brackets, for example `<20hp 100m 100mv>`. Treat that line as the end of the current server reply.

## Play

After the playing prompt, the server reads one telnet line at a time in `ConnectionHandler._game_loop` and passes the text to `InterpHandler.handle_command`. `InterpUtil.extract_parameters` uses the first word as the command name or shortcut and the remainder as arguments. Commands and shortcuts come from `resources/collections/SOMDB.Commands.json`. Handler behavior is under `src/interp/commands/`.

Send the next command only after the previous reply has ended. A normal reply ends at the playing prompt. A paged reply ends only after each `[Hit Enter to continue]` has been acknowledged.

Learn commands from the server's `commands` output, then read `help <name>` for each name. Do not freeze a private command list in Python when `commands` already returns the set this character can use.

| Player action | Server output to parse | Server source |
| --- | --- | --- |
| Available commands and help | `commands`, `help <name>` | `src/interp/commands/Info.py` `do_commands`, `do_help` |
| Areas | `areas` columns, 39 characters wide | `Info.do_areas`, `Info._area_credit_line` |
| Other players | `who` lines, then `Players found:` | `Info.do_who`, `src/util/InfoUtil.py` `who_line` |
| Current room, exits, occupants | `look` | `Info.do_look`, `src/area/RoomHandler.py`, `src/util/PlayerUtil.py` `format_visible_character_line` |
| Movement | `north`, `east`, `south`, `west`, `up`, `down` | `src/interp/commands/Movement.py`, `RoomHandler.move_player` |
| Objects | `get`, `drop`, `inventory`, and related commands | `src/interp/commands/Object.py` |
| Combat | `kill` and the combat round text | `src/interp/commands/Fight.py`, `src/combat/CombatHandler.py` |
| Speech | `say` and the other communication commands | `src/interp/commands/Communications.py` |

For a command not in this table, find its document in `SOMDB.Commands.json`, then open the handler named there. Match the player parser to that handler's return text.

Mark a `who` character `agentic` only when the name matches a character name in this repo's Agents collection. The logged-in character is `self_character`. In room text, a name that matches `who` is a player. A proper name that does not match `who` is an NPC. An article-led description (`a`, `an`, `the`, `some`) is a mobile. Change this rule only when server output shows a better distinction, and update the player test with that output.

## Verification

Player tests belong in `tests/` and add `src` to `sys.path`. Prefer a short fixture quoted from the server handler over a live telnet session. When the user asks to try a real login, use `SOM_ACCOUNT_PASSWORD` and `python src/main.py --agent <name>`. Do not print the password or the auth token.
