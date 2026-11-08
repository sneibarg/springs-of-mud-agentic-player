# Gear

Proposal for a gear catalog, the working-memory records it reads, and gear goals. This document does not change the runtime.

`CommandCatalog` is a read model. It is built each step from stored commands, and `pick` returns a verb only when that verb is known and filed under the category the algorithm asked for. `GearCatalog` is the same kind of object for pieces of gear. The records live on `WorkingMemory`. The catalog is not saved. A gear goal is a `Strategy`, beside `LevelStrategy`, and it runs when the level algorithm yields the step.

The other proposals stay in force. `docs/proposals/Memory.md` keeps gear off the character knowledge document. `docs/proposals/Goal.md` still owns goal config and the level clock. `docs/proposals/Strategy.md` still owns `direct` and `CommandCatalog`. `docs/proposals/GameplayEngine.md` still sends one command per step, after danger, flight, standing, and an owed reply.

## What the server actually tells us

`equipment` prints `You are using:` and one line per occupied slot. The labels are the server's `EQUIP_SLOT_LABELS`: light, two fingers, two necks, torso, head, legs, feet, hands, arms, shield, body, waist, two wrists, wielded, held, and floating. `look <player>` prints the same labels after a line that ends with `is using:`. The `look_player` prompt already maps those labels onto slot names and keeps two fingers, necks, or wrists as two entries. Order is what distinguishes the pair. The text after the label is the short description, not a keyword and not a score.

`inventory` prints `You are carrying:` and the visible unworn lines from `InfoUtil.visible_inventory_lines`.

`compare` looks only in what the character is carrying, including worn gear. One argument compares that item to the equipped item of the same type that shares a wear flag. Two arguments compare those two carried items. Only weapons and armor have a compare value (`ItemApi.compare_value`). The reply is one of three sentences, or a refusal:

- `<item> looks better than <other>.`
- `<item> looks worse than <other>.`
- `<item> looks about the same as <other>.`
- `Compare what to what?`
- `You do not have that item.`
- `You aren't wearing anything comparable.`
- `You can't compare those items.`

There is no number in the reply. A catalog that stores "better by 4" is inventing a value the server did not send.

`look <item>` is the description. The `look_item` prompt already classifies the reply as shown, nothing special, ambiguous, missing, or blocked. It does not name an item type.

`look <name>` on a player or mobile shows the gear they are wearing. That is a lead. `compare` cannot use an item that is on someone else's body. A short description seen on them is not a relation to our own piece.

`enchant weapon` and `enchant armor` are spells. The item must be carried, not worn (`The item must be carried to be enchanted.`). The spell replies include `That isn't a weapon.`, `glows blue`, `glows a brillant blue!`, `glows brightly, then fades`, `Nothing seemed to happen.`, and `shivers violently and explodes`. Success is not a new compare value. The item can be destroyed. `cast` is the combat-category verb. The spell name is its argument. `wear`, `wield`, and `hold` replace the piece already in the slot (`Equipped.wear_item(..., replace=True)`). `remove` exists and is not on the SUMMARY index, so the catalog can use it only when that character's stored command list has it.

## Ownership

| Piece | Owner | Saved |
| --- | --- | --- |
| One studied piece: where it is, its short text, look, compare, enchant, and what a player said | `GearPiece` on `WorkingMemory` | Agent-memory document, section `gear` |
| Query over those pieces | `GearCatalog` | Nowhere. Built each step, like `CommandCatalog` |
| Replace or enchant goal | `Goal` with `kind: gear` | Config. Met state on the piece and on a small gear progress block |
| The algorithm that spends a step on gear | `GearStrategy` | Nowhere |
| Parsing `equipment`, `compare`, `look`, and enchant lines | `src/play` | Nowhere. It calls `WorkingMemory` |

`WorldKnowledge` does not gain a gear section. A knowledge save replaces the whole document. Room `itemLines` stay the raw look text they already are. A gear piece seen on the ground is still a `GearPiece` with location `room`, not a second copy of the room snapshot.

`GearCatalog` lives in `src/strategy`, next to `CommandCatalog`. It does not send telnet, call Ollama, or decide that a goal is met. `GearStrategy` asks it, then asks `CommandCatalog.pick` for the verb.

## GearPiece

`src/memory/GearPiece.py`. The type owns its own updates. `WorkingMemory` stores the list, finds a piece, and includes `gear` in `to_review`, `to_collection`, and `from_collection`. That is the memory proposal's rule for a new section: the type serializes itself, and `clear` drops the list.

Identity is the short description plus the place we saw it. Mortal output has no vnum. Two lines with the same short text stay two pieces when their places differ. A later line with the same short text and the same place updates the existing piece.

Fields:

- `short`. The text after an equipment label, or the inventory line, trimmed.
- `keyword`. The word that `look` and `compare` accepted. Empty until one does.
- `location`. `worn`, `carried`, `room`, or `other`.
- `slot`. A worn slot name from the label map. Empty when it is not worn. Two fingers are `finger` with `slot_index` 1 and 2, in the order printed. Necks and wrists work the same way.
- `slot_index`. 1 when the label is unique.
- `holder`. Our character name, a room name, or the other person's name.
- `look_result`. Empty, `shown`, `nothing_special`, `ambiguous`, `missing`, or `blocked`.
- `description`. The look text when we have one. Raw server text is enough.
- `comparison`. Empty, `better`, `worse`, `same`, or `incomparable`.
- `compared_to`. The other short text in the compare sentence. Empty when we have not compared.
- `enchant`. Empty, `success`, `exceptional`, `failed`, `disenchanted`, or `destroyed`.
- `kind`. Empty, `weapon`, or `armor`. Set from the slot we wore it in, or from a compare that succeeded against a piece whose kind is already known. `compare` succeeding means both pieces are weapons or both are armor. It does not by itself say which.
- `weapon_type`. Empty, or one of `sword`, `dagger`, `spear`, `mace`, `axe`, `flail`, `whip`, `polearm`. Set only from `Weapon type is <type>.` A short description that contains the word sword does not set it. A staff the server classifies as a spear stays empty until that sentence says `spear`.
- `wield_band`. Empty, or the wield reply for this piece: `part`, `confident`, `skilled`, `adequate`, `clumsy`, `fumble`, or `lost`. The server chooses that sentence from the character's learned percent with the weapon's type. The sentence does not name the type.
- `gear_level`. Empty, or the object's level as a whole number. The gear-level section names the only sentences that set it.
- `level_block`. Empty, or `refused`. The wear refusal sets `refused`. A later score whose level is greater than or equal to `gear_level` clears it.
- `rejects`. Sides that cannot wear this piece: any of `good`, `evil`, and `neutral`. Empty until the alignment section learns one. An identify that names no anti flag stores an empty list and sets `alignment_known`.
- `alignment_known`. False until the identify extra-flags clause has been read. A zap adds a side and does not by itself mark the other sides as allowed.
- `alignment_block`. Empty, or `zapped`. Either zap sentence sets `zapped`. It clears when the current side is known and is not in `rejects`.
- `reports`. What players told us. Each report is the speaker name, the raw text, a claim of empty, `better`, `worse`, or `same`, and a reported type that stays empty until the words name one of the eight types. A reported type does not set `weapon_type`. A reported level does not set `gear_level`. A reported alignment does not set `rejects`.

A blank comparison is not `same`. A report is not a comparison. `GearCatalog` will not treat a player's sentence as `looks better than`.

`ambiguous` look result freezes that piece. The algorithm does not invent `2.sword`. It stops issuing `look` and `compare` for that keyword until a later, pinned server form says how to name one of a pair.

## GearCatalog

Built from the current gear list. Same inputs, same answers.

- `worn(slot, index)` returns the worn piece, or nothing.
- `carried()` returns pieces with location `carried` that are not destroyed.
- `needs_look()` returns owned pieces (`worn` or `carried`) whose `look_result` is empty. Ambiguous pieces are left out.
- `needs_compare()` returns an owned piece whose `comparison` is empty, whose `look_result` is `shown` or `nothing_special`, and whose kind is `weapon` or `armor` or whose slot is one this proposal treats as a weapon or armor slot. Wielded is the weapon slot. Torso, head, legs, feet, hands, arms, shield, body, waist, and the paired finger, neck, and wrist slots are armor slots for this purpose. Light, held, and floating are not compared and are not enchanted.
- `replacement(slot, index)` returns a carried piece whose `comparison` is `better` and whose `compared_to` is the short text of the piece worn in that slot.
- `empty_slot(slot, index)` is true when no worn piece is stored there.
- `seen_on(name)` returns pieces with location `other` and that holder.
- `ask_next(names)` returns one `(holder, slot, short)` we have seen on a player in `names` and have not yet stored a report for. Agentic names come first when the caller passes them first. The catalog does not know who is agentic. The strategy does, from the session being.
- `enchant_spare(kind)` returns a carried piece of that kind, not destroyed, with `enchant` empty, that is not the only piece of that kind we own. The worn piece does not qualify. Enchant requires the item to be carried, and this query is the steady rule below. A weapon spare also has to pass the skill rule in the weapon-skill section. A spare the gear-level section calls blocked is left out, and so is a spare the alignment section calls blocked. Destroying an upgrade the character cannot wear yet does not help the hunt that is trying to reach it.
- `skill_percent(weapon_type)` returns the learned percent for that type, or nothing when `practice` has not listed it.
- `skilled_replacement(slot, index)` is `replacement` for an armor slot. For `wielded` it drops a piece the weapon-skill section calls unusable, and it orders the rest by that section's rank. A piece the gear-level section calls blocked is left out of either slot. A piece the alignment section calls blocked is left out. When the slot is already worn and the piece's alignment is still unknown, it is left out as well, so a probe cannot strip the worn piece.
- `gear_gate(character_level)` returns the lowest object level among carried pieces the gear-level section counts as a pending upgrade, when that level is above the character. Empty when the character's score level is unknown, or when no such piece exists.

`pick` is the wrong word. A gear query returns a piece, not a verb. The strategy then asks `CommandCatalog` for `compare`, `look`, `wear`, `wield`, `hold`, `get`, `equipment`, `inventory`, `practice`, `tell`, or `cast`. A verb that is not known, or that is filed under a different category, is not sent. `compare` and `look` are `objects` on the SUMMARY index. `practice` is `other`. `tell` is `information / communication`. `cast` is `combat`. `remove` is used only when the stored command list includes it.

## Weapon skills

A better weapon is not a better choice when the character cannot use its type. `compare` ranks the item. The weapon skill ranks the character. The catalog keeps both, and the wielded slot uses both.

