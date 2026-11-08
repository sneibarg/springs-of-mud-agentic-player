# Strategy

Proposal for the Strategy pattern in `src/strategy`. A strategy is a gameplay algorithm. The engine holds one and asks it for the next command. Another algorithm replaces it by replacing that object. This document does not change the runtime.

The goal and the progress clock are not strategies. They live in `src/goal`, proposed in `docs/proposals/Goal.md`. That package defines the goal and analyzes progress into a `GoalView`. The algorithm reads the view. It does not parse `score`, move the risk notch, or decide whether the pace is behind.

The engine proposal is `docs/proposals/GameplayEngine.md`. The engine is the context. After danger, flight from a fight it did not start, standing up, and an owed reply, it calls the strategy. With no goal configured, that slot stays the engine's wander.

## The pattern

| Role | Type | Job |
| --- | --- | --- |
| Context | `GameplayEngine` | Holds a `Strategy`. Calls `direct` once per venture step. Performs the `Directive` after its own checks. |
| Strategy | `Strategy` | The algorithm interface. One method. |
| Concrete strategy | `LevelStrategy` | One gameplay algorithm: pursue the level goal through the command categories. |
| Input | `goal.GoalView` | The goal package's analysis for this step. The strategy does not construct it. |
| Catalog | `CommandCatalog` | Known commands grouped by help-index category. The algorithm's way of naming a verb. |
| Result | `Directive` or nothing | The next command, or a yield so the engine may greet or wait. |

The engine's field is typed as `Strategy`. The venture step calls `self._strategy.direct(view, catalog)`. That call does not mention `LevelStrategy`, a level number, or a clock.

The composition root installs the concrete algorithm when it builds the engine. `goal.kind == "level"` installs `LevelStrategy`. A later goal installs a later class. That branch runs once, at construction. The loop does not grow a branch when a new algorithm arrives. A test installs a fake `Strategy` the same way.

`Strategy.direct` raises `NotImplementedError`. A bare strategy is not a silent wander. Wander is the context's behavior when the field is empty, which is the case when no goal is configured.

The algorithm is pure. It does not send telnet, open a socket, call Ollama, or write memory. The engine sends the line and tells the goal package what the server reported.

## What the algorithm uses the categories for

Bootstrap stores a category on each command it learned from the help index. The headings in the server SUMMARY, stored in lowercase, are:

| Stored category | Commands on that index |
| --- | --- |
| `movement` | `north` `south` `east` `west` `up` `down` `exits` `recall` `sleep` `wake` `rest` `stand` |
| `group` | `follow` `group` `gtell` `split` |
| `objects` | `get` `put` `drop` `give` `sacrifice` `wear` `wield` `hold` `recite` `quaff` `zap` `brandish` `lock` `unlock` `open` `close` `pick` `inventory` `equipment` `look` `compare` `eat` `drink` `fill` `list` `buy` `sell` `value` |
| `information / communication` | `help` `credits` `commands` `areas` `report` `score` `time` `weather` `where` `who` `description` `password` `title` `bug` `idea` `typo` `gossip` `cgossip` `say` `shout` `tell` `yell` `emote` `pose` `note` |
| `combat` | `kill` `flee` `kick` `rescue` `disarm` `backstab` `cast` `wimpy` |
| `other` | `!` `save` `quit` `practice` `train` |

`look` sits in `objects`. `score`, `areas`, `where`, and `who` sit in `information / communication`. `kill` and `flee` sit in `combat`. `rest`, `stand`, and `recall` sit in `movement`. `practice` and `train` sit in `other`. `follow` and `group` sit in `group`.

The engine proposal's mob phase names `kill`, `flee`, and `consider` as bare verbs. This algorithm names a category and a preference list. `CommandCatalog.pick` returns the verb. A character whose index files a command under a different heading follows the stored heading.

Categories are empty when `bootstrap.defer` is true. That is the current `resources/agent.yml`. `pick` still runs. A blank category is filled from the SUMMARY table, and only for a name on that table. A stored category, from either memory or knowledge, wins over the table for that name.

## The catalog

