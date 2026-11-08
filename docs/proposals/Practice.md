# Practice

Proposal for choosing which skill or spell the character practices first, and which one it buys with a training session. This document does not change the runtime.

A percent on a skill changes the hits `LevelStrategy` already starts. A spell changes a fight only when some command casts it. The level algorithm's engage preference is `kill`. This proposal does not add a cast. The choice splits in two. `optimal` spends a session on the next ability that changes those hits. `preference` spends a session on the next name the operator listed. One style does not finish the other's list.

The other proposals stay in force. `docs/proposals/Strategy.md` still owns `direct` and `CommandCatalog`. `LevelStrategy.direct` stays `(view, command_catalog)`. Its tests that `practice`, `train`, and `cast` are absent from every level directive stay true. `docs/proposals/Goal.md` still owns the level clock. `GoalView` does not gain a skill field. `docs/proposals/Gear.md` still sends bare `practice` once, and it still never sends `practice <skill>`. This proposal is the session that does. `docs/proposals/Memory.md` still keeps new facts off the character knowledge document. Parsers live in `src/play`. The algorithm lives in `src/strategy`. Memory stores the rows and does not choose one.

## Two verbs, and a third this proposal leaves alone

`practice <skill>` spends one practice session on a name already printed by bare `practice`. `gain <name>` spends training sessions to put a skill, or a whole group, on that list at 1%. `train` spends a training session on an attribute. Help TRAIN says to train wisdom and constitution to 18 before practicing anything else. That is the attribute command. This proposal does not send `train`, `gain convert`, or `gain points`.

Bare `practice` does not spend a session and does not need a trainer. `Info.do_practice` prints each visible learned name in an 18-column field, three spaces, the percent in three columns, and `%`, three names to a line, then `You have <n> practice sessions left.` The command position is `POS_SLEEPING`, so the listing works while resting. `Character.visible_learned_entries` skips a learned level below 1, and `Ability.practice_visible` skips a name until the character's level reaches that class's level. A skill the class learns at a later level is absent from the listing until then. The percent on that listing is the number this proposal stores. The `skills` command prints a percent for a skill and `n/a` below the required level. The `spells` command prints mana, not a percent. This proposal does not send `skills` or `spells`.

`practice <skill>` uses the guards on the practice command, in order. Asleep: `In your dreams, or what?` No sessions: `You have no practice sessions left.` No practice trainer in the room: `You can't do that here.` The name is not visible, or its class rating is not positive: `You can't practice that.` Learned already at adept: `You are already learned at %s.` A session that stays under adept replies `You practice %s.` A session that reaches adept replies `You are now learned at %s.` The room sees `%c practices %s.` or `%c is now learned at %s.` The lookup is a prefix match (`Character.get_learned(..., prefix=True)`). The argument this proposal sends is the full name from the listing, including the space in `hand to hand` and `shield block`. A shorter prefix can hit a different name.

The adept those replies mean is `LearningService.practice_adept`: the class `skill_adept`, or 75 when that value is missing or not positive. Mage, cleric, thief, and warrior in `SOMDB.GameData.json` each have `skill_adept` 75. Help PRACTICE says the maximum is between 80% and 100%. The code is 75, and the success path assigns that adept rather than a number above it. The reply does not print the new percent. When the stored class is `mage`, `cleric`, `thief`, or `warrior`, `You are now learned at <name>.` stores 75. Any other class stores the name as finished and does not invent a percent.

`Ability.practice_gain` is `max(1, intelligence learn-bonus // rating)` with rating at least 1. A higher rating rises fewer points in one session. This proposal does not recompute that division and does not read the intelligence bonus table. The next bare listing is the new percent. `You practice <name>.` marks the listing stale. It does not add a guessed delta.

Use can raise a skill from the practiced adept up to 100. `LearningService.check_improve` queues `You have become better at <name>!` when a successful use improves it, and `You learn from your mistakes, and your <name> skill improves.` when a failed use improves it. The second sentence adds a random 1 to 3. Neither sentence prints the new percent. Both mark the listing stale. This proposal does not spend a session to chase either sentence.

