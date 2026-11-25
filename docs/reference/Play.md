# Play

While the control mode is `play` and the telnet session is connected, the drive thread repeats one observe-decide-act step. `idle` stops the steps and leaves the session connected. The engine does not send `quit`. A later `play` steps again and does not bootstrap again.

`PlayerControl.drive` still calls `on_play` once, the first time the mode becomes `play`. That call restores commands from world knowledge or runs `Bootstrapper`, the same as before. When `bootstrap.initial` already did that work, the engine from that login is kept and `on_play` does not load knowledge a second time. After `on_play`, `drive` calls `GameplayEngine.step` on that same thread. `bootstrap` still runs on that thread, and that iteration does not step. A step that has started finishes its exchange before the mode change is noticed.

## One step

`step` does four things, then returns the command it sent, or an empty string when it waits.

1. **Observe.** `CommandChannel.drain` reads lines the server has already queued. It answers the same pager and replace-existing gates as `exchange`. A playing prompt is stored on `last_prompt` and left out of the text. Drain sends no gameplay command.
2. **Fold.** A look that contains `Obvious exits:` becomes the current room, its exits, and the mobiles in it. A score page that contains the level line, the hit line, and `You need N exp to level.` updates the play clock. `You are standing.` clears a fight. A line ending in `is here, fighting YOU!` marks a fight this character did not start.
3. **Decide.** The first matching rule below produces at most one command.
4. **Act.** `CommandChannel.exchange` sends that command. The reply is folded before the method returns, so the next step decides from it.

A wait sends nothing. The drive thread pauses `wait_s` after a step that sent nothing, then drains again. Lines that arrive during that pause are included in the next observe.

Disconnect, `PromptTimeout`, and the channel's auth and save failures stop the drive loop. The mode is left as the operator set it.

## What the step may send

The command list is the session commands, then the command records on world knowledge. A verb that is in neither list is not sent. `quit`, `delete`, `murder`, `steal`, `password`, and `!` are not sent even when the list contains them.

The rules, in order:

1. **Danger.** The clock says the character is fighting, the last playing prompt has hit points at or below 20, and `flee` is known. Send `flee`.
2. **Leave a threat.** A mobile is here fighting this character, and this step did not `kill` that mobile. Send an untried exit from the current room. If none is known, send `flee`. If neither is known, wait.
3. **Look.** This process has no current room, `look` is known, and an earlier look did not fail to name a room. Send `look`. A bootstrap that just finished already has the room, so this rule waits. A restore from knowledge looks once. After a direction is sent, the room is no longer current and the next step looks again.
4. **No goal.** `resources/agent.yml` has no `goal` section. Wait. The loop still drains.
5. **Score.** The clock has not folded a score, `score` is known, and an earlier score page did not contain the three lines above. Send `score`.
6. **Level question.** Ask Knowledge Machine, then send the first licensed attempt whose verb is known. While the character is fighting, `kill`, a direction, and `recall` are not sent. The library does not yet identify the opponent, so those hunt results wait instead of starting another attack or leaving the room by a hunt rule.

`goal` is optional:

```yaml
goal:
  kind: level
  level: 5
  risk: cautious
  minutes: 0
```

`kind` must be `level`. `level` is an integer of 1 or more. `risk` is `cautious`, `steady`, or `bold`, and it defaults to `steady`. `minutes` of 0, the default, is an open budget. A present section without `level` raises `ValueError`. Without the section, no level question is asked.

The play clock lives on the engine for this process. It keeps the level, the experience still to level, the span from the first score on that level, the hours from the score line, the notch, the cooldown, the save count, and the steps since the last score. It is not written to working memory or world knowledge. Elapsed minutes are the difference in score-page hours times 60. A fraction inside the level is not parsed. The span is 0 until the first score on that level.

