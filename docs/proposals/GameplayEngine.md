# GameplayEngine

Proposal for the loop that plays the character after bootstrap. This document does not change the runtime. Implementation stays in this repository. Sockets stay in `src/net`. Prompt text stays in the Prompts collection. Persona stays on the agent document.

## The gap

`PlayerControl.drive` calls `on_play` once. `main._begin_play` either restores the command list from world knowledge or runs `Bootstrapper`, copies the snapshot into `WorkingMemory` with `absorb_world`, saves, and returns. The mode remains `play`. The drive loop then waits until stop or disconnect. The character stays logged on and sends nothing else.

`bootstrap.initial` has the same shape. Startup can connect, log on, and bootstrap, and the mode stays `idle`. Nobody chooses a second command.

The pieces a player needs are already stored, and nothing reads them as a situation:

- `WorldKnowledge` holds the durable snapshot for one character: help, commands, areas, players from `who`, mobiles, NPCs, and the room from the last `look`. `KnowledgeClient` loads and saves that document.
- `WorkingMemory` holds the session: beings and auras, rooms and look items, commands with category and help text, consider readings, conversations, and aggressive mobiles. `MemoryClient` loads and saves that document per agent.
- `CommandChannel` sends one line and reads until the playing prompt. It drops the prompt text, so `<20hp 100m 100mv>` is visible to the operator and then discarded.
- `Agent.description` is the persona. The fixture is one sentence. There is no goals field.
- The Prompts collection extracts server text. It has no prompt that chooses an action or writes a line of speech.
- `Conversation` records a topic, a place, participants, and an interest priority. It does not record whether we owe someone a reply, or what standing we have with them.

The server has no friendship command. A connection is formed by the lines the character sends: `say`, `tell`, `reply`, channel speech, a social, `follow`, and `group`. Those commands already exist in `springs-of-mud-server` `Communications` and `SocialHandler`. The engine uses them. It does not add a game feature.

## Role

`GameplayEngine` is the play loop. While the control mode is `play` and the telnet session is connected, it reads both stores, chooses one legal command, sends that command through the existing `CommandChannel`, and writes the result back.

Playing the game and forming social connections are both this loop. They are two sources of the next command, under one order of priority. Survival and an unanswered tell both outrank wandering.

The engine runs on the drive thread, the same thread that already runs bootstrap. The control listener only changes mode. One thread talks to the game.

## Ownership

| Concern | Owner |
| --- | --- |
| Logon, telnet bytes, REST, Ollama HTTP | `src/net` |
| Login snapshot: `commands`, `help`, `areas`, `who`, `look` | `Bootstrapper` |
| Operator grammar: `idle`, `play`, `bootstrap`, `memory`, `output` | `PlayerControl` |
| Durable character snapshot | `WorldKnowledge` |
| Session beings, rooms, considers, conversations, bonds | `WorkingMemory` |
| One step of play: observe, choose, send, record | `GameplayEngine` |
| Turning a batch of server lines into those records | `PlayObserver` |
| The joined view one decision reads | `Situation` |

`GameplayEngine` does not open a socket, parse IAC, log a password or a token, or replace `Bootstrapper`. A later `play` still skips bootstrap when knowledge already has commands. `bootstrap` from the operator still reruns bootstrap on the drive thread. The engine pauses for that call, then continues with the new snapshot.

## The two stores

The engine holds both objects for the life of the process. It writes each fact to the store that already means that fact.

`WorkingMemory` is what is true in this session, and what the agent is in the middle of.

- Who is in the current room, with kind, agentic flag, auras, and the aggressive pose.
- Rooms visited this session, including look items when those were stored.
- The command list the character can legally type, with category and help text when bootstrap kept them here.
- `ConsiderOpponent` readings. An outlook is an estimate. It goes stale. It stays off the knowledge document.
- `Conversation` records: one conversation per speaker and place.
- `SocialConnection` records, proposed below. Standing, a pending reply, and the last line we sent.

`WorldKnowledge` is who this character has learned the world contains.

- The command catalog and help pages when they were persisted.
- Areas, the `who` identity of a player (level, race, class, title, agentic, self), and the last room snapshot.
- Mobiles and NPCs already recorded by name and room.

The engine joins them by name when it builds a `Situation`. A player in the room is the session `SessionBeing`, plus `WorldKnowledge.player_named` when that record exists, plus the session `SocialConnection` and any `Conversation`. The agentic flag is taken if either store has it. The logged-on character is left out of the people the engine may greet. `PlayerRecord.self_character` and the logon name both mean that person.

