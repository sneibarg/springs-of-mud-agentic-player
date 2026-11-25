# Springs of MUD component library review

Date: 2026-11-25

## Assessment

The component library is a useful foundation for adaptive leveling, but it does not yet reliably enable intentional, dynamic gameplay. Several decision rules can stall play, violate a configured risk ceiling, or disagree with the player architecture. The player runtime also lacks the recurring decision loop and KM integration needed to turn the library into gameplay.

Intentional play requires a goal to influence action selection, observations to establish whether an action worked, and the next decision to respond to that outcome. This library implements part of the goal analysis and hunt policy. It does not yet establish that complete feedback cycle.

## Scope and sources

The review compared the nine KM components under `E:/IdeaProjects/som-knowledge-machine/src/resources/som-component-library` with this repository's [Architecture Map](../reference/Architecture.md), [Working Memory](../reference/WorkingMemory.md), and the proposals for [GameplayEngine](../proposals/GameplayEngine.md), [Goal](../proposals/Goal.md), [Strategy](../proposals/Strategy.md), [Memory](../proposals/Memory.md), [Personality](../proposals/Personality.md), [Practice](../proposals/Practice.md), and [Gear](../proposals/Gear.md).

The player repository reviewed was `C:/Users/scott/PycharmProjects/springs-of-mud-agentic-player`. The active KM workspace at `C:/Users/scott/OneDrive/Documents/ChatGPT/som-knowledge-machine` referenced the library but did not contain that directory. The library reviewed was the copy in the E: checkout. Runtime references describe implemented behavior; proposal documents describe intended behavior.

KM source references below use paths relative to the root of that E: checkout, with line numbers from the reviewed files. This is a review of the local snapshots, not a claim about every checkout or a published artifact.

## Findings

### P1 Combat can fall through into another attack or travel

`src/resources/som-component-library/Som-Level-Directive.km:131` selects the first hunt rule, but explicitly omits strategy rules 5 and 6: hold against an acceptable opponent, or escape an unacceptable one. Later survey, engage, and travel rules remain eligible while fighting.

A probe with `fighting=t`, full health, and a fresh safe goblin returned rule 9, `kill goblin`. Without a mobile reading, a combat view can instead yield, allowing later strategies to run. This conflicts with the strategy proposal's combat hold behavior and can produce repeated attacks, inappropriate movement, or unrelated work during combat.

Implement opponent identification and explicit combat hold/escape branches before general hunting. Until opponent identity is available, define a conservative combat outcome rather than allowing ordinary hunt rules to proceed. Preserve the engine's preceding emergency danger rule.

### P1 Restored progress can exceed the configured risk ceiling

`Som-Goal-View.km:91` checks clock compatibility using kind and target. The notch rules at `Som-Goal-View.km:264` can preserve the prior notch without constraining it to the current ceiling.

Restoring a bold notch with the same target and a newly configured cautious ceiling preserved bold in a probe. The library then licensed attacking a risky mobile. The operator's changed risk setting therefore did not govern the decision.

Clamp the prior notch to the current ceiling before evaluating any directive. Keep compatible progress while enforcing current configuration. Cover a restart with a changed ceiling in an integration test.

### P1 Stale consider readings have no refresh path

`Som-Level-Directive.km:81` surveys readings only when the outlook is absent. Engage selection at line 88 requires a fresh outlook. A stale safe reading satisfies neither condition.

A probe with a stale safe goblin and no exits returned rule 14, yielding instead of considering the goblin again. An otherwise suitable opponent can remain unusable indefinitely.

Survey relevant stale readings as well as missing readings. The observer must invalidate freshness after leaving a room or observing material changes, and a successful consider must refresh it for the current visit.

### P1 The player runtime does not consume the decisions

[src/control/PlayerControl.py](../../src/control/PlayerControl.py), around line 86, calls `on_play` once and then waits. [src/main.py](../../src/main.py), around line 122, restores knowledge or bootstraps and returns. There is no recurring observe-decide-act loop or KM bridge in the reviewed runtime.

The component library assumes that the caller has already applied safety rules, built projections, selected catalog commands, maintained counters, and persisted progress. Those assumptions are not yet fulfilled by this runtime. This is an integration gap rather than a reason to move sockets, observation, or persistence into KM.

Implement the GameplayEngine loop on the drive thread. Project one decision from current observations, evaluate it against a caller-owned library baseline, translate its result through the command catalog, execute at most one command, and observe the response before deciding again. Keep idle and disconnect behavior consistent with the runtime architecture.

### P2 Target selection does not implement the documented preferences

`Som-Level-Directive.km:88` selects the first eligible reading in caller order. The strategy proposal specifies safe before even before risky, followed by lowercase name. A probe that placed a risky opponent before a safe opponent selected the risky one.

Survey selection also includes unread players. A player placed before a fresh safe goblin caused rule 8 to consider the player. The player is excluded from attack selection, but can still consume hunt survey steps.