`CommandCatalog` is built each step from the union of session commands and knowledge command records, the same union the engine uses for "known." A non-blank session category wins. A non-blank knowledge category fills a blank session category. The SUMMARY table fills a category that is still blank, and only when the command name is listed in that table.

`pick(category, preference)` returns the first name in `preference` that is known and whose category equals `category`. Comparison is stripped and case-insensitive. A known command filed under a different category is skipped. The algorithm cannot swing `kill` by asking for a movement command, and it cannot move north by asking for a combat command.

Names `pick` never returns: `quit`, `delete`, `murder`, `steal`, `password`, `!`. `!` repeats the last command with no look at the room. `quit` ends the session the engine proposal keeps open on idle.

`consider` is not on the SUMMARY index. The fallback also files it under `information / communication`, because this algorithm uses it as a reading. A stored category still wins. The level algorithm asks for `information / communication` when it wants a reading, and it will not see a `consider` that bootstrap filed under `combat`.

The catalog is part of the strategy package because it is how the algorithm speaks in categories. It is not a progress record and it is not saved.

## Directive

A directive is what `direct` returns.

- `role`. One of `survey`, `travel`, `engage`, `escape`, `hold`, `recover`, `checkpoint`.
- `category`. The heading `pick` used.
- `command`. The verb `pick` returned. Empty when the role is `hold`.
- `argument`. A mobile name, a direction, or empty.
- `allow_social`. When false, the engine skips a greeting on this step. An owed reply has already been sent before `direct` was called.

The line is `command` when `argument` is empty, otherwise `command` and `argument` separated by one space. The engine sends it only when the verb is in `known_commands` and `catalog.category_of(command)` is still the directive's category.

`hold` sends nothing. ROM combat already swings once a fight has started. The algorithm does not stack `kill`.

Returning nothing yields the step. The engine may greet. Every directive this algorithm returns has `allow_social` false. A yield is the step that allows a greeting.

## The view the algorithm reads

`GoalView` is defined in the goal proposal. `LevelStrategy` reads these fields and no clock arithmetic:

- `met`. The goal package has already compared level to the target.
- `notch`. `cautious`, `steady`, or `bold`, after pace and deaths have been applied.
- `pace`. `behind`, `ahead`, `on`, `open`, or `sampling`.
- `score_due`. No score yet, or the goal package says the last score is older than its cadence.
- `areas_known`.
- `fighting`.
- `hit` and `max_hit`. `max_hit` is null until a score supplied it.
- `position`. The last score's position word, or empty.
- `mobiles`. Name, consider outlook or empty, and whether that consider is fresh for this visit to this room.
- `untried_exits`. Directions printed for this room that this process has not taken, in printed order.
- `repop_room`. The engine has seen a kill in this room. The algorithm uses it as a reason to wait. Mobiles that are here now are still judged by the notch.
- `checkpoint_due`. The goal package's save count for this level is still zero.
- `gear_gate`. Empty, or an object level the engine copied from the gear catalog. The gear proposal says which carried piece supplies it, and when a budgeted goal leaves the field empty. This algorithm does not compare the number with the score.

The algorithm does not see `exp_to_level`, the minute budget, or the cooldown. Those have already become `notch`, `pace`, `met`, and `checkpoint_due`. It does not see the gear list. `gear_gate` is already a single level or empty.

## LevelStrategy

`LevelStrategy.direct` returns the first matching directive. The same view and the same catalog return the same directive. Ties break by the order below, then by the mobile name in lowercase.

The notch selects the consider outlooks this algorithm will fight:

| Notch | Outlooks |
| --- | --- |
| `cautious` | `safe` |
| `steady` | `safe`, `even` |
| `bold` | `safe`, `even`, `risky` |

`fatal`, `unknown`, a refusal, and a missing consider are not fights. A missing consider is a survey. Players are never the argument of `kill`.

While fighting, the notch selects an early flee once `max_hit` is known:

- `cautious` when `hit / max_hit` is at or below one half.
- `steady` when `hit / max_hit` is at or below one third.
- `bold` when `hit` is at or below the engine's `play.flee_hp`.

