# Personality

Proposal for the disposition that decides when people take a step the strategies would otherwise take, and what the character says when they do. This document does not change the runtime.

The operator's plan stays where it already lives. `goal.risk` is the notch ceiling. `practice.style` is the training list. Gear goals are the replace and enchant list. Personality does not raise the notch, reorder practice, or wear a piece. It answers two questions the engine already has and currently answers with one greeting:

- After the level child has been asked, does the next installed child get this step, or does a person?
- When the character speaks, which verb and which words go out?

`docs/proposals/Strategy.md` still owns `LevelStrategy.direct`. That method stays `(view, command_catalog)`. Its tests that `practice`, `train`, and `cast` are absent stay true. `docs/proposals/Goal.md` still owns the clock. `GoalView` does not gain a personality field. `docs/proposals/Practice.md` and `docs/proposals/Gear.md` still run, in that order, when this disposition leaves them the step. `docs/proposals/Memory.md` still keeps session facts off the character knowledge document. `docs/proposals/GameplayEngine.md` still runs danger, flight from a fight we did not start, standing up, and an owed reply before any of this. Parsers stay in `src/play`. The disposition lives in `src/personality`. It is not a `Strategy`.

## What a personality is

Three axes. Each axis is one decision the engine already branches on.

| Axis | Values | Decision |
| --- | --- | --- |
| `bearing` | `intent`, `civil`, `sociable` | Which yield in the strategy sequence may be spent on a person. |
| `company` | `solo`, `civil`, `companion` | Who is addressed, and whether `follow` or `group` is offered. |
| `manner` | `spare`, `plain`, `warm` | The words, or the social, used when speech is already chosen. |

A named personality fills all three. An operator who wants a different mix sets the three fields and leaves the name out.

| Name | Bearing | Company | Manner |
| --- | --- | --- | --- |
| `hunter` | `intent` | `solo` | `spare` |
| `traveler` | `civil` | `civil` | `plain` |
| `companion` | `sociable` | `companion` | `warm` |

`hunter` spends the step on the plan until every installed child has yielded, and then still does not greet. An owed tell is answered, in the short form below. `traveler` may greet once the level child has yielded, and does not follow anyone. `companion` may speak during a repop wait, greet, follow an agentic friend, and group a player who is following us.

Absent `personality` section: no disposition is installed. The engine proposal's greeting, reply templates, and company phase stay as written there. Installing this package does not change a process whose config has no section.

## Config

`resources/agent.yml` gains an optional `personality` section. `AgentConfig` reads it the way it reads `goal`. The values are handed to `Personality`. They are not a goal setting and not a strategy setting.

```yaml
personality:
  name: traveler
```

A mix uses the axes and no name:

```yaml
personality:
  bearing: civil
  company: companion
  manner: plain
```

`Personality.from_section` raises:

- A present section with no name and no axes: `ValueError("personality needs a name or a bearing, company, and manner")`.
- `name` together with `bearing`, `company`, or `manner`: `ValueError("personality.name cannot be combined with bearing, company, or manner")`.
- Any other name: `ValueError("personality.name must be hunter, traveler, or companion")`.
- Name omitted and any axis omitted: `ValueError("personality.bearing, personality.company, and personality.manner are all required")`.
- Any other bearing: `ValueError("personality.bearing must be intent, civil, or sociable")`.
- Any other company: `ValueError("personality.company must be solo, civil, or companion")`.
- Any other manner: `ValueError("personality.manner must be spare, plain, or warm")`.

The agent document is unchanged. `Agent.description` stays the one-sentence persona the greet and reply prompts already accept. The fixture sentence is `Scott Neibarger's agentic player.` That sentence is a voice hint. It is not written into the game with `description`. `Info.do_description` with no argument prints `Your description is:` and `(None).` when the character has none. `look` at a person with an empty description prints `You see nothing special.` Publishing the operator sentence would put it on that look. This proposal does not send `description`.

Alignment stays on the gear proposal. It decides what can be worn. It is not a fourth axis.

## When the plan keeps the step

The engine still holds one `Strategy`. When a personality is installed, the composition root wraps the installed children in one `SequenceStrategy` if they are not already wrapped, including a lone level strategy. The loop still does not name `LevelStrategy`, `PracticeStrategy`, or `GearStrategy`.