Establish one owner for filtering and ranking readings. Either encode the policy in KM or define and test the caller's ordering contract. Do not leave tactical preference dependent on incidental observation order. Resolve whether player consideration belongs in the level strategy at all.

### P2 Dead ends do not trigger the proposed travel fallback

`Som-Level-Directive.km:185` requires a nonempty untried exit sequence for rule 12. An empty room with no untried exits, no checkpoint due, and no legal mobile returned rule 14 rather than attempting recall or where.

The strategy proposal's rule 12 applies when no legal mobile and no exit the notch will take remain. The implementation can strand the agent at an exhausted room.

Make the fallback depend on the absence of an executable productive action. Preserve any deliberate checkpoint opportunity, then permit recall or where when exploration is exhausted. Test both no exits and exits rejected by the notch.

### P2 Death and deadline semantics need reconciliation

`Som-Goal-View.km:237` sends a bold notch directly to cautious on death. The Goal proposal's prose specifies a one-step drop, while its own test examples conflict with that prose. This disagreement needs an explicit decision rather than treating either description as unambiguous.

The deadline rules at `Som-Goal-View.km:249` and line 264 also override the death cooldown. A probe with an expired deadline, cautious prior notch, and 30 cooldown steps returned bold. A death can therefore reduce risk only until the next view, despite the stated recovery period.

Define a single transition table for death, deadline escalation, score events, and ordinary views. State whether cooldown or deadline escalation wins. Apply that decision consistently to the proposal, component rules, caller persistence, and tests.

## Architectural strengths

Caller-owned state, immutable projections, separate progress analysis and action selection, and catalog-controlled commands are sound boundaries. Starting each decision from the loaded library baseline avoids accidental reuse of a previous query's derived facts. The implementation should preserve that property while keeping durable progress in working memory.

The narrow level strategy is also a reasonable component boundary. Practice, equipment, personality, and relationships belong to the separate strategies and disposition described in the proposals. Their absence from this library is a scope limitation, not inherently a defect. They still need a working composition path before the overall agent can express those intentions.

## Requirements for dynamic gameplay

The next implementation should complete one feedback cycle:

1. Drain and observe server events, including events received while waiting.
2. Build a current situation and project the active goal and progress.
3. Apply the engine's emergency and reply priorities, then evaluate the installed strategies.
4. Resolve a directive against the actual command catalog and send at most one command.
5. Observe success, refusal, changed state, and progress before selecting the next action.

Define attempt sequences as ordered alternatives, if that is their intended meaning, and stop after the first executable command. A sequence must not accidentally become several commands in one step. An unavailable command or repeated refusal must not monopolize every later decision.

Preserve distinct outcomes for hold, yield, blocked, and goal complete. An empty result alone does not explain whether the agent intends to wait, has finished, lacks evidence, or cannot execute its chosen action. The integration should retain a reason, the goal it serves, the relevant evidence, and the observation that will allow reconsideration. Existing KM explanation facilities can contribute to this without creating a second implementation of the policy.

Prioritize combat control, current risk limits, stale observation refresh, and the recurring loop before adding more gameplay verbs. Then connect the level strategy to practice, gear, and personality using the composition rules already proposed. These steps make the agent responsive to outcomes rather than merely able to emit a command.

## Validation

The focused suite passed: **21 tests, 663 assertions, zero failures and zero errors**. It ran through a direct JDK invocation against the active workspace evaluator, with the test's library path redirected in memory to the E: checkout. This was a focused suite run, not a successful run of the full `clojure -M:test` command.

Nine additional evaluator probes produced these results:

| Scenario | Observed result |
| --- | --- |
| Fighting at full health with a fresh safe opponent | Rule 9, kill the opponent |
| Stale safe consider reading, no exits | Rule 14, yield |
| Steady notch, repop room, open pace, untried north exit | Rule 10, travel north |
| Restored bold notch, current cautious ceiling, risky opponent | Bold retained; rule 9, kill |
| Death from bold | Cautious; cooldown 30 |
| View after deadline and death, cooldown still 30 | Bold restored |
| Unread player before a fresh safe goblin | Rule 8, consider the player |
| Risky opponent before safe opponent at bold | Rule 9, attack the risky opponent |
| No legal mobile, empty exit sequence, checkpoint not due | Rule 14, yield |

The repop probe also exposes a policy ambiguity: the strategy prose describes waiting in a productive room, while its numbered order can permit travel before that hold. Resolve the intended precedence before treating this as a separate implementation defect.

Passing tests establish the current component behavior, including some disputed choices. They do not establish successful autonomous gameplay. Acceptance should include multi-step scenarios covering combat hold and escape, stale observation refresh, unavailable commands, movement refusal, death cooldown, goal completion, restart with changed risk, and response to new events while holding.

No gameplay implementation, component source, tests, or configuration was changed by the review.