The server's weapon skills are `sword`, `dagger`, `spear`, `mace`, `axe`, `flail`, `whip`, and `polearm`. `SkillUtil.weapon_skill_name` maps each of those types to the skill of the same name. An exotic weapon uses `hand to hand`. An empty hand uses `hand to hand` as well. Armor slots have no weapon skill. `shield block` is a different skill and is not a reason to wear or refuse a shield in this proposal.

`practice` with no argument prints the skills the character can see, three to a line, as `<name>` padded to 18 columns, three spaces, the percent padded to 3, and `%`. It then prints `You have <n> practice sessions left.` That command does not spend a session. `practice <skill>` does spend one. This proposal sends only the bare command. It does not train `sword` or any other name. The level proposal already leaves spending practices out of the level algorithm. Gear leaves it out too.

Those eight names, plus `hand to hand` when it is printed, are stored as `WeaponSkill` records on `WorkingMemory`: `name` and `percent`. A later bare `practice` replaces the list. A name that is absent after that reading is a type the character has not learned. The catalog treats an absent weapon skill as unusable, the same as a printed `0%` or `1%`. The records ride the agent-memory document under `weaponSkills`. They are not copied onto world knowledge. `clear` drops them with the gear list.

`GearCatalog` is built with that list as well as the pieces. `skill_percent` reads it. The piece's `weapon_type` is the join key. Until `identify` prints `Weapon type is <type>.`, the type is empty and there is nothing to join. The word in the short description is not the type. Game data that files a school staff under the spear skill is not visible to the agent. A player's report may name a type. That name stays on the report. It does not set `weapon_type` and it does not change `skill_percent`.

Wielding is the other sentence the server uses. `Item.weapon_skill_feedback_key` turns the learned percent into one line, and `Equipped` appends it only when the slot is `wielded`:

| Printed line | Stored band | Learned percent |
| --- | --- | --- |
| `<item> feels like a part of you!` | `part` | 100 |
| `You feel quite confident with <item>.` | `confident` | 86–99 |
| `You are skilled with <item>.` | `skilled` | 71–85 |
| `Your skill with <item> is adequate.` | `adequate` | 51–70 |
| `<item> feels a little clumsy in your hands.` | `clumsy` | 26–50 |
| `You fumble and almost drop <item>.` | `fumble` | 2–25 |
| `You don't even know which end is up on <item>.` | `lost` | 0–1 |

The line names the item, not the type. The parser stores `wield_band` on that piece. It does not invent a percent from the band, and it does not copy the band onto the `WeaponSkill` row. The percent remains what `practice` printed. The band is how this character felt with this object.

A wielded candidate is unusable when any of these is true:

- `weapon_type` is one of the eight skills and `skill_percent` is missing, or it is 25 or lower. Percent 0 and 1 are the `lost` line. Percent 2 through 25 is the `fumble` line. `clumsy` starts at 26 and stays usable.
- `wield_band` is `fumble` or `lost`.
- `weapon_type` is empty and `wield_band` is empty. The catalog will not prefer it over a typed piece. An empty wielded slot may still try one such piece, once, so the wield sentence can fill the band. It does not try a second untyped piece while the first is still `fumble` or `lost` and `remove` is unknown.

Among the pieces that remain, `skilled_replacement` orders by `skill_percent` descending, then by `wield_band` in the table order above, then by short text. A mace that compares better and is at 10% is unusable. A sword that compares better and is at 80% is the one `skilled_replacement` returns. A mace that compares better and is at 80% is chosen over a sword that also compares better and is at 40%. Compare still has to say `better` before either replaces a worn weapon. The skill order chooses among those better pieces. It does not promote a `worse` or `same` piece over them.

An empty wielded slot accepts the highest-ranked usable carried weapon. When every carried weapon is unusable, the slot stays empty. `hand to hand` is the skill that empty hand is using. The strategy does not wield a lost weapon to fill the hand.

`enchant_spare` for a weapon uses the same unusable test. A spare whose type the character fumbles is not enchanted. Destroying it would not improve a weapon the character can use. An armor spare is unchanged, because armor has no weapon skill.

`cast identify <keyword>` is the command that fills `weapon_type`, when `cast` is known under `combat`. It is one identify, for a wielded candidate whose type is empty, or for a weapon or armor candidate whose `gear_level` is empty or whose alignment is still unknown. The gear-level section reads `level is <n>` from that same page. The alignment section reads the extra-flags clause. Affect bonuses stay unparsed. `glows blue` still does not become a skill percent, and it does not become an object level.

## Gear level

The object's level is the lowest character level that may wear, wield, or hold it. `Equipped.wear_item` checks `character.level` against `item.level` before it chooses a slot. Below that level the character is told `You must be level <n> to use this object.` The `<n>` is the object's level. The room is told `<name> tries to use <item>, but is too inexperienced.` That room line has no number, and it is someone else's attempt when we hear it. This proposal does not read a level from it.

`compare` does not print a level. `look` does not. A short description that contains a number does not. A player's report does not. The catalog does not treat a low object level as a weak piece or a high object level as a strong one. `compare` remains the only better, worse, or same. A level 1 sword that compares better stays ahead of a level 10 sword that compares worse.

Two sentences we cause ourselves do print the number:

- Identify's summary line is `Weight is <weight>, value is <cost>, level is <level>.` The integer after `level is` is `gear_level`. Weight and value stay unparsed, with the affect lines.
- `wear`, `wield`, and `hold` answer `You must be level <n> to use this object.` That stores `gear_level` as `<n>` on the piece we just named, and sets `level_block` to `refused`.