A level-up prints `You raise a level!!` and `You gain <hp> hit point(s), <mana> mana, <move> move, and <practices> practice(s).` That sentence does not mention training sessions. `CharacterAdvancement.advance_level` adds the wisdom practice bonus and adds one train in the same function. This proposal does not recompute the wisdom table and does not parse the level-up sentence as a counter. The practice footer remains `GearProgress.practices_left`. The score line `You have <practices> practices and <trains> training sessions.` is the trains source. A later footer replaces `practices_left`. A later score line replaces trains. One does not overwrite the other.

## What a stored percent changes

For a player, `CombatHandler._weapon_skill_total` uses the learned percent of the weapon's skill. An empty hand and an exotic weapon use `hand to hand`. The total is 20 plus that percent, and the percent is capped at 100 before the 20 is added. Weapon damage is the weapon dice times that total, divided by 100. An empty hand uses the same total inside the unarmed range. The NPC formula `40 + 5 * level // 2` in `SkillApi.get_rating` is the mobile's rating. It is not the player's learned percent. Practicing the skill the current swing uses is the spend that changes the experience the level goal is hunting.

These checks also read the learned percent, with no extra command from the level algorithm:

| Check | When it applies |
| --- | --- |
| `shield block` | The defender is awake and a shield is worn. |
| `parry` | A player with an empty wielded slot does not parry. A worn weapon uses the parry percent. |
| `dodge` | The defender is awake. |
| `enhanced damage` | A roll against the percent adds damage on a hit that is already landing. |
| `second attack` | The percent divided by 2 is the chance of another hit. |
| `third attack` | The percent divided by 4 is the chance of a hit after that. |

`recall` from combat fails when `random.randint(1, 100) < 80 * SkillApi.get_rating(...) // 100`. For a player that rating is the learned percent. At 1% the threshold is 0 and the check does not fail. At 75% the threshold is 60. The failure line is `You failed!.` Help RECALL says the chance depends on the skill and that 100% does not insure success. Raising the percent makes this comparison fail more often. Optimal does not practice `recall`. A preference list may name it.

`backstab`, `bash`, `kick`, `disarm`, `rescue`, `trip`, `hide`, `sneak`, `peek`, `steal`, and `pick lock` are real skills. `LevelStrategy` does not send them. Gear casts `identify` and `enchant weapon` or `enchant armor`, and this proposal does not spend a practice to raise those spells. A later strategy that casts a damage spell would be the place that adds that spell. This one does not.

Help WEAPONS says parry is best when the character is skilled at both weapons. The parry check uses the parry percent. This proposal follows the check.

## Who the character is

Score prints `Race: <race>  Sex: <sex>  Class: <class>` with the class's full name. That word is stored as the class. `mage`, `cleric`, `thief`, and `warrior` are the four curricula. Any other word is no class. A later score replaces it.

`InfoUtil.who_line` prints the class as the first three letters, capitalized, unless the level is an immortal rank (`IMP`, `CRE`, `SUP`, `DEI`, `GOD`, `IMM`, `DEM`, `ANG`, `AVA`). `WorldReader` stores that token on `PlayerRecord.character_class` for the row with `self_character`. `Mag`, `Cle`, `Thi`, and `War` map to mage, cleric, thief, and warrior. The who token fills the class only while score has not stored one. It does not replace a score class.

With no class, optimal still practices a wielded weapon's skill and the passives that are already on the listing. It does not guess a class weapon, and it does not buy a skill whose level filter needs the class. Preference does not need the class to spend a name that is already on the listing.

The class record names a school weapon: mage and thief `OBJ_VNUM_SCHOOL_DAGGER`, cleric `OBJ_VNUM_SCHOOL_MACE`, warrior `OBJ_VNUM_SCHOOL_SWORD`. This proposal uses that only as the skill name `dagger`, `mace`, or `sword`. It does not look up the object, and it does not assume the character is holding one. Help GROUPS says the skills chosen at creation are the only skills the character will ever learn. The gain command adds skills later and its help says gained skills do not increase creation points. No creation path that applies `rom basics`, the class basics group, or the class default group was found. The practice listing is the evidence of what this character already has. A new character is not assumed to know `dagger`.

## What each class can buy