Session sections stay off `WorldKnowledge.to_document`, except the command records bootstrap already publishes. Bonds, considers, and conversation text stay on working memory. That document is already saved with `PUT /api/v1/agent-memory/{agentName}` and restored with `from_collection`. A bond therefore survives the next process start without a new modulith collection.

A knowledge save still replaces the whole document. The engine keeps the in-memory `WorldKnowledge` from bootstrap or from `from_document` and saves that object. It does not build a partial body. A room update must not drop the command list. When `bootstrap.defer` is false, model help text lives on working memory and the knowledge command list may be empty. The engine treats a command as known when either store has it.

A later `play` today restores commands and does not absorb the stored room or players. The engine's first step in that case is one `look` and one `who`, so the session has a current room and the people in it. That is not a second bootstrap. Help pages are not read again. When this process just finished bootstrap, those two commands are skipped. `_begin_play` tells the engine whether the snapshot is fresh.

## One step

`step` does five things, then returns. The drive loop calls it again while the mode is `play`.

1. **Drain.** Read lines the server has already queued: says, tells, arrivals, combat, the tick. Answer the same gates `CommandChannel` already answers (`[Hit Enter to continue]`, the replace-existing prompt). Do not send a command in order to hear these lines.
2. **Observe.** `PlayObserver` applies that batch, and the reply of the previous command, to both stores.
3. **Join.** Build one `Situation` from working memory, world knowledge, the last playing prompt, and the engine's own step counters.
4. **Choose.** The first matching priority below produces at most one command.
5. **Act and record.** `CommandChannel.exchange` sends it. The reply is observed before the next choice. Our own echo is recorded as speech we sent, so it does not become a debt to answer.

`idle` stops the loop between steps. A step that has already sent a command finishes that exchange. The engine does not send `quit`. The session stays connected, which is the current idle rule. The existing end-of-process memory save still runs. The engine also saves memory when it goes idle and after each social exchange, so a killed process keeps the bond. A failed save is logged and play continues.

Disconnect, `PromptTimeout`, and the channel's existing auth and save failures stop the loop and are reported. The mode is left as the operator set it.

## Hearing the world between commands

`CommandChannel.exchange` is one command, then lines, then a prompt. Play also happens while the character is quiet. Someone tells us. A mobile arrives already fighting. Those lines sit on the telnet client until something polls.

Add `drain` on `CommandChannel`. It returns queued lines and does not send. It uses the same gate handling and the same prompt test. When the polled line is a playing prompt, store it on `last_prompt` and leave it out of the returned text, matching `exchange`. `exchange` also stores `last_prompt`.

The engine drains at the start of every step, including a step whose choice is to wait. A wait sends nothing. It only listens, then returns. Waiting is how the character stands in a room long enough to be spoken to.

The prompt `<20hp 100m 100mv>` is parsed locally. Hit points, mana, and movement are integers on the `Situation`. They are not sent to Ollama. `score` is a later command, used when the policy needs hunger, position, or wimpy. The `score` prompt already knows how to read that page. With `play.defer` true, that call is skipped and the playing prompt is the only vital sign.

## Situation

`Situation` is a frozen value built for one step. It has no behavior beyond the facts the policy reads. It can live beside the engine until it grows a function, and then it moves to its own file under the repository rule.

Fields:

- `room_name`, `exits`, `items` from the session room.
- `hit`, `mana`, `movement` from `last_prompt`, each null when no prompt has been seen.
- `fighting`: true after we send `kill`, or after a mobile line ending in `is here, fighting YOU!`. Cleared when we send `flee` or the observer sees that fight end. The death and flee lines are pinned from the server message catalog in the combat phase, in a test fixture, before that phase sends `kill`.
- `people`: beings whose session `room_name` is this room, excluding self. Each entry carries kind, agentic, aggressive, the knowledge identity when present, consider outlook when present, and standing.
- `pending`: the bond that is owed a reply, if any.
- `known_commands`: the union of session commands and knowledge command records.
- `fresh_room`: true when this process already ran `look` for this room.

## What the next command may be

A command is sent only when its verb is in `known_commands`. Directions printed by `look` (`north`, `south`, `east`, `west`, `up`, `down`) are allowed when that word is in the command list. The engine does not invent a verb from a help page it has not stored.

Version 1's policy uses this set, and only when the verb was learned:

`look`, `who`, `score`, `stand`, `rest`, `say`, `tell`, `reply`, `north`, `south`, `east`, `west`, `up`, `down`.