Drink, scroll, wand, and staff refusals are different sentences. They are not this field. A shop `list` prints the level in a column, `[<level> <price> <qty>] <short>`, under the header `[Lv Price Qty]`. This proposal does not send `list` or `buy`, and a shop line does not create a piece.

`GearCatalog` is built with the character's score level as well as the pieces and the skill list. That level is the integer from `You are <name> <title>, level <level>,`. Until a score has been stored, the catalog has no character level.

A piece is blocked when `gear_level` is known, the score level is known, and the score level is lower. It is also blocked when `level_block` is `refused` and the score level is missing or still lower. A score that reaches `gear_level` clears `refused`. An unknown `gear_level` is not blocked, so one `wear`, `wield`, or `hold` can draw the refusal and learn the number. `skilled_replacement` and the empty-slot equip both skip a blocked piece. `needs_compare` does not. `compare` works on a carried item the character is not yet allowed to wear.

`gear_gate` is how that number reaches the level algorithm. `LevelStrategy` still does not wear, compare, or cast. It reads one new view field, `gear_gate`. The engine copies `GearCatalog.gear_gate(character_level)` onto the view. The goal package stores the integer and does not inspect pieces. Pace, `met`, and the notch stay on the configured `goal.level`. A locked sword does not make a cautious character bold, and it does not rewrite the target in the config.

The gate is the lowest `gear_level` above the score level among carried pieces the skill rule still allows and that already qualify as an upgrade: `comparison` is `better` against the piece worn in that slot, or the slot is empty and the empty-slot rule would accept the piece. It is not the single piece `skilled_replacement` would wear first. A better sword at 15 and a better usable mace at 9 publish 9, so the hunt reaches the mace before the sword. The mace at 10% skill does not publish a gate. A `worse` or `same` piece does not. A piece with an empty `gear_level` does not. A piece the alignment section calls blocked does not. Reaching a higher level does not change the character's side, so a rejected piece is not a reason to keep hunting. When the score reaches the published number, that piece can be worn and the next higher qualifying piece can publish a new gate.

The level algorithm's first rule stays "return nothing" when `met` is true and `gear_gate` is empty. A set `gear_gate` leaves that rule unmatched. The hunt below it keeps the same notch, the same flee lines, and the same consider outlooks. The character keeps earning levels until a score shows a level greater than or equal to the gate. Gear still waits while that hunt returns a directive. On a step the level algorithm yields, gear may identify or compare, and it does not wield the blocked piece.

The engine copies the gate when the level goal is open-ended (`minutes` 0), and while `met` is still false. Once a budgeted goal is met, the engine leaves `gear_gate` empty. The configured stop still holds, and the locked piece stays carried until a later open-ended run or until the configured target was already high enough to wear it. A process with no level goal does not grow a hunt from a locked piece. The gear goal waits, and it does not send `kill`.

A successful or exceptional enchant may raise the object's level by one on the server, up to one below the hero level. The glow line does not print the new number. The parser clears `gear_level` and `level_block` on `success` and `exceptional`. The next identify or the next wear reads the object again. The parser does not add one to the stored level. `failed`, `disenchanted`, and `destroyed` leave a stored level as it is, and `destroyed` already drops the piece out of the catalog.

## Alignment

Whether a piece can be worn depends on the character's side and on three item flags. `Equipped.alignment_blocked` rejects the wear when the character is good and the piece has `ITEM_ANTI_GOOD`, when the character is evil and the piece has `ITEM_ANTI_EVIL`, or when the character is neutral and the piece has `ITEM_ANTI_NEUTRAL`. The check runs after a replacement has already removed the piece that was in the slot. A level refusal returns before that removal. An alignment failure does not.

The server's sides, from `CharacterApi`, are an integer alignment:

| Integer | Side |
| --- | --- |
| 350 or higher | `good` |
| -350 or lower | `evil` |
| -349 through 349 | `neutral` |

`score` is the reading. At level 10 and above the line is `Alignment: <n>. You are <word>.` Below level 10 the line is `You are <word>.` and the integer is absent. The words are `angelic`, `saintly`, `good`, `kind`, `neutral`, `mean`, `evil`, `demonic`, and `satanic`. When the integer is present, the table above is the side. When it is absent, `angelic`, `saintly`, and `good` are `good`; `evil`, `demonic`, and `satanic` are `evil`; `kind`, `neutral`, and `mean` are `neutral`. An alignment of exactly 350 prints as `kind` and is still `good`. The integer is what catches that point. A word-only `kind` stays `neutral`, because the score did not show 350.

`WorkingMemory` stores that reading as `alignment`: the word, the integer when the line had one, and the side. `clear` drops it. The knowledge document does not get it. The catalog is built with the side. Until a score has been stored, the side is empty. A custom prompt that prints the raw number is not parsed. A kill changes alignment inside the server, and this proposal does not recompute that change. The next score is the new side.

Identify prints the flags in `Object '<name>' is type <kind>, extra flags <flags>.` Each flag name is the enum name after the first underscore, in lower case, with underscores turned into spaces. The three restrictions therefore appear as `anti good`, `anti evil`, and `anti neutral`. `extra flags none.` means the piece rejects no side. The bare word `evil` on that line is `ITEM_EVIL`, and `bless` is `ITEM_BLESS`. Neither is a wear restriction. `glow` and `hum` are not either. `(Glowing)` and `(Humming)` on an equipment line are the same two flags and do not set `rejects`.