Ratings on a group are stored as mage, cleric, thief, warrior. `GenericUtil.to_int` keeps a stored `-1` (`int("-1")` is `-1`). `Movement._group_rating` uses that value. A cost that is not positive returns `That group is beyond your powers.` A rating of 0 and a rating of -1 both fail that check. The gain list already omits a group the character knows and a group whose rating is not positive, so those groups never appear as a row to buy. The same rule omits an individual skill whose `ratingByClass` is not positive. A spell cannot be gained by itself. The reply is `You must learn the full group.`

Group ratings below are the curriculum. The agent buys a row only when `gain list` printed it, at the cost that line printed. The table answers whether a printed group name contains the skill the algorithm is missing. A group contains a name when its skill list or its spell list names it, or names a nested group that contains it. That is the same expansion `Movement._add_group` performs. If the printed list and this table disagree, the printed list is the offer. A group this table does not know is not treated as containing the missing name.

| Group | Rating mage, cleric, thief, warrior | Members |
| --- | --- | --- |
| `rom basics` | 0, 0, 0, 0 | skills `scrolls`, `staves`, `wands`, `recall` |
| `mage basics` | 0, -1, -1, -1 | skill `dagger` |
| `cleric basics` | -1, 0, -1, -1 | skill `mace` |
| `thief basics` | -1, -1, 0, -1 | skills `dagger`, `steal` |
| `warrior basics` | -1, -1, -1, 0 | skills `sword`, `second attack` |
| `mage default` | 40, -1, -1, -1 | skill `lore`; nested `beguiling`, `combat`, `detection`, `enhancement`, `illusion`, `maladictions`, `protective`, `transportation`, `weather` |
| `cleric default` | -1, 40, -1, -1 | skills `flail`, `shield block`; nested `attack`, `creation`, `curative`, `benedictions`, `detection`, `healing`, `maladictions`, `protective`, `transportation`, `weather` |
| `thief default` | -1, -1, 40, -1 | skills `mace`, `sword`, `backstab`, `disarm`, `dodge`, `second attack`, `trip`, `hide`, `peek`, `pick lock`, `sneak` |
| `warrior default` | -1, -1, -1, 40 | nested `weaponsmaster`; skills `shield block`, `bash`, `disarm`, `enhanced damage`, `parry`, `rescue`, `third attack` |
| `weaponsmaster` | 40, 40, 40, 20 | skills `axe`, `dagger`, `flail`, `mace`, `polearm`, `spear`, `sword`, `whip` |
| `attack` | -1, 5, -1, 8 | spells `demonfire`, `dispel evil`, `dispel good`, `earthquake`, `flamestrike`, `heat metal`, `ray of truth` |
| `beguiling` | 4, -1, 6, -1 | spells `calm`, `charm person`, `sleep` |
| `benedictions` | -1, 4, -1, 8 | spells `bless`, `calm`, `frenzy`, `holy word`, `remove curse` |
| `combat` | 6, -1, 10, 9 | spells `acid blast`, `burning hands`, `chain lightning`, `chill touch`, `colour spray`, `fireball`, `lightning bolt`, `magic missile`, `shocking grasp` |
| `creation` | 4, 4, 8, 8 | spells `continual light`, `create food`, `create spring`, `create water`, `create rose`, `floating disc` |
| `curative` | -1, 4, -1, 8 | spells `cure blindness`, `cure disease`, `cure poison` |
| `detection` | 4, 3, 6, -1 | spells `detect evil`, `detect good`, `detect hidden`, `detect invis`, `detect magic`, `detect poison`, `farsight`, `identify`, `know alignment`, `locate object` |
| `draconian` | 8, -1, -1, -1 | spells `acid breath`, `fire breath`, `frost breath`, `gas breath`, `lightning breath` |
| `enchantment` | 6, -1, -1, -1 | spells `enchant armor`, `enchant weapon`, `fireproof`, `recharge` |
| `enhancement` | 5, -1, 9, 9 | spells `giant strength`, `haste`, `infravision`, `refresh` |
| `harmful` | -1, 3, -1, 6 | spells `cause critical`, `cause light`, `cause serious`, `harm` |
| `healing` | -1, 3, -1, 6 | spells `cure critical`, `cure light`, `cure serious`, `heal`, `mass healing`, `refresh` |
| `illusion` | 4, -1, 7, -1 | spells `invis`, `mass invis`, `ventriloquate` |
| `maladictions` | 5, 5, 9, 9 | spells `blindness`, `change sex`, `curse`, `energy drain`, `plague`, `poison`, `slow`, `weaken` |
| `protective` | 4, 4, 7, 8 | spells `armor`, `cancellation`, `dispel magic`, `fireproof`, `protection evil`, `protection good`, `sanctuary`, `shield`, `stone skin` |
| `transportation` | 4, 4, 8, 9 | spells `fly`, `gate`, `nexus`, `pass door`, `portal`, `summon`, `teleport`, `word of recall` |
| `weather` | 4, 4, 8, 8 | spells `call lightning`, `control weather`, `faerie fire`, `faerie fog`, `lightning bolt` |