Later phases add `consider`, `kill`, `flee`, `recall`, `follow`, `group`, and `open`, under the same known-command rule. Social names such as `wave` are added only after the stored `socials` help page names them. They are server socials, resolved by `SocialHandler`, and they often do not appear in `commands`.

`kill` is never aimed at a player in this proposal. `murder`, `steal`, `quit`, `delete`, and wizard commands are outside the policy set even if a trusted character's command list contains them.

Speech requires the server position `POS_RESTING` or better. `say` answers `In your dreams, or what?` while sleeping. If the last `score` says the position is sleeping, resting, or sitting, the engine sends `stand` before a greeting. Until `score` has been read, it attempts the speech command and treats that refusal as "stand, then retry once."

## Priority

The first rule that matches is the whole step. The engine does not ask the model which rule applies.

1. **Danger.** `fighting` is true and the prompt hit points are at or below `play.flee_hp` (default 20). Send `flee` when it is known. This rule is inactive until the combat phase exists. Before that phase the engine never starts a fight, and an aggressive mobile is a reason to leave the room.
2. **Leave a threat.** An aggressive mobile is in this room and we did not start that fight. Send an exit we have not taken. Send `flee` only when the observer says we are in the fight.
3. **Stand.** A speech or movement command was refused because the character is asleep, resting, or sitting. Send `stand`.
4. **Answer.** A `SocialConnection` is `pending`. Send one reply, then clear `pending`. A tell is answered with `reply` when that command is known, otherwise `tell <name> <text>`. A say that names us is answered with `say <text>` in the room.
5. **Greet.** The room has a player whose standing is `unknown` or `noticed`, and no rule above matched. Agentic players come first, then other players. One greeting. NPCs are not greeted in version 1. Mobiles are not greeted. A player with standing `avoid` is not greeted. When `resources/agent.yml` has a `personality` section, `docs/proposals/Personality.md` decides whether this greeting runs and whether it takes a step before a later strategy child. With no such section, this rule stays.
6. **See the room.** This room has no session record yet. Send `look`. Run the same room parse `WorldReader` uses. When `play.defer` is false and the look prompts and an Ollama client exist, the look, items, exits, and mobs prompts may be sent the way bootstrap sends them, and the items stay on the session room. When `play.defer` is true, store the server text and skip those calls.
7. **See who is on.** No `who` has been sent this play, or `play.who_every` steps have passed (default 20). Send `who`. Update knowledge player identities and session beings. An agentic name is still one that matches an agent document.
8. **Move.** Send an exit from this room that this process has not taken. Remember the attempt on the engine, keyed by room name. The destination is unknown until the next `look`, so the tried exit is process-local in version 1. A closed door is left for the later `open` phase. `look_direction` already knows how to read that reply.
9. **Wait.** Drain only. This is a successful step.

`play.social_every` (default 4) counts non-answer steps between greetings. Answering a tell does not wait for that count. The same player is greeted once per session. The same utterance text is not sent twice in a row.

## Social connections

`SocialConnection` is a session record in `src/memory`, next to `Conversation`. It has functions, so it is its own file. `WorkingMemory` stores it the way it stores conversations: remember, lookup by name, include it in `to_review`, `to_collection`, and `from_collection`.

Fields:

- `name`. The character name as the server printed it.
- `standing`. One of `unknown`, `noticed`, `greeted`, `talking`, `grouped`, `avoid`.
- `last_room`. The room name when we last saw them.
- `pending`. Empty, `tell`, or `say`.
- `pending_text`. The line we owe an answer to.
- `last_utterance`. The last line we sent them, so a greeting is not repeated.
- `turns`. How many times we have spoken to them.

Transitions, applied by `PlayObserver` and by the engine after a successful send:

- Seen in a room, standing still `unknown`: `noticed`.
- We greet them: `greeted`, and `turns` increases.
- They answer, or `turns` reaches 2: `talking`.
- `follow` or `group` succeeds in a later phase: `grouped`.
- They are in a fight against us: `avoid`. Version 1 has no player-combat command, so this standing is recorded and then treated as a reason to leave and not to speak.

`Conversation` stays the log of the subject. One conversation per speaker and place. The topic is the speaker's name. The location is `tells`, `room`, or `channel`. The location name is the speaker for a tell, the room name for a say, or the channel name (`gossip`, `question`, `grats`, `quote`, `music`, `auction`). Participants are the speaker and this character. A line addressed to us sets interest high enough that `conversations()` lists it first. The pending flag on the bond, not the interest number, is what forces a reply.

### Lines the observer claims

The command catalog renders these shapes. The observer matches them and ignores our own echoes.