`SequenceStrategy.direct` gains an optional `on_yield` callable. The engine passes it only when a disposition is installed, the same way it passes `practice_catalog` only to a strategy that accepts it. `LevelStrategy.direct` does not grow a parameter. With `on_yield` omitted, the sequence is still the first child directive, and the gear and practice tests that depend on that stay true.

After each child returns, the sequence calls `on_yield(child_index, directive, last)`. `last` is true when this child is the last installed one. The callable is the engine method that asks the disposition. The sequence does not import `src/personality`.

- The callable returns a directive: the sequence returns that directive and does not ask a later child.
- The callable returns nothing, and the child returned a directive: the sequence returns the child's directive.
- The callable returns nothing, and the child returned nothing: the sequence asks the next child.

`Disposition.interrupt` is that decision. It returns one `Directive` with role `speak`, or nothing. `speak` joins `equip`, `cast`, `question`, and `learn` as a role added after the strategy proposal. `allow_social` on it is false. The speak line is the greeting, so the engine does not greet a second time on that step.

`interrupt` returns nothing in all of these cases. A directive the child returned then stands. A child that returned nothing leaves the next child to be asked:

- `social_due` is false. The engine's existing `play.social_every` counter is that flag. Default 4. An owed reply does not wait on it and is not this call.
- `view.fighting` is true.
- The child returned a directive whose role is anything other than an empty `hold`. A hunt, a flee, a rest, a recover, a survey, a travel, a checkpoint, a learn, an equip, a cast, and a gear question all keep the step. A `hold` whose command is non-empty keeps the step.
- The child returned an empty `hold` and the bearing is `intent` or `civil`. That hold is the repop wait in the level algorithm. `civil` leaves the wait in place. `sociable` may spend it, below.
- The child returned nothing, the bearing is `intent`, and a later child is still installed. Practice and gear run. `intent` speaks only after the last child has also returned nothing.
- The child returned nothing, the bearing is `civil` or `sociable`, and this child is not the first child and not the last. The one opening is the level child's yield. A later yield is not a second opening. The last child's yield is the idle opening, for every bearing.

`interrupt` may return `speak` in three openings:

1. **Sociable wait.** The child returned an empty `hold`, `fighting` is false, and the bearing is `sociable`.
2. **Civil opening.** The first child returned nothing, and the bearing is `civil` or `sociable`.
3. **Idle opening.** The last child returned nothing. Every bearing, including `intent`. `solo` then declines inside the act choice, so a hunter's idle opening still sends nothing.

One speak per opening. The next non-answer steps belong to the children until `social_due` is true again. A companion does not hold practice shut. It inserts one act on the cadence the engine already counts.

The model is not asked which opening applies. `play.defer` stays the speech switch it already is. `bootstrap.defer` is untouched.

## Who is addressed

`Disposition.act` chooses the addressee once an opening has matched. The engine prepares it with the room's people, the bonds, the known commands, whether the stored help topic `SOCIALS` contains the word `nod`, the character name from the agent document, and `social_due`. People are the situation's list: players in this room, excluding self. Mobiles and NPCs are not in the choice. A bond at standing `avoid` is not addressed.

`company` `solo` returns nothing from `act`. The owed reply has already been sent by the engine.

For `civil` and `companion`, the first matching act is the step:

1. **Continue.** `companion` only. A player in the room at standing `talking` or `grouped`, or whose bond `company` is `following`, agentic first, then the lowercase name. Skip a player whose `last_utterance` is already the continue line for this room.
2. **Greet.** A player at standing `unknown` or `noticed`. Agentic first, then the lowercase name. A player at `greeted` waits for them to answer. The engine proposal's transition to `talking` stays the observer's job.
3. **Group.** `companion` only. A player in the room who has produced `<Name> now follows you.` since we last grouped them, `group` known under category `group`, and our own bond `company` is not `following`. We group a player who follows us. We do not group a player we are following. The group command answers `%t isn't following you.` and `But you are following someone else!` for those two mistakes.
4. **Follow.** `companion` only. An agentic player in the room at standing `talking`, `follow` known under category `group`, bond `company` empty, and not `refused`. One follow.