`lore` is a skill. Its group entry sits on `mage default`. It does not identify an item. Optimal does not buy `mage default` to get a spell, and it does not practice `lore`.

The numbers in the next table are `levelByClass` / `ratingByClass`. The level is when bare `practice` can show the name. The rating is the train cost of gaining that skill by itself. A rating of 0 is omitted from the gain list, and `practice` answers `You can't practice that.`

| Skill | Mage | Cleric | Thief | Warrior |
| --- | --- | --- | --- | --- |
| `sword` | 1/5 | 1/6 | 1/3 | 1/2 |
| `dagger` | 1/2 | 1/3 | 1/2 | 1/2 |
| `mace` | 1/5 | 1/2 | 1/3 | 1/3 |
| `axe` | 1/6 | 1/6 | 1/5 | 1/4 |
| `flail` | 1/6 | 1/3 | 1/6 | 1/4 |
| `spear` | 1/4 | 1/4 | 1/4 | 1/3 |
| `polearm` | 1/6 | 1/6 | 1/6 | 1/4 |
| `whip` | 1/6 | 1/5 | 1/5 | 1/4 |
| `hand to hand` | 25/8 | 10/5 | 15/6 | 6/4 |
| `shield block` | 1/6 | 1/4 | 1/6 | 1/2 |
| `parry` | 22/8 | 20/8 | 13/6 | 1/4 |
| `dodge` | 20/8 | 22/8 | 1/4 | 13/6 |
| `enhanced damage` | 45/10 | 30/9 | 25/5 | 1/3 |
| `second attack` | 30/10 | 24/8 | 12/5 | 5/3 |
| `third attack` | 53/0 | 53/0 | 24/10 | 12/4 |
| `recall` | 1/2 | 1/2 | 1/2 | 1/2 |

`recall` is on the table because every class can practice it at level 1. Optimal still skips it, for the combat-recall comparison above.

Once `dagger` is learned, a level 1 mage's listing can show it. `hand to hand` stays hidden until level 25, `dodge` until 20, `parry` until 22, and `second attack` until 30. `third attack` is rating 0, so the gain list omits it and `practice` refuses it. The listing, not this table, decides what can be practiced today. The table decides whether a missing name may be bought yet. `gain` itself does not check the level. Buying `dodge` at level 1 spends trains on a skill `practice` will refuse until level 20. Optimal does not buy a name while the score level is below the level in this table. No score level means no gain.

Spells a player might expect to raise first, same level/rating columns. They appear on the practice listing only after the character has learned them. Optimal does not buy their groups and does not practice them. A mage spell rating of 1 would rise quickly. That is not a reason to spend the session while engage is `kill`.

| Spell | Mage | Cleric | Thief | Warrior |
| --- | --- | --- | --- | --- |
| `magic missile` | 1/1 | 53/1 | 2/2 | 2/2 |
| `burning hands` | 7/1 | 53/1 | 10/2 | 9/2 |
| `armor` | 7/1 | 2/1 | 10/2 | 5/2 |
| `bless` | 53/1 | 7/1 | 53/2 | 8/2 |
| `cure light` | 53/1 | 1/1 | 53/2 | 3/2 |
| `sanctuary` | 36/1 | 20/1 | 42/2 | 30/2 |
| `identify` | 15/1 | 16/1 | 18/2 | 53/2 |
| `enchant weapon` | 17/2 | 53/2 | 53/4 | 53/4 |

`refresh` is in both `enhancement` and `healing`. A preference name that sits in more than one group buys the cheapest printed group that contains it.

## Optimal order

