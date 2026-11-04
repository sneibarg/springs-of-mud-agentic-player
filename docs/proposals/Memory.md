# Memory

Refactor proposal for the memory subsystem: `WorkingMemory` and `WorldKnowledge`. This document does not change the runtime.

The engine, strategy, and goal proposals add types these two classes will be asked to hold. The review rule used here is responsibility: the object that owns an invariant keeps the operations that maintain it, and scheduling, transport, and algorithms stay outside. No pattern is added unless the current code already shows the duplication or the coupling.

`docs/proposals/GameplayEngine.md` joins the two stores at read time into a `Situation`. `docs/proposals/Strategy.md` builds a `CommandCatalog` from the union of their command lists. `docs/proposals/Goal.md` stores `Progress` on the agent-memory document and builds a `GoalView` from both stores. None of those proposals replaces either aggregate.

## The two stores stay

They are different records, with different keys and different documents.

| | `WorkingMemory` | `WorldKnowledge` |
| --- | --- | --- |
| Question | What is this agent in the middle of? | What has this character learned about the world? |
| Saved by | `PUT /api/v1/agent-memory/{agentName}` | `PUT /api/v1/agent-knowledge/{characterId}` |
| Identity | Agent name | Character id |
| Holds today | Beings, rooms, commands, considers, conversations | Help, commands, areas, players, mobiles, NPCs, one room, login lines |

Merging them into one object would put goal progress and bonds on the character snapshot, or who-identity and help pages on the agent document. A knowledge save replaces the whole document. A session fact added there is wiped by the next snapshot that forgets to copy it. The proposals already keep bonds and `Progress` off `to_document`. This refactor keeps that boundary.

The new types land as themselves:

- `SocialConnection` (`src/memory/SocialConnection.py`) owns standing, pending, and the last utterance. `WorkingMemory` stores and finds it. It does not grow `note_heard` / `note_spoken` beside `remember_player`.
- `Progress` (`src/goal/Progress.py`) owns the clock, `note_score`, `note_death`, and `view`. `WorkingMemory` holds one instance and serializes the `goal` section. It does not grow notch math.
- `GoalView` and `Situation` are built by the goal package and the engine. They are not stored.
- `CommandCatalog` is built by the strategy package each step. It is not a third command list.

## What is wrong with the classes as they stand

### One command invariant, two implementations

`WorkingMemory.remember_command` (`src/memory/WorkingMemory.py`, around line 129) and `WorldKnowledge.remember_command` (`src/play/WorldKnowledge.py`, around line 116) implement the same rule: a blank category or blank help text does not erase a stored value, and order follows the first insert. `SessionCommand` and `CommandRecord` are the same three fields. Both `replace_commands` methods copy with `getattr` on `name`, `category`, and `help_text`.

`Bootstrapper._publish_commands` copies the session list onto knowledge. `main._begin_play` copies `command_records()` back onto the session and leaves every other section. With `bootstrap.defer` false, categories and model help text stay on the session, and `to_document` writes only `WorldKnowledge._command_order`. A later save can persist a command list with blank categories while the session still has them. The strategy catalog is a union for that reason.

`command_records` is also a second question. When `_command_order` is empty it synthesizes records from help topics (`WorldKnowledge.py`, around line 138). `has_commands` calls that method, so a document with help topics and no `commands` array skips bootstrap. `tests/test_knowledge_client.py` pins this, and pins that `to_document` still writes `"commands": []`. `summary` counts `_commands`, not `command_records`, so the same object can report zero commands and `has_commands()` true.

If `CommandCatalog` is built from `command_records()`, those synthetic rows become verbs. They have blank categories, so the SUMMARY fallback in the strategy proposal would file them. Help-topic keys are not the server `commands` list.

The refactor splits the two questions. Stored command rows are one list. The help-topic fallback remains the bootstrap skip rule and is not the catalog.

### The session reaches into the world snapshot

`absorb_world` (`WorkingMemory.py`, around line 318) copies players, mobiles, NPCs, and the current room's name, description, and exits. It uses `getattr` for `self_character`, `agentic`, `pose`, `detail`, and `auras`. It does not copy room items. It does not copy commands. Knowledge mobiles are keyed `room|name` (`WorldKnowledge._being_key`). Session beings are keyed by name only (`_upsert`). Two knowledge rows for one name collapse to whichever `absorb_world` visits last, and that row's room becomes the session room.