A parsed extra-flags clause sets `alignment_known`. Each `anti <side>` phrase adds that side to `rejects`. A clause with none of the three phrases stores an empty `rejects` list. The piece can then be worn by any side. A player's report does not set `rejects`. A short description does not. `compare` and `look` do not name the flags.

`bless` and `curse` can glow an item with a holy or malevolent aura. Those spells set `ITEM_BLESS` or `ITEM_EVIL`. They do not clear an anti flag. This proposal does not cast them, and those glow lines do not change `rejects`.

Two of our own sentences mean the wear was refused and the piece left us:

- `wear`, `wield`, and `hold` say `You are zapped by <item> and drop it.` The room hears `<name> is zapped by <item> and drops it.` The room line is someone else's attempt when we are not the one who tried. The piece we named is no longer carried. Its location becomes `room`. The same reply can include `You stop using <other>.` first. That other piece was the one already in the slot. It is now `carried`, and the slot is empty. The new piece is on the ground. The replace goal does not become met.
- After a kill moves alignment, a worn piece that no longer matches says `You are zapped by <item>.` There is no `and drop it` on that sentence. The piece is still removed and placed in the room. Location becomes `room`.

The wear sentence adds the stored side to `rejects` when a side is already stored, and it sets `alignment_block` to `zapped`. The kill sentence sets `alignment_block` and waits. The next score supplies the side, and that side is added to `rejects`. A further kill before that score can move the integer again. The following score is still the side this proposal stores. A later zap against a fresh score corrects a side that was guessed across that gap.

A piece is alignment-blocked when the current side is in `rejects`, or when `alignment_block` is `zapped` and the current side is still empty or still in `rejects`. `skilled_replacement` and `enchant_spare` skip a blocked piece. `needs_compare` does not. `compare` does not look at alignment.

An occupied slot is not the probe. `wear_item` removes the worn piece before the alignment check, so one blind wear can empty the slot and drop the new piece. When `alignment_known` is false and the slot is worn, the catalog does not offer the piece. `cast identify` is what fills the flags first, when `cast` is known. An empty slot may try one piece whose flags are still unknown. The level check still runs first, so a too-high piece returns `You must be level <n> to use this object.` and stays carried. A piece that passes the level check and fails alignment zaps to the room, and it is not tried again.

`gear_gate` ignores a blocked piece. The level algorithm does not grow a hunt to change sides, and it does not choose mobiles because they would move alignment. A good character leaves an anti-good sword carried. An evil character can still wear that same sword once the flags say only `good` is rejected.

## Learning a piece

Play parses the server line and updates the piece. The parsers are local. `play.defer` can stay true. The `look_item` and `look_player` prompts remain optional enrichment when defer is false. They do not replace the sentences this proposal matches exactly.

1. **Worn set.** After `equipment`, or after our own look when the reply contains `You are using:`, replace the worn set. A slot that disappeared is no longer `worn`. The piece stays in the list as `carried` only when a later inventory line has the same short text. Otherwise its location becomes empty, which means we no longer know where it is. The catalog ignores an empty location.
2. **Carried set.** After `inventory`, the `You are carrying:` lines replace location `carried`. `You are not carrying anything.` clears carried.
3. **Look.** `look <keyword>` stores `look_result` and `description` on the piece with that keyword. The first keyword tried for a new short text is its last word. `You do not see that here.` tries the word before that, once. A second miss leaves `keyword` empty and `look_result` `missing`. `You see nothing special.` is `nothing_special` and still counts as looked.
4. **Compare.** A better, worse, or same sentence stores `comparison` on the piece named first and the other's short text on `compared_to`. `You can't compare those items.` stores `incomparable` when we know which keyword we sent. `You aren't wearing anything comparable.` stores that the worn counterpart is absent. It is not `better`.
5. **Someone else's body.** `look <player>` stores each equipment line as location `other`, holder that player, slot from the label. It does not copy those pieces into `carried`. A mobile's equipment is stored the same way and is not passed to `ask_next`. Shop and healer speech stay out of gear reports.
6. **A player's answer.** The reply to our question becomes one report on the piece we asked about. With `play.defer` true the claim stays empty and the raw text is kept. With defer false, a `gear_reply` prompt may set the claim to `better`, `worse`, `same`, or leave it empty. The prompt does not set `comparison`.
7. **Enchant.** The glow, fade, failure, and explode lines set `enchant` on the piece whose short text appears in the sentence. Explode also sets location empty. A later `compare` is a new comparison, not a change to `enchant`. `success` and `exceptional` clear `gear_level` and `level_block`. They do not store a new number.
8. **Practice list.** A bare `practice` reply replaces the `WeaponSkill` list. The percent is the integer before `%`. `You have <n> practice sessions left.` is stored on gear progress as `practices_left` and is not spent by this proposal.
9. **Wield band.** One of the seven wield sentences sets `wield_band` on the piece whose short text is in the sentence.
10. **Weapon type.** `Weapon type is <type>.` sets `weapon_type` when `<type>` is one of the eight skill names. Any other word leaves the type empty.
11. **Object level.** `level is <n>` in the identify summary sets `gear_level` to that integer. `You must be level <n> to use this object.` sets `gear_level` to `<n>` and `level_block` to `refused` on the piece just named. A score line at that level or higher clears `refused`.
12. **Alignment.** `Alignment: <n>. You are <word>.` or `You are <word>.` stores the alignment reading. The extra-flags clause sets `alignment_known` and `rejects` from `anti good`, `anti evil`, and `anti neutral` only. `You stop using <item>.` moves that piece to `carried`. `You are zapped by <item> and drop it.` moves that piece to `room`, sets `alignment_block` to `zapped`, and adds the stored side when one exists. `You are zapped by <item>.` moves that piece to `room`, sets `alignment_block`, and waits for the next score to name the side.