The candidate list is built for this step. The first candidate that is not finished is the one session.

1. **Wielded type.** The worn weapon's `weapon_type` is one of `sword`, `dagger`, `spear`, `mace`, `axe`, `flail`, `whip`, `polearm`. Practice it until adept. An empty `weapon_type` is not guessed from the short text. A staff stays unnamed until identify says `spear`, which is the gear proposal's rule.
2. **Class weapon, and the wielded slot is empty.** Mage or thief: `dagger`. Cleric: `mace`. Warrior: `sword`. Practice it while the stored percent is missing or at or below 25. Gear treats a percent at or below 25 as unusable, so the slot stays empty until a reading shows a higher percent. Once the stored percent is above 25, this candidate drops out until that type is actually wielded. Further sessions then come from step 1. Gain it when it is missing, the score level has reached the table, and a printed offer adds it.
3. **`hand to hand`, and the wielded slot is empty.** Practice it when it is on the listing and still below adept. It is what the unarmed swing uses. It is not gained while step 2 is still the unfinished candidate. A level 1 mage does not have it on the listing.
4. **`shield block`, when a shield is worn.**
5. **`parry`, when a weapon is worn.** An empty wielded slot does not parry, so it is not practiced then.
6. **`dodge`.**
7. **`enhanced damage`.**
8. **`second attack`.**
9. **`third attack`.**

Steps 4 through 9 are finished at adept. A candidate on the listing below its goal is practiced. A candidate absent from the listing is gained when the class is known, the score level has reached the table, trains cover a printed offer, and an offer adds that name. The cheapest such offer wins. A skill row tied with a group row prefers the skill row. `sword` at the printed cost 2 beats `weaponsmaster` at 20 and `warrior default` at 40. An unaffordable gain does not get replaced by a cheaper later gain. The walk may still practice a later name that is already on the listing. No offer, a table level still in the future, or a rating of 0 skips the candidate.

Optimal does not practice a name because a wield line said `clumsy`. A clumsy weapon is already above 25 and, when it is the wielded type, step 1 raises it to adept. A fumble on the class weapon, with the slot empty again, is step 2.

The worn snapshot is the one the gear proposal defines, including `You are using:` followed by `Nothing.` Optimal sends one `equipment` survey when this session has no snapshot yet, so the shield and the weapon are known before a session is spent. Preference does not wait for that snapshot.

## Preference

`preference` walks the operator's names and then stops. It does not continue into the optimal list. An operator who wants the optimal names and then a spell writes those names, in order, in the list.

The first listed name that is on the practice listing and below adept is practiced. When none are, the first listed name that is missing and that a printed offer can add is gained. A skill offer for that name is a candidate. A group offer is a candidate when this proposal's membership table says the group contains the name. The cheapest printed candidate wins, with the same skill-over-group tie. `You must learn the full group.` marks that name `group_only`. A later gain of that name is a group, or nothing when no printed group contains it. Optimal never sets out to buy a spell group. A preference list that names `magic missile` does, through `combat`, when `gain list` shows `combat`.

A name the listing does not show is not practiced. A name the gain list does not offer is not gained. The style does not fall through when the list is exhausted.

## Where the session is spent

Practice trainers and gain trainers are different mobiles. Practice requires `ACT_PRACTICE` (1024). Gain requires `ACT_GAIN` (134217728). Both missing-trainer replies are the sentence `You can't do that here.` The sentence marks only the verb that was just sent. A room can accept one and refuse the other. A successful `practice <skill>`, or `You are now learned at <name>.`, stores the room name as the practice guild. A successful `gain list` stores it as the gain guild. Bare `practice` works in any room and does not mark a guild.

There is no path to a guild and no room number in this algorithm. Help GAIN says to check New Thalos. That sentence is not a route. The hunt walks where it already walks. The first time level yields in a room that has a name and a mobile, and that verb is not yet marked, the spend or the `gain list` is the probe. `You can't do that here.` marks the room refused for that verb. A later step in that room does not probe it again. A room with no mobile, a room with no name, and a refused room return nothing. Gear and the rest of the step proceed. Sessions sit until a later room accepts the verb.