`civil` stops after the greet. It does not continue, group, or follow. A room with nobody on that list returns nothing, and the next strategy child runs.

The same line is not sent twice. When `last_utterance` is already the line this act would send, that player is skipped and the next player is considered. When every candidate would repeat, `act` returns nothing.

`say`, `tell`, `reply`, `follow`, and `group` are sent only when `CommandCatalog.pick` returns them under the category in the strategy proposal. `say`, `tell`, and `reply` are `information / communication`. `follow` and `group` are `group`. A help-only command list does not make `group` available. That is the memory proposal's `known_commands` rule. `nod` is a social, resolved by `SocialHandler`, and it is not on the SUMMARY index. It is sent when the stored help topic `SOCIALS` contains the word `nod`. It is not sent because a help page merely exists.

## What is said

Manner chooses the words after the act is chosen. With `play.defer` true, or when the `greet` or `reply` prompt is missing, the line is the template. With `play.defer` false and the prompt loaded, the model returns the words only, for `plain` and `warm`. The engine still supplies the verb. The prompt's user fields gain `manner` beside the persona, our character name, their name, and the line they said for a reply. `spare` does not call the model for a room greeting.

| Act | `spare` | `plain` | `warm` |
| --- | --- | --- | --- |
| Greet, other player | `nod <name>` | `say Hello, <name>.` | `say Hello, <name>. I'm <character>.` |
| Greet, agentic | `nod <name>` | `say Hello, <name>. I'm <character>.` | `say Hello, <name>. I'm <character>.` |
| Continue | `nod <name>` | `say Hello, <name>.` | `say Good to see you, <name>.` |
| Reply to a tell | `reply Hello.` | `reply Hello, <name>.` | `reply Hello, <name>.` |
| Reply to a named say | `say Hello.` | `say Hello, <name>.` | `say Hello, <name>.` |

`plain` keeps the engine proposal's split: an agentic greeting includes our name, and another player's greeting is `say Hello, <name>.` `warm` uses our name for both. `spare` uses `nod` for a room act. A tell is still words. `nod` does not answer a player who is in another room.

When `reply` is not known, a tell reply uses `tell <name>` and the same words, which is the engine proposal's fallback. When `say` is not known, a room greeting uses `nod` if `nod` is available. When `nod` is not available, `spare` uses the `plain` say line. When that verb is also unknown, the act returns nothing and the next child runs.

These lines are not used:

- `pose`. `Communications.do_pose` picks `random.choice` among payload keys that start with `pose_`. The stored keys are `poseHeroic`, `poseCautious`, `poseHappy`, `poseYawn`, and `posePonder`. Help `EMOTE PMOTE POSE SOCIAL` says the message depends on class and level. The code picks at random. The character cannot choose the pose. `pose` is not sent.
- `wave`. The social's `victFound` is `$n waves goodbye to you.  Have a good journey.` That is a farewell. The spare greeting is `nod`, whose `charFound` is `You nod at $N.` and whose `victFound` is `$n nods at you in agreement.`
- `gossip`, `shout`, `yell`, `question`, `quote`, `grats`, `auction`, and `music`. A bare `gossip` toggles the channel. The payload lines are `Gossip channel is now ON.` and `Gossip channel is now OFF.` This proposal does not send a channel verb with or without an argument.
- `emote` and `pmote`. A free emote is a second way to say what `nod` already says, and `pmote` rewrites the target's name into the text.
- The gear question templates `What are you wearing on your <slot>?` and `What weapon are you using?` A `question` directive is performed as the gear proposal wrote it. Manner does not rewrite it.

A gear question also fails the interrupt test above, because its role is `question`. The question keeps the step.

## Company

`follow` and `group` are companion acts. They use the same openings as speech. They do not run during a level hunt.

The follow payload's success line to the follower is `You now follow %t.` The leader sees `%c now follows you.` The refusal when the target blocks followers is `%t doesn't seem to want any followers.` `You already follow yourself.` is the self case. `Follow whom?` and `They aren't here.` are the miss. Follow's command position is `POS_RESTING`. Asleep is `In your dreams, or what?`

The group payload's success line to the leader is `%t joins your group.` The new member sees `You join %c's group.` `%t isn't following you.` means we tried to group someone who is not our follower. `But you are following someone else!` means we are already a follower. Both are refusals of a `group` we should not have sent. The act order above avoids them. If one still arrives, the bond is left as it was and `group` is not retried that visit.