Identify's affect lines stay unparsed. They are the server text for an enchantment bonus. This proposal does not turn them into a skill percent, and it does not invent a bonus from `glows blue`. The summary's weight and value stay unparsed with them.

## Asking

The strategy asks only after `seen_on` has a slot we are willing to replace, and only a player. Mobiles and NPCs are not asked. One question per holder per slot per session. The report stores that the question was spent.

The line is `tell <name> <text>` when `tell` is known, otherwise `say <text>` when we are in the same room. The template, used when `play.defer` is true or the prompt is missing, is `What are you wearing on your <slot>?` For the wielded slot the template is `What weapon are you using?` The question does not ask them to give the item. A gift is a later `give`, and it is not in this proposal.

`allow_social` on this directive is false. An owed reply has already been sent by the engine. This question is not a greeting, and it does not replace one. The engine greeting still runs on a step where every strategy yields.

A claim that names a keyword we do not have is only a report. We `look` and `compare` a piece ourselves before any `wear` or `wield`. If we never hold it, the replace goal does not complete from the conversation.

## Goals

`goal.kind` gains `gear`. The existing `level` value is unchanged. A process may carry one goal or both. The config key `goals` is a list. A single `goal` mapping still means a one-element list, so a current level config stays valid.

```yaml
goals:
  - kind: level
    level: 5
    risk: steady
    minutes: 0
  - kind: gear
    action: replace
    slot: wielded
    risk: steady
```

`action` is `replace` or `enchant`. Anything else raises `ValueError("goal.action must be replace or enchant")`. `slot` is one of the slot names above. `replace` requires it. `enchant` uses it as the kind source: `wielded` means weapon, an armor slot means armor. Light, held, and floating raise `ValueError("goal.slot cannot be enchanted")`. `risk` uses the same three words as the level goal and does not move the level notch. A missing gear risk defaults to `steady`.

The level clock stays on `Progress`. Gear does not write notches, deaths, or experience. Gear met state is `GearProgress` on the memory document under `gearGoal`: the action, the slot, and `met`. `met` becomes true when the condition below holds, and a later `equipment` that shows a different short text in that slot clears it. `clear` on `WorkingMemory` drops gear pieces and gear progress with the other sections.

**Replace is met** when the worn piece in that slot has `comparison` `better` than the piece that was worn at the start of the goal, or the slot was empty and a looked piece is now worn there. A report does not meet it.

**Enchant is met** when the piece in that slot, or the carried spare we enchanted for that slot, has `enchant` `success` or `exceptional`, and a later compare against the previous worn piece is `better` or `same`. `failed` does not meet it. `destroyed` or `disenchanted` does not meet it. The goal stays open so another spare can be tried. It does not retry a piece whose `enchant` is already set.

Risk for enchant, because the spell can destroy the item:

| Ceiling | What may be enchanted |
| --- | --- |
| `cautious` | Nothing. The strategy does not send `cast`. Replace still runs. |
| `steady` | A carried spare from `enchant_spare`. The worn piece stays worn. |
| `bold` | That spare, or the worn piece after `remove` when `remove` is known. If `remove` is not known, bold uses the spare only. |

`steady` and `bold` send `cast` only when `cast` is known under `combat`, and only with the argument `enchant weapon` or `enchant armor` matching the kind. No other spell is sent. A piece whose `comparison` is `incomparable`, or whose kind is empty, is not a target.

## GearStrategy

`GearStrategy` subclasses `Strategy`. `direct(view, command_catalog, gear_catalog)` returns one `Directive` or nothing. The level algorithm's signature stays `direct(view, command_catalog)`. The context passes the gear catalog only to a strategy that accepts it. `LevelStrategy` does not wear, compare, or cast. The one gear fact it reads is `gear_gate` on the view, from the gear-level section.

The composition root installs a `SequenceStrategy` when more than one goal is configured, and when `PracticeStrategy` is installed beside a goal. `SequenceStrategy` is a `Strategy` whose `direct` calls each child in config order and returns the first directive. One field on the engine still holds a `Strategy`. The loop still does not name `LevelStrategy`, `PracticeStrategy`, or `GearStrategy`.

Order inside that sequence is the level goal first, then gear goals in the order written. `docs/proposals/Practice.md` inserts `PracticeStrategy` after level and before gear when that strategy is installed. While the level algorithm returns a hunt, a flee, or a rest, later children wait. Gear uses the step when every child before it returns nothing. One command per step still holds. A gear survey does not run during a fight the level strategy is holding.

`GearStrategy.direct` returns the first match. `allow_social` is false whenever it returns a directive.