`gain` with no argument, once a gain trainer is in the room, replies `<trainer> tells you 'I do not understand...'`. The list is `gain list`. The header line starts with `group` or `skill`, three name-and-cost pairs wide. The parser reads the 18-column name and the cost. It does not split the name on spaces. `gain` selects with `name.startswith` in registry order, so the argument is the full printed name. Offers replace the stored offers. A successful `trains you in the art of <name>` marks the offers stale and does not add the group's members at 1%. The code does set each new member to 1%. The next bare `practice` is what shows them. `You already know that group!` and `You already know that skill!` drop that offer. `That group is beyond your powers.` and `That skill is beyond your powers.` drop it. `You are not yet ready for that group.` and `You are not yet ready for that skill.` clear the stored trains so the next score line is required before another gain. `I do not understand...` marks the offers stale.

`gain` stands at position `STANDING`. It is sent only when the view's position is the standing word from `You are standing.` Resting, sitting, sleeping, and fighting do not get a gain. The command would answer `Nah... You feel too relaxed...`, `Better stand up first.`, `In your dreams, or what?`, or `No way!  You are still fighting!` A practice spend is sent when the position is empty or awake. Sleeping and worse wait. `You have no practice sessions left.` sets `practices_left` to 0. `You can't practice that.` locks that name until the score level changes.

A fight does not get a session. The level algorithm returns a directive while it is fighting, and the engine's danger rule runs first. `PracticeStrategy` also returns nothing when the view says the character is fighting.

## PracticeStrategy

`PracticeStrategy` subclasses `Strategy`. `direct(view, command_catalog, practice_catalog)` returns one `Directive` or nothing. The level signature stays `(view, command_catalog)`. The context passes `practice_catalog` only to a strategy that accepts it, the same way the gear proposal passes `gear_catalog`.

The composition root installs it when a level goal exists and `practice.style` is not `off`, and when a `practice` section is present with `optimal` or `preference`. Absent section and a level goal means `optimal`. Absent section and no level goal means it is not installed. The engine still holds one `Strategy`. `SequenceStrategy` asks level, then practice, then gear, and skips a child that is not installed. While level returns a hunt, a flee, or a rest, practice waits. While practice returns a directive, gear waits. `allow_social` is false whenever practice returns a directive. When a personality is installed, `docs/proposals/Personality.md` may take the step after the level child yields and before this strategy is asked. A hunt, a flee, and a rest are not that opening. `practice.style` stays the operator's list.

The role for a spend is `learn`. A reading stays `survey`. `practice` is on the SUMMARY index under `other`, so the catalog fallback can supply it. `gain` is not on that index. `pick` returns `gain` only when the stored command list includes it. A help-only knowledge list does not make `gain` available. That is the memory proposal's `known_commands` rule.

`PracticeStrategy.direct` returns the first match.

1. **Optimal, and no worn snapshot this session.** `survey`, category `objects`, preference `equipment`.
2. **The practice listing is missing, or a spend has marked it stale.** `survey`, category `other`, preference `practice`, no argument. This does not need a guild.
3. **The next action is a practice spend, `practices_left` is a positive number, the position allows it, and the room is the practice guild or an unprobed room with a mobile.** `learn`, category `other`, preference `practice`, argument the full name.
4. **The next action is a gain, trains are known and cover the cheapest offer, the position is standing, `gain` is known, and the offers are missing or stale.** `survey`, argument `list`, category left blank unless the stored list files `gain` under a heading. The preference is `gain`. The room must be the gain guild or an unprobed room with a mobile.
5. **That same gain, and the offers are fresh.** `learn`, preference `gain`, argument the full group or skill name from the offer.
6. **Nothing.** Return nothing.

`practices_left` unknown takes step 2 before a probe. Trains unknown skips steps 4 and 5. The level algorithm's `score_due` is what fills trains, because level runs first. Zero practices and zero trains return nothing and do not probe.

## Config

`practice` is its own section. It is not a `goal.kind`. The level goal stays the level goal.

```yaml
practice:
  style: optimal
```

```yaml
practice:
  style: preference
  names:
    - backstab
    - dodge
    - magic missile