The engine proposal's join is a read: session being, plus `player_named`, plus the bond. `GoalView` is the same kind of read. A mutating copy on `WorkingMemory` makes the session depend on the knowledge shape, which is why the method is written against `getattr` instead of `PlayerRecord` and `BeingRecord`. `WorkingMemory` cannot import `play.WorldKnowledge` cleanly while `observe_line` already imports `play.WorldReader` and `play/__init__.py` imports `Bootstrapper`, which imports `WorkingMemory`.

`absorb_world` stays behavior-compatible until the engine builds the view. It should not gain `SocialConnection`, `Progress`, or catalog rules.

### Both classes are the document, the review, and the rules

`WorkingMemory.to_collection` camel-cases `to_review`. The operator file and the agent-memory body are one shape. `from_collection` is a second copy of every section. `clear` drops the five dicts by hand. `write_collection` writes the fixture file. `observe_line` parses a look line, peels aura prefixes, and remembers a mobile.

`Conversation` already owns its location check and its interest. `remember_conversation` still merges participants and interest on `WorkingMemory`. `ConsiderOpponent` owns the outlook parse. `remember_consider` still files the reading under two keys and creates a being.

`WorldKnowledge.to_document` and `from_document` are the REST body `KnowledgeClient` sends. That is the right aggregate for that body. The method is also where command order, help topics, areas, beings, and the room are encoded. `summary` reads `_commands` from outside the command API.

Adding the engine's bonds and the goal clock by the same style means every new fact edits `to_review`, `from_collection`, `clear`, and `WorkingMemory`'s method list. `Progress.note_score` and `SocialConnection` transitions would sit beside `remember_room`. Those are different reasons to change.

## Ownership after the refactor

| Fact | Owner | Stored on |
| --- | --- | --- |
| First-wins command name, category, help text, server order | `CommandList` | Both aggregates, one type |
| Which of those rows were actually saved | `CommandList.records` | The `commands` array of each document |
| Help topics standing in for a missing command array | `WorldKnowledge.commands_from_help` | Not written back as `commands` |
| Union the catalog reads: session category wins, knowledge fills a blank, stored rows only | `known_commands(memory, knowledge)` in `src/memory` | Nowhere. The strategy package wraps it with the SUMMARY fallback |
| Who-identity from `who` (level, race, class, title, flags, self) | `PlayerRecord` on `WorldKnowledge` | Knowledge document |
| Presence now (kind, agentic, aggressive, auras, one room name) | `SessionBeing` on `WorkingMemory` | Memory document |
| Last room snapshot, including server `itemLines` | `RoomSnapshot` on `WorldKnowledge` | Knowledge document, one room |
| Rooms visited, including look items | `SessionRoom` on `WorkingMemory` | Memory document |
| Consider outlook | `ConsiderOpponent` | Memory document |
| Conversation topic and interest | `Conversation` | Memory document |
| Bond standing and pending reply | `SocialConnection` | Memory document, `connections` |
| Level clock, notch, pace inputs | `Progress` | Memory document, `goal` |
| Joined people, legal mobiles, untried exits | `GoalView` / `Situation` | Not stored |
| Verb chosen from a category | `CommandCatalog` / `Strategy` | Not stored |

`PlayerRecord` and `SessionBeing` stay different types. One has the `who` line. The other has the aggressive pose and a single current room. `RoomSnapshot` and `SessionRoom` stay different types. One is the last server look, including raw item lines. The other is the map the strategy walks. Unifying them would push either document across the boundary above.

`RoomItem` and `SessionItem` are the same three fields (`name`, `line`, `source`) and `_session_item` does not accept a `RoomItem`. That is a smaller copy of the command-record split. One `LookItem` dataclass, fields only, used by both rooms. No behavior moves with it.

## CommandList

`src/memory/CommandList.py` holds the list. `KnownCommand` is the field dataclass in that file: `name`, `category`, `help_text`. `SessionCommand` and `CommandRecord` are removed after callers use `KnownCommand`. Both names are the same value today.

