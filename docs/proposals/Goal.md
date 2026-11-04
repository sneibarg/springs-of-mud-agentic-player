# Goal

Proposal for a `src/goal` package. The package defines the goal and analyzes progress toward it. A strategy reads that analysis. It does not own the clock. This document does not change the runtime.

The algorithm proposal is `docs/proposals/Strategy.md`. `LevelStrategy.direct` receives a `GoalView` from this package. The engine proposal is `docs/proposals/GameplayEngine.md`. The engine records server lines here, then asks the strategy what to do.

## Role

Three types, and no command choice.

| Type | Job |
| --- | --- |
| `Goal` | What was asked for. Target level, risk ceiling, time budget. Loaded from config. |
| `Progress` | What has happened. Scores, deaths, the notch, the save count. Saved with working memory. |
| `GoalView` | The analysis for one step. Built from the goal, the progress, and the facts the engine gathered. This is the object `Strategy.direct` reads. |

The package does not send telnet, open a socket, call Ollama, or pick a verb. `note_score` parses two server lines locally. `play.defer` can stay true.

A death is part of the analysis because it is a time event. The server help topic DEATH says the character loses experience equal to two-thirds of the way back to the start of the current level, and wakes at the temple altar. `Fight.do_flee` applies `-10` experience except when a thief is told they snuck away. This package does not reimplement either number. The next score shows the loss. Until that score, a death still drops the notch, because waiting for the score before becoming careful gives the lost time back to the bold notch.

## Config

`resources/agent.yml` gains an optional `goal` section. Absent, the engine installs no strategy and keeps the wander described in the engine proposal.

```yaml
goal:
  kind: level
  level: 5
  risk: steady
  minutes: 0
```

`AgentConfig` reads it the way it reads `bootstrap`. The values are handed to `Goal`. They are not a strategy setting. The concrete `Strategy` is chosen from `kind` at construction, as the strategy proposal describes.

- `kind` defaults to `level` when the section exists. Any other string raises `ValueError("goal.kind must be level")`. A later goal adds a value here.
- `level` is required for `level`. It is an integer of at least 1. Otherwise `ValueError("goal.level must be an integer level")`.
- `risk` is the ceiling: `cautious`, `steady`, or `bold`. Default `steady`. Anything else raises `ValueError("goal.risk must be cautious, steady, or bold")`.
- `minutes` is the budget. `0` or omitted means open-ended. A negative or a non-integer raises `ValueError("goal.minutes must be a whole number of minutes")`.

One process runs one agent, so one goal matches that process. Agent documents have no goal field. A per-agent goal is a field those documents do not carry yet. That is a gap to report, not a change to som-server-modulith.

## Goal

`Goal` is the loaded section. Fields: `kind`, `level`, `risk`, `minutes`. It validates them in one place, so `AgentConfig` stores the section and `Goal.from_section` raises the errors above. The composition root builds one `Goal` and one `Progress` for the engine. The strategy is not built by `Goal`. That would make this package choose an algorithm.

## Progress

`Progress` is the clock. It is stored on `WorkingMemory` under `goal`, saved and restored with the agent-memory document, and shown by the control `memory` review. The engine proposal's other session sections stay as they are. This block is the goal's memory, not a transcript. The knowledge document does not gain a goal section. A progress change is a memory save.

Fields:

- `kind` and `level`. The goal that started this clock. A load whose kind or target differs from the current `Goal` starts a fresh clock.
- `started_at`. UTC timestamp of the first score.
- `start_level` and `start_fraction`. Level and fraction on that score.
- `level` and `exp_to_level`. The latest score.
- `exp_span`. The `exp to level` figure from the first score on the current level. The next score after a level gain replaces it.
- `max_hit`. From the latest score, when that page printed it.
- `position`. The position word from the latest score, or empty.
- `hungry` and `thirsty`. Recorded for a later algorithm. Version 1's level strategy does not eat or drink.
- `deaths`.
- `notch`. Starts at `cautious` and never rises past `Goal.risk`.
- `cooldown_steps`. Steps remaining after a death, during which the notch cannot rise.
- `saves`. How many checkpoints this level has recorded. The view's `checkpoint_due` is `saves == 0`.
- `met`. True once a score shows the target level or higher.
- `score_steps`. Steps since the last score. The engine increments this once per step.
- `deadline_missed`. True once, when a budget runs out unmet. The engine logs that once.