```

- `style` is `optimal`, `preference`, or `off`. Anything else raises `ValueError("practice.style must be optimal, preference, or off")`.
- `preference` with `names` missing or empty raises `ValueError("practice.names must list at least one skill or spell")`.
- A name that is not a non-empty string raises `ValueError("practice.names must list skill and spell names")`.
- `off` does not install `PracticeStrategy`.

## Records

| Piece | Owner | Saved |
| --- | --- | --- |
| One learned name and its percent | `LearnedAbility` on `WorkingMemory` | Section `learnedAbilities` |
| Trains, room marks, gain offers, the stale and locked flags | `PracticeState` on `WorkingMemory` | Section `practice` |
| The eight weapon percents the gear proposal already stores | `WeaponSkill` | Section `weaponSkills`, written by the same listing parser |
| Query that chooses the next name | `PracticeCatalog` | Nowhere. Built each step |
| The algorithm | `PracticeStrategy` | Nowhere |

`LearnedAbility` fields are `name`, `percent` (empty until a listing printed one), `done`, and `group_only`. `done` is set by `You are already learned at <name>.` and by `You are now learned at <name>.` `PracticeState` fields are `class_name` (empty, or `mage`, `cleric`, `thief`, `warrior`), `trains` (empty or a whole number), `listing_stale`, `offers` (`name`, `kind` of `group` or `skill`, `cost`), `offers_stale`, and `rooms`. A room has the room name, `practice` of empty, `accepted`, or `refused`, and `gain` of the same three. `clear` drops `learnedAbilities` and `practice`. The knowledge document does not gain either key. Sections are written out by name. There is no section registry.

The bare-practice parser writes every printed name onto `LearnedAbility` and writes the eight weapon names onto `WeaponSkill` as well. That is the gear proposal's practice reading when both land. One parser. A name absent from a later listing is dropped from both. The column width is 18, then three spaces, then the percent. `hand to hand` stays one name.

`PracticeCatalog` is constructed with the memory rows, the score level, the class token, the worn weapon type, whether a shield is worn, whether a weapon is worn, whether the wielded slot is empty, the room name, whether the room has a mobile, and the view position. It does not send telnet or call Ollama. `next_practice` and `next_gain` implement the order above. The goal package does not import it.

## Types

| Type | File | Role |
| --- | --- | --- |
| `LearnedAbility` | `src/memory/LearnedAbility.py` | One name, its percent, `done`, and `group_only`. |
| `PracticeState` | `src/memory/PracticeState.py` | Trains, room marks, gain offers, stale flags. |
| `PracticeCatalog` | `src/strategy/PracticeCatalog.py` | The next name to practice or gain. Not saved. |
| `PracticeStrategy` | `src/strategy/PracticeStrategy.py` | The algorithm. |

`Directive.role` gains `learn` for a spend. Readings stay `survey`.

## Tests

`tests/test_practice_catalog.py` and `tests/test_practice_strategy.py`. No socket and no model. The live suite stays out.

- A listing `dagger                40%  parry                 10%  magic missile         15%  ` stores three abilities. `dagger` also stores a `WeaponSkill`. `magic missile` does not. The name `hand to hand` is one skill.
- `Class: warrior` stores `class_name` `warrior`. A later who token `Mag` does not replace it. With no score class, the who token `War` stores `warrior`. `IMP` stores nothing.
- `You have 3 practice sessions left.` sets `GearProgress.practices_left` to 3. The score line `You have 4 practices and 2 training sessions.` sets trains to 2 and leaves `practices_left` at 3.
- `You practice dagger.` sets `listing_stale` and leaves the stored percent at 40. The following strategy directive is bare `practice`.
- `You are now learned at dagger.` with `class_name` `warrior` stores 75 and `done`. `You are already learned at parry.` sets `done` and does not lower a stored percent.
- `You have become better at dagger!` and `You learn from your mistakes, and your dagger skill improves.` set `listing_stale` and do not add 1 or 3.
- `You can't do that here.` after `practice dagger` marks that room `practice: refused` and leaves `gain` empty. The same sentence after `gain list` marks `gain: refused` and leaves `practice` empty.
- `You can't practice that.` locks the name until the score level changes. `You have no practice sessions left.` sets `practices_left` to 0.
- A gain listing whose group rows include `weaponsmaster      20    ` and whose skill rows include `sword              2     ` stores those two offers. The cheapest offer that adds `sword` is the skill at 2.
- `trains you in the art of weaponsmaster` sets `offers_stale` and does not add `axe` or `dagger`.
- `tells you 'You must learn the full group.'` sets `group_only` on `magic missile`. `tells you 'That group is beyond your powers.'` drops that offer. `tells you 'You are not yet ready for that skill.'` clears trains.
- Optimal, class `warrior`, sword wielded at 40, parry at 10, no shield: the practice is `sword`. The same sword at 75 practices `parry`. A worn shield and `shield block` at 10, with sword at 75, practices `shield block` before `parry`.
- Optimal, empty wielded slot, class `mage`, score level 1, `dagger` at 20, `hand to hand` absent: the practice is `dagger`. `hand to hand` is not gained. `dodge` is not gained. With `dagger` missing, trains 2, and a skill offer `dagger` at 2, the gain is `dagger`. With trains 1, that gain is skipped.
- Optimal, empty slot, class `warrior`, score level 6, `sword` at 40, `hand to hand` at 10: the practice is `hand to hand`. Sword is already above 25 and is not wielded.
- Optimal does not return `recall`, `magic missile`, `bash`, or `backstab` when those names are on the listing below adept.
- Preference names `backstab`, then `dodge`, with both on the listing: the practice is `backstab`. When `backstab` is `done` and `dodge` is `done`, the strategy returns nothing while `sword` is still at 10.
- Preference name `magic missile`, absent from the listing, with `combat` offered at 6: the gain argument is `combat`. Optimal with the same offer does not gain `combat`.
- `gain convert` and `train` are absent from every directive. `practice sword` is absent from every `GearStrategy` directive. Bare `practice` remains the gear survey when the wielded goal has no skill list.
- `LevelStrategy` still omits `practice`, `train`, and `cast`. A sequence of level, practice, and gear returns `kill` when level returns `kill`, returns `practice dagger` when level returns nothing and dagger is the next spend in an accepted room, and returns `compare` when practice also returns nothing.
- A help-only command list does not send `gain`. The knowledge `to_document` has no `learnedAbilities` key and no `practice` key. The memory document round-trips the ability and the room mark.
- `You can't do that here.` in a room with no stored name does not create a room mark. A room with no mobile returns nothing.