1. **No worn snapshot this session.** `survey`, category `objects`, preference `equipment`.
2. **Wielded goal, and no `WeaponSkill` list yet.** `survey`, category `other`, preference `practice`, with no argument. One reading. A second step does not send `practice` again unless the list was cleared.
3. **A weapon or armor candidate that still needs a reading `identify` can fill, when `cast` is known.** `cast`, category `combat`, preference `cast`, argument `identify <keyword>`. One candidate per step. A wielded candidate qualifies when `weapon_type` is empty, `gear_level` is empty, or alignment is still unknown. An armor candidate qualifies when `gear_level` is empty or alignment is still unknown. Light, held, and floating do not take this step.
4. **Owned piece in `needs_look`.** `survey`, category `objects`, preference `look`, argument the keyword it is trying.
5. **Owned piece in `needs_compare`.** `survey`, category `objects`, preference `compare`, argument that keyword. One argument. The server picks the worn counterpart.
6. **Replace, and `skilled_replacement` has a piece.** `equip`, category `objects`, preference `wield` for the wielded slot, `hold` for held, otherwise `wear`, argument that piece's keyword. An armor slot uses the same query, and the skill rule does not remove armor pieces from it. A level-blocked piece is already out of the query. An alignment-blocked piece is already out, and so is a piece whose alignment is still unknown while the slot is worn.
7. **Replace, slot empty, and a carried piece for that slot is usable.** The same equip directive. An empty weapon slot uses the weapon-skill rank. When every carried weapon is unusable, level-blocked, or alignment-blocked, this step does not fire. One piece whose alignment is still unknown may be tried, once. An empty armor slot accepts a looked piece whose kind is `armor`, and it does not accept an unknown kind, a level-blocked piece, or an alignment-blocked piece. An empty hand stays empty rather than wear a potion.
8. **Enchant, and the ceiling allows a target from the catalog.** `cast`, category `combat`, preference `cast`, argument `enchant weapon <keyword>` or `enchant armor <keyword>`. A weapon target has already failed the unusable test inside `enchant_spare`.
9. **A player in the room is wearing a slot this goal replaces, and `ask_next` returns them.** `question`, category `information / communication`, preference `tell`, then `say`.
10. **Nothing.** Return nothing.

`get` from the room is not in this list. A ground piece can be recorded from a room look, and it is not picked up until a later phase pins weight and `get` replies. `drop` is not in this list. A worse piece stays carried.

The directive roles add `equip`, `cast`, and `question` to the set in the strategy proposal. The engine already sends `command` plus `argument`. `cast` is one argument string, including the spell name and the keyword.

## Where it sits in the step

1. Drain and observe. Gear parsers update `WorkingMemory` before any strategy runs.
2. Danger, leave-threat, stand, and an owed reply. Unchanged, and still ahead of every strategy.
3. `strategy.direct(...)`. A sequence asks level, then gear. When `PracticeStrategy` is installed, it is asked after level and before gear, as `docs/proposals/Practice.md` describes. When a personality is installed, `docs/proposals/Personality.md` may return a speak directive after the level child yields and before practice and gear are asked. A level hunt, flee, or rest is still returned as the level child wrote it. A gear `question` is still the gear line, and manner does not rewrite it.
4. Greeting when every strategy returns nothing and no personality is installed. A personality's speak directive is that greeting, on the opening that proposal names.
5. Wait.

A gear question does not skip an owed tell. A `compare` does not skip a flee.

## Types

| Type | File | Role |
| --- | --- | --- |
| `GearPiece` | `src/memory/GearPiece.py` | One piece and its look, compare, enchant, weapon type, wield band, object level, alignment restrictions, and reports. |
| `WeaponSkill` | `src/memory/WeaponSkill.py` | One practiced weapon skill: name and percent. |
| `GearCatalog` | `src/strategy/GearCatalog.py` | Queries over the piece list and the skill list. Not saved. |
| `GearStrategy` | `src/strategy/GearStrategy.py` | The gear algorithm. |
| `SequenceStrategy` | `src/strategy/SequenceStrategy.py` | First directive from an ordered list of strategies. |
| `GearProgress` | `src/goal/GearProgress.py` | Action, slot, and `met` for the gear goal. |

`WorkingMemory` gains the `gear` list, the `weaponSkills` list, `gear_goal`, and `alignment`. The knowledge document does not.

## Tests

`tests/test_gear_catalog.py` and `tests/test_gear_strategy.py`. No socket and no model.