A consider is fresh only after this visit's `consider` reply estimated the mobile. A stale consider is given to the question with no outlook, so the library surveys it again. Players are not put on that list. A notch stored from an earlier question is clamped to the current `goal.risk` before the question is built.

`som-flee-floor` on the question is 20. That is the same threshold as the danger rule.

## Knowledge Machine

KM is reached through som-nlp-service, the same origin as `ollama.base_url`. `KmClient` is the bridge.

| Method | Route | What it does |
| --- | --- | --- |
| `query` | `POST /km/query` | One expression. A successful result stays on the service session. |
| `assert_expression` | `POST /km/assertions` | One expression. A successful fact stays on the service session. |
| `baseline` | `POST /km/baseline` | One question, a list of expressions. The service starts from the library it loaded at startup and drops the derived frames. |
| `query_player` | `POST /km/players/{player}/query` | Query one retained player situation. |
| `assert_player` | `POST /km/players/{player}/assertions` | Assert into one retained player situation. |

Every `run_agent` startup checks the agent's KM situation before loading saved connections, opening the control listener, or logging into the game. This also runs when the agent starts idle, with no goal or initial game bootstrap. Listing agents does not call KM.

`KmPlayer` names the instance `Player-{accountName}-{characterName}`, preserving case; for example, `Player-sneibarg-Janky`. Within either component, each UTF-8 byte other than an ASCII letter or digit is encoded as `_xx` in lowercase hexadecimal. This keeps names valid for the player routes and prevents different account/character pairs from sharing a situation.

Startup queries `(in-situation *Global (the instance-of of *Player-sneibarg-Janky))`. An existing `Som-Agentic-Player` is reused. A missing instance is asserted in `*Global`, then queried again to confirm creation. A failed request, failed reasoning result, incompatible existing instance, or unconfirmed creation stops startup with exit status 1. No situation is cleared or replaced. `KmPlayer.query` and `assert_expression` use the player routes so later expressions can access that situation's retained assertions. Gameplay level questions continue to use the separate baseline flow.

Assertions survive agent runtime restarts while the same NLP service process is running. The service currently stores player situations in memory and loses runtime assertions on its own restart. Startup recreates a missing player; it cannot recover assertions lost by the service. Durable service persistence is a companion-service gap.

The body for `baseline` is `{"expressions": ["...", "..."]}`. A successful body is `{"ok": true, "results": [...]}`. Each result has `answer` in KM's printed syntax. An empty answer is `nil`. A blank expression is not sent. HTTP 400 and 501 raise `KmError` with the service's `error` string.

The level question is the caller-owned clock, not the service session. `*Goal`, `*Clock`, and `*View` are built for this step only. The last four expressions read `som-notch`, `som-cooldown-next`, `som-licensed-rule`, and `som-attempts` of the licensed directive. An attempt is `(:args role category verb argument)`. Several attempts are one `:seq`. The first executable verb is the command. A hold, rule 1, rule 14, or a stale clock has no attempts, and the step waits.

`km.base_url` overrides the origin. It defaults to `ollama.base_url`. The paths default to `/km/query`, `/km/assertions`, and `/km/baseline`. `resources/agent.yml` does not need a `km` section.

`km.players_path` overrides `/km/players` for the player-scoped methods.

`/km/query` and `/km/assertions` are not used by the step. They remain for a caller that wants the retained session. The step uses `baseline` so one clock is not still present when the next question runs.

## What this iteration does not do

- It does not greet, reply, follow, or group.
- It does not practice, wear, or cast.
- It does not send `who`.
- It does not save memory or knowledge on each step. The process still saves memory when it exits.
- It does not treat a death as a KM `death` event. A score that says `You are standing.` clears the fight flag. A `flee` this step sent also clears it.
- It does not path to a room. An exit is one untried direction from the current look.
- A server refusal of a known command can be chosen again on a later step, except a look or a score that produced no usable page, which is not sent again this process.
- `bootstrap.defer` is unchanged. The step does not call Ollama.