## Phases

1. **Records and parsers.** `LearnedAbility`, `PracticeState`, the practice listing, the gain listing, the practice replies, the gain replies, the score trains line, and the two improve sentences. Weapon rows stay on `WeaponSkill`. No telnet and no strategy. `tests/test_practice_catalog.py` covers the parsers and `next_practice` / `next_gain` against hand-built rows.
2. **Strategy.** `PracticeStrategy` and the `learn` role. Sequence order level, then practice, then gear. Depends on the strategy types those proposals introduce. Does not wait on voice prompts.
3. **Gain.** Offers, the membership table, `group_only`, the train check, and the standing check. `gain` is sent only when the stored command list has it.

The live suite stays out of every phase.

## Gaps this proposal leaves in place

- The character does not walk to a guild. A refused room stays refused. Sessions sit until the hunt enters a room that accepts the verb. One yield in a new room that has a mobile is the probe.
- `train`, `gain convert`, and `gain points` are not sent. Help TRAIN's wisdom and constitution advice is a different command.
- Use can raise a percent from 75 toward 100. The two improve sentences mark the listing stale. The algorithm does not spend a practice to cause them.
- The level and rating table can drift from the server. `You can't practice that.` locks the name until the score level changes. A group this table does not list is not treated as containing a missing spell.
- `recall` stays off the optimal list while the combat failure check grows with the learned percent. A server change that makes a higher percent succeed more often is the point at which `recall` would join that list.
- Offensive and curative spells stay off the optimal list while engage is `kill`. Gear still casts `identify` and the two enchant spells at whatever percent the character already has.
- The area list, command categories, pace, `met`, and the notch are unchanged. This proposal does not publish a gate and does not choose a mobile.
- `groups` is not sent. Creation is not assumed to have granted a basics group.

## Implementation note

`docs/reference` describes the running code. Add the practice section to the working-memory reference in the phase that stores `LearnedAbility`. Until phase 1 lands, this file is the only description. The level strategy, the gear strategy, and the two memory documents stay as their own proposals describe them, with the sequence order and the `practice <skill>` gap amended there.