- `You say '...'`, `You tell <name> '...'`, `You gossip '...'`: our echo. Update `last_utterance`. Do not set `pending`.
- `<Name> tells you '...'`: location `tells`, pending `tell`, standing at least `talking` once we answer.
- `<Name> says '...'` when the quoted text contains our character name: location `room`, pending `say`. A say that does not name us is stored as a room conversation and does not demand a reply.
- `<Name> gossips '...'` and the same shape for the other channels: location `channel`. Interest rises when the text names us. Version 1 does not answer the channel and does not start one. Public speech is easy to spam, and nothing in the current memory says we were invited.
- `They aren't here.`, `<name> can't hear you.`, `Your message didn't get through`, and `<name> is not receiving tells.`: the send failed. Clear the attempt. Leave standing unchanged. Do not immediately retry.

Socials aimed at us (`<Name> smiles at you.`) vary by social. Version 1 does not parse them. A later phase can treat a social whose victim text names us as a `noticed` bond and a reason to greet, once those strings are taken from `SOMDB.Socials` into a fixture.

NPC shop and healer speech (`<name> tells you '...'` from a shopkeeper, a healer's `says`) can match the tell pattern. If the speaker is a session NPC rather than a player, store the conversation and do not set `pending`. Version 1 does not buy, sell, or `heal`.

### What a greeting is

With `play.defer` true, or when the `greet` prompt is missing, the line is fixed:

`say Hello, <name>.`

An agentic player gets the character name in that sentence: `say Hello, <name>. I'm <character>.`

With `play.defer` false and a `greet` prompt loaded, the model returns the words only. The engine still sends `say`. The model does not return the verb in version 1.

A tell is answered from the `reply` prompt the same way. The template, when the model is not used, is `reply Hello, <name>.` or `tell <name> Hello.` when `reply` is not known.

`Agent.description` is the voice hint inside those prompts. The prompt must tolerate a one-sentence description. A richer persona is an agent-document change, done when someone edits that collection, not by the engine inventing fields. When a personality is installed, the templates and the `nod` greeting in `docs/proposals/Personality.md` replace this section's fixed lines. The description is still the voice hint, and it is still not sent with the `description` command.

## play.defer

`bootstrap.defer` means bootstrap skips Ollama. It stays that flag. The user's `resources/agent.yml` can keep `bootstrap.defer: true`.

Add `play.defer`, default false, loaded as `AgentConfig.defer_play`. A non-boolean raises `ValueError("play.defer must be a boolean")`, the same rule as `bootstrap.defer`.

When `play.defer` is false, the engine may call Ollama for the `greet` and `reply` prompts, and for the room prompts on a new `look`. When it is true, the engine sends no Ollama request. Greetings and replies use the templates. Room text is stored from the server parse.

Constructing `OllamaClient` still sends nothing. Only `complete` does.

## Prompts

Two new extractor prompts, in the fixture `resources/collections/SOMDB.Prompts.json` and loaded with the existing `GET /api/v1/agent-prompts`. The runtime does not PUT prompts. Live text is whatever the modulith is serving. A missing prompt means the template is used. That gap is reported in the log, and play continues.

`greet` user fields are the persona, our character name, their name, and whether they are agentic. The schema is `{ "text": string }`. The system text tells the model to return one short spoken sentence, with no command verb and no quotes.

`reply` adds the line they said. Same schema.

Neither prompt chooses `kill`, a direction, or a social name.

## Control

`drive` today sets `played` after one `on_play` and does not call it again. Change that contract:

- `on_play` still does the current restore-or-bootstrap work and returns the engine, or nothing if logon or the knowledge load failed.
- While the mode is `play`, `drive` calls `engine.step`.
- `idle` stops calling `step` and leaves the engine in place.
- A later `play` calls `step` again and does not bootstrap again.
- `bootstrap` runs `on_bootstrap` on the drive thread, as it does now. `step` is not called on that iteration. After bootstrap returns, the engine replaces its knowledge reference with the new snapshot and clears the "opening look already done" flag when the operator forced a new snapshot.

`played` for the final memory save becomes true once `on_play` has succeeded, including a command restore. That matches today.

`output` is unchanged. Telnet lines still pass through `GameplayOutput`. The engine does not print its own copy of server text.

## Persistence

Memory: the existing `_save_memory` path. Call it from the engine on idle, after a social send, and every `play.save_every` steps (default 10). The process `finally` block remains the last save.

Knowledge: the existing `_save_knowledge` path, full `to_document`, when `who` or `look` changed a durable field. Skip the save when the step only changed session bonds or tried an exit.

Do not save knowledge from a newly constructed empty `WorldKnowledge`. The engine receives the instance `_begin_play` already loaded or bootstrapped.

## Types

| Type | File | Role |
| --- | --- | --- |
| `GameplayEngine` | `src/play/GameplayEngine.py` | The step loop, the priority, the templates, the save cadence. |
| `PlayObserver` | `src/play/PlayObserver.py` | Apply server lines to both stores. Reuse `WorldReader` parses, `observe_line`, and `parse_consider`. |
| `SocialConnection` | `src/memory/SocialConnection.py` | One bond. `from_json` follows `Conversation`. |
| `Situation` | fields used by the engine; its own file if it gains a function | The joined read model for one step. |

`WorkingMemory` gains `remember_connection`, `connection_for`, and `connections`. `to_review` gains a `connections` list so `memory` on the control socket shows the bonds.

`CommandChannel` gains `drain` and `last_prompt`.

`AgentConfig` gains `defer_play` and the integers `flee_hp`, `social_every`, `who_every`, and `save_every`. The integers have the defaults above. A non-integer raises the same kind of `ValueError` the port already raises.

The engine is play and the bond is memory. A `personality` section uses the package in `docs/proposals/Personality.md`. With no such section, no package is added.

## Phases

Each phase is playable on its own and has unit tests with a fake channel. The live suite stays out of these phases.

1. **Loop.** `drain`, `last_prompt`, `step`, drive integration, opening `look` and `who` after a restore, one unused exit, wait, idle stops the loop without `quit`. No model. No speech. Tests: a queued tell is drained and does not itself send; an exit is sent once; idle sends nothing further; a restored knowledge document still has its commands after a `look` save.
2. **Bonds.** `SocialConnection` on working memory, tell and named-say detection, one template greeting, one template reply, agentic players first, no second greeting, NPC tells stored without `pending`. Tests use server-shaped lines from the command catalog. `play.defer` true sends no Ollama request.
3. **Voice.** `greet` and `reply` prompts when `play.defer` is false. A missing prompt uses the phase 2 template. The model returns words. The engine supplies `say` or `reply`.
4. **Mobs.** `consider` before any `kill`. Outlook `safe` or `even` may `kill` a mobile. `risky`, `fatal`, `unknown`, and a refusal do not. Prompt hit points at or below `play.flee_hp` send `flee`. An aggressive mobile we did not attack is left by an exit. Death and flee lines come from a fixture taken from the server messages.
5. **Company.** `follow` an agentic player already at standing `talking`. `group` is sent only after `<Name> now follows you.` Grouping a player we ourselves follow is refused with `%t isn't following you.` or `But you are following someone else!` A group success sets `grouped`. `gtell` stays out until group membership is observable from a server line we have pinned. When a personality is installed, only company `companion` sends these, on the openings in `docs/proposals/Personality.md`. With no personality section, this phase sends them.

## Tests

`tests/test_gameplay_engine.py`, the same style as `tests/test_bootstrapper.py`: a fake client, no socket, no Ollama process unless the test supplies a fake `complete`.

The phase list above is the assertion list. In addition:

- A command absent from both stores is not sent, and the step falls through to the next priority.
- `You tell Marcus 'Hello.'` does not create a pending reply.
- Two players in the room, one agentic: the agentic player is greeted and the other is not, on that step.
- An aggressive mobile and a player in the same room: the step moves, and no `say` is sent.
- `play.defer` false with a fake client records one completion body for a greeting, and the telnet line is `say` plus the returned text.
- The knowledge document written after `look` contains the command records it had before the step.

## Gaps this proposal leaves in place

These are limits of the current contracts. They are not permission to edit another repository.

- The modulith has no social-connection document. Bonds ride on the existing agent-memory document. A large transcript will make that document large. Version 1 stores standing and the last line, not a scrollback.
- `Agent.description` is one sentence. Voice prompts have little persona to use until that document is richer.
- `GET /api/v1/agent-prompts` must be serving `greet` and `reply` before live play can use them. The fixture update does not update the live collection.
- The playing prompt carries current hit points, mana, and movement, not the maxima. "Low" is an absolute `play.flee_hp` until `score` has been read.
- Tried exits are forgotten when the process exits, because they are not on either saved document in version 1.
- Channel conversation is recorded and not answered.
- Shop, heal, practice, get, wear, and cast are real play, and they are later work. The priority list has a place to hang them: after answers and before wandering.

## Implementation note

Reference docs (`Architecture`, `OperatorControl`, `WorkingMemory`, `Bootstrap`) describe the running code. Update them in the phase that makes each sentence true. Until phase 1 lands, this file is the only description of the engine.