`note_score(lines)` parses locally. The two lines are the ones `Info.do_score` prints and the score prompt already documents:

- `You are <name> <title>, level <level>, <ageYears> years old (<hoursPlayed> hours).`
- `You need <expToLevel> exp to level.`

Hunger and thirst follow the score prompt's sentences: `You are hungry.` and `You are thirsty.` Absent, the flags are false. Hit points and `maxHit` are the score sentence `You have <hit>/<maxHit> hit, ...` when it is present. A page that does not contain the level line and the exp line leaves the previous score in place.

Between scores, a pinned line `You receive <n> experience points.` may reduce the in-memory `exp_to_level` by `n`. The next score overwrites that estimate. The line is the one `CombatHandler` appends. A test fixture pins it.

Fraction through the level is `1 - exp_to_level / exp_span` when `exp_span` is positive. Levels earned since the clock started are `(current_level - start_level) + current_fraction - start_fraction`. A death moves `exp_to_level` back up. The next score lowers levels-earned. The fraction is the time cost. The two-thirds rule is not copied into this math.

`note_death` adds one death, drops the notch one step (`bold` to `steady`, `steady` to `cautious`), and sets `cooldown_steps` to 30. The engine calls it when the observer sees the character die and return. The death lines are pinned in a fixture during implementation, the same way the engine proposal pins flee lines before it sends `flee`.

`note_checkpoint` adds one to `saves`. The engine calls it after a `save` directive is performed. A level change in `note_score` sets `saves` back to 0.

`tick` adds one to `score_steps` and, while `cooldown_steps` is positive, subtracts one from it. The engine calls `tick` once per step, including a step that only waits.

## Analysis

`GoalView` is built by `Progress.view(goal, world)`, where `world` is the room, the mobiles, the exits, and the areas the engine already holds. The strategy receives the view and does not call `view` itself.

Pace is one of five words:

| Pace | When |
| --- | --- |
| `sampling` | A deadline is set and the sample is not ready. The sample is two minutes of clock time and two scores. |
| `open` | `minutes` is 0. There is no rate to compare. |
| `behind` | The sample is ready and `actual < needed * 0.8`. |
| `ahead` | The sample is ready and `actual > needed * 1.2`. |
| `on` | The sample is ready and the rate sits in that band. |

```
remaining_levels = target_level - current_level_as_fraction
remaining_minutes = budget_minutes - elapsed_minutes
needed = remaining_levels / remaining_minutes
actual = levels_earned / elapsed_minutes
```

`remaining_levels` uses the fractional level. When `remaining_minutes` is at or below zero and the goal is unmet, `deadline_missed` becomes true and the notch is raised to the ceiling if it is lower. It stops there. The character keeps playing.

Notch movement, applied inside `note_score` and `note_death`, not inside the strategy:

- Open-ended play (`pace` would be `open`) raises the notch to the ceiling once, at the first score. It does not move again for pace. A death still drops it, and it stays dropped. There is no pace rule to raise it back.
- A deadline starts at `cautious` and does not take that first-score raise.
- When the new pace is `behind` and `cooldown_steps` is 0, the notch rises one step, if the ceiling allows.
- When the new pace is `ahead`, the notch drops one step, if it is above `cautious`.
- One raise or one drop per score. A single fight does not walk `cautious` to `bold`.

`score_due` on the view is true when no score has been recorded, or when `score_steps` is at least `goal.score_every`. That cadence defaults to 15 and is also forced true by the engine when a fight ends, through `Progress.mark_score_due`. The field is an integer on the `goal` section. A non-integer raises `ValueError("goal.score_every must be a positive integer")`.

The view's world fields are copied, not interpreted into a command:

- `areas_known`. At least one `AreaRecord` is stored.
- `fighting`, `hit`, `max_hit`, `position`.
- `mobiles`. Name, outlook, fresh. Fresh means the consider was taken in this room during this visit. The engine passes that flag. This package does not parse `consider`.
- `untried_exits`. The engine's process-local table, in printed order.
- `repop_room`. The engine has seen a kill in this room. This package does not decide that the kill was legal.
- `room_stale`. The engine says the session room record needs another look.
- `gear_gate`. Empty, or a level the engine copied from the gear catalog before `view` returns. Pace, `met`, and the notch ignore it. This package does not read gear pieces. The gear proposal says when the engine leaves the field empty.

`met`, `notch`, `pace`, `score_due`, `checkpoint_due`, `hit`, and `max_hit` are the analysis. The world fields and `gear_gate` are on the same object so `direct` has one argument besides the catalog. They are still built here, because the strategy proposal does not define a view type of its own.

## Types

| Type | File | Role |
| --- | --- | --- |
| `Goal` | `src/goal/Goal.py` | Kind, target, ceiling, budget, score cadence. |
| `Progress` | `src/goal/Progress.py` | Clock, `note_score`, `note_death`, `note_checkpoint`, `tick`, `view`. |
| `GoalView` | `src/goal/GoalView.py` | The frozen analysis for one `direct` call. |

A class with functions has its own file. `WorkingMemory` gains the `goal` section in `to_review`, `to_collection`, and `from_collection`. A blank or missing section restores an empty progress. The strategy package is not imported from here.

## Tests

`tests/test_goal.py`. No socket and no model.

- A non-integer level, an unknown risk, and a negative minute budget each raise the error named above.
- The first score at level 1 with `You need 1000 exp to level.` sets `exp_span` to 1000 and fraction 0. A later score of 400 exp to level sets fraction 0.6.
- Target 5, now level 5, sets `met`.
- Target 5, level 1, fraction 0, budget 10 minutes, elapsed 5, no levels earned, two scores: pace is `behind`, ceiling `bold`, cooldown 0. The notch becomes `steady` and stops there for that score. The next behind score raises it to `bold`.
- A death then sets the notch to `cautious` and `cooldown_steps` to 30. A further behind score during the cooldown does not raise it.
- Pace `ahead` lowers the notch one step.
- `minutes` 0 and ceiling `steady` raises the notch to `steady` at the first score and does not raise it for a later score.
- `You receive 100 experience points.` lowers `exp_to_level` by 100. The next score replaces that figure.
- A restored document with a different target level starts a fresh clock.
- `view` sets `score_due` after 15 ticks, and `checkpoint_due` while `saves` is 0.

The level algorithm's command choices are `tests/test_level_strategy.py`, against a view this package's tests already know how to build.

## Phases

1. **Goal and progress.** Config, `note_score`, pace, notch, death cooldown, `GoalView`. No telnet. This phase does not wait for the engine.
2. **Memory.** The `goal` section round-trips through `to_collection` and `from_collection`.
3. **Engine recording.** The engine calls `note_score`, `note_death`, `tick`, and `view` around `strategy.direct`. This waits until the engine proposal's phase 1 loop exists.

## Gaps this proposal leaves in place

- The character's area name is not on a mortal prompt, and `where` lists people. `AreaRecord.level_range` is stored, including values such as `1-5`. Version 1 does not turn that list into a destination. The view's `areas_known` only says the list has been read.
- `exp_span` comes from the first score on a level. A score taken in the middle of a level stores the remaining experience as that span, so finishing the level counts as a whole level earned. Pace overstates progress and delays a raise. The next level's first score replaces the span.
- The two-thirds death penalty and the flee penalty appear in the next score. They are not a second formula here.
- The agent document still has no goal. Until it does, two agents need two configs, or they share the goal in `agent.yml`.

## Implementation note

`docs/reference` describes the running code. Add a goal reference in the phase that makes the package real. Until then this file is the description of the types the strategy proposal used to keep in `src/strategy`.