Bond fields this proposal adds on `SocialConnection`, beside the engine proposal's standing, pending, and last utterance:

- `company`. Empty, `following`, or `refused`.
- The continue check uses `last_utterance` and `last_room`. A continue line already stored for this room is not sent again.

`You now follow <name>.` sets `company` to `following`. It does not set standing to `grouped`. `<Name> now follows you.` records that this player is a follower, so a later companion opening may `group` them. `%t joins your group.` and `You join <name>'s group.` set standing to `grouped`. `%t doesn't seem to want any followers.` sets `company` to `refused` for that name. Standing stays. `avoid` remains the engine proposal's mark for a player who is in a fight against us. A follow refusal is not that mark. `You stop following <name>.` clears `following`.

`gtell` stays unused until a group line above has been seen. The engine proposal already holds it for that reason.

The engine proposal's stand rule still applies before `say`, `nod`, and `follow` when the last score says the position is sleeping, resting, or sitting. This proposal does not add a second stand rule. `reply` remains legal at `POS_SLEEPING` on the reply command, so an owed tell does not wait for `stand`.

## Lines the observer claims

`PlayObserver` applies these. `Disposition` does not parse. Our own echoes update `last_utterance` and do not set `pending`, which is the engine proposal's rule for `You say '...'` and `You tell <name> '...'`.

- `You nod at <name>.` A spare greet or continue landed. Standing moves from `unknown` or `noticed` to `greeted` on a greet. A continue leaves standing as it was. `turns` increases on a greet.
- `Nod your head off -- they aren't here.` The send missed. Clear the attempt. Leave standing and `company` unchanged.
- `You are anti-social!` `SocialHandler._denial` returns this when `COMM_NOEMOTE` is set. `nod` is marked unavailable for the session. The next spare room act uses the plain say line. The emote command's own refusal is `You can't show your emotions.` A `nod` refusal is the social sentence, and the observer claims that one.
- `You now follow <name>.` `company` becomes `following`.
- `<Name> now follows you.` That player can be grouped on a later opening.
- `<name> doesn't seem to want any followers.` `company` becomes `refused`.
- `<name> joins your group.` and `You join <name>'s group.` Standing becomes `grouped`.
- `<name> isn't following you.` and `But you are following someone else!` Leave the bond. Do not send `group` to that name again this visit.

A say that does not name us, a channel line, and an NPC tell stay as the engine proposal recorded them. Version 1 of that proposal does not answer a channel. This proposal does not add that answer.

## Where it sits in the step

1. Drain and observe.
2. Danger, leave-threat, and stand. Unchanged.
3. An owed reply. When a disposition is installed, `Disposition.reply` supplies the verb and the words. The reply is still sent. `solo` answers. When no disposition is installed, the engine proposal's templates stay.
4. `strategy.direct(...)`. When a disposition is installed, the sequence calls `on_yield` after each child. A returned `speak` is performed. A child's directive is performed when the disposition leaves it. Practice still waits while level returns a hunt, a flee, or a rest. Gear still waits while practice returns a directive.
5. When `direct` returns nothing and no disposition is installed: the engine greeting, under `play.social_every`.
6. When `direct` returns nothing and a disposition is installed: the disposition already declined. The step does not greet again.
7. Wait.

A speak directive does not skip a flee that the level child returned. The flee fails the interrupt test and is the directive the sequence returns.

## Types

| Type | File | Role |
| --- | --- | --- |
| `Personality` | `src/personality/Personality.py` | The loaded section. Name or axes. `from_section` raises the errors above. |
| `Disposition` | `src/personality/Disposition.py` | `interrupt` and `act` and `reply`. Built from one `Personality`. Not saved. |
| `SocialConnection.company` | `src/memory/SocialConnection.py` | Empty, `following`, or `refused`. The engine proposal's bond gains the field. |

`WorkingMemory` already stores the bond once the engine proposal's bond phase exists. `to_collection` writes `company` with the bond. A missing value restores empty. `clear` drops the bond with the rest of the session. The knowledge document does not gain a `personality` key or a `company` field. There is no section registry. Personality is config, read once at construction.