The engine's danger rule remains the floor at `play.flee_hp` and runs before `direct`. This flee is how a cautious notch leaves sooner than that floor. Without `max_hit`, the algorithm does not invent a percentage and does not add its own flee. A flee can cost experience. The algorithm still leaves inside the notch, because the goal package has already treated a death as the larger setback. It does not flee at full health.

`pace` selects exploration. `cautious` takes an untried exit only when `pace` is `behind` and `repop_room` is false. `steady` and `bold` take an untried exit whenever the room has no legal mobile. `sampling` and `on` and `ahead` do not open a new exit at `cautious`. An empty room that has produced a legal kill (`repop_room`) is a place to wait, not a place to wander, when the pace is `ahead`, `on`, `open`, or `sampling`.

1. **Goal met, and no gear gate.** `met` is true and `gear_gate` is empty. Return nothing. The character does not hunt the next level. A set `gear_gate` leaves this rule unmatched. The hunt below keeps the notch, the flee lines, and the consider outlooks already on the view. The gear proposal is what publishes the gate and what clears it.
2. **Score due.** `score_due`. `survey`, category `information / communication`, preference `score`.
3. **Areas missing.** `areas_known` is false and a score exists. `survey`, same category, preference `areas`, then `where`.
4. **Fighting, and the notch wants out.** The early-flee rule above matches. `escape`, category `combat`, preference `flee`.
5. **Fighting, and the opponent is inside the notch.** `hold`.
6. **Fighting, and the opponent is outside the notch.** `escape`, category `combat`, preference `flee`. If `flee` is unknown, `escape` with category `movement` and preference `recall`, then a known untried exit.
7. **Not fighting, and the notch's health line is missed.** `recover`, category `movement`, preference `rest`. The following step, once `hit` is back over the line, is `stand` when `position` is `resting`. The engine proposal already stands when a command is refused for position. This role is the planned rest.
8. **A mobile is inside the notch and has no consider.** `survey`, category `information / communication`, preference `consider`, argument that mobile. Several unread mobiles: the lowest name.
9. **A mobile is inside the notch and the consider is fresh.** `engage`, category `combat`, preference `kill`, argument that mobile. Among legal outlooks, `safe` beats `even` beats `risky`. The same outlook breaks by name.
10. **No legal mobile, and the notch allows an untried exit.** `travel`, category `movement`, argument that exit. The exit must be known in `movement`. Preference follows `untried_exits`.
11. **No legal mobile, and `repop_room` is true, and the pace says wait.** `survey`, category `objects`, preference `look`, when the view says the room record is stale. Otherwise `hold`. `look` is `objects` on the SUMMARY index. The engine's "see the room" rule still covers a room with no session record, before `direct` is called.
12. **No legal mobile and no exit the notch will take.** `travel`, category `movement`, preference `recall`, when `recall` is known. Then `survey`, category `information / communication`, preference `where`. Then nothing.
13. **Checkpoint.** `checkpoint_due` and no rule above returned a hunt. `checkpoint`, category `other`, preference `save`.
14. **Nothing to hunt.** Return nothing.

`practice` and `train` stay under `other` and are not in a preference list. `eat` and `drink` stay under `objects` and are not selected. `follow` and `group` stay under `group`. The engine proposal's company phase is what sends them. This algorithm leaves that category unused so the grind does not drag another player into a fight.

`kick`, `cast`, `backstab`, `disarm`, `rescue`, and `wimpy` are `combat` and are not in the engage preference. Engage is `kill` only. `wimpy` would make the server flee on its own, outside this algorithm.

## Where the context calls it

1. Drain and observe.
2. The goal package records the new lines and rebuilds the `GoalView`.
3. Danger at `play.flee_hp`.
4. Leave an aggressive mobile the engine did not engage.
5. Stand after a position refusal.
6. Answer a pending tell or a say that names us.
7. `strategy.direct(view, catalog)`. Perform the directive when it returns one.
8. When `direct` returns nothing: the engine greeting, under `play.social_every`. When a personality is installed, that greeting is the disposition in `docs/proposals/Personality.md`, and a yield means the disposition declined.
9. Wait.