`remember` lowercases the name, rejects a blank name, appends on first insert, and leaves a stored category or help text in place when the new value is blank. `replace` clears and re-adds. `records` returns the stored order and nothing else. `has_stored` is `bool(records)`.

`WorldKnowledge` and `WorkingMemory` each hold one `CommandList`. Their `remember_command`, `commands`, and `replace_commands` methods delegate, so current callers keep working through the phase that moves them. `replace` takes `KnownCommand` values, not `getattr`.

`WorldKnowledge.command_records` keeps today's fallback so `has_commands` and `tests/test_knowledge_client.py` stay true for a help-only document. The implementation calls `commands_from_help` when the list is empty, and `to_document` continues to write only stored rows. `summary` counts stored rows and stored categories, matching the `commands` array it persists. A help-only document still skips bootstrap and still summarizes zero stored commands. That is the current summary behavior, made the same question as the array.

```python
def known_commands(memory: WorkingMemory, knowledge: WorldKnowledge) -> list[KnownCommand]:
    """Stored rows only. Session category and help text win when non-blank."""
```

Order is the session order when the session has rows, then any stored knowledge name the session lacks. Help-topic synthesis is not included. `CommandCatalog` is constructed from this list. The SUMMARY fallback for a blank category stays in the strategy package, where that proposal already puts it.

`main._begin_play` still copies knowledge command rows onto the session when it skips bootstrap. It copies stored rows when they exist, and the help fallback when they do not, so an old document still fills the session. It still does not copy the room or the players.

## WorkingMemory as a composite

The class remains the agent-scoped aggregate and the `to_collection` / `from_collection` boundary. Sections that already have a type keep that type. New sections are fields, not new families of `remember_*` methods.

Fields:

- `commands: CommandList`
- `progress: Progress`, present once the goal package exists. Until that phase, the field is absent and the document has no `goal` key.
- connections, keyed by name, values `SocialConnection`, once the engine proposal's bond phase exists.

`to_collection` still emits the current sections, camelCase, looked up by `agentName`. It adds `connections` from `SocialConnection.to_json` and `goal` from `Progress.to_document` only when those types are part of the build. `from_collection` restores them through those types. A missing key leaves the section empty. `savedAt` and `id` stay ignored. A blank `agentName` still raises.

`to_review` stays the operator view and gains the same sections, snake_case, so `memory` on the control socket shows bonds and the clock. `to_collection` may keep calling `to_review` and camel-casing it while the shapes match. The day a wire field must differ from the review, the section's own `to_document` is the wire path. `Progress` and `SocialConnection` start that way. Beings, rooms, considers, and conversations do not get a second encoder in this refactor.

`clear` clears every section the instance holds, including connections and progress. Production code does not call `clear` today. The save is the persistence boundary. A clock survives because the process saves and reloads, not because `clear` is selective.

`remember_conversation` stays until a later pass. Moving its merge onto `Conversation` is real, and it is not required to land bonds or the goal clock. `remember_consider` stays. It is the session rule that an estimated opponent becomes a being.

`observe_line` leaves `WorkingMemory`. The fighting-you parse and `split_look_prefixes` are play text. A function in `src/play` reads the line and calls `note_aggressive` and `remember_mobile`. `TestAggressiveMobiles` and `TestAuras` call that function. `WorkingMemory` no longer imports `play`. That removes the cycle that forced the lazy import.

`absorb_world` moves to `src/play` as a function that takes `WorkingMemory` and `WorldKnowledge` and performs today's copy, typed against `PlayerRecord`, `BeingRecord`, and `RoomSnapshot`. Behavior stays: skip `self_character`, do not clear considers, do not pass items, mark a mobile aggressive when pose is `fighting` and detail starts with `YOU`, and collapse by session name. `TestAbsorbWorld` calls the play function. `WorkingMemory` stops describing knowledge fields.

`write_review` and `write_collection` stay on `WorkingMemory`. They are the existing file edges. This refactor does not add a repository. `MemoryClient` and `KnowledgeClient` remain the REST adapters.

## WorldKnowledge

The class remains the character snapshot. `to_document` / `from_document` stay the knowledge body. `HelpTopic`, `AreaRecord`, `PlayerRecord`, `BeingRecord`, and `RoomSnapshot` stay the knowledge records.