The disposition does not send telnet, open a socket, call Ollama, or write memory. The engine sends the line and tells the observer what came back. Constructing `OllamaClient` still sends nothing. Only `complete` does, and only for a `plain` or `warm` greet or reply when `play.defer` is false and the prompt is loaded.

## Tests

`tests/test_personality.py`. No socket, no model, no live suite. The sequence cases construct a `SequenceStrategy` with two fake children and pass `on_yield`.

- Each named personality fills the axes in the table. A name combined with an axis raises the error named above. An unknown name, an unknown axis, a missing axis, and an empty section each raise the error named for it.
- `intent` returns nothing when the first child yields and a later child exists. It returns a greet when the last child yields, company is `civil`, and a player at `unknown` is in the room.
- `civil` returns `say Hello, <name>.` when the first child yields, and returns nothing when that child returns `kill`. A second child yielding, with a third still waiting, returns nothing.
- `sociable` returns a speak directive when the child returns an empty `hold` and `fighting` is false. The same hold while `fighting` is true returns nothing. A `hold` with a command returns nothing. A `question` directive returns nothing.
- `social_due` false returns nothing on a civil opening.
- `solo` returns nothing for a room that contains a player. `reply` for a pending tell is still `reply Hello.` under manner `spare`.
- Two players, one agentic, both `unknown`: the agentic player is the greet. An NPC and a mobile in the same room are not. A player at `avoid` is not.
- `companion` continues with a `talking` agentic player before greeting an `unknown` player. The continue line is `say Good to see you, <name>.` A second opening in that room does not repeat it.
- `companion` returns `follow <name>` for an agentic player at `talking` when nobody needs a greet. It returns nothing for a player at `greeted`. It returns `group <name>` when that player has followed us, and nothing when our own `company` is `following`.
- `You now follow <name>.` sets `company` to `following` and leaves standing. `<name> doesn't seem to want any followers.` sets `refused` and leaves standing off `avoid`.
- Spare greet is `nod <name>` when the help text contains `nod`. It is the plain say line when the help text does not. `You are anti-social!` makes the next spare act the plain say line.
- The acted verbs do not include `pose`, `wave`, `gossip`, `emote`, or `description`.
- A sequence whose first child returns `kill` returns `kill` with a companion disposition installed. A sequence whose first child returns nothing, disposition `traveler`, returns the greet and does not ask the second child. A sequence whose first child returns nothing, disposition `hunter`, asks the second child.
- `LevelStrategy` directives still omit `practice`, `train`, and `cast`. A knowledge `to_document` has no `personality` key.

## Phases

1. **Disposition.** Config, `interrupt`, `act`, and `reply` against hand-built people and a hand-built child result. No telnet. No sequence. No voice prompts.
2. **Sequence.** `on_yield` on `SequenceStrategy`. The composition root wraps a lone level strategy when a personality is installed. Depends on the strategy types those proposals introduce. Level, practice, and gear algorithms stay as written. No voice prompts.
3. **Lines.** Observer updates for `nod`, follow, and group. Bond `company` round-trips through `to_collection`. `play.defer` true sends no Ollama request. A missing greet prompt uses the template. The live suite stays out.

## Gaps this proposal leaves in place

- There is no path to a person. Speech and follow happen in the room the plan already entered.
- Channel lines stay recorded and unanswered. A public channel is easy to spam, and a bare channel verb toggles it.
- The in-game description stays whatever the character already has. `Agent.description` is the prompt hint.
- `pose` stays random on the server and unused here.
- Use of `nod` depends on the stored `SOCIALS` help page containing that word. A server that removes the social falls back to `say`.
- `goal.risk`, the notch, `practice.style`, and the gear goal list are unchanged. A hunter with `practice.style: preference` still trains the operator's names. A companion with `risk: cautious` still flees at half health.
- One social act per `play.social_every` window. Sessions, compares, and hunts use the steps in between.
- The area list, the pace, and `met` are unchanged. Personality does not pick a destination.

## Implementation note

`docs/reference` describes the running code. Add a personality reference in the phase that makes the package real. Until then this file is the description of the disposition. `resources/agent.yml` keeps `bootstrap.defer: true`. This proposal does not start the agent.