Rules 3 through 6 stay on the engine. They are not a strategy. The strategy does not call back into the engine.

## Types

| Type | File | Role |
| --- | --- | --- |
| `Strategy` | `src/strategy/Strategy.py` | The algorithm interface. `direct(view, catalog)`. |
| `LevelStrategy` | `src/strategy/LevelStrategy.py` | The level algorithm. Subclass of `Strategy`. |
| `CommandCatalog` | `src/strategy/CommandCatalog.py` | Headings, SUMMARY fallback, `pick`, the refused names. |
| `Directive` | `src/strategy/Directive.py` | The command `direct` returns. |

A class with functions has its own file. No Ollama client is constructed here. `Goal`, `Progress`, and `GoalView` are not in this package.

## Tests

`tests/test_strategy.py` covers the catalog and `tests/test_level_strategy.py` covers `LevelStrategy`. No socket and no model. The test builds a `GoalView` and a catalog. It does not build a clock.

- A catalog with blank categories files `kill` under `combat` and `score` under `information / communication`. A stored category `movement` on `kill` makes `pick("combat", ("kill",))` return nothing.
- `quit`, `password`, and `!` are never picked.
- `score_due` returns `score`.
- A fresh `safe` consider returns `kill` and that mobile. An `even` consider at notch `cautious` does not. The same consider at `steady` does. A `risky` consider engages only at `bold`. `fatal` never engages.
- Two legal mobiles: `safe` is chosen over `even`. Two `safe` mobiles: the lowercase name that sorts first is chosen.
- Fighting at half health on `cautious` returns `flee`. Fighting at full health returns `hold`.
- An untried exit at `steady` with an empty room returns that direction. The same room at `cautious` with pace `on` does not. Pace `behind` at `cautious` does.
- `met` with an empty `gear_gate` returns nothing. `met` with `gear_gate` set returns `kill` for a fresh `safe` mobile, and the notch on the view is the notch the directive uses.
- A hunt directive has `allow_social` false.
- `checkpoint_due` on an otherwise idle view returns `save` once. The next view with `checkpoint_due` false returns nothing.
- `practice`, `train`, `follow`, `cast`, and `wimpy` are absent from every directive.
- A `Strategy` subclass installed on the engine is the object `direct` is called on. `LevelStrategy` is not named by the loop. That assertion lands with the engine tests.

Pace, notch changes, and `note_score` are tests of the goal package, in `tests/test_goal.py`.

## Phases

1. **Catalog.** SUMMARY fallback, `pick`, refused names. No telnet.
2. **Level algorithm.** `LevelStrategy.direct` against a hand-built `GoalView`. Depends on the goal package's `GoalView` type, not on its clock. A test can construct the view with the fields filled in.
3. **Context.** `GameplayEngine` holds a `Strategy`, asks the goal package for a view, and performs one directive. This waits until the engine proposal's phase 1 loop exists. It does not wait for voice prompts or the company phase.
4. **Fight and rooms.** `consider`, `kill`, `hold`, `flee`, untried exits, and `recall`, using the categories above. One fight policy. The engine proposal's phase 4 does not grow a second one.

## Gaps this proposal leaves in place

- The algorithm cannot name the area the character is standing in. Travel is `untried_exits` and `recall`. The goal proposal records why the area list is not a path.
- `bootstrap.defer` true leaves categories blank. The SUMMARY fallback covers the index in the server help topic SUMMARY. A command this server adds, and that bootstrap did not categorize, is invisible until a category is stored.
- A stored category is what `pick` trusts when the live help index differs from the fixture.
- Shop, heal, wear, get, and cast are later concrete strategies, or later preference lists on a later algorithm. The catalog already groups their verbs. Version 1 does not select them.
- `src/goal` has to exist before phase 2 can type `direct` against `GoalView`. Phase 1 does not need it.

## Implementation note

`docs/reference` describes the running code. Add a strategy reference in the phase that makes the package real. Until then this file, with `docs/proposals/Goal.md`, replaces the earlier draft that kept the view and the progress clock inside `src/strategy`.