Changes:

- Commands delegate to `CommandList`.
- `commands_from_help` is the named fallback. `has_commands` still uses it.
- `to_document` writes stored commands only. A room update on the same instance still saves the command list, because the instance holds the list. Callers keep saving that instance. They do not build a new `WorldKnowledge` for a room.
- No `goal`, `connections`, `considers`, or `conversations` key is added.
- `absorb` is not a method here. Play copies out. Knowledge does not know the session.

`summary` remains the login report. It counts stored commands and stored categories.

Being keys stay `room|name`. The session's one-name key stays the session's rule. The view builder, when the engine exists, is what joins a session being to `player_named`. This refactor does not add that builder and does not extend `absorb_world` into one.

## What this does not add

A repository or unit-of-work around the two clients. The clients are already the adapters, and the documents are already the contracts.

An event bus for "memory changed." The engine calls `note_score`, `note_death`, and `remember` because it already has the line. A bus would hide that order.

A `Strategy` inside this subsystem. The algorithm package is the strategy. Memory supplies `known_commands` and holds `Progress`.

A shared `Being` hierarchy. `PlayerRecord`, `BeingRecord`, and `SessionBeing` are not substitutable. Inheritance would invent a common mutate path the documents do not share.

A plugin registry of sections. Two new sections are known: `connections` and `goal`. They are written out by name.

## Phases

Each phase keeps the current tests green and adds the tests named here. The live suite stays out.

1. **CommandList.** `KnownCommand`, first-wins remember, stored `records`, `known_commands` union, help fallback only through `commands_from_help`. `tests/test_command_list.py` covers a blank category leaving a stored one, session category winning over knowledge, and a help-only knowledge object staying out of `known_commands` while `has_commands()` stays true. Existing bootstrap, knowledge-client, and command tests stay on the delegated methods.

2. **Break the cycle.** Move `observe_line` and `absorb_world` to `src/play`. `WorkingMemory` does not import `play`. Aura and aggressive tests, and `TestAbsorbWorld`, call the play functions and expect the same beings and rooms.

3. **Bonds.** `SocialConnection` and the `connections` section on the memory document, in the engine proposal's bond phase. Round-trip in `from_collection`. `clear` drops them. Knowledge `to_document` has no `connections` key.

4. **Goal clock.** `WorkingMemory.progress` and the `goal` section, in the goal proposal's memory phase. `Progress` serializes itself. A restored document with a different target still starts a fresh clock, as that proposal tests. Knowledge `to_document` has no `goal` key.

5. **LookItem.** One field dataclass for `name`, `line`, and `source`, used by `RoomSnapshot` and `SessionRoom`. `_session_item` accepts it. No change to when bootstrap copies items. Defer false still leaves look-prompt items on the session.

Phases 3 and 4 wait for those types. Phases 1, 2, and 5 do not wait for the engine loop.

## Tests that must stay true

- Blank category or help text on a second remember leaves the stored value. Both aggregates.
- `replace_commands` from knowledge onto the session restores name, category, and help text in order.
- A help-only knowledge document: `has_commands()` is true, `to_document` writes an empty `commands` array, `known_commands` does not invent those names.
- `absorb` still skips the self character, does not clear considers, does not strip session room items, and still collapses two knowledge mobiles of the same name to one session being.
- `(White Aura)` on a fighting-you line is stored. `(Invis)` is not.
- `from_collection` ignores `savedAt` and `id`, rejects a blank agent name, and restores conversations, considers, rooms, and items.
- A knowledge save of the in-memory object after a room change still contains the stored command rows.

## Gaps this proposal leaves in place

- Untried exits stay process-local, as the strategy proposal says, until a later phase saves them. They are not added to either document here.
- The area the character is standing in is still not a field on either store.
- `main._begin_play` still does not copy the saved room or players into the session. The engine proposal's opening `look` and `who` cover that. This refactor does not change the skip.
- `remember_conversation`'s merge stays on `WorkingMemory` through these phases.

## Implementation note

`docs/reference/WorkingMemory.md` and `docs/reference/WorldKnowledge.md` describe the running code. Update them in the phase that moves each behavior. Until phase 1 lands, this file is the only description of the refactor.