- An equipment fixture with two `<worn on finger>` lines stores `finger` indexes 1 and 2 in print order.
- `a rusty sword looks better than a wooden sword.` sets `better` and `compared_to`. It does not set a number.
- `You can't compare those items.` sets `incomparable`. A report whose text says "it is better" leaves `comparison` empty.
- `replacement("wielded", 1)` returns the carried piece only when its comparison is `better` against the worn short text.
- `sword               80%` and `axe                 10%` from a practice listing store those two skills. A better axe at 10% is unusable. `skilled_replacement` returns the better sword at 80% and does not return the axe.
- `Weapon type is spear.` sets `weapon_type` to `spear`. The short text `a staff` does not.
- `You fumble and almost drop a rusty sword.` sets `wield_band` to `fumble`. A later replace does not wield it again.
- `Weight is 2, value is 100, level is 10.` sets `gear_level` to 10. It does not set `comparison`, and it does not store the weight or the value. The short text `a level 10 sword` does not set `gear_level`. A report that says the piece is level 10 does not either.
- `You must be level 15 to use this object.` sets `gear_level` to 15 and `level_block` to `refused`. A later replace does not wield it while the score level is 8. A score at level 15 clears the block, and `skilled_replacement` can return it.
- A better sword at object level 15 and a better usable mace at object level 9 set `gear_gate` to 9. A better axe at 10% skill does not set the gate. A sword that compares the same, at object level 20, does not set the gate.
- A `GoalView` with `met` true and `gear_gate` empty makes `LevelStrategy` return nothing. The same view with `gear_gate` 9 and a fresh `safe` mobile returns `kill`. The notch on the view is unchanged.
- `glows blue` sets `enchant` to `success` and clears `gear_level`. It does not store 11.
- `extra flags anti good.` with `Alignment: 800. You are saintly.` blocks that piece. The same flags with `Alignment: -800. You are demonic.` do not. `extra flags evil glow.` does not block a good character. `extra flags none.` stores an empty `rejects` list and `alignment_known`.
- `You are kind.` with no integer stores side `neutral`. `Alignment: 350. You are kind.` stores side `good`.
- `You stop using a wooden sword.` then `You are zapped by a silver sword and drop it.` while the side is `good` leaves the wooden sword `carried`, moves the silver sword to `room`, adds `good` to its `rejects`, and does not meet the replace goal. A later replace does not wear the silver sword.
- `You are zapped by a silver sword.` sets `alignment_block` to `zapped` and does not add a side. The next score line `You are evil.` adds `evil`.
- An occupied slot and unknown alignment does not send `wield`. An empty slot and unknown alignment sends one `wield`. A better anti-good sword does not set `gear_gate` while the side is `good`. A report that calls the sword anti-good does not set `rejects`.
- Bare `practice` is the survey when the wielded goal has no skill list. `practice sword` is not sent.
- `enchant_spare` skips the worn piece and skips a destroyed piece.
- Cautious enchant returns nothing when the only candidate is a spare. Steady returns `cast enchant weapon <keyword>` for that spare. The directive's category is `combat`.
- `cast` filed under a category other than `combat` is not sent.
- A help-only knowledge command list does not make `compare` available. That is the memory proposal's `known_commands` rule.
- `SequenceStrategy` with level then gear returns the level directive when the level child returns `kill`, and returns `compare` when the level child returns nothing. A sequence that also has practice is covered in `docs/proposals/Practice.md`.
- `look` on another player stores location `other` and `ask_next` returns that player once.
- `You do not have that item.` does not create a piece.
- `glows blue` sets `enchant` to `success`. `shivers violently and explodes` sets `destroyed`. Neither sets `comparison`.
- The knowledge `to_document` from a memory object that holds gear has no `gear` key. The memory document round-trips the piece.

## Phases

1. **Records and catalog.** Equipment, inventory, compare, and look parsers. `GearPiece` and `GearCatalog`. No telnet. No goal.
2. **Replace.** `GearStrategy` equip rules, the weapon-skill join, the object-level join, the alignment join, `gear_gate` on the view, `SequenceStrategy`, and `goal.kind: gear` with `action: replace`. Waits on the strategy and goal types those proposals introduce. Does not wait on voice prompts. The practice reading, the wield-band parser, the wear-refusal parser, the score-alignment parser, and the zap parser land in this phase. `cast identify` lands here only when the command list already has `cast`. The level algorithm's `met` rule reads `gear_gate` in this same phase.
3. **Ask.** Look at a player, one question, reports stored separately from compare. Agentic names first.
4. **Enchant.** Spare and bold rules, enchant reply lines, re-compare after a glow. `remove` only when the command list has it.
5. **Ground loot.** `get` a looked room piece when the slot is empty and score weight is under the maximum. This phase pins the `get` replies before it sends `get`.

## Gaps this proposal leaves in place

- Two identical short descriptions in the same place stay ambiguous. Version 1 does not send a numbered keyword.
- A player's claim can be wrong. The replace goal ignores it until our own `compare` agrees.
- `identify` also prints affect bonuses, weight, and value. This proposal reads `Weapon type is <type>.`, `level is <n>`, and the `anti good`, `anti evil`, and `anti neutral` phrases from that page. Affect, weight, and value text stay unused. The glow is still not a skill percent and still not a new object level. `bless` and `curse` are not cast, and a holy or malevolent aura does not change `rejects`.
- A weapon type guessed from the short description is not stored. A staff that uses the spear skill stays untyped until identify says `spear`.
- `practice <skill>` can raise a percent. This proposal never sends that form. `docs/proposals/Practice.md` is the session that does, and only for a name on the optimal or preference list that is still below adept. A clumsy sword is not practiced merely because the wield band was clumsy.
- `remove` is absent from the SUMMARY fallback. A worn piece cannot be enchanted on a character whose command list does not include `remove`, except by the steady path that enchants a spare already in the inventory.
- The area list and command categories are unchanged. The level clock's pace, `met`, and notch stay on the configured target. `gear_gate` extends an open-ended hunt and does not raise the notch. A budgeted goal that is already met does not keep hunting for a locked piece. A rejected alignment does not extend the hunt and does not choose which mobile to kill. Shop `list` prints an object level, and this proposal does not send `list` or `buy`.
- Giving, buying, and sacrificing gear are later actions. The objects category already contains `give`, `buy`, and `sacrifice`. No preference list here selects them.

## Implementation note

`docs/reference` describes the running code. Add the gear section to the working-memory reference in the phase that stores `GearPiece`. Until phase 1 lands, this file is the only description. The level strategy, the command catalog, and the two memory documents stay as their own proposals describe them.
